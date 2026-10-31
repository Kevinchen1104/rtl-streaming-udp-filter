"""Build the reports in results/ from the raw regression, lint, and synthesis output.

Fails if an input is missing, any test did not pass, or any coverage bin
missed its goal.
"""

from __future__ import annotations

import importlib.metadata
import json
import platform
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
RAW = RESULTS / "raw"

sys.path.insert(0, str(ROOT))
from sim import coverage  # noqa: E402

import render_waveforms  # noqa: E402


def load_json(path: Path) -> dict:
    if not path.is_file():
        raise RuntimeError(f"missing result file: {path.relative_to(ROOT)}")
    return json.loads(path.read_text(encoding="utf-8"))


def require_pass(payload: dict, label: str) -> None:
    if payload.get("status") != "pass":
        raise RuntimeError(f"{label} did not pass")


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n")


def write_lines(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines).rstrip("\n") + "\n", encoding="utf-8", newline="\n")


def tool_version(command: list[str]) -> str:
    executable = shutil.which(command[0])
    if not executable:
        raise RuntimeError(f"tool not found: {command[0]}")
    completed = subprocess.run(
        [executable, *command[1:]], cwd=ROOT, text=True,
        capture_output=True, errors="replace",
    )
    lines = [line.strip() for line in (completed.stdout + completed.stderr).splitlines()
             if line.strip()]
    if completed.returncode or not lines:
        raise RuntimeError(f"version command failed: {' '.join(command)}")
    return lines[0]


def cocotb_tests(path: Path) -> list[dict[str, str]]:
    """Every cocotb testcase as {group, scenario, result}."""
    if not path.is_file():
        raise RuntimeError(f"missing cocotb JUnit report: {path.relative_to(ROOT)}")
    tests = []
    for case in ET.parse(path).getroot().iter("testcase"):
        name = str(case.get("name"))
        group, _, params = name.partition("/")
        scenario = params.split("=", 1)[1] if "=" in params else params
        failed = case.find("failure") is not None or case.find("error") is not None
        tests.append({
            "group": group,
            "scenario": scenario,
            "result": "fail" if failed else "pass",
        })
    if not tests:
        raise RuntimeError("cocotb JUnit report has no testcases")
    return tests


