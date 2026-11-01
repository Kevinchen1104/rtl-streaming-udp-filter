"""Test frames and expected results shared by the cocotb tests and the
Basys 3 hardware test. Nothing here depends on cocotb.
"""

from __future__ import annotations

import random
from dataclasses import asdict, dataclass

from sim.packet_builder import PacketFields, build_frame
from sim.reference_model import ReferenceResult, classify_frame


PORT = 0xBEEF
MSG = 0xA5


def model(frame: bytes, sequence: int, msg_enabled: bool = False) -> ReferenceResult:
    return classify_frame(
        frame,
        dst_port=PORT,
        msg_type_enable=msg_enabled,
        msg_type=MSG,
        sequence=sequence,
    )


def descriptor_of(expected: ReferenceResult) -> tuple[int, ...]:
    return (
        int(expected.accept), int(expected.reason), expected.src_ip,
        expected.dst_ip, expected.src_port, expected.dst_port,
        expected.payload_len, expected.sequence,
    )


def expected_output(expected: ReferenceResult) -> bytes:
    return expected.expected_payload if expected.accept else expected.speculative_payload


def directed_cases() -> list[tuple[str, bytes, bool]]:
    other_port = PacketFields(dst_port=0x1234)
    return [
        ("minimal_zero", build_frame(), False),
        ("one_byte", build_frame(b"x"), False),
        ("multi_byte", build_frame(b"abcdef"), False),
        ("msg_one", build_frame(bytes([MSG])), True),
        ("msg_multi", build_frame(bytes([MSG]) + b"hello"), True),
        ("padding", build_frame(b"abc", padding=b"\x00" * 20), False),
        ("df0", build_frame(b"x", fields=PacketFields(df=False)), False),
        ("df1", build_frame(b"x", fields=PacketFields(df=True)), False),
        ("non_ipv4", build_frame(fields=PacketFields(ether_type=0x0806)), False),
        ("bad_version", build_frame(fields=PacketFields(version=6)), False),
        ("ihl4", build_frame(fields=PacketFields(ihl=4)), False),
        ("ihl6", build_frame(fields=PacketFields(ihl=6)), False),
        ("tcp", build_frame(fields=PacketFields(protocol=6)), False),
        ("icmp", build_frame(fields=PacketFields(protocol=1)), False),
        ("mf", build_frame(fields=PacketFields(mf=True)), False),
        ("fragment_offset", build_frame(fields=PacketFields(fragment_offset=3)), False),
        ("port_mismatch", build_frame(b"abc", fields=other_port), False),
        ("port_mismatch_closes_at_udp_header",
         build_frame(b"x", fields=other_port)[:42], False),
        ("port_mismatch_then_late_truncation",
         build_frame(b"abcdef", fields=other_port)[:45], False),
        ("port_mismatch_with_padding",
         build_frame(b"abc", fields=other_port, padding=b"\x00" * 8), False),
        ("message_mismatch", build_frame(b"\x00abc"), True),
        ("message_mismatch_closes_on_first_byte", build_frame(b"\x00abc")[:43], True),
        ("message_mismatch_then_late_truncation", build_frame(b"\x00abc")[:44], True),
        ("message_empty", build_frame(), True),
        ("ip_short", build_frame(ip_total_length=27, udp_length=7), False),
        ("udp_short", build_frame(ip_total_length=28, udp_length=7), False),
        ("udp_long_relation", build_frame(b"x", ip_total_length=29, udp_length=10), False),
        ("udp_short_relation", build_frame(b"xy", ip_total_length=30, udp_length=9), False),
        ("too_long", build_frame(b"x", ip_total_length=2040), False),
        ("late_first", build_frame(b"abcd")[:43], False),
        ("late_middle", build_frame(b"abcd")[:44], False),
        ("late_before_final", build_frame(b"abcd")[:45], False),
        ("long_padding", build_frame(b"abc", padding=b"\x55" * 1024), False),
        ("maximum_logical",
         build_frame(bytes((i * 17) & 0xFF for i in range(2006))), False),
    ]


# Category weights out of 100. Accepted frames are weighted up so the payload
# path and output backpressure see plenty of traffic.
CATEGORY_WEIGHTS = {
    "accept": 34,
    "non_ipv4": 5,
    "bad_ipv4_header": 5,
    "non_udp": 5,
    "fragmented": 5,
    "frame_too_long": 4,
    "bad_length": 4,
    "truncated": 14,
    "port_mismatch": 8,
    "msg_mismatch": 8,
    "filter_reject_truncated": 8,
}


@dataclass
class RandomCase:
    frame: bytes
    msg_enabled: bool
    df: bool
    truncation: str = "none"


