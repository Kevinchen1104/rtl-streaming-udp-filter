from __future__ import annotations

import importlib.metadata
import json
import platform
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
RAW = RESULTS / "raw"


def load_raw(name: str) -> dict[str, object]:
    path = RAW / name
    if not path.is_file():
        raise RuntimeError(f"missing result artifact: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("status") != "pass":
        raise RuntimeError(f"artifact did not report pass: {path}")
    return payload


def load_json(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise RuntimeError(f"missing result artifact: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def tool_version(command: list[str]) -> str:
    executable = shutil.which(command[0])
    if not executable:
        raise RuntimeError(f"tool not found: {command[0]}")
    completed = subprocess.run(
        [executable, *command[1:]],
        cwd=ROOT,
        text=True,
        capture_output=True,
        errors="replace",
    )
    if completed.returncode:
        raise RuntimeError(
            f"version command failed ({completed.returncode}): {' '.join(command)}"
        )
    lines = [
        line.strip()
        for line in (completed.stdout + completed.stderr).splitlines()
        if line.strip()
    ]
    if not lines:
        raise RuntimeError(f"version command produced no output: {' '.join(command)}")
    return lines[0]


def checked_status(payload: dict[str, object], label: str) -> None:
    if payload.get("status") != "pass":
        raise RuntimeError(f"{label} did not report pass")


def scenario_rows(
    directed: dict[str, object],
    backpressure: dict[str, object],
    reset: dict[str, object],
) -> list[tuple[str, str, str]]:
    sources = [
        ("directed_rtl_matrix", directed.get("results")),
        ("backpressure_and_sequencing", backpressure.get("metrics")),
        ("reset_abort_matrix", reset.get("results")),
    ]
    rows: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str]] = set()
    for source, raw_results in sources:
        if not isinstance(raw_results, dict) or not raw_results:
            raise RuntimeError(f"{source} has no named scenario results")
        for key, value in raw_results.items():
            identity = (source, str(key))
            if identity in seen:
                raise RuntimeError(f"duplicate scenario identity: {identity}")
            seen.add(identity)
            if source == "backpressure_and_sequencing":
                status = "pass"
            else:
                status = str(value)
            if status != "pass":
                raise RuntimeError(f"scenario did not pass: {source}/{key}")
            rows.append((str(key).replace("_", " "), source, status))
    return rows


def main() -> int:
    regression_raw = load_raw("regression.json")
    directed = load_raw("directed_matrix.json")
    randomized = load_raw("randomized.json")
    reset = load_raw("reset.json")
    backpressure = load_raw("backpressure.json")
    latency_directed = load_json(RAW / "latency_directed.json")
    lint = load_json(RESULTS / "lint_summary.json")
    synth = load_json(RESULTS / "synthesis_summary.json")
    checked_status(lint, "lint")
    checked_status(synth, "synthesis")

    matrix_rows = scenario_rows(directed, backpressure, reset)
    regression = {
        "status": "pass",
        "reference_model_pytest_cases": regression_raw[
            "reference_model_pytest_cases"
        ],
        "rtl_pytest_entry_cases": regression_raw["rtl_pytest_entry_cases"],
        "cocotb_test_coroutines": regression_raw["cocotb_test_coroutines"],
        "directed_frames": directed["frame_count"],
        "flow_control_scenarios": backpressure["scenario_count"],
        "reset_scenarios": reset["reset_scenarios"],
        "randomized_frames": randomized["total_frames"],
        "fixed_seeds": randomized["seeds"],
        "scenario_matrix_rows": len(matrix_rows),
        "simulator": tool_version(["iverilog", "-V"]),
    }
    (RESULTS / "regression_summary.json").write_text(
        json.dumps(regression, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    reg_md = [
        "# Regression summary",
        "",
        "- Status: `pass`",
        f"- Reference-model pytest cases: `{regression['reference_model_pytest_cases']}`",
        f"- RTL pytest entry cases: `{regression['rtl_pytest_entry_cases']}`",
        f"- Cocotb test coroutines: `{regression['cocotb_test_coroutines']}`",
        f"- Directed frames: `{regression['directed_frames']}`",
        f"- Flow-control scenarios: `{regression['flow_control_scenarios']}`",
        f"- Reset scenarios: `{regression['reset_scenarios']}`",
        f"- Randomized frames: `{regression['randomized_frames']}`",
        f"- Fixed seeds: `{', '.join(map(str, regression['fixed_seeds']))}`",
        f"- Named scenario-matrix rows: `{regression['scenario_matrix_rows']}`",
        "",
        "Counts describe different verification scopes and are reported separately.",
    ]
    (RESULTS / "regression_summary.md").write_text(
        "\n".join(reg_md) + "\n", encoding="utf-8", newline="\n"
    )

    coverage = {
        "source": "fixed-seed RTL randomized regression",
        "total_frames": randomized["total_frames"],
        "bins": randomized["coverage"],
        "percentage_reported": False,
    }
    (RESULTS / "functional_coverage.json").write_text(
        json.dumps(coverage, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    cov_md = [
        "# Functional coverage hit counts",
        "",
        f"Source frames: `{coverage['total_frames']}`. Percentage coverage is not reported.",
        "",
    ]
    bins = coverage["bins"]
    if not isinstance(bins, dict):
        raise RuntimeError("randomized coverage bins are not a mapping")
    for group, group_bins in bins.items():
        if not isinstance(group_bins, dict):
            raise RuntimeError(f"coverage group is not a mapping: {group}")
        cov_md += [str(group).replace("_", " ").title(), ""]
        cov_md[-2] = f"## {cov_md[-2]}"
        cov_md += [f"- `{name}`: {count}" for name, count in group_bins.items()]
        cov_md.append("")
    (RESULTS / "functional_coverage.md").write_text(
        "\n".join(cov_md), encoding="utf-8", newline="\n"
    )

    flow = backpressure["metrics"]
    if not isinstance(flow, dict):
        raise RuntimeError("backpressure metrics are not a mapping")
    no_stall = flow["no_stall"]
    fixed_bp = flow["output_stalls"]
    if not isinstance(no_stall, dict) or not isinstance(fixed_bp, dict):
        raise RuntimeError("latency baseline metrics are malformed")

    port_only = latency_directed["multi_byte"]
    if not isinstance(port_only, dict):
        raise RuntimeError("multi-byte latency metrics are malformed")
    first_output_latency = (
        int(port_only["first_payload_output_valid_cycle"])
        - int(port_only["first_payload_input_handshake_cycle"])
    )
    handshake_cycles = [
        int(cycle) for cycle in port_only["payload_output_handshake_cycles"]
    ]
    if len(handshake_cycles) < 2:
        raise RuntimeError("insufficient payload handshakes for throughput measurement")
    throughput_intervals = [
        right - left
        for left, right in zip(handshake_cycles, handshake_cycles[1:])
    ]
    if len(set(throughput_intervals)) != 1:
        raise RuntimeError(
            f"no-stall payload intervals are not constant: {throughput_intervals}"
        )

    latency = {
        "cycle_definition": (
            "cycle 0 is the first monitored rising-edge transfer opportunity "
            "for each frame; all listed handshakes use pre-edge ready/valid values"
        ),
        "registered_first_output_latency_cycles": first_output_latency,
        "no_stall_payload_throughput_cycles_per_byte": throughput_intervals[0],
        "fixed_output_backpressure_added_result_cycles": (
            int(fixed_bp["result_handshake_cycle"])
            - int(no_stall["result_handshake_cycle"])
        ),
        "port_only_accepted": port_only,
        "message_filter_accepted": latency_directed["msg_multi"],
        "port_mismatch": latency_directed["port_mismatch"],
        "message_mismatch": latency_directed["message_mismatch"],
        "late_truncation": latency_directed["late_middle"],
        "fixed_backpressure_baseline": no_stall,
        "fixed_backpressure_case": fixed_bp,
    }
    (RESULTS / "latency_metrics.json").write_text(
        json.dumps(latency, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    lat_md = [
        "# Measured simulation latency",
        "",
        str(latency["cycle_definition"]),
        "",
        (
            "- First payload output-valid latency: "
            f"`{first_output_latency}` cycle(s) after its input handshake."
        ),
        (
            "- No-stall sustained payload throughput: one byte every "
            f"`{throughput_intervals[0]}` cycle(s)."
        ),
        (
            "- Fixed periodic output backpressure added "
            f"`{latency['fixed_output_backpressure_added_result_cycles']}` cycles "
            "through result handshake versus the same no-stall frame."
        ),
        "",
        "## Scenario event cycles",
        "",
    ]
    for key in [
        "port_only_accepted",
        "message_filter_accepted",
        "port_mismatch",
        "message_mismatch",
        "late_truncation",
    ]:
        lat_md += [f"### {key.replace('_', ' ').title()}", ""]
        scenario = latency[key]
        if not isinstance(scenario, dict):
            raise RuntimeError(f"latency scenario is malformed: {key}")
        lat_md += [
            f"- `{name}`: `{event}`"
            for name, event in scenario.items()
            if not name.startswith("saw_")
            and name != "payload_output_handshake_cycles"
        ]
        lat_md.append("")
    (RESULTS / "latency_metrics.md").write_text(
        "\n".join(lat_md), encoding="utf-8", newline="\n"
    )

    matrix_md = [
        "# Verification matrix",
        "",
        "Every row below comes from a named scenario reported by the passing cocotb regression.",
        "",
        "| ID | Executed scenario | Test source | Result |",
        "|---:|---|---|---|",
    ]
    for index, (name, source, status) in enumerate(matrix_rows, 1):
        matrix_md.append(f"| {index} | {name} | `{source}` | {status} |")
    (RESULTS / "verification_matrix.md").write_text(
        "\n".join(matrix_md) + "\n", encoding="utf-8", newline="\n"
    )

    versions = [
        f"Python: {platform.python_version()}",
        f"pytest: {importlib.metadata.version('pytest')}",
        f"cocotb: {importlib.metadata.version('cocotb')}",
        f"Icarus: {tool_version(['iverilog', '-V'])}",
        f"Verilator: {lint['tool_version']}",
        f"Yosys: {synth['tool_version']}",
    ]
    (RESULTS / "tool_versions.txt").write_text(
        "\n".join(versions) + "\n", encoding="utf-8", newline="\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
