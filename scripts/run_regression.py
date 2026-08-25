from __future__ import annotations

import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "results" / "raw"


def run_pytest(
    name: str, targets: list[str], junit_name: str
) -> subprocess.CompletedProcess[str]:
    command = [
        sys.executable,
        "-m",
        "pytest",
        *targets,
        "-ra",
        "-p",
        "no:cacheprovider",
        f"--junitxml={RAW / junit_name}",
    ]
    completed = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        errors="replace",
    )
    with (RAW / "regression.log").open("a", encoding="utf-8") as log:
        log.write(f"\n== {name} ==\n$ {' '.join(map(str, command))}\n")
        log.write(completed.stdout)
        log.write(completed.stderr)
    print(completed.stdout, end="")
    print(completed.stderr, end="", file=sys.stderr)
    return completed


def junit_case_count(path: Path) -> int:
    root = ET.parse(path).getroot()
    return sum(1 for _ in root.iter("testcase"))


def junit_case_names(path: Path) -> list[str]:
    root = ET.parse(path).getroot()
    names = [node.get("name") for node in root.iter("testcase")]
    if any(name is None for name in names):
        raise RuntimeError(f"unnamed testcase in JUnit report: {path}")
    return [str(name) for name in names]


def write_status(payload: dict[str, object]) -> None:
    (RAW / "regression.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n"
    )


def main() -> int:
    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / "regression.log").write_text("", encoding="utf-8", newline="\n")

    reference = run_pytest(
        "Reference model",
        ["sim/test_reference_model.py"],
        "reference_model_junit.xml",
    )
    if reference.returncode:
        write_status({
            "status": "fail",
            "failed_stage": "reference_model",
            "exit_status": reference.returncode,
        })
        return reference.returncode

    rtl = run_pytest(
        "RTL regression",
        ["sim/test_udp_packet_filter.py"],
        "rtl_junit.xml",
    )
    if rtl.returncode:
        write_status({
            "status": "fail",
            "failed_stage": "rtl_regression",
            "exit_status": rtl.returncode,
            "reference_model_pytest_cases": junit_case_count(
                RAW / "reference_model_junit.xml"
            ),
        })
        return rtl.returncode

    expected_coroutines = {
        "directed_rtl_matrix": "directed_matrix.json",
        "backpressure_and_sequencing": "backpressure.json",
        "fixed_seed_randomized_regression": "randomized.json",
        "reset_abort_matrix": "reset.json",
    }
    simulator = os.environ.get("SIM", "icarus")
    cocotb_junit = (
        ROOT / "build" / f"cocotb-{simulator}"
        / "test_rtl_regression.result.xml"
    )
    actual_coroutines = junit_case_names(cocotb_junit)
    if set(actual_coroutines) != set(expected_coroutines):
        write_status({
            "status": "fail",
            "failed_stage": "cocotb_case_inventory",
            "expected": sorted(expected_coroutines),
            "actual": sorted(actual_coroutines),
        })
        raise RuntimeError(
            "cocotb testcase inventory differs from the expected evidence set"
        )

    for artifact_name in expected_coroutines.values():
        path = RAW / artifact_name
        if not path.is_file():
            raise RuntimeError(f"missing cocotb result artifact: {path}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("status") != "pass":
            raise RuntimeError(f"cocotb artifact did not report pass: {path}")

    write_status({
        "status": "pass",
        "reference_model_pytest_cases": junit_case_count(
            RAW / "reference_model_junit.xml"
        ),
        "rtl_pytest_entry_cases": junit_case_count(RAW / "rtl_junit.xml"),
        "cocotb_test_coroutines": len(actual_coroutines),
        "cocotb_testcase_names": actual_coroutines,
        "cocotb_result_artifacts": list(expected_coroutines.values()),
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
