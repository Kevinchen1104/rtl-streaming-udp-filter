"""Run the reference-model tests and the cocotb RTL regression.

Writes JUnit XML for both, a combined log, and results/raw/regression.json.
The cocotb JUnit report is copied to results/raw/cocotb_junit.xml; it is the
source of the verification matrix.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "results" / "raw"


def run_pytest(name: str, targets: list[str], junit_name: str) -> int:
    command = [
        sys.executable, "-m", "pytest", *targets,
        "-ra", "-p", "no:cacheprovider", f"--junitxml={RAW / junit_name}",
    ]
    completed = subprocess.run(
        command, cwd=ROOT, text=True, capture_output=True, errors="replace",
    )
    with (RAW / "regression.log").open("a", encoding="utf-8") as log:
        log.write(f"\n== {name} ==\n$ {' '.join(map(str, command))}\n")
        log.write(completed.stdout)
        log.write(completed.stderr)
    print(completed.stdout, end="")
    print(completed.stderr, end="", file=sys.stderr)
    return completed.returncode


def junit_results(path: Path) -> list[tuple[str, str]]:
    """Return (test name, pass|fail|skip) for every testcase in a JUnit file."""
    results = []
    for case in ET.parse(path).getroot().iter("testcase"):
        if case.find("failure") is not None or case.find("error") is not None:
            status = "fail"
        elif case.find("skipped") is not None:
            status = "skip"
        else:
            status = "pass"
        results.append((str(case.get("name")), status))
    return results


def write_status(payload: dict[str, object]) -> None:
    (RAW / "regression.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n"
    )


def main() -> int:
    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / "regression.log").write_text("", encoding="utf-8", newline="\n")

    if run_pytest("Reference model", ["sim/test_reference_model.py"],
                  "reference_model_junit.xml"):
        write_status({"status": "fail", "failed_stage": "reference_model"})
        return 1
    model_results = junit_results(RAW / "reference_model_junit.xml")

    simulator = os.environ.get("SIM", "icarus")
    cocotb_xml = ROOT / "build" / f"cocotb-{simulator}" / "test_rtl_regression.result.xml"
    cocotb_xml.unlink(missing_ok=True)
    rtl_status = run_pytest("RTL regression", ["sim/test_udp_packet_filter.py"],
                            "rtl_junit.xml")
    if not cocotb_xml.is_file():
        write_status({"status": "fail", "failed_stage": "rtl_regression",
                      "detail": "cocotb produced no results file"})
        return 1
    shutil.copyfile(cocotb_xml, RAW / "cocotb_junit.xml")
    rtl_results = junit_results(RAW / "cocotb_junit.xml")
    failed = [name for name, status in rtl_results if status != "pass"]
    if rtl_status or failed or not rtl_results:
        write_status({"status": "fail", "failed_stage": "rtl_regression",
                      "failed_tests": failed})
        return 1

    harness_xml = ROOT / "build" / f"cocotb-hw-{simulator}" / "test_hw_wrapper.result.xml"
    harness_xml.unlink(missing_ok=True)
    harness_status = run_pytest("Hardware-test harness", ["sim/test_hw_wrapper.py"],
                                "hw_harness_junit.xml")
    if not harness_xml.is_file():
        write_status({"status": "fail", "failed_stage": "hw_harness",
                      "detail": "cocotb produced no results file"})
        return 1
    shutil.copyfile(harness_xml, RAW / "hw_harness_cocotb_junit.xml")
    harness_results = junit_results(RAW / "hw_harness_cocotb_junit.xml")
    harness_failed = [name for name, status in harness_results if status != "pass"]
    if harness_status or harness_failed or not harness_results:
        write_status({"status": "fail", "failed_stage": "hw_harness",
                      "failed_tests": harness_failed})
        return 1

    write_status({
        "status": "pass",
        "simulator": simulator,
        "reference_model_tests": len(model_results),
        "cocotb_tests": len(rtl_results),
        "hw_harness_tests": len(harness_results),
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
