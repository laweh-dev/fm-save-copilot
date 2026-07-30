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
import re
from typing import TYPE_CHECKING, Callable, Optional

from fm_copilot import tactics

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


def _render_table(table_lines: list[str]) -> str:
    rows = [[c.strip() for c in line.strip("|").split("|")] for line in table_lines]
    if len(rows) >= 2 and all(re.match(r"^:?-+:?$", c) for c in rows[1]):
        header, body = rows[0], rows[2:]
    else:
        header, body = rows[0], rows[1:]

    thead = "".join(f"<th>{_inline_md(c)}</th>" for c in header)
    tbody = "".join(
        "<tr>" + "".join(f"<td>{_inline_md(c)}</td>" for c in row) + "</tr>"
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


def _stat_tiles(tiles: list[tuple[str, str]]) -> str:
    cells = "".join(
        f'<div class="stat-tile"><div class="stat-value">{html_lib.escape(value)}</div>'
        f'<div class="stat-label">{html_lib.escape(label)}</div></div>'
        for label, value in tiles
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
        markers.append(
            f'<g>'
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="15" fill="#132a52" stroke="#fff" stroke-width="2"/>'
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
    h = analysis.headline_facts
    wage = analysis.wage_analysis
    shape = analysis.shape_analysis

    def fmt_money(n: float) -> str:
        n = float(n or 0)
        if n >= 1_000_000:
            return f"£{n / 1_000_000:.1f}M"
        if n >= 1_000:
            return f"£{n / 1_000:.0f}K"
        return f"£{n:.0f}"

    tiles = [
        ("Squad size", str(h["total_players"])),
        ("Available bodies", f"{h['available_count']}/{h['total_players']}"),
        ("Weekly wage bill", fmt_money(wage["total_weekly"])),
        ("Top formation", f"{shape['top_formation']} · {shape['top_xi_avg_score']:.0f} avg"),
    ]
    return _stat_tiles(tiles)


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


def _chart_age_profile(analysis: "SquadAnalysis") -> str:
    counts = analysis.age_profile["bucket_counts"]
    order = ["U21", "21-24", "25-28", "29-32", "33+"]
    data = [(band, float(counts.get(band, 0)), CATEGORICAL_BLUE) for band in order]
    return _svg_bar_chart(data, title="Squad headcount by age band", value_suffix=" players")


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
  ul {{ margin: 0 0 14px; padding-left: 20px; }}
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
  @media (max-width: 640px) {{
    .stat-strip {{ grid-template-columns: repeat(2, 1fr); }}
  }}
  @media print {{
    body {{ background: white; }}
    section {{ break-inside: avoid; box-shadow: none; }}
    nav.toc {{ display: none; }}
    .leaderboard {{ background: white; border: 1px solid var(--border); }}
    .lb-name {{ color: var(--ink-primary); }}
    .lb-title {{ color: var(--ink-secondary); }}
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
<nav class="toc">{toc}</nav>
{body}
</div>
</body>
</html>
"""


def _wrap_sections(body_html: str) -> str:
    # Split right before each section heading. Anything before the first
    # heading (e.g. a stray "---" separator some models add after the title)
    # isn't a real section, so it's dropped rather than wrapped as an empty card.
    parts = re.split(r"(?=<h2 )", body_html)
    return "\n".join(f"<section>{part.strip()}</section>" for part in parts if part.strip().startswith("<h2"))


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

    add_chart("2-the-shape", _pitch_diagram(analysis.shape_analysis))
    add_chart("2-the-shape", _chart_formation_viability(analysis))
    if style_fit:
        add_chart("2-the-shape", _chart_style_fit(style_fit))
    add_chart("5-the-wage-bill", _chart_wage_distribution(analysis))
    add_chart("9-what-good-looks-like", _chart_age_profile(analysis))
    if style_fit and style_fit.get("league_context"):
        add_chart("10-how-we-compare-to-the-league", _chart_league_comparison(style_fit))
    if analysis.squad_audit.get("has_data"):
        add_chart("11-squad-audit", _chart_squad_audit_tiers(analysis.squad_audit))
        add_chart("11-squad-audit", _chart_value_created(analysis.squad_audit))

    for anchor, chart_html in charts_by_anchor.items():
        body_html = _inject_chart(body_html, anchor, chart_html)

    body_html = _wrap_sections(body_html)
    toc_html = _build_toc(body_md)
    stats_html = _headline_stat_tiles(analysis)

    return PAGE_TEMPLATE.format(
        title=html_lib.escape(title), toc=toc_html, body=body_html, stats=stats_html,
        surface=SURFACE, page=PAGE, ink_primary=INK_PRIMARY, ink_secondary=INK_SECONDARY,
        ink_muted=INK_MUTED, gridline=GRIDLINE, border=BORDER, categorical_blue=CATEGORICAL_BLUE,
    )
