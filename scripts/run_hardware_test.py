"""Run the filter on a Basys 3 and check it against the reference model.

1. Build the bitstream with Vivado (fpga/basys3/build.tcl).
2. Load it over JTAG (volatile; the board's flash is not touched).
3. Send test frames over the USB-UART and compare every payload byte and
   result record with sim/reference_model.py.

Needs Vivado, a Basys 3 on USB, and pyserial (requirements-hw.txt).
Writes results/hardware_test.{json,md}. Not part of run_all.py or CI.

    python scripts/run_hardware_test.py [--port COM3] [--skip-build] [--skip-program]
"""

from __future__ import annotations

import argparse
import json
import random
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from run_vivado import find_vivado, utilization  # noqa: E402
from sim.frames import CATEGORY_WEIGHTS, MSG, PORT, directed_cases, model, random_case  # noqa: E402
from sim.hw_protocol import (  # noqa: E402
    CMD_RESET, ResponseParser, check_response, frame_command,
)
from sim.packet_builder import build_frame  # noqa: E402

BAUD = 1_000_000
CORE_CLOCK_MHZ = 125
BATCH_BYTES = 3800           # stays below the board's 4096-byte RX FIFO
SEEDS = [1, 7, 42, 2027]
STALL_LEVELS = [0, 0, 64, 128, 192]
BUILD = ROOT / "build" / "hardware"
RAW = ROOT / "results" / "raw" / "hardware"
BOARD_SOURCES = [
    "rtl/stream_byte_buffer.sv", "rtl/udp_packet_filter.sv",
    "rtl/udp_packet_filter_reason_codes.svh",
    "fpga/basys3/uart_rx.sv", "fpga/basys3/uart_tx.sv", "fpga/basys3/sync_fifo.sv",
    "fpga/basys3/bram_fifo.sv",
    "fpga/basys3/hw_test_core.sv", "fpga/basys3/basys3_top.sv",
    "fpga/basys3/basys3.xdc", "fpga/basys3/build.tcl", "fpga/basys3/program.tcl",
]


def run_vivado_batch(vivado: str, work: Path, tcl: str, args: list[str], log: str):
    return subprocess.run(
        [vivado, "-mode", "batch", "-nojournal", "-log", log, "-source", tcl, "-tclargs", *args],
        cwd=work, text=True, capture_output=True, errors="replace",
    )


def build(vivado: str) -> dict:
    """Build in an ASCII-only temp folder (Vivado mishandles non-ASCII paths)."""
    work = Path(tempfile.mkdtemp(prefix="udp_hw_build_"))
    try:
        src = work / "src"
        src.mkdir()
        for name in BOARD_SOURCES:
            shutil.copyfile(ROOT / name, src / Path(name).name)
        print("Building the bitstream (a few minutes)...", flush=True)
        done = run_vivado_batch(vivado, work, "src/build.tcl", ["src", "out"], "build.log")
        out = work / "out"
        if RAW.exists():
            shutil.rmtree(RAW)
        RAW.mkdir(parents=True)
        for path in [work / "build.log", *out.glob("*.rpt"), out / "summary.txt"]:
            if path.is_file():
                shutil.copyfile(path, RAW / path.name)
        if done.returncode or not (out / "basys3_top.bit").is_file():
            raise RuntimeError("Vivado build failed; see results/raw/hardware/build.log")
        BUILD.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(out / "basys3_top.bit", BUILD / "basys3_top.bit")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return read_build_summary()


def read_build_summary() -> dict:
    fields = dict(line.split(" ", 1) for line in
                  (RAW / "summary.txt").read_text(encoding="utf-8").splitlines() if line)
    report = (RAW / "utilization.rpt").read_text(encoding="utf-8", errors="replace")
    summary = {
        "vivado_version": fields["vivado_version"],
        "part": fields["part"],
        "wns_ns": float(fields["wns_ns"]),
        "whs_ns": float(fields["whs_ns"]),
        "utilization": utilization(report),
    }
    if summary["wns_ns"] < 0 or summary["whs_ns"] < 0:
        raise RuntimeError(f"bitstream misses timing: WNS {summary['wns_ns']}, "
                           f"WHS {summary['whs_ns']}")
    return summary


