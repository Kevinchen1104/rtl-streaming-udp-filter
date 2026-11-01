from __future__ import annotations

from pathlib import Path

from cocotb_tools.runner import get_runner


def test_hw_wrapper(repo_root: Path, simulator_name: str) -> None:
    """Simulate the Basys 3 test harness with a fast UART."""
    runner = get_runner(simulator_name)
    rtl = repo_root / "rtl"
    board = repo_root / "fpga" / "basys3"
    sources = [
        rtl / "stream_byte_buffer.sv",
        rtl / "udp_packet_filter_checks.sv",
        rtl / "udp_packet_filter.sv",
        board / "uart_rx.sv",
        board / "uart_tx.sv",
        board / "sync_fifo.sv",
        board / "bram_fifo.sv",
        board / "hw_test_core.sv",
    ]
    build_dir = repo_root / "build" / f"cocotb-hw-{simulator_name}"
    runner.build(
        sources=sources,
        hdl_toplevel="hw_test_core",
        build_dir=build_dir,
        always=True,
        clean=True,
        build_args=["-g2012"] if simulator_name == "icarus" else [],
        includes=[rtl],
        parameters={"CLKS_PER_BIT": 8},
    )
    runner.test(
        hdl_toplevel="hw_test_core",
        test_module="sim.hw_wrapper_testbench",
        test_dir=build_dir,
    )
