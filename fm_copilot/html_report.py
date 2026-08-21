"""Convert the DoF markdown report into a styled, self-contained HTML report
with hand-built inline SVG charts.

No new dependency: both the markdown parsing and the charting are hand-built,
since we fully control the (small, known) subset of markdown that report.py
actually produces. Colors are taken verbatim from the dataviz skill's
pre-validated reference palette (references/palette.md) — light mode only,
since this is a generated offline document, not an interactive app.
"""

from __future__ import annotations

import html as html_lib
import math
import re
from typing import TYPE_CHECKING, Callable, Optional

from fm_copilot import roles, tactics

if TYPE_CHECKING:
    from fm_copilot.analyzer import SquadAnalysis

# --- Palette (dataviz skill reference palette, light mode) ---
SURFACE = "#fcfcfb"
PAGE = "#f9f9f7"
INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRIDLINE = "#e1e0d9"
BORDER = "rgba(11,11,11,0.10)"

CATEGORICAL_BLUE = "#2a78d6"  # single-hue magnitude bars (categorical slot 1)

# Style-fit tiers are an ordered good->critical scale, so they use the
# status palette (fixed, never themed) rather than arbitrary categorical hues.
STATUS_COLORS = {
    "Does very well": "#0ca30c",
    "Does well": "#fab219",
    "Doesn't do well": "#ec835a",
    "Doesn't work at all": "#d03b3b",
}

# Exact-match known table-cell values -> a colored pill instead of plain
# text. Generic, applied by _render_table to every cell, so it colorizes
# the style-fit tier column, the exit value-trend column, and the Squad
# Audit tier column all at once with zero per-table special-casing.
SEMANTIC_TAGS: dict[str, str] = {
    **STATUS_COLORS,
    "rising": "#0ca30c",
    "stable": "#898781",
    "declining": "#d03b3b",
    "Core": CATEGORICAL_BLUE,
    "Rotation": "#5aa0e0",
    "Filler": "#898781",
    "Saleable": "#ec835a",
    "Exit": "#d03b3b",
}

# Decision-board Call-column colors (report_v2.html's 3-tag scheme: sell,
# buy, hold) — checked before SEMANTIC_TAGS in _render_cell since "Buy #1",
# "Buy #2"... needs a prefix match, not an exact one.
DECISION_SELL = "#8c3b2f"
DECISION_BUY = "#2f5d46"
DECISION_HOLD = "#5b5236"
DECISION_TAG_COLORS: dict[str, str] = {
    "Sell": DECISION_SELL,
    "Protect": DECISION_HOLD,
    "Hold": DECISION_HOLD,
    "Fix free": DECISION_HOLD,
}

# Pitch coordinates (0-100, x=touchline to touchline, y=0 attacking third to
# y=100 own goal) for every slot name used across the 6 formations in
# roles.py's FORMATIONS dict. One shared map — no per-formation special-casing.
SLOT_COORDS: dict[str, tuple[int, int]] = {
    "GK": (50, 93),
    "RB": (84, 76), "LB": (16, 76), "RCB": (64, 80), "LCB": (36, 80), "CB": (50, 80),
    "RWB": (87, 58), "LWB": (13, 58),
    "RDM": (62, 62), "LDM": (38, 62), "DM": (50, 64),
    "RCM": (64, 48), "LCM": (36, 48), "RM": (85, 47), "LM": (15, 47),
    "AM": (50, 32), "AMR": (72, 30), "AML": (28, 30),
    "RW": (82, 20), "LW": (18, 20),
    "ST": (50, 10), "RST": (60, 10), "LST": (40, 10),
}


# ---------------------------------------------------------------------------
# Markdown -> HTML (hand-rolled, targeted at exactly what report.py produces:
# #/## headers, paragraphs, "- " bullet lists, pipe tables, **bold**, "---")
# ---------------------------------------------------------------------------

def _slugify(text: str) -> str:
    text = re.sub(r"[^\w\s-]", "", text.lower())
    return re.sub(r"\s+", "-", text.strip())


def _inline_md(text: str) -> str:
    text = html_lib.escape(text)
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)


def _render_cell(text: str) -> str:
    stripped = text.strip()
    color = DECISION_TAG_COLORS.get(stripped)
    if color is None and stripped.startswith("Buy #"):
        color = DECISION_BUY
    if color is None:
        color = SEMANTIC_TAGS.get(stripped)
    if color:
        return f'<span class="tag" style="background:{color}">{html_lib.escape(stripped)}</span>'
    return _inline_md(text)


def _render_table(table_lines: list[str]) -> str:
    rows = [[c.strip() for c in line.strip("|").split("|")] for line in table_lines]
    if len(rows) >= 2 and all(re.match(r"^:?-+:?$", c) for c in rows[1]):
        header, body = rows[0], rows[2:]
    else:
        header, body = rows[0], rows[1:]

    thead = "".join(f"<th>{_inline_md(c)}</th>" for c in header)
    tbody = "".join(
        "<tr>" + "".join(f"<td>{_render_cell(c)}</td>" for c in row) + "</tr>"
        for row in body
    )
    return f'<div class="table-wrap"><table><thead><tr>{thead}</tr></thead><tbody>{tbody}</tbody></table></div>'


def markdown_to_html(md_text: str) -> str:
    lines = md_text.split("\n")
    out: list[str] = []
    paragraph: list[str] = []
    i = 0

    def flush_paragraph() -> None:
        if paragraph:
            out.append("<p>" + " ".join(paragraph) + "</p>")
            paragraph.clear()

    while i < len(lines):
        stripped = lines[i].strip()

        if not stripped:
            flush_paragraph()
            i += 1
            continue

        if stripped == "---":
            flush_paragraph()
            out.append("<hr>")
            i += 1
            continue

        # Literal collapsible-section markup, emitted verbatim by report.py
        # around specific tables (e.g. a long reference table) — passed
        # through untouched rather than wrapped in a <p>.
        if stripped.startswith("<details") or stripped.startswith("<summary") or stripped == "</details>":
            flush_paragraph()
            out.append(stripped)
            i += 1
            continue

        header_match = re.match(r"^(#{1,3})\s+(.*)$", stripped)
        if header_match:
            flush_paragraph()
            level = len(header_match.group(1))
            content = header_match.group(2)
            out.append(f'<h{level} id="{_slugify(content)}">{_inline_md(content)}</h{level}>')
            i += 1
            continue

        if stripped.startswith("|"):
            flush_paragraph()
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                table_lines.append(lines[i].strip())
                i += 1
            out.append(_render_table(table_lines))
            continue

        if stripped.startswith("- "):
            flush_paragraph()
            items = []
            while i < len(lines) and lines[i].strip().startswith("- "):
                items.append(f"<li>{_inline_md(lines[i].strip()[2:])}</li>")
                i += 1
            out.append("<ul>" + "".join(items) + "</ul>")
            continue

        # Ordered list ("1. ", "2. "...) — added for _render_sequencing
        # (report-restructure.md stage 2), which numbers its own rows; the
        # numbers are already correct in the source text, so <ol> is used
        # purely for list semantics/indentation, not renumbering.
        ordered_match = re.match(r"^\d+\.\s+(.*)$", stripped)
        if ordered_match:
            flush_paragraph()
            items = []
            while i < len(lines):
                m = re.match(r"^\d+\.\s+(.*)$", lines[i].strip())
                if not m:
                    break
                items.append(f"<li>{_inline_md(m.group(1))}</li>")
                i += 1
            out.append("<ol>" + "".join(items) + "</ol>")
            continue

        paragraph.append(_inline_md(stripped))
        i += 1

    flush_paragraph()
    return "\n".join(out)


