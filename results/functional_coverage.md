# Functional coverage hit counts

Source frames: `800`. Percentage coverage is not reported.

## Reason

- `ACCEPT`: 75
- `NON_IPV4`: 85
- `BAD_IPV4_HEADER`: 91
- `NON_UDP`: 86
- `FRAGMENTED`: 75
- `BAD_LENGTH_OR_TRUNCATED`: 87
- `DST_PORT_MISMATCH`: 110
- `MSG_TYPE_MISMATCH`: 102
- `FRAME_TOO_LONG`: 89

## Accepted Payload Size

- `0`: 18
- `8-63`: 16
- `64-255`: 11
- `1`: 10
- `256+`: 11
- `2-7`: 9

## Message Filter

- `disabled`: 373
- `enabled`: 427

## Port

- `match`: 690
- `mismatch`: 110

## Padding

- `yes`: 57
- `no`: 743

## Df

- `1`: 397
- `0`: 403

## Input Gaps

- `yes`: 419
- `no`: 381

## Output Backpressure

- `no`: 772
- `yes`: 28

## Result Backpressure

- `no`: 507
- `yes`: 293

## Truncation Region

- `none`: 713
- `udp`: 12
- `ethernet`: 17
- `ipv4`: 26
- `first_payload`: 15
- `later_payload`: 17

## Output Semantic

- `no_output`: 711
- `full_good_output`: 57
- `partial_error_output`: 32
