# Changelog

## Unreleased

- Vivado out-of-context implementation for the Basys 3 (XC7A35T-1):
  `scripts/run_vivado.py` and `synth/vivado_ooc.tcl`, run locally. 327 LUTs,
  341 FFs, 125 MHz met with 2.3 ns of slack.

## 1.1.0

Design
- `s_axis_tready` comes from a flop: the payload buffer is now a two-entry
  skid buffer, and the first-payload state no longer makes ready depend on
  `s_axis_tdata`.
- The result reason follows one whole-frame priority order. A frame rejected
  by the port or message filter that ends before its declared datagram end now
  reports `BAD_LENGTH_OR_TRUNCATED`.
- Critical path shortened for 125 MHz on ECP5 (down-counting payload counter
  with registered flags, length and port checks one byte early).
- 6-bit header counter instead of a 16-bit byte counter.

Verification
- Each scenario is its own cocotb test; the verification matrix comes from
  the JUnit report.
- Coverage bins are declared with goals, and a missed goal fails the run.
- Random traffic rebalanced toward accepted frames and output stalls.
- New tests: back-to-back frames, input ready isolation, waveform traces.
- SymbiYosys proof of the handshake and frame-accounting properties.

Flow
- FPGA results: ECP5 place and route with a 125 MHz gate, Xilinx 7-series
  resource estimate.
- CI and checked-in results use the same pinned OSS CAD Suite build.

## 1.0.0

First release.
