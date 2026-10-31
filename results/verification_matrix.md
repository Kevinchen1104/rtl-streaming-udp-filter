# Verification matrix

Generated from the cocotb JUnit report (`results/raw/cocotb_junit.xml`). Each row is a separate cocotb test with its own result.

| # | Test | Scenario | Result |
|---:|---|---|---|
| 1 | `directed_frame` | minimal zero | pass |
| 2 | `directed_frame` | one byte | pass |
| 3 | `directed_frame` | multi byte | pass |
| 4 | `directed_frame` | msg one | pass |
| 5 | `directed_frame` | msg multi | pass |
| 6 | `directed_frame` | padding | pass |
| 7 | `directed_frame` | df0 | pass |
| 8 | `directed_frame` | df1 | pass |
| 9 | `directed_frame` | non ipv4 | pass |
| 10 | `directed_frame` | bad version | pass |
| 11 | `directed_frame` | ihl4 | pass |
| 12 | `directed_frame` | ihl6 | pass |
| 13 | `directed_frame` | tcp | pass |
| 14 | `directed_frame` | icmp | pass |
| 15 | `directed_frame` | mf | pass |
| 16 | `directed_frame` | fragment offset | pass |
| 17 | `directed_frame` | port mismatch | pass |
| 18 | `directed_frame` | port mismatch closes at udp header | pass |
| 19 | `directed_frame` | port mismatch then late truncation | pass |
| 20 | `directed_frame` | port mismatch with padding | pass |
| 21 | `directed_frame` | message mismatch | pass |
| 22 | `directed_frame` | message mismatch closes on first byte | pass |
| 23 | `directed_frame` | message mismatch then late truncation | pass |
| 24 | `directed_frame` | message empty | pass |
| 25 | `directed_frame` | ip short | pass |
| 26 | `directed_frame` | udp short | pass |
| 27 | `directed_frame` | udp long relation | pass |
| 28 | `directed_frame` | udp short relation | pass |
| 29 | `directed_frame` | too long | pass |
| 30 | `directed_frame` | late first | pass |
| 31 | `directed_frame` | late middle | pass |
| 32 | `directed_frame` | late before final | pass |
| 33 | `directed_frame` | long padding | pass |
| 34 | `directed_frame` | maximum logical | pass |
| 35 | `header_truncation_sweep` | - | pass |
| 36 | `configuration_latched_per_frame` | - | pass |
| 37 | `sequence_wraps_at_32_bits` | - | pass |
| 38 | `flow_control` | 0 | pass |
| 39 | `flow_control` | 1 | pass |
| 40 | `flow_control` | 2 | pass |
| 41 | `flow_control` | 3 | pass |
| 42 | `flow_control` | 4 | pass |
| 43 | `flow_control` | 5 | pass |
| 44 | `reject_ignores_output_ready` | port mismatch | pass |
| 45 | `reject_ignores_output_ready` | message mismatch | pass |
| 46 | `input_ready_is_registered` | - | pass |
| 47 | `back_to_back_frames` | - | pass |
| 48 | `waveform_example` | accepted with output stall | pass |
| 49 | `waveform_example` | late truncation | pass |
| 50 | `reset_mid_frame` | idle | pass |
| 51 | `reset_mid_frame` | ethernet header | pass |
| 52 | `reset_mid_frame` | ipv4 header | pass |
| 53 | `reset_mid_frame` | udp header | pass |
| 54 | `reset_mid_frame` | payload with output stalled | pass |
| 55 | `reset_while_descriptor_stalled` | - | pass |
| 56 | `randomized_regression` | 1 | pass |
| 57 | `randomized_regression` | 7 | pass |
| 58 | `randomized_regression` | 42 | pass |
| 59 | `randomized_regression` | 2027 | pass |
