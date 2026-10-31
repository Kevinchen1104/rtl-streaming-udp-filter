"""Run the SymbiYosys proof and cover tasks in formal/."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys

from yosys_tools import ROOT, version


FORMAL = ROOT / "formal"
SBY_FILE = "udp_packet_filter.sby"
TASKS = ["prove", "cover"]


def main() -> int:
    raw = ROOT / "results" / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    sby = shutil.which("sby")
    if not sby:
        print("ERROR: sby not found on PATH (install OSS CAD Suite)", file=sys.stderr)
        return 2

    completed = subprocess.run([sby, "-f", SBY_FILE, *TASKS], cwd=FORMAL, text=True,
                               capture_output=True, errors="replace")
    output = completed.stdout + completed.stderr
    (raw / "formal.log").write_text(output, encoding="utf-8", newline="\n")

    results = {}
    for task in TASKS:
        status_file = FORMAL / f"udp_packet_filter_{task}" / "status"
        status = (status_file.read_text(encoding="utf-8").split() or ["UNKNOWN"])[0] \
            if status_file.is_file() else "MISSING"
        results[task] = status
    passed = completed.returncode == 0 and all(s == "PASS" for s in results.values())

    summary = {
        "status": "pass" if passed else "fail",
        "tool_version": version("yosys"),
        "tasks": results,
        "properties_file": "formal/udp_packet_filter_formal.sv",
    }
    (ROOT / "results" / "formal_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8", newline="\n")
    lines = [
        "# Formal verification",
        "",
        f"- Status: `{summary['status']}`",
        f"- Tool: SymbiYosys with {summary['tool_version']}",
        f"- Properties: [`formal/udp_packet_filter_formal.sv`](../formal/udp_packet_filter_formal.sv)",
        "",
        "| Task | Engine | Result |",
        "|---|---|---|",
        f"| prove | `abc pdr` (unbounded) | {results['prove']} |",
        f"| cover | `smtbmc yices`, depth 64 | {results['cover']} |",
    ]
    (ROOT / "results" / "formal_summary.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(output, end="")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