# ---------------------------------------------------------------------------
# SVG bar chart (single primitive, reused by every chart below)
# ---------------------------------------------------------------------------

def _svg_bar_chart(
    data: list[tuple[str, float, str]],
    *, width: int = 640, row_height: int = 32, title: str = "", value_suffix: str = "",
    value_fmt: Optional[Callable[[float], str]] = None,
) -> str:
    if not data:
        return ""
    label_width = 190
    value_texts = [value_fmt(value) if value_fmt else f"{value:.1f}{value_suffix}" for _, value, _ in data]
    # Reserve enough right-hand margin for the longest value label, so it
    # never runs past the viewBox edge regardless of bar length.
    value_margin = max((len(t) for t in value_texts), default=4) * 7 + 16
    bar_area_width = max(width - label_width - value_margin, 60)
    max_value = max((v for _, v, _ in data), default=0) or 1
    height = len(data) * row_height + 16

    rows_svg = []
    y = 8
    for (label, value, color), value_text in zip(data, value_texts):
        bar_w = max((value / max_value) * bar_area_width, 2)
        bar_y = y + (row_height - 18) / 2
        cy = y + row_height / 2 + 4
        rows_svg.append(
            f'<text x="{label_width - 10}" y="{cy:.1f}" text-anchor="end" '
            f'font-size="13" fill="{INK_SECONDARY}">{html_lib.escape(label)}</text>'
            f'<rect x="{label_width}" y="{bar_y:.1f}" width="{bar_w:.1f}" height="18" rx="4" fill="{color}"/>'
            f'<text x="{label_width + bar_w + 8:.1f}" y="{cy:.1f}" '
            f'font-size="13" fill="{INK_PRIMARY}" font-weight="600">{html_lib.escape(value_text)}</text>'
        )
        y += row_height

    title_html = f'<div class="chart-title">{html_lib.escape(title)}</div>' if title else ""
    return (
        f'<div class="chart">{title_html}'
        f'<svg viewBox="0 0 {width} {height}" width="100%" role="img" '
        f'aria-label="{html_lib.escape(title)}">'
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="{SURFACE}"/>'
        f'{"".join(rows_svg)}</svg></div>'
    )


def _svg_radar(labels: list[str], actual: list[float], ideal: list[float], *, size: int = 200, max_value: float = 20) -> str:
    """Polygon-on-a-spoke-grid radar chart: solid filled polygon for a
    candidate's actual attributes, dashed outline for the role's ideal
    benchmark (roles.ideal_attribute_values). Same coordinate-math
    complexity as _pitch_diagram — no new charting dependency."""
    if not labels:
        return ""
    n = len(labels)
    cx = cy = size / 2
    radius = size * 0.34
    # The viewBox is padded well beyond the plot circle itself, purely so
    # attribute labels (some as long as "Communication") have room to spill
    # outward without clipping at the edge — doesn't change the rendered
    # on-page size, just the coordinate headroom.
    pad = size * 0.34

    def point(i: int, value: float) -> tuple[float, float]:
        angle = -math.pi / 2 + (2 * math.pi * i / n)
        r = radius * max(min(value / max_value, 1.0), 0.0)
        return (cx + r * math.cos(angle), cy + r * math.sin(angle))

    def ring_points(frac: float) -> str:
        return " ".join(
            f"{cx + radius * frac * math.cos(-math.pi / 2 + 2 * math.pi * i / n):.1f},"
            f"{cy + radius * frac * math.sin(-math.pi / 2 + 2 * math.pi * i / n):.1f}"
            for i in range(n)
        )

    rings = "".join(
        f'<polygon points="{ring_points(frac)}" fill="none" stroke="{GRIDLINE}" stroke-width="1"/>'
        for frac in (0.25, 0.5, 0.75, 1.0)
    )
    spokes = "".join(
        f'<line x1="{cx}" y1="{cy}" x2="{point(i, max_value)[0]:.1f}" y2="{point(i, max_value)[1]:.1f}" '
        f'stroke="{GRIDLINE}" stroke-width="1"/>'
        for i in range(n)
    )
    actual_pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in (point(i, v) for i, v in enumerate(actual)))
    ideal_pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in (point(i, v) for i, v in enumerate(ideal)))

    labels_svg = []
    for i, label in enumerate(labels):
        lx, ly = point(i, max_value * 1.2)
        anchor = "middle"
        if lx < cx - 5:
            anchor = "end"
        elif lx > cx + 5:
            anchor = "start"
        labels_svg.append(
            f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="{anchor}" '
            f'font-size="8.5" fill="{INK_MUTED}">{html_lib.escape(label)}</text>'
        )

    view = size + 2 * pad
    return (
        f'<svg viewBox="{-pad:.0f} {-pad:.0f} {view:.0f} {view:.0f}" width="100%" style="max-width:200px" role="img" '
        f'aria-label="Attribute radar vs. role benchmark">'
        f'{rings}{spokes}'
        f'<polygon points="{ideal_pts}" fill="none" stroke="{INK_MUTED}" stroke-width="1.5" stroke-dasharray="4,3"/>'
        f'<polygon points="{actual_pts}" fill="{CATEGORICAL_BLUE}" fill-opacity="0.28" stroke="{CATEGORICAL_BLUE}" stroke-width="2"/>'
        f'{"".join(labels_svg)}'
        f'</svg>'
    )


def _fmt_money(n: float) -> str:
    n = float(n or 0)
    if n >= 1_000_000:
        return f"£{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"£{n / 1_000:.0f}K"
    return f"£{n:.0f}"


def _leaderboard(items: list[tuple[str, str]], title: str = "") -> str:
    """A bold ranked top-N panel — the punchy visual treatment for a
    ranking, as distinct from _svg_bar_chart's plain magnitude comparison."""
    if not items:
        return ""
    rows = "".join(
        f'<div class="lb-row"><div class="lb-rank">{i}</div>'
        f'<div class="lb-name">{html_lib.escape(name)}</div>'
        f'<div class="lb-value">{html_lib.escape(value)}</div></div>'
        for i, (name, value) in enumerate(items, start=1)
    )
    title_html = f'<div class="lb-title">{html_lib.escape(title)}</div>' if title else ""
    return f'<div class="leaderboard">{title_html}{rows}</div>'


