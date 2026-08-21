"""Facts + context -> markdown, via Claude (or free mode without an API key)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Optional

from fm_copilot import html_report, roles, tactics
from fm_copilot.config import Config
from fm_copilot.parser import (
    GOALKEEPING_ATTRIBUTES,
    MENTAL_ATTRIBUTES,
    PHYSICAL_ATTRIBUTES,
    TECHNICAL_ATTRIBUTES,
    Player,
)

if TYPE_CHECKING:
    from fm_copilot.analyzer import SquadAnalysis

PROMPTS_DIR = Path(__file__).parent / "prompts"

TECHNICAL_SHORT = {
    "Corners": "cor", "Crossing": "cro", "Dribbling": "dri", "Finishing": "fin",
    "First Touch": "fir", "Free Kick Taking": "fre", "Heading": "hea", "Long Shots": "lon",
    "Long Throws": "lth", "Marking": "mar", "Passing": "pas", "Penalty Taking": "pen",
    "Tackling": "tck", "Technique": "tec",
}
MENTAL_SHORT = {
    "Aggression": "agg", "Anticipation": "ant", "Bravery": "brv", "Composure": "cmp",
    "Concentration": "cnt", "Decisions": "dec", "Determination": "det", "Flair": "fla",
    "Leadership": "ldr", "Off the Ball": "otb", "Positioning": "pos", "Teamwork": "tea",
    "Vision": "vis", "Work Rate": "wor",
}
PHYSICAL_SHORT = {
    "Acceleration": "acc", "Agility": "agi", "Balance": "bal", "Jumping Reach": "jum",
    "Natural Fitness": "nat", "Pace": "pac", "Stamina": "sta", "Strength": "str",
}
GK_SHORT = {
    "Aerial Reach": "aer", "Command of Area": "cmd", "Communication": "com",
    "Eccentricity": "ecc", "Handling": "han", "Kicking": "kic", "One on Ones": "1v1",
    "Reflexes": "ref", "Rushing Out": "rus", "Punching Tendency": "pun", "Throwing": "thr",
}

# v2 schema (report-restructure.md). Sections 2-3 are reserved for stage 2
# (decision board / sequencing) — stage 1 renumbers everything else around
# them and explicitly tells the model to skip the gap rather than invent
# content for it. Indices below are relied on positionally by
# _free_mode_report.
SECTION_HEADERS = [
    "1. HEADLINE VERDICT",           # 0
    "2. THE WINDOW",                 # 1 — reserved, stage 2
    "3. ORDER OF OPERATIONS",        # 2 — reserved, stage 2
    "4. THE SHAPE",                  # 3
    "5. WHAT THIS SQUAD CANNOT DO",  # 4
    "6. EDGES",                      # 5
    "7. THE MONEY",                  # 6
    "8. AGAINST THE DIVISION",       # 7 — conditional: has_style_fit
    "9. TARGETS",                    # 8
    "10. HOUSEKEEPING",              # 9 — conditional: has_squad_audit or has_development_pipeline
]


def _money(n: Optional[float]) -> str:
    if n is None:
        return "unknown"
    n = float(n)
    if n >= 1_000_000:
        return f"£{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"£{n / 1_000:,.0f}K"
    return f"£{n:.0f}"

def _money_full(n: Optional[float]) -> str:
    return "unknown" if n is None else f"£{n:,.0f}"


def _table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return "None"
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        out.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Squad analysis rendering (shared between API-mode prompt and free mode)
# ---------------------------------------------------------------------------

def _render_headline(headline: dict) -> str:
    lines = [
        f"- Total registered: {headline['total_players']}",
        f"- Available bodies: {headline['available_count']}",
        f"- Injured ({len(headline['injured'])}): {', '.join(headline['injured']) or 'none'}",
        f"- On loan out ({len(headline['on_loan'])}): {', '.join(headline['on_loan']) or 'none'}",
        f"- Unavailable ({len(headline['unavailable'])}): {', '.join(headline['unavailable']) or 'none'}",
        f"- Suspended ({len(headline['suspended'])}): {', '.join(headline['suspended']) or 'none'}",
        f"- Transfer listed ({len(headline['transfer_listed'])}): {', '.join(headline['transfer_listed']) or 'none'}",
        f"- Unhappy ({len(headline['unhappy'])}): {', '.join(headline['unhappy']) or 'none'}",
        f"- Loanees in ({len(headline['loanees_in'])}): {', '.join(headline['loanees_in']) or 'none'}",
        f"- Goalkeepers: {headline['gk_available_count']}/{headline['gk_total_count']} available — {headline['gk_backup_situation']}",
    ]
    return "\n".join(lines)


def _render_headline_compact(headline: dict) -> str:
    """One-line version of _render_headline for the actual Section 1 body
    (report-restructure.md stage 1) — the full breakdown above still feeds
    the LLM's context, this is what a time-strapped reader actually sees."""
    flags = []
    for key, label in [
        ("injured", "injured"), ("on_loan", "on loan"), ("unavailable", "unavailable"),
        ("suspended", "suspended"), ("transfer_listed", "transfer-listed"), ("unhappy", "unhappy"),
    ]:
        if headline[key]:
            flags.append(f"{len(headline[key])} {label}")
    flags_str = f" ({', '.join(flags)})" if flags else ""
    return (
        f"{headline['available_count']}/{headline['total_players']} available{flags_str}. "
        f"GK: {headline['gk_available_count']}/{headline['gk_total_count']} available — {headline['gk_backup_situation']}."
    )


def _render_formation_viability(viability: list[dict]) -> str:
    rows = [
        [r["formation"], f"{r['total_score']:.0f}", f"{r['avg_score']:.1f}",
         ", ".join(r["structural_weaknesses"]) or "none"]
        for r in viability
    ]
    return _table(["Formation", "Total score", "Avg score", "Weak slots"], rows)


def _render_style_fit(style_fit: dict) -> str:
    counts = style_fit["tier_counts"]
    counts_desc = " · ".join(f"{n} {label.lower()}" for label, n in counts.items())
    league_ctx = style_fit.get("league_context")

    parts = [f"**Tactical direction: {style_fit['style_label']}** — {counts_desc}"]

    if league_ctx:
        parts.append(
            f"Benchmarked against {league_ctx['league_player_count']} players across "
            f"{league_ctx['league_club_count']} clubs in the current league, weighted by starts+subs."
            + (
                " Apps data is sparse league-wide, so this benchmark is currently behaving like an "
                "unweighted average across the league rather than favouring regular starters."
                if league_ctx["sparse_apps_warning"] else ""
            )
        )
        rows = [
            [
                name, position_group, f"{score:.1f}", tier,
                f"{pct:.0f}%" if pct is not None else "—", league_tier,
            ]
            for name, position_group, score, tier, pct, league_tier in league_ctx["player_scores"]
        ]
        parts.append(_table(
            ["Player", "Position", "Score", "Fit", "League %ile", "League fit"], rows,
        ))
    else:
        rows = [
            [name, position_group, f"{score:.1f}", tier]
            for name, position_group, score, tier in style_fit["player_scores"]
        ]
        parts.append(_table(["Player", "Position", "Score", "Fit"], rows))

    return "\n\n".join(parts)


