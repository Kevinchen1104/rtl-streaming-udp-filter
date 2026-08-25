from __future__ import annotations

import os
from pathlib import Path

from cocotb_tools.runner import get_runner


def test_rtl_regression(repo_root: Path, simulator_name: str) -> None:
    runner = get_runner(simulator_name)
    sources = [
        repo_root / "rtl" / "stream_byte_buffer.sv",
        repo_root / "rtl" / "udp_packet_filter_sva.sv",
        repo_root / "rtl" / "udp_packet_filter.sv",
    ]
    build_dir = repo_root / "build" / f"cocotb-{simulator_name}"
    runner.build(
        sources=sources,
        hdl_toplevel="udp_packet_filter",
        build_dir=build_dir,
        always=True,
        clean=True,
        build_args=["-g2012"] if simulator_name == "icarus" else [],
        includes=[repo_root],
    )
    os.environ["UDP_FILTER_REPO_ROOT"] = str(repo_root)
    runner.test(
        hdl_toplevel="udp_packet_filter",
        test_module="sim.rtl_testbench",
        test_dir=build_dir,
    )
