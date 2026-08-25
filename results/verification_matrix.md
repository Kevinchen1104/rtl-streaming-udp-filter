# Verification matrix

Every row below comes from a named scenario reported by the passing cocotb regression.

| ID | Executed scenario | Test source | Result |
|---:|---|---|---|
| 1 | minimal zero | `directed_rtl_matrix` | pass |
| 2 | one byte | `directed_rtl_matrix` | pass |
| 3 | multi byte | `directed_rtl_matrix` | pass |
| 4 | msg one | `directed_rtl_matrix` | pass |
| 5 | msg multi | `directed_rtl_matrix` | pass |
| 6 | padding | `directed_rtl_matrix` | pass |
| 7 | df0 | `directed_rtl_matrix` | pass |
| 8 | df1 | `directed_rtl_matrix` | pass |
| 9 | non ipv4 | `directed_rtl_matrix` | pass |
| 10 | bad version | `directed_rtl_matrix` | pass |
| 11 | ihl4 | `directed_rtl_matrix` | pass |
| 12 | ihl6 | `directed_rtl_matrix` | pass |
| 13 | tcp | `directed_rtl_matrix` | pass |
| 14 | icmp | `directed_rtl_matrix` | pass |
| 15 | mf | `directed_rtl_matrix` | pass |
| 16 | fragment offset | `directed_rtl_matrix` | pass |
| 17 | port mismatch | `directed_rtl_matrix` | pass |
| 18 | port mismatch same cycle truncation | `directed_rtl_matrix` | pass |
| 19 | message mismatch | `directed_rtl_matrix` | pass |
| 20 | message mismatch same byte truncation | `directed_rtl_matrix` | pass |
| 21 | message mismatch then late truncation | `directed_rtl_matrix` | pass |
| 22 | message empty | `directed_rtl_matrix` | pass |
| 23 | ip short | `directed_rtl_matrix` | pass |
| 24 | udp short | `directed_rtl_matrix` | pass |
| 25 | udp long relation | `directed_rtl_matrix` | pass |
| 26 | udp short relation | `directed_rtl_matrix` | pass |
| 27 | too long | `directed_rtl_matrix` | pass |
| 28 | late first | `directed_rtl_matrix` | pass |
| 29 | late middle | `directed_rtl_matrix` | pass |
| 30 | late before final | `directed_rtl_matrix` | pass |
| 31 | long padding | `directed_rtl_matrix` | pass |
| 32 | maximum logical | `directed_rtl_matrix` | pass |
| 33 | header truncation 0 through 41 | `directed_rtl_matrix` | pass |
| 34 | configuration latched | `directed_rtl_matrix` | pass |
| 35 | sequence wrap | `directed_rtl_matrix` | pass |
| 36 | no stall | `backpressure_and_sequencing` | pass |
| 37 | input gaps | `backpressure_and_sequencing` | pass |
| 38 | output stalls | `backpressure_and_sequencing` | pass |
| 39 | simultaneous | `backpressure_and_sequencing` | pass |
| 40 | result stall | `backpressure_and_sequencing` | pass |
| 41 | periodic long payload | `backpressure_and_sequencing` | pass |
| 42 | port mismatch output never ready | `backpressure_and_sequencing` | pass |
| 43 | message mismatch output never ready | `backpressure_and_sequencing` | pass |
| 44 | idle reset | `reset_abort_matrix` | pass |
| 45 | ethernet reset | `reset_abort_matrix` | pass |
| 46 | ipv4 reset | `reset_abort_matrix` | pass |
| 47 | udp reset | `reset_abort_matrix` | pass |
| 48 | payload output stall reset | `reset_abort_matrix` | pass |
| 49 | descriptor stall reset | `reset_abort_matrix` | pass |
| 50 | post reset sequence zero | `reset_abort_matrix` | pass |
