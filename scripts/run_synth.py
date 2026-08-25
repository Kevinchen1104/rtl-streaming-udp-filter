from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    raw = ROOT / "results" / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    executable = shutil.which("yosys")
    if not executable:
        print("ERROR: yosys is required for generic synthesis", file=sys.stderr)
        return 2
    version_run = subprocess.run(
        [executable, "-V"], cwd=ROOT, text=True, capture_output=True,
        errors="replace",
    )
    version_lines = [
        line.strip()
        for line in (version_run.stdout + version_run.stderr).splitlines()
        if line.strip()
    ]
    if version_run.returncode or not version_lines:
        print("ERROR: unable to determine Yosys version", file=sys.stderr)
        return 2
    version = version_lines[0]
    execute_command = [executable, "-s", "synth/udp_packet_filter.ys"]
    command = ["yosys", "-s", "synth/udp_packet_filter.ys"]
    completed = subprocess.run(
        execute_command, cwd=ROOT, text=True, capture_output=True, errors="replace"
    )
    output = completed.stdout + completed.stderr
    (raw / "synthesis.log").write_text(
        "$ " + " ".join(command) + "\n" + output,
        encoding="utf-8", newline="\n",
    )

    hierarchy_sections = output.split("=== design hierarchy ===")
    hierarchy = hierarchy_sections[-1] if len(hierarchy_sections) > 1 else ""
    total_match = re.search(r"Number of cells:\s+(\d+)", hierarchy)
    cells: dict[str, int] = {}
    if total_match:
        after_total = hierarchy[total_match.end():]
        for cell_type, count in re.findall(r"^\s+(\S+)\s+(\d+)\s*$", after_total, re.MULTILINE):
            if cell_type.startswith("$_"):
                cells[cell_type] = int(count)
    warnings = [line.strip() for line in output.splitlines()
                if "warning:" in line.lower()]
    zero_problems = "Found and reported 0 problems." in output
    inferred_latches = [
        line.strip()
        for line in output.splitlines()
        if re.search(r"(?<!No )latch inferred for signal", line, re.IGNORECASE)
    ]
    no_latches = (
        "No latch inferred" in output
        and not inferred_latches
        and "dlatch" not in hierarchy.lower()
    )
    gate_status = (
        completed.returncode
        or (0 if total_match else 1)
        or (0 if zero_problems else 1)
        or (0 if no_latches else 1)
        or (1 if warnings else 0)
    )
    summary = {
        "status": "pass" if gate_status == 0 else "fail",
        "command": command,
        "script": "synth/udp_packet_filter.ys",
        "exit_status": gate_status,
        "tool_exit_status": completed.returncode,
        "tool_version": version,
        "top_module": "udp_packet_filter",
        "parameters": {"MAX_LOGICAL_FRAME_BYTES": 2048},
        "total_cells_hierarchical": int(total_match.group(1)) if total_match else None,
        "cell_types": cells,
        "warnings": warnings,
        "check_reported_zero_problems": zero_problems,
        "inferred_latches": inferred_latches,
        "no_inferred_latches": no_latches,
    }
    (ROOT / "results" / "synthesis_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8", newline="\n"
    )
    md = [
        "# Generic synthesis summary", "",
        f"- Status: `{summary['status']}`",
        f"- Tool: `{version}`",
        f"- Gate exit status: `{gate_status}`",
        f"- Tool exit status: `{completed.returncode}`",
        "- Top: `udp_packet_filter`",
        "- `MAX_LOGICAL_FRAME_BYTES`: `2048`",
        f"- Hierarchical total cells: `{summary['total_cells_hierarchical']}`",
        f"- Yosys check: `{'0 problems' if zero_problems else 'not confirmed'}`",
        f"- Inferred latches: `{'none' if no_latches else 'review required'}`",
        f"- Command: `{' '.join(command)}`", "", "## Cell types", "",
    ]
    md += [f"- `{name}`: {count}" for name, count in sorted(cells.items())]
    md += ["", "## Warnings", ""]
    md += [f"- {warning}" for warning in warnings] if warnings else ["None emitted."]
    md += ["", "This is generic synthesis evidence, not FPGA timing, LUT, WNS, or Fmax evidence."]
    (ROOT / "results" / "synthesis_summary.md").write_text(
        "\n".join(md) + "\n", encoding="utf-8", newline="\n"
    )
    print(output, end="")
    return gate_status


if __name__ == "__main__":
    raise SystemExit(main())
