"""cocotb tests for udp_packet_filter.

Each scenario is its own cocotb test, so the JUnit report lists every scenario
with its own result. Tests that measure latency, throughput, or coverage also
write JSON under results/raw/ for scripts/generate_results.py.

Inputs are driven on the falling edge and sampled 1 ns later, so every value
checked here is the value the DUT sees at the next rising edge.
"""

from __future__ import annotations

import json
import os
import random
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

import cocotb
from cocotb import Param
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, Timer

from sim import coverage
from sim.packet_builder import PacketFields, build_frame
from sim.reference_model import Reason, ReferenceResult, classify_frame


PORT = 0xBEEF
MSG = 0xA5
SEEDS = [1, 7, 42, 2027]
FRAMES_PER_SEED = 200
CLOCK_PERIOD_NS = 10


@dataclass
class RunOptions:
    input_gap: Callable[[int], bool] | None = None
    output_ready: Callable[[int], bool] | None = None
    result_ready: Callable[[int, bool], bool] | None = None
    change_config_midframe: bool = False
    probe_next_frame: bool = False
    check_ready_isolation: bool = False
    # If set, run_frame appends one snapshot of the DUT ports per cycle.
    trace: list[dict[str, int]] | None = None


@dataclass
class RunMetrics:
    first_input_handshake_cycle: int | None = None
    udp_header_final_handshake_cycle: int | None = None
    first_payload_input_handshake_cycle: int | None = None
    first_payload_output_valid_cycle: int | None = None
    first_payload_output_handshake_cycle: int | None = None
    final_payload_output_handshake_cycle: int | None = None
    input_frame_closing_handshake_cycle: int | None = None
    result_valid_cycle: int | None = None
    result_handshake_cycle: int | None = None
    saw_input_gap: bool = False
    saw_output_stall: bool = False
    saw_result_stall: bool = False
    payload_output_handshake_cycles: list[int] = field(default_factory=list)


def value(signal) -> int:
    return int(signal.value)


def raw_dir(*parts: str) -> Path:
    path = Path(os.environ["UDP_FILTER_REPO_ROOT"]) / "results" / "raw"
    for part in parts:
        path = path / part
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n"
    )


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


def read_descriptor(dut) -> tuple[int, ...]:
    return (
        value(dut.result_accept), value(dut.result_reason),
        value(dut.result_src_ip), value(dut.result_dst_ip),
        value(dut.result_src_port), value(dut.result_dst_port),
        value(dut.result_payload_len), value(dut.result_sequence),
    )


def expected_output(expected: ReferenceResult) -> bytes:
    return expected.expected_payload if expected.accept else expected.speculative_payload


async def drive_idle(dut) -> None:
    dut.s_axis_tdata.value = 0
    dut.s_axis_tvalid.value = 0
    dut.s_axis_tlast.value = 0
    dut.cfg_dst_port.value = PORT
    dut.cfg_msg_type_enable.value = 0
    dut.cfg_msg_type.value = MSG
    dut.m_axis_tready.value = 0
    dut.result_ready.value = 0


async def reset_dut(dut, cycles: int = 3) -> None:
    await drive_idle(dut)
    dut.rst_n.value = 0
    await Timer(1, unit="ns")
    for _ in range(cycles):
        await RisingEdge(dut.clk)
        assert value(dut.s_axis_tready) == 0
        assert value(dut.m_axis_tvalid) == 0
        assert value(dut.result_valid) == 0
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)


async def start(dut) -> None:
    cocotb.start_soon(Clock(dut.clk, CLOCK_PERIOD_NS, unit="ns").start())
    await reset_dut(dut)


async def check_ready_isolation(dut) -> None:
    """Flip m_axis_tready inside the cycle; s_axis_tready must not follow."""
    ready_before = value(dut.s_axis_tready)
    original = value(dut.m_axis_tready)
    dut.m_axis_tready.value = 1 - original
    await Timer(1, unit="ns")
    assert value(dut.s_axis_tready) == ready_before, (
        "m_axis_tready reached s_axis_tready through combinational logic"
    )
    dut.m_axis_tready.value = original
    await Timer(1, unit="ns")