def program(vivado: str, bitstream: Path) -> None:
    work = Path(tempfile.mkdtemp(prefix="udp_hw_prog_"))
    try:
        shutil.copyfile(bitstream, work / "basys3_top.bit")
        shutil.copyfile(ROOT / "fpga" / "basys3" / "program.tcl", work / "program.tcl")
        print("Loading the bitstream over JTAG...", flush=True)
        done = run_vivado_batch(vivado, work, "program.tcl", ["basys3_top.bit"], "program.log")
        if done.returncode or "DONE: 1" not in done.stdout:
            print(done.stdout[-3000:], file=sys.stderr)
            raise RuntimeError("programming the Basys 3 failed")
    finally:
        shutil.rmtree(work, ignore_errors=True)


def find_port() -> str:
    from serial.tools import list_ports
    ports = [p.device for p in list_ports.comports() if (p.vid, p.pid) == (0x0403, 0x6010)]
    if not ports:
        raise RuntimeError("no Basys 3 serial port found (FTDI 0403:6010); use --port")
    return ports[0]


def test_plan(frames_per_seed: int) -> list[tuple[str, bytes, bool, int]]:
    """(group, frame, message filter on, stall level) for every frame to send."""
    plan = []
    for _, frame, msg in directed_cases():
        for stall in (0, 160):
            plan.append(("directed", frame, msg, stall))
    full = build_frame(b"abcd")
    plan += [("header_truncation_sweep", full[:end], False, 0) for end in range(1, 43)]
    names, weights = list(CATEGORY_WEIGHTS), list(CATEGORY_WEIGHTS.values())
    for seed in SEEDS:
        rng = random.Random(seed)
        for index in range(frames_per_seed):
            category = names[index] if index < len(names) else rng.choices(names, weights)[0]
            case = random_case(rng, category)
            plan.append((f"random_seed_{seed}", case.frame, case.msg_enabled,
                         rng.choice(STALL_LEVELS)))
    return plan


