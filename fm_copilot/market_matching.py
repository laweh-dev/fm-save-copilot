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
    }


def build_target_dossier(
    recruitment_priorities: list[dict],
    market_players: list[Player],
    style_key: Optional[str] = None,
    today: Optional[date] = None,
) -> list[dict]:
    """For each recruitment priority, rank the market pool by role-fit (style-fit
    as tiebreaker when a tactic is set) and keep the top 3. Heavily-unscouted
    players naturally sink to the bottom — their attributes resolve to 0, so no
    special-casing is needed to keep them out of the shortlist.
    """
    today = today or date.today()
    dossier: list[dict] = []

    for priority in recruitment_priorities:
        role = priority["role"]
        age_lo, age_hi = _age_bounds(priority["profile"]["age_range"])
        pool = [p for p in market_players if age_lo <= p.age <= age_hi]

        candidates = [_candidate(p, role, style_key, today) for p in pool]
        candidates.sort(key=lambda c: (c["role_score"], c["style_score"] or 0.0), reverse=True)

        dossier.append({
            "role": role,
            "slot": priority["slot"],
            "rationale": priority["rationale"],
            "age_range": priority["profile"]["age_range"],
            "candidates": candidates[:TOP_N_CANDIDATES],
        })

    return dossier
