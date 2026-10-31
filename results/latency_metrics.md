# Latency and throughput (simulation)

Cycle 0 is the first rising edge at which the frame's first byte can transfer. Handshakes are counted at the rising edge where valid and ready are both high.

| Measurement | Cycles |
|---|---:|
| First payload byte: input handshake to output valid | 1 |
| Payload throughput with no stalls | 1 per byte |
| Last input byte to descriptor valid (6-byte payload) | 2 |

## Gap between back-to-back frames

8 frames (645 bytes) sent with `s_axis_tvalid` held high and both sinks always ready took 655 cycles. Input stall cycles after each kind of frame:

| Frame | Stall cycles before the next frame |
|---|---:|
| accepted payload | 2 |
| accepted zero payload | 1 |
| accepted with padding | 1 |
| port mismatch | 1 |
| non ipv4 | 1 |
| late truncation | 2 |

## Event cycles per scenario

### multi byte

- `first_input_handshake_cycle`: 0
- `udp_header_final_handshake_cycle`: 41
- `first_payload_input_handshake_cycle`: 42
- `first_payload_output_valid_cycle`: 43
- `first_payload_output_handshake_cycle`: 43
- `final_payload_output_handshake_cycle`: 48
- `input_frame_closing_handshake_cycle`: 47
- `result_valid_cycle`: 49
- `result_handshake_cycle`: 49

### msg multi

- `first_input_handshake_cycle`: 0
- `udp_header_final_handshake_cycle`: 41
- `first_payload_input_handshake_cycle`: 42
- `first_payload_output_valid_cycle`: 43
- `first_payload_output_handshake_cycle`: 43
- `final_payload_output_handshake_cycle`: 48
- `input_frame_closing_handshake_cycle`: 47
- `result_valid_cycle`: 49
- `result_handshake_cycle`: 49

### port mismatch

- `first_input_handshake_cycle`: 0
- `udp_header_final_handshake_cycle`: 41
- `first_payload_input_handshake_cycle`: 42
- `first_payload_output_valid_cycle`: None
- `first_payload_output_handshake_cycle`: None
- `final_payload_output_handshake_cycle`: None
- `input_frame_closing_handshake_cycle`: 44
- `result_valid_cycle`: 45
- `result_handshake_cycle`: 45

### message mismatch

- `first_input_handshake_cycle`: 0
- `udp_header_final_handshake_cycle`: 41
- `first_payload_input_handshake_cycle`: 42
- `first_payload_output_valid_cycle`: None
- `first_payload_output_handshake_cycle`: None
- `final_payload_output_handshake_cycle`: None
- `input_frame_closing_handshake_cycle`: 45
- `result_valid_cycle`: 46
- `result_handshake_cycle`: 46

### late middle

- `first_input_handshake_cycle`: 0
- `udp_header_final_handshake_cycle`: 41
- `first_payload_input_handshake_cycle`: 42
- `first_payload_output_valid_cycle`: 43
- `first_payload_output_handshake_cycle`: 43
- `final_payload_output_handshake_cycle`: 44
- `input_frame_closing_handshake_cycle`: 43
- `result_valid_cycle`: 45
- `result_handshake_cycle`: 45
