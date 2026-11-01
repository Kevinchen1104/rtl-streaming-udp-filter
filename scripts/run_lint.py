from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(
    command: list[str], environment: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command, cwd=ROOT, text=True, encoding="utf-8",
        capture_output=True, errors="replace", env=environment
    )


def find_verilator() -> str | None:
    found = shutil.which("verilator")
    if found:
        return found
    if os.name == "nt":
        for directory in os.environ.get("PATH", "").split(os.pathsep):
            candidate = Path(directory) / "verilator"
            if candidate.is_file():
                return str(candidate)
    return None


def run_verilator(executable: str, arguments: list[str]) -> subprocess.CompletedProcess[str]:
    if os.name == "nt":
        binary = Path(executable).with_name("verilator_bin.exe")
        root = Path(executable).parent.parent / "share" / "verilator"
        if binary.is_file() and root.is_dir():
            environment = os.environ.copy()
            environment["VERILATOR_ROOT"] = str(root)
            return run([str(binary), *arguments], environment)
    return run([executable, *arguments])


def main() -> int:
    raw = ROOT / "results" / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    executable = find_verilator()
    if not executable:
        print("ERROR: verilator is required for lint", file=sys.stderr)
        return 2
    version_binary = Path(executable).with_name("verilator_bin.exe")
    if os.name == "nt" and version_binary.is_file():
        version_run = run([str(version_binary), "--version"])
    else:
        version_run = run_verilator(executable, ["--version"])
    version_lines = [
        line.strip()
        for line in (version_run.stdout + version_run.stderr).splitlines()
        if line.strip()
    ]
    if version_run.returncode or not version_lines:
        print("ERROR: unable to determine Verilator version", file=sys.stderr)
        return 2
    filter_sources = ["rtl/stream_byte_buffer.sv", "rtl/udp_packet_filter.sv"]
    targets = {
        # The filter itself.
        "udp_packet_filter": filter_sources,
        # The Basys 3 test harness around it (the MMCM top is Vivado-only).
        "hw_test_core": filter_sources + [
            "fpga/basys3/uart_rx.sv", "fpga/basys3/uart_tx.sv",
            "fpga/basys3/sync_fifo.sv", "fpga/basys3/bram_fifo.sv",
            "fpga/basys3/hw_test_core.sv",
        ],
    }
    commands: list[list[str]] = []
    output = ""
    tool_status = 0
    for top, sources in targets.items():
        arguments = ["--lint-only", "--Wall", "--Wno-fatal", "-DSYNTHESIS",
                     "-Irtl", "--top-module", top, *sources]
        commands.append(["verilator", *arguments])
        completed = run_verilator(executable, arguments)
        output += "$ " + " ".join(commands[-1]) + "\n" + completed.stdout + completed.stderr
        tool_status = tool_status or completed.returncode
    warnings = [line for line in output.splitlines() if "%Warning" in line]
    gate_status = tool_status or (1 if warnings else 0)
    summary = {
        "status": "pass" if gate_status == 0 else "fail",
        "commands": commands,
        "exit_status": gate_status,
        "tool_exit_status": tool_status,
        "tool_version": version_lines[0],
        "warning_count": len(warnings),
        "warnings": warnings,
    }
    (raw / "lint.log").write_text(output, encoding="utf-8", newline="\n")
    (ROOT / "results" / "lint_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8", newline="\n"
    )
    md = [
        "# Lint summary", "", f"- Status: `{summary['status']}`",
        f"- Tool: `{summary['tool_version']}`",
        f"- Gate exit status: `{gate_status}`",
        f"- Tool exit status: `{tool_status}`",
        f"- Warnings: `{len(warnings)}`",
        "- Commands:",
        *[f"  - `{' '.join(command)}`" for command in commands],
        "",
    ]
    if warnings:
        md += ["## Warnings", ""] + [f"- `{warning}`" for warning in warnings]
    else:
        md.append("No warnings or errors were emitted.")
    (ROOT / "results" / "lint_summary.md").write_text(
        "\n".join(md) + "\n", encoding="utf-8", newline="\n"
    )
    print(output, end="")
    return gate_status


if __name__ == "__main__":
    raise SystemExit(main())
