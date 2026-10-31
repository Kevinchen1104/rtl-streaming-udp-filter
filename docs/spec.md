# Streaming UDP Packet Filter: Specification

Version 1.1. This document defines what the block does at its ports. How it
is built is in [architecture.md](architecture.md); how it is verified is in
[verification-plan.md](verification-plan.md).

## 1. What the block does

The block takes one raw Ethernet II frame at a time, one byte per cycle,
over a ready/valid interface. It keeps IPv4/UDP datagrams addressed to a
configured destination port and, optionally, whose first payload byte matches
a configured message type. It forwards the UDP payload of those datagrams and,
for every frame, produces one result record that says whether the frame was
accepted and why not if it was rejected.

### Supported frames

- Input starts at the first byte of the destination MAC. There is no preamble,
  SFD, or FCS; the MAC in front of this block handles those.
- EtherType `0x0800` (IPv4), IPv4 version 4 with IHL 5 (no options),
  protocol 17 (UDP).
- Not fragmented: MF is 0 and the fragment offset is 0. DF is ignored.
- `ip_total_length >= 28`, `udp_length >= 8`, and
  `udp_length == ip_total_length - 20`.
- IPv4 and UDP checksums are not checked.
- Bytes after the end of the IPv4 datagram are Ethernet padding. They are
  read and dropped.

Not supported: VLAN tags, IPv6, IP options, fragment reassembly, checksum
checks, more than one result record in flight, and timeouts.

## 2. Byte layout

All multibyte fields are big-endian. Offsets count from the first byte of the
destination MAC.

| Offset | Bytes | Field |
|---:|---:|---|
| 0-5 | 6 | Destination MAC (ignored) |
| 6-11 | 6 | Source MAC (ignored) |
| 12-13 | 2 | EtherType |
| 14 | 1 | IPv4 version and IHL |
| 15 | 1 | DSCP/ECN (ignored) |
| 16-17 | 2 | IPv4 total length |
| 18-19 | 2 | Identification (ignored) |
| 20-21 | 2 | Flags and fragment offset |
| 22 | 1 | TTL (ignored) |
| 23 | 1 | Protocol |
| 24-25 | 2 | IPv4 header checksum (ignored) |
| 26-29 | 4 | Source IPv4 address |
| 30-33 | 4 | Destination IPv4 address |
| 34-35 | 2 | UDP source port |
| 36-37 | 2 | UDP destination port |
| 38-39 | 2 | UDP length |
| 40-41 | 2 | UDP checksum (ignored) |
| 42 onward | variable | UDP payload |

## 3. Ports

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

The streams use AXI4-Stream signal names and handshake rules: a byte moves
on a rising edge where valid and ready are both high, and a source holds its
valid, data, and last until that happens. Only TDATA, TVALID, TREADY, TLAST,
and one TUSER bit exist; there is no TKEEP, TSTRB, TID, or TDEST.

`MAX_LOGICAL_FRAME_BYTES` is a policy limit on `14 + ip_total_length`, not a
buffer size. It must be at least 42.

## 4. Reset

- `rst_n` is active low and sampled on the rising edge of `clk`.
- While `rst_n` is low, `s_axis_tready`, `m_axis_tvalid`, and `result_valid`
  are low, including before the first clock edge of the reset.
- Reset clears all state. A frame in progress is dropped without a result
  record, and the next result record has sequence 0.

## 5. Input

The first byte accepted while the block is idle is offset 0 of a new frame.
The byte accepted with `s_axis_tlast` high is the last byte of the frame.
`cfg_dst_port`, `cfg_msg_type_enable`, and `cfg_msg_type` are sampled with the
first byte and used for the whole frame.

While a result record is waiting for `result_ready`, the block does not
accept the next frame.

## 6. Payload output

Payload is forwarded while the frame still passes every check that has been
decided, before the frame has ended (cut-through). So:

- A frame rejected before its payload starts produces no output.
- With message filtering on, the first payload byte is compared before it is
  forwarded; a mismatch produces no output.
- A frame that passes every check produces its payload, and the last payload
  byte has `m_axis_tlast = 1` and `m_axis_tuser_error = 0`. Zero-length
  payloads produce no output.
- A frame that ends before its declared payload is complete, after some of
  its payload was forwarded, ends the output with `m_axis_tlast = 1` and
  `m_axis_tuser_error = 1`.

