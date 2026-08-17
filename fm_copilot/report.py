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


def _render_target_dossier(dossier: list[dict]) -> str:
    if not dossier:
        return "No market export provided — Target Dossier not available."

    parts = [
        "**Caveat:** computed from role-fit/style-fit and FM's own value estimate — not a real "
        "scouting report, no guarantee of availability or willingness to move."
    ]
    for entry in dossier:
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
        if entry.get("kind") == "exit_replacement":
            header = f"**Replacement case: {entry['slot']}** ({entry['role']}, age {entry['age_range']}) — {entry['rationale']}"
        elif entry.get("kind") == "opportunity":
            header = f"**Upgrade opportunity: {entry['slot']}** ({entry['role']}, age {entry['age_range']}) — {entry['rationale']}"
        else:
            header = f"**{entry['role']} ({entry['slot']}, age {entry['age_range']})** — {entry['rationale']}"
        parts.append(header)
        parts.append(_table(
            ["Player", "Club", "Age", "Role score", "Style score", "Contract", "Value (walk-away)", "Wage/w"], rows,
        ))
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
Squad-wide read on tactical style-fit for the chosen approach. If league-context data is present, benchmark against the actual standard of opposition in this division — which position groups hold up at this level and which fall short, using league percentiles, and name the players who prove the point. If no league-context data is present, give the same read using the absolute style-fit scale instead and say so once. Still no opposition or league players named — the comparison is statistical, never a source of named individuals."""

SECTION_11_BLOCK = """
## 11. SQUAD AUDIT
Only appears when squad-audit data (playing-time status, minutes, purchase fee) is present. A categorised read of the whole squad — core, rotation, filler, saleable, exit — using the club's own playing-time judgement, not a re-derivation from role scores. Name the exit and saleable players specifically, with the value case: what we paid versus what they're worth now. Flag any player where the club's playing-time promise (agreed) doesn't match reality (actual) as a retention risk worth naming. If recurring injury data is present, name any Core or Rotation player with a recurring injury history as an availability risk — it doesn't mean they're injured now, it means squad planning can't fully rely on their minutes."""

SECTION_12_BLOCK = """
## 12. TARGET DOSSIER
Only appears when market-file candidates are present. This is the one and only section in the entire briefing permitted to name a real market player. It carries up to three kinds of entries, all from the Target Dossier data below and all tagged in that data — keep them clearly separated with their own sub-headings:
- Recruitment candidates, tied back to a Section 7 priority: name the shortlisted candidates and tie each one to the priority it fulfils — role score, style score if a tactical direction was set, contract situation (flag anyone with a contract expiring within about a year as cheaper to negotiate), and value range as the walk-away price. When a budget was set, these are already ranked with affordability in mind — a candidate marked as a stretch target is a deliberate exception (a genuine step up, shown despite being outside the ordinary budget split), not an oversight, so name it as exactly that: an outlier worth knowing about, not a like-for-like option with the rest.
- Replacement cases, tied back to a specific Section 8 exit: same candidate detail, framed as "if we sell [player], here's who could replace them" — only present for exits that leave a genuine gap, so treat every one shown as a real case worth making, not a formality.
- An upgrade opportunity, when present: a single, focused pick at a position the squad isn't short on, framed as "here's who could take this XI from good to excellent, and it's affordable" — not a coverage gap, so don't describe it as one. Only ever one of these, so give it a real, standalone case rather than folding it in as an afterthought.
Open the section with the standing caveat: this is computed from role-fit/style-fit and FM's own value estimate, not a real scouting report, and carries no guarantee of availability or willingness to move. Do not name any of these candidates, or any other market player, anywhere else in the briefing — Sections 7 and 8 stay profile-only/reasoning-only, exactly as they are when this section is absent."""

SECTION_13_BLOCK = """
## 13. DEVELOPMENT PIPELINE
Only appears when the squad has at least one U21 player. Each one, named, with a concrete recommendation grounded in the data below — their best role and score, squad-audit tier, and real minutes played this season, not a generic scouting projection. Group the read around the recommendation, not a scroll of individual paragraphs: who to protect and build a contract around, who needs minutes managed while their trajectory plays out, who needs a development loan to get regular first-team football this squad isn't giving them, and who just needs monitoring with no urgent action. Where minutes/tier data isn't present for a player, say plainly that there isn't enough data to judge trajectory rather than guessing."""


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
2-3 paragraphs. Total players vs usable bodies. Availability status breakdown. What football we can play, what we cannot. Set the stakes.

