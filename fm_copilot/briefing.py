"""The Briefing: a 3-page A4 dashboard, replacing the old 11-section HTML
report. Fully deterministic — no LLM call, no dependency on an API key.
Every element is a chart, table, or list built directly from an already-
computed SquadAnalysis + the parsed players list.

Spec: `Useful artefacts/Claude Code Prompt - The Briefing.md`.
"""

from __future__ import annotations

import html as html_lib
import re
from typing import TYPE_CHECKING, Optional

from fm_copilot import roles
from fm_copilot.report import _decision_board_rows

if TYPE_CHECKING:
    from fm_copilot.analyzer import SquadAnalysis
    from fm_copilot.parser import Player

FONTS_LINK = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link href="https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@62..125,400..800'
    '&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">'
)

# ---------------------------------------------------------------------------
# Formatting utilities
# ---------------------------------------------------------------------------

def _ordinal(n: float) -> str:
    n = int(round(n))
    if 10 <= abs(n) % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(abs(n) % 10, "th")
    return f"{n}{suffix}"


def _fmt_money(n: Optional[float]) -> str:
    if n is None:
        return "—"
    n = float(n)
    if n == 0:
        return "Free"
    if abs(n) >= 1_000_000:
        return f"£{n / 1_000_000:.1f}M"
    if abs(n) >= 1_000:
        return f"£{n / 1_000:.0f}K"
    return f"£{n:.0f}"


def _fmt_money_range(low: Optional[float], high: Optional[float]) -> str:
    if low is None or high is None:
        return "—"
    low, high = float(low), float(high)
    if low == 0 and high == 0:
        return "Free"

    def unit(v: float) -> str:
        if v >= 1_000_000:
            return "M"
        if v >= 1_000:
            return "K"
        return ""

    ul, uh = unit(low), unit(high)
    if ul == uh and ul:
        div = 1_000_000 if ul == "M" else 1_000
        fmt = "{:.1f}" if ul == "M" else "{:.0f}"
        return f"£{fmt.format(low / div)}–{fmt.format(high / div)}{ul}"
    return f"{_fmt_money(low)}–{_fmt_money(high)}"


def _fmt_money_ceiling(n: Optional[float]) -> str:
    if n is None:
        return "—"
    return f"≤{_fmt_money(n)}"


def _esc(text: str) -> str:
    return html_lib.escape(str(text))


def _truncate_words(text: str, max_words: int) -> str:
    """Word-boundary cap for list notes (spec: 'list notes ≤ 6 words') —
    used instead of a character slice, which chops mid-word."""
    words = text.split()
    return text if len(words) <= max_words else " ".join(words[:max_words])


def pct_color(p: Optional[float]) -> str:
    """3-way colour band for a real league percentile (spec's pct(p))."""
    if p is None:
        return "var(--neutral)"
    if p >= 75:
        return "var(--buy)"
    if p >= 50:
        return "var(--neutral)"
    return "var(--sell)"


def role_score_color(score: float) -> str:
    """Fallback pitch-dot colouring when no league percentile exists —
    the project's own established role-fit bands (roles.CAPABLE_THRESHOLD
    /STRONG_THRESHOLD), not pct_color's 50/75 percentile bands. Reusing
    pct_color's bands directly on a raw role score left the pitch almost
    entirely grey (screenshot-verified: real role scores cluster 60-72,
    rarely crossing 75), since percentile and role-fit scores aren't
    actually on a matched scale despite both being ~0-100."""
    if score >= roles.STRONG_THRESHOLD:
        return "var(--buy)"
    if score >= roles.CAPABLE_THRESHOLD:
        return "var(--neutral)"
    return "var(--sell)"


def candidate_color(candidate_score: float, squad_best_score: Optional[float]) -> str:
    if squad_best_score is not None and candidate_score > squad_best_score:
        return "var(--buy)"
    return "var(--neutral)"


ACTION_CHIP_COLOR = {
    "Fix": "var(--fix)", "Fix free": "var(--fix)",
    "Buy": "var(--buy)",
    "Sell": "var(--sell)",
    "Protect": "var(--protect)", "Hold": "var(--protect)",
}
ACTION_BADGE_LETTER = {"Sell": "S", "Protect": "P", "Hold": "P", "Fix free": "F"}


def _action_chip(label: str, call_key: str) -> str:
    color = ACTION_CHIP_COLOR.get(call_key, "var(--neutral)")
    return f'<span class="chip" style="background:{color}">{_esc(label)}</span>'


# ---------------------------------------------------------------------------
# Pitch coordinates — one flat lookup across all 6 formations in
# roles.FORMATIONS, same structure as the old html_report.py SLOT_COORDS.
# Slots the spec gives exact numbers for (4-3-3) use those; every other
# slot is adapted from the prior report's coordinate system, which already
# covered every formation the tool can output.
# ---------------------------------------------------------------------------

PITCH_COORDS: dict[str, tuple[float, float]] = {
    "GK": (50, 90),
    "RB": (86, 70), "LB": (14, 70), "RCB": (63, 75), "LCB": (37, 75),
    # CB (the middle slot of a back-3, 3-5-2/3-4-3 only) sits noticeably
    # deeper than RCB/LCB — level with them caused the 30px circles and
    # 52px surname labels to overlap (screenshot-verified against the real
    # sample squad).
    "CB": (50, 85),
    "RWB": (87, 58), "LWB": (13, 58),
    "RDM": (62, 60), "LDM": (38, 60), "DM": (50, 57),
    "RCM": (74, 43), "LCM": (26, 43), "RM": (85, 45), "LM": (15, 45),
    "AM": (50, 30), "AMR": (72, 28), "AML": (28, 28),
    "RW": (82, 19), "LW": (18, 19),
    "ST": (50, 11), "RST": (60, 11), "LST": (40, 11),
}


# ---------------------------------------------------------------------------
# Page 1 — Snapshot
# ---------------------------------------------------------------------------

def _effective_shape(analysis: "SquadAnalysis") -> tuple[str, dict]:
    """Formation + XI actually drawn — the requested override when one was
    given and matched a known formation, else the analyzer's own
    top-viability pick. Mirrors analyzer._effective_formation's logic
    without importing a private cross-module function for one 3-line check."""
    shape = analysis.shape_analysis
    override = shape.get("override_formation")
    if override and override.get("matched_shape"):
        return override["matched_shape"], override["xi"]
    return shape["top_formation"], shape["top_xi"]


