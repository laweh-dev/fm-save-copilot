"""Output-scoring engine: what a player actually produced.

The parallel to roles.py. Where roles.py scores a player on what FM says
they can do (attributes), this scores them on what they did (per-90 match
statistics). The two are kept deliberately separate — no stat feeds a
role-fit score and no attribute feeds an output score — because the
interesting signal is precisely where the two disagree.

Bands are hardcoded, football-sensible reference points per position group,
the same standing as roles.ROLE_WEIGHTS: defensible judgement, not FM's
internal formulas, and not calibrated to any particular division. In a
low-standard save a whole squad can legitimately read "weak" against them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from fm_copilot.parser import PlayerStats

# Below this, per-90 figures are noise rather than evidence. ~5 full matches.
MINUTES_FLOOR = 450

BAND_POINTS = {"elite": 100.0, "strong": 75.0, "adequate": 50.0, "weak": 25.0}

GROUP_LABELS = {
    "centre_back": "Centre-back",
    "full_back": "Full-back / wing-back",
    "defensive_mid": "Defensive midfield",
    "central_mid": "Central midfield",
    "wide_attacker": "Wide attacker",
    "striker": "Striker",
    "goalkeeper": "Goalkeeper",
}


@dataclass(frozen=True)
class Band:
    """Thresholds for one metric within one position group.

    elite/strong/adequate are the floors of each band; anything below
    `adequate` is weak. When higher_is_better is False the comparison
    inverts and the three numbers are ceilings instead.
    """

    weight: int
    elite: float
    strong: float
    adequate: float
    higher_is_better: bool = True


# Per-position metric subsets, deliberately not the full column set: a
# centre-back has no shooting metrics in their table, so they can't be
# marked down for not shooting.
STAT_GROUP_BANDS: dict[str, dict[str, Band]] = {
    "centre_back": {
        "Hdrs W/90":    Band(3, 4.5, 3.2, 2.2),
        "Hdr %":        Band(2, 70, 60, 50),
        "Tck/90":       Band(2, 2.6, 2.0, 1.4),
        "Tck R":        Band(2, 80, 72, 62),
        "Int/90":       Band(2, 2.2, 1.5, 0.9),
        "Poss Won/90":  Band(2, 9.0, 7.0, 5.0),
        "Poss Lost/90": Band(2, 8.0, 11.0, 14.0, higher_is_better=False),
        "Pas %":        Band(2, 88, 83, 76),
        "Pr passes/90": Band(1, 6.0, 4.0, 2.5),
    },
    "full_back": {
        "Tck/90":       Band(2, 3.2, 2.5, 1.8),
        "Tck R":        Band(2, 78, 70, 60),
        "Int/90":       Band(2, 2.2, 1.5, 1.0),
        "Poss Won/90":  Band(2, 9.5, 7.5, 5.5),
        "Poss Lost/90": Band(2, 10.0, 13.0, 16.0, higher_is_better=False),
        "Crs A/90":     Band(2, 5.0, 3.5, 2.0),
        "Cr C/A":       Band(2, 28, 20, 12),
        "Pr passes/90": Band(2, 6.0, 4.0, 2.5),
        "xA/90":        Band(2, 0.22, 0.14, 0.08),
        "Pas %":        Band(1, 84, 78, 72),
        "Drb/90":       Band(1, 2.0, 1.2, 0.6),
    },
    "defensive_mid": {
        "Tck/90":       Band(3, 3.0, 2.3, 1.6),
        "Poss Won/90":  Band(3, 10.0, 8.0, 6.0),
        "Poss Lost/90": Band(3, 9.0, 12.0, 15.0, higher_is_better=False),
        "Pas %":        Band(3, 89, 85, 79),
        "Tck R":        Band(2, 78, 70, 60),
        "Int/90":       Band(2, 2.0, 1.4, 0.9),
        "Pr passes/90": Band(2, 7.0, 5.0, 3.0),
        "Pres C/90":    Band(1, 4.0, 3.0, 2.0),
        "Hdrs W/90":    Band(1, 2.0, 1.2, 0.7),
    },
    "central_mid": {
        "Pr passes/90": Band(3, 7.5, 5.5, 3.5),
        "Pas %":        Band(2, 88, 84, 78),
        "K Ps/90":      Band(2, 2.0, 1.3, 0.8),
        "xA/90":        Band(2, 0.25, 0.16, 0.09),
        "Poss Lost/90": Band(2, 11.0, 14.0, 17.0, higher_is_better=False),
        "Tck/90":       Band(2, 2.6, 1.9, 1.3),
        "Poss Won/90":  Band(2, 9.0, 7.0, 5.0),
        "Drb/90":       Band(1, 2.0, 1.2, 0.6),
        "Shot/90":      Band(1, 1.6, 1.0, 0.5),
        "Pres A/90":    Band(1, 14.0, 11.0, 8.0),
    },
    "wide_attacker": {
        "xA/90":        Band(3, 0.35, 0.22, 0.13),
        "xG/90":        Band(3, 0.40, 0.25, 0.15),
        "Drb/90":       Band(3, 3.5, 2.2, 1.2),
        "Gls/90":       Band(2, 0.45, 0.28, 0.15),
        "K Ps/90":      Band(2, 2.2, 1.5, 0.9),
        "OP-KP/90":     Band(2, 1.8, 1.2, 0.7),
        "Shot/90":      Band(2, 2.8, 2.0, 1.2),
        "Crs A/90":     Band(1, 5.0, 3.5, 2.0),
        "Cr C/A":       Band(1, 28, 20, 12),
        "Pres A/90":    Band(1, 16.0, 12.0, 9.0),
    },
    "striker": {
        "xG/90":        Band(3, 0.60, 0.40, 0.25),
        "Gls/90":       Band(3, 0.65, 0.45, 0.28),
        "Shot/90":      Band(2, 3.5, 2.5, 1.6),
        "Shot %":       Band(2, 55, 45, 35),
        "xA/90":        Band(1, 0.30, 0.20, 0.12),
        "Pres A/90":    Band(1, 14.0, 10.0, 7.0),
        "Hdrs W/90":    Band(1, 2.5, 1.5, 0.8),
    },
    # Goalkeepers intentionally absent — see score_output.
}


@dataclass
class MetricPlacement:
    metric: str
    value: float
    band: str
    weight: int


@dataclass
class OutputScore:
    score: Optional[float]
    placements: list[MetricPlacement] = field(default_factory=list)
    standout: Optional[str] = None
    weakest: Optional[str] = None
    unscored_reason: Optional[str] = None
    minutes: Optional[int] = None

    @property
    def metrics_used(self) -> int:
        return len(self.placements)


# ---------------------------------------------------------------------------
# Position grouping
# ---------------------------------------------------------------------------

def stats_position_group(position: str) -> str:
    """Map an FM position string to a stats position group.

    Finer than analyzer._position_group's four buckets, which is why this
    lives here rather than reusing it: a centre-back and a wing-back share
    a bucket there, but have nothing in common on Crs A/90.
    """
    if not position:
        return "central_mid"

    first = position.split(",")[0].strip()
    match = re.match(r"^([A-Za-z/]+)\s*(?:\(([^)]*)\))?", first)
    if not match:
        return "central_mid"

    codes = {c.strip().upper() for c in match.group(1).split("/") if c.strip()}
    sides = set((match.group(2) or "").upper().replace(" ", ""))

    if "GK" in codes:
        return "goalkeeper"
    if codes & {"ST", "AF", "FW", "CF"}:
        return "striker"
    if "WB" in codes:
        return "full_back"
    if "D" in codes:
        # A defender listed centrally is a centre-back even if also listed
        # wide; the central duty is the demanding one.
        return "centre_back" if ("C" in sides or not sides) else "full_back"
    if "DM" in codes:
        return "defensive_mid"
    if codes & {"M", "AM", "W"}:
        wide_only = bool(sides & {"R", "L"}) and "C" not in sides
        return "wide_attacker" if wide_only else "central_mid"
    return "central_mid"


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def place(band: Band, value: float) -> str:
    """Which band a raw metric value falls in. Thresholds are inclusive."""
    if band.higher_is_better:
        if value >= band.elite:
            return "elite"
        if value >= band.strong:
            return "strong"
        if value >= band.adequate:
            return "adequate"
        return "weak"
    if value <= band.elite:
        return "elite"
    if value <= band.strong:
        return "strong"
    if value <= band.adequate:
        return "adequate"
    return "weak"


def score_output(player_stats: "PlayerStats", group: str) -> OutputScore:
    """Score one player's output for their position group.

    Returns an OutputScore with score=None and a reason rather than a
    misleading number when the player can't fairly be scored.
    """
    minutes = player_stats.minutes

    # No goalkeeping metrics exist in this export — no saves, save %, clean
    # sheets. Scoring a keeper on Pas % alone is worse than abstaining.
    if group == "goalkeeper":
        return OutputScore(score=None, unscored_reason="goalkeeper", minutes=minutes)

    if minutes is None or minutes < MINUTES_FLOOR:
        return OutputScore(score=None, unscored_reason="insufficient_minutes", minutes=minutes)

    bands = STAT_GROUP_BANDS.get(group, {})
    placements = [
        MetricPlacement(metric=metric, value=value, band=place(band, value), weight=band.weight)
        for metric, band in bands.items()
        if (value := player_stats.metric(metric)) is not None
    ]
    if not placements:
        return OutputScore(score=None, unscored_reason="no_metrics", minutes=minutes)

    total_weight = sum(p.weight for p in placements)
    score = sum(BAND_POINTS[p.band] * p.weight for p in placements) / total_weight

    ranked = sorted(placements, key=lambda p: (BAND_POINTS[p.band], p.weight), reverse=True)
    return OutputScore(
        score=round(score, 1),
        placements=placements,
        standout=ranked[0].metric,
        weakest=ranked[-1].metric,
        minutes=minutes,
    )
