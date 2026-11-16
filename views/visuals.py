"""Pictures that can be read in a couple of seconds: the scorecard shape, the
price-against-value bar, the health dots and the 52-week range.

The two drawings are SVG images built here, in the app's colours.
"""

import math
from html import escape

import streamlit as st

from .style import BLUE, BORDER, CARD, GOLD, GREEN, GREY, MUTED, RED

TEXT = "#e8ecf4"


def _score_colour(score) -> str:
    if score is None:
        return GREY
    return GREEN if score >= 3.5 else GOLD if score >= 2 else RED


def scorecard(scores: list, overall=None) -> None:
    """The five scores as a shape: big and even is a strong all-rounder, a dent is a weakness."""
    width, height, centre, middle, radius = 400, 330, 200, 158, 96
    count = len(scores)

    def point(index: int, level: float) -> tuple:
        angle = -math.pi / 2 + 2 * math.pi * index / count
        return (centre + radius * level / 5 * math.cos(angle),
                middle + radius * level / 5 * math.sin(angle))

    def polygon(level) -> str:
        return " ".join(f"{x:.1f},{y:.1f}" for x, y in (point(i, level) for i in range(count)))

    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
             f'width="{width}" height="{height}" font-family="Source Sans Pro, Helvetica, Arial, sans-serif">']
    for ring in (1, 2, 3, 4, 5):
        parts.append(f'<polygon points="{polygon(ring)}" fill="none" stroke="{BORDER}" stroke-width="1"/>')
    for index in range(count):
        x, y = point(index, 5)
        parts.append(f'<line x1="{centre}" y1="{middle}" x2="{x:.1f}" y2="{y:.1f}" stroke="{BORDER}"/>')

    shape = " ".join(f"{x:.1f},{y:.1f}" for x, y in
                     (point(i, s["score"] or 0) for i, s in enumerate(scores)))
    parts.append(f'<polygon points="{shape}" fill="{GOLD}" fill-opacity="0.28" '
                 f'stroke="{GOLD}" stroke-width="2" stroke-linejoin="round"/>')

    for index, item in enumerate(scores):
        x, y = point(index, item["score"] or 0)
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.5" fill="{GOLD}"/>')
        label_x, label_y = point(index, 6.5)
        anchor = "middle" if abs(label_x - centre) < 12 else "start" if label_x > centre else "end"
        shown = "n/a" if item["score"] is None else f"{item['score']:.1f}"
        parts.append(
            f'<text x="{label_x:.1f}" y="{label_y - 4:.1f}" text-anchor="{anchor}" fill="{MUTED}" '
            f'font-size="12.5">{escape(item["name"])}<title>{escape(item["why"])}</title></text>'
            f'<text x="{label_x:.1f}" y="{label_y + 13:.1f}" text-anchor="{anchor}" '
            f'fill="{_score_colour(item["score"])}" font-size="15" font-weight="700">{shown}</text>')
    if overall is not None:
        parts.append(f'<text x="{centre}" y="{height - 8}" text-anchor="middle" fill="{MUTED}" '
                     f'font-size="13">Overall <tspan fill="{TEXT}" font-weight="700" font-size="16">'
                     f'{overall:.1f}</tspan> out of 5</text>')
    parts.append("</svg>")
    st.image("".join(parts), width=width)


