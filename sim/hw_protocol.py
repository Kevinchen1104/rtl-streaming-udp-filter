"""Byte protocol between the host and fpga/basys3/hw_test_core.sv.

Host to board:
    0xA6                                  reset the filter; board answers 0xAC
    0xA5 port_hi port_lo msg_en msg stall len_hi len_lo <len frame bytes>
                                          run one frame through the filter

    stall (0-255) sets how often the board holds m_axis_tready and
    result_ready low for this frame; 0 never stalls.

Board to host, for each frame:
    0xB0 | last << 1 | error, data        one byte per payload beat
    0xC0, 20 bytes                        the result record: accept, reason,
                                          src_ip(4), dst_ip(4), src_port(2),
                                          dst_port(2), payload_len(2), sequence(4)
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sim.frames import descriptor_of, expected_output
from sim.reference_model import ReferenceResult


CMD_FRAME = 0xA5
CMD_RESET = 0xA6
RSP_RESET = 0xAC
TAG_BEAT = 0xB0
TAG_RESULT = 0xC0
RESULT_BYTES = 20
MAX_FRAME_BYTES = 4096 - 8  # RX FIFO depth minus the command header


class ProtocolError(RuntimeError):
    pass


def frame_command(frame: bytes, *, dst_port: int, msg_type_enable: bool,
                  msg_type: int, stall_level: int = 0) -> bytes:
    if not 0 < len(frame) <= MAX_FRAME_BYTES:
        raise ValueError(f"frame length {len(frame)} out of range")
    return bytes([
        CMD_FRAME, dst_port >> 8, dst_port & 0xFF, int(msg_type_enable),
        msg_type & 0xFF, stall_level & 0xFF, len(frame) >> 8, len(frame) & 0xFF,
    ]) + frame


@dataclass
class FrameResponse:
    beats: list[tuple[int, bool, bool]] = field(default_factory=list)  # data, last, error
    result: tuple[int, ...] = ()


class ResponseParser:
    """Turns the board's byte stream into FrameResponse objects."""

    def __init__(self) -> None:
        self._buffer = bytearray()
        self._current = FrameResponse()
        self.frames: list[FrameResponse] = []
        self.reset_acks = 0

    def feed(self, data: bytes) -> None:
        self._buffer += data
        while self._buffer:
            tag = self._buffer[0]
            if tag == RSP_RESET:
                del self._buffer[:1]
                self.reset_acks += 1
            elif tag & 0xFC == TAG_BEAT:
                if len(self._buffer) < 2:
                    return
                self._current.beats.append(
                    (self._buffer[1], bool(tag & 0x02), bool(tag & 0x01)))
                del self._buffer[:2]
            elif tag == TAG_RESULT:
                if len(self._buffer) < 1 + RESULT_BYTES:
                    return
                body = bytes(self._buffer[1:1 + RESULT_BYTES])
                del self._buffer[:1 + RESULT_BYTES]
                self._current.result = (
                    body[0], body[1],
                    int.from_bytes(body[2:6], "big"), int.from_bytes(body[6:10], "big"),
                    int.from_bytes(body[10:12], "big"), int.from_bytes(body[12:14], "big"),
                    int.from_bytes(body[14:16], "big"), int.from_bytes(body[16:20], "big"),
                )
                self.frames.append(self._current)
                self._current = FrameResponse()
            else:
                raise ProtocolError(f"unexpected byte 0x{tag:02X} from the board")


def check_response(response: FrameResponse, expected: ReferenceResult) -> list[str]:
    """Differences between what the board sent and what the model expects."""
    problems = []
    data = bytes(beat[0] for beat in response.beats)
    if data != expected_output(expected):
        problems.append(f"payload {data[:16].hex()}... != expected "
                        f"{expected_output(expected)[:16].hex()}...")
    if response.beats:
        if not response.beats[-1][1]:
            problems.append("final payload beat has last=0")
        if any(beat[1] for beat in response.beats[:-1]):
            problems.append("last=1 before the final payload beat")
        if response.beats[-1][2] != expected.terminal_error:
            problems.append(f"final error={response.beats[-1][2]}, "
                            f"expected {expected.terminal_error}")
    if response.result != descriptor_of(expected):
        problems.append(f"result {response.result} != expected {descriptor_of(expected)}")
    return problems
