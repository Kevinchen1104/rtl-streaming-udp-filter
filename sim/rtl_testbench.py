from __future__ import annotations

import json
import os
import random
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, Timer

from sim.packet_builder import PacketFields, build_frame
from sim.reference_model import Reason, ReferenceResult, classify_frame


PORT = 0xBEEF
MSG = 0xA5
SEEDS = [1, 7, 42, 2027]


@dataclass
class RunOptions:
    input_gap: Callable[[int], bool] | None = None
    output_ready: Callable[[int], bool] | None = None
    result_ready: Callable[[int, bool], bool] | None = None
    change_config_midframe: bool = False
    probe_next_frame: bool = False


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


async def run_frame(
    dut,
    frame: bytes,
    expected: ReferenceResult,
    *,
    msg_type_enable: bool = False,
    options: RunOptions | None = None,
) -> RunMetrics:
    options = options or RunOptions()
    source_index = 0
    source_active = False
    output_beats: list[tuple[int, bool, bool]] = []
    descriptor = None
    metrics = RunMetrics()
    prior_output_stall = None
    prior_result_stall = None
    prior_byte_index = value(dut.byte_index)
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
        if (options.probe_next_frame and source_index == len(frame)
                and descriptor is None):
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

        in_hs = bool(value(dut.s_axis_tvalid) and value(dut.s_axis_tready))
        out_valid = bool(value(dut.m_axis_tvalid))
        out_hs = bool(out_valid and value(dut.m_axis_tready))
        res_valid = bool(value(dut.result_valid))
        res_hs = bool(res_valid and value(dut.result_ready))

        current_byte_index = value(dut.byte_index)
        if current_byte_index != prior_byte_index:
            assert prior_input_handshake, "parser byte index changed without input handshake"
        prior_byte_index = current_byte_index
        prior_input_handshake = in_hs

        if prior_output_stall is not None:
            assert out_valid
            assert (value(dut.m_axis_tdata), value(dut.m_axis_tlast),
                    value(dut.m_axis_tuser_error)) == prior_output_stall
        prior_output_stall = (
            (value(dut.m_axis_tdata), value(dut.m_axis_tlast),
             value(dut.m_axis_tuser_error))
            if out_valid and not value(dut.m_axis_tready)
            else None
        )
        metrics.saw_output_stall |= out_valid and not bool(value(dut.m_axis_tready))

        current_descriptor = (
            value(dut.result_accept), value(dut.result_reason),
            value(dut.result_src_ip), value(dut.result_dst_ip),
            value(dut.result_src_port), value(dut.result_dst_port),
            value(dut.result_payload_len), value(dut.result_sequence),
        )
        if prior_result_stall is not None:
            assert res_valid
            assert current_descriptor == prior_result_stall
        prior_result_stall = current_descriptor if res_valid and not rr else None
        metrics.saw_result_stall |= res_valid and not rr

        if options.probe_next_frame and source_index == len(frame) and not res_hs:
            assert not in_hs

        if res_valid:
            assert not out_valid
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

    expected_bytes = expected.expected_payload if expected.accept else expected.speculative_payload
    assert bytes(beat[0] for beat in output_beats) == expected_bytes
    if output_beats:
        assert output_beats[-1][1]
        assert output_beats[-1][2] == expected.terminal_error
        assert all(not beat[1] for beat in output_beats[:-1])
    assert descriptor == (
        int(expected.accept), int(expected.reason), expected.src_ip,
        expected.dst_ip, expected.src_port, expected.dst_port,
        expected.payload_len, expected.sequence,
    )
    return metrics


def model(frame: bytes, sequence: int, msg_enabled: bool = False,
          max_bytes: int = 2048) -> ReferenceResult:
    return classify_frame(
        frame,
        dst_port=PORT,
        msg_type_enable=msg_enabled,
        msg_type=MSG,
        max_logical_frame_bytes=max_bytes,
        sequence=sequence,
    )


