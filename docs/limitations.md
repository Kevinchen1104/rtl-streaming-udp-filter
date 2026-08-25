# Limitations

- Only Ethernet II EtherType `0x0800`, IPv4 version 4/IHL 5, unfragmented UDP
  is eligible. VLAN, IPv6, IP options, fragments, and reassembly are absent.
- IPv4 and UDP checksum fields are ignored. Corruption is not detected by this
  block unless it violates a checked structural field.
- There is one frame and one descriptor in flight. A held result backpressures
  the next frame.
- Payload is speculative. A late-truncated rejected frame can have transferred
  partial output; commit-only consumers need external buffering.
- There is no timeout. A source that never transfers `tlast` leaves the parser
  in that frame because the interface has no separate start-of-frame signal.
- Input begins after preamble/SFD and excludes FCS. This is not a PHY or MAC.
- The ready/valid behavior is specified locally; the interface is not presented
  as AXI4-Stream compliant.
- Generic Yosys synthesis confirms that the RTL can be lowered by that tool. It
  does not establish FPGA LUT use, WNS, Fmax, ASIC timing, power, or physical
  quality.
- No FPGA wrapper or Basys3 hardware test is included. Ethernet or UART-fed
  FPGA validation is outside the verified scope.