def _read_note(name: str, decisive: dict, style_fit: Optional[dict]) -> str:
    """Per-XI-slot note folding old Section 6 (Decisive Players) and the
    style-fit detail table into the Shape table itself — same facts, no
    second section restating them (report-restructure.md stage 1)."""
    notes = []
    load_bearing_by_name = {d["player"]: d for d in decisive.get("load_bearing", [])}
    if name in load_bearing_by_name:
        d = load_bearing_by_name[name]
        next_best = f"{d['next_best']} {d['next_best_score']:.1f}" if d["next_best"] else "none"
        notes.append(f"Load-bearing, next option {next_best}.")
    if name == decisive.get("ceiling", {}).get("player"):
        notes.append("Ceiling player" + (" (young)." if decisive["ceiling"].get("is_young") else "."))
    if name == decisive.get("structure", {}).get("player"):
        notes.append(f"Structural — {decisive['structure']['roles_at_65plus']} roles at 65+.")
    if name == decisive.get("floor", {}).get("player"):
        notes.append("Floor player.")
    if style_fit:
        for row in style_fit["player_scores"]:
            if row[0] != name:
                continue
            pct = row[4] if len(row) > 4 else None
            if pct is not None:
                notes.append(f"{pct:.0f}th-pct style fit.")
            else:
                notes.append(f"Style fit: {row[3]}.")
            break
    return " ".join(notes) or "—"


def _render_shape(shape: dict, decisive: dict, style_fit: Optional[dict] = None) -> str:
    parts = [f"**Top formation:** {shape['top_formation']} (avg {shape['top_xi_avg_score']:.1f})"]
    xi_rows = [
        [slot, name, role, f"{score:.1f}", _read_note(name, decisive, style_fit)]
        for slot, (name, role, score) in shape["top_xi"].items()
    ]
    parts.append(_table(["Slot", "Player", "Role", "Score", "Read"], xi_rows))

    deps = shape["key_dependencies"]
    if deps:
        dep_rows = [
            [d["playmaker"], f"{d['playmaker_role']} {d['playmaker_score']:.1f} (str {d['playmaker_strength']})",
             d["enabler"], f"{d['enabler_score']:.1f} (str {d['enabler_strength']}, {d['enabler_height']}cm)"]
            for d in deps
        ]
        parts.append("Key dependencies (playmaker → physical enabler):")
        parts.append(_table(["Playmaker", "Playmaker fit", "Enabler", "Enabler fit"], dep_rows))
    else:
        parts.append("Key dependencies: none identified.")

    override = shape.get("override_formation")
    if override:
        if override.get("matched_shape"):
            ov_rows = [
                [slot, name, role, f"{score:.1f}"]
                for slot, (name, role, score) in override["xi"].items()
            ]
            parts.append(
                f"**Override formation requested:** \"{override['requested_text']}\" "
                f"(evaluated as {override['matched_shape']}, total {override['total_score']:.0f}, "
                f"avg {override['avg_score']:.1f}, weak slots: {', '.join(override['structural_weaknesses']) or 'none'})"
            )
            parts.append(_table(["Slot", "Player", "Role", "Score"], ov_rows))
        else:
            parts.append(
                f"**Override formation requested:** \"{override['requested_text']}\" — "
                f"not one of the 6 modelled shapes; treat as directional context only."
            )

    if style_fit:
        parts.append(f"**Tactical direction:** {style_fit['style_label']} — Read column above carries the per-player fit; full breakdown is Section 8.")
    else:
        parts.append("Tactical direction: not specified.")
    return "\n\n".join(parts)


def _render_role_coverage(summary: dict) -> str:
    rows = []
    for role in roles.ROLE_WEIGHTS:
        s = summary[role]
        top3 = ", ".join(f"{n} {sc:.1f}" for n, sc in s["top3"])
        rows.append([role, str(s["capable_count"]), str(s["strong_count"]), str(s["elite_count"]), top3 or "none"])
    return _table(["Role", "Capable (>=60)", "Strong (>=70)", "Elite (>=75)", "Top 3"], rows)


def _render_tactical(tactical: list[dict]) -> str:
    if not tactical:
        return "No tactical impossibilities flagged."
    return "\n".join(f"- **{t['flag']}** — {t['evidence']}" for t in tactical)


def _render_cannot_do(tactical: list[dict], recruitment: list[dict], decisive: dict) -> str:
    """Old Section 3 (tactical impossibilities) plus a Fix column, and old
    Section 6's load-bearing rows folded in as a second kind of hard limit
    (report-restructure.md stage 1) — a load-bearing single point of
    failure is exactly as much a "cannot do" as a missing role.
    _recruitment_priorities() (analyzer.py) sets an impossibility-derived
    priority's slot to the impossibility's own flag string, so matching by
    slot==flag reuses that link rather than re-deriving it.
    """
    priority_by_slot = {r["slot"]: r for r in recruitment}
    rows = []
    for t in tactical:
        fix = "—"
        pr = priority_by_slot.get(t["flag"])
        if pr:
            ceiling = pr.get("cost_ceiling")
            fix = pr["role"] + (f" — {_money(ceiling['low'])}-{_money(ceiling['high'])}" if ceiling else "")
        rows.append([t["flag"], t["evidence"], fix])

    for d in decisive.get("load_bearing", []):
        next_option = f"next option {d['next_best_score']:.1f}" if d["next_best"] else "no alternative"
        rows.append([
            f"Absorb losing {d['player']}",
            f"{d['role']} {d['score']:.1f} → {next_option}",
            "Not a signing — manage minutes",
        ])

    if not rows:
        return "No hard limits or load-bearing single points of failure identified."
    return _table(["Limit", "Evidence", "Fix"], rows)


def _render_hidden(hidden: dict) -> str:
    lines = [
        f"- Set-piece attacking asset: {'YES' if hidden['set_piece_asset']['flag'] else 'no'} — {hidden['set_piece_asset']['evidence']}",
        f"- Set-piece defensive risk: {'YES' if hidden['set_piece_defensive_risk']['flag'] else 'no'} — {hidden['set_piece_defensive_risk']['evidence']}",
        f"- Wide pace: {'YES' if hidden['wide_pace']['flag'] else 'no'} — {hidden['wide_pace']['evidence']}",
        f"- Youth pipeline (<=21, best-role-score >=65): {hidden['youth_pipeline']['count']} — "
        + (", ".join(f"{n} (age {a}, {sc})" for n, a, sc in hidden["youth_pipeline"]["players"]) or "none"),
    ]
    return "\n".join(lines)


def _render_wage(wage: dict) -> str:
    parts = [
        f"**Total wage bill:** {_money_full(wage['total_weekly'])}/w ({_money(wage['total_yearly'])}/yr)",
        "Top 5 earners:",
        _table(
            ["Player", "Wage/w", "Best role", "Score"],
            [[e["player"], _money_full(e["wage"]), e["best_role"], f"{e['best_role_score']:.1f}"] for e in wage["top5_earners"]],
        ),
        "Wage-to-role-score outliers (potentially overpaid):",
        _table(
            ["Player", "Wage/w", "Best role", "Score", "Ratio", "Key-tier weaknesses"],
            [
                [o["player"], _money_full(o["wage"]), o["best_role"], f"{o['best_role_score']:.1f}", f"{o['ratio']:.1f}",
                 ", ".join(f"{a} {v}" for a, v in o["weaknesses"])]
                for o in wage["wage_outliers"]
            ],
        ),
        "Best-value contracts (young, high fit, below-median wage):",
        _table(
            ["Player", "Age", "Wage/w", "Best role", "Score"],
            [[b["player"], str(b["age"]), _money_full(b["wage"]), b["best_role"], f"{b['best_role_score']:.1f}"] for b in wage["best_value_contracts"]],
        ),
        "Position-group wage cost:",
        _table(
            ["Group", "Weekly cost", "% of total"],
            [
                [g, _money_full(v), f"{(v / wage['total_weekly'] * 100) if wage['total_weekly'] else 0:.0f}%"]
                for g, v in wage["position_cost"].items()
            ],
        ),
    ]
    if wage["position_cost_flagged"]:
        parts.append(f"Flagged (>45% of wage bill): {', '.join(wage['position_cost_flagged'])}")
    return "\n\n".join(parts)


