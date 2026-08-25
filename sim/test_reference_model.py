from __future__ import annotations

from pathlib import Path

import pytest

from sim.packet_builder import PacketFields, build_frame, replace_u16
from sim.reference_model import Reason, classify_frame


PORT = 0xBEEF
RAW = Path(__file__).parent / "raw_vectors"


def load_hex(name: str) -> bytes:
    return bytes.fromhex((RAW / name).read_text(encoding="ascii"))


def classify(frame: bytes, **kwargs: object):
    options = dict(dst_port=PORT, msg_type_enable=False, msg_type=0xA5)
    options.update(kwargs)
    return classify_frame(frame, **options)


def test_hand_written_big_endian_minimal_vector() -> None:
    result = classify(load_hex("accepted_minimal.hex"), sequence=0x1020_3040)
    assert result.reason is Reason.ACCEPT
    assert result.src_ip == 0xC000_0201
    assert result.dst_ip == 0xC633_6402
    assert result.src_port == 0x1234
    assert result.dst_port == 0xBEEF
    assert result.payload_len == 0
    assert result.sequence == 0x1020_3040


def test_hand_written_non_ipv4_vector() -> None:
    result = classify(load_hex("rejected_non_ipv4.hex"))
    assert result.reason is Reason.NON_IPV4
    assert result.src_ip == result.dst_ip == 0


def test_hand_written_late_truncation_vector() -> None:
    result = classify(load_hex("truncated_payload.hex"))
    assert result.reason is Reason.BAD_LENGTH_OR_TRUNCATED
    assert result.payload_len == 4
    assert result.speculative_payload == b"\xaa\xbb"
    assert result.terminal_error


@pytest.mark.parametrize("payload", [b"", b"\x11", b"abcdef", bytes(range(64))])
def test_port_only_accepts_and_returns_payload(payload: bytes) -> None:
    result = classify(build_frame(payload))
    assert result.accept
    assert result.expected_payload == payload
    assert result.payload_len == len(payload)


@pytest.mark.parametrize("payload", [b"\xa5", b"\xa5hello"])
def test_message_filter_accepts_match(payload: bytes) -> None:
    result = classify(build_frame(payload), msg_type_enable=True)
    assert result.accept
    assert result.expected_payload == payload


def test_padding_is_not_payload() -> None:
    result = classify(build_frame(b"abc", padding=bytes(range(128))))
    assert result.reason is Reason.ACCEPT
    assert result.expected_payload == b"abc"
    assert result.padding_length == 128


@pytest.mark.parametrize("df", [False, True])
def test_df_is_ignored(df: bool) -> None:
    assert classify(build_frame(b"x", fields=PacketFields(df=df))).accept


@pytest.mark.parametrize(
    ("frame", "reason"),
    [
        (build_frame(fields=PacketFields(ether_type=0x86DD)), Reason.NON_IPV4),
        (build_frame(fields=PacketFields(version=6)), Reason.BAD_IPV4_HEADER),
        (build_frame(fields=PacketFields(ihl=4)), Reason.BAD_IPV4_HEADER),
        (build_frame(fields=PacketFields(ihl=6)), Reason.BAD_IPV4_HEADER),
        (build_frame(fields=PacketFields(protocol=6)), Reason.NON_UDP),
        (build_frame(fields=PacketFields(protocol=1)), Reason.NON_UDP),
        (build_frame(fields=PacketFields(mf=True)), Reason.FRAGMENTED),
        (build_frame(fields=PacketFields(fragment_offset=1)), Reason.FRAGMENTED),
    ],
)
def test_eligibility_reasons(frame: bytes, reason: Reason) -> None:
    assert classify(frame).reason is reason


def test_non_udp_priority_over_fragmented() -> None:
    frame = build_frame(fields=PacketFields(protocol=6, mf=True))
    assert classify(frame).reason is Reason.NON_UDP


def test_destination_mismatch_precedes_message_filter() -> None:
    frame = build_frame(b"\x00", fields=PacketFields(dst_port=0x1234))
    result = classify(frame, msg_type_enable=True)
    assert result.reason is Reason.DST_PORT_MISMATCH
    assert result.payload_len == 1
    assert result.speculative_payload == b""