async def run_frame(
    dut,
    frame: bytes,
    expected: ReferenceResult,
    *,
    msg_type_enable: bool = False,
    options: RunOptions | None = None,
) -> RunMetrics:
    """Drive one frame, monitor every cycle, and compare with the model."""
    options = options or RunOptions()
    source_index = 0
    source_active = False
    output_beats: list[tuple[int, bool, bool]] = []
    descriptor = None
    metrics = RunMetrics()
    prior_output_stall = None
    prior_result_stall = None
    prior_counters = (value(dut.header_index), value(dut.payload_left))
    prior_input_handshake = False

    dut.cfg_dst_port.value = PORT
    dut.cfg_msg_type_enable.value = int(msg_type_enable)
    dut.cfg_msg_type.value = MSG
    dut.s_axis_tvalid.value = 0
    cycle = 0

    while descriptor is None:
        await FallingEdge(dut.clk)

        if source_index < len(frame) and not source_active:
            permit = True if options.input_gap is None else options.input_gap(cycle)
            if permit:
                source_active = True
            else:
                metrics.saw_input_gap = True
        if source_active:
            dut.s_axis_tvalid.value = 1
            dut.s_axis_tdata.value = frame[source_index]
            dut.s_axis_tlast.value = int(source_index == len(frame) - 1)
        else:
            dut.s_axis_tvalid.value = 0
            dut.s_axis_tlast.value = 0
        if options.probe_next_frame and source_index == len(frame):
            # Offer the next frame's first byte early; it must not transfer
            # while this frame's descriptor is pending.
            dut.s_axis_tvalid.value = 1
            dut.s_axis_tdata.value = 0xD5
            dut.s_axis_tlast.value = 0

        ready = True if options.output_ready is None else options.output_ready(cycle)
        dut.m_axis_tready.value = int(ready)
        result_is_valid = bool(value(dut.result_valid))
        rr = True if options.result_ready is None else options.result_ready(cycle, result_is_valid)
        dut.result_ready.value = int(rr)

        if options.change_config_midframe and source_index > 0:
            dut.cfg_dst_port.value = PORT ^ 0xFFFF
            dut.cfg_msg_type_enable.value = int(not msg_type_enable)
            dut.cfg_msg_type.value = MSG ^ 0xFF

        await Timer(1, unit="ns")
        if options.check_ready_isolation:
            await check_ready_isolation(dut)

        in_hs = bool(value(dut.s_axis_tvalid) and value(dut.s_axis_tready))
        out_valid = bool(value(dut.m_axis_tvalid))
        out_hs = bool(out_valid and value(dut.m_axis_tready))
        res_valid = bool(value(dut.result_valid))
        res_hs = bool(res_valid and value(dut.result_ready))

        if options.trace is not None:
            options.trace.append({
                "cycle": cycle, "source_index": source_index,
                "s_valid": value(dut.s_axis_tvalid), "s_ready": value(dut.s_axis_tready),
                "s_data": value(dut.s_axis_tdata), "s_last": value(dut.s_axis_tlast),
                "m_valid": value(dut.m_axis_tvalid), "m_ready": value(dut.m_axis_tready),
                "m_data": value(dut.m_axis_tdata), "m_last": value(dut.m_axis_tlast),
                "m_error": value(dut.m_axis_tuser_error),
                "r_valid": value(dut.result_valid), "r_ready": value(dut.result_ready),
                "r_reason": value(dut.result_reason),
            })

        current_counters = (value(dut.header_index), value(dut.payload_left))
        if current_counters != prior_counters:
            assert prior_input_handshake, "parser counters changed without input handshake"
        prior_counters = current_counters
        prior_input_handshake = in_hs

        if prior_output_stall is not None:
            assert out_valid, "payload valid dropped while stalled"
            assert (value(dut.m_axis_tdata), value(dut.m_axis_tlast),
                    value(dut.m_axis_tuser_error)) == prior_output_stall
        prior_output_stall = (
            (value(dut.m_axis_tdata), value(dut.m_axis_tlast),
             value(dut.m_axis_tuser_error))
            if out_valid and not value(dut.m_axis_tready)
            else None
        )
        metrics.saw_output_stall |= out_valid and not bool(value(dut.m_axis_tready))

        current_descriptor = read_descriptor(dut)
        if prior_result_stall is not None:
            assert res_valid, "result valid dropped while stalled"
            assert current_descriptor == prior_result_stall
        prior_result_stall = current_descriptor if res_valid and not rr else None
        metrics.saw_result_stall |= res_valid and not rr

        if options.probe_next_frame and source_index == len(frame) and not res_hs:
            assert not in_hs, "next frame accepted while a descriptor was pending"

        if res_valid:
            assert not out_valid, "descriptor valid while payload is still pending"
            assert value(dut.result_accept) == (value(dut.result_reason) == 0)
            if metrics.result_valid_cycle is None:
                metrics.result_valid_cycle = cycle
        if in_hs:
            if metrics.first_input_handshake_cycle is None:
                metrics.first_input_handshake_cycle = cycle
            if source_index == 41:
                metrics.udp_header_final_handshake_cycle = cycle
            if source_index == 42:
                metrics.first_payload_input_handshake_cycle = cycle
            if source_index == len(frame) - 1:
                metrics.input_frame_closing_handshake_cycle = cycle
        if out_valid and metrics.first_payload_output_valid_cycle is None:
            metrics.first_payload_output_valid_cycle = cycle
        if out_hs:
            metrics.payload_output_handshake_cycles.append(cycle)
            output_beats.append(
                (value(dut.m_axis_tdata), bool(value(dut.m_axis_tlast)),
                 bool(value(dut.m_axis_tuser_error)))
            )
            if metrics.first_payload_output_handshake_cycle is None:
                metrics.first_payload_output_handshake_cycle = cycle
            if value(dut.m_axis_tlast):
                metrics.final_payload_output_handshake_cycle = cycle
        if res_hs:
            descriptor = current_descriptor
            metrics.result_handshake_cycle = cycle

        await RisingEdge(dut.clk)
        if in_hs:
            source_index += 1
            source_active = False
        cycle += 1
        if cycle > 20000:
            raise AssertionError(
                f"frame transaction timed out len={len(frame)} index={source_index} "
                f"state={value(dut.state)} result_valid={value(dut.result_valid)}"
            )

    assert bytes(beat[0] for beat in output_beats) == expected_output(expected)
    if output_beats:
        assert output_beats[-1][1], "final payload beat is missing last"
        assert output_beats[-1][2] == expected.terminal_error
        assert all(not beat[1] for beat in output_beats[:-1])
    assert descriptor == descriptor_of(expected)
    return metrics