## 2. THE SHAPE
The formation the personnel supports (or the override formation, evaluated). Best XI position by position with roles and scores. Key dependencies (load-bearing pairs). Why the block sits where it sits (based on work rates, stamina, tackling data). If a tactical direction was specified, name specific players who suit it and specific players who don't, citing their style-fit score and the attribute driving it — this is a distinct judgment from role-fit, so a player can be excellent at their role and a poor fit for the chosen style at the same time.

## 3. WHAT THIS SQUAD CANNOT DO
Each tactical impossibility as a paragraph with numeric evidence. Rule out formations, styles, and plan Bs the squad cannot execute.

## 4. HIDDEN STRENGTHS AND EXPLOITABLE EDGES
Set pieces, unusual profiles, unexpected patterns. Include set-piece defensive liabilities alongside offensive assets. If nothing material, say so briefly and move on.

## 5. THE WAGE BILL
Total. Distribution across positions. Worst contracts (named, with reasoning). Best-value contracts (named). The story the wage bill tells about squad priorities.

## 6. DECISIVE PLAYERS
Ceiling player, structural player, floor player, load-bearing players. Each named with reasoning. What breaks if any of them is unavailable.

## 7. RECRUITMENT PRIORITIES
Open with a short budget line only if transfer/wage budget or exit-proceeds data is present: what's available to spend, expected exit proceeds, and how it reconciles against total priority cost when known. Omit this line entirely if no budget data was given at all — do not invent one. Then the priorities: ranked, max 3-4 signings. Each is a role + profile ("experienced backup GK", "structural LB, left-footed, age 22-27, tackling 13+ crossing 13+ stamina 15+"), NOT a named player, plus its fallback profile — a deliberately looser plan B (wider age range, lower floors) for when the primary target isn't gettable. If a cost ceiling is available for a priority, cite it as the expected spend; if not, say the cost isn't known yet rather than guessing a figure. Rationale ties to coverage gaps and tactical needs. If a tactical direction was specified, factor style-fit into the profiles too — a position with adequate role-fit depth can still be a recruitment priority if none of the incumbents suit the chosen style. When both budget and Target Dossier candidates are present, a light sequencing note is welcome — which priority to move on first and why (cheapest, most urgent gap, or the one funding the rest via an exit) — but keep it a sentence, not a week-by-week negotiation plan; don't invent timing detail the data doesn't support.

## 8. EXITS
4-6 players ranked. Each named with reasoning: wage vs contribution, duplicated profile, contract cliff, mood, transfer listed. Where value data supports it, cite the value trend (now vs. projected in 1-2 years) to sharpen the sell-now-vs-hold timing — a declining trend strengthens the case to sell now, a rising one is a reason to weigh the sale more carefully. If the data marks a trend as insufficient, don't force a projection. If a player has a replacement case built, point to Section 12 by name for the detail ("a replacement case for this profile is set out in Section 12") — do not name any market player here, Section 8 stays reasoning-only about the departing player. Include the exit that funds the biggest signing.

## 9. WHAT GOOD LOOKS LIKE
Age profile assessment (quality by age, not just headcount). If recruitment + exits are executed, what this squad becomes over 12-18 months. Concrete grounding — cite ages, contracts, wage headroom created by exits.
{section_10}
{section_11}
{section_12}
{section_13}
```

Rules:
- Follow the section order exactly. Do not add sections, do not merge sections. Sections 10, 11, 12, and 13 exist only when shown above — the briefing stops at the last section actually shown.
- Be concise: lead each point with the verdict, then the minimum evidence. Cite 1-2 attributes per claim, not a stacked list. Not every player earns a full paragraph — group minor names into one sentence and save paragraph treatment for the players the point actually turns on.
- Every claim must be grounded in the data above. Cite specific attributes and scores inline.
- Recruitment (7) names roles/profiles, not specific players; Exits (8) names the departing squad player but never a market replacement. The single exception is Section 12, Target Dossier, when present — that section exists specifically to name real shortlisted market players against Section 7's profiles and Section 8's replacement cases. Nowhere else, ever, names a market player.
- No player is named unless they appear in the data above.
- If league-context data is present, use it to describe how good "good" is at this level (e.g. "excellent in isolation, but only mid-table for this division") — but never name an opposition or league player. League data recalibrates what a tier means; it is never a source of named individuals.
- Prose-led. Tables only where they clarify (top earners table, exit candidates table, recruitment priorities table, target dossier table).
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
