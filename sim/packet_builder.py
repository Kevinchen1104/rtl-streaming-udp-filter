"""Packet construction helpers, intentionally separate from classification."""

from __future__ import annotations

import struct
from dataclasses import dataclass


@dataclass(frozen=True)
class PacketFields:
    dst_mac: bytes = bytes.fromhex("02 00 00 00 00 01")
    src_mac: bytes = bytes.fromhex("02 00 00 00 00 02")
    ether_type: int = 0x0800
    version: int = 4
    ihl: int = 5
    dscp_ecn: int = 0
    identification: int = 0x1234
    df: bool = False
    mf: bool = False
    fragment_offset: int = 0
    ttl: int = 64
    protocol: int = 17
    ip_checksum: int = 0
    src_ip: int = 0xC0000201
    dst_ip: int = 0xC6336402
    src_port: int = 0x1234
    dst_port: int = 0xBEEF
    udp_checksum: int = 0


def build_frame(
    payload: bytes = b"",
    *,
    fields: PacketFields = PacketFields(),
    padding: bytes = b"",
    ip_total_length: int | None = None,
    udp_length: int | None = None,
) -> bytes:
    """Build raw Ethernet-II bytes without preamble, SFD, FCS, or checksums."""
    if len(fields.dst_mac) != 6 or len(fields.src_mac) != 6:
        raise ValueError("MAC addresses must be six bytes")
    actual_udp_length = 8 + len(payload) if udp_length is None else udp_length
    actual_ip_length = 20 + actual_udp_length if ip_total_length is None else ip_total_length
    flags_fragment = (
        (int(fields.df) << 14)
        | (int(fields.mf) << 13)
        | (fields.fragment_offset & 0x1FFF)
    )
    eth = fields.dst_mac + fields.src_mac + struct.pack("!H", fields.ether_type)
    ip = struct.pack(
        "!BBHHHBBHII",
        ((fields.version & 0xF) << 4) | (fields.ihl & 0xF),
        fields.dscp_ecn,
        actual_ip_length,
        fields.identification,
        flags_fragment,
        fields.ttl,
        fields.protocol,
        fields.ip_checksum,
        fields.src_ip,
        fields.dst_ip,
    )
    udp = struct.pack(
        "!HHHH",
        fields.src_port,
        fields.dst_port,
        actual_udp_length,
        fields.udp_checksum,
    )
    return eth + ip + udp + payload + padding


def replace_u16(frame: bytes, offset: int, value: int) -> bytes:
    mutable = bytearray(frame)
    mutable[offset : offset + 2] = struct.pack("!H", value & 0xFFFF)
    return bytes(mutable)
