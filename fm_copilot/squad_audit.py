"""Squad audit: per-player core/rotation/filler/saleable/exit classification,
grounded in FM's own "Actual Playing Time" status rather than derived from
scratch, plus purchase-vs-current-value tracking.

Degrades gracefully: if a squad export doesn't have the playing-time/minutes/
transfer-fee columns, every player gets tier "Unknown" and the report says
so — this never blocks a run.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from fm_copilot.parser import Player

TIER_CORE = "Core"
TIER_ROTATION = "Rotation"
TIER_FILLER = "Filler"
TIER_SALEABLE = "Saleable"
TIER_EXIT = "Exit"
TIER_UNKNOWN = "Unknown"

TIER_ORDER = [TIER_CORE, TIER_ROTATION, TIER_FILLER, TIER_SALEABLE, TIER_EXIT, TIER_UNKNOWN]

# Maps FM's own "Actual Playing Time" status to our 5-tier squad-audit
# classification. Each mapping is grounded in the user's own stated
# philosophy for that status, not an arbitrary guess:
#   - Star/Important/Regular Starter: "first choices... play in most games"
#   - Squad Player/Impact Sub: genuine rotation contributors (35-60%)
#   - Breakthrough Prospect: "the most important youngsters... a game or two"
#   - Emergency Backup/Backup: kept long-term on purpose ("mentor types...
#     several years without complaint"), not a sale signal
#   - Future Prospect: retained for development, not urgent either way
#   - Fringe Player: "most players with this role will be up for sale"
#   - Youngster: "youngsters I doubt will make the cut" — better realised
#     as value than kept
#   - Out On Loan: not part of first-team plans
#   - Surplus to Requirements: FM's own explicit "not wanted" flag
PLAYING_TIME_TIER: dict[str, str] = {
    "Star Player": TIER_CORE,
    "Important Player": TIER_CORE,
    "Regular Starter": TIER_CORE,
    "Squad Player": TIER_ROTATION,
    "Impact Sub": TIER_ROTATION,
    "Breakthrough Prospect": TIER_ROTATION,
    "Emergency Backup": TIER_FILLER,
    "Backup": TIER_FILLER,
    "Future Prospect": TIER_FILLER,
    "Fringe Player": TIER_SALEABLE,
    "Youngster": TIER_SALEABLE,
    "Out On Loan": TIER_SALEABLE,
    "Surplus to Requirements": TIER_EXIT,
}


def classify_tier(actual_playing_time: Optional[str]) -> str:
    if not actual_playing_time:
        return TIER_UNKNOWN
    # Unrecognised labels default to Filler (a neutral, non-alarming tier)
    # rather than crashing or silently dropping the player.
    return PLAYING_TIME_TIER.get(actual_playing_time.strip(), TIER_FILLER)


def compute_squad_audit(players: list["Player"]) -> dict:
    entries = []
    tier_counts = {tier: 0 for tier in TIER_ORDER}
    total_value_created = 0.0
    total_purchase_spend = 0
    players_with_value_data = 0
    mismatches = []
    unmapped_labels: set[str] = set()

    for p in players:
        tier = classify_tier(p.actual_playing_time)
        tier_counts[tier] += 1

        if p.actual_playing_time and p.actual_playing_time.strip() not in PLAYING_TIME_TIER:
            unmapped_labels.add(p.actual_playing_time.strip())

        current_value_mid = None
        if p.value_low is not None and p.value_high is not None:
            current_value_mid = (p.value_low + p.value_high) / 2

        value_created = None
        if current_value_mid is not None and p.last_transfer_fee is not None:
            value_created = current_value_mid - p.last_transfer_fee
            total_value_created += value_created
            total_purchase_spend += p.last_transfer_fee
            players_with_value_data += 1

        mismatch = bool(
            p.actual_playing_time and p.agreed_playing_time
            and p.actual_playing_time.strip() != p.agreed_playing_time.strip()
        )
        if mismatch:
            mismatches.append({
                "player": p.name, "actual": p.actual_playing_time, "agreed": p.agreed_playing_time,
            })

        entries.append({
            "player": p.name,
            "tier": tier,
            "actual_playing_time": p.actual_playing_time,
            "agreed_playing_time": p.agreed_playing_time,
            "apps_starts": p.apps_starts,
            "apps_subs": p.apps_subs,
            "minutes_played": p.minutes_played,
            "last_transfer_fee": p.last_transfer_fee,
            "current_value_low": p.value_low,
            "current_value_high": p.value_high,
            "value_created": value_created,
            "mismatch": mismatch,
        })

    has_data = any(p.actual_playing_time for p in players)

    return {
        "has_data": has_data,
        "entries": entries,
        "tier_counts": tier_counts,
        "total_value_created": total_value_created if players_with_value_data else None,
        "total_purchase_spend": total_purchase_spend if players_with_value_data else None,
        "players_with_value_data": players_with_value_data,
        "mismatches": mismatches,
        "unmapped_labels": sorted(unmapped_labels),
    }
