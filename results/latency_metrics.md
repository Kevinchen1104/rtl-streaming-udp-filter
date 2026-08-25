# Measured simulation latency

cycle 0 is the first monitored rising-edge transfer opportunity for each frame; all listed handshakes use pre-edge ready/valid values

- First payload output-valid latency: `1` cycle(s) after its input handshake.
- No-stall sustained payload throughput: one byte every `1` cycle(s).
- Fixed periodic output backpressure added `31` cycles through result handshake versus the same no-stall frame.

## Scenario event cycles

### Port Only Accepted

- `first_input_handshake_cycle`: `0`
- `udp_header_final_handshake_cycle`: `41`
- `first_payload_input_handshake_cycle`: `42`
- `first_payload_output_valid_cycle`: `43`
- `first_payload_output_handshake_cycle`: `43`
- `final_payload_output_handshake_cycle`: `48`
- `input_frame_closing_handshake_cycle`: `47`
- `result_valid_cycle`: `49`
- `result_handshake_cycle`: `49`

### Message Filter Accepted

- `first_input_handshake_cycle`: `0`
- `udp_header_final_handshake_cycle`: `41`
- `first_payload_input_handshake_cycle`: `42`
- `first_payload_output_valid_cycle`: `43`
- `first_payload_output_handshake_cycle`: `43`
- `final_payload_output_handshake_cycle`: `48`
- `input_frame_closing_handshake_cycle`: `47`
- `result_valid_cycle`: `49`
- `result_handshake_cycle`: `49`

### Port Mismatch

- `first_input_handshake_cycle`: `0`
- `udp_header_final_handshake_cycle`: `41`
- `first_payload_input_handshake_cycle`: `42`
- `first_payload_output_valid_cycle`: `None`
- `first_payload_output_handshake_cycle`: `None`
- `final_payload_output_handshake_cycle`: `None`
- `input_frame_closing_handshake_cycle`: `44`
- `result_valid_cycle`: `45`
- `result_handshake_cycle`: `45`

### Message Mismatch

- `first_input_handshake_cycle`: `0`
- `udp_header_final_handshake_cycle`: `41`
- `first_payload_input_handshake_cycle`: `42`
- `first_payload_output_valid_cycle`: `None`
- `first_payload_output_handshake_cycle`: `None`
- `final_payload_output_handshake_cycle`: `None`
- `input_frame_closing_handshake_cycle`: `45`
- `result_valid_cycle`: `46`
- `result_handshake_cycle`: `46`

### Late Truncation

- `first_input_handshake_cycle`: `0`
- `udp_header_final_handshake_cycle`: `41`
- `first_payload_input_handshake_cycle`: `42`
- `first_payload_output_valid_cycle`: `43`
- `first_payload_output_handshake_cycle`: `43`
- `final_payload_output_handshake_cycle`: `44`
- `input_frame_closing_handshake_cycle`: `43`
- `result_valid_cycle`: `45`
- `result_handshake_cycle`: `45`
