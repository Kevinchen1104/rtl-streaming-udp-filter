"""Render cycle traces recorded by the cocotb `waveform_example` test as SVG.

Input:  results/raw/waves/<name>.json (one snapshot of the ports per cycle)
Output: results/waveforms/<name>.svg
"""

from __future__ import annotations

import json
from html import escape
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CYCLE_W = 44
ROW_H = 26
LABEL_W = 160
TOP = 44
WAVE_H = 14

REASONS = {0: "ACCEPT", 1: "NON_IPV4", 2: "BAD_IPV4", 3: "NON_UDP", 4: "FRAG",
           5: "TRUNC", 6: "PORT", 7: "MSG", 8: "TOO_LONG"}

# (label, kind, key, valid key, ready key)
ROWS = [
    ("clk", "clock", "", "", ""),
    ("s_axis_tvalid", "bit", "s_valid", "", ""),
    ("s_axis_tready", "bit", "s_ready", "", ""),
    ("s_axis_tdata", "bus", "s_data", "s_valid", "s_ready"),
    ("s_axis_tlast", "bit", "s_last", "", ""),
    ("m_axis_tvalid", "bit", "m_valid", "", ""),
    ("m_axis_tready", "bit", "m_ready", "", ""),
    ("m_axis_tdata", "bus", "m_data", "m_valid", "m_ready"),
    ("m_axis_tlast", "bit", "m_last", "", ""),
    ("m_axis_tuser_error", "bit", "m_error", "", ""),
    ("result_valid", "bit", "r_valid", "", ""),
    ("result_ready", "bit", "r_ready", "", ""),
    ("result_reason", "bus", "r_reason", "r_valid", "r_ready"),
]

INK = "#1f2328"
MUTED = "#8c959f"
GRID = "#eaeef2"
TRANSFER = "#d1f0d9"
STALLED = "#fbe5b5"


def _bus_label(key: str, value: int) -> str:
    if key == "r_reason":
        return REASONS.get(value, str(value))
    if 0x20 < value < 0x7F:
        return f"'{chr(value)}'"
    return f"{value:02X}"


def render(trace: list[dict[str, int]], title: str) -> str:
    cycles = len(trace)
    width = LABEL_W + cycles * CYCLE_W + 12
    height = TOP + len(ROWS) * ROW_H + 50
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="ui-monospace, SFMono-Regular, '
        f'Menlo, Consolas, monospace" font-size="11">',
        f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
        f'<text x="12" y="20" font-size="13" font-weight="bold" fill="{INK}">'
        f'{escape(title)}</text>',
    ]
    first_cycle = trace[0]["cycle"]
    for i in range(cycles + 1):
        x = LABEL_W + i * CYCLE_W
        out.append(f'<line x1="{x}" y1="{TOP - 6}" x2="{x}" '
                   f'y2="{TOP + len(ROWS) * ROW_H}" stroke="{GRID}"/>')
        if i < cycles:
            out.append(f'<text x="{x + CYCLE_W / 2}" y="{TOP - 10}" text-anchor="middle" '
                       f'fill="{MUTED}" font-size="10">{first_cycle + i}</text>')

    for row, (label, kind, key, valid_key, ready_key) in enumerate(ROWS):
        y = TOP + row * ROW_H
        high, low = y + (ROW_H - WAVE_H) / 2, y + (ROW_H + WAVE_H) / 2
        out.append(f'<text x="12" y="{y + ROW_H / 2 + 4}" fill="{INK}">{label}</text>')
        if kind == "clock":
            path = []
            for i in range(cycles):
                x = LABEL_W + i * CYCLE_W
                path.append(f"M{x},{low} L{x},{high} L{x + CYCLE_W / 2},{high} "
                            f"L{x + CYCLE_W / 2},{low} L{x + CYCLE_W},{low}")
            out.append(f'<path d="{" ".join(path)}" fill="none" stroke="{INK}"/>')
        elif kind == "bit":
            points = []
            for i, snapshot in enumerate(trace):
                x = LABEL_W + i * CYCLE_W
                level = high if snapshot[key] else low
                points += [f"{x},{level}", f"{x + CYCLE_W},{level}"]
            out.append(f'<polyline points="{" ".join(points)}" fill="none" '
                       f'stroke="{INK}" stroke-width="1.5"/>')
        else:
            for i, snapshot in enumerate(trace):
                x = LABEL_W + i * CYCLE_W
                if not snapshot[valid_key]:
                    mid = (high + low) / 2
                    out.append(f'<line x1="{x}" y1="{mid}" x2="{x + CYCLE_W}" y2="{mid}" '
                               f'stroke="{MUTED}"/>')
                    continue
                fill = TRANSFER if snapshot[ready_key] else STALLED
                out.append(
                    f'<polygon points="{x + 3},{(high + low) / 2} {x + 6},{high} '
                    f'{x + CYCLE_W - 6},{high} {x + CYCLE_W - 3},{(high + low) / 2} '
                    f'{x + CYCLE_W - 6},{low} {x + 6},{low}" fill="{fill}" stroke="{INK}"/>')
                out.append(f'<text x="{x + CYCLE_W / 2}" y="{(high + low) / 2 + 4}" '
                           f'text-anchor="middle" fill="{INK}" font-size="10">'
                           f'{escape(_bus_label(key, snapshot[key]))}</text>')

    legend_y = TOP + len(ROWS) * ROW_H + 20
    out += [
        f'<rect x="12" y="{legend_y - 10}" width="14" height="12" fill="{TRANSFER}" '
        f'stroke="{INK}"/>',
        f'<text x="32" y="{legend_y}" fill="{INK}">transfer (valid and ready)</text>',
        f'<rect x="220" y="{legend_y - 10}" width="14" height="12" fill="{STALLED}" '
        f'stroke="{INK}"/>',
        f'<text x="240" y="{legend_y}" fill="{INK}">valid, stalled</text>',
        f'<text x="12" y="{legend_y + 18}" fill="{MUTED}">'
        'Cycle numbers count from the first byte of the frame.</text>',
        "</svg>",
    ]
    return "\n".join(out) + "\n"


TITLES = {
    "accepted_with_output_stall":
        "Accepted frame, 6-byte payload, output stalled for 2 cycles",
    "late_truncation":
        "Frame declares 6 payload bytes but ends after 3",
}


def main() -> int:
    source = ROOT / "results" / "raw" / "waves"
    target = ROOT / "results" / "waveforms"
    target.mkdir(parents=True, exist_ok=True)
    files = sorted(source.glob("*.json"))
    if not files:
        raise RuntimeError("no waveform traces in results/raw/waves")
    for path in files:
        trace = json.loads(path.read_text(encoding="utf-8"))
        svg = render(trace, TITLES.get(path.stem, path.stem.replace("_", " ")))
        (target / f"{path.stem}.svg").write_text(svg, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
