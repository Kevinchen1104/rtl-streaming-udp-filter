"""Whole-frame reference classifier for the v1 protocol subset.

The model looks at a complete, already-delimited frame and walks the checks
in the order given by the specification. The first check that fails decides
the reason. A check whose field is not fully present in the frame reports
BAD_LENGTH_OR_TRUNCATED.
"""

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


ETH_HEADER_BYTES = 14
IPV4_HEADER_BYTES = 20
UDP_HEADER_BYTES = 8
PAYLOAD_OFFSET = ETH_HEADER_BYTES + IPV4_HEADER_BYTES + UDP_HEADER_BYTES


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
    """Classify one frame. See docs/spec.md, section "Result reasons"."""
    sequence &= 0xFFFF_FFFF
    size = len(frame)
    truncated = Reason.BAD_LENGTH_OR_TRUNCATED

    def has(end: int) -> bool:
        """True when bytes [0, end) are all present."""
        return size >= end

    def result(reason: Reason, **fields: object) -> ReferenceResult:
        return ReferenceResult(
            accept=reason is Reason.ACCEPT,
            reason=reason,
            sequence=sequence,
            **fields,
        )

    # Eligibility checks, in specification order.
    if not has(14):
        return result(truncated)
    if _u16(frame, 12) != 0x0800:
        return result(Reason.NON_IPV4)
    if not has(15):
        return result(truncated)
    if frame[14] >> 4 != 4 or frame[14] & 0xF != 5:
        return result(Reason.BAD_IPV4_HEADER)
    if not has(18):
        return result(truncated)
    ip_total_length = _u16(frame, 16)
    logical_length = ETH_HEADER_BYTES + ip_total_length
    if logical_length > max_logical_frame_bytes:
        return result(Reason.FRAME_TOO_LONG, logical_frame_length=logical_length)
    if not has(24):
        return result(truncated, logical_frame_length=logical_length)
    if frame[23] != 17:
        return result(Reason.NON_UDP, logical_frame_length=logical_length)
    if _u16(frame, 20) & 0x3FFF:
        return result(Reason.FRAGMENTED, logical_frame_length=logical_length)

    # Metadata fields are reported once they are complete.
    metadata = dict(
        src_ip=_u32(frame, 26) if has(30) else 0,
        dst_ip=_u32(frame, 30) if has(34) else 0,
        src_port=_u16(frame, 34) if has(36) else 0,
        dst_port=_u16(frame, 36) if has(38) else 0,
        logical_frame_length=logical_length,
    )

    # Structure: complete UDP header, consistent lengths, complete datagram.
    if not has(PAYLOAD_OFFSET):
        return result(truncated, **metadata)
    udp_length = _u16(frame, 38)
    if (
        ip_total_length < IPV4_HEADER_BYTES + UDP_HEADER_BYTES
        or udp_length < UDP_HEADER_BYTES
        or udp_length != ip_total_length - IPV4_HEADER_BYTES
    ):
        return result(truncated, **metadata)

    payload_length = udp_length - UDP_HEADER_BYTES
    available = frame[PAYLOAD_OFFSET:logical_length]
    metadata.update(
        payload_len=payload_length,
        padding_length=max(0, size - logical_length),
    )
    port_matches = metadata["dst_port"] == (dst_port & 0xFFFF)
    message_matches = not msg_type_enable or (
        len(available) > 0 and available[0] == (msg_type & 0xFF)
    )

    if len(available) < payload_length:
        # Payload is forwarded while the frame still passes both filters, so
        # a truncated candidate can leave a partial, error-terminated stream.
        forwarded = available if port_matches and message_matches else b""
        return result(
            truncated,
            speculative_payload=forwarded,
            terminal_error=bool(forwarded),
            **metadata,
        )

    # Filters.
    if not port_matches:
        return result(Reason.DST_PORT_MISMATCH, **metadata)
    if msg_type_enable and not message_matches:
        return result(Reason.MSG_TYPE_MISMATCH, **metadata)

    return result(
        Reason.ACCEPT,
        expected_payload=available,
        speculative_payload=available,
        **metadata,
    )