def test_udp_header_close_truncation_precedes_same_cycle_port_reject() -> None:
    frame = build_frame(b"x", fields=PacketFields(dst_port=0x1234))[:42]
    assert classify(frame).reason is Reason.BAD_LENGTH_OR_TRUNCATED


def test_message_mismatch_and_empty_message_payload() -> None:
    assert classify(build_frame(b"\x00"), msg_type_enable=True).reason is Reason.MSG_TYPE_MISMATCH
    assert classify(build_frame(), msg_type_enable=True).reason is Reason.MSG_TYPE_MISMATCH


@pytest.mark.parametrize(
    "frame",
    [
        build_frame(ip_total_length=27, udp_length=7),
        build_frame(ip_total_length=28, udp_length=7),
        build_frame(b"x", ip_total_length=29, udp_length=10),
        build_frame(b"xy", ip_total_length=30, udp_length=9),
    ],
)
def test_invalid_length_relationships(frame: bytes) -> None:
    result = classify(frame)
    assert result.reason is Reason.BAD_LENGTH_OR_TRUNCATED
    assert result.payload_len == 0


def test_frame_too_long_is_decided_when_total_length_is_complete() -> None:
    frame = build_frame(b"x", ip_total_length=0x0800)[:18]
    result = classify(frame)
    assert result.reason is Reason.FRAME_TOO_LONG
    assert result.logical_frame_length == 2062


@pytest.mark.parametrize("end", range(1, 43))
def test_header_truncation_sweep(end: int) -> None:
    frame = build_frame(b"abcd")[:end]
    assert classify(frame).reason is Reason.BAD_LENGTH_OR_TRUNCATED


@pytest.mark.parametrize("actual", [1, 2, 3])
def test_payload_truncation_is_speculative_and_error_terminated(actual: int) -> None:
    frame = build_frame(b"abcd")[: 42 + actual]
    result = classify(frame)
    assert result.reason is Reason.BAD_LENGTH_OR_TRUNCATED
    assert result.speculative_payload == b"abcd"[:actual]
    assert result.terminal_error


def test_first_byte_message_mismatch_plus_early_last_is_truncation() -> None:
    frame = build_frame(b"\x00rest")[:43]
    result = classify(frame, msg_type_enable=True)
    assert result.reason is Reason.BAD_LENGTH_OR_TRUNCATED
    assert result.speculative_payload == b""


def test_message_mismatch_remains_decisive_on_later_truncation() -> None:
    frame = build_frame(b"\x00rest")[:44]
    result = classify(frame, msg_type_enable=True)
    assert result.reason is Reason.MSG_TYPE_MISMATCH
    assert result.speculative_payload == b""


def test_complete_message_mismatch_emits_nothing() -> None:
    result = classify(build_frame(b"\x00rest"), msg_type_enable=True)
    assert result.reason is Reason.MSG_TYPE_MISMATCH
    assert result.speculative_payload == b""


def test_metadata_commits_only_on_complete_field() -> None:
    frame = build_frame(b"x")
    assert classify(frame[:29]).src_ip == 0
    assert classify(frame[:30]).src_ip == 0xC0000201
    assert classify(frame[:33]).dst_ip == 0
    assert classify(frame[:34]).dst_ip == 0xC6336402
    assert classify(frame[:35]).src_port == 0
    assert classify(frame[:36]).src_port == 0x1234
    assert classify(frame[:37]).dst_port == 0
    assert classify(frame[:38]).dst_port == 0xBEEF


def test_sequence_wraps_to_32_bits() -> None:
    assert classify(build_frame(), sequence=0x1_0000_0001).sequence == 1


def test_maximum_supported_logical_length() -> None:
    payload = bytes((index * 17) & 0xFF for index in range(2006))
    result = classify(build_frame(payload))
    assert result.accept
    assert result.logical_frame_length == 2048
    assert result.payload_len == 2006


def test_replace_u16_helper_is_big_endian() -> None:
    frame = replace_u16(build_frame(), 36, 0x1234)
    assert frame[36:38] == b"\x12\x34"
