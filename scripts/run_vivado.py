"""Vivado implementation results for the Basys 3 (XC7A35T), run locally.

Not part of run_all.py or CI, because Vivado is not freely redistributable.
Finds Vivado through $VIVADO, PATH, or the default install folders, runs
synth/vivado_ooc.tcl, and writes results/vivado_summary.{json,md}.

The RTL is copied to an ASCII-only temporary folder first, because Vivado
does not handle non-ASCII characters in paths reliably.
"""

from __future__ import annotations

import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TCL = ROOT / "synth" / "vivado_ooc.tcl"
RTL_FILES = ["stream_byte_buffer.sv", "udp_packet_filter.sv", "udp_packet_filter_reason_codes.svh"]
XC7A35T = {"Slice LUTs": 20800, "Slice Registers": 41600, "Slice": 8150}


def find_vivado() -> str | None:
    candidates = [os.environ.get("VIVADO"), shutil.which("vivado")]
    patterns = [
        "C:/AMDDesignTools/*/Vivado/bin/vivado.bat",
        "C:/Xilinx/Vivado/*/bin/vivado.bat",
        "/tools/Xilinx/Vivado/*/bin/vivado",
        "/opt/Xilinx/Vivado/*/bin/vivado",
    ]
    for pattern in patterns:
        candidates += sorted(glob.glob(pattern), reverse=True)
    return next((c for c in candidates if c and Path(c).is_file()), None)


def utilization(report: str) -> dict[str, int]:
    """Read 'Used' counts from the Vivado utilization report tables."""
    used = {}
    for name in ["Slice LUTs", "LUT as Logic", "Slice Registers", "CARRY4", "Slice",
                 "F7 Muxes", "Block RAM Tile", "DSPs"]:
        match = re.search(rf"^\|\s*{re.escape(name)}\*?\s*\|\s*(\d+)\s*\|", report, re.MULTILINE)
        if match:
            used[name] = int(match.group(1))
    return used


def main() -> int:
    vivado = find_vivado()
    if not vivado:
        print("ERROR: Vivado not found; set VIVADO to vivado(.bat)", file=sys.stderr)
        return 2

    work = Path(tempfile.mkdtemp(prefix="udp_vivado_"))
    try:
        rtl = work / "rtl"
        rtl.mkdir()
        for name in RTL_FILES:
            shutil.copyfile(ROOT / "rtl" / name, rtl / name)
        shutil.copyfile(TCL, work / TCL.name)
        out = work / "out"
        completed = subprocess.run(
            [vivado, "-mode", "batch", "-nojournal", "-log", "vivado.log",
             "-source", TCL.name, "-tclargs", "rtl", "out"],
            cwd=work, text=True, capture_output=True, errors="replace",
        )
        raw = ROOT / "results" / "raw" / "vivado"
        if raw.exists():
            shutil.rmtree(raw)
        raw.mkdir(parents=True)
        for path in [work / "vivado.log", *out.glob("*.rpt"), out / "summary.txt"]:
            if path.is_file():
                shutil.copyfile(path, raw / path.name)
        if completed.returncode or not (out / "summary.txt").is_file():
            print(completed.stdout[-4000:] + completed.stderr[-2000:], file=sys.stderr)
            print("ERROR: Vivado run failed; see results/raw/vivado/vivado.log", file=sys.stderr)
            return 1

        fields = dict(line.split(" ", 1) for line in
                      (out / "summary.txt").read_text(encoding="utf-8").splitlines() if line)
        used = utilization((out / "utilization.rpt").read_text(encoding="utf-8", errors="replace"))
    finally:
        shutil.rmtree(work, ignore_errors=True)

    period = float(fields["period_ns"])
    wns = float(fields["wns_ns"])
    whs = float(fields["whs_ns"])
    fmax = round(1000.0 / (period - wns), 1)
    summary = {
        "status": "pass" if wns >= 0 and whs >= 0 else "fail",
        "vivado_version": fields["vivado_version"],
        "part": fields["part"],
        "mode": "out of context (register to register)",
        "clock_target_mhz": round(1000.0 / period, 1),
        "wns_ns": wns,
        "whs_ns": whs,
        "estimated_fmax_mhz": fmax,
        "critical_path": {
            "from": fields["critical_from"],
            "to": fields["critical_to"],
            "logic_levels": int(fields["logic_levels"]),
        },
        "utilization": used,
        "utilization_percent": {
            name: round(100 * used[name] / total, 1)
            for name, total in XC7A35T.items() if name in used
        },
    }
    (ROOT / "results" / "vivado_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8", newline="\n")

    lines = [
        "# Vivado results: Basys 3 (XC7A35T-1)",
        "",
        f"- Status: `{summary['status']}` (timing met at {summary['clock_target_mhz']} MHz)"
        if summary["status"] == "pass" else f"- Status: `{summary['status']}`",
        f"- Tool: Vivado {summary['vivado_version']}, part `{summary['part']}`, "
        "out of context (no I/O), default directives",
        f"- Worst setup slack (WNS): {wns:.3f} ns at an 8.000 ns clock, "
        f"so roughly {fmax} MHz is reachable",
        f"- Worst hold slack (WHS): {whs:.3f} ns",
        f"- Critical path: `{fields['critical_from']}` to `{fields['critical_to']}`, "
        f"{fields['logic_levels']} logic levels",
        "",
        "| Resource | Used | Share of XC7A35T |",
        "|---|---:|---:|",
    ]
    for name, count in used.items():
        share = summary["utilization_percent"].get(name)
        lines.append(f"| {name} | {count} | {f'{share}%' if share is not None else '-'} |")
    lines += [
        "",
        "Run locally with `python scripts/run_vivado.py`; CI cannot run Vivado. "
        "Full reports are written to `results/raw/vivado/` (not committed).",
    ]
    (ROOT / "results" / "vivado_summary.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print("\n".join(lines))
    return 0 if summary["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