def _stat_tiles(tiles: list[tuple[str, str, str]]) -> str:
    cells = "".join(
        f'<div class="stat-tile"><div class="stat-value">{html_lib.escape(value)}</div>'
        f'<div class="stat-label">{html_lib.escape(label)}</div>'
        + (f'<div class="stat-sub">{html_lib.escape(sub)}</div>' if sub else "")
        + "</div>"
        for label, value, sub in tiles
    )
    return f'<div class="stat-strip">{cells}</div>'


# ---------------------------------------------------------------------------
# Chart generators (each consumes SquadAnalysis / already-computed data —
# no new scoring logic, purely visualizing what's already there)
# ---------------------------------------------------------------------------

def _pitch_background(width: int, height: int) -> str:
    stripe_h = height / 10
    stripes = "".join(
        f'<rect x="0" y="{i * stripe_h:.1f}" width="{width}" height="{stripe_h:.1f}" '
        f'fill="{"#3f9457" if i % 2 == 0 else "#3a8b51"}"/>'
        for i in range(10)
    )
    cx, cy = width / 2, height / 2
    line = "rgba(255,255,255,0.75)"
    box_w, box_h = width * 0.56, height * 0.14
    six_w, six_h = width * 0.28, height * 0.06
    return (
        f'{stripes}'
        f'<rect x="2" y="2" width="{width - 4}" height="{height - 4}" fill="none" stroke="{line}" stroke-width="2"/>'
        f'<line x1="2" y1="{cy:.1f}" x2="{width - 2}" y2="{cy:.1f}" stroke="{line}" stroke-width="2"/>'
        f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{width * 0.15:.1f}" fill="none" stroke="{line}" stroke-width="2"/>'
        f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="3" fill="{line}"/>'
        f'<rect x="{(width - box_w) / 2:.1f}" y="2" width="{box_w:.1f}" height="{box_h:.1f}" fill="none" stroke="{line}" stroke-width="2"/>'
        f'<rect x="{(width - six_w) / 2:.1f}" y="2" width="{six_w:.1f}" height="{six_h:.1f}" fill="none" stroke="{line}" stroke-width="2"/>'
        f'<rect x="{(width - box_w) / 2:.1f}" y="{height - 2 - box_h:.1f}" width="{box_w:.1f}" height="{box_h:.1f}" fill="none" stroke="{line}" stroke-width="2"/>'
        f'<rect x="{(width - six_w) / 2:.1f}" y="{height - 2 - six_h:.1f}" width="{six_w:.1f}" height="{six_h:.1f}" fill="none" stroke="{line}" stroke-width="2"/>'
    )


def _role_score_color(score: float) -> str:
    # Same thresholds as roles.py's capable/strong/elite bands, same
    # palette as the semantic table tags — one color language throughout.
    if score >= 75:
        return "#0ca30c"
    if score >= 70:
        return CATEGORICAL_BLUE
    if score >= 60:
        return "#fab219"
    return "#d03b3b"


def _pitch_diagram(shape: dict) -> str:
    top_xi = shape.get("top_xi")
    if not top_xi:
        return ""
    width, height = 560, 720

    def px(x: float, y: float) -> tuple[float, float]:
        return (x / 100) * width, (y / 100) * height

    markers = []
    for slot, (name, role, score) in top_xi.items():
        coord = SLOT_COORDS.get(slot, (50, 50))
        x, y = px(*coord)
        marker_color = _role_score_color(score)
        markers.append(
            f'<g>'
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="15" fill="{marker_color}" stroke="#fff" stroke-width="2"/>'
            f'<text x="{x:.1f}" y="{y + 4:.1f}" text-anchor="middle" font-size="9.5" fill="#fff" '
            f'font-weight="700">{html_lib.escape(slot)}</text>'
            f'<rect x="{x - 48:.1f}" y="{y + 19:.1f}" width="96" height="17" rx="8.5" fill="rgba(255,255,255,0.95)"/>'
            f'<text x="{x:.1f}" y="{y + 31:.1f}" text-anchor="middle" font-size="10.5" fill="#0b0b0b" '
            f'font-weight="600">{html_lib.escape(name)}</text>'
            f'</g>'
        )

    return (
        f'<div class="chart"><div class="chart-title">Best XI — {html_lib.escape(shape["top_formation"])}</div>'
        f'<svg viewBox="0 0 {width} {height}" width="100%" style="max-width:420px" role="img" '
        f'aria-label="Best XI on the pitch">'
        f'{_pitch_background(width, height)}'
        f'{"".join(markers)}</svg></div>'
    )


def _chart_formation_viability(analysis: "SquadAnalysis") -> str:
    viability = analysis.shape_analysis["viability"]
    items = [(r["formation"], f"{r['total_score']:.0f}") for r in viability]
    return _leaderboard(items, title="Formation viability — best XI total score")


def _headline_stat_tiles(analysis: "SquadAnalysis") -> str:
    """KPI strip under the masthead — report_v2.html's reference (report-
    restructure.md stage 6), ported to this project's existing tile
    component (just adding the sub-line it didn't have before) rather than
    rebuilding it. Every figure here already exists elsewhere in the
    report; this is a glance-level summary, not a new computation.
    """
    h = analysis.headline_facts
    wage = analysis.wage_analysis
    shape = analysis.shape_analysis
    audit = analysis.squad_audit

    weak = len(shape.get("top_xi_structural_weaknesses") or [])
    tiles = [
        (
            "Squad", str(h["total_players"]),
            f"{h['available_count']} available · {len(h['injured'])} injured",
        ),
        (
            "Wage bill", _fmt_money(wage["total_weekly"]) + "/w",
            f"{', '.join(wage['position_cost_flagged'])} flagged" if wage.get("position_cost_flagged") else "",
        ),
        (
            "Best XI score", f"{shape['top_xi_total_score']:.0f}",
            f"{shape['top_formation']} · avg {shape['top_xi_avg_score']:.1f} · {weak} weak slot{'s' if weak != 1 else ''}",
        ),
    ]

    style_fit = analysis.tactical_style_fit
    if style_fit:
        counts = style_fit["tier_counts"]
        elite = counts.get("Does very well", 0)
        well = counts.get("Does well", 0)
        not_well = sum(v for k, v in counts.items() if k not in ("Does very well", "Does well"))
        tiles.append((
            "Elite fits", str(elite),
            f"{well} do well · {not_well} don't",
        ))

    wb = analysis.window_budget or {}
    if wb.get("available_transfer_budget") is not None:
        pct = 0
        if wb.get("priority_cost_high") and wb["available_transfer_budget"]:
            pct = round(min(wb["priority_cost_high"] / wb["available_transfer_budget"], 1.0) * 100)
        tiles.append((
            "Available", _fmt_money(wb["available_transfer_budget"]),
            f"{_fmt_money(wb['priority_cost_high'])} costed · {pct}% used" if wb.get("priority_cost_high") else "",
        ))
    elif wb.get("transfer_budget") is not None:
        tiles.append(("Transfer budget", _fmt_money(wb["transfer_budget"]), ""))
    elif audit.get("total_value_created") is not None:
        tiles.append(("Value created", _fmt_money(audit["total_value_created"]), ""))

    return _stat_tiles(tiles)