Bytes already forwarded cannot be taken back. The result record decides
whether a frame's payload is good. A consumer that must only see complete,
accepted payloads buffers each frame's payload until its result record says
accept.

`m_axis_tdata`, `m_axis_tlast`, and `m_axis_tuser_error` hold while
`m_axis_tvalid` is high and `m_axis_tready` is low.

## 7. Result record

Exactly one result record is produced for each frame that ends with an
accepted `s_axis_tlast` byte. A frame ended by reset produces none.

- `result_valid` rises only after every payload byte of the frame has been
  transferred.
- All `result_*` fields hold until `result_valid` and `result_ready` are both
  high.
- `result_sequence` counts result records, starting at 0 after reset and
  wrapping at 2^32.
- `result_accept` is 1 exactly when `result_reason` is `ACCEPT`.

### Reasons

| Value | Name | Meaning |
|---:|---|---|
| 0 | `ACCEPT` | Supported, well formed, and passes both filters |
| 1 | `NON_IPV4` | EtherType is not `0x0800` |
| 2 | `BAD_IPV4_HEADER` | Version is not 4, or IHL is not 5 |
| 3 | `NON_UDP` | Protocol is not 17 |
| 4 | `FRAGMENTED` | MF is set or the fragment offset is not zero |
| 5 | `BAD_LENGTH_OR_TRUNCATED` | Lengths are inconsistent, or the frame ends before the datagram does |
| 6 | `DST_PORT_MISMATCH` | Complete datagram, destination port differs |
| 7 | `MSG_TYPE_MISMATCH` | Port matches; message filtering is on and the payload is empty or its first byte differs |
| 8 | `FRAME_TOO_LONG` | `14 + ip_total_length` exceeds `MAX_LOGICAL_FRAME_BYTES` |

### Which reason applies

The reason depends only on the bytes of the frame. Checks run in this order,
and the first one that fails sets the reason:

1. EtherType (bytes 12-13) is `0x0800`, else `NON_IPV4`.
2. Version is 4 and IHL is 5 (byte 14), else `BAD_IPV4_HEADER`.
3. `14 + ip_total_length` (bytes 16-17) is within the limit, else
   `FRAME_TOO_LONG`.
4. Protocol (byte 23) is 17, else `NON_UDP`.
5. MF and fragment offset (bytes 20-21) are zero, else `FRAGMENTED`.
6. The UDP header is complete, the length rules in section 1 hold, and the
   frame reaches the end of the declared datagram, else
   `BAD_LENGTH_OR_TRUNCATED`.
7. The destination port matches, else `DST_PORT_MISMATCH`.
8. With message filtering on, the payload is not empty and its first byte
   matches, else `MSG_TYPE_MISMATCH`.

If the frame ends before the bytes a check needs, that check reports
`BAD_LENGTH_OR_TRUNCATED`. A frame that fails checks 1-5 keeps that reason
even if it is also short. A frame that fails the port or message filter is
still reported as truncated if it ends before its declared datagram end.

### Metadata

`result_src_ip`, `result_dst_ip`, `result_src_port`, and `result_dst_port`
hold a field only if all of its bytes arrived; otherwise they are 0.
`result_payload_len` is `udp_length - 8` once the UDP header is complete and
the length rules hold, including for filter rejects and truncated frames, and
0 otherwise.

## 8. Timing

- Header and drained bytes are accepted every cycle.
- Payload moves at one byte per cycle when the output is ready.
- The first payload byte appears on the output one cycle after it is accepted.
- `s_axis_tready` does not depend combinationally on `m_axis_tready`.
- Between frames, input is not ready for one cycle (two if the frame's last
  byte was a forwarded payload byte) while the result record is handed off,
  when `m_axis_tready` and `result_ready` are both high.

Measured values are in [results/latency_metrics.md](../results/latency_metrics.md).

## 9. Frames that never end

There is no timeout. If the source never sends `s_axis_tlast`, the block
stays in that frame until reset.

## Changes from version 1.0

- A frame rejected by the port or message filter that ends before its
  declared datagram end now reports `BAD_LENGTH_OR_TRUNCATED`. In 1.0 this
  depended on which byte the frame ended on.
- `s_axis_tready` no longer depends combinationally on `m_axis_tready`.