def _render_money(wage: dict, audit: dict) -> str:
    """Old Section 5 (Wage Bill) plus the value-created block from old
    Section 11 (Squad Audit) — report-restructure.md stage 1."""
    parts = [_render_wage(wage)]
    if audit.get("total_value_created") is not None:
        parts.append(
            f"**Value created:** {_money_full(audit['total_value_created'])} across "
            f"{audit['players_with_value_data']} players with a known purchase fee "
            f"(bought for {_money_full(audit['total_purchase_spend'])} total)."
        )
    return "\n\n".join(parts)


def _render_decisive(decisive: dict) -> str:
    c, s, f = decisive["ceiling"], decisive["structure"], decisive["floor"]
    parts = [
        f"- **Ceiling:** {c['player']} — {c['role']} {c['score']:.1f}" + (" (young)" if c["is_young"] else ""),
        f"- **Structure:** {s['player']} — {s['roles_at_65plus']} roles at 65+",
        f"- **Floor:** {f['player']} — {f['role']} {f['score']:.1f}, {_money_full(f['wage'])}/w",
    ]
    lb = decisive["load_bearing"]
    if lb:
        parts.append("Load-bearing players (sole strong option at a starting-XI role):")
        parts.append(
            _table(
                ["Player", "Role", "Slot", "Score", "Next best alternative"],
                [
                    [d["player"], d["role"], d["slot"], f"{d['score']:.1f}",
                     f"{d['next_best']} ({d['next_best_score']:.1f})" if d["next_best"] else "none"]
                    for d in lb
                ],
            )
        )
    else:
        parts.append("Load-bearing players: none identified.")
    return "\n".join(parts)


def _render_recruitment(recruitment: list[dict]) -> str:
    rows = []
    for r in recruitment:
        floors = ", ".join(f"{a} {v}+" for a, v in r["profile"]["attribute_floors"].items())
        primary = f"{floors}; age {r['profile']['age_range']}"

        fallback = "-"
        fb = r.get("fallback_profile")
        if fb:
            fb_floors = ", ".join(f"{a} {v}+" for a, v in fb["attribute_floors"].items())
            fallback = f"{fb_floors}; age {fb['age_range']}"

        cost = "not known — add --market for a real figure"
        ceiling = r.get("cost_ceiling")
        if ceiling:
            cost = f"{_money(ceiling['low'])}-{_money(ceiling['high'])}"

        rows.append([r["role"], r["rationale"], primary, fallback, cost])
    return _table(["Role", "Rationale", "Primary profile", "Fallback profile", "Cost ceiling"], rows)


def _render_window_budget(wb: dict) -> str:
    if wb.get("transfer_budget") is None and wb.get("wage_budget") is None:
        return "No budget specified — profiles and priorities shown without a spend ceiling."

    lines = [
        f"- Transfer budget: {_money_full(wb['transfer_budget']) if wb['transfer_budget'] is not None else 'not specified'}",
        f"- Wage budget: {_money_full(wb['wage_budget']) + '/w' if wb['wage_budget'] is not None else 'not specified'}",
    ]
    if wb.get("exit_proceeds_low") is not None:
        lines.append(
            f"- Expected exit proceeds: {_money(wb['exit_proceeds_low'])}-{_money(wb['exit_proceeds_high'])}"
        )
        if wb.get("available_transfer_budget") is not None:
            lines.append(
                f"- Available to spend (budget + low end of exit proceeds): {_money(wb['available_transfer_budget'])}"
            )
    if wb.get("priorities_costed"):
        lines.append(
            f"- Priorities costed from the Target Dossier: {wb['priorities_costed']}/{wb['priorities_total']}, "
            f"totalling {_money(wb['priority_cost_low'])}-{_money(wb['priority_cost_high'])}"
        )
        if wb.get("reconciliation") is not None:
            sign = "headroom" if wb["reconciliation"] >= 0 else "shortfall"
            lines.append(f"- Reconciliation (worst case): {_money(abs(wb['reconciliation']))} {sign}")
    else:
        lines.append("- Priority costs: not known yet — add --market for real cost ceilings from Target Dossier candidates.")
    return "\n".join(lines)


def _render_exits(exits: list[dict]) -> str:
    rows = []
    for e in exits:
        value_now = _money(e["value_now"]) if e.get("value_now") is not None else "unknown"
        proj_1yr = _money(e["projected_value_1yr"]) if e.get("projected_value_1yr") is not None else "insufficient data"
        proj_2yr = _money(e["projected_value_2yr"]) if e.get("projected_value_2yr") is not None else "insufficient data"
        trend = e.get("value_trend") or "-"
        replacement = "see Target Dossier" if e.get("has_replacement_case") else "-"
        rows.append([
            e["player"], str(e["age"]), _money_full(e["wage"]), e["best_role"] or "-", f"{e['best_role_score']:.1f}",
            ", ".join(e["reasons"]), value_now, proj_1yr, proj_2yr, trend, replacement,
        ])
    return _table(
        ["Player", "Age", "Wage/w", "Best role", "Score", "Reasons",
         "Value now", "Value +1yr", "Value +2yr", "Trend", "Replacement"],
        rows,
    )


def _lead_row(need: str, top: Optional[dict], rationale: str) -> list[str]:
    if not top:
        return [need, "none found in range", "-", "-", "-", "-", rationale]
    lead = top["player"] + (f" ({top['club']})" if top.get("club") else "")
    style = f"{top['style_score']:.1f}" if top.get("style_score") is not None else "—"
    value = f"{_money(top['value_low'])}-{_money(top['value_high'])}" if top.get("value_low") is not None else "unknown"
    return [need, lead, f"{top['role_score']:.1f}", style, value, _money_full(top["wage"]), rationale]


def _render_targets_lead_table(dossier: list[dict], recruitment: list[dict]) -> str:
    """One row per recruitment priority (tagged Buy #N, matching the
    decision board's own numbering) and one row per exit-replacement
    dossier entry (tagged REPLACES <player>) — report-restructure.md
    stage 3. This is the only place named market candidates surface
    before the full dossier detail further down; Section 9's own
    recruitment/exit prose stays profile-only either way.
    """
    rows = []
    recruitment_entries = [e for e in dossier if e.get("kind") == "recruitment"]
    for i, entry in enumerate(recruitment_entries, start=1):
        candidates = entry.get("candidates") or []
        top = candidates[0] if candidates else None
        rows.append(_lead_row(f"Buy #{i} — {entry['role']}", top, entry["rationale"]))

    for entry in dossier:
        if entry.get("kind") not in ("exit_replacement_listed", "exit_replacement_valuable"):
            continue
        candidates = entry.get("candidates") or []
        top = candidates[0] if candidates else None
        rows.append(_lead_row(f"REPLACES {entry['slot']}", top, entry["rationale"]))

    if not rows:
        return ""
    return _table(["Need", "Lead candidate", "Role score", "Style score", "Walk-away", "Wage/w", "Case"], rows)


def _render_age_profile(age_profile: dict) -> str:
    rows = [
        [b, str(age_profile["bucket_counts"][b]), f"{age_profile['bucket_quality'][b]:.1f}"]
        for b in ["U21", "21-24", "25-28", "29-32", "33+"]
    ]
    parts = [
        _table(["Age band", "Count", "Avg best-role-score"], rows),
        f"Aging positions (2+ starters 30+): {', '.join(age_profile['aging_positions']) or 'none'}",
        f"Youth pipeline positions (U21 at 65+): {', '.join(age_profile['youth_pipeline_positions']) or 'none'}",
    ]
    return "\n\n".join(parts)


