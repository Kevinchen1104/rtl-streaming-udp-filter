# Streaming UDP Packet Filter v1 Specification

- **Version:** 1.0
- **Implementation:** synthesizable SystemVerilog
- **Verification:** Python, cocotb, pytest
- **Synthesis target:** generic Yosys netlist

This document defines the supported protocol subset, external interface,
observable behavior, verification requirements, and scope boundaries for v1.

## 1. Purpose and scope

The block receives one raw Ethernet II frame at a time over an 8-bit
ready/valid interface. It parses a constrained IPv4/UDP subset, rejects
unsupported or malformed frames, filters supported datagrams, forwards
candidate UDP payload bytes, and emits one authoritative result descriptor per
completed input frame.

### Supported subset

- Input begins at Ethernet destination-MAC byte 0.
- Preamble, SFD, and FCS are not present.
- Ethernet II EtherType must be `16'h0800`.
- IPv4 version must be 4 and IHL must be 5.
- IPv4 protocol must be 17 for UDP.
- `MF` and fragment offset must both be zero; `DF` is ignored.
- IPv4 and UDP checksum fields are not verified.
- IPv4 total length must be at least 28.
- UDP length must be at least 8.
- UDP length must equal `ip_total_length - 20`.
- Ethernet padding may follow the logical IPv4 datagram and is drained.
- Destination-port filtering is always enabled.
- First-payload-byte filtering is optional.

### Excluded features

VLAN, IPv6, IP options, fragment reassembly, checksum validation, Ethernet
PHY/MAC signaling, multiple outstanding descriptors, timeout-based recovery,
and physical timing closure are outside v1.

## 2. Byte layout and endianness

All multibyte fields use network byte order (big-endian). Offsets are measured
from Ethernet destination-MAC byte 0.

| Offset | Bytes | Field |
|---:|---:|---|
| 0-5 | 6 | Destination MAC, ignored |
| 6-11 | 6 | Source MAC, ignored |
| 12-13 | 2 | EtherType |
| 14 | 1 | IPv4 version/IHL |
| 15 | 1 | DSCP/ECN, ignored |
| 16-17 | 2 | IPv4 total length |
| 18-19 | 2 | Identification, ignored |
| 20-21 | 2 | Flags and fragment offset |
| 22 | 1 | TTL, ignored |
| 23 | 1 | IPv4 protocol |
| 24-25 | 2 | IPv4 checksum, ignored |
| 26-29 | 4 | Source IPv4 address |
| 30-33 | 4 | Destination IPv4 address |
| 34-35 | 2 | UDP source port |
| 36-37 | 2 | UDP destination port |
| 38-39 | 2 | UDP length |
| 40-41 | 2 | UDP checksum, ignored |
| 42 onward | variable | UDP payload |

Multibyte metadata is committed only after every byte of the field transfers.
A field truncated before its final byte remains zero in the descriptor.

## 3. Top-level interface

```systemverilog
module udp_packet_filter #(
    parameter int unsigned MAX_LOGICAL_FRAME_BYTES = 2048
) (
    input  logic        clk,
    input  logic        rst_n,

    input  logic [7:0]  s_axis_tdata,
    input  logic        s_axis_tvalid,
    output logic        s_axis_tready,
    input  logic        s_axis_tlast,

    input  logic [15:0] cfg_dst_port,
    input  logic        cfg_msg_type_enable,
    input  logic [7:0]  cfg_msg_type,

    output logic [7:0]  m_axis_tdata,
    output logic        m_axis_tvalid,
    input  logic        m_axis_tready,
    output logic        m_axis_tlast,
    output logic        m_axis_tuser_error,

    output logic        result_valid,
    input  logic        result_ready,
    output logic        result_accept,
    output logic [3:0]  result_reason,
    output logic [31:0] result_src_ip,
    output logic [31:0] result_dst_ip,
    output logic [15:0] result_src_port,
    output logic [15:0] result_dst_port,
    output logic [15:0] result_payload_len,
    output logic [31:0] result_sequence
);
```

### Reset

- `rst_n` is active-low and synchronous to `clk`.
- While reset is asserted, input ready, output valid, and result valid are zero.
- Reset clears parser state, buffer state, metadata, descriptor state, and the
  sequence counter.
- Reset during a frame aborts that frame without a descriptor.
- The next completed frame after reset has sequence zero.

