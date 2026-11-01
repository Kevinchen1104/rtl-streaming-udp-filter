"""cocotb tests for the Basys 3 hardware-test harness (fpga/basys3/hw_test_core.sv).

The UART runs at 8 clocks per bit here so a few dozen frames simulate in
seconds. Responses go through the same parser and checks as the real board.
"""

from __future__ import annotations

import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge

from sim.frames import CATEGORY_WEIGHTS, MSG, PORT, directed_cases, model, random_case
from sim.hw_protocol import CMD_RESET, ResponseParser, check_response, frame_command

CLKS_PER_BIT = 8


async def uart_send(dut, data: bytes) -> None:
    for byte in data:
        for bit in [0, *[(byte >> i) & 1 for i in range(8)], 1]:
            dut.uart_rx_i.value = bit
            await ClockCycles(dut.clk, CLKS_PER_BIT)


async def uart_monitor(dut, parser: ResponseParser) -> None:
    while True:
        await FallingEdge(dut.uart_tx_o)
        await ClockCycles(dut.clk, CLKS_PER_BIT // 2)
        if int(dut.uart_tx_o.value) != 0:
            continue
        byte = 0
        for index in range(8):
            await ClockCycles(dut.clk, CLKS_PER_BIT)
            byte |= int(dut.uart_tx_o.value) << index
        await ClockCycles(dut.clk, CLKS_PER_BIT)
        parser.feed(bytes([byte]))


async def start(dut) -> ResponseParser:
    cocotb.start_soon(Clock(dut.clk, 8, unit="ns").start())
    dut.uart_rx_i.value = 1
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 5)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 5)
    parser = ResponseParser()
    cocotb.start_soon(uart_monitor(dut, parser))
    return parser


async def wait_for(dut, condition, max_cycles: int) -> None:
    for _ in range(max_cycles // 100):
        if condition():
            return
        await ClockCycles(dut.clk, 100)
    raise AssertionError("timed out waiting for the board model to answer")


async def run_batch(dut, parser: ResponseParser,
                    cases: list[tuple[bytes, bool, int]], first_sequence: int) -> None:
    """Send all frames back to back, then check every response in order."""
    already = len(parser.frames)
    for frame, msg_enabled, stall in cases:
        await uart_send(dut, frame_command(frame, dst_port=PORT, msg_type_enable=msg_enabled,
                                           msg_type=MSG, stall_level=stall))
    await wait_for(dut, lambda: len(parser.frames) == already + len(cases), 2_000_000)
    for offset, (frame, msg_enabled, _) in enumerate(cases):
        expected = model(frame, first_sequence + offset, msg_enabled)
        problems = check_response(parser.frames[already + offset], expected)
        assert not problems, f"frame {offset}: {problems}"


@cocotb.test()
async def reset_command_is_acknowledged(dut) -> None:
    parser = await start(dut)
    await uart_send(dut, bytes([CMD_RESET]))
    await wait_for(dut, lambda: parser.reset_acks == 1, 10_000)


@cocotb.test()
async def directed_frames_round_trip(dut) -> None:
    """Short directed frames with no, some, and heavy output stalls."""
    parser = await start(dut)
    cases = [(frame, msg, (0, 128, 220)[index % 3])
             for index, (_, frame, msg) in enumerate(directed_cases()) if len(frame) <= 120]
    await run_batch(dut, parser, cases, 0)

    # A reset command restarts the sequence numbers.
    await uart_send(dut, bytes([CMD_RESET]))
    await wait_for(dut, lambda: parser.reset_acks == 1, 10_000)
    await run_batch(dut, parser, cases[:2], 0)


@cocotb.test()
async def random_frames_round_trip(dut) -> None:
    parser = await start(dut)
    rng = random.Random(3)
    names, weights = list(CATEGORY_WEIGHTS), list(CATEGORY_WEIGHTS.values())
    cases = []
    while len(cases) < 12:
        case = random_case(rng, rng.choices(names, weights)[0])
        if len(case.frame) <= 200:
            cases.append((case.frame, case.msg_enabled, rng.choice([0, 64, 128, 192])))
    await run_batch(dut, parser, cases, 0)
