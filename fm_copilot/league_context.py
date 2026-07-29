"""League-context benchmarking: how a squad player's style-fit score
compares to the actual standard of opposition in their league.

Pure statistics, no LLM, no named opposition players ever produced here —
this module only recalibrates what a tier means, it never surfaces who
the comparison players are. Every league player counts toward the
benchmark, weighted by appearances (starts count more than sub
appearances), so the benchmark self-corrects for pre-season: if apps are
near-zero league-wide, weights flatten out and the benchmark falls back
to an unweighted read of the whole population, with no special case
needed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from fm_copilot import tactics

if TYPE_CHECKING:
    from fm_copilot.parser import Player

PERCENTILE_EXCELS = 80.0
PERCENTILE_SOLID = 50.0
PERCENTILE_BELOW_PAR = 20.0

NO_LEAGUE_DATA = "No league data"


def compute_apps_weight(player: "Player") -> float:
    starts = player.apps_starts or 0
    subs = player.apps_subs or 0
    return max(starts + 0.5 * subs, 0.1)


def build_position_distributions(
    league_players: list["Player"], style_key: str
) -> dict[str, list[tuple[float, float]]]:
    distributions: dict[str, list[tuple[float, float]]] = {g: [] for g in tactics.POSITION_GROUPS}
    for p in league_players:
        group = tactics.classify_position_group(p.position)
        score = tactics.compute_style_score(p, style_key)
        weight = compute_apps_weight(p)
        distributions[group].append((score, weight))
    for group in distributions:
        distributions[group].sort(key=lambda t: t[0])
    return distributions


def weighted_percentile(distribution: list[tuple[float, float]], value: float) -> Optional[float]:
    if not distribution:
        return None
    total = sum(w for _, w in distribution)
    if total <= 0:
        return None
    below = sum(w for s, w in distribution if s < value)
    equal = sum(w for s, w in distribution if s == value)
    rank = (below + 0.5 * equal) / total * 100
    return round(rank, 1)


def percentile_tier(pct: float) -> str:
    if pct >= PERCENTILE_EXCELS:
        return tactics.TIER_LABELS["excels"]
    if pct >= PERCENTILE_SOLID:
        return tactics.TIER_LABELS["solid"]
    if pct >= PERCENTILE_BELOW_PAR:
        return tactics.TIER_LABELS["below_par"]
    return tactics.TIER_LABELS["poor_fit"]


def contextualize_style_fit(squad_style_fit: dict, league_players: list["Player"], style_key: str) -> dict:
    distributions = build_position_distributions(league_players, style_key)

    augmented = []
    for name, position_group, score, tier in squad_style_fit["player_scores"]:
        pct = weighted_percentile(distributions.get(position_group, []), score)
        league_tier = percentile_tier(pct) if pct is not None else NO_LEAGUE_DATA
        augmented.append((name, position_group, score, tier, pct, league_tier))

    total_players = len(league_players)
    clubs = {p.club for p in league_players if p.club}
    with_apps = sum(1 for p in league_players if (p.apps_starts or 0) + (p.apps_subs or 0) > 0)
    apps_signal_ratio = round(with_apps / total_players, 2) if total_players else 0.0

    return {
        "player_scores": augmented,
        "league_player_count": total_players,
        "league_club_count": len(clubs),
        "apps_signal_ratio": apps_signal_ratio,
        "sparse_apps_warning": total_players > 0 and apps_signal_ratio < 0.10,
    }