def _truncate(text: str, limit: int = 70) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + "…"


def _exec_summary_rows(analysis: "SquadAnalysis") -> list[tuple[str, str, str]]:
    # Deterministic, computed straight from already-analyzed data — never
    # from LLM prose — so this looks and behaves identically in free mode
    # and full mode, same as every _chart_* function below.
    rows: list[tuple[str, str, str]] = []

    shape = analysis.shape_analysis
    weak = shape.get("top_xi_structural_weaknesses") or []
    shape_verdict = (
        f"{shape['top_formation']} suits this squad best — {', '.join(weak)} still exposed"
        if weak else f"{shape['top_formation']} suits this squad best — no structural weak slots"
    )
    rows.append(("Shape", shape_verdict, "4-the-shape"))

    tactical = analysis.tactical_impossibilities
    risk_verdict = tactical[0]["flag"].capitalize() if tactical else "No tactical impossibilities flagged"
    rows.append(("Biggest risk", risk_verdict, "5-what-this-squad-cannot-do"))

    outliers = analysis.wage_analysis.get("wage_outliers") or []
    if outliers:
        top = outliers[0]
        wage_verdict = f"{top['player']} — {_fmt_money(top['wage'])}/w on a {top['best_role_score']:.1f} {top['best_role']}"
    else:
        wage_verdict = "No major wage outliers flagged"
    rows.append(("Wage flag", wage_verdict, "7-the-money"))

    exits = analysis.exit_candidates
    if exits:
        top = exits[0]
        sell_verdict = f"{top['player']} — {', '.join(top['reasons']) or 'flagged for exit'}"
    else:
        sell_verdict = "No exit candidates flagged"
    rows.append(("Top sell", _truncate(sell_verdict), "9-targets"))

    recruitment = analysis.recruitment_priorities
    if recruitment:
        top = recruitment[0]
        need = top["rationale"].split(" — ")[0]
        buy_verdict = f"{top['role']} — {need}"
    else:
        buy_verdict = "No recruitment priorities flagged"
    rows.append(("Top buy", _truncate(buy_verdict), "9-targets"))

    wb = analysis.window_budget or {}
    if wb.get("transfer_budget") is not None or wb.get("wage_budget") is not None:
        if wb.get("reconciliation") is not None:
            sign = "headroom" if wb["reconciliation"] >= 0 else "shortfall"
            budget_verdict = f"{_fmt_money(abs(wb['reconciliation']))} {sign} against costed priorities"
        else:
            budget_verdict = f"{_fmt_money(wb.get('transfer_budget') or 0)} transfer budget set — priority costs not known yet"
        rows.append(("Budget", budget_verdict, "9-targets"))

    return rows


def _render_exec_summary(analysis: "SquadAnalysis") -> str:
    rows = _exec_summary_rows(analysis)
    if not rows:
        return ""
    rows_html = "".join(
        f'<a class="es-row" href="#{anchor}">'
        f'<div class="es-label">{html_lib.escape(label)}</div>'
        f'<div class="es-verdict">{html_lib.escape(verdict)}</div>'
        f'</a>'
        for label, verdict, anchor in rows
    )
    return f'<div class="exec-summary"><div class="es-title">At a glance</div>{rows_html}</div>'


def _chart_style_fit(style_fit: dict) -> str:
    counts = style_fit["tier_counts"]
    data = [(label, float(n), STATUS_COLORS[label]) for label, n in counts.items()]
    return _svg_bar_chart(
        data, title=f"Style-fit distribution — {style_fit['style_label']}", value_suffix=" players"
    )


def _chart_wage_distribution(analysis: "SquadAnalysis") -> str:
    position_cost = analysis.wage_analysis["position_cost"]
    data = [(group.capitalize(), float(v), CATEGORICAL_BLUE) for group, v in position_cost.items()]
    return _svg_bar_chart(
        data, title="Weekly wage cost by position group", value_fmt=lambda v: f"£{v:,.0f}"
    )


def _chart_budget_allocation(analysis: "SquadAnalysis") -> str:
    """A ranked spend plan, visualising numbers that are already computed
    (window_budget, recruitment_priorities' cost ceilings) rather than
    inventing new ones. Deliberately reuses the same conservative basis
    (priority_cost_high, the reconciliation figure) the prose budget block
    in Section 7 already uses, so this chart can never show a different
    story than the text sitting right next to it.
    """
    wb = analysis.window_budget or {}
    transfer_budget = wb.get("transfer_budget")
    priority_cost_high = wb.get("priority_cost_high")
    if transfer_budget is None or priority_cost_high is None:
        return ""

    # Same pool the prose reconciliation line uses (budget + low-end exit
    # proceeds when known) — never the raw transfer budget alone, or the bar
    # could show "over budget" while the headroom figure right next to it
    # says otherwise.
    spend_pool = wb.get("available_transfer_budget") or transfer_budget

    costed = [r for r in analysis.recruitment_priorities if r.get("cost_ceiling")]
    if not costed:
        return ""

    rows_html = []
    for i, r in enumerate(costed, start=1):
        ceiling = r["cost_ceiling"]
        rows_html.append(
            "<tr>"
            f'<td style="color:{INK_MUTED};">#{i}</td>'
            f"<td>{html_lib.escape(r['role'])}</td>"
            f"<td style=\"color:{INK_SECONDARY};font-size:12.5px;\">{html_lib.escape(r['rationale'])}</td>"
            f'<td style="font-weight:600;">{_fmt_money(ceiling["low"])}–{_fmt_money(ceiling["high"])}</td>'
            "</tr>"
        )
    table_html = (
        '<div class="table-wrap"><table><thead><tr>'
        "<th>#</th><th>Role</th><th>Rationale</th><th>Cost ceiling</th>"
        f"</tr></thead><tbody>{''.join(rows_html)}</tbody></table></div>"
    )

    utilisation_pct = max(min(priority_cost_high / spend_pool, 1.0), 0.0) * 100 if spend_pool else 0
    reconciliation = wb.get("reconciliation")
    over_budget = reconciliation is not None and reconciliation < 0
    bar_color = "#d03b3b" if over_budget else CATEGORICAL_BLUE
    remaining_label = "Shortfall" if over_budget else "Headroom"
    remaining_value = _fmt_money(abs(reconciliation)) if reconciliation is not None else "unknown"
    remaining_color = "#d03b3b" if over_budget else "#0ca30c"

    summary_html = (
        '<div class="budget-summary">'
        f'<div class="budget-summary-item"><div class="budget-summary-label">Costed (worst case)</div>'
        f'<div class="budget-summary-value">{_fmt_money(priority_cost_high)}</div></div>'
        '<div class="budget-summary-bar-wrap">'
        f'<div class="budget-summary-label">Utilisation — {_fmt_money(spend_pool)} available</div>'
        '<div class="budget-bar-track">'
        f'<div class="budget-bar-fill" style="width:{utilisation_pct:.0f}%;background:{bar_color};"></div>'
        "</div>"
        f'<div class="budget-summary-label">{utilisation_pct:.0f}% of budget</div>'
        "</div>"
        f'<div class="budget-summary-item"><div class="budget-summary-label">{remaining_label}</div>'
        f'<div class="budget-summary-value" style="color:{remaining_color};">{remaining_value}</div></div>'
        "</div>"
    )

    return (
        '<div class="chart"><div class="chart-title">Budget allocation — ranked spend plan</div>'
        f"{table_html}{summary_html}</div>"
    )


