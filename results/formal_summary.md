# Formal verification

- Status: `pass`
- Tool: SymbiYosys with Yosys 0.69+173 (git sha1 53f1cdd34-dirty, Release, Clang /usr/bin/clang++ 21.1.8)
- Properties: [`formal/udp_packet_filter_formal.sv`](../formal/udp_packet_filter_formal.sv)

| Task | Engine | Result |
|---|---|---|
| prove | `abc pdr` (unbounded) | PASS |
| cover | `smtbmc yices`, depth 64 | PASS |
