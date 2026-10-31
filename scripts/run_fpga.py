"""FPGA resource and timing results with open-source tools.

- Lattice ECP5 LFE5U-25F, speed grade 6: synth_ecp5 and nextpnr-ecp5, out of
  context (no I/O pins), 125 MHz target, five placement seeds. Fails if any
  seed misses 125 MHz, the clock needed for 1 Gb/s at 8 bits per cycle.
- Xilinx 7-series (the XC7A35T on a Basys 3): synth_xilinx resource estimate
  only. Open-source place and route for 7-series is not mature enough to
  quote timing.
"""

from __future__ import annotations

import json
import re
import sys

from yosys_tools import ROOT, RTL_SOURCES, TOP, cell_counts, require, run, version


TARGET_MHZ = 125
SEEDS = [1, 2, 3, 4, 5]
ECP5_DEVICE = {"name": "LFE5U-25F", "flag": "--25k", "package": "CABGA381"}
XC7A35T = {"LUT": 20800, "FF": 41600}


def main() -> int:
    build = ROOT / "build" / "fpga"
    raw = ROOT / "results" / "raw"
    build.mkdir(parents=True, exist_ok=True)
    raw.mkdir(parents=True, exist_ok=True)
    try:
        yosys = require("yosys")
        nextpnr = require("nextpnr-ecp5")
        pnr_version = version("nextpnr-ecp5", "--version")
        match = re.search(r"Version ([^)\s]+)", pnr_version)
        versions = {"yosys": version("yosys"),
                    "nextpnr-ecp5": match.group(1) if match else pnr_version}
    except RuntimeError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    read = f"read_verilog -sv -Irtl -DSYNTHESIS {' '.join(RTL_SOURCES)}"
    problems: list[str] = []

    # ---- Xilinx 7-series resource estimate ------------------------------
    xc7_stat = "build/fpga/xc7_stat.json"
    xc7 = run([yosys, "-p", f"{read}; synth_xilinx -family xc7 -flatten -top {TOP}; "
                            f"tee -q -o {xc7_stat} stat -json"], raw / "fpga_xc7.log")
    if xc7.returncode:
        problems.append("synth_xilinx failed")
        xc7_cells: dict[str, int] = {}
    else:
        _, xc7_cells = cell_counts(ROOT / xc7_stat)
    xc7_summary = {
        "LUT": sum(n for cell, n in xc7_cells.items() if re.fullmatch(r"LUT[1-6]", cell)),
        "FF": sum(n for cell, n in xc7_cells.items() if re.fullmatch(r"FD[A-Z]{2}", cell)),
        "CARRY4": xc7_cells.get("CARRY4", 0),
        "MUXF7/F8": xc7_cells.get("MUXF7", 0) + xc7_cells.get("MUXF8", 0),
        "BRAM/DSP": sum(n for cell, n in xc7_cells.items() if cell.startswith(("RAMB", "DSP"))),
    }

    # ---- ECP5 synthesis, place and route --------------------------------
    ecp5_netlist = "build/fpga/ecp5.json"
    ecp5 = run([yosys, "-p", f"{read}; synth_ecp5 -top {TOP} -json {ecp5_netlist}"],
               raw / "fpga_ecp5_synth.log")
    runs = []
    if ecp5.returncode:
        problems.append("synth_ecp5 failed")
    else:
        for seed in SEEDS:
            report = f"build/fpga/ecp5_seed{seed}.json"
            pnr = run([nextpnr, ECP5_DEVICE["flag"], "--package", ECP5_DEVICE["package"],
                       "--out-of-context", "--json", ecp5_netlist, "--freq", str(TARGET_MHZ),
                       "--seed", str(seed), "--report", report, "--timing-allow-fail"],
                      raw / f"fpga_ecp5_pnr_seed{seed}.log")
            if pnr.returncode:
                problems.append(f"nextpnr-ecp5 failed for seed {seed}")
                continue
            data = json.loads((ROOT / report).read_text(encoding="utf-8"))
            used = data["utilization"]
            runs.append({
                "seed": seed,
                "fmax_mhz": round(float(data["fmax"]["clk"]["achieved"]), 1),
                "logic_cells": used["TRELLIS_COMB"]["used"],
                "logic_cells_available": used["TRELLIS_COMB"]["available"],
                "FF": used["TRELLIS_FF"]["used"],
                "FF_available": used["TRELLIS_FF"]["available"],
            })
    fmax = [entry["fmax_mhz"] for entry in runs]
    if fmax and min(fmax) < TARGET_MHZ:
        problems.append(f"Fmax {min(fmax)} MHz is below the {TARGET_MHZ} MHz target")

    summary = {
        "status": "fail" if problems or not runs else "pass",
        "problems": problems,
        "tool_versions": versions,
        "ecp5": {
            "device": ECP5_DEVICE["name"], "package": ECP5_DEVICE["package"],
            "speed_grade": 6, "out_of_context": True, "target_mhz": TARGET_MHZ,
            "fmax_min_mhz": min(fmax) if fmax else None,
            "fmax_max_mhz": max(fmax) if fmax else None,
            "runs": runs,
        },
        "xilinx_7series_estimate": {
            "cells": xc7_summary,
            "xc7a35t_percent": {
                key: round(100 * xc7_summary[key] / total, 1) for key, total in XC7A35T.items()
            },
        },
    }
    (ROOT / "results" / "fpga_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8", newline="\n")

    lines = [
        "# FPGA results",
        "",
        f"- Status: `{summary['status']}`",
        f"- Tools: {versions['yosys']}; {versions['nextpnr-ecp5']}",
        "",
        f"## Lattice ECP5 {ECP5_DEVICE['name']} (speed grade 6), place and route",
        "",
        "Out of context (no I/O pins), so these are register-to-register numbers. "
        f"Target {TARGET_MHZ} MHz: 8 bits per cycle at 125 MHz is 1 Gb/s. "
        "Logic cells are nextpnr's TRELLIS_COMB count (each a LUT4 or half a carry cell).",
        "",
        "| Seed | Fmax (MHz) | Logic cells | FF |",
        "|---:|---:|---:|---:|",
    ]
    lines += [f"| {r['seed']} | {r['fmax_mhz']} | {r['logic_cells']} / {r['logic_cells_available']} "
              f"| {r['FF']} / {r['FF_available']} |" for r in runs]
    lines += [
        "",
        "## Xilinx 7-series estimate (synthesis only)",
        "",
        "Yosys `synth_xilinx` cell counts, not Vivado results, and no timing.",
        "",
        "| Resource | Count | Share of XC7A35T (Basys 3) |",
        "|---|---:|---:|",
    ]
    for key, count in xc7_summary.items():
        share = summary["xilinx_7series_estimate"]["xc7a35t_percent"].get(key)
        lines.append(f"| {key} | {count} | {f'{share}%' if share is not None else '-'} |")
    if problems:
        lines += ["", "## Problems", ""] + [f"- {problem}" for problem in problems]
    (ROOT / "results" / "fpga_summary.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print("\n".join(lines))
    return 0 if summary["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
