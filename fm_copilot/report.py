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

SECTION_HEADERS = [
    "1. HEADLINE VERDICT", "2. THE SHAPE", "3. WHAT THIS SQUAD CANNOT DO",
    "4. HIDDEN STRENGTHS AND EXPLOITABLE EDGES", "5. THE WAGE BILL", "6. DECISIVE PLAYERS",
    "7. RECRUITMENT PRIORITIES", "8. EXITS", "9. WHAT GOOD LOOKS LIKE",
    "10. HOW WE COMPARE TO THE LEAGUE",
    "11. SQUAD AUDIT",
    "12. TARGET DOSSIER",
    "13. DEVELOPMENT PIPELINE",
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


def _render_shape(shape: dict, style_fit: Optional[dict] = None) -> str:
    parts = [f"**Top formation:** {shape['top_formation']} (avg {shape['top_xi_avg_score']:.1f})"]
    xi_rows = [
        [slot, name, role, f"{score:.1f}"]
        for slot, (name, role, score) in shape["top_xi"].items()
    ]
    parts.append(_table(["Slot", "Player", "Role", "Score"], xi_rows))

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
        parts.append(_render_style_fit(style_fit))
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
        replacement = "see Section 12" if e.get("has_replacement_case") else "-"
        rows.append([
            e["player"], str(e["age"]), _money_full(e["wage"]), e["best_role"] or "-", f"{e['best_role_score']:.1f}",
            ", ".join(e["reasons"]), value_now, proj_1yr, proj_2yr, trend, replacement,
        ])
    return _table(
        ["Player", "Age", "Wage/w", "Best role", "Score", "Reasons",
         "Value now", "Value +1yr", "Value +2yr", "Trend", "Replacement"],
        rows,
    )


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


def _render_target_dossier(dossier: list[dict]) -> str:
    if not dossier:
        return "No market export provided — Target Dossier not available."

    by_kind: dict[str, list[dict]] = {}
    for entry in dossier:
        by_kind.setdefault(entry.get("kind", "recruitment"), []).append(entry)

    parts = [
        "**Caveat:** computed from role-fit/style-fit and FM's own value estimate — not a real "
        "scouting report, no guarantee of availability or willingness to move."
    ]
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
    return "\n\n".join(parts)


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


def _squad_analysis_markdown(analysis: "SquadAnalysis") -> str:
    sections = [
        ("### Headline facts", _render_headline(analysis.headline_facts)),
        ("### Formation viability", _render_formation_viability(analysis.shape_analysis["viability"])),
        ("### Shape", _render_shape(analysis.shape_analysis, analysis.tactical_style_fit)),
        ("### Role coverage (all 28 roles)", _render_role_coverage(analysis.role_coverage_summary)),
        ("### Tactical impossibilities", _render_tactical(analysis.tactical_impossibilities)),
        ("### Hidden strengths and risks", _render_hidden(analysis.hidden_strengths)),
        ("### Wage analysis", _render_wage(analysis.wage_analysis)),
        ("### Decisive players", _render_decisive(analysis.decisive_players)),
        ("### Window budget (goes at the top of Section 7)", _render_window_budget(analysis.window_budget)),
        ("### Recruitment priorities", _render_recruitment(analysis.recruitment_priorities)),
        ("### Exit candidates", _render_exits(analysis.exit_candidates)),
        ("### Age profile", _render_age_profile(analysis.age_profile)),
        ("### Strategic outlook (Section 9's this window / next window / 12-month view)", _render_strategic_outlook(analysis.strategic_outlook)),
        ("### Squad audit", _render_squad_audit(analysis.squad_audit)),
        ("### Development pipeline", _render_development_pipeline(analysis.development_pipeline)),
    ]
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

SECTION_10_BLOCK = """
## 10. HOW WE COMPARE TO THE LEAGUE
A table — Position group | Players | Avg score | Avg league %ile (or the absolute style-fit scale if no league-context data is present, say so once). If league-context data is present, that's the benchmark against the actual standard of opposition in this division — which position groups hold up and which fall short. One line below the table naming the players who most prove the point. Still no opposition or league players named — the comparison is statistical, never a source of named individuals."""

SECTION_11_BLOCK = """
## 11. SQUAD AUDIT
Only appears when squad-audit data (playing-time status, minutes, purchase fee) is present. Lead with the tier breakdown in one line (core/rotation/filler/saleable/exit counts). Then a table for exit and saleable players specifically — Player | Tier | Bought for | Now worth — using the club's own playing-time judgement, not a re-derivation from role scores. If any player's playing-time promise (agreed) doesn't match reality (actual), a short table of those too, flagged as a retention risk. If recurring injury data is present, a short table of any Core or Rotation player with a recurring injury history — it doesn't mean they're injured now, it means squad planning can't fully rely on their minutes."""

SECTION_12_BLOCK = """
## 12. TARGET DOSSIER
Only appears when market-file candidates are present. This is the one and only section in the entire briefing permitted to name a real market player. It carries up to 5 sub-headings, in this exact order, each only present when the Target Dossier data below has entries tagged for it — write a one-line "none currently" note for a sub-heading with no entries rather than omitting it silently. Every sub-heading is a table (candidate detail is inherently tabular — role score, style score, contract, value — don't write it up as prose):
- **Must sign, irrespective of outgoings**: a table tied back to each Section 7 priority — the shortlisted candidates against the priority they fulfil, with role score, style score if a tactical direction was set, contract situation (flag anyone with a contract expiring within about a year as cheaper to negotiate), and value range as the walk-away price. When a budget was set, these are already ranked with affordability in mind — a candidate marked as a stretch target is a deliberate exception (a genuine step up, shown despite being outside the ordinary budget split), not an oversight, so flag it as exactly that: an outlier worth knowing about, not a like-for-like option with the rest.
- **If [player] leaves (transfer-listed)**: a table of replacement cases tied to a specific Section 8 exit who is already transfer-listed — framed as "the club has already decided to sell [player]; here's who could replace them", since this sale isn't hypothetical.
- **If we choose to sell [player]**: a table of replacement cases for other genuine sell candidates (Core/Rotation tier or load-bearing) who are not transfer-listed — framed as a proactive, funding-driven sale rather than a forced one: "if we chose to cash in on [player], here's the replacement case" — don't imply the club has already decided to sell these.
- **Market opportunities**: a table of players priced well below what their role-fit attributes should command in this market — not tied to any squad gap or incumbent, so frame these explicitly as bargains worth knowing about, not a coverage need. Include the value gap the data gives you (e.g. "38% below the going rate for a player of this quality") as its own column or inline.
- **Squad-wide succession plan**: the compact table you're given, every squad player, one row each — reproduce it as given (player, tier, minutes, best role, top 4 replacement candidates with role score), don't expand it into individual write-ups. Frame this explicitly as a contingency index ("who could replace X if they left, for any reason — injury, being poached, anything") rather than a recommendation to sell anyone — the tier and minutes columns explain why the bar differs: a first-team regular needs a like-for-like or better name in that row, a fringe player just needs competent cover.
Open the section with the standing caveat: this is computed from role-fit/style-fit and FM's own value estimate, not a real scouting report, and carries no guarantee of availability or willingness to move. Do not name any of these candidates, or any other market player, anywhere else in the briefing — Sections 7 and 8 stay profile-only/reasoning-only, exactly as they are when this section is absent."""

SECTION_13_BLOCK = """
## 13. DEVELOPMENT PIPELINE
Only appears when the squad has at least one U21 player. A table: Player | Age | Best role/score | Tier | Minutes | Recommendation — covering every U21 player, grounded in the data below, not a generic scouting projection. Recommendation is one of: protect the contract, don't rotate; manage minutes, review for extension; development loan; monitor, no urgent action — or "not enough data" where minutes/tier data isn't present for a player, rather than guessing. One line below the table only if there's a genuine cross-player pattern worth naming (e.g. a cluster all needing loans at once)."""


def _task_instructions(
    has_style_fit: bool, has_squad_audit: bool = False, has_target_dossier: bool = False,
    has_development_pipeline: bool = False,
) -> str:
    section_10 = SECTION_10_BLOCK if has_style_fit else ""
    section_11 = SECTION_11_BLOCK if has_squad_audit else ""
    section_12 = SECTION_12_BLOCK if has_target_dossier else ""
    section_13 = SECTION_13_BLOCK if has_development_pipeline else ""
    return f"""## Task

Produce the Director of Football briefing in exactly this section order. Do not add sections, do not merge sections, do not reorder them.

```
# <CLUB NAME IF DERIVABLE, ELSE "SQUAD REVIEW"> — DIRECTOR OF FOOTBALL BRIEFING

## 1. HEADLINE VERDICT
2-3 sentences, not paragraphs. Total players vs usable bodies, the availability breakdown as a short inline stat line (not a sentence per status), what football we can play and can't. Set the stakes and move on — the diagnosis happens in the sections that follow, this one doesn't need to pre-empt them.

## 2. THE SHAPE
State the formation the personnel supports (or the override formation, evaluated) in one line. Best XI as a table: Slot | Player | Role | Score. Key dependencies (load-bearing pairs) as a second short table or list if there's more than one. Then, in prose (2-3 sentences): why the block sits where it sits (work rate, stamina, tackling data), and — if a tactical direction was specified — which specific players suit it and which don't, citing their style-fit score and the attribute driving it. This judgment is genuinely a paragraph's job (it's reasoning, not a list), so it's the exception here, not the pattern.

## 3. WHAT THIS SQUAD CANNOT DO
A table: Impossibility | Evidence. One row per tactical impossibility, numeric evidence in the second column. A one-line prose gloss above the table only if there's a genuine connecting point across more than one row (e.g. two impossibilities that share a root cause) — otherwise the table stands alone.

## 4. HIDDEN STRENGTHS AND EXPLOITABLE EDGES
A short table or bullet list: Flag | Yes/No | Evidence (set-piece asset, set-piece risk, wide pace, youth pipeline, and anything else material). If nothing is flagged, say so in one line and move on — don't pad with a table that has no real rows.

## 5. THE WAGE BILL
One line: total, and the distribution across positions. Then a table for worst contracts and a table (or the same table, tagged) for best-value contracts — Player | Wage | Score | Note. Close with one sentence on what the wage bill says about squad priorities, only if that verdict isn't obvious from the tables themselves.

## 6. DECISIVE PLAYERS
A table: Role | Player | Score | What breaks if unavailable — covering the ceiling player, structural player, floor player, and every load-bearing player. This is a table by nature (4+ named items, same 4 facts each) — don't expand it back into individual paragraphs.

## 7. RECRUITMENT PRIORITIES
Open with a short budget line only if transfer/wage budget or exit-proceeds data is present: what's available to spend, expected exit proceeds, and how it reconciles against total priority cost when known. Omit this line entirely if no budget data was given at all — do not invent one. Then a table — Role | Profile | Fallback profile | Cost ceiling | Rationale — covering every priority given below, in the order given: do not invent extra ones beyond that list, and do not trim it down to hit a smaller number either. The list is already evidence-driven (structural weaknesses, single-point-of-failure positions, tactical impossibilities), so a squad in reasonable shape will naturally show fewer rows and a squad with real structural gaps can genuinely need more than 3 or 4 — let the data set the count, not a target number. Profiles are role + attribute floors ("structural LB, left-footed, age 22-27, tackling 13+ crossing 13+ stamina 15+"), NOT a named player. If a cost ceiling is available cite it; if not, say the cost isn't known yet rather than guessing a figure. If a tactical direction was specified, factor style-fit into the profiles too. When both budget and Target Dossier candidates are present, one sentence on sequencing is welcome below the table — which priority to move on first and why (cheapest, most urgent gap, or the one funding the rest via an exit) — not a week-by-week negotiation plan.

## 8. EXITS
A table: Player | Reason(s) | Value trend | Replacement — 4-6 players, ranked. Reasons: wage vs contribution, duplicated profile, contract cliff, mood, transfer listed. Value trend only where the data supports a projection (now vs. 1-2 years) — leave the cell blank rather than force one. Replacement column reads "see Section 12" for any player with a replacement case built, "-" otherwise — do not name a market player here, Section 8 stays reasoning-only about the departing player. Below the table, one sentence identifying the exit that funds the biggest signing.

## 9. WHAT GOOD LOOKS LIKE
One line on the age profile (quality by age, not just headcount). Then three sub-headings, each a short table or 2-3 line bullet list — every one of them from data already given above, not speculation:
- **This window:** what's actually achievable now — Section 7's priorities, tied to the budget already set (or the full priority list if no budget was given), each tied back to the specific gap it closes.
- **Next window:** priorities that are real and already identified but don't fit within this window's budget — name them as the next thing to fund. If nothing is currently deferred, say so plainly rather than inventing a future need.
- **12-month view:** if recruitment and exits are executed, what this squad becomes over the next year — aging positions needing renewal, youth pipeline positions already covering the gap, wage headroom created by exits. Concrete grounding — cite ages, contracts, specific players.
{section_10}
{section_11}
{section_12}
{section_13}
```

Rules:
- Follow the section order exactly. Do not add sections, do not merge sections. Sections 10, 11, 12, and 13 exist only when shown above — the briefing stops at the last section actually shown.
- Tables and short lists are the default wherever the section says so above — that's most sections. Reproduce the structure the data already has (the Squad Analysis context is already tabulated for this) rather than dissolving it into paragraphs. Prose is for the handful of places called out above as genuinely needing it (Section 2's tactical reasoning, one-line verdicts, connecting sentences) — even there, 1-3 sentences, lead with the verdict, cite 1-2 attributes per claim, not a stacked list.
- Every claim must be grounded in the data above. Cite specific attributes and scores inline.
- Recruitment (7) names roles/profiles, not specific players; Exits (8) names the departing squad player but never a market replacement. The single exception is Section 12, Target Dossier, when present — that section exists specifically to name real shortlisted market players against Section 7's profiles and Section 8's replacement cases. Nowhere else, ever, names a market player.
- No player is named unless they appear in the data above.
- If league-context data is present, use it to describe how good "good" is at this level (e.g. "excellent in isolation, but only mid-table for this division") — but never name an opposition or league player. League data recalibrates what a tier means; it is never a source of named individuals.
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
            "## Target Dossier candidates — Section 12 material ONLY, never name these players "
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
    h = analysis.headline_facts
    shape = analysis.shape_analysis
    lines = [
        "# FM Save Copilot — Analytical mode (no DoF narrative)",
        "No API key found — this is deterministic analyzer output only. Configure `config.yaml` or `ANTHROPIC_API_KEY` for a full narrative briefing.",
        "",
        _context_section(analysis, objective, formation_override),
        "",
        f"## {SECTION_HEADERS[0]}",
        _render_headline(h),
        "",
        f"## {SECTION_HEADERS[1]}",
        _render_shape(shape, analysis.tactical_style_fit),
        "",
        f"## {SECTION_HEADERS[2]}",
        _render_tactical(analysis.tactical_impossibilities),
        "",
        f"## {SECTION_HEADERS[3]}",
        _render_hidden(analysis.hidden_strengths),
        "",
        f"## {SECTION_HEADERS[4]}",
        _render_wage(analysis.wage_analysis),
        "",
        f"## {SECTION_HEADERS[5]}",
        _render_decisive(analysis.decisive_players),
        "",
        f"## {SECTION_HEADERS[6]}",
        _render_window_budget(analysis.window_budget),
        "",
        _render_recruitment(analysis.recruitment_priorities),
        "",
        f"## {SECTION_HEADERS[7]}",
        _render_exits(analysis.exit_candidates),
        "",
        f"## {SECTION_HEADERS[8]}",
        _render_age_profile(analysis.age_profile),
        "",
        _render_strategic_outlook(analysis.strategic_outlook),
    ]
    if analysis.tactical_style_fit:
        lines += [
            "",
            f"## {SECTION_HEADERS[9]}",
            _render_league_comparison(analysis.tactical_style_fit),
        ]
    if analysis.squad_audit.get("has_data"):
        lines += [
            "",
            f"## {SECTION_HEADERS[10]}",
            _render_squad_audit(analysis.squad_audit, collapse_mismatches=collapse_mismatches),
        ]
    if analysis.target_dossier:
        lines += [
            "",
            f"## {SECTION_HEADERS[11]}",
            _render_target_dossier(analysis.target_dossier),
        ]
    if analysis.development_pipeline:
        lines += [
            "",
            f"## {SECTION_HEADERS[12]}",
            _render_development_pipeline(analysis.development_pipeline),
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

    if Path(out_path).suffix.lower() == ".md":
        Path(out_path).write_text(report_text)
    else:
        Path(out_path).write_text(html_report.generate_html_report(report_text, analysis))

    print(f"Report written to {out_path} ({word_count} words)")
