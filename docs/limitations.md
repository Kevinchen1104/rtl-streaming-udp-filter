# Limitations

**Protocol.** Only Ethernet II, IPv4 without options, unfragmented UDP. No
VLAN tags, IPv6, or reassembly. Checksums are not checked, so a corrupted
frame is caught only if the corruption breaks a field the block does check.

**Cut-through.** Payload leaves before the frame ends. If a frame turns out to
be short, bytes already sent cannot be recalled; the stream ends with an error
beat and the result record says `BAD_LENGTH_OR_TRUNCATED`. A consumer that
needs only complete, accepted payloads must buffer each frame until its result
record arrives.

**One frame at a time.** A result record waiting for `result_ready` holds off
the next frame.

**No timeout.** A source that never sends `tlast` leaves the block in that
frame until reset.

**Not a MAC.** Input starts after the preamble and SFD and has no FCS; the MAC
in front of the block handles those.

**Implementation numbers.** ECP5 timing comes from nextpnr out of context, so
it covers register-to-register paths, not I/O. The Vivado results for the
Basys 3 are also out of context and are rerun by hand, not in CI. The design
has not been run on hardware.