def read_until(port, parser: ResponseParser, done, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while not done():
        data = port.read(max(1, port.in_waiting))
        if data:
            parser.feed(data)
            deadline = time.monotonic() + timeout
        elif time.monotonic() > deadline:
            raise RuntimeError("the board stopped answering")


def run_tests(port_name: str, frames_per_seed: int) -> dict:
    import serial

    plan = test_plan(frames_per_seed)
    failures: list[dict] = []
    reasons: Counter[str] = Counter()
    groups: Counter[str] = Counter()
    stalled_frames = 0
    bytes_out = bytes_in = beats = 0
    started = time.monotonic()

    with serial.Serial(port_name, BAUD, timeout=0.05) as port:
        port.reset_input_buffer()
        parser = ResponseParser()
        port.write(bytes([CMD_RESET]))
        read_until(port, parser, lambda: parser.reset_acks == 1, 2.0)

        sequence = 0
        index = 0
        while index < len(plan):
            batch, size = [], 0
            while index < len(plan):
                group, frame, msg, stall = plan[index]
                command = frame_command(frame, dst_port=PORT, msg_type_enable=msg,
                                        msg_type=MSG, stall_level=stall)
                if batch and size + len(command) > BATCH_BYTES:
                    break
                batch.append((group, frame, msg, stall, command))
                size += len(command)
                index += 1
            first = len(parser.frames)
            port.write(b"".join(item[4] for item in batch))
            bytes_out += size
            read_until(port, parser, lambda: len(parser.frames) == first + len(batch), 5.0)
            for offset, (group, frame, msg, stall, _) in enumerate(batch):
                expected = model(frame, sequence, msg)
                response = parser.frames[first + offset]
                problems = check_response(response, expected)
                groups[group] += 1
                reasons[expected.reason.name] += 1
                stalled_frames += bool(stall)
                beats += len(response.beats)
                bytes_in += 2 * len(response.beats) + 21
                if problems and len(failures) < 20:
                    failures.append({"group": group, "sequence": sequence,
                                     "frame": frame.hex(), "problems": problems})
                elif problems:
                    failures.append({"group": group, "sequence": sequence})
                sequence = (sequence + 1) & 0xFFFF_FFFF
            print(f"\r{sequence}/{len(plan)} frames, {len(failures)} mismatches",
                  end="", flush=True)
    print()
    return {
        "frames": sum(groups.values()),
        "mismatches": len(failures),
        "groups": dict(groups),
        "reasons": dict(sorted(reasons.items())),
        "frames_with_output_stalls": stalled_frames,
        "payload_beats_checked": beats,
        "bytes_sent": bytes_out,
        "bytes_received": bytes_in,
        "seconds": round(time.monotonic() - started, 1),
        "failures": failures,
    }


def git(*args: str) -> str:
    done = subprocess.run(["git", *args], cwd=ROOT, text=True, capture_output=True)
    return done.stdout.strip()


def write_report(port: str, build_summary: dict, tests: dict) -> None:
    status = "pass" if tests["mismatches"] == 0 else "fail"
    report = {
        "status": status,
        "date_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "commit_sha": git("rev-parse", "HEAD"),
        "source_dirty": bool(git("status", "--porcelain", "--", "rtl", "fpga", "sim")),
        "board": "Digilent Basys 3",
        "part": build_summary["part"],
        "filter_clock_mhz": CORE_CLOCK_MHZ,
        "uart_baud": BAUD,
        "serial_port": port,
        "build": build_summary,
        "tests": tests,
    }
    results = ROOT / "results"
    (results / "hardware_test.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")

    util = build_summary["utilization"]
    lines = [
        "# Hardware test: Basys 3",
        "",
        f"- Status: `{status}`: {tests['frames']} frames, "
        + ("every payload byte and result record matched the reference model."
           if status == "pass" else f"{tests['mismatches']} frames did not match."),
        f"- Board: Digilent Basys 3, `{build_summary['part']}`. The filter runs at "
        f"{CORE_CLOCK_MHZ} MHz, made from the 100 MHz oscillator by an MMCM.",
        f"- Link: USB-UART at {BAUD // 1000} kbaud. Each frame is buffered on the FPGA, "
        "then streamed into the filter at one byte per clock.",
        f"- Bitstream: Vivado {build_summary['vivado_version']}, whole design "
        f"(filter, UART, FIFOs): WNS {build_summary['wns_ns']:.3f} ns, "
        f"WHS {build_summary['whs_ns']:.3f} ns at {CORE_CLOCK_MHZ} MHz; "
        f"{util.get('Slice LUTs', '?')} LUTs, {util.get('Slice Registers', '?')} FFs.",
        f"- Run: {report['date_utc']}, commit `{report['commit_sha'][:7]}`, "
        f"{tests['seconds']} s.",
        "",
        "| Frames | Count |",
        "|---|---:|",
    ]
    lines += [f"| {group.replace('_', ' ')} | {count} |" for group, count in tests["groups"].items()]
    lines += [
        f"| **total** | **{tests['frames']}** |",
        "",
        f"{tests['frames_with_output_stalls']} frames ran with random output and result "
        f"stalls; {tests['payload_beats_checked']} payload beats were checked.",
        "",
        "| Expected reason | Frames |",
        "|---|---:|",
    ]
    lines += [f"| `{name}` | {count} |" for name, count in tests["reasons"].items()]
    if tests["failures"]:
        lines += ["", "## Mismatches", ""]
        lines += [f"- {f['group']} seq {f['sequence']}: {f.get('problems', '')}"
                  for f in tests["failures"][:20]]
    lines += [
        "",
        "Run with `python scripts/run_hardware_test.py` (needs Vivado, the board, and "
        "`pip install -r requirements-hw.txt`). The harness is described in "
        "[docs/hardware-test.md](../docs/hardware-test.md).",
    ]
    (results / "hardware_test.md").write_text("\n".join(lines) + "\n",
                                               encoding="utf-8", newline="\n")
    print("\n".join(lines))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", help="serial port (default: find the Basys 3)")
    parser.add_argument("--skip-build", action="store_true", help="reuse build/hardware/")
    parser.add_argument("--skip-program", action="store_true", help="board already loaded")
    parser.add_argument("--frames-per-seed", type=int, default=500)
    args = parser.parse_args()

    vivado = find_vivado()
    if not vivado and not (args.skip_build and args.skip_program):
        print("ERROR: Vivado not found; set VIVADO", file=sys.stderr)
        return 2
    try:
        build_summary = read_build_summary() if args.skip_build else build(vivado)
        if not args.skip_program:
            program(vivado, BUILD / "basys3_top.bit")
        port = args.port or find_port()
        tests = run_tests(port, args.frames_per_seed)
    except RuntimeError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    write_report(port, build_summary, tests)
    return 0 if tests["mismatches"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
