# Generic synthesis summary

- Status: `pass`
- Tool: `Yosys 0.56 (git sha1 9c447ad9d4b1ea589369364eea38b4d70da2c599, x86_64-w64-mingw32-g++ 16.1.0 -march=nocona -msahf -mtune=generic -O2 -fstack-protector-strong -O3)`
- Gate exit status: `0`
- Tool exit status: `0`
- Top: `udp_packet_filter`
- `MAX_LOGICAL_FRAME_BYTES`: `2048`
- Hierarchical total cells: `3210`
- Yosys check: `0 problems`
- Inferred latches: `none`
- Command: `yosys -s synth/udp_packet_filter.ys`

## Cell types

- `$_ANDNOT_`: 162
- `$_AND_`: 101
- `$_DFF_P_`: 9
- `$_MUX_`: 863
- `$_NAND_`: 74
- `$_NOR_`: 661
- `$_NOT_`: 128
- `$_ORNOT_`: 607
- `$_OR_`: 115
- `$_SDFFE_PN0P_`: 332
- `$_XNOR_`: 130
- `$_XOR_`: 28

## Warnings

None emitted.

This is generic synthesis evidence, not FPGA timing, LUT, WNS, or Fmax evidence.
