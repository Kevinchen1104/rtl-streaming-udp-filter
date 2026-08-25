# Architecture

## Design boundary

The top module and all externally visible behavior are defined in `spec.md`.
Input begins at Ethernet destination-MAC byte 0 and excludes
preamble, SFD, and FCS. Only Ethernet II / IPv4 version 4 with IHL 5 /
unfragmented UDP is eligible. IPv4 and UDP checksums are ignored, not verified.
`udp_length` must equal `ip_total_length - 20`.

Configuration is sampled on the first input handshake and held until the
descriptor handshakes or reset aborts the frame.

## Data and transaction flow

```text
input ready/valid bytes
          |
          v
 Ethernet -> IPv4 -> UDP/length -> port -> optional message byte
                                                |
                      +-------------------------+------------------+
                      |                                            |
                 elastic byte buffer                         reject/drain
                      |                                            |
               speculative payload                          no early output
                      +------------------+-------------------------+
                                         v
                             authoritative descriptor
```

The descriptor is not made valid until the frame has closed and every payload
beat for that frame has handshaken. A consumer needing commit-only data must
buffer speculative bytes and commit them only after an accepted descriptor.

## State model

```text
IDLE -> ETH -> IPV4 -> UDP -> FIRST_PAYLOAD/PASS_PAYLOAD -> DRAIN
  ^                                                        |       |
  |                                                        v       v
  +---------------- RESULT_HOLD <- WAIT_OUTPUT <------------+-------+
```

`DRAIN` is also entered by every early eligibility/filter reject and after the
declared payload has completed when Ethernet padding remains. All counters and
parse transitions advance only on an input handshake. `WAIT_OUTPUT` is used
when the input frame has closed but the terminal buffered payload beat has not
handshaken.

## Byte order

All network fields are big-endian. The parser retains the high byte of each
16-bit field and commits the field when its low byte handshakes. Four-byte IP
addresses are shifted in and committed only on their fourth byte. UDP payload
byte 0 is Ethernet offset 42: 14 Ethernet + 20 IPv4 + 8 UDP bytes.

## Length and reason ordering

The implemented resolution of the specification is:

1. a complete non-IPv4 EtherType is decisive;
2. a complete bad version/IHL is decisive;
3. the logical maximum is decisive as soon as `ip_total_length` completes at
   byte 17;
4. fragmentation is latched at byte 21 and evaluated at protocol byte 23, so
   `NON_UDP` takes priority over `FRAGMENTED`;
5. a supported candidate must reach the complete UDP header before IP/UDP
   length checks, port filtering, and message filtering;
6. a premature frame close is truncation unless an earlier complete field has
   already put the parser in drain.

A fragmented frame that closes before protocol byte 23 is truncated because
the required IPv4 header did not complete and the parser had not yet applied
the latched fragmentation reject.

## Payload and backpressure

The registered one-entry buffer uses `out_can_take = !m_axis_tvalid ||
m_axis_tready`. In a pass state, input ready follows this capacity; header and
drain states do not depend on output ready. Stable registered data, last, and
error fields are held whenever output is valid and stalled.

With message filtering enabled, the first payload byte is accepted into the
same registered output buffer only when it matches. A mismatch is discarded.
When disabled, the first payload byte follows the ordinary pass path.

If `tlast` closes the frame on an emitted byte before the declared payload end,
that byte is marked last and error. Bytes already emitted remain speculative;
the descriptor reports `BAD_LENGTH_OR_TRUNCATED`. A good declared final byte is
marked last without error. Additional bytes are Ethernet padding and are never
emitted.

## Descriptor and inter-frame behavior

There is one descriptor slot. It holds every field stable until ready/valid
handshake and prevents new input. Sequence counts completed input frames when
their descriptors are created, modulo 2^32. Synchronous active-low reset aborts
an incomplete frame without a descriptor and resets the next sequence to zero.

## Exclusions and rationale

Options, VLAN, reassembly, checksums, and multiple outstanding descriptors need
additional parse/storage or transaction machinery and are intentionally outside
this implementation. A source that never asserts `tlast` leaves the core in that
frame because the interface has no independent start-of-frame marker or
timeout.

Generic synthesis targets `udp_packet_filter` directly using
`synth/udp_packet_filter.ys`.