def _chart_age_profile(analysis: "SquadAnalysis") -> str:
    counts = analysis.age_profile["bucket_counts"]
    order = ["U21", "21-24", "25-28", "29-32", "33+"]
    data = [(band, float(counts.get(band, 0)), CATEGORICAL_BLUE) for band in order]
    return _svg_bar_chart(data, title="Squad headcount by age band", value_suffix=" players")


def _chart_strategic_outlook(analysis: "SquadAnalysis") -> str:
    """Compact 3-card visual for Section 9's forward look — this window,
    next window, 12-month view — built straight from
    analyzer._strategic_outlook, no new figures of its own. Supplements the
    prose card already there, same additive pattern as every other chart.
    """
    outlook = analysis.strategic_outlook
    if not outlook:
        return ""

    def priority_items(rows: list[dict]) -> str:
        return "".join(
            '<div class="outlook-item"><div class="outlook-item-role">'
            f'{html_lib.escape(r["role"])} '
            f'<span style="color:{INK_MUTED};font-weight:400;">({html_lib.escape(r["slot"])})</span>'
            "</div></div>"
            for r in rows
        )

    this_window = outlook.get("this_window") or []
    next_window = outlook.get("next_window") or []
    aging = outlook.get("aging_positions") or []
    youth = outlook.get("youth_pipeline_positions") or []

    this_html = priority_items(this_window) or '<div class="outlook-empty">No recruitment priorities identified.</div>'
    if not outlook.get("has_budget"):
        next_html = '<div class="outlook-empty">Not yet knowable — no transfer budget set.</div>'
    else:
        next_html = priority_items(next_window) or '<div class="outlook-empty">Nothing deferred — budget covers everything costed.</div>'

    twelve_parts = []
    if aging:
        twelve_parts.append(
            '<div class="outlook-item"><div class="outlook-item-role">Aging: '
            f'{html_lib.escape(", ".join(aging))}</div></div>'
        )
    if youth:
        twelve_parts.append(
            '<div class="outlook-item"><div class="outlook-item-role">Pipeline cover: '
            f'{html_lib.escape(", ".join(youth))}</div></div>'
        )
    twelve_html = "".join(twelve_parts) or '<div class="outlook-empty">No material aging or pipeline signal yet.</div>'

    cards = [("This window", this_html), ("Next window", next_html), ("12-month view", twelve_html)]
    cards_html = "".join(
        f'<div class="outlook-card"><div class="outlook-card-title">{title}</div>{body}</div>'
        for title, body in cards
    )
    return (
        '<div class="chart"><div class="chart-title">Strategic outlook — three horizons</div>'
        f'<div class="outlook-grid">{cards_html}</div></div>'
    )


def _chart_league_comparison(style_fit: dict) -> str:
    league_ctx = style_fit.get("league_context")
    if not league_ctx:
        return ""
    abs_counts = style_fit["tier_counts"]
    league_counts = {label: 0 for label in tactics.TIER_LABELS.values()}
    for entry in league_ctx["player_scores"]:
        league_tier = entry[-1]
        if league_tier in league_counts:
            league_counts[league_tier] += 1

    abs_data = [(label, float(n), STATUS_COLORS[label]) for label, n in abs_counts.items()]
    league_data = [(label, float(n), STATUS_COLORS[label]) for label, n in league_counts.items()]
    return (
        '<div class="chart-pair">'
        + _svg_bar_chart(abs_data, title="Absolute scale", width=320)
        + _svg_bar_chart(league_data, title="League-relative", width=320)
        + "</div>"
    )


def _chart_style_fit_percentiles(style_fit: dict) -> str:
    """Per-player league-percentile bars with a median rule (report_v2.html's
    Section 8 reference) — CSS bars, not SVG, matching that reference's own
    construction. Reuses league_ctx["player_scores"] directly; no new
    scoring. A bar below the 50th-percentile median gets the "weak" fill —
    same "league-relative is authoritative" framing _render_style_fit
    already states in the markdown (stage 4c), just visualized.
    """
    league_ctx = style_fit.get("league_context")
    if not league_ctx:
        return ""
    rows = [
        (name, position_group, pct)
        for name, position_group, _score, _tier, pct, _league_tier in league_ctx["player_scores"]
        if pct is not None
    ]
    if not rows:
        return ""
    rows.sort(key=lambda r: r[2], reverse=True)

    bar_rows = []
    for name, position_group, pct in rows:
        weak = " weak" if pct < 50 else ""
        bar_rows.append(
            '<div class="bar-row">'
            f'<div>{html_lib.escape(name)} <span class="bar-pos">{html_lib.escape(position_group)}</span></div>'
            '<div class="bar-track">'
            f'<div class="bar-fill{weak}" style="width:{pct:.0f}%"></div>'
            '<div class="median" style="left:50%"></div>'
            "</div>"
            f'<div class="bar-val">{pct:.0f}th</div>'
            "</div>"
        )

    return (
        '<div class="chart"><div class="chart-title">Style-fit percentile — vs. the current league, sorted best to worst</div>'
        f'<div class="bars">{"".join(bar_rows)}'
        '<div class="legend">VERTICAL RULE = DIVISION MEDIAN</div></div></div>'
    )


def _fmt_signed_money(v: float) -> str:
    sign = "+" if v >= 0 else "-"
    return f"{sign}£{abs(v):,.0f}"


def _chart_squad_audit_tiers(audit: dict) -> str:
    if not audit.get("has_data"):
        return ""
    data = [(tier, float(n), CATEGORICAL_BLUE) for tier, n in audit["tier_counts"].items() if n]
    return _svg_bar_chart(data, title="Squad audit — tier breakdown", value_suffix=" players")


def _chart_value_created(audit: dict) -> str:
    if not audit.get("has_data") or audit.get("total_value_created") is None:
        return ""
    entries = [e for e in audit["entries"] if e["value_created"] is not None]
    entries.sort(key=lambda e: e["value_created"], reverse=True)
    top = entries[:8]
    if not top:
        return ""
    items = [(e["player"], _fmt_signed_money(e["value_created"])) for e in top]
    return _leaderboard(items, title="Value created — current value vs. purchase fee")