# --------------------------------------------------------------------------
# Directed frames
# --------------------------------------------------------------------------

def _directed_cases() -> list[tuple[str, bytes, bool]]:
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


# Directed cases whose cycle-by-cycle events go into the latency report.
LATENCY_CASES = {"multi_byte", "msg_multi", "port_mismatch", "message_mismatch", "late_middle"}


@cocotb.test()
@cocotb.parametrize(case=[Param(case, case[0]) for case in _directed_cases()])
async def directed_frame(dut, case: tuple[str, bytes, bool]) -> None:
    """One hand-picked frame, checked against the reference model."""
    name, frame, msg_enabled = case
    await start(dut)
    metrics = await run_frame(
        dut, frame, model(frame, 0, msg_enabled), msg_type_enable=msg_enabled,
    )
    if name in LATENCY_CASES:
        write_json(raw_dir("metrics") / f"latency_{name}.json", asdict(metrics))


@cocotb.test()
async def header_truncation_sweep(dut) -> None:
    """Close the frame after each header byte, back to back, 42 frames."""
    await start(dut)
    full = build_frame(b"abcd")
    for sequence, end in enumerate(range(1, 43)):
        frame = full[:end]
        await run_frame(dut, frame, model(frame, sequence))


@cocotb.test()
async def configuration_latched_per_frame(dut) -> None:
    """Changing the configuration inputs mid-frame must not affect the frame."""
    await start(dut)
    frame = build_frame(bytes([MSG]) + b"latched")
    await run_frame(
        dut, frame, model(frame, 0, True), msg_type_enable=True,
        options=RunOptions(change_config_midframe=True),
    )


@cocotb.test()
async def sequence_wraps_at_32_bits(dut) -> None:
    await start(dut)
    frame = build_frame(b"wrap")
    dut.sequence_counter.value = 0xFFFF_FFFF
    await run_frame(dut, frame, model(frame, 0xFFFF_FFFF))
    await run_frame(dut, frame, model(frame, 0))


