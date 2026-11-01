# Verification plan

## Approach

- **Reference model.** `sim/reference_model.py` classifies a complete frame by
  walking the ordered checks from the specification. It has no notion of
  cycles or parser states. `sim/test_reference_model.py` tests it with pytest,
  including three hand-written hex vectors in `sim/raw_vectors/` that pin down
  byte order independently of the packet builder.
- **RTL tests.** `sim/rtl_testbench.py` runs cocotb on Icarus Verilog. Each
  scenario is its own cocotb test, so the JUnit report has one result per
  scenario. `run_frame` drives one frame, monitors every cycle, and compares
  each payload beat and the descriptor against the model.
- **In-RTL checks.** `rtl/udp_packet_filter_checks.sv` holds immediate
  assertions that run in every simulation. Synthesis and lint define
  `SYNTHESIS` and skip it; that is why Icarus warns that `$error` cannot be
  synthesized.
- **Formal.** `formal/udp_packet_filter_formal.sv` restates the handshake and
  frame-accounting properties for SymbiYosys. The only constraints on the
  free inputs are: start in reset, and hold valid, data, and last while
  stalled. `abc pdr` proves every assertion for all reachable states (not just
  to a fixed depth), and a cover task shows each situation is reachable, so
  the proof is not vacuous.
- **Hardware.** The filter runs on a Basys 3 at 125 MHz. A PC sends the
  simulation's directed, truncation-sweep, and random frames over USB-UART and
  checks every payload byte and result record against the same model. The
  harness itself has a cocotb test (`sim/hw_wrapper_testbench.py`, three tests)
  in the regular regression. See [hardware-test.md](hardware-test.md).

## What is checked where

| Property | Checked by |
|---|---|
| Payload data, last, and error hold while the output is stalled | Formal proof; RTL checks; `run_frame` monitor |
| A stalled payload beat is never dropped or overwritten | Same stability check plus the payload scoreboard |
| Descriptor fields hold while the descriptor is stalled | Formal proof; RTL checks; `run_frame` monitor |
| `result_accept` equals `result_reason == ACCEPT` | Formal proof; RTL checks; `run_frame` monitor |
| No descriptor while payload from the frame is still pending | Formal proof; RTL checks; `run_frame` monitor |
| At most one descriptor per closed frame; none without a closed frame | Formal proof |
| No payload beat after a frame's last beat until its descriptor is taken | Formal proof |
| `tuser_error` only on a last beat | Formal proof |
| Handshake outputs low during reset | Formal proof; `reset_dut` |
| Parser counters change only after an input handshake | `run_frame` monitor |
| Exact payload bytes, order, and length; nothing for rejects | Scoreboard against the model |
| Good payload ends with `last=1, error=0`; partial with `last=1, error=1` | Scoreboard |
| Exactly one descriptor per closed frame, with the right sequence | Scoreboard; `back_to_back_frames` |
| A reset-aborted frame leaves no descriptor and sequence restarts at 0 | `reset_mid_frame`, `reset_while_descriptor_stalled` |
| Configuration is sampled once per frame | `configuration_latched_per_frame` |
| A pending descriptor blocks the next frame | Formal proof; `flow_control` (`result_stall_blocks_next_frame`) |
| Rejected frames drain even if the payload output is never ready | `reject_ignores_output_ready` |
| `m_axis_tready` has no combinational path to `s_axis_tready` | `input_ready_is_registered` flips output ready mid-cycle |

## RTL tests

| Test | Scenarios |
|---|---|
| `directed_frame` | 34 hand-picked frames: payload sizes, filters, padding, every reason, length errors, truncation, filter rejects followed by truncation, the 2048-byte maximum |
| `header_truncation_sweep` | The frame closed after each of the 42 header bytes, back to back |
| `configuration_latched_per_frame` | Config inputs inverted mid-frame |
| `sequence_wraps_at_32_bits` | Sequence counter forced to `0xFFFFFFFF` |
| `flow_control` | A 96-byte payload under six input-gap, output-stall, and result-stall patterns |
| `reject_ignores_output_ready` | Port and message rejects with the output never ready |
| `input_ready_is_registered` | Output ready toggled inside each cycle while payload flows |
| `back_to_back_frames` | Eight frames with `tvalid` held high; measures the gap between frames |
| `reset_mid_frame` | Reset in idle, in each header, and with two payload beats buffered |
| `reset_while_descriptor_stalled` | Reset while the descriptor waits for `result_ready` |
| `randomized_regression` | 200 random frames for each of seeds 1, 7, 42, 2027 |
| `waveform_example` | Records two short traces for the waveform figures in `results/waveforms/` |

## Randomized regression and coverage

Each seed first generates one frame from every category, then picks categories
by weight. Accepted frames are about a third of the traffic so the payload path
and output backpressure get exercised. Truncation, filter rejects, filter
rejects followed by truncation, and each eligibility reject make up the rest.
Input gaps, output stalls, and result stalls are each turned on at random per
frame.

Coverage bins and their goals are declared up front in `sim/coverage.py`, and
every bin needs at least five hits. Bins include every reason, accepted payload
size ranges, each truncation region, output kind (full, partial with error,
none), and two crosses: payload frames with and without an output stall, and
partial-output frames with and without an output stall. A missed goal fails
the run, so an unreached bin cannot quietly drop out of the report.

## Reports

`python scripts/run_all.py` runs the model tests, the RTL tests, lint,
generic synthesis, FPGA place and route, the formal tasks, and report
generation, and stops at the first failure.
`scripts/generate_results.py` builds `results/` from the JUnit reports and the
JSON that tests write to `results/raw/` (not committed). The
[verification matrix](../results/verification_matrix.md) lists every cocotb
test from the JUnit report.
