"""Facts + context -> markdown, via Claude (or free mode without an API key)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Optional

from fm_copilot import roles, tactics
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
        return "_none_"
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
        rows.append([r["role"], r["rationale"], f"{floors}; age {r['profile']['age_range']}"])
    return _table(["Role", "Rationale", "Profile"], rows)


def _render_exits(exits: list[dict]) -> str:
    rows = [
        [e["player"], str(e["age"]), _money_full(e["wage"]), e["best_role"] or "-", f"{e['best_role_score']:.1f}",
         ", ".join(e["reasons"])]
        for e in exits
    ]
    return _table(["Player", "Age", "Wage/w", "Best role", "Score", "Reasons"], rows)


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
        ("### Recruitment priorities", _render_recruitment(analysis.recruitment_priorities)),
        ("### Exit candidates", _render_exits(analysis.exit_candidates)),
        ("### Age profile", _render_age_profile(analysis.age_profile)),
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

TASK_INSTRUCTIONS = """## Task

Produce the Director of Football briefing in exactly this section order. Do not add sections, do not merge sections, do not reorder them.

```
# <CLUB NAME IF DERIVABLE, ELSE "SQUAD REVIEW"> — DIRECTOR OF FOOTBALL BRIEFING

## 1. HEADLINE VERDICT
2-3 paragraphs. Total players vs usable bodies. Availability status breakdown. What football we can play, what we cannot. Set the stakes.

## 2. THE SHAPE
The formation the personnel supports (or the override formation, evaluated). Best XI position by position with roles and scores. Key dependencies (load-bearing pairs). Why the block sits where it sits (based on work rates, stamina, tackling data). If a tactical direction was specified, name specific players who suit it and specific players who don't, citing their style-fit score and the attributes driving it — this is a distinct judgment from role-fit, so a player can be excellent at their role and a poor fit for the chosen style at the same time. If league-context data is present, also say how that fit reads against the standard of this league specifically — a score that looks strong in isolation can be ordinary once benchmarked, and vice versa.

## 3. WHAT THIS SQUAD CANNOT DO
Each tactical impossibility as a paragraph with numeric evidence. Rule out formations, styles, and plan Bs the squad cannot execute.

## 4. HIDDEN STRENGTHS AND EXPLOITABLE EDGES
Set pieces, unusual profiles, unexpected patterns. Include set-piece defensive liabilities alongside offensive assets. If nothing material, say so briefly and move on.

## 5. THE WAGE BILL
Total. Distribution across positions. Worst contracts (named, with reasoning). Best-value contracts (named). The story the wage bill tells about squad priorities.

## 6. DECISIVE PLAYERS
Ceiling player, structural player, floor player, load-bearing players. Each named with reasoning. What breaks if any of them is unavailable.

## 7. RECRUITMENT PRIORITIES
Ranked, max 3-4 signings. Each is a role + profile ("experienced backup GK", "structural LB, left-footed, age 22-27, tackling 13+ crossing 13+ stamina 15+"), NOT a named player. Rationale ties to coverage gaps and tactical needs. If a tactical direction was specified, factor style-fit into the profiles too — a position with adequate role-fit depth can still be a recruitment priority if none of the incumbents suit the chosen style.

## 8. EXITS
4-6 players ranked. Each named with reasoning: wage vs contribution, duplicated profile, contract cliff, mood, transfer listed. Include the exit that funds the biggest signing.

## 9. WHAT GOOD LOOKS LIKE
Age profile assessment (quality by age, not just headcount). If recruitment + exits are executed, what this squad becomes over 12-18 months. Concrete grounding — cite ages, contracts, wage headroom created by exits.
```

Rules:
- Follow the section order exactly. Do not add sections, do not merge sections.
- Every claim must be grounded in the data above. Cite specific attributes and scores inline.
- Recruitment section names roles/profiles, not specific players.
- No player is named unless they appear in the data above.
- If league-context data is present, use it to describe how good "good" is at this level (e.g. "excellent in isolation, but only mid-table for this division") — but never name an opposition or league player. League data recalibrates what a tier means; it is never a source of named individuals.
- Prose-led. Tables only where they clarify (top earners table, exit candidates table, recruitment priorities table).
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
        TASK_INSTRUCTIONS,
    ]
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


# ---------------------------------------------------------------------------
# Free mode
# ---------------------------------------------------------------------------

def _free_mode_report(analysis: "SquadAnalysis", players: list[Player], objective: Optional[str], formation_override: Optional[str]) -> str:
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
        _render_recruitment(analysis.recruitment_priorities),
        "",
        f"## {SECTION_HEADERS[7]}",
        _render_exits(analysis.exit_candidates),
        "",
        f"## {SECTION_HEADERS[8]}",
        _render_age_profile(analysis.age_profile),
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
    if config.free_mode:
        report_text = _free_mode_report(analysis, players, objective, formation_override)
    else:
        system_prompt = (PROMPTS_DIR / "edwards.md").read_text()
        user_message = build_user_message(analysis, players, objective, formation_override)
        report_text = _call_claude(system_prompt, user_message, config)

    Path(out_path).write_text(report_text)
    word_count = len(report_text.split())
    print(f"Report written to {out_path} ({word_count} words)")
