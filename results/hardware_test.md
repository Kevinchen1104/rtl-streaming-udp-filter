# Hardware test: Basys 3

- Status: `pass`: 2110 frames, every payload byte and result record matched the reference model.
- Board: Digilent Basys 3, `xc7a35tcpg236-1`. The filter runs at 125 MHz, made from the 100 MHz oscillator by an MMCM.
- Link: USB-UART at 1000 kbaud. Each frame is buffered on the FPGA, then streamed into the filter at one byte per clock.
- Bitstream: Vivado 2026.1, whole design (filter, UART, FIFOs): WNS 1.254 ns, WHS 0.063 ns at 125 MHz; 688 LUTs, 736 FFs.
- Run: 2026-11-01T05:43:16+00:00, commit `ed73898`, 4.5 s.

| Frames | Count |
|---|---:|
| directed | 68 |
| header truncation sweep | 42 |
| random seed 1 | 500 |
| random seed 7 | 500 |
| random seed 42 | 500 |
| random seed 2027 | 500 |
| **total** | **2110** |

1211 frames ran with random output and result stalls; 79048 payload beats were checked.

| Expected reason | Frames |
|---|---:|
| `ACCEPT` | 717 |
| `BAD_IPV4_HEADER` | 104 |
| `BAD_LENGTH_OR_TRUNCATED` | 578 |
| `DST_PORT_MISMATCH` | 179 |
| `FRAGMENTED` | 109 |
| `FRAME_TOO_LONG` | 88 |
| `MSG_TYPE_MISMATCH` | 142 |
| `NON_IPV4` | 104 |
| `NON_UDP` | 89 |

Run with `python scripts/run_hardware_test.py` (needs Vivado, the board, and `pip install -r requirements-hw.txt`). The harness is described in [docs/hardware-test.md](../docs/hardware-test.md).
