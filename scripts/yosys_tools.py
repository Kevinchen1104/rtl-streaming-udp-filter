"""Helpers shared by the Yosys-based scripts."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RTL_SOURCES = ["rtl/stream_byte_buffer.sv", "rtl/udp_packet_filter.sv"]
TOP = "udp_packet_filter"

# Messages that newer Yosys/ABC builds print on every run and that say
# nothing about the design.
BENIGN_WARNINGS = [
    re.compile(r"ABC: Warning: The network is combinational"),
    re.compile(r"Warning: Feature 'write_xaiger2' is experimental"),
]


def require(tool: str) -> str:
    path = shutil.which(tool)
    if not path:
        raise RuntimeError(f"{tool} not found on PATH (install OSS CAD Suite)")
    return path


def version(tool: str, flag: str = "-V") -> str:
    completed = subprocess.run([require(tool), flag], text=True, capture_output=True,
                               errors="replace")
    lines = [line.strip() for line in (completed.stdout + completed.stderr).splitlines()
             if line.strip()]
    if completed.returncode or not lines:
        raise RuntimeError(f"could not read {tool} version")
    return lines[0]


def run(command: list[str], log_path: Path) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True,
                               errors="replace")
    log_path.write_text("$ " + " ".join(command) + "\n" + completed.stdout + completed.stderr,
                        encoding="utf-8", newline="\n")
    return completed


def design_warnings(output: str) -> list[str]:
    warnings = []
    for line in output.splitlines():
        if "warning" not in line.lower():
            continue
        if any(pattern.search(line) for pattern in BENIGN_WARNINGS):
            continue
        warnings.append(line.strip())
    return warnings


def cell_counts(stat_json: Path) -> tuple[int, dict[str, int]]:
    """Total cells and cells by type from a flattened `stat -json` report."""
    design = json.loads(stat_json.read_text(encoding="utf-8"))["design"]
    by_type = {name: int(count) for name, count in design["num_cells_by_type"].items()}
    return int(design["num_cells"]), dict(sorted(by_type.items()))
