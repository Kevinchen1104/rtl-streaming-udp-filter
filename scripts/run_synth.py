"""Generic Yosys synthesis: the RTL lowers to gates with no problems or latches.

Cell counts here are tool-version dependent and only a sanity check. FPGA
resource and timing numbers come from scripts/run_fpga.py.
"""

from __future__ import annotations

import json
import sys

from yosys_tools import ROOT, TOP, cell_counts, design_warnings, require, run, version


SCRIPT = "synth/udp_packet_filter.ys"


def main() -> int:
    raw = ROOT / "results" / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    try:
        yosys = require("yosys")
        tool_version = version("yosys")
    except RuntimeError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    completed = run([yosys, "-s", SCRIPT], raw / "synthesis.log")
    output = completed.stdout + completed.stderr
    stat_path = raw / "generic_stat.json"
    total, by_type = cell_counts(stat_path) if stat_path.is_file() else (0, {})
    latches = {name: count for name, count in by_type.items() if "latch" in name.lower()}
    warnings = design_warnings(output)

    problems = []
    if completed.returncode:
        problems.append(f"yosys exited {completed.returncode} (check -assert fails on problems)")
    if not total:
        problems.append("no cell statistics")
    if latches:
        problems.append(f"latches inferred: {latches}")
    if warnings:
        problems.append(f"{len(warnings)} warnings")

    summary = {
        "status": "fail" if problems else "pass",
        "problems": problems,
        "tool_version": tool_version,
        "script": SCRIPT,
        "top_module": TOP,
        "total_cells": total,
        "cell_types": by_type,
        "latches": latches,
        "warnings": warnings,
    }
    (ROOT / "results" / "synthesis_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8", newline="\n")
    lines = [
        "# Generic synthesis",
        "",
        f"- Status: `{summary['status']}`",
        f"- Tool: {tool_version}",
        f"- Script: `{SCRIPT}` (flattened, `check -assert`)",
        f"- Latches: {'none' if not latches else latches}",
        f"- Warnings: {len(warnings)}",
        f"- Generic cells: {total}",
        "",
        "Generic cell counts change between Yosys versions; see "
        "[FPGA results](fpga_summary.md) for LUT, FF, and timing numbers.",
    ]
    if problems:
        lines += ["", "## Problems", ""] + [f"- {problem}" for problem in problems]
    if warnings:
        lines += ["", "## Warnings", ""] + [f"- `{warning}`" for warning in warnings]
    (ROOT / "results" / "synthesis_summary.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(output, end="")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