def main() -> int:
    regression = load_json(RAW / "regression.json")
    lint = load_json(RESULTS / "lint_summary.json")
    synth = load_json(RESULTS / "synthesis_summary.json")
    fpga = load_json(RESULTS / "fpga_summary.json")
    formal = load_json(RESULTS / "formal_summary.json")
    require_pass(regression, "regression")
    require_pass(lint, "lint")
    require_pass(synth, "synthesis")
    require_pass(fpga, "FPGA place and route")
    require_pass(formal, "formal verification")

    tests = cocotb_tests(RAW / "cocotb_junit.xml")
    failed = [t for t in tests if t["result"] != "pass"]
    if failed:
        raise RuntimeError(f"cocotb tests failed: {failed}")
    groups = Counter(t["group"] for t in tests)

    # Coverage: merge seeds, check every declared bin against its goal.
    seed_files = sorted((RAW / "coverage").glob("seed_*.json"))
    if not seed_files:
        raise RuntimeError("no randomized coverage files found")
    seed_parts = [load_json(path) for path in seed_files]
    hits = coverage.merge([part["hits"] for part in seed_parts])
    unmet = coverage.unmet_goals(hits)
    if unmet:
        raise RuntimeError("coverage goals not met: " + "; ".join(unmet))
    random_frames = sum(int(part["frames"]) for part in seed_parts)
    seeds = sorted(int(part["seed"]) for part in seed_parts)
    bin_count = sum(len(bins) for bins in coverage.GOALS.values())

    # Latency and throughput.
    metrics_dir = RAW / "metrics"
    multi = load_json(metrics_dir / "latency_multi_byte.json")
    first_output = (multi["first_payload_output_valid_cycle"]
                    - multi["first_payload_input_handshake_cycle"])
    handshakes = multi["payload_output_handshake_cycles"]
    intervals = {right - left for left, right in zip(handshakes, handshakes[1:])}
    if len(intervals) != 1:
        raise RuntimeError(f"no-stall payload intervals are not constant: {intervals}")
    cycles_per_byte = intervals.pop()
    descriptor_after_close = (multi["result_valid_cycle"]
                              - multi["input_frame_closing_handshake_cycle"])
    back_to_back = load_json(metrics_dir / "back_to_back.json")
    gaps = {kind: sorted(set(values))
            for kind, values in back_to_back["input_stall_cycles_after_frame"].items()}

    simulator = tool_version(["iverilog", "-V"])

    # ---- regression summary --------------------------------------------
    summary = {
        "status": "pass",
        "reference_model_tests": regression["reference_model_tests"],
        "cocotb_tests": len(tests),
        "cocotb_tests_by_group": dict(groups),
        "randomized_frames": random_frames,
        "seeds": seeds,
        "coverage_bins": bin_count,
        "coverage_goal_per_bin": coverage.MIN_HITS,
        "simulator": simulator,
    }
    write_json(RESULTS / "regression_summary.json", summary)
    lines = [
        "# Regression summary",
        "",
        f"- Reference-model tests (pytest): {summary['reference_model_tests']}, all passed",
        f"- RTL tests (cocotb on Icarus Verilog): {len(tests)}, all passed",
        f"- Randomized frames: {random_frames} (seeds {', '.join(map(str, seeds))})",
        f"- Functional coverage: all {bin_count} bins reached their goal "
        f"(at least {coverage.MIN_HITS} hits each)",
        "",
        "| cocotb test | Scenarios |",
        "|---|---:|",
    ]
    lines += [f"| `{group}` | {count} |" for group, count in groups.items()]
    lines += ["", "Per-scenario results: [verification matrix](verification_matrix.md)."]
    write_lines(RESULTS / "regression_summary.md", lines)

    # ---- functional coverage -------------------------------------------
    write_json(RESULTS / "functional_coverage.json", {
        "source": "fixed-seed randomized RTL regression",
        "frames": random_frames,
        "seeds": seeds,
        "goals": coverage.GOALS,
        "hits": hits,
    })
    lines = [
        "# Functional coverage",
        "",
        f"From {random_frames} randomized frames (seeds {', '.join(map(str, seeds))}). "
        "Every bin is declared in `sim/coverage.py` with a minimum hit count; "
        "the run fails if any bin falls short.",
        "",
    ]
    for group, bins in coverage.GOALS.items():
        lines += [f"## {group.replace('_', ' ').capitalize()}", "",
                  "| Bin | Goal | Hits |", "|---|---:|---:|"]
        lines += [f"| `{name}` | {goal} | {hits[group][name]} |" for name, goal in bins.items()]
        lines.append("")
    write_lines(RESULTS / "functional_coverage.md", lines)

    # ---- latency --------------------------------------------------------
    latency = {
        "cycle_definition": (
            "Cycle 0 is the first rising edge at which the frame's first byte can "
            "transfer. Handshakes are counted at the rising edge where valid and "
            "ready are both high."
        ),
        "first_payload_output_latency_cycles": first_output,
        "payload_cycles_per_byte": cycles_per_byte,
        "descriptor_valid_after_last_input_cycles": descriptor_after_close,
        "back_to_back": back_to_back,
        "scenarios": {
            name: load_json(metrics_dir / f"latency_{name}.json")
            for name in ["multi_byte", "msg_multi", "port_mismatch",
                         "message_mismatch", "late_middle"]
        },
    }
    write_json(RESULTS / "latency_metrics.json", latency)
    lines = [
        "# Latency and throughput (simulation)",
        "",
        latency["cycle_definition"],
        "",
        "| Measurement | Cycles |",
        "|---|---:|",
        f"| First payload byte: input handshake to output valid | {first_output} |",
        f"| Payload throughput with no stalls | {cycles_per_byte} per byte |",
        f"| Last input byte to descriptor valid (6-byte payload) | {descriptor_after_close} |",
        "",
        "## Gap between back-to-back frames",
        "",
        f"{back_to_back['frames']} frames ({back_to_back['input_bytes']} bytes) sent with "
        "`s_axis_tvalid` held high and both sinks always ready took "
        f"{back_to_back['cycles_first_to_last_input']} cycles. Input stall cycles after each "
        "kind of frame:",
        "",
        "| Frame | Stall cycles before the next frame |",
        "|---|---:|",
    ]
    lines += [f"| {kind.replace('_', ' ')} | {', '.join(map(str, values))} |"
              for kind, values in gaps.items()]
    lines += ["", "## Event cycles per scenario", ""]
    for name, events in latency["scenarios"].items():
        lines += [f"### {name.replace('_', ' ')}", ""]
        lines += [f"- `{key}`: {value}" for key, value in events.items()
                  if not key.startswith("saw_") and key != "payload_output_handshake_cycles"]
        lines.append("")
    write_lines(RESULTS / "latency_metrics.md", lines)

    # ---- verification matrix -------------------------------------------
    lines = [
        "# Verification matrix",
        "",
        "Generated from the cocotb JUnit report (`results/raw/cocotb_junit.xml`). "
        "Each row is a separate cocotb test with its own result.",
        "",
        "| # | Test | Scenario | Result |",
        "|---:|---|---|---|",
    ]
    lines += [f"| {index} | `{t['group']}` | {t['scenario'].replace('_', ' ') or '-'} "
              f"| {t['result']} |" for index, t in enumerate(tests, 1)]
    write_lines(RESULTS / "verification_matrix.md", lines)

    render_waveforms.main()

    # ---- tool versions --------------------------------------------------
    write_lines(RESULTS / "tool_versions.txt", [
        f"Python: {platform.python_version()}",
        f"pytest: {importlib.metadata.version('pytest')}",
        f"cocotb: {importlib.metadata.version('cocotb')}",
        f"Icarus: {simulator}",
        f"Verilator: {lint['tool_version']}",
        f"Yosys: {synth['tool_version']}",
        f"nextpnr-ecp5: {fpga['tool_versions']['nextpnr-ecp5']}",
        f"SymbiYosys: {tool_version(['sby', '--version'])}",
    ])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