# --------------------------------------------------------------------------
# Flow control
# --------------------------------------------------------------------------

def _backpressure_options(name: str) -> RunOptions:
    held = 0

    def hold_result_ready(cycle: int, valid: bool) -> bool:
        nonlocal held
        if valid:
            held += 1
            return held > 4
        return True

    return {
        "no_stall": RunOptions(),
        "input_gaps": RunOptions(input_gap=lambda c: c % 3 != 0),
        "output_stalls": RunOptions(output_ready=lambda c: c % 4 != 1),
        "input_gaps_and_output_stalls": RunOptions(
            input_gap=lambda c: c % 3 != 0,
            output_ready=lambda c: c % 5 not in {1, 2},
        ),
        "long_output_stalls": RunOptions(output_ready=lambda c: c % 7 not in {2, 3, 4}),
        "result_stall_blocks_next_frame": RunOptions(
            result_ready=hold_result_ready, probe_next_frame=True,
        ),
    }[name]


@cocotb.test()
@cocotb.parametrize(scenario=[
    "no_stall", "input_gaps", "output_stalls", "input_gaps_and_output_stalls",
    "long_output_stalls", "result_stall_blocks_next_frame",
])
async def flow_control(dut, scenario: str) -> None:
    """A 96-byte message-filtered payload under one flow-control pattern."""
    await start(dut)
    frame = build_frame(bytes([MSG]) + bytes(range(1, 96)), padding=b"\x00" * 12)
    metrics = await run_frame(
        dut, frame, model(frame, 0, True), msg_type_enable=True,
        options=_backpressure_options(scenario),
    )
    if scenario == "result_stall_blocks_next_frame":
        assert metrics.saw_result_stall
    if scenario in {"output_stalls", "long_output_stalls"}:
        assert metrics.saw_output_stall


@cocotb.test()
@cocotb.parametrize(case=[
    Param((build_frame(b"payload", fields=PacketFields(dst_port=0x1234)), False),
          "port_mismatch"),
    Param((build_frame(b"\x00payload"), True), "message_mismatch"),
])
async def reject_ignores_output_ready(dut, case: tuple[bytes, bool]) -> None:
    """A rejected frame drains even if the payload output is never ready."""
    frame, msg_enabled = case
    await start(dut)
    await run_frame(
        dut, frame, model(frame, 0, msg_enabled), msg_type_enable=msg_enabled,
        options=RunOptions(output_ready=lambda c: False),
    )


@cocotb.test()
async def input_ready_is_registered(dut) -> None:
    """m_axis_tready must have no combinational path to s_axis_tready."""
    await start(dut)
    rng = random.Random(5)
    frame = build_frame(bytes([MSG]) + bytes(rng.randrange(256) for _ in range(80)))
    await run_frame(
        dut, frame, model(frame, 0, True), msg_type_enable=True,
        options=RunOptions(
            output_ready=lambda c: rng.random() > 0.4,
            check_ready_isolation=True,
        ),
    )