def _chart_target_dossier_highlights(analysis: "SquadAnalysis") -> str:
    dossier = analysis.target_dossier
    if not dossier:
        return ""
    items = []
    for entry in dossier:
        kind = entry.get("kind")
        if kind == "succession":
            # The succession plan is a 30-row contingency index, not a set
            # of "worth pursuing" picks — including it here would bury the
            # real top picks from the other 4 categories in noise.
            continue
        candidates = entry.get("candidates")
        if not candidates:
            continue
        top = candidates[0]
        if kind in ("exit_replacement_listed", "exit_replacement_valuable"):
            label = f"{top['player']} — for {entry['slot']}"
        elif kind == "value_opportunity":
            label = f"{top['player']} — {entry['rationale']}"
        else:
            label = f"{top['player']} — {entry['role']}"
        items.append((label, f"{top['role_score']:.1f}"))
    return _leaderboard(items, title="Target Dossier — top pick per need")


def _entry_group_label(entry: dict) -> str:
    kind = entry.get("kind")
    if kind == "exit_replacement_listed":
        return f"If {entry['slot']} leaves (transfer-listed)"
    if kind == "exit_replacement_valuable":
        return f"If we sell {entry['slot']}"
    if kind == "value_opportunity":
        return f"Market opportunity: {entry['slot']}"
    return f"{entry['role']} — {entry['slot']}"


def _chart_target_dossier_radars(analysis: "SquadAnalysis") -> str:
    """Supplements (doesn't replace) Target Dossier's existing candidate
    tables with a visual attribute profile per candidate — built directly
    from analysis.target_dossier, same additive-injection pattern as every
    other chart, so report.py's markdown (the LLM's data feed, and free
    mode's plain tables) is completely untouched by this."""
    dossier = analysis.target_dossier
    if not dossier:
        return ""

    groups = []
    for entry in dossier:
        if entry.get("kind") == "succession":
            # 30 players x 4 radars would bury the handful of real,
            # worth-a-visual-profile candidates from the other 4 categories —
            # the succession plan gets its own compact table instead (see
            # report.py's _render_succession_plan).
            continue
        candidates = entry.get("candidates")
        if not candidates:
            continue
        ideal = roles.ideal_attribute_values(entry["role"])
        if not ideal:
            continue
        attr_labels = list(ideal.keys())
        ideal_vals = [ideal[a] for a in attr_labels]

        cards = []
        for c in candidates:
            attrs = c.get("attributes") or {}
            actual_vals = [attrs.get(a, 0) for a in attr_labels]
            radar_svg = _svg_radar(attr_labels, actual_vals, ideal_vals)
            stretch_note = ' <span style="color:#d03b3b;font-size:10px;">(stretch)</span>' if c.get("stretch_target") else ""
            cards.append(
                '<div class="radar-card">'
                f'<div class="radar-card-name">{html_lib.escape(c["player"])}{stretch_note}</div>'
                f'<div class="radar-card-score">{c["role_score"]:.1f} role fit</div>'
                f'{radar_svg}'
                '</div>'
            )
        if not cards:
            continue
        groups.append(
            f'<div class="radar-group"><div class="radar-group-title">{html_lib.escape(_entry_group_label(entry))}</div>'
            f'<div class="radar-grid">{"".join(cards)}</div></div>'
        )

    if not groups:
        return ""
    return (
        '<div class="chart"><div class="chart-title">Candidate attribute profiles vs. role benchmark '
        '(solid = candidate, dashed = role ideal)</div>'
        f'{"".join(groups)}</div>'
    )


def _exit_replacement_pairs(analysis: "SquadAnalysis") -> list[tuple[dict, dict]]:
    """(exit_candidate, top_replacement_candidate) for every exit that has a
    replacement case — the same pairing Target Dossier's "Replacement case"
    entries already represent, just matched back to the exit's own data."""
    dossier = analysis.target_dossier or []
    exits_by_name = {e["player"]: e for e in analysis.exit_candidates}
    pairs = []
    for entry in dossier:
        if entry.get("kind") not in ("exit_replacement_listed", "exit_replacement_valuable"):
            continue
        candidates = entry.get("candidates")
        exiting = exits_by_name.get(entry["slot"])
        if not candidates or not exiting:
            continue
        pairs.append((exiting, candidates[0]))
    return pairs


def _chart_ins_and_outs_pairing(analysis: "SquadAnalysis") -> str:
    pairs = _exit_replacement_pairs(analysis)
    if not pairs:
        return ""
    items = []
    for exiting, incoming in pairs:
        if incoming["value_low"] is not None:
            value = f"{_fmt_money(incoming['value_low'])}-{_fmt_money(incoming['value_high'])}"
        else:
            value = f"{incoming['role_score']:.1f}"
        items.append((f"{exiting['player']} → {incoming['player']}", value))
    return _leaderboard(items, title="Ins & outs — who covers who")


def _chart_ins_outs_comparison(analysis: "SquadAnalysis") -> str:
    pairs = _exit_replacement_pairs(analysis)
    if not pairs:
        return ""
    data = []
    for exiting, incoming in pairs:
        data.append((f"{exiting['player']} (out)", exiting["best_role_score"], "#d03b3b"))
        data.append((f"{incoming['player']} (in)", incoming["role_score"], "#0ca30c"))
    return _svg_bar_chart(data, title="Role-fit — outgoing vs. incoming")


def _inject_chart(body_html: str, anchor_id: str, chart_html: str) -> str:
    if not chart_html:
        return body_html
    pattern = rf'(<h[23] id="{re.escape(anchor_id)}">.*?</h[23]>)'
    return re.sub(pattern, lambda m: m.group(1) + chart_html, body_html, count=1)


def _build_toc(body_md: str) -> str:
    links = []
    for line in body_md.split("\n"):
        m = re.match(r"^##\s+(.*)$", line.strip())
        if m:
            text = m.group(1)
            links.append(f'<a href="#{_slugify(text)}">{html_lib.escape(text)}</a>')
    return "".join(links)


# ---------------------------------------------------------------------------
# Page template
# ---------------------------------------------------------------------------