def value_bar(price: float, values: list, band=None) -> None:
    """Today's price as a pin on a line, with what each method says the share is worth.

    `values` is a list of {"label", "value"}; `band` is an optional (low, high)
    range to shade, such as the DCF's bear-to-bull cases.
    """
    marks = [v for v in values if v["value"] is not None and v["value"] > 0]
    if not marks:
        return
    points = [price] + [m["value"] for m in marks] + list(band or [])
    low, high = min(points), max(points)
    pad = (high - low) * 0.12 or price * 0.1
    low, high = max(low - pad, 0), high + pad
    width, left, right, line_y = 1000, 30, 970, 62

    def x(value: float) -> float:
        return left + (right - left) * (value - low) / (high - low)

    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} 130" width="{width}" '
             'height="130" font-family="Source Sans Pro, Helvetica, Arial, sans-serif">',
             f'<line x1="{left}" y1="{line_y}" x2="{right}" y2="{line_y}" stroke="{BORDER}" '
             'stroke-width="6" stroke-linecap="round"/>']
    if band and band[1] > band[0]:
        parts.append(f'<rect x="{x(band[0]):.1f}" y="{line_y - 9}" width="{x(band[1]) - x(band[0]):.1f}" '
                     f'height="18" rx="9" fill="{GOLD}" fill-opacity="0.30"/>')

    # Labels sit on two rows under the line so neighbours don't overlap.
    rows_end = [-1e9, -1e9]
    for mark in sorted(marks, key=lambda m: m["value"]):
        mx = x(mark["value"])
        text = f'{mark["label"]} ${mark["value"]:,.0f}'
        half = len(text) * 3.6
        row = 0 if mx - half > rows_end[0] else 1
        rows_end[row] = mx + half
        label_y = line_y + 34 + row * 24
        anchor_x = min(max(mx, left + half), right - half)
        parts.append(
            f'<line x1="{mx:.1f}" y1="{line_y - 11}" x2="{mx:.1f}" y2="{label_y - 14}" stroke="{GOLD}" stroke-width="2"/>'
            f'<circle cx="{mx:.1f}" cy="{line_y}" r="6" fill="{GOLD}"/>'
            f'<text x="{anchor_x:.1f}" y="{label_y}" text-anchor="middle" fill="{GOLD}" '
            f'font-size="14" font-weight="600">{escape(text)}</text>')

    px = x(price)
    text = f"Price today ${price:,.2f}"
    half = len(text) * 4.2
    anchor_x = min(max(px, left + half), right - half)
    parts.append(
        f'<line x1="{px:.1f}" y1="{line_y - 26}" x2="{px:.1f}" y2="{line_y + 12}" stroke="{BLUE}" stroke-width="3"/>'
        f'<circle cx="{px:.1f}" cy="{line_y}" r="8" fill="{BLUE}" stroke="{CARD}" stroke-width="2"/>'
        f'<text x="{anchor_x:.1f}" y="{line_y - 34}" text-anchor="middle" fill="{BLUE}" '
        f'font-size="15" font-weight="700">{escape(text)}</text></svg>')
    st.image("".join(parts), width="stretch")


def health_dots(results: list, labels: dict) -> None:
    """One dot per health check, coloured by its result. Hover a dot for the question."""
    colours = {"good": GREEN, "watch": GOLD, "weak": RED}
    dots = "".join(
        f'<span title="{escape(r["question"])} {escape(labels[r["status"]])}. {escape(r["detail"])}" '
        f'style="display:inline-block;width:14px;height:14px;border-radius:50%;margin-right:6px;'
        f'background:{colours.get(r["status"], GREY)}"></span>'
        for r in results)
    good = sum(r["status"] == "good" for r in results)
    weak = sum(r["status"] == "weak" for r in results)
    summary = f"{good} of {len(results)} health checks good" + (f", {weak} weak" if weak else "")
    st.html(f'<div style="display:flex;align-items:center;gap:12px;margin:6px 0 2px">'
            f'<div>{dots}</div><div style="color:{MUTED};font-size:0.85rem">{summary}</div></div>')


def range_bar(low: float, high: float, value: float, low_label: str, high_label: str) -> None:
    """Where a value sits between a low and a high, e.g. today's price in its 52-week range."""
    if not high > low:
        return
    share = min(max((value - low) / (high - low), 0), 1)
    st.html(
        f'<div style="margin:4px 0 10px">'
        f'<div style="position:relative;height:8px;border-radius:4px;'
        f'background:linear-gradient(90deg,{RED}55,{GOLD}55,{GREEN}55)">'
        f'<div style="position:absolute;left:calc({share:.3f}*(100% - 14px));top:-4px;width:14px;height:16px;'
        f'border-radius:4px;background:{BLUE}"></div></div>'
        f'<div style="display:flex;justify-content:space-between;color:{MUTED};font-size:0.8rem;'
        f'margin-top:6px"><span>{escape(low_label)}</span>'
        f'<span>{share:.0%} of the way from low to high</span><span>{escape(high_label)}</span></div></div>')