@cocotb.test()
async def back_to_back_frames(dut) -> None:
    """Stream frames with tvalid held high and count input stall cycles.

    Measures the gap the core inserts between frames when the source, the
    payload sink, and the descriptor sink never stall.
    """
    await start(dut)
    other_port = PacketFields(dst_port=0x1234)
    frames: list[tuple[str, bytes]] = [
        ("accepted_payload", build_frame(bytes(range(64)))),
        ("accepted_payload", build_frame(b"0123456789")),
        ("accepted_zero_payload", build_frame()),
        ("accepted_with_padding", build_frame(b"abc", padding=b"\x00" * 15)),
        ("port_mismatch", build_frame(b"0123456789", fields=other_port)),
        ("non_ipv4", build_frame(b"abc", fields=PacketFields(ether_type=0x86DD))),
        ("late_truncation", build_frame(b"abcdefgh")[:46]),
        ("accepted_payload", build_frame(bytes(range(200)))),
    ]
    expected = [model(frame, sequence) for sequence, (_, frame) in enumerate(frames)]
    stream = [
        (frame_index, byte, index == len(frame) - 1)
        for frame_index, (_, frame) in enumerate(frames)
        for index, byte in enumerate(frame)
    ]

    dut.m_axis_tready.value = 1
    dut.result_ready.value = 1
    position = 0
    cycle = 0
    first_cycle: dict[int, int] = {}
    close_cycle: dict[int, int] = {}
    output_beats: list[tuple[int, bool, bool]] = []
    descriptors: list[tuple[int, ...]] = []

    while len(descriptors) < len(frames):
        await FallingEdge(dut.clk)
        if position < len(stream):
            frame_index, byte, last = stream[position]
            dut.s_axis_tvalid.value = 1
            dut.s_axis_tdata.value = byte
            dut.s_axis_tlast.value = int(last)
        else:
            dut.s_axis_tvalid.value = 0
            dut.s_axis_tlast.value = 0
        await Timer(1, unit="ns")

        if value(dut.s_axis_tvalid) and value(dut.s_axis_tready):
            frame_index, _, last = stream[position]
            first_cycle.setdefault(frame_index, cycle)
            if last:
                close_cycle[frame_index] = cycle
            position += 1
        if value(dut.m_axis_tvalid) and value(dut.m_axis_tready):
            output_beats.append(
                (value(dut.m_axis_tdata), bool(value(dut.m_axis_tlast)),
                 bool(value(dut.m_axis_tuser_error)))
            )
        if value(dut.result_valid) and value(dut.result_ready):
            descriptors.append(read_descriptor(dut))

        await RisingEdge(dut.clk)
        cycle += 1
        assert cycle < 10000, "back-to-back stream timed out"

    assert descriptors == [descriptor_of(result) for result in expected]
    # Split the output stream at each last beat and compare frame by frame.
    segments: list[tuple[bytes, bool]] = []
    current = bytearray()
    for data, last, error in output_beats:
        current.append(data)
        if last:
            segments.append((bytes(current), error))
            current = bytearray()
    assert not current, "output stream ended without a last beat"
    assert segments == [
        (expected_output(result), result.terminal_error)
        for result in expected if expected_output(result)
    ]

    gaps: dict[str, list[int]] = {}
    for index in range(len(frames) - 1):
        bubble = first_cycle[index + 1] - close_cycle[index] - 1
        gaps.setdefault(frames[index][0], []).append(bubble)
    total_bytes = len(stream)
    write_json(raw_dir("metrics") / "back_to_back.json", {
        "frames": len(frames),
        "input_bytes": total_bytes,
        "cycles_first_to_last_input": close_cycle[len(frames) - 1] - first_cycle[0] + 1,
        "input_stall_cycles_after_frame": gaps,
    })


@cocotb.test()
@cocotb.parametrize(example=[
    Param((build_frame(b"abcdef"), lambda c: c not in {44, 45}), "accepted_with_output_stall"),
    Param((build_frame(b"abcdef")[:45], None), "late_truncation"),
])
async def waveform_example(dut, example: tuple[bytes, Callable[[int], bool] | None]) -> None:
    """Record the end of a frame for the waveform figures in results/waveforms/."""
    frame, output_ready = example
    await start(dut)
    trace: list[dict[str, int]] = []
    await run_frame(dut, frame, model(frame, 0),
                    options=RunOptions(output_ready=output_ready, trace=trace))
    first = next(i for i, snapshot in enumerate(trace) if snapshot["source_index"] >= 39)
    name = "accepted_with_output_stall" if len(frame) > 45 else "late_truncation"
    write_json(raw_dir("waves") / f"{name}.json", trace[first:])


# --------------------------------------------------------------------------
# Reset
# --------------------------------------------------------------------------

async def send_prefix(dut, frame: bytes, count: int, *, output_ready: bool = True,
                      close: bool = False) -> None:
    index = 0
    dut.result_ready.value = 0
    dut.m_axis_tready.value = int(output_ready)
    while index < count:
        await FallingEdge(dut.clk)
        dut.s_axis_tvalid.value = 1
        dut.s_axis_tdata.value = frame[index]
        dut.s_axis_tlast.value = int(close and index == count - 1)
        await Timer(1, unit="ns")
        handshake = bool(value(dut.s_axis_tready))
        await RisingEdge(dut.clk)
        if handshake:
            index += 1
    dut.s_axis_tvalid.value = 0