def _render_strategic_outlook(outlook: dict) -> str:
    def priority_line(r: dict) -> str:
        ceiling = r.get("cost_ceiling")
        cost = f"{_money(ceiling['low'])}-{_money(ceiling['high'])}" if ceiling else "cost not known yet"
        return f"- **{r['role']}** ({r['slot']}) — {r['rationale']} — {cost}"

    this_window = outlook.get("this_window") or []
    next_window = outlook.get("next_window") or []

    parts = ["**This window:**"]
    parts.append(
        "\n".join(priority_line(r) for r in this_window) if this_window
        else "No recruitment priorities identified."
    )

    parts.append("**Next window:**")
    if not outlook.get("has_budget"):
        parts.append("Not yet knowable — no transfer budget set to test affordability against.")
    elif next_window:
        parts.append("\n".join(priority_line(r) for r in next_window))
    else:
        parts.append("Nothing deferred — this window's budget covers every costed priority.")

    parts.append("**12-month view:**")
    aging = outlook.get("aging_positions") or []
    youth = outlook.get("youth_pipeline_positions") or []
    parts.append(f"- Aging positions (2+ starters 30+): {', '.join(aging) or 'none'}")
    parts.append(f"- Youth pipeline cover already emerging: {', '.join(youth) or 'none'}")

    return "\n\n".join(parts)


def _render_squad_audit(audit: dict, collapse_mismatches: bool = False) -> str:
    if not audit.get("has_data"):
        return (
            "Not available in this export. Add Actual Playing Time, Agreed Playing Time, Mins, "
            "and Last Trans. Fee columns to the squad view to unlock the squad audit."
        )

    counts = audit["tier_counts"]
    counts_desc = " · ".join(f"{n} {tier.lower()}" for tier, n in counts.items() if n)
    parts = [f"**Tier breakdown:** {counts_desc}"]

    if audit["total_value_created"] is not None:
        parts.append(
            f"**Value created:** {_money_full(audit['total_value_created'])} across "
            f"{audit['players_with_value_data']} players with a known purchase fee "
            f"(bought for {_money_full(audit['total_purchase_spend'])} total, now worth that plus the above, "
            f"combined)."
        )

    exit_saleable = sorted(
        (e for e in audit["entries"] if e["tier"] in ("Exit", "Saleable")),
        key=lambda e: e["tier"],
    )
    if exit_saleable:
        rows = [
            [
                e["player"], e["tier"], e["actual_playing_time"] or "-",
                _money_full(e["last_transfer_fee"]),
                f"{_money(e['current_value_low'])}-{_money(e['current_value_high'])}"
                if e["current_value_low"] is not None else "unknown",
            ]
            for e in exit_saleable
        ]
        parts.append("Exit / saleable players:")
        parts.append(_table(["Player", "Tier", "Status", "Bought for", "Now worth"], rows))

    if audit["mismatches"]:
        rows = [[m["player"], m["agreed"], m["actual"]] for m in audit["mismatches"]]
        mismatches_table = _table(["Player", "Agreed", "Actual"], rows)
        # Collapsed only for free mode's direct display (see _free_mode_report).
        # The API-mode call site feeds this as LLM context, not final display
        # markup — literal <details> tags there would just be noise the model
        # has to ignore, since it writes its own prose/table for this content.
        if collapse_mismatches:
            parts.append(
                f"<details><summary>Playing-time promise mismatches ({len(audit['mismatches'])}) — agreed vs. actual</summary>\n\n"
                + mismatches_table + "\n\n</details>"
            )
        else:
            parts.append(f"Playing-time promise mismatches ({len(audit['mismatches'])}) — agreed vs. actual:")
            parts.append(mismatches_table)

    if audit.get("injury_risks"):
        rows = [[r["player"], r["tier"], r["injury"]] for r in audit["injury_risks"]]
        parts.append(
            f"Recurring injury risk ({len(audit['injury_risks'])}) — history of injury trouble, "
            f"not necessarily injured right now. Core/Rotation entries are the higher-consequence ones:"
        )
        parts.append(_table(["Player", "Tier", "Recurring issue"], rows))

    return "\n\n".join(parts)


# Order matches SECTION_12_BLOCK's 5 sub-headings exactly.
TARGET_DOSSIER_GROUPS = [
    ("recruitment", "Must sign — irrespective of outgoings"),
    ("exit_replacement_listed", "If a transfer-listed player leaves"),
    ("exit_replacement_valuable", "If we choose to sell a valuable player"),
    ("value_opportunity", "Market opportunities — undervalued on attributes"),
    ("succession", "Squad-wide succession plan"),
]


def _render_target_dossier_entry(entry: dict) -> str:
    rows = []
    for c in entry["candidates"]:
        style = f"{c['style_score']:.1f}" if c["style_score"] is not None else "—"
        contract = c["contract_end"] or "unknown"
        if c["contract_expiring_soon"]:
            contract += " (expiring soon)"
        value = (
            f"{_money(c['value_low'])}-{_money(c['value_high'])}"
            if c["value_low"] is not None else "unknown"
        )
        player_name = c["player"] + (" (stretch target — over budget)" if c.get("stretch_target") else "")
        rows.append([
            player_name, c["club"] or "unknown", str(c["age"]), f"{c['role_score']:.1f}", style,
            contract, value, _money_full(c["wage"]),
        ])
    kind = entry.get("kind")
    if kind in ("exit_replacement_listed", "exit_replacement_valuable"):
        header = f"**Replacement case: {entry['slot']}** ({entry['role']}, age {entry['age_range']}) — {entry['rationale']}"
    elif kind == "value_opportunity":
        header = f"**Value opportunity: {entry['slot']}** ({entry['role']}, age {entry['age_range']}) — {entry['rationale']}"
    else:
        header = f"**{entry['role']} ({entry['slot']}, age {entry['age_range']})** — {entry['rationale']}"
    table = _table(
        ["Player", "Club", "Age", "Role score", "Style score", "Contract", "Value (walk-away)", "Wage/w"], rows,
    )
    return f"{header}\n\n{table}"


def _render_succession_plan(entries: list[dict]) -> str:
    # One combined compact table, not N full per-entry tables like the other
    # 4 categories — this covers every squad player, so the detailed
    # contract/value/style-score breakdown from _render_target_dossier_entry
    # would make the section unreadably long. Just enough to answer "who
    # could replace this player, and roughly how good are they."
    rows = []
    for entry in entries:
        replacements = ", ".join(f"{c['player']} ({c['role_score']:.1f})" for c in entry["candidates"])
        rows.append([
            entry["slot"], entry.get("tier") or "Unknown",
            str(entry["minutes_played"]) if entry.get("minutes_played") is not None else "unknown",
            entry["role"], replacements or "no candidates in range",
        ])
    return _table(["Player", "Tier", "Minutes", "Best role", "Top 4 replacements"], rows)


def _render_target_dossier(dossier: list[dict], collapse: bool = False) -> str:
    """Full per-candidate detail across all 5 categories — the standing
    caveat now lives at the foot of Section 9 (report-restructure.md stage
    3, alongside the new lead-candidate table), not here, so it's stated
    once, not twice. `collapse` wraps the whole thing in <details> for
    HTML free-mode output only (same pattern as
    _render_squad_audit(collapse_mismatches=...)) — the API-mode call site
    feeds this as LLM context, never collapsed, same reasoning as that
    existing precedent.
    """
    if not dossier:
        return "No market export provided — Target Dossier not available."

    by_kind: dict[str, list[dict]] = {}
    for entry in dossier:
        by_kind.setdefault(entry.get("kind", "recruitment"), []).append(entry)

    parts = []
    for kind, heading in TARGET_DOSSIER_GROUPS:
        parts.append(f"### {heading}")
        entries = by_kind.get(kind, [])
        if not entries:
            parts.append("None currently.")
            continue
        if kind == "succession":
            parts.append(_render_succession_plan(entries))
            continue
        for entry in entries:
            parts.append(_render_target_dossier_entry(entry))
    body = "\n\n".join(parts)

    if collapse:
        return f"<details><summary>Full Target Dossier detail — every candidate, contract, and value</summary>\n\n{body}\n\n</details>"
    return body


