"""Declarative, whole-frame reference classifier for the v1 protocol subset."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class Reason(IntEnum):
    ACCEPT = 0
    NON_IPV4 = 1
    BAD_IPV4_HEADER = 2
    NON_UDP = 3
    FRAGMENTED = 4
    BAD_LENGTH_OR_TRUNCATED = 5
    DST_PORT_MISMATCH = 6
    MSG_TYPE_MISMATCH = 7
    FRAME_TOO_LONG = 8


@dataclass(frozen=True)
class ReferenceResult:
    accept: bool
    reason: Reason
    src_ip: int = 0
    dst_ip: int = 0
    src_port: int = 0
    dst_port: int = 0
    payload_len: int = 0
    expected_payload: bytes = b""
    speculative_payload: bytes = b""
    terminal_error: bool = False
    sequence: int = 0
    logical_frame_length: int = 0
    padding_length: int = 0


def _u16(frame: bytes, offset: int) -> int:
    return int.from_bytes(frame[offset : offset + 2], "big")


def _u32(frame: bytes, offset: int) -> int:
    return int.from_bytes(frame[offset : offset + 4], "big")


def classify_frame(
    frame: bytes,
    *,
    dst_port: int,
    msg_type_enable: bool,
    msg_type: int,
    max_logical_frame_bytes: int = 2048,
    sequence: int = 0,
) -> ReferenceResult:
    """Classify one already-delimited frame without mirroring the RTL FSM.

    Eligibility fields are evaluated only when their complete bytes exist.
    The logical-frame maximum becomes decisive when the IPv4 total-length
    field completes at byte 17. Fragment status is held until protocol byte 23,
    where NON_UDP takes priority over FRAGMENTED.
    """
    sequence &= 0xFFFF_FFFF

    def result(reason: Reason, **kwargs: object) -> ReferenceResult:
        return ReferenceResult(
            accept=reason is Reason.ACCEPT,
            reason=reason,
            sequence=sequence,
            **kwargs,
        )

    if len(frame) < 14:
        return result(Reason.BAD_LENGTH_OR_TRUNCATED)
    if _u16(frame, 12) != 0x0800:
        return result(Reason.NON_IPV4)
    if len(frame) < 15:
        return result(Reason.BAD_LENGTH_OR_TRUNCATED)
    if frame[14] >> 4 != 4 or frame[14] & 0xF != 5:
        return result(Reason.BAD_IPV4_HEADER)
    if len(frame) < 18:
        return result(Reason.BAD_LENGTH_OR_TRUNCATED)

    ip_total_length = _u16(frame, 16)
    logical_length = 14 + ip_total_length
    if logical_length > max_logical_frame_bytes:
        return result(
            Reason.FRAME_TOO_LONG,
            logical_frame_length=logical_length,
        )
    if len(frame) < 24:
        return result(
            Reason.BAD_LENGTH_OR_TRUNCATED,
            logical_frame_length=logical_length,
        )
    if frame[23] != 17:
        return result(Reason.NON_UDP, logical_frame_length=logical_length)
    flags_fragment = _u16(frame, 20)
    if flags_fragment & 0x3FFF:
        return result(Reason.FRAGMENTED, logical_frame_length=logical_length)

    src_ip = _u32(frame, 26) if len(frame) >= 30 else 0
    dst_ip = _u32(frame, 30) if len(frame) >= 34 else 0
    if len(frame) < 34:
        return result(
            Reason.BAD_LENGTH_OR_TRUNCATED,
            src_ip=src_ip,
            dst_ip=dst_ip,
            logical_frame_length=logical_length,
        )
    src_port = _u16(frame, 34) if len(frame) >= 36 else 0
    observed_dst_port = _u16(frame, 36) if len(frame) >= 38 else 0
    if len(frame) < 42:
        return result(
            Reason.BAD_LENGTH_OR_TRUNCATED,
            src_ip=src_ip,
            dst_ip=dst_ip,
            src_port=src_port,
            dst_port=observed_dst_port,
            logical_frame_length=logical_length,
        )

    udp_length = _u16(frame, 38)
    if ip_total_length < 28 or udp_length < 8 or udp_length != ip_total_length - 20:
        return result(
            Reason.BAD_LENGTH_OR_TRUNCATED,
            src_ip=src_ip,
            dst_ip=dst_ip,
            src_port=src_port,
            dst_port=observed_dst_port,
            logical_frame_length=logical_length,
        )

    payload_length = udp_length - 8
    common = dict(
        src_ip=src_ip,
        dst_ip=dst_ip,
        src_port=src_port,
        dst_port=observed_dst_port,
        payload_len=payload_length,
        logical_frame_length=logical_length,
        padding_length=max(0, len(frame) - logical_length),
    )
    # Structural validation and the premature close happen together on UDP
    # byte 41. No filter reject has entered drain yet, so truncation wins.
    if payload_length > 0 and len(frame) == 42:
        return result(Reason.BAD_LENGTH_OR_TRUNCATED, **common)
    if observed_dst_port != (dst_port & 0xFFFF):
        return result(Reason.DST_PORT_MISMATCH, **common)
    if payload_length == 0:
        return result(
            Reason.MSG_TYPE_MISMATCH if msg_type_enable else Reason.ACCEPT,
            **common,
        )

    available_payload = frame[42 : min(len(frame), logical_length)]
    if msg_type_enable:
        if not available_payload:
            return result(Reason.BAD_LENGTH_OR_TRUNCATED, **common)
        if available_payload[0] != (msg_type & 0xFF):
            # Truncation wins only when the mismatching first byte also closes
            # a frame that declared additional payload. If a later byte closes
            # the frame, the earlier message mismatch is already decisive.
            if len(available_payload) == 1 and payload_length > 1:
                return result(Reason.BAD_LENGTH_OR_TRUNCATED, **common)
            return result(Reason.MSG_TYPE_MISMATCH, **common)

    if len(available_payload) < payload_length:
        return result(
            Reason.BAD_LENGTH_OR_TRUNCATED,
            speculative_payload=available_payload,
            terminal_error=bool(available_payload),
            **common,
        )

    payload = available_payload[:payload_length]
    return result(
        Reason.ACCEPT,
        expected_payload=payload,
        speculative_payload=payload,
        **common,
    )