### Input transfer

An input byte transfers only when `s_axis_tvalid && s_axis_tready`. The first
transferred byte in idle is offset 0. The transferred byte with
`s_axis_tlast=1` closes the frame. Data, last, and valid must remain stable while
valid is asserted and ready is deasserted.

### Configuration sampling

All configuration inputs are sampled on the first input handshake and remain
internally fixed for that frame.

### Payload output

A payload byte transfers only when `m_axis_tvalid && m_axis_tready`. Data, last,
and error remain stable during a stall. Zero-length payloads produce no output
beat.

The final good payload beat carries `m_axis_tlast=1` and
`m_axis_tuser_error=0`. If a frame closes early on a forwarded payload byte,
that final partial beat carries both last and error.

### Result descriptor

Exactly one descriptor is produced for every frame closed by an input
handshake, except a reset-aborted frame. All fields remain stable until
`result_valid && result_ready`.

No descriptor may handshake before every payload beat from the same frame has
handshaken. A pending descriptor backpressures the next input frame. Sequence
increments once per created descriptor and wraps modulo 2^32.

## 4. Speculative cut-through semantics

Payload is speculative until the result descriptor is accepted. A cut-through
design cannot recall bytes transferred before a late error is discovered.

- Early rejects produce no payload.
- Late payload truncation may produce a partial payload stream.
- A partial stream terminates with output last and error asserted.
- The result descriptor is authoritative for committing or discarding data.
- A commit-only downstream system requires external transaction buffering.

## 5. Result reasons

| Value | Symbol | Meaning |
|---:|---|---|
| 0 | `REASON_ACCEPT` | Supported, structurally valid, all filters match |
| 1 | `REASON_NON_IPV4` | EtherType is not IPv4 |
| 2 | `REASON_BAD_IPV4_HEADER` | Version is not 4 or IHL is not 5 |
| 3 | `REASON_NON_UDP` | IPv4 protocol is not UDP |
| 4 | `REASON_FRAGMENTED` | MF is set or fragment offset is nonzero |
| 5 | `REASON_BAD_LENGTH_OR_TRUNCATED` | Invalid length relationship or premature close |
| 6 | `REASON_DST_PORT_MISMATCH` | Structurally valid datagram, destination port differs |
| 7 | `REASON_MSG_TYPE_MISMATCH` | Port matches, message filter fails or payload is empty |
| 8 | `REASON_FRAME_TOO_LONG` | Logical Ethernet+IPv4 length exceeds the parameter |

`result_accept` is one exactly when the result reason is `REASON_ACCEPT`.

### Priority

1. A premature close reports truncation unless an earlier complete field has
   already caused a decisive drain state.
2. A complete non-IPv4 EtherType is decisive.
3. Bad version/IHL precedes later IPv4 eligibility checks.
4. Logical maximum is checked when total length completes.
5. At protocol byte 23, non-UDP precedes fragmented.
6. Structural length checks precede destination and message filters.
7. Destination-port mismatch precedes message mismatch.
8. Early close on the first message byte precedes a same-byte message mismatch
   when additional payload was declared.
9. If a message mismatch is observed before a later premature close, the
   mismatch remains decisive because the parser has already entered drain.

### Metadata

Source/destination IP addresses and ports contain only fully observed fields.
Declared payload length is nonzero only after all structural length checks pass.
It remains available for filter rejects and late truncation.

## 6. Parser behavior

The implementation uses the following states:

- `ST_IDLE`
- `ST_ETH_HEADER`
- `ST_IPV4_HEADER`
- `ST_UDP_HEADER`
- `ST_FIRST_PAYLOAD`
- `ST_PASS_PAYLOAD`
- `ST_DRAIN`
- `ST_WAIT_OUTPUT`
- `ST_RESULT_HOLD`

Every byte index and payload counter advances only on an input handshake.

### Ethernet and IPv4

MAC addresses are counted and ignored. EtherType is committed at byte 13.
Version/IHL is checked at byte 14, total length at bytes 16-17, fragmentation at
bytes 20-21, and protocol at byte 23. IP addresses are shifted and committed at
bytes 29 and 33.

Fragment information is held until protocol byte 23 so `NON_UDP` has priority
over `FRAGMENTED`.

### UDP and filtering