def _render_development_pipeline(pipeline: list[dict]) -> str:
    if not pipeline:
        return "No U21 players in this squad."
    rows = [
        [
            p["player"], str(p["age"]), p["best_role"] or "-", f"{p['best_role_score']:.1f}",
            p["tier"] or "Unknown",
            str(p["minutes_played"]) if p["minutes_played"] is not None else "unknown",
            p["recommendation"], p["rationale"],
        ]
        for p in pipeline
    ]
    return _table(
        ["Player", "Age", "Best role", "Score", "Tier", "Minutes", "Recommendation", "Why"], rows,
    )


def _render_housekeeping(audit: dict, pipeline: list[dict], age_profile: dict) -> str:
    """Old Section 11's playing-time mismatches + old Section 13
    (Development Pipeline), plus a condensed age-profile line that old
    Section 9's "12-month view" used to carry — report-restructure.md
    stage 1. The rest of old Section 9 (this-window/next-window) is
    superseded by the decision board + sequencing (stage 2), so it isn't
    reproduced here — restating it would be exactly the duplication this
    restructure exists to remove.
    """
    parts = []
    if audit.get("has_data") and audit.get("mismatches"):
        rows = [[m["player"], m["agreed"], m["actual"]] for m in audit["mismatches"]]
        parts.append(f"Playing-time promise mismatches ({len(audit['mismatches'])}) — agreed vs. actual, a retention risk:")
        parts.append(_table(["Player", "Agreed", "Actual"], rows))

    if audit.get("has_data") and audit.get("injury_risks"):
        rows = [[r["player"], r["tier"], r["injury"]] for r in audit["injury_risks"]]
        parts.append("Recurring injury risk — not necessarily injured now, Core/Rotation entries are the higher-consequence ones:")
        parts.append(_table(["Player", "Tier", "Recurring issue"], rows))

    if pipeline:
        parts.append(_render_development_pipeline(pipeline))

    aging = age_profile.get("aging_positions") or []
    youth = age_profile.get("youth_pipeline_positions") or []
    if aging or youth:
        parts.append(
            f"**Age profile:** aging positions (2+ starters 30+): {', '.join(aging) or 'none'}. "
            f"Youth pipeline cover already emerging: {', '.join(youth) or 'none'}."
        )

    if not parts:
        return "Nothing outstanding."
    return "\n\n".join(parts)


def _decision_board_rows(analysis: "SquadAnalysis") -> list[dict]:
    """Every row here is Python assembly over data that already exists —
    no new analysis (report-restructure.md stage 2). Call/Who/Number are
    the fixed facts; Trigger/Why are a factual Python-written draft (what
    free mode uses as-is) that the API-mode LLM is asked to tighten to one
    clause each, not invent from scratch.
    """
    rows: list[dict] = []

    for c in analysis.exit_candidates:
        who = f"{c['player']} ({c['best_role']} {c['best_role_score']:.1f}, {_money_full(c['wage'])}/w)"
        number = f"Accept {_money(c['value_low'])}+" if c.get("value_low") is not None else "Value unknown"
        trigger = "Any reasonable bid" if "transfer listed" in c["reasons"] else "On acceptable offer"
        why_bits = list(c["reasons"])
        if c.get("value_trend"):
            why_bits.append(f"value {c['value_trend']}")
        rows.append({
            "call": "Sell", "who": who, "number": number, "trigger": trigger,
            "why": "; ".join(why_bits) or "—", "player": c["player"],
        })

    for i, r in enumerate(analysis.recruitment_priorities, start=1):
        ceiling = r.get("cost_ceiling")
        number = f"{_money(ceiling['low'])}-{_money(ceiling['high'])}" if ceiling else "cost unknown"
        rows.append({
            "call": f"Buy #{i}", "who": r["role"], "number": number,
            "trigger": "Immediate, no exit needed", "why": r["rationale"], "player": None,
        })

    decisive = analysis.decisive_players
    ceiling_player = decisive.get("ceiling") or {}
    if ceiling_player.get("player"):
        who = f"{ceiling_player['player']} ({ceiling_player['role']} {ceiling_player['score']:.1f})"
        rows.append({
            "call": "Protect", "who": who, "number": "Retain",
            "trigger": "Before it becomes a problem", "why": "Squad ceiling player — the best fit in the building",
            "player": ceiling_player["player"],
        })

    for d in decisive.get("load_bearing", []):
        if d["player"] == ceiling_player.get("player"):
            continue  # already a Protect row above, don't double up
        next_option = f"next option {d['next_best_score']:.1f}" if d["next_best"] else "no alternative"
        who = f"{d['player']} ({d['role']} {d['score']:.1f})"
        rows.append({
            "call": "Hold", "who": who, "number": "Retain, no like-for-like cover",
            "trigger": "Only with a replacement contracted first",
            "why": f"Sole strong option at the role, {next_option}", "player": d["player"],
        })

    # Players already on the board as a Sell don't also get a Fix row —
    # correcting playing-time paperwork for someone being sold is moot.
    already_selling = {r["player"] for r in rows if r["call"] == "Sell"}
    tier_by_name = {e["player"]: e["tier"] for e in analysis.squad_audit.get("entries", [])}
    for m in analysis.squad_audit.get("mismatches", []):
        if m["player"] in already_selling:
            continue
        tier = tier_by_name.get(m["player"])
        if tier not in ("Core", "Rotation"):
            continue
        rows.append({
            "call": "Fix free", "who": m["player"], "number": "£0", "trigger": "This week",
            "why": f"{tier} player on a {m['agreed']} deal, actually playing like {m['actual']}",
            "player": m["player"],
        })

    return rows


def _render_decision_board(analysis: "SquadAnalysis") -> str:
    rows = _decision_board_rows(analysis)
    if not rows:
        return "No decisions flagged this window."
    table_rows = [[r["call"], r["who"], r["number"], r["trigger"], r["why"]] for r in rows]
    return _table(["Call", "Who", "Number", "Trigger", "Why"], table_rows)


_SEQUENCING_ORDER = {"Fix free": 0, "Sell": 2, "Protect": 3, "Hold": 3}


def _render_sequencing(analysis: "SquadAnalysis") -> str:
    """Default ordering by call type (administrative fixes first, then
    buys in their existing priority order, then sells, then ongoing
    protect/hold calls) — a Python-assembled starting sequence, not a new
    analysis. Stage 4 adds a `gate` field to specific exit rows (e.g. "sell
    only once the replacement is signed") that will need to move that row
    after its corresponding buy; until then this reflects call-type order
    only.
    """
    rows = _decision_board_rows(analysis)
    if not rows:
        return "No sequencing constraints — nothing on the decision board yet."

    def sort_key(r: dict) -> tuple:
        call = r["call"]
        if call.startswith("Buy"):
            return (1, call)
        return (_SEQUENCING_ORDER.get(call, 4), call)

    ordered = sorted(rows, key=sort_key)
    lines = []
    for i, r in enumerate(ordered, start=1):
        who_name = r["who"].split(" (")[0]
        lines.append(f"{i}. **{r['call']} — {who_name}.** {r['why']}")
    return "\n".join(lines)