PAGE_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  :root {{
    --surface: {surface}; --page: {page}; --ink-primary: {ink_primary};
    --ink-secondary: {ink_secondary}; --ink-muted: {ink_muted};
    --gridline: {gridline}; --border: {border};
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; background: var(--page); color: var(--ink-primary);
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
    line-height: 1.6;
  }}
  .page {{ max-width: 900px; margin: 0 auto; padding: 40px 24px 80px; }}
  header.banner {{
    background: var(--surface); border: 1px solid var(--border); border-radius: 8px;
    padding: 28px 32px; margin-bottom: 24px;
  }}
  header.banner h1 {{ margin: 0 0 6px; font-size: 24px; }}
  header.banner .meta {{ color: var(--ink-secondary); font-size: 13px; }}
  nav.toc {{
    background: var(--surface); border: 1px solid var(--border); border-radius: 8px;
    padding: 14px 22px; margin-bottom: 28px; font-size: 13.5px;
  }}
  nav.toc a {{ color: var(--ink-secondary); text-decoration: none; margin-right: 14px; display: inline-block; }}
  nav.toc a:hover {{ color: var(--ink-primary); text-decoration: underline; }}
  section {{
    background: var(--surface); border: 1px solid var(--border); border-radius: 8px;
    padding: 26px 32px; margin-bottom: 18px;
  }}
  h2 {{ font-size: 18px; margin-top: 0; border-bottom: 1px solid var(--gridline); padding-bottom: 10px; }}
  h3 {{ font-size: 15px; color: var(--ink-secondary); }}
  p {{ margin: 0 0 14px; }}
  ul, ol {{ margin: 0 0 14px; padding-left: 20px; }}
  li {{ margin-bottom: 4px; }}
  strong {{ color: var(--ink-primary); }}
  .table-wrap {{ overflow-x: auto; margin: 14px 0; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
  th, td {{ text-align: left; padding: 7px 12px; border-bottom: 1px solid var(--gridline); white-space: nowrap; }}
  th {{ color: var(--ink-secondary); font-weight: 600; }}
  hr {{ border: none; border-top: 1px solid var(--gridline); margin: 18px 0; }}
  .chart {{ margin: 16px 0 22px; }}
  .chart-title {{ font-size: 12.5px; color: var(--ink-muted); margin-bottom: 6px; }}
  .chart-pair {{ display: flex; gap: 24px; flex-wrap: wrap; }}
  .chart-pair .chart {{ flex: 1 1 260px; }}
  .radar-group {{ margin: 14px 0 20px; }}
  .radar-group-title {{ font-size: 12.5px; color: var(--ink-secondary); font-weight: 600; margin-bottom: 10px; }}
  .radar-grid {{ display: flex; gap: 16px; flex-wrap: wrap; }}
  .radar-card {{
    background: var(--surface); border: 1px solid var(--border); border-radius: 8px;
    padding: 12px; text-align: center; flex: 0 0 200px;
  }}
  .radar-card-name {{ font-size: 12.5px; font-weight: 600; color: var(--ink-primary); margin-bottom: 1px; }}
  .radar-card-score {{ font-size: 11px; color: var(--ink-secondary); margin-bottom: 4px; }}
  .budget-summary {{
    display: flex; align-items: flex-end; gap: 24px; margin-top: 14px;
    background: var(--surface); border: 1px solid var(--border); border-radius: 8px;
    padding: 16px 20px; flex-wrap: wrap;
  }}
  .budget-summary-item {{ flex: 0 0 auto; }}
  .budget-summary-bar-wrap {{ flex: 1 1 200px; min-width: 160px; }}
  .budget-summary-label {{
    font-size: 11px; color: var(--ink-muted); text-transform: uppercase; letter-spacing: 0.04em;
    margin-bottom: 4px;
  }}
  .budget-summary-value {{ font-size: 19px; font-weight: 700; color: var(--ink-primary); }}
  .budget-bar-track {{
    height: 8px; border-radius: 4px; background: var(--gridline); overflow: hidden; margin: 4px 0;
  }}
  .budget-bar-fill {{ height: 100%; border-radius: 4px; }}
  .outlook-grid {{ display: flex; gap: 14px; flex-wrap: wrap; }}
  .outlook-card {{
    background: var(--surface); border: 1px solid var(--border); border-radius: 8px;
    padding: 14px 16px; flex: 1 1 200px; min-width: 180px;
  }}
  .outlook-card-title {{
    font-size: 11.5px; color: var(--ink-muted); text-transform: uppercase; letter-spacing: 0.04em;
    font-weight: 600; margin-bottom: 8px;
  }}
  .outlook-item {{ padding: 5px 0; border-top: 1px solid var(--gridline); }}
  .outlook-item:first-of-type {{ border-top: none; }}
  .outlook-item-role {{ font-size: 12.5px; color: var(--ink-primary); font-weight: 600; }}
  .outlook-empty {{ font-size: 12.5px; color: var(--ink-secondary); }}
  .stat-strip {{
    display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 24px;
  }}
  .stat-tile {{
    background: var(--surface); border: 1px solid var(--border); border-radius: 8px;
    padding: 18px 14px; text-align: center;
  }}
  .stat-value {{ font-size: 23px; font-weight: 700; color: var(--ink-primary); line-height: 1.2; }}
  .stat-label {{
    font-size: 11.5px; color: var(--ink-secondary); margin-top: 5px;
    text-transform: uppercase; letter-spacing: 0.04em;
  }}
  .stat-sub {{ font-size: 11.5px; color: var(--ink-muted); margin-top: 2px; }}
  .bars {{ margin: 12px 0 4px; }}
  .bar-row {{
    display: grid; grid-template-columns: 160px 1fr 44px; align-items: center; gap: 10px;
    font-size: 12.5px; padding: 3px 0; color: var(--ink-secondary);
  }}
  .bar-pos {{ color: var(--ink-muted); font-size: 11px; }}
  .bar-track {{ background: var(--gridline); height: 9px; border-radius: 2px; position: relative; }}
  .bar-fill {{ background: {categorical_blue}; height: 9px; border-radius: 2px; }}
  .bar-fill.weak {{ background: #d03b3b; }}
  .bar-val {{ font-size: 11.5px; color: var(--ink-secondary); text-align: right; }}
  .median {{ position: absolute; top: -3px; bottom: -3px; width: 1px; background: var(--ink-primary); opacity: 0.55; }}
  .legend {{
    font-size: 11px; color: var(--ink-muted); margin-top: 8px;
    text-transform: uppercase; letter-spacing: 0.04em;
  }}
  .leaderboard {{ background: #14141c; border-radius: 10px; padding: 18px 22px; margin: 16px 0 22px; }}
  .lb-title {{
    font-size: 12px; color: #9a99a8; margin-bottom: 10px;
    text-transform: uppercase; letter-spacing: 0.04em;
  }}
  .lb-row {{
    display: flex; align-items: center; gap: 14px; padding: 8px 0;
    border-bottom: 1px solid rgba(255,255,255,0.08);
  }}
  .lb-row:last-child {{ border-bottom: none; }}
  .lb-rank {{
    width: 24px; height: 24px; border-radius: 50%; background: {categorical_blue}; color: #fff;
    display: flex; align-items: center; justify-content: center;
    font-size: 12px; font-weight: 700; flex-shrink: 0;
  }}
  .lb-name {{ flex: 1; color: #fff; font-size: 13.5px; font-weight: 600; }}
  .lb-value {{
    background: #fff; color: #14141c; font-weight: 700; font-size: 12.5px;
    padding: 4px 13px; border-radius: 999px;
  }}
  .exec-summary {{ background: #14141c; border-radius: 10px; padding: 18px 22px; margin-bottom: 28px; }}
  .es-title {{
    font-size: 12px; color: #9a99a8; margin-bottom: 10px;
    text-transform: uppercase; letter-spacing: 0.04em;
  }}
  .es-row {{
    display: flex; align-items: baseline; gap: 16px; padding: 9px 0;
    border-bottom: 1px solid rgba(255,255,255,0.08);
    text-decoration: none; color: inherit;
  }}
  .es-row:last-child {{ border-bottom: none; }}
  .es-label {{
    flex: 0 0 110px; font-size: 11.5px; color: #9a99a8; font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.03em;
  }}
  .es-verdict {{ flex: 1; color: #fff; font-size: 13.5px; }}
  .es-row:hover .es-verdict {{ text-decoration: underline; }}
  .tag {{
    display: inline-block; padding: 2px 10px; border-radius: 999px;
    font-size: 11.5px; font-weight: 600; color: #fff; white-space: nowrap;
  }}
  details {{ margin: 14px 0; }}
  details summary {{
    cursor: pointer; font-weight: 600; color: var(--ink-secondary); font-size: 13.5px;
    padding: 4px 0;
  }}
  details summary:hover {{ color: var(--ink-primary); }}
  details[open] summary {{ margin-bottom: 4px; }}
  section.accent-decision {{ border-left: 3px solid var(--ink-primary); }}
  section.accent-recruitment {{ border-left: 3px solid {categorical_blue}; }}
  section.accent-audit {{ border-left: 3px solid #7a5cd6; }}
  section.accent-dossier {{ border-left: 3px solid #0ca30c; }}
  @media (max-width: 640px) {{
    .stat-strip {{ grid-template-columns: repeat(2, 1fr); }}
    .es-row {{ flex-direction: column; gap: 2px; }}
    .es-label {{ flex: none; }}
  }}
  @media print {{
    body {{ background: white; }}
    section {{ break-inside: avoid; box-shadow: none; }}
    nav.toc {{ display: none; }}
    .leaderboard {{ background: white; border: 1px solid var(--border); }}
    .lb-name {{ color: var(--ink-primary); }}
    .lb-title {{ color: var(--ink-secondary); }}
    .exec-summary {{ background: white; border: 1px solid var(--border); }}
    .es-verdict {{ color: var(--ink-primary); }}
    .es-label, .es-title {{ color: var(--ink-secondary); }}
  }}
</style>
</head>
<body>
<div class="page">
<header class="banner">
  <h1>{title}</h1>
  <div class="meta">FM Save Copilot — Director of Football briefing</div>
</header>
{stats}
{exec_summary}
<nav class="toc">{toc}</nav>
{body}
</div>
<script>
// <details> content is hidden by the browser regardless of author CSS
// unless the `open` attribute is set — force it open for printing (Print
// to PDF is a documented usage path) and restore the on-screen state after.
window.addEventListener("beforeprint", () => {{
  document.querySelectorAll("details").forEach(d => {{ d.dataset.wasOpen = d.open; d.open = true; }});
}});
window.addEventListener("afterprint", () => {{
  document.querySelectorAll("details").forEach(d => {{ d.open = d.dataset.wasOpen === "true"; }});
}});
</script>
</body>
</html>
"""


# A subtle left-border accent on the "decision" sections only — not a
# full 12-color rainbow, which would look busy rather than clear.
# v2 schema (report-restructure.md stage 6) — Section 2 (the decision
# board) gets its own accent since it's the section everything else exists
# to justify; Exits and Development Pipeline no longer have separate
# sections (merged into Targets and Housekeeping respectively), so those
# two old accent keys are retired along with them.
SECTION_ACCENTS = {
    "2-the-window": "accent-decision",
    "9-targets": "accent-recruitment",
    "10-housekeeping": "accent-audit",
    "target-dossier": "accent-dossier",
}


def _wrap_sections(body_html: str) -> str:
    # Split right before each section heading. Anything before the first
    # heading (e.g. a stray "---" separator some models add after the title)
    # isn't a real section, so it's dropped rather than wrapped as an empty card.
    parts = re.split(r"(?=<h2 )", body_html)
    out = []
    for part in parts:
        part = part.strip()
        if not part.startswith("<h2"):
            continue
        m = re.match(r'<h2 id="([^"]+)"', part)
        accent = SECTION_ACCENTS.get(m.group(1)) if m else None
        cls = f' class="{accent}"' if accent else ""
        out.append(f"<section{cls}>{part}</section>")
    return "\n".join(out)


def generate_html_report(markdown_text: str, analysis: "SquadAnalysis") -> str:
    lines = markdown_text.split("\n", 1)
    title = lines[0].lstrip("#").strip() if lines and lines[0].startswith("#") else "FM Save Copilot Report"
    body_md = lines[1] if len(lines) > 1 else markdown_text

    body_html = markdown_to_html(body_md)

    style_fit = analysis.tactical_style_fit
    charts_by_anchor: dict[str, str] = {}

    def add_chart(anchor: str, chart_html: str) -> None:
        if chart_html:
            charts_by_anchor[anchor] = charts_by_anchor.get(anchor, "") + chart_html

    # v2 schema anchors (report-restructure.md stage 6) — every anchor below
    # must match a heading id the new 10-section template actually produces,
    # or add_chart is a silent no-op (this is exactly what broke in stages
    # 1-5: charts kept the old anchors while the headings moved).
    add_chart("4-the-shape", _pitch_diagram(analysis.shape_analysis))
    add_chart("4-the-shape", _chart_formation_viability(analysis))
    if style_fit:
        add_chart("4-the-shape", _chart_style_fit(style_fit))
    add_chart("7-the-money", _chart_wage_distribution(analysis))
    if analysis.squad_audit.get("has_data"):
        add_chart("7-the-money", _chart_value_created(analysis.squad_audit))
    if style_fit and style_fit.get("league_context"):
        add_chart("8-against-the-division", _chart_style_fit_percentiles(style_fit))
    add_chart("9-targets", _chart_budget_allocation(analysis))
    if analysis.target_dossier:
        add_chart("9-targets", _chart_ins_and_outs_pairing(analysis))
        add_chart("9-targets", _chart_ins_outs_comparison(analysis))
        add_chart("target-dossier", _chart_target_dossier_highlights(analysis))
        add_chart("target-dossier", _chart_target_dossier_radars(analysis))
    if analysis.squad_audit.get("has_data"):
        add_chart("10-housekeeping", _chart_squad_audit_tiers(analysis.squad_audit))
    add_chart("10-housekeeping", _chart_age_profile(analysis))

    for anchor, chart_html in charts_by_anchor.items():
        body_html = _inject_chart(body_html, anchor, chart_html)

    body_html = _wrap_sections(body_html)
    toc_html = _build_toc(body_md)
    stats_html = _headline_stat_tiles(analysis)
    exec_summary_html = _render_exec_summary(analysis)

    return PAGE_TEMPLATE.format(
        title=html_lib.escape(title), toc=toc_html, body=body_html, stats=stats_html,
        exec_summary=exec_summary_html,
        surface=SURFACE, page=PAGE, ink_primary=INK_PRIMARY, ink_secondary=INK_SECONDARY,
        ink_muted=INK_MUTED, gridline=GRIDLINE, border=BORDER, categorical_blue=CATEGORICAL_BLUE,
    )