@cocotb.test()
async def directed_rtl_matrix(dut) -> None:
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    cases: list[tuple[str, bytes, bool]] = [
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
        ("port_mismatch", build_frame(b"abc", fields=PacketFields(dst_port=0x1234)), False),
        ("port_mismatch_same_cycle_truncation",
         build_frame(b"x", fields=PacketFields(dst_port=0x1234))[:42], False),
        ("message_mismatch", build_frame(b"\x00abc"), True),
        ("message_mismatch_same_byte_truncation",
         build_frame(b"\x00abc")[:43], True),
        ("message_mismatch_then_late_truncation",
         build_frame(b"\x00abc")[:44], True),
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
        ("maximum_logical", build_frame(bytes((i * 17) & 0xFF for i in range(2006))), False),
    ]

    sequence = 0
    matrix_results: dict[str, str] = {}
    latency: dict[str, dict] = {}
    for name, frame, msg_enabled in cases:
        metrics = await run_frame(
            dut, frame, model(frame, sequence, msg_enabled),
            msg_type_enable=msg_enabled,
        )
        matrix_results[name] = "pass"
        if name in {"multi_byte", "msg_multi", "port_mismatch",
                    "message_mismatch", "late_middle"}:
            latency[name] = asdict(metrics)
        sequence += 1

    # Every early header close, including a one-byte frame through byte 41.
    full = build_frame(b"abcd")
    for end in range(1, 43):
        frame = full[:end]
        await run_frame(dut, frame, model(frame, sequence))
        sequence += 1
    matrix_results["header_truncation_0_through_41"] = "pass"

    # Configuration changes after byte zero must not affect this frame.
    frame = build_frame(bytes([MSG]) + b"latched")
    await run_frame(
        dut, frame, model(frame, sequence, True), msg_type_enable=True,
        options=RunOptions(change_config_midframe=True),
    )
    sequence += 1
    matrix_results["configuration_latched"] = "pass"

    # Explicitly exercise modulo-2^32 descriptor sequencing.
    frame = build_frame(b"wrap")
    dut.sequence_counter.value = 0xFFFF_FFFF
    await run_frame(dut, frame, model(frame, 0xFFFF_FFFF))
    await run_frame(dut, frame, model(frame, 0))
    frame_count = sequence + 2
    matrix_results["sequence_wrap"] = "pass"

    root = Path(os.environ["UDP_FILTER_REPO_ROOT"])
    raw = root / "results" / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    (raw / "directed_matrix.json").write_text(
        json.dumps({
            "status": "pass",
            "frame_count": frame_count,
            "results": matrix_results,
        }, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    (raw / "latency_directed.json").write_text(
        json.dumps(latency, indent=2), encoding="utf-8", newline="\n"
    )


@cocotb.test()
async def backpressure_and_sequencing(dut) -> None:
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)
    frame = build_frame(bytes([MSG]) + bytes(range(1, 96)), padding=b"\x00" * 12)
    sequence = 0
    report: dict[str, dict] = {}

    result_stall_count = 0

    def hold_result_ready(cycle: int, valid: bool) -> bool:
        nonlocal result_stall_count
        if valid:
            result_stall_count += 1
            return result_stall_count > 4
        return True

    scenarios = [
        ("no_stall", RunOptions()),
        ("input_gaps", RunOptions(input_gap=lambda cycle: cycle % 3 != 0)),
        ("output_stalls", RunOptions(output_ready=lambda cycle: cycle % 4 != 1)),
        ("simultaneous", RunOptions(
            input_gap=lambda cycle: cycle % 3 != 0,
            output_ready=lambda cycle: cycle % 5 not in {1, 2},
        )),
        ("result_stall", RunOptions(
            result_ready=hold_result_ready,
            probe_next_frame=True,
        )),
        ("periodic_long_payload", RunOptions(
            output_ready=lambda cycle: cycle % 7 not in {2, 3},
        )),
    ]
    for name, options in scenarios:
        metrics = await run_frame(
            dut, frame, model(frame, sequence, True),
            msg_type_enable=True, options=options,
        )
        report[name] = asdict(metrics)
        if name == "result_stall":
            assert metrics.saw_result_stall
        sequence += 1

    # No-payload rejects must drain independently of output readiness.
    mismatch_port = build_frame(b"payload", fields=PacketFields(dst_port=0x1234))
    metrics = await run_frame(
        dut, mismatch_port, model(mismatch_port, sequence),
        options=RunOptions(output_ready=lambda cycle: False),
    )
    report["port_mismatch_output_never_ready"] = asdict(metrics)
    sequence += 1
    mismatch_msg = build_frame(b"\x00payload")
    metrics = await run_frame(
        dut, mismatch_msg, model(mismatch_msg, sequence, True),
        msg_type_enable=True,
        options=RunOptions(output_ready=lambda cycle: False),
    )
    report["message_mismatch_output_never_ready"] = asdict(metrics)

    root = Path(os.environ["UDP_FILTER_REPO_ROOT"])
    raw = root / "results" / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    (raw / "backpressure.json").write_text(
        json.dumps({
            "status": "pass",
            "scenario_count": len(report),
            "metrics": report,
        }, indent=2),
        encoding="utf-8",
        newline="\n",
    )


def random_case(rng: random.Random, category: int) -> tuple[bytes, bool, dict[str, str]]:
    lengths = [0, 1, rng.randint(2, 7), rng.randint(8, 63),
               rng.randint(64, 255), rng.randint(256, 320)]
    payload_len = rng.choice(lengths)
    payload = bytes(rng.randrange(256) for _ in range(payload_len))
    msg_enabled = bool(rng.getrandbits(1))
    if msg_enabled and payload:
        payload = bytes([MSG]) + payload[1:]
    fields = PacketFields(
        df=bool(rng.getrandbits(1)),
        src_ip=rng.randrange(1 << 32), dst_ip=rng.randrange(1 << 32),
        src_port=rng.randrange(1 << 16), dst_port=PORT,
    )
    padding_len = rng.choice([0, 0, 0, rng.randint(1, 80)])
    padding = bytes(rng.randrange(256) for _ in range(padding_len))
    truncation = "none"

    if category == 0:
        if msg_enabled and not payload:
            msg_enabled = False
        frame = build_frame(payload, fields=fields, padding=padding)
    elif category == 1:
        frame = build_frame(payload, fields=PacketFields(**{
            **asdict(fields), "ether_type": 0x86DD,
        }), padding=padding)
    elif category == 2:
        frame = build_frame(payload, fields=PacketFields(**{
            **asdict(fields), "version": rng.choice([0, 6]),
        }), padding=padding)
    elif category == 3:
        frame = build_frame(payload, fields=PacketFields(**{
            **asdict(fields), "protocol": rng.choice([1, 6, 58]),
        }), padding=padding)
    elif category == 4:
        frame = build_frame(payload, fields=PacketFields(**{
            **asdict(fields), "mf": True,
        }), padding=padding)
    elif category == 5:
        mode = rng.randrange(5)
        base = build_frame(payload or b"abcd", fields=fields)
        if mode == 0:
            end = rng.randint(1, 13)
            truncation = "ethernet"
            frame = base[:end]
        elif mode == 1:
            end = rng.randint(14, 33)
            truncation = "ipv4"
            frame = base[:end]
        elif mode == 2:
            end = rng.randint(34, 41)
            truncation = "udp"
            frame = base[:end]
        elif mode == 3:
            declared = build_frame(bytes([MSG, 1, 2, 3]), fields=fields)
            frame = declared[:43]
            msg_enabled = bool(rng.getrandbits(1))
            truncation = "first_payload"
        else:
            declared_payload = bytes([MSG]) + bytes(range(1, 12))
            declared = build_frame(declared_payload, fields=fields)
            frame = declared[:rng.randint(44, 52)]
            truncation = "later_payload"
    elif category == 6:
        frame = build_frame(payload, fields=PacketFields(**{
            **asdict(fields), "dst_port": PORT ^ 0xFFFF,
        }), padding=padding)
    elif category == 7:
        payload = bytes([MSG ^ 0xFF]) + (payload[1:] if payload else b"")
        if not payload:
            payload = bytes([MSG ^ 0xFF])
        frame = build_frame(payload, fields=fields, padding=padding)
        msg_enabled = True
    else:
        frame = build_frame(b"", fields=fields,
                            ip_total_length=2040, udp_length=2020)

    return frame, msg_enabled, {
        "df": "1" if fields.df else "0",
        "truncation": truncation,
        "port": "mismatch" if category == 6 else "match",
    }


@cocotb.test()
async def fixed_seed_randomized_regression(dut) -> None:
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)
    from collections import Counter

    coverage: dict[str, Counter[str]] = {
        name: Counter() for name in [
            "reason", "accepted_payload_size", "message_filter", "port",
            "padding", "df", "input_gaps", "output_backpressure",
            "result_backpressure", "truncation_region", "output_semantic",
        ]
    }
    sequence = 0
    per_seed: dict[str, int] = {}
    for seed in SEEDS:
        rng = random.Random(seed)
        for index in range(200):
            category = index % 9 if index < 18 else rng.randrange(9)
            frame, msg_enabled, tags = random_case(rng, category)
            expected = model(frame, sequence, msg_enabled)
            use_input_gaps = bool(rng.getrandbits(1))
            use_output_stalls = bool(rng.getrandbits(1))
            use_result_stalls = bool(rng.getrandbits(1))
            options = RunOptions(
                input_gap=(lambda cycle, r=rng: r.random() > 0.25)
                if use_input_gaps else None,
                output_ready=(lambda cycle, r=rng: r.random() > 0.30)
                if use_output_stalls else None,
                result_ready=(lambda cycle, valid: (not valid) or cycle % 4 == 0)
                if use_result_stalls else None,
            )
            metrics = await run_frame(
                dut, frame, expected, msg_type_enable=msg_enabled,
                options=options,
            )

            coverage["reason"][expected.reason.name] += 1
            if expected.accept:
                n = expected.payload_len
                size_bin = ("0" if n == 0 else "1" if n == 1 else
                            "2-7" if n <= 7 else "8-63" if n <= 63 else
                            "64-255" if n <= 255 else "256+")
                coverage["accepted_payload_size"][size_bin] += 1
            coverage["message_filter"]["enabled" if msg_enabled else "disabled"] += 1
            coverage["port"][tags["port"]] += 1
            coverage["padding"]["yes" if expected.padding_length else "no"] += 1
            coverage["df"][tags["df"]] += 1
            coverage["input_gaps"]["yes" if metrics.saw_input_gap else "no"] += 1
            coverage["output_backpressure"]["yes" if metrics.saw_output_stall else "no"] += 1
            coverage["result_backpressure"]["yes" if metrics.saw_result_stall else "no"] += 1
            coverage["truncation_region"][tags["truncation"]] += 1
            semantic = ("full_good_output" if expected.accept and expected.payload_len
                        else "partial_error_output" if expected.terminal_error
                        else "no_output")
            coverage["output_semantic"][semantic] += 1
            sequence += 1
        per_seed[str(seed)] = 200

    root = Path(os.environ["UDP_FILTER_REPO_ROOT"])
    raw = root / "results" / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    (raw / "randomized.json").write_text(
        json.dumps({
            "status": "pass",
            "seeds": SEEDS,
            "frames_per_seed": per_seed,
            "total_frames": sequence,
            "coverage": {name: dict(counts) for name, counts in coverage.items()},
        }, indent=2), encoding="utf-8", newline="\n",
    )


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