def _squad_analysis_markdown(analysis: "SquadAnalysis") -> str:
    sections = [
        ("### Headline facts", _render_headline(analysis.headline_facts)),
        (
            "### Decision board (Call/Who/Number are fixed — reproduce exactly; "
            "Trigger/Why below are a factual draft, tighten to one clause each)",
            _render_decision_board(analysis),
        ),
        ("### Sequencing (default order — same rows as the decision board)", _render_sequencing(analysis)),
        ("### Formation viability", _render_formation_viability(analysis.shape_analysis["viability"])),
        ("### Shape", _render_shape(analysis.shape_analysis, analysis.decisive_players, analysis.tactical_style_fit)),
        ("### Role coverage (all 28 roles)", _render_role_coverage(analysis.role_coverage_summary)),
        ("### Tactical impossibilities", _render_tactical(analysis.tactical_impossibilities)),
        ("### Hidden strengths and risks", _render_hidden(analysis.hidden_strengths)),
        ("### Wage analysis", _render_wage(analysis.wage_analysis)),
        ("### Decisive players", _render_decisive(analysis.decisive_players)),
        ("### Window budget (goes at the top of Section 7)", _render_window_budget(analysis.window_budget)),
        ("### Recruitment priorities (profile-only fallback if no Target Dossier data)", _render_recruitment(analysis.recruitment_priorities)),
        ("### Exit candidates", _render_exits(analysis.exit_candidates)),
        ("### Age profile", _render_age_profile(analysis.age_profile)),
        ("### Strategic outlook (Section 9's this window / next window / 12-month view)", _render_strategic_outlook(analysis.strategic_outlook)),
        ("### Squad audit", _render_squad_audit(analysis.squad_audit)),
        ("### Development pipeline", _render_development_pipeline(analysis.development_pipeline)),
    ]
    if analysis.target_dossier:
        sections.append((
            "### Section 9 lead-candidate table (Need/Lead candidate/Number are fixed — reproduce exactly; end Section 9 with the caveat below)",
            _render_targets_lead_table(analysis.target_dossier, analysis.recruitment_priorities)
            + "\n\n**Caveat:** computed from role-fit/style-fit and FM's own value estimate — not a real "
            "scouting report, no guarantee of availability or willingness to move.",
        ))
    return "\n\n".join(f"{heading}\n{body}" for heading, body in sections)


# ---------------------------------------------------------------------------
# Player cards
# ---------------------------------------------------------------------------

def _card_names(analysis: "SquadAnalysis", players: list[Player]) -> set[str]:
    names: set[str] = set()
    for name, _role, _score in analysis.shape_analysis["top_xi"].values():
        names.add(name)
    for d in analysis.decisive_players["load_bearing"]:
        names.add(d["player"])
    for key in ("ceiling", "structure", "floor"):
        p = analysis.decisive_players[key].get("player")
        if p:
            names.add(p)
    for c in analysis.exit_candidates:
        names.add(c["player"])
    for e in analysis.wage_analysis["top5_earners"]:
        names.add(e["player"])

    best_scores = {p.name: (roles.top_roles(p, 1)[0][1] if p.attributes else 0.0) for p in players}
    top5_by_score = sorted(players, key=lambda p: best_scores[p.name], reverse=True)[:5]
    for p in top5_by_score:
        names.add(p.name)
    return names


def _render_card(player: Player) -> str:
    top5 = roles.top_roles(player, 5)
    top5_str = ", ".join(f"{r} {s:.1f}" for r, s in top5)

    header = f"### {player.name} (age {player.age}, {player.height_cm or '?'}cm, {player.nationality or 'unknown'})"
    line2 = (
        f"Wage: {_money_full(player.wage)}/w  Contract: {player.contract_end or 'unknown'}  "
        f"Value: {_money(player.value_low)}-{_money(player.value_high)}  "
        f"Status: {', '.join(player.status) or 'Available'}"
    )
    line3 = f"CA/PA: {player.ca if player.ca is not None else '?'}/{player.pa if player.pa is not None else '?'}  Personality: {player.personality or 'unknown'}"
    line4 = f"Top 5 roles: {top5_str}"

    lines = [header, line2, line3, line4]
    if player.is_goalkeeper:
        gk_line = "Goalkeeping: " + ", ".join(f"{code} {player.attr(a)}" for a, code in GK_SHORT.items())
        lines.append(gk_line)
    else:
        tech_line = "Technical: " + ", ".join(f"{code} {player.attr(a)}" for a, code in TECHNICAL_SHORT.items())
        lines.append(tech_line)
    mental_line = "Mental: " + ", ".join(f"{code} {player.attr(a)}" for a, code in MENTAL_SHORT.items())
    physical_line = "Physical: " + ", ".join(f"{code} {player.attr(a)}" for a, code in PHYSICAL_SHORT.items())
    lines.append(mental_line)
    lines.append(physical_line)
    return "\n".join(lines)


def _render_roster_row(player: Player) -> list[str]:
    top1 = roles.top_roles(player, 1)
    role, score = top1[0] if top1 else ("-", 0.0)
    return [
        player.name, str(player.age), player.position, _money_full(player.wage),
        role, f"{score:.1f}", ", ".join(player.status) or "Available",
    ]


def _card_and_roster_sections(analysis: "SquadAnalysis", players: list[Player]) -> tuple[str, str]:
    card_names = _card_names(analysis, players)
    players_by_name = {p.name: p for p in players}

    carded = [players_by_name[n] for n in card_names if n in players_by_name]
    carded.sort(key=lambda p: roles.top_roles(p, 1)[0][1] if roles.top_roles(p, 1) else 0, reverse=True)
    cards_md = "\n\n".join(_render_card(p) for p in carded)

    remaining = [p for p in players if p.name not in card_names]
    remaining.sort(key=lambda p: roles.top_roles(p, 1)[0][1] if roles.top_roles(p, 1) else 0, reverse=True)
    roster_rows = [_render_roster_row(p) for p in remaining]
    roster_md = _table(["Name", "Age", "Position", "Wage/w", "Best role", "Score", "Status"], roster_rows)

    return cards_md, roster_md


# ---------------------------------------------------------------------------
# Prompt assembly + API call
# ---------------------------------------------------------------------------

# v2 schema (report-restructure.md stage 1). Sections 2-3 are reserved for
# stage 2 (decision board / sequencing) — the template below explicitly
# tells the model to skip that gap rather than invent content for it.
# Target Dossier isn't merged into Section 9 yet (that's stage 3) — it's
# still appended as its own unnumbered block, exactly as before, just moved
# to sit after the new Section 10 instead of after old Section 11.
SECTION_8_BLOCK = """
## 8. AGAINST THE DIVISION
A table — Position group | Players | Avg score | Avg league %ile (or the absolute style-fit scale if no league-context data is present, say so once). If league-context data is present, that's the benchmark against the actual standard of opposition in this division — which position groups hold up and which fall short. One line below the table naming the players who most prove the point. Still no opposition or league players named — the comparison is statistical, never a source of named individuals."""

SECTION_10_BLOCK = """
## 10. HOUSEKEEPING
Only appears when squad-audit data or development-pipeline data is present. A table for playing-time promise mismatches (agreed vs. actual), when present — flagged as a retention risk. A table for recurring injury risk in Core/Rotation players, when present. A table for the development pipeline (every U21 player: role, tier, minutes, recommendation), when present. One line on age profile — aging positions needing renewal, youth pipeline cover already emerging — when material. Skip any of these that have no data rather than padding with an empty table."""