Ports and UDP length are committed by byte 39. At byte 41 the design verifies:

- `ip_total_length >= 28`;
- `udp_length >= 8`;
- `udp_length == ip_total_length - 20`.

Only after these checks does destination-port filtering apply. A zero-byte
payload is accepted only when message filtering is disabled.

When message filtering is enabled, the first payload byte is compared before
being exposed. A mismatch is discarded and the remaining frame is drained.

### Payload completion and padding

The final declared payload byte is emitted with last asserted. Additional bytes
before input `tlast` are Ethernet padding and are not forwarded. If the frame
closes while a terminal output beat remains buffered, `ST_WAIT_OUTPUT` holds
input not-ready until that beat handshakes, then creates the descriptor.

### Unterminated frames

No timeout exists. A frame that never transfers `tlast` leaves the parser in its
current transaction.

## 7. Elastic output buffer

The one-entry registered buffer uses:

```text
out_can_take = !m_axis_tvalid || m_axis_tready
```

Payload input ready follows this capacity. A simultaneous output handshake and
new input handshake replaces the transferred byte without inserting a bubble.
A stalled valid entry is never overwritten.

Header and drain paths do not depend on output ready when no payload entry is
pending.

## 8. Performance contract

- Header and drain states accept up to one byte per cycle.
- Accepted payload sustains one byte per cycle without downstream stalls.
- The registered buffer makes first output valid one cycle after the first
  payload input handshake.
- A pending descriptor creates an intentional inter-frame stall.

Measured cycle events and the fixed backpressure comparison are saved in
`results/latency_metrics.json` and `results/latency_metrics.md`.

## 9. Independent reference model

`sim/reference_model.py` parses a complete byte array declaratively. It does not
mirror RTL states or counters. Packet construction is isolated in
`sim/packet_builder.py`, and hand-written raw vectors independently check byte
order and classification semantics.

The scoreboard compares exact payload events, descriptor fields, sequence, and
late-truncation terminal behavior.

## 10. Verification requirements

The directed matrix covers:

- zero-, one-, multi-byte, message-filtered, padded, DF, endian, and maximum
  accepted frames;
- all eligibility and filter reasons;
- invalid IP/UDP lengths and logical maximum;
- truncation at every header byte and multiple payload positions;
- input gaps, payload stalls, result stalls, immediate next-frame pressure,
  and long accepted payloads;
- reset in idle, each header region, stalled payload, and stalled descriptor;
- mixed classification sequencing and modulo sequence wrap.

Random regression uses seeds `1`, `7`, `42`, and `2027`, with 200 frames per
seed. It mixes field mutations, padding, filter modes, truncation regions, and
all three backpressure dimensions.

The generated named-scenario mapping is stored in
`results/verification_matrix.md`; its row count comes from the executed
regression artifacts.

## 11. Assertions and coverage

Executed RTL assertions and cocotb monitors verify:

1. output stability while stalled;
2. byte-index changes only after input handshake;
3. descriptor stability while stalled;
4. accept/reason equivalence;
5. no output for early rejects;
6. exact good payload length and order;
7. error termination of partial output;
8. good final-beat last/error semantics;
9. no stalled-buffer overwrite;
10. one descriptor per closed frame;
11. no descriptor for reset-aborted frames;
12. per-frame configuration stability;
13. payload completion before descriptor validity.

Functional coverage reports raw hit counts for every reason, payload-size bin,
filter mode, port relation, padding, DF, backpressure dimension, truncation
region, and output semantic. Percentage coverage is not reported.

## 12. Reproducibility, lint, synthesis, and CI

The canonical command is:

```text
python scripts/run_all.py
```

It runs reference-model tests, RTL simulation, Verilator lint, generic Yosys
synthesis, and evidence generation, returning nonzero on failure.

Saved evidence includes exact tool versions, commands, exit status, warning
counts, regression counts, coverage hits, latency events, Yosys check results,
and generic cell statistics.

The GitHub Actions workflow runs the same command on pushes and pull requests.

## 13. Scope boundaries

Successful generic Yosys synthesis demonstrates that the design can be lowered
to a generic netlist. It does not establish FPGA LUT count, WNS, Fmax, board
operation, Ethernet line rate, ASIC timing, power, or physical implementation
quality.

FPGA wrappers and hardware validation are outside this specification.
