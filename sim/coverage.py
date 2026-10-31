"""Functional coverage bins and goals for the randomized RTL regression.

Every bin is declared here up front with a minimum hit count. The randomized
test records hits, and scripts/generate_results.py fails the run if any bin
misses its goal. A bin that is never hit therefore shows up as a failure
instead of silently disappearing from the report.
"""

from __future__ import annotations

from collections import Counter

from sim.reference_model import Reason

MIN_HITS = 5

# group -> {bin: minimum hits}
GOALS: dict[str, dict[str, int]] = {
    "reason": {reason.name: MIN_HITS for reason in Reason},
    "accepted_payload_size": {
        name: MIN_HITS for name in ["0", "1", "2-7", "8-63", "64-255", "256+"]
    },
    "message_filter": {"enabled": MIN_HITS, "disabled": MIN_HITS},
    "padding": {"yes": MIN_HITS, "no": MIN_HITS},
    "df": {"0": MIN_HITS, "1": MIN_HITS},
    "input_gaps": {"yes": MIN_HITS, "no": MIN_HITS},
    "result_backpressure": {"yes": MIN_HITS, "no": MIN_HITS},
    "truncation_region": {
        name: MIN_HITS
        for name in [
            "none", "ethernet", "ipv4", "udp", "first_payload",
            "later_payload", "after_filter_reject",
        ]
    },
    "output_semantic": {
        "full_good_output": MIN_HITS,
        "partial_error_output": MIN_HITS,
        "no_output": MIN_HITS,
    },
    # Only frames that produced payload output: did the output stall?
    "output_backpressure_on_payload": {"stalled": MIN_HITS, "not_stalled": MIN_HITS},
    # Cross: late truncation while the output was also stalling.
    "partial_output_x_output_stall": {"stalled": MIN_HITS, "not_stalled": MIN_HITS},
}


def payload_size_bin(length: int) -> str:
    if length <= 1:
        return str(length)
    if length <= 7:
        return "2-7"
    if length <= 63:
        return "8-63"
    if length <= 255:
        return "64-255"
    return "256+"


def new_counters() -> dict[str, Counter[str]]:
    return {group: Counter() for group in GOALS}


def merge(parts: list[dict[str, dict[str, int]]]) -> dict[str, dict[str, int]]:
    """Add up per-seed hit counts, keeping every declared bin."""
    total = {group: {name: 0 for name in bins} for group, bins in GOALS.items()}
    for part in parts:
        for group, bins in part.items():
            if group not in total:
                raise ValueError(f"undeclared coverage group: {group}")
            for name, count in bins.items():
                if name not in total[group]:
                    raise ValueError(f"undeclared coverage bin: {group}/{name}")
                total[group][name] += int(count)
    return total


def unmet_goals(hits: dict[str, dict[str, int]]) -> list[str]:
    missing = []
    for group, bins in GOALS.items():
        for name, goal in bins.items():
            count = hits.get(group, {}).get(name, 0)
            if count < goal:
                missing.append(f"{group}/{name}: {count} < {goal}")
    return missing
