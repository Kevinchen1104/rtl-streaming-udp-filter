# Vivado results: Basys 3 (XC7A35T-1)

- Status: `pass` (timing met at 125.0 MHz)
- Tool: Vivado 2026.1, part `xc7a35tcpg236-1`, out of context (no I/O), default directives
- Worst setup slack (WNS): 2.287 ns at an 8.000 ns clock, so roughly 175.0 MHz is reachable
- Worst hold slack (WHS): 0.151 ns
- Critical path: `field_hi_reg[1]/C` to `FSM_sequential_state_reg[1]/CE`, 5 logic levels

| Resource | Used | Share of XC7A35T |
|---|---:|---:|
| Slice LUTs | 327 | 1.6% |
| LUT as Logic | 327 | - |
| Slice Registers | 341 | 0.8% |
| CARRY4 | 24 | - |
| Slice | 136 | 1.7% |
| F7 Muxes | 0 | - |
| Block RAM Tile | 0 | - |
| DSPs | 0 | - |

Run locally with `python scripts/run_vivado.py`; CI cannot run Vivado. Full reports are written to `results/raw/vivado/` (not committed).