def _verdict(analysis: "SquadAnalysis") -> tuple[str, str]:
    formation, xi = _effective_shape(analysis)
    weak = analysis.shape_analysis.get("top_xi_structural_weaknesses") or []
    scores = [s for _n, _r, s in xi.values()]
    elite_count = sum(1 for s in scores if s >= roles.ELITE_THRESHOLD)
    strong_count = sum(1 for s in scores if s >= roles.STRONG_THRESHOLD)

    if weak:
        n = len(weak)
        title = f"{formation} works, {n} gap{'s' if n != 1 else ''} exposed"
    elif elite_count == 0:
        title = "Competitive shape, no ceiling"
    else:
        title = f"{formation} holds, ready to build"

    facts = []
    facts.append("No player rates 70+" if strong_count == 0 else f"{strong_count} player{'s' if strong_count != 1 else ''} rate 70+")

    spof = [r for r in analysis.recruitment_priorities if "single point of failure" in r["rationale"]]
    if spof:
        facts.append(f"one recognised {spof[0]['slot']} body")

    facts.append(f"{formation} exposed at {', '.join(weak)}" if weak else f"the {formation} holds with no weak slots")

    sub = ". ".join(f[0].upper() + f[1:] for f in facts[:3]) + "."
    return title, sub


def _kpi_strip(analysis: "SquadAnalysis") -> str:
    h = analysis.headline_facts
    wage = analysis.wage_analysis
    _formation, xi = _effective_shape(analysis)
    scores = [s for _n, _r, s in xi.values()]
    strong_count = sum(1 for s in scores if s >= roles.STRONG_THRESHOLD)
    avg_score = sum(scores) / len(scores) if scores else 0.0
    formation = _formation

    wb = analysis.window_budget or {}
    reconciliation = wb.get("reconciliation")
    if reconciliation is not None:
        headroom = (_fmt_money(abs(reconciliation)) + " short") if reconciliation < 0 else _fmt_money(reconciliation)
    elif wb.get("available_transfer_budget") is not None:
        headroom = _fmt_money(wb["available_transfer_budget"])
    else:
        headroom = "—"

    cols = [
        (str(h["total_players"]), f"{len(h['injured'])} injured"),
        (_fmt_money(wage["total_weekly"]), "wages / week"),
        (f"{avg_score:.1f}", formation),
        (str(strong_count), "players 70+"),
        (headroom, "headroom"),
    ]
    cells = "".join(
        f'<div class="kpi"><div class="kpi-v">{_esc(v)}</div><div class="kpi-l">{_esc(l)}</div></div>'
        for v, l in cols
    )
    return f'<div class="kpi-strip">{cells}</div>'


def _percentile_lookup(analysis: "SquadAnalysis") -> dict[str, float]:
    style_fit = analysis.tactical_style_fit
    lookup: dict[str, float] = {}
    if style_fit and style_fit.get("league_context"):
        for name, _pg, _score, _tier, pct, _lt in style_fit["league_context"]["player_scores"]:
            if pct is not None:
                lookup[name] = pct
    return lookup


def _pitch_svg(analysis: "SquadAnalysis") -> str:
    formation, xi = _effective_shape(analysis)
    pct_lookup = _percentile_lookup(analysis)
    has_league = bool(pct_lookup)
    badge_by_player: dict[str, str] = {}
    for row in _decision_board_rows(analysis):
        letter = ACTION_BADGE_LETTER.get(row["call"])
        if letter and row.get("player"):
            badge_by_player[row["player"]] = letter

    w, h = 262, 350
    line = "var(--line-2)"
    box_w, box_h = w * 0.56, h * 0.15
    parts = [
        f'<rect x="0" y="0" width="{w}" height="{h}" fill="var(--panel)"/>',
        f'<rect x="1" y="1" width="{w - 2}" height="{h - 2}" fill="none" stroke="{line}" stroke-width="1.5"/>',
        f'<line x1="1" y1="{h / 2:.1f}" x2="{w - 1}" y2="{h / 2:.1f}" stroke="{line}" stroke-width="1"/>',
        f'<circle cx="{w / 2:.1f}" cy="{h / 2:.1f}" r="35" fill="none" stroke="{line}" stroke-width="1"/>',
        f'<rect x="{(w - box_w) / 2:.1f}" y="1" width="{box_w:.1f}" height="{box_h:.1f}" fill="none" stroke="{line}" stroke-width="1"/>',
        f'<rect x="{(w - box_w) / 2:.1f}" y="{h - 1 - box_h:.1f}" width="{box_w:.1f}" height="{box_h:.1f}" fill="none" stroke="{line}" stroke-width="1"/>',
    ]

    for slot, (name, _role, score) in xi.items():
        cx, cy = PITCH_COORDS.get(slot, (50, 50))
        px, py = cx / 100 * w, cy / 100 * h
        pct = pct_lookup.get(name)
        fill = pct_color(pct) if pct is not None else role_score_color(score)
        parts.append(
            f'<circle cx="{px:.1f}" cy="{py:.1f}" r="15" fill="{fill}" stroke="var(--paper)" stroke-width="2"/>'
            f'<text x="{px:.1f}" y="{py + 3.5:.1f}" text-anchor="middle" font-family="\'IBM Plex Mono\'" '
            f'font-size="10" font-weight="600" fill="#fff">{score:.0f}</text>'
        )
        badge = badge_by_player.get(name)
        if badge:
            bx, by = px + 11, py - 11
            badge_color = "var(--sell)" if badge == "S" else ("var(--fix)" if badge == "F" else "var(--protect)")
            parts.append(
                f'<circle cx="{bx:.1f}" cy="{by:.1f}" r="7.5" fill="{badge_color}" stroke="var(--paper)" stroke-width="1.5"/>'
                f'<text x="{bx:.1f}" y="{by + 2.8:.1f}" text-anchor="middle" font-family="\'IBM Plex Mono\'" '
                f'font-size="8" font-weight="600" fill="#fff">{badge}</text>'
            )
        surname = name.split(" ")[-1]
        parts.append(
            f'<rect x="{px - 26:.1f}" y="{py + 17:.1f}" width="52" height="13" fill="var(--paper)"/>'
            f'<text x="{px:.1f}" y="{py + 26.5:.1f}" text-anchor="middle" font-family="Archivo" '
            f'font-size="10" font-weight="650" fill="var(--ink)">{_esc(surname)}</text>'
        )

    svg = (
        f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" aria-label="Best XI — {_esc(formation)}">'
        f'{"".join(parts)}</svg>'
    )
    labels = ("75th+", "50–74th", "below 50th") if has_league else ("70+", "60–69", "below 60")
    legend = (
        '<div class="pitch-legend">'
        f'<span><i style="background:var(--buy)"></i>{labels[0]}</span>'
        f'<span><i style="background:var(--neutral)"></i>{labels[1]}</span>'
        f'<span><i style="background:var(--sell)"></i>{labels[2]}</span>'
        '</div>'
    )
    return f'<div class="pitch-box">{svg}{legend}</div>'


