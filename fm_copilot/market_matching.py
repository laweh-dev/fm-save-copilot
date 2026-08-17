"""Matches real market-file players against recruitment priorities.

This is the only module that produces named-player output. Its result feeds
exactly one place downstream — report.py's Section 12, Target Dossier — and
nowhere else. Reuses the existing role-fit and style-fit engines unchanged;
no new scoring logic.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Optional

from fm_copilot import roles, tactics
from fm_copilot.parser import Player

TOP_N_CANDIDATES = 3


def _age_bounds(age_range: str) -> tuple[int, int]:
    m = re.match(r"(\d+)\s*-\s*(\d+)", age_range)
    if not m:
        return (0, 99)
    return (int(m.group(1)), int(m.group(2)))


def _is_position_eligible(player: Player, required_families: set[str]) -> bool:
    """GitHub issue #3: the candidate pool used to be filtered by age only,
    so a center-back could out-score real attackers on an Advanced Forward
    search purely on attribute overlap and get recommended as a striker
    target. Reuses roles.py's own position-parsing (roles.position_groups)
    and formation-derived role->family mapping (roles.role_eligible_families)
    — the exact same eligibility vocabulary already used for the squad's
    own Best XI selection, not a second parallel implementation.
    """
    for families, _sides in roles.position_groups(player.position):
        if families & required_families:
            return True
    return False


def _contract_years_remaining(contract_end: Optional[str], today: date) -> Optional[int]:
    if not contract_end:
        return None
    m = re.search(r"(20\d{2})", contract_end)
    if not m:
        return None
    return int(m.group(1)) - today.year


def _candidate(player: Player, role: str, style_key: Optional[str], today: date) -> dict:
    role_score = roles.compute_role_scores(player).get(role, 0.0)
    style_score = tactics.compute_style_score(player, style_key) if style_key else None
    years_remaining = _contract_years_remaining(player.contract_end, today)
    return {
        "player": player.name,
        "club": player.club,
        "age": player.age,
        "position": player.position,
        "role": role,
        "role_score": role_score,
        "style_score": style_score,
        "contract_end": player.contract_end,
        "contract_years_remaining": years_remaining,
        "contract_expiring_soon": years_remaining is not None and years_remaining <= 1,
        "value_low": player.value_low,
        "value_high": player.value_high,
        "wage": player.wage,
        "stretch_target": False,
        "attributes": player.attributes,
    }


def _rank_and_limit(candidates: list[dict], budget: Optional[int]) -> list[dict]:
    """Rank by role-fit (style-fit as tiebreaker) and keep the top 3.
    Heavily-unscouted players naturally sink to the bottom — their
    attributes resolve to 0, so no special-casing is needed to keep them
    out of the shortlist.

    When a budget is known, affordable candidates are ranked ahead of ones
    whose value clearly exceeds it — otherwise budget has no effect on who
    gets shortlisted at all, just on a cost figure reported after the fact.
    A candidate over budget still gets a look-in, but only when they're a
    genuine step up (elite-tier, or a clear gap above the best affordable
    option), flagged as a stretch target rather than silently swapped in.
    """
    candidates = sorted(candidates, key=lambda c: (c["role_score"], c["style_score"] or 0.0), reverse=True)
    if budget is None:
        return candidates[:TOP_N_CANDIDATES]

    affordable, stretch = [], []
    for c in candidates:
        (affordable if c["value_low"] is None or c["value_low"] <= budget else stretch).append(c)

    top = affordable[:TOP_N_CANDIDATES]
    if stretch:
        best_stretch = stretch[0]
        best_shown_score = top[0]["role_score"] if top else 0.0
        if best_stretch["role_score"] >= roles.ELITE_THRESHOLD or best_stretch["role_score"] >= best_shown_score + 5:
            best_stretch["stretch_target"] = True
            top.append(best_stretch)

    return top


def build_target_dossier(
    recruitment_priorities: list[dict],
    market_players: list[Player],
    style_key: Optional[str] = None,
    today: Optional[date] = None,
    kind: str = "recruitment",
    budget_per_priority: Optional[int] = None,
) -> list[dict]:
    """For each priority, rank the market pool by role-fit (style-fit as
    tiebreaker) and budget (when known — see _rank_and_limit) and keep the
    top 3, plus a flagged stretch target when one stands out.

    `kind` distinguishes recruitment-driven priorities (Section 7), exit-
    driven replacement cases (Section 8), and market-opportunity upgrades —
    same engine, same section (Section 12), just tagged so the report can
    render them distinctly.
    """
    today = today or date.today()
    dossier: list[dict] = []

    for priority in recruitment_priorities:
        role = priority["role"]
        age_lo, age_hi = _age_bounds(priority["profile"]["age_range"])
        required_families = roles.role_eligible_families(role)
        pool = [
            p for p in market_players
            if age_lo <= p.age <= age_hi and _is_position_eligible(p, required_families)
        ]

        candidates = [_candidate(p, role, style_key, today) for p in pool]
        candidates = _rank_and_limit(candidates, budget_per_priority)

        dossier.append({
            "role": role,
            "slot": priority["slot"],
            "rationale": priority["rationale"],
            "age_range": priority["profile"]["age_range"],
            "candidates": candidates,
            "kind": kind,
        })

    return dossier
