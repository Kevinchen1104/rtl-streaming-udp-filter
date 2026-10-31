# Functional coverage

From 800 randomized frames (seeds 1, 7, 42, 2027). Every bin is declared in `sim/coverage.py` with a minimum hit count; the run fails if any bin falls short.

## Reason

| Bin | Goal | Hits |
|---|---:|---:|
| `ACCEPT` | 5 | 262 |
| `NON_IPV4` | 5 | 38 |
| `BAD_IPV4_HEADER` | 5 | 42 |
| `NON_UDP` | 5 | 51 |
| `FRAGMENTED` | 5 | 38 |
| `BAD_LENGTH_OR_TRUNCATED` | 5 | 226 |
| `DST_PORT_MISMATCH` | 5 | 53 |
| `MSG_TYPE_MISMATCH` | 5 | 58 |
| `FRAME_TOO_LONG` | 5 | 32 |

## Accepted payload size

| Bin | Goal | Hits |
|---|---:|---:|
| `0` | 5 | 43 |
| `1` | 5 | 53 |
| `2-7` | 5 | 41 |
| `8-63` | 5 | 47 |
| `64-255` | 5 | 38 |
| `256+` | 5 | 40 |

## Message filter

| Bin | Goal | Hits |
|---|---:|---:|
| `enabled` | 5 | 411 |
| `disabled` | 5 | 389 |

## Padding

| Bin | Goal | Hits |
|---|---:|---:|
| `yes` | 5 | 83 |
| `no` | 5 | 717 |

## Df

| Bin | Goal | Hits |
|---|---:|---:|
| `0` | 5 | 414 |
| `1` | 5 | 386 |

## Input gaps

| Bin | Goal | Hits |
|---|---:|---:|
| `yes` | 5 | 395 |
| `no` | 5 | 405 |

## Result backpressure

| Bin | Goal | Hits |
|---|---:|---:|
| `yes` | 5 | 291 |
| `no` | 5 | 509 |

## Truncation region

| Bin | Goal | Hits |
|---|---:|---:|
| `none` | 5 | 607 |
| `ethernet` | 5 | 18 |
| `ipv4` | 5 | 26 |
| `udp` | 5 | 19 |
| `first_payload` | 5 | 31 |
| `later_payload` | 5 | 30 |
| `after_filter_reject` | 5 | 69 |

## Output semantic

| Bin | Goal | Hits |
|---|---:|---:|
| `full_good_output` | 5 | 219 |
| `partial_error_output` | 5 | 61 |
| `no_output` | 5 | 520 |

## Output backpressure on payload

| Bin | Goal | Hits |
|---|---:|---:|
| `stalled` | 5 | 100 |
| `not_stalled` | 5 | 180 |

## Partial output x output stall

| Bin | Goal | Hits |
|---|---:|---:|
| `stalled` | 5 | 15 |
| `not_stalled` | 5 | 46 |