def _short_evidence(role_hint: str, evidence: str) -> str:
    m = re.search(r"(\d+\.\d+)", evidence)
    if m and role_hint:
        return f"{role_hint} {m.group(1)}"
    if m:
        return m.group(1)
    return evidence[:16]


def _cannot_do_rows(analysis: "SquadAnalysis") -> list[tuple[str, str, str, str]]:
    priority_by_slot = {r["slot"]: r for r in analysis.recruitment_priorities}
    rows: list[tuple[str, str, str, str]] = []
    for t in analysis.tactical_impossibilities:
        pr = priority_by_slot.get(t["flag"])
        role_hint = pr["role"] if pr else ""
        label = t["flag"][:1].upper() + t["flag"][1:]
        if len(label.split()) > 4:
            label = " ".join(label.split()[:4])
        evidence = _short_evidence(role_hint, t["evidence"])
        chip = _action_chip(f"Buy {pr['role']}", "Buy") if pr else ""
        rows.append((label, evidence, chip, "Buy" if pr else ""))

    for r in analysis.recruitment_priorities:
        if "single point of failure" not in r["rationale"]:
            continue
        rows.append((
            f"Thin at {r['slot']}", "1 body only",
            _action_chip(f"Buy {r['role']}", "Buy"), "Buy",
        ))

    return rows[:6]


def _cannot_do_html(analysis: "SquadAnalysis") -> str:
    rows = _cannot_do_rows(analysis)
    if not rows:
        return ""
    body = "".join(
        f'<div class="cd-row"><div class="cd-label">{_esc(label)}</div>'
        f'<div class="cd-evidence">{_esc(evidence)}</div><div class="cd-chip">{chip}</div></div>'
        for label, evidence, chip, _key in rows
    )
    return f'<div class="panel-block"><div class="section-label">What the squad can\'t do</div>{body}</div>'


_DIVISION_BUCKETS = {"GK": "GK", "FB": "DEF", "CB": "DEF", "DM": "MID", "CM": "MID", "AM": "MID", "WI": "ATT", "ST": "ATT"}
_DIVISION_ORDER = ["GK", "DEF", "MID", "ATT"]


def _division_bars_html(analysis: "SquadAnalysis") -> str:
    style_fit = analysis.tactical_style_fit
    league_ctx = style_fit.get("league_context") if style_fit else None
    if not league_ctx:
        return ""

    buckets: dict[str, list[float]] = {b: [] for b in _DIVISION_ORDER}
    for _name, position_group, _score, _tier, pct, _lt in league_ctx["player_scores"]:
        if pct is None:
            continue
        bucket = _DIVISION_BUCKETS.get(position_group)
        if bucket:
            buckets[bucket].append(pct)

    rows = []
    for b in _DIVISION_ORDER:
        vals = buckets.get(b) or []
        if not vals:
            continue
        avg = sum(vals) / len(vals)
        fill = "var(--ink)" if avg >= 50 else "var(--sell)"
        rows.append(
            f'<div class="div-row"><div class="div-label">{b}</div>'
            f'<div class="div-track"><div class="div-fill" style="width:{avg:.0f}%;background:{fill}"></div>'
            f'<div class="div-tick" style="left:50%"></div></div>'
            f'<div class="div-val">{_ordinal(avg)}</div></div>'
        )
    if not rows:
        return ""
    return (
        '<div class="panel-block"><div class="section-label">Against the division · avg %ile</div>'
        + "".join(rows) + '<div class="caption">Line = division median.</div></div>'
    )


