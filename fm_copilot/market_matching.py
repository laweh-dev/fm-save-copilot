"""Matches real market-file players against recruitment priorities.

This is the only module that produces named-player output. Its result feeds
exactly one place downstream — report.py's Section 12, Target Dossier — and
nowhere else. Reuses the existing role-fit and style-fit engines unchanged;
no new scoring logic.
"""

from __future__ import annotations

import re
import statistics
from datetime import date
from typing import Optional

from fm_copilot import roles, tactics
from fm_copilot.parser import Player

TOP_N_CANDIDATES = 3
# 20 looked like a safe floor on paper, but verified against a real market
# export: only ~1 in 20 players in a typical file are fully scouted at all,
# and after the age/quality filter that leaves well under 20 even in a
# normal-sized market. 12 still requires real signal (min 5 pooled
# comparables per score band, enforced separately below) without silently
# disabling the whole feature on realistic data.
VALUE_OPPORTUNITY_MIN_POOL = 12
VALUE_OPPORTUNITY_MIN_COMPARABLES = 5
VALUE_OPPORTUNITY_BAND_WIDTH = 2
VALUE_OPPORTUNITY_BAND_WINDOW = 4
VALUE_OPPORTUNITY_RATIO_CEILING = 0.6


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


def _candidate(
    player: Player, role: str, style_key: Optional[str], today: date,
    score_cache: Optional[dict] = None,
) -> dict:
    # Role score doesn't depend on style_key/today, so it's safe to share
    # across every priority in one build_target_dossier() call — with many
    # priorities searching overlapping position/age pools (e.g. several
    # defenders all searching the same market CBs), this avoids recomputing
    # all 28 role scores for the same player dozens of times. Verified
    # against the real market file: ~3.6x faster for a ~30-priority search,
    # same values either way.
    if score_cache is not None:
        key = id(player)
        if key not in score_cache:
            score_cache[key] = roles.compute_role_scores(player)
        role_score = score_cache[key].get(role, 0.0)
    else:
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


def _rank_and_limit(candidates: list[dict], budget: Optional[int], limit: int = TOP_N_CANDIDATES) -> list[dict]:
    """Rank by role-fit (style-fit as tiebreaker) and keep the top `limit`.
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
        return candidates[:limit]

    affordable, stretch = [], []
    for c in candidates:
        (affordable if c["value_low"] is None or c["value_low"] <= budget else stretch).append(c)

    top = affordable[:limit]
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
    limit: int = TOP_N_CANDIDATES,
) -> list[dict]:
    """For each priority, rank the market pool by role-fit (style-fit as
    tiebreaker) and budget (when known — see _rank_and_limit) and keep the
    top `limit` (3 by default), plus a flagged stretch target when one
    stands out.

    `kind` distinguishes recruitment-driven priorities (Section 7), the two
    flavours of exit-replacement case (transfer-listed vs. a valuable
    proactive sale), and the squad-wide succession plan — same engine, same
    section (Section 12), just tagged so the report can render them
    distinctly under their own sub-headings.
    """
    today = today or date.today()
    dossier: list[dict] = []
    score_cache: dict = {}

    for priority in recruitment_priorities:
        role = priority["role"]
        age_lo, age_hi = _age_bounds(priority["profile"]["age_range"])
        required_families = roles.role_eligible_families(role)
        pool = [
            p for p in market_players
            if age_lo <= p.age <= age_hi and _is_position_eligible(p, required_families)
        ]

        candidates = [_candidate(p, role, style_key, today, score_cache) for p in pool]
        candidates = _rank_and_limit(candidates, budget_per_priority, limit)

        dossier.append({
            "role": role,
            "slot": priority["slot"],
            "rationale": priority["rationale"],
            "age_range": priority["profile"]["age_range"],
            "candidates": candidates,
            "kind": kind,
        })

    return dossier


def find_value_opportunities(
    market_players: list[Player],
    style_key: Optional[str] = None,
    today: Optional[date] = None,
    limit: int = 5,
) -> list[dict]:
    """Scans the whole market for players priced well below what their own
    role-fit quality should command — a genuine bargain, independent of any
    squad gap or incumbent (unlike every other dossier entry, which is
    matched against a specific priority or exit). Judged against a value
    curve built from the market pool itself: the same windowed-median
    approach analyzer.py already uses for age-based value depreciation,
    bucketed by role-score instead of age.

    "Unscouted" players are excluded the same way _rank_and_limit already
    reasons about them — attributes that are all 0 aren't a real signal,
    they're an absence of one.
    """
    today = today or date.today()

    scored: list[tuple[Player, str, float]] = []
    for p in market_players:
        if p.value_low is None or p.value_high is None:
            continue
        if not (17 <= p.age <= 30):
            continue
        if not p.attributes or min(p.attributes.values()) <= 0:
            continue
        top = roles.top_roles(p, 1)
        if not top or top[0][1] < roles.STRONG_THRESHOLD:
            continue
        scored.append((p, top[0][0], top[0][1]))

    if len(scored) < VALUE_OPPORTUNITY_MIN_POOL:
        return []

    def band(score: float) -> int:
        return round(score / VALUE_OPPORTUNITY_BAND_WIDTH) * VALUE_OPPORTUNITY_BAND_WIDTH

    by_band: dict[int, list[float]] = {}
    for p, _role, score in scored:
        by_band.setdefault(band(score), []).append((p.value_low + p.value_high) / 2)

    def expected_value(score: float) -> Optional[float]:
        b = band(score)
        pooled: list[float] = []
        for step in range(-VALUE_OPPORTUNITY_BAND_WINDOW, VALUE_OPPORTUNITY_BAND_WINDOW + 1, VALUE_OPPORTUNITY_BAND_WIDTH):
            pooled.extend(by_band.get(b + step, []))
        if len(pooled) < VALUE_OPPORTUNITY_MIN_COMPARABLES:
            return None
        return statistics.median(pooled)

    flagged: list[tuple[dict, float]] = []
    for p, role, score in scored:
        actual = (p.value_low + p.value_high) / 2
        expected = expected_value(score)
        if expected is None or expected <= 0:
            continue
        ratio = actual / expected
        if ratio > VALUE_OPPORTUNITY_RATIO_CEILING:
            continue
        candidate = _candidate(p, role, style_key, today)
        candidate["value_gap_pct"] = round((1 - ratio) * 100)
        flagged.append((candidate, expected))

    flagged.sort(key=lambda pair: pair[0]["value_gap_pct"], reverse=True)

    entries = []
    for candidate, _expected in flagged[:limit]:
        entries.append({
            "role": candidate["role"],
            "slot": candidate["player"],
            "rationale": (
                f"{candidate['value_gap_pct']}% below the typical value for a "
                f"{candidate['role_score']:.1f} {candidate['role']} performer in this market"
            ),
            "age_range": f"{max(16, candidate['age'] - 3)}-{min(40, candidate['age'] + 3)}",
            "candidates": [candidate],
            "kind": "value_opportunity",
        })
    return entries
