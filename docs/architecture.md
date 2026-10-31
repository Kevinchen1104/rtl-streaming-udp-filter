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

The parser evaluates each check as soon as its field completes:

- EtherType at byte 13, version/IHL at byte 14, and the logical maximum at
  byte 17. A failure moves to drain with that reason.
- Fragmentation is latched at byte 21 and evaluated together with protocol at
  byte 23, so `NON_UDP` takes priority over `FRAGMENTED`.
- Length rules and the destination port are evaluated at byte 41, the last
  UDP header byte.

Eligibility rejects leave `result_payload_len` at zero. After byte 41, the
parser counts payload bytes in every state, including drain after a port or
message reject. When `tlast` arrives, a count below the declared payload length
turns the pending reason into `BAD_LENGTH_OR_TRUNCATED` (the `close_reason`
function). This makes the result match the whole-frame priority order in the
specification without special same-byte cases.

## Payload and backpressure

Payload goes through a two-entry skid buffer (`stream_byte_buffer`). In a
payload state, input ready is `!skid_valid`, a flop output, so downstream
ready never reaches upstream ready combinationally. Header and drain states do
not depend on output ready. Data, last, and error are held whenever output is
valid and stalled.

With message filtering enabled, input ready in the first-payload state still
comes only from the buffer. The first byte is written to the buffer only when
it matches; a mismatching byte is accepted and dropped. When filtering is
disabled, the first payload byte follows the ordinary pass path.

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