def _round_axis_max(v: float) -> float:
    if v <= 0:
        return 1000
    if v < 20_000:
        step = 1_000
    elif v < 100_000:
        step = 5_000
    else:
        step = 10_000
    return (int(v // step) + 1) * step


def _scatter_svg(analysis: "SquadAnalysis", players: list["Player"]) -> str:
    scored = []
    for p in players:
        if not p.wage:
            continue
        scores = roles.compute_role_scores(p)
        if not scores:
            continue
        best_score = max(scores.values())
        scored.append((p, best_score))
    if not scored:
        return ""

    outlier_names = {o["player"] for o in analysis.wage_analysis.get("wage_outliers", [])}
    best_value_names = {b["player"] for b in analysis.wage_analysis.get("best_value_contracts", [])}

    wages = [p.wage for p, _s in scored]
    scores = [s for _p, s in scored]
    x_max = _round_axis_max(max(wages))
    y_lo, y_hi = min(scores) - 1, max(scores) + 1

    w, h = 640, 220
    pad_l, pad_r, pad_t, pad_b = 34, 16, 10, 24
    plot_w, plot_h = w - pad_l - pad_r, h - pad_t - pad_b

    def px(wage: float) -> float:
        return pad_l + (wage / x_max) * plot_w

    def py(score: float) -> float:
        return pad_t + (1 - (score - y_lo) / max(y_hi - y_lo, 0.01)) * plot_h

    parts = [
        f'<rect x="{pad_l:.1f}" y="{pad_t:.1f}" width="{plot_w * 0.4:.1f}" height="{plot_h * 0.4:.1f}" fill="var(--buy)" opacity="0.07"/>',
        f'<rect x="{pad_l + plot_w * 0.6:.1f}" y="{pad_t + plot_h * 0.6:.1f}" width="{plot_w * 0.4:.1f}" height="{plot_h * 0.4:.1f}" fill="var(--sell)" opacity="0.07"/>',
        f'<text x="{pad_l + 4:.1f}" y="{pad_t + 12:.1f}" font-family="\'IBM Plex Mono\'" font-size="9" fill="var(--faint)">BARGAINS</text>',
        f'<text x="{w - pad_r - 4:.1f}" y="{h - pad_b - 6:.1f}" text-anchor="end" font-family="\'IBM Plex Mono\'" font-size="9" fill="var(--faint)">OVERPAID</text>',
        f'<line x1="{pad_l:.1f}" y1="{pad_t:.1f}" x2="{pad_l:.1f}" y2="{h - pad_b:.1f}" stroke="var(--ink)" stroke-width="1"/>',
        f'<line x1="{pad_l:.1f}" y1="{h - pad_b:.1f}" x2="{w - pad_r:.1f}" y2="{h - pad_b:.1f}" stroke="var(--ink)" stroke-width="1"/>',
        f'<text x="{pad_l:.1f}" y="{h - 6:.1f}" font-family="\'IBM Plex Mono\'" font-size="9" fill="var(--faint)">£0</text>',
        f'<text x="{w - pad_r:.1f}" y="{h - 6:.1f}" text-anchor="end" font-family="\'IBM Plex Mono\'" font-size="9" fill="var(--faint)">{_fmt_money(x_max)}</text>',
        f'<text x="{pad_l - 6:.1f}" y="{pad_t + 8:.1f}" text-anchor="end" font-family="\'IBM Plex Mono\'" font-size="9" fill="var(--faint)">{y_hi:.0f}</text>',
        f'<text x="{pad_l - 6:.1f}" y="{h - pad_b:.1f}" text-anchor="end" font-family="\'IBM Plex Mono\'" font-size="9" fill="var(--faint)">{y_lo:.0f}</text>',
    ]

    placed_labels: list[tuple[float, float]] = []
    for p, score in scored:
        x, y = px(p.wage), py(score)
        if p.name in outlier_names:
            color = "var(--sell)"
        elif p.name in best_value_names:
            color = "var(--buy)"
        else:
            color = "var(--neutral)"
        ly = y
        # Keep nudging down until clear of every previously-placed label —
        # a single pass only checked once, so a label could still collide
        # with a second nearby neighbour after dodging the first.
        for _attempt in range(12):
            collision = next((True for lx2, ly2 in placed_labels if abs(lx2 - x) < 42 and abs(ly2 - ly) < 9), False)
            if not collision:
                break
            ly += 9
        placed_labels.append((x, ly))
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="{color}"/>')
        parts.append(
            f'<text x="{x + 7:.1f}" y="{ly + 3:.1f}" font-family="Archivo" font-size="9.5" fill="var(--ink-2)">'
            f'{_esc(p.name.split(" ")[-1])}</text>'
        )

    position_cost = analysis.wage_analysis.get("position_cost", {})
    total = analysis.wage_analysis.get("total_weekly") or 1
    def pct_of(group: str) -> int:
        return round((position_cost.get(group, 0) / total) * 100)
    label = (
        f'Bill {_fmt_money(total)}/w · DEF {pct_of("defence")}% · '
        f'MID {pct_of("midfield")}% · ATT {pct_of("attack")}%'
    )

    svg = f'<svg viewBox="0 0 {w} {h}" width="100%" height="{h}" role="img" aria-label="Wage vs role score">{"".join(parts)}</svg>'
    return (
        '<div class="scatter-block">'
        f'<div class="scatter-label">{_esc(label)}</div>{svg}</div>'
    )


def _page1(analysis: "SquadAnalysis", players: list["Player"]) -> str:
    title, sub = _verdict(analysis)
    kpis = _kpi_strip(analysis)
    pitch = _pitch_svg(analysis)
    cannot_do = _cannot_do_html(analysis)
    division = _division_bars_html(analysis)
    scatter = _scatter_svg(analysis, players)

    style_fit = analysis.tactical_style_fit
    league_present = bool(style_fit and style_fit.get("league_context"))
    if league_present:
        n = style_fit["league_context"]["league_player_count"]
        clubs = style_fit["league_context"]["league_club_count"]
        pct_note = f"League %ile vs {n} players, {clubs} clubs · Strong = 70+"
    else:
        pct_note = "Role-fit scale (no --league data) · Strong = 70+"

    right_col = cannot_do + division
    return f"""
<div class="page">
  <div class="page-header"><span>Director of Football · Squad Review</span><span>Snapshot · 1/3</span></div>
  <div class="verdict-block">
    <div class="verdict-title">{_esc(title)}</div>
    <div class="verdict-sub">{_esc(sub)}</div>
  </div>
  {kpis}
  <div class="row-2col">
    {pitch}
    <div class="col-stack">{right_col}</div>
  </div>
  {scatter}
  <div class="footer"><span>{_esc(pct_note)}</span><span>Badges: F fix · S sell · P protect</span></div>
</div>
"""


# ---------------------------------------------------------------------------
# Page 2 — The window
# ---------------------------------------------------------------------------

_CALL_ORDER = ["Fix", "Buy", "Sell", "Protect"]


def _call_bucket(call: str) -> str:
    if call.startswith("Buy"):
        return "Buy"
    if call == "Fix free":
        return "Fix"
    if call in ("Protect", "Hold"):
        return "Protect"
    return call  # "Sell"


def _grouped_rows(analysis: "SquadAnalysis") -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {k: [] for k in _CALL_ORDER}
    for row in _decision_board_rows(analysis):
        groups[_call_bucket(row["call"])].append(row)
    return groups


def _segmented_bar_html(groups: dict[str, list[dict]]) -> str:
    total = sum(len(v) for v in groups.values()) or 1
    var_map = {"Fix": "var(--fix)", "Buy": "var(--buy)", "Sell": "var(--sell)", "Protect": "var(--protect)"}
    segs = []
    labels = []
    for key in _CALL_ORDER:
        n = len(groups[key])
        width_pct = (n / total) * 100
        segs.append(f'<div class="seg" style="width:{width_pct:.1f}%;background:{var_map[key]}"></div>')
        sub_label = "Fix, £0" if key == "Fix" else key
        labels.append(f'<div class="seg-label"><div class="seg-n">{n}</div><div class="seg-t">{_esc(sub_label)}</div></div>')
    return f'<div class="window-bar"><div class="bar-track">{"".join(segs)}</div></div><div class="seg-labels">{"".join(labels)}</div>'


def _phases_strip_html(groups: dict[str, list[dict]]) -> str:
    fix_n, buy_n, sell_n = len(groups["Fix"]), len(groups["Buy"]), len(groups["Sell"])
    cells = [
        ("Fix", "This week", f"Fix {fix_n} contract{'s' if fix_n != 1 else ''}"),
        ("Buy", "Immediately", f"{buy_n} buy{'s' if buy_n != 1 else ''}, no sale needed"),
        ("Sell", "Then", f"{sell_n} sale{'s' if sell_n != 1 else ''} to fund upgrades"),
    ]
    html_cells = "".join(
        f'<div class="phase-cell"><div class="phase-top" style="color:{ACTION_CHIP_COLOR[key]}">{_esc(top)}</div>'
        f'<div class="phase-main">{_esc(main)}</div></div>'
        for key, top, main in cells
    )
    return f'<div class="phases-strip">{html_cells}</div>'


def _action_board_html(analysis: "SquadAnalysis", groups: dict[str, list[dict]]) -> str:
    wb = analysis.window_budget or {}
    caps = {"Fix": 9, "Buy": 5, "Sell": 6, "Protect": 6}

    # Decision-board rows only carry a formatted "Accept £X+" string for
    # Sell — the raw low/high figures needed for a total range live on
    # exit_candidates itself, matched by player name.
    exit_value_by_name = {e["player"]: (e.get("value_low"), e.get("value_high")) for e in analysis.exit_candidates}
    sell_lows, sell_highs = [], []
    for r in groups["Sell"]:
        lo, hi = exit_value_by_name.get(r.get("player"), (None, None))
        if lo is not None and hi is not None:
            sell_lows.append(lo)
            sell_highs.append(hi)

    money_by_col = {
        "Fix": "£0",
        "Buy": _fmt_money_ceiling(wb.get("priority_cost_high")) if wb.get("priority_cost_high") else "",
        "Sell": _fmt_money_range(sum(sell_lows), sum(sell_highs)) if sell_lows else "",
        "Protect": "",
    }

    # "Buy: ROLE · Lead surname" — the decision board itself only carries
    # the role (no candidate is chosen until the Target Dossier search
    # runs), so the lead's surname is looked up separately, keyed by role.
    lead_surname_by_role: dict[str, str] = {}
    for entry in analysis.target_dossier or []:
        if entry.get("kind") == "recruitment" and entry.get("candidates"):
            lead_surname_by_role.setdefault(entry["role"], entry["candidates"][0]["player"].split(" ")[-1])

    cols_html = []
    for key in _CALL_ORDER:
        rows = groups[key]
        n_total = len(rows)
        rows = rows[: caps[key]]
        color = ACTION_CHIP_COLOR[key]
        items = []
        for r in rows:
            name = r["who"].split(" (")[0]
            if key == "Buy":
                lead = lead_surname_by_role.get(name)
                if lead:
                    name = f"{name} · {lead}"
            note = _short_note_for(key, r)
            items.append(
                f'<div class="board-item"><div class="board-name">{_esc(name)}</div>'
                f'<div class="board-note">{_esc(note)}</div></div>'
            )
        if n_total > caps[key]:
            items.append(f'<div class="board-item board-more">+{n_total - caps[key]} more in appendix</div>')
        money = money_by_col.get(key, "")
        cols_html.append(
            f'<div class="board-col" style="border-top-color:{color}">'
            f'<div class="board-head"><span class="board-title">{key} · {n_total}</span>'
            f'<span class="board-money" style="color:{color}">{_esc(money)}</span></div>'
            f'{"".join(items)}</div>'
        )
    return f'<div class="action-board">{"".join(cols_html)}</div>'


def _short_note_for(key: str, row: dict) -> str:
    if key == "Fix":
        why = row["why"]
        m = re.search(r"on a (.+?) deal, actually playing like (.+)$", why)
        if m:
            return f"{m.group(1)} → {m.group(2)}"
        return _truncate_words(why, 6)
    if key == "Buy":
        return _truncate_words(row["why"].split(" — ")[0], 6)
    if key == "Sell":
        return f"{row['trigger']} · {row['number']}"
    if key == "Protect":
        # Bucket covers both the true "Protect" (squad ceiling) row and
        # "Hold" rows (other load-bearing players) — different underlying
        # facts, so different note text rather than one truncated blob.
        if row["call"] == "Hold":
            m = re.search(r"next option (\d+\.\d+)", row["why"])
            if m:
                return f"Next best {m.group(1)}"
        return "Squad ceiling player"
    return _truncate_words(row["why"], 6)


def _waterfall_html(analysis: "SquadAnalysis") -> str:
    wb = analysis.window_budget or {}
    transfer_budget = wb.get("transfer_budget")
    if transfer_budget is None:
        return ""
    exit_low = wb.get("exit_proceeds_low") or 0
    available = wb.get("available_transfer_budget") or transfer_budget
    buys = wb.get("priority_cost_high") or 0
    reconciliation = wb.get("reconciliation")
    headroom = reconciliation if reconciliation is not None else (available - buys)

    scale = max(transfer_budget + exit_low, available, buys, abs(headroom), 1)

    def bar(value: float, start: float, color: str, align_right: bool = False) -> str:
        w_pct = min(abs(value) / scale, 1.0) * 100
        left = (start / scale) * 100 if not align_right else max(0.0, ((start - abs(value)) / scale) * 100)
        return f'<div class="wf-track"><div class="wf-fill" style="left:{left:.1f}%;width:{w_pct:.1f}%;background:{color}"></div></div>'

    rows = [
        ("Transfer budget", bar(transfer_budget, 0, "var(--ink)"), _fmt_money(transfer_budget)),
        ("Sales, low estimate", bar(exit_low, transfer_budget, "var(--sell)"), _fmt_money(exit_low)),
        ("Available", bar(available, 0, "var(--ink)"), _fmt_money(available)),
        ("Buys, worst case", bar(buys, available, "var(--buy)", align_right=True), _fmt_money(buys)),
        ("Headroom" if headroom >= 0 else "Shortfall", bar(headroom, 0, "var(--ink)"), _fmt_money(abs(headroom))),
    ]
    row_html = "".join(
        f'<div class="wf-row"><div class="wf-label">{_esc(label)}</div>{track}<div class="wf-val">{val}</div></div>'
        for label, track, val in rows
    )
    sign = "headroom" if headroom >= 0 else "shortfall"
    caption = f"Top sale estimate ({_fmt_money(exit_low)}): {sign} {_fmt_money(abs(headroom))}."
    return f'<div class="waterfall"><div class="section-label">Where the money comes from</div>{row_html}<div class="caption">{_esc(caption)}</div></div>'


def _page2(analysis: "SquadAnalysis") -> str:
    groups = _grouped_rows(analysis)
    total_moves = sum(len(v) for v in groups.values())
    return f"""
<div class="page">
  <div class="page-header"><span>Director of Football · Squad Review</span><span>The window · 2/3</span></div>
  <div class="page-title">{total_moves} move{"s" if total_moves != 1 else ""} this window</div>
  {_segmented_bar_html(groups)}
  {_phases_strip_html(groups)}
  {_action_board_html(analysis, groups)}
  {_waterfall_html(analysis)}
</div>
"""


# ---------------------------------------------------------------------------
# Page 3 — Shortlist
# ---------------------------------------------------------------------------

def _need_card_html(entry: dict, priority: dict, squad_best: Optional[float]) -> str:
    candidates = (entry.get("candidates") or [])[:3]
    if not candidates:
        return ""
    rows = []
    for i, c in enumerate(candidates):
        color = candidate_color(c["role_score"], squad_best)
        pct_of_bar = max(min((c["role_score"] - 55) / (72 - 55), 1.0), 0.0) * 100
        tick_pct = max(min(((squad_best or 55) - 55) / (72 - 55), 1.0), 0.0) * 100 if squad_best is not None else None
        weight = "750" if i == 0 else "500"
        sub = f"{c['age']} · {_fmt_money_range(c['value_low'], c['value_high'])} · {_fmt_money(c['wage'])}/w"
        tick_html = f'<div class="cand-tick" style="left:{tick_pct:.0f}%"></div>' if tick_pct is not None else ""
        rows.append(
            '<div class="cand-row">'
            f'<div class="cand-name"><div class="cand-n" style="font-weight:{weight}">{_esc(c["player"])}</div>'
            f'<div class="cand-sub">{_esc(sub)}</div></div>'
            f'<div class="cand-bar"><div class="cand-track">{tick_html}'
            f'<div class="cand-fill" style="width:{pct_of_bar:.0f}%;background:{color}"></div></div></div>'
            f'<div class="cand-score">{c["role_score"]:.1f}</div>'
            '</div>'
        )
    top = candidates[0]
    note = f"{top['player'].split(' ')[-1]} leads on role fit"
    if top.get("stretch_target"):
        note = f"{top['player'].split(' ')[-1]} is a stretch target"
    need = priority["rationale"].split(" — ")[0][:40]
    return (
        '<div class="need-card">'
        f'<div class="need-head"><span class="need-role">{_esc(entry["role"])}</span>'
        f'<span class="need-need">{_esc(need)}</span></div>'
        f'{"".join(rows)}'
        f'<div class="need-note">{_esc(note)}</div>'
        '</div>'
    )


_LEGEND_CELL = """
<div class="need-card legend-cell">
  <div class="legend-row"><i style="background:var(--buy)"></i>Beats current squad best</div>
  <div class="legend-row"><i style="background:var(--neutral)"></i>Below squad best: depth only</div>
  <div class="legend-row"><i style="background:var(--ink)"></i>Current squad best (tick)</div>
  <div class="legend-note">Bold = first choice · age · fee · wage/w</div>
</div>
"""


def _need_cards_html(analysis: "SquadAnalysis") -> str:
    dossier_by_role: dict[str, dict] = {}
    for entry in analysis.target_dossier or []:
        if entry.get("kind") == "recruitment":
            dossier_by_role.setdefault(entry["role"], entry)

    priorities = [r for r in analysis.recruitment_priorities if r["role"] in dossier_by_role]
    priorities = priorities[:5]

    # The squad's own best score at each exact role — from role_coverage_summary
    # (computed for all 28 roles regardless of formation), not the current
    # top XI, which only covers whichever roles the best-supported formation
    # actually uses. A recruitment priority is frequently for a role nobody
    # in the current XI plays at all (that's often exactly why it's a
    # priority) — using top_xi alone left every such card uniformly grey,
    # never able to show a genuine "beats the squad" green bar.
    coverage = analysis.role_coverage_summary or {}

    cards = []
    for r in priorities:
        entry = dossier_by_role[r["role"]]
        top3 = (coverage.get(r["role"]) or {}).get("top3") or []
        squad_best = top3[0][1] if top3 else None
        card = _need_card_html(entry, r, squad_best)
        if card:
            cards.append(card)

    if not cards:
        return ""

    cards.append(_LEGEND_CELL)
    return f'<div class="need-grid">{"".join(cards)}</div>'


def _sell_dumbbell_row(exit_candidate: dict, entry: dict) -> str:
    candidates = entry.get("candidates") or []
    if not candidates:
        return ""
    top = candidates[0]
    current_score = exit_candidate["best_role_score"]
    delta = top["role_score"] - current_score
    delta_str = f"+{delta:.1f}" if delta > 0.05 else ("±0.0" if abs(delta) <= 0.05 else f"{delta:.1f}")

    lo, hi = 58.0, 70.0

    def bar_pct(v: float) -> float:
        return max(min((v - lo) / (hi - lo), 1.0), 0.0) * 100

    x1, x2 = bar_pct(current_score), bar_pct(top["role_score"])
    left, right = min(x1, x2), max(x1, x2)
    out_sub = f"{exit_candidate['best_role_score']:.1f} · {_fmt_money(exit_candidate.get('wage'))}"
    in_sub = f"{_esc(top.get('club') or 'unknown')} · {top['age']} · {_fmt_money(top['wage'])}/w"

    dumbbell = (
        '<div class="dumbbell-track">'
        f'<div class="dumbbell-line" style="left:{left:.0f}%;width:{max(right - left, 0):.0f}%"></div>'
        f'<div class="dumbbell-dot sell" style="left:{x1:.0f}%"></div>'
        f'<div class="dumbbell-dot buy" style="left:{x2:.0f}%"></div>'
        '</div>'
    )
    fee = _fmt_money_range(top["value_low"], top["value_high"])
    return (
        '<div class="sell-row">'
        f'<div class="sell-out"><div class="sell-out-name">{_esc(exit_candidate["player"])}</div>'
        f'<div class="sell-out-sub">{out_sub}</div></div>'
        f'<div class="sell-dumbbell">{dumbbell}</div>'
        f'<div class="sell-in"><div class="sell-in-name">{_esc(top["player"])}</div>'
        f'<div class="sell-in-sub">{in_sub}</div></div>'
        f'<div class="sell-delta">{delta_str}</div>'
        f'<div class="sell-fee">{fee}</div>'
        '</div>'
    )


def _sell_replacements_html(analysis: "SquadAnalysis") -> str:
    exits_by_name = {e["player"]: e for e in analysis.exit_candidates}
    rows = []
    for entry in analysis.target_dossier or []:
        if entry.get("kind") not in ("exit_replacement_listed", "exit_replacement_valuable"):
            continue
        exiting = exits_by_name.get(entry["slot"])
        if not exiting:
            continue
        row = _sell_dumbbell_row(exiting, entry)
        if row:
            rows.append(row)

    if not rows:
        return ""

    capped = rows[:5]
    more = ""
    if len(rows) > 5:
        more = f'<div class="sell-row sell-more">+{len(rows) - 5} more in appendix</div>'
    header = (
        '<div class="sell-row sell-header">'
        '<div>Outgoing</div><div></div><div>Replacement</div><div>Δ</div><div>Fee</div></div>'
    )
    return (
        '<div class="sell-block"><div class="section-label">If you sell · replacements</div>'
        + header + "".join(capped) + more + "</div>"
    )


def _page3(analysis: "SquadAnalysis") -> str:
    need_cards = _need_cards_html(analysis)
    sell_block = _sell_replacements_html(analysis)
    return f"""
<div class="page">
  <div class="page-header"><span>Director of Football · Squad Review</span><span>Shortlist · 3/3</span></div>
  <div class="page-title">Who to call</div>
  {need_cards}
  {sell_block}
  <div class="footer"><span>Computed from role/style fit and FM value estimates. Availability not guaranteed.</span><span></span></div>
</div>
"""


# ---------------------------------------------------------------------------
# Document shell
# ---------------------------------------------------------------------------

PAGE_CSS = """
:root{
  --paper:#fbfaf7; --panel:#f1efe8; --ink:#161614; --ink-2:#3d3c39;
  --muted:#6b6962; --faint:#9a978e; --line:#e3e1da; --line-2:#cfccc2;
  --neutral:#8a877f;
  --fix:oklch(0.62 0.13 75); --buy:oklch(0.55 0.12 150);
  --sell:oklch(0.56 0.15 28); --protect:oklch(0.52 0.12 250);
}
*{box-sizing:border-box;}
body{margin:0;background:#e6e4de;font-family:Archivo,sans-serif;}
.page{
  width:794px;height:1123px;margin:24px auto;padding:44px 52px;background:var(--paper);
  color:var(--ink);display:flex;flex-direction:column;gap:22px;overflow:hidden;
  break-after:page;
}
.page-header{
  display:flex;justify-content:space-between;font-family:'IBM Plex Mono';font-size:10px;
  text-transform:uppercase;color:var(--muted);letter-spacing:.04em;
  border-bottom:1.5px solid var(--ink);padding-bottom:8px;flex:0 0 auto;
}
.footer{
  display:flex;justify-content:space-between;font-family:'IBM Plex Mono';font-size:9.5px;
  color:var(--faint);border-top:1px solid var(--line);padding-top:8px;margin-top:auto;flex:0 0 auto;
}
.verdict-title{font-family:Archivo;font-weight:750;font-stretch:72%;font-size:40px;line-height:1.0;}
.verdict-sub{font-family:Archivo;font-size:14px;line-height:1.45;color:var(--ink-2);margin-top:8px;max-width:640px;}
.section-label{
  font-family:'IBM Plex Mono';font-size:10px;font-weight:600;text-transform:uppercase;
  letter-spacing:.08em;color:var(--muted);margin-bottom:6px;
}
.kpi-strip{display:flex;border-top:1px solid var(--ink);border-bottom:1px solid var(--ink);}
.kpi{flex:1;padding:10px 14px;border-left:1px solid var(--line);}
.kpi:first-child{border-left:none;}
.kpi-v{font-family:'IBM Plex Mono';font-size:22px;font-weight:600;letter-spacing:-.02em;}
.kpi-l{font-family:'IBM Plex Mono';font-size:9.5px;font-weight:500;text-transform:uppercase;letter-spacing:.07em;color:var(--muted);margin-top:2px;}
.row-2col{display:flex;gap:30px;}
.pitch-box{flex:0 0 262px;}
.pitch-legend{display:flex;gap:12px;margin-top:6px;font-family:'IBM Plex Mono';font-size:9px;color:var(--muted);}
.pitch-legend span{display:flex;align-items:center;gap:4px;}
.pitch-legend i{width:7px;height:7px;border-radius:50%;display:inline-block;}
.col-stack{flex:1;display:flex;flex-direction:column;gap:16px;min-width:0;}
.panel-block{}
.cd-row{
  display:grid;grid-template-columns:1fr 92px 78px;align-items:center;gap:6px;
  padding:5px 0;border-bottom:1px solid var(--line);font-size:12px;
}
.cd-label{font-family:Archivo;font-weight:600;}
.cd-evidence{font-family:'IBM Plex Mono';font-size:10px;color:var(--muted);}
.cd-chip{text-align:right;}
.chip{
  display:inline-block;color:#fff;font-family:'IBM Plex Mono';font-size:10px;font-weight:600;
  padding:3px 6px;border-radius:2px;white-space:nowrap;
}
.div-row{display:grid;grid-template-columns:38px 1fr 40px;align-items:center;gap:8px;padding:3px 0;}
.div-label{font-family:'IBM Plex Mono';font-size:10px;color:var(--muted);}
.div-track{height:14px;background:var(--panel);position:relative;}
.div-fill{height:14px;}
.div-tick{position:absolute;top:-3px;bottom:-3px;width:1.5px;background:var(--ink);}
.div-val{font-family:'IBM Plex Mono';font-size:11px;text-align:right;}
.caption{font-family:'IBM Plex Mono';font-size:9.5px;color:var(--faint);margin-top:6px;}
.scatter-block{}
.scatter-label{font-family:'IBM Plex Mono';font-size:10px;color:var(--muted);text-align:right;margin-bottom:4px;}
.page-title{font-family:Archivo;font-weight:750;font-size:26px;}
.window-bar .bar-track{height:16px;display:flex;gap:2px;}
.window-bar .seg{height:16px;}
.seg-labels{display:flex;margin-top:4px;}
.seg-label{flex:1;}
.seg-n{font-family:'IBM Plex Mono';font-size:15px;font-weight:600;}
.seg-t{font-family:'IBM Plex Mono';font-size:9.5px;color:var(--muted);text-transform:uppercase;letter-spacing:.05em;}
.phases-strip{display:flex;gap:2px;}
.phase-cell{flex:1;background:var(--panel);padding:12px 14px;}
.phase-top{font-family:'IBM Plex Mono';font-size:9.5px;text-transform:uppercase;letter-spacing:.05em;font-weight:600;}
.phase-main{font-family:Archivo;font-size:13px;font-weight:650;margin-top:3px;}
.action-board{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;flex:1;min-height:0;}
.board-col{border-top:4px solid;display:flex;flex-direction:column;min-width:0;}
.board-head{display:flex;justify-content:space-between;align-items:baseline;border-bottom:1px solid var(--ink);padding:6px 0;}
.board-title{font-family:Archivo;font-size:15px;font-weight:750;}
.board-money{font-family:'IBM Plex Mono';font-size:11px;font-weight:600;}
.board-item{padding:6px 0;border-bottom:1px solid var(--line);}
.board-name{font-family:Archivo;font-size:12.5px;font-weight:650;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.board-note{font-family:'IBM Plex Mono';font-size:10px;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.board-more{font-family:'IBM Plex Mono';font-size:10px;color:var(--faint);}
.waterfall{margin-top:auto;}
.wf-row{display:grid;grid-template-columns:150px 1fr 64px;align-items:center;gap:8px;padding:2px 0;}
.wf-label{font-family:'IBM Plex Mono';font-size:10px;color:var(--muted);}
.wf-track{height:18px;background:var(--panel);position:relative;}
.wf-fill{position:absolute;top:0;height:18px;}
.wf-val{font-family:'IBM Plex Mono';font-size:11px;text-align:right;}
.need-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px 22px;}
.need-card{border-top:1.5px solid var(--ink);padding-top:8px;}
.need-head{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:6px;}
.need-role{font-family:'IBM Plex Mono';font-size:12px;font-weight:600;}
.need-need{font-family:Archivo;font-size:11px;color:var(--muted);}
.cand-row{display:grid;grid-template-columns:1fr 80px 70px;align-items:center;gap:8px;padding:4px 0;}
.cand-n{font-family:Archivo;font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.cand-sub{font-family:'IBM Plex Mono';font-size:9.5px;color:var(--muted);}
.cand-track{height:8px;background:var(--panel);position:relative;}
.cand-fill{height:8px;}
.cand-tick{position:absolute;top:-2px;bottom:-2px;width:1.5px;background:var(--ink);z-index:1;}
.cand-score{font-family:'IBM Plex Mono';font-size:11px;font-weight:600;text-align:right;}
.need-note{font-family:Archivo;font-size:11px;color:var(--ink-2);margin-top:4px;}
.legend-cell{border-top:1.5px solid var(--line-2);}
.legend-row{display:flex;align-items:center;gap:6px;font-family:Archivo;font-size:11px;padding:3px 0;}
.legend-row i{width:9px;height:9px;display:inline-block;border-radius:2px;}
.legend-note{font-family:'IBM Plex Mono';font-size:9.5px;color:var(--faint);margin-top:4px;}
.sell-block{margin-top:8px;}
.sell-row{display:grid;grid-template-columns:150px 1fr 150px 52px 76px;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid var(--line);}
.sell-header{font-family:'IBM Plex Mono';font-size:9.5px;text-transform:uppercase;color:var(--muted);letter-spacing:.05em;}
.sell-out-name{font-family:Archivo;font-size:12px;font-weight:650;color:var(--sell);}
.sell-out-sub{font-family:'IBM Plex Mono';font-size:9.5px;color:var(--muted);}
.sell-in-name{font-family:Archivo;font-size:12px;font-weight:650;}
.sell-in-sub{font-family:'IBM Plex Mono';font-size:9.5px;color:var(--muted);}
.dumbbell-track{height:10px;position:relative;}
.dumbbell-line{position:absolute;top:4px;height:2px;background:var(--buy);}
.dumbbell-dot{position:absolute;top:0;width:10px;height:10px;border-radius:50%;margin-left:-5px;}
.dumbbell-dot.sell{background:var(--sell);}
.dumbbell-dot.buy{background:var(--buy);}
.sell-delta{font-family:'IBM Plex Mono';font-size:12px;color:var(--buy);}
.sell-fee{font-family:'IBM Plex Mono';font-size:11px;text-align:right;}
.sell-more{font-family:'IBM Plex Mono';font-size:10px;color:var(--faint);grid-template-columns:1fr;}
@media print{
  body{background:#fff;}
  .page{margin:0;box-shadow:none;}
  @page{size:A4;margin:0;}
}
"""


def generate_briefing_html(analysis: "SquadAnalysis", players: list["Player"]) -> str:
    page1 = _page1(analysis, players)
    page2 = _page2(analysis)
    page3 = _page3(analysis)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>The Briefing — Director of Football Squad Review</title>
{FONTS_LINK}
<style>{PAGE_CSS}</style>
</head>
<body>
{page1}
{page2}
{page3}
</body>
</html>
"""
