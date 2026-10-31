# FPGA results

- Status: `pass`
- Tools: Yosys 0.69+173 (git sha1 53f1cdd34-dirty, Release, Clang /usr/bin/clang++ 21.1.8); nextpnr-0.11.1-40-geb4f15c3

## Lattice ECP5 LFE5U-25F (speed grade 6), place and route

Out of context (no I/O pins), so these are register-to-register numbers. Target 125 MHz: 8 bits per cycle at 125 MHz is 1 Gb/s. Logic cells are nextpnr's TRELLIS_COMB count (each a LUT4 or half a carry cell).

| Seed | Fmax (MHz) | Logic cells | FF |
|---:|---:|---:|---:|
| 1 | 126.4 | 1019 / 24288 | 346 / 24288 |
| 2 | 129.3 | 1019 / 24288 | 346 / 24288 |
| 3 | 132.3 | 1019 / 24288 | 346 / 24288 |
| 4 | 126.1 | 1019 / 24288 | 346 / 24288 |
| 5 | 130.7 | 1019 / 24288 | 346 / 24288 |

## Xilinx 7-series estimate (synthesis only)

Yosys `synth_xilinx` cell counts, not Vivado results, and no timing.

| Resource | Count | Share of XC7A35T (Basys 3) |
|---|---:|---:|
| LUT | 571 | 2.7% |
| FF | 346 | 0.8% |
| CARRY4 | 27 | - |
| MUXF7/F8 | 0 | - |
| BRAM/DSP | 0 | - |