TARGET_DOSSIER_BLOCK = """
## TARGET DOSSIER (appears after Section 10, unnumbered for now)
Only appears when market-file candidates are present. Section 9 above already named the lead candidate for each need — this section is the full shortlist behind each lead, plus the two categories Section 9 doesn't cover at all (market opportunities, succession plan). Don't re-introduce or re-justify a lead candidate here; this is depth, not a second first impression. It carries up to 5 sub-headings, in this exact order, each only present when the Target Dossier data below has entries tagged for it — write a one-line "none currently" note for a sub-heading with no entries rather than omitting it silently. Every sub-heading is a table (candidate detail is inherently tabular — role score, style score, contract, value — don't write it up as prose):
- **Must sign, irrespective of outgoings**: the full shortlist (not just the lead) behind each Section 9 "Buy #N" row — role score, style score if a tactical direction was set, contract situation (flag anyone with a contract expiring within about a year as cheaper to negotiate), and value range as the walk-away price. A candidate marked as a stretch target is a deliberate exception (a genuine step up, shown despite being outside the ordinary budget split), not an oversight — flag it as exactly that.
- **If [player] leaves (transfer-listed)**: the full shortlist behind each Section 9 "REPLACES [player]" row for an exit who is already transfer-listed — this sale isn't hypothetical.
- **If we choose to sell [player]**: the full shortlist behind each Section 9 "REPLACES [player]" row for a proactive, funding-driven sale rather than a forced one — don't imply the club has already decided to sell these.
- **Market opportunities**: a table of players priced well below what their role-fit attributes should command in this market — not tied to any squad gap or incumbent, so frame these explicitly as bargains worth knowing about, not a coverage need. Include the value gap the data gives you (e.g. "38% below the going rate for a player of this quality") as its own column or inline.
- **Squad-wide succession plan**: the compact table you're given, every squad player, one row each — reproduce it as given (player, tier, minutes, best role, top 4 replacement candidates with role score), don't expand it into individual write-ups. Frame this explicitly as a contingency index ("who could replace X if they left, for any reason — injury, being poached, anything") rather than a recommendation to sell anyone — the tier and minutes columns explain why the bar differs: a first-team regular needs a like-for-like or better name in that row, a fringe player just needs competent cover.
Do not name any of these candidates, or any other market player, anywhere else in the briefing — Section 9's lead-candidate table and this section are the only two places a market player is ever named."""


def _task_instructions(
    has_style_fit: bool, has_squad_audit: bool = False, has_target_dossier: bool = False,
    has_development_pipeline: bool = False,
) -> str:
    section_8 = SECTION_8_BLOCK if has_style_fit else ""
    section_10 = SECTION_10_BLOCK if (has_squad_audit or has_development_pipeline) else ""
    target_dossier = TARGET_DOSSIER_BLOCK if has_target_dossier else ""
    return f"""## Task

Produce the Director of Football briefing in exactly this section order. Do not add sections, do not merge sections, do not reorder them.

```
# <CLUB NAME IF DERIVABLE, ELSE "SQUAD REVIEW"> — DIRECTOR OF FOOTBALL BRIEFING

## 1. HEADLINE VERDICT
One verdict sentence — the single biggest constraint on what football this squad can play right now. Then one inline stat line: available bodies vs total, goalkeeper cover. Nothing else — the diagnosis happens in the sections that follow.

## 2. THE WINDOW
The decision board below is already assembled — Call, Who, and Number are fixed, reproduce them exactly, in the same row order. For Trigger and Why, tighten the factual draft you're given to one clause each — don't pad, don't invent detail the data doesn't support, and don't restate a fact from another section (cross-reference it: "see Section 5" etc.). One line above the table: how many decisions, roughly how they split (cost money / raise money / cost nothing).

## 3. ORDER OF OPERATIONS
The sequencing below is already assembled in a sensible default order — reproduce it as a numbered list, tightening each line to the same one-clause style as the decision board's Why column. Where two rows have no real dependency between them, say so briefly rather than inventing a reason they must happen in that order.

## 4. THE SHAPE
State the formation the personnel supports (or the override formation, evaluated) in one line. Best XI as a table: Slot | Player | Role | Score | Read — the Read column carries the decisive-player flags (ceiling/structural/floor/load-bearing) and the style-fit read for that player, already given to you pre-computed per player; reproduce it, don't re-derive it. Key dependencies (load-bearing pairs) as a second short table if there's more than one. At most 3 bullets below the table for genuine reasoning a table can't hold (why the block sits where it does; which players suit a specified tactical direction and which don't, citing the attribute driving it) — 1-2 sentences each, cite 1-2 attributes.

## 5. WHAT THIS SQUAD CANNOT DO
A table: Limit | Evidence | Fix. One row per tactical impossibility (numeric evidence, and the recruitment priority that fixes it when one exists) plus one "Absorb losing X" row per load-bearing player — it's exactly as much a hard limit as a missing role. No prose gloss unless two rows share a root cause worth naming in one line.

## 6. EDGES
A short table or bullet list: Flag | Yes/No | Evidence (set-piece asset, set-piece risk, wide pace, youth pipeline, and anything else material). If nothing is flagged, say so in one line and move on — don't pad with a table that has no real rows.

## 7. THE MONEY
One line: total wage bill, and the distribution across positions. A table for worst contracts and a table for best-value contracts — Player | Wage | Score | Note. The value-created figure (bought-for vs. now-worth, aggregated) as one line if present. Close with one sentence on what the wage bill says about squad priorities, only if that verdict isn't obvious from the tables themselves.
{section_8}

## 9. TARGETS
Open with a short budget line only if transfer/wage budget or exit-proceeds data is present: what's available to spend, expected exit proceeds, and how it reconciles against total priority cost when known. Omit this line entirely if no budget data was given at all — do not invent one. Then exactly one of the following two forms, chosen by whether Target Dossier data is present below:
- **No Target Dossier data:** a table — Role | Profile | Fallback profile | Cost ceiling | Rationale — covering every recruitment priority given below, in the order given: do not invent extra ones beyond that list, and do not trim it down to hit a smaller number either — let the data set the count. Profiles are role + attribute floors ("structural LB, left-footed, age 22-27, tackling 13+ crossing 13+ stamina 15+"), NOT a named player. No player named anywhere in this section.
- **Target Dossier data present:** the lead-candidate table you're given — Need | Lead candidate | Role score | Style score | Walk-away | Wage/w | Case — reproduce it as given, one row per recruitment priority (tagged "Buy #N") and one row per exit replacement case (tagged "REPLACES [player]"). Tighten the Case column to one clause if the given rationale runs long, but don't drop the number that grounds it. End the section with the standing caveat you're given verbatim: computed from role-fit/style-fit and FM's own value estimate, not a real scouting report, no guarantee of availability or willingness to move.
Do not build a separate exits table here — Section 2's decision board already carries who's being sold and why; a replaced exit gets its REPLACES row above, an exit without a replacement case needs no further mention here. One sentence below the table identifying the exit that funds the biggest signing, when relevant.
{section_10}
{target_dossier}
```

Rules:
- Follow the section order exactly. Do not add sections, do not merge sections, do not renumber.
- Tables and short lists are the default wherever the section says so above — that's most sections. Reproduce the structure the data already has (the Squad Analysis context is already tabulated for this) rather than dissolving it into paragraphs. Prose is for the handful of places called out above as genuinely needing it — even there, 1-3 sentences, lead with the verdict, cite 1-2 attributes per claim, not a stacked list.
- Every claim must be grounded in the data above. Cite specific attributes and scores inline.
- Section 9 names roles/profiles only when no Target Dossier data is present. When Target Dossier data is present, Section 9's lead-candidate table and the full Target Dossier block below are the only two places a market player is ever named — nowhere else, ever, not even in passing in another section's prose.
- No player is named unless they appear in the data above.
- If league-context data is present, use it to describe how good "good" is at this level (e.g. "excellent in isolation, but only mid-table for this division") — but never name an opposition or league player. League data recalibrates what a tier means; it is never a source of named individuals.
- Whole briefing: 2,000-2,500 words. No section over 350 words. Sections 5, 6, and 10 under 200 words each.
"""