async def reset_then_clean_frame(dut) -> None:
    """Reset, then check that the next frame is handled from a clean state.

    A descriptor left over from the aborted frame, or a sequence number other
    than zero, makes run_frame fail.
    """
    await reset_dut(dut, cycles=2)
    clean = build_frame(b"clean")
    await run_frame(dut, clean, model(clean, 0))


@cocotb.test()
@cocotb.parametrize(point=[
    Param((0, True), "idle"),
    Param((5, True), "ethernet_header"),
    Param((20, True), "ipv4_header"),
    Param((38, True), "udp_header"),
    Param((44, False), "payload_with_output_stalled"),
])
async def reset_mid_frame(dut, point: tuple[int, bool]) -> None:
    """Reset after sending part of a frame; the frame must leave no trace."""
    count, output_ready = point
    await start(dut)
    if count:
        await send_prefix(dut, build_frame(b"accepted-payload"), count,
                          output_ready=output_ready)
    await reset_then_clean_frame(dut)


@cocotb.test()
async def reset_while_descriptor_stalled(dut) -> None:
    await start(dut)
    zero = build_frame()
    await send_prefix(dut, zero, len(zero), close=True)
    for _ in range(20):
        await FallingEdge(dut.clk)
        await Timer(1, unit="ns")
        if value(dut.result_valid):
            break
    assert value(dut.result_valid)
    held = (value(dut.result_reason), value(dut.result_sequence))
    for _ in range(4):
        await RisingEdge(dut.clk)
        assert (value(dut.result_reason), value(dut.result_sequence)) == held
    await reset_then_clean_frame(dut)


# --------------------------------------------------------------------------
# Fixed-seed randomized regression
# --------------------------------------------------------------------------

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


def _record_coverage(hits, case: RandomCase, expected: ReferenceResult,
                     metrics: RunMetrics) -> None:
    hits["reason"][expected.reason.name] += 1
    if expected.accept:
        hits["accepted_payload_size"][coverage.payload_size_bin(expected.payload_len)] += 1
    hits["message_filter"]["enabled" if case.msg_enabled else "disabled"] += 1
    hits["padding"]["yes" if expected.padding_length else "no"] += 1
    hits["df"]["1" if case.df else "0"] += 1
    hits["input_gaps"]["yes" if metrics.saw_input_gap else "no"] += 1
    hits["result_backpressure"]["yes" if metrics.saw_result_stall else "no"] += 1
    hits["truncation_region"][case.truncation] += 1
    if expected.accept and expected.payload_len:
        semantic = "full_good_output"
    elif expected.terminal_error:
        semantic = "partial_error_output"
    else:
        semantic = "no_output"
    hits["output_semantic"][semantic] += 1
    stalled = "stalled" if metrics.saw_output_stall else "not_stalled"
    if semantic != "no_output":
        hits["output_backpressure_on_payload"][stalled] += 1
    if semantic == "partial_error_output":
        hits["partial_output_x_output_stall"][stalled] += 1


@cocotb.test()
@cocotb.parametrize(seed=SEEDS)
async def randomized_regression(dut, seed: int) -> None:
    """200 frames per seed with random fields, filters, and flow control."""
    await start(dut)
    rng = random.Random(seed)
    names = list(CATEGORY_WEIGHTS)
    weights = list(CATEGORY_WEIGHTS.values())
    hits = coverage.new_counters()

    for sequence in range(FRAMES_PER_SEED):
        # Visit every category once before sampling by weight.
        category = (names[sequence] if sequence < len(names)
                    else rng.choices(names, weights)[0])
        case = random_case(rng, category)
        expected = model(case.frame, sequence, case.msg_enabled)
        options = RunOptions(
            input_gap=(lambda c, r=rng: r.random() > 0.25)
            if rng.getrandbits(1) else None,
            output_ready=(lambda c, r=rng: r.random() > 0.30)
            if rng.getrandbits(1) else None,
            result_ready=(lambda c, valid: (not valid) or c % 4 == 0)
            if rng.getrandbits(1) else None,
        )
        metrics = await run_frame(
            dut, case.frame, expected, msg_type_enable=case.msg_enabled, options=options,
        )
        _record_coverage(hits, case, expected, metrics)

    write_json(raw_dir("coverage") / f"seed_{seed}.json", {
        "seed": seed,
        "frames": FRAMES_PER_SEED,
        "hits": {group: dict(counts) for group, counts in hits.items()},
    })
