# Regression summary

- Reference-model tests (pytest): 84, all passed
- RTL tests (cocotb on Icarus Verilog): 59, all passed
- Randomized frames: 800 (seeds 1, 7, 42, 2027)
- Functional coverage: all 39 bins reached their goal (at least 5 hits each)

| cocotb test | Scenarios |
|---|---:|
| `directed_frame` | 34 |
| `header_truncation_sweep` | 1 |
| `configuration_latched_per_frame` | 1 |
| `sequence_wraps_at_32_bits` | 1 |
| `flow_control` | 6 |
| `reject_ignores_output_ready` | 2 |
| `input_ready_is_registered` | 1 |
| `back_to_back_frames` | 1 |
| `waveform_example` | 2 |
| `reset_mid_frame` | 5 |
| `reset_while_descriptor_stalled` | 1 |
| `randomized_regression` | 4 |

Per-scenario results: [verification matrix](verification_matrix.md).