def _context_section(analysis: "SquadAnalysis", objective: Optional[str], formation_override: Optional[str]) -> str:
    style_fit = analysis.tactical_style_fit
    tactic_line = (
        f"not specified — DoF writes without a specific style lens" if not style_fit
        else style_fit["style_label"]
    )
    return (
        "## Context\n"
        f"- Objective: {objective or 'not specified — write at abstract level'}\n"
        f"- Formation override: {formation_override or 'not specified — analyzer identified best-supported shape'}\n"
        f"- Tactical direction: {tactic_line}"
    )


def build_user_message(analysis: "SquadAnalysis", players: list[Player], objective: Optional[str], formation_override: Optional[str]) -> str:
    cards_md, roster_md = _card_and_roster_sections(analysis, players)
    parts = [
        _context_section(analysis, objective, formation_override),
        "## Squad analysis\n" + _squad_analysis_markdown(analysis),
        "## Full player cards\n" + cards_md,
        "## Full squad roster\n" + roster_md,
    ]
    if analysis.target_dossier:
        parts.append(
            "## Target Dossier candidates — Target Dossier material ONLY, never name these players "
            "anywhere else in the report\n" + _render_target_dossier(analysis.target_dossier)
        )
    parts.append(_task_instructions(
        bool(analysis.tactical_style_fit),
        bool(analysis.squad_audit.get("has_data")),
        bool(analysis.target_dossier),
        bool(analysis.development_pipeline),
    ))
    return "\n\n".join(parts)


def _call_claude(system_prompt: str, user_message: str, config: Config) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=config.api_key)
    response = client.messages.create(
        model=config.model,
        max_tokens=config.max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )
    return "".join(block.text for block in response.content if block.type == "text")


def _render_league_comparison(style_fit: dict) -> str:
    league_ctx = style_fit.get("league_context")
    counts = style_fit["tier_counts"]
    counts_desc = " · ".join(f"{n} {label.lower()}" for label, n in counts.items())

    if not league_ctx:
        return (
            f"**{style_fit['style_label']}** — absolute scale only, no league import provided.\n\n"
            f"Squad-wide: {counts_desc}."
        )

    groups: dict[str, list[tuple[float, Optional[float]]]] = {}
    for _name, position_group, score, _tier, pct, _league_tier in league_ctx["player_scores"]:
        groups.setdefault(position_group, []).append((score, pct))

    rows = []
    for group in tactics.POSITION_GROUPS:
        entries = groups.get(group)
        if not entries:
            continue
        avg_score = sum(s for s, _ in entries) / len(entries)
        pcts = [p for _, p in entries if p is not None]
        avg_pct = sum(pcts) / len(pcts) if pcts else None
        rows.append([
            group, str(len(entries)), f"{avg_score:.1f}",
            f"{avg_pct:.0f}%" if avg_pct is not None else "no league data",
        ])

    parts = [
        f"**{style_fit['style_label']}** — benchmarked against {league_ctx['league_player_count']} players "
        f"across {league_ctx['league_club_count']} clubs.",
        f"Squad-wide (absolute): {counts_desc}.",
        _table(["Position group", "Players", "Avg score", "Avg league %ile"], rows),
    ]
    if league_ctx["sparse_apps_warning"]:
        parts.append(
            "Apps data is sparse league-wide — this benchmark is currently behaving like an unweighted "
            "average across the league rather than favouring regular starters."
        )
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Free mode
# ---------------------------------------------------------------------------

def _free_mode_report(
    analysis: "SquadAnalysis", players: list[Player], objective: Optional[str], formation_override: Optional[str],
    collapse_mismatches: bool = False,
) -> str:
    # v2 schema (report-restructure.md stages 1-2).
    h = analysis.headline_facts
    shape = analysis.shape_analysis
    lines = [
        "# FM Save Copilot — Analytical mode (no DoF narrative)",
        "No API key found — this is deterministic analyzer output only. Configure `config.yaml` or `ANTHROPIC_API_KEY` for a full narrative briefing.",
        "",
        _context_section(analysis, objective, formation_override),
        "",
        f"## {SECTION_HEADERS[0]}",
        _render_headline_compact(h),
        "",
        f"## {SECTION_HEADERS[1]}",
        _render_decision_board(analysis),
        "",
        f"## {SECTION_HEADERS[2]}",
        _render_sequencing(analysis),
        "",
        f"## {SECTION_HEADERS[3]}",
        _render_shape(shape, analysis.decisive_players, analysis.tactical_style_fit),
        "",
        f"## {SECTION_HEADERS[4]}",
        _render_cannot_do(analysis.tactical_impossibilities, analysis.recruitment_priorities, analysis.decisive_players),
        "",
        f"## {SECTION_HEADERS[5]}",
        _render_hidden(analysis.hidden_strengths),
        "",
        f"## {SECTION_HEADERS[6]}",
        _render_money(analysis.wage_analysis, analysis.squad_audit),
    ]
    if analysis.tactical_style_fit:
        lines += [
            "",
            f"## {SECTION_HEADERS[7]}",
            _render_league_comparison(analysis.tactical_style_fit),
        ]
    lines += [
        "",
        f"## {SECTION_HEADERS[8]}",
        _render_window_budget(analysis.window_budget),
        "",
    ]
    if analysis.target_dossier:
        # Un-isolated (report-restructure.md stage 3): named leads land
        # here, right next to the profile/rationale that motivated them —
        # not 3,000 words away in a separate, unnumbered block. The old
        # profile-only recruitment table and the exits table both get
        # superseded here: Sell facts already live in Section 2's decision
        # board, and every replaced exit gets a REPLACES row below instead.
        lead_table = _render_targets_lead_table(analysis.target_dossier, analysis.recruitment_priorities)
        lines.append(lead_table or "No lead candidates in range for any priority.")
        lines.append("")
        lines.append(
            "**Caveat:** computed from role-fit/style-fit and FM's own value estimate — not a real "
            "scouting report, no guarantee of availability or willingness to move."
        )
    else:
        lines.append(_render_recruitment(analysis.recruitment_priorities))
        lines.append("")
        lines.append(_render_exits(analysis.exit_candidates))
    if analysis.squad_audit.get("has_data") or analysis.development_pipeline:
        lines += [
            "",
            f"## {SECTION_HEADERS[9]}",
            _render_housekeeping(analysis.squad_audit, analysis.development_pipeline, analysis.age_profile),
        ]
    if analysis.target_dossier:
        lines += [
            "",
            "## TARGET DOSSIER",
            _render_target_dossier(analysis.target_dossier, collapse=collapse_mismatches),
        ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def generate(
    analysis: "SquadAnalysis",
    players: list[Player],
    objective: Optional[str],
    formation_override: Optional[str],
    config: Config,
    out_path: str,
) -> None:
    is_html_output = Path(out_path).suffix.lower() != ".md"

    if config.free_mode:
        # <details> collapsing is an HTML-rendering feature — only ask for it
        # when the output is actually going to be rendered as HTML, so a
        # .md request stays plain markdown with no raw HTML tags in it.
        report_text = _free_mode_report(analysis, players, objective, formation_override, collapse_mismatches=is_html_output)
    else:
        system_prompt = (PROMPTS_DIR / "edwards.md").read_text()
        user_message = build_user_message(analysis, players, objective, formation_override)
        report_text = _call_claude(system_prompt, user_message, config)

    word_count = len(report_text.split())
    if word_count > 2800:
        print(f"[report] WARNING: {word_count} words — over the 2,000-2,500 word target (report-restructure.md).")

    if Path(out_path).suffix.lower() == ".md":
        Path(out_path).write_text(report_text)
    else:
        Path(out_path).write_text(html_report.generate_html_report(report_text, analysis))

    print(f"Report written to {out_path} ({word_count} words)")