async def reset_and_clean_frame(dut) -> None:
    await reset_dut(dut, cycles=2)
    clean = build_frame(b"clean")
    await run_frame(dut, clean, model(clean, 0))


@cocotb.test()
async def reset_abort_matrix(dut) -> None:
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    frame = build_frame(b"accepted-payload")

    reset_results: dict[str, str] = {"idle_reset": "pass"}
    await reset_and_clean_frame(dut)
    reset_points = [
        ("ethernet_reset", 5, True),
        ("ipv4_reset", 20, True),
        ("udp_reset", 38, True),
        ("payload_output_stall_reset", 43, False),
    ]
    for name, count, output_ready in reset_points:
        await send_prefix(dut, frame, count, output_ready=output_ready)
        await reset_and_clean_frame(dut)
        reset_results[name] = "pass"

    # Complete a zero-payload frame, then reset while its descriptor is stalled.
    zero = build_frame()
    await send_prefix(dut, zero, len(zero), close=True)
    await FallingEdge(dut.clk)
    dut.s_axis_tvalid.value = 0
    for _ in range(20):
        await Timer(1, unit="ns")
        if value(dut.result_valid):
            break
        await RisingEdge(dut.clk)
        await FallingEdge(dut.clk)
    assert value(dut.result_valid)
    held = (value(dut.result_reason), value(dut.result_sequence))
    for _ in range(4):
        await RisingEdge(dut.clk)
        assert (value(dut.result_reason), value(dut.result_sequence)) == held
    await reset_and_clean_frame(dut)
    reset_results["descriptor_stall_reset"] = "pass"
    reset_results["post_reset_sequence_zero"] = "pass"

    root = Path(os.environ["UDP_FILTER_REPO_ROOT"])
    raw = root / "results" / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    (raw / "reset.json").write_text(
        json.dumps({
            "status": "pass",
            "reset_scenarios": 6,
            "results": reset_results,
        }, indent=2),
        encoding="utf-8",
        newline="\n",
    )