def _random_payload(rng: random.Random, minimum: int = 0) -> bytes:
    low, high = rng.choice([(0, 0), (1, 1), (2, 7), (8, 63), (64, 255), (256, 600)])
    size = max(minimum, rng.randint(low, high))
    return bytes(rng.randrange(256) for _ in range(size))


def _with_message(payload: bytes, message: int) -> bytes:
    return bytes([message]) + payload[1:] if payload else payload


def random_case(rng: random.Random, category: str) -> RandomCase:
    df = bool(rng.getrandbits(1))
    msg_enabled = bool(rng.getrandbits(1))
    fields = PacketFields(
        df=df,
        src_ip=rng.randrange(1 << 32),
        dst_ip=rng.randrange(1 << 32),
        src_port=rng.randrange(1 << 16),
        dst_port=PORT,
    )
    padding = (
        bytes(rng.randrange(256) for _ in range(rng.randint(1, 40)))
        if rng.random() < 0.25 else b""
    )
    payload = _random_payload(rng)
    if msg_enabled:
        payload = _with_message(payload, MSG)

    def changed(**kwargs: object) -> PacketFields:
        return PacketFields(**{**asdict(fields), **kwargs})

    if category == "accept":
        if msg_enabled and not payload:
            msg_enabled = False
        return RandomCase(build_frame(payload, fields=fields, padding=padding), msg_enabled, df)
    if category == "non_ipv4":
        ether_type = rng.choice([0x86DD, 0x0806, 0x8100])
        return RandomCase(build_frame(payload, fields=changed(ether_type=ether_type),
                                      padding=padding), msg_enabled, df)
    if category == "bad_ipv4_header":
        bad = rng.choice([{"version": 6}, {"version": 0}, {"ihl": 4}, {"ihl": 6}, {"ihl": 15}])
        return RandomCase(build_frame(payload, fields=changed(**bad), padding=padding),
                          msg_enabled, df)
    if category == "non_udp":
        protocol = rng.choice([1, 6, 58])
        return RandomCase(build_frame(payload, fields=changed(protocol=protocol),
                                      padding=padding), msg_enabled, df)
    if category == "fragmented":
        bad = rng.choice([{"mf": True}, {"fragment_offset": rng.randint(1, 0x1FFF)}])
        return RandomCase(build_frame(payload, fields=changed(**bad), padding=padding),
                          msg_enabled, df)
    if category == "frame_too_long":
        total = rng.randint(2035, 0xFFFF)
        return RandomCase(build_frame(b"", fields=fields, ip_total_length=total,
                                      udp_length=total - 20), msg_enabled, df)
    if category == "bad_length":
        udp_length = 8 + len(payload)
        total = rng.choice([
            rng.randint(20, 27),                 # IPv4 total length too short
            udp_length + 20 + rng.randint(1, 4),  # lengths disagree
        ])
        return RandomCase(build_frame(payload, fields=fields, ip_total_length=total,
                                      udp_length=udp_length), msg_enabled, df)
    if category in {"port_mismatch", "msg_mismatch"}:
        if category == "port_mismatch":
            fields = changed(dst_port=rng.choice([0x0000, 0x1234, PORT ^ 0x0001, 0xFFFF]))
        else:
            msg_enabled = True
            payload = _with_message(payload, MSG ^ rng.randint(1, 0xFF))
        return RandomCase(build_frame(payload, fields=fields, padding=padding), msg_enabled, df)
    if category == "truncated":
        region = rng.choice(["ethernet", "ipv4", "udp", "first_payload", "later_payload"])
        payload = _random_payload(rng, minimum=3)
        if msg_enabled:
            payload = _with_message(payload, MSG)
        full = build_frame(payload, fields=fields)
        end = {
            "ethernet": lambda: rng.randint(1, 13),
            "ipv4": lambda: rng.randint(14, 33),
            "udp": lambda: rng.randint(34, 41),
            "first_payload": lambda: 43,
            "later_payload": lambda: rng.randint(44, len(full) - 1),
        }[region]()
        return RandomCase(full[:end], msg_enabled, df, region)
    if category == "filter_reject_truncated":
        payload = _random_payload(rng, minimum=3)
        if rng.getrandbits(1):
            fields = changed(dst_port=PORT ^ 0x00FF)
            if msg_enabled:
                payload = _with_message(payload, MSG)
        else:
            msg_enabled = True
            payload = _with_message(payload, MSG ^ 0x5A)
        full = build_frame(payload, fields=fields)
        return RandomCase(full[:rng.randint(42, len(full) - 1)], msg_enabled, df,
                          "after_filter_reject")
    raise ValueError(category)
