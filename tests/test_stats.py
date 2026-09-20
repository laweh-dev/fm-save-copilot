"""Coverage for stats.py — the output-scoring engine.

The band tables themselves are football judgement and aren't asserted
value-by-value here (that would just restate the table). What is asserted
is the machinery that a wrong answer in would be silent and inverting:
band boundaries, the lower-is-better metrics, the minutes gate, and the
goalkeeper exclusion.
"""

import pytest

from fm_copilot import stats
from fm_copilot.parser import PlayerStats


def _stats(name: str = "Test Player", minutes: int = 2000, **metrics: float) -> PlayerStats:
    return PlayerStats(
        name=name, club="Test FC", position="ST (C)", minutes=minutes, metrics=dict(metrics)
    )


# --- position grouping ---------------------------------------------------

@pytest.mark.parametrize("position,expected", [
    ("GK", "goalkeeper"),
    ("D (C)", "centre_back"),
    ("D (RC)", "centre_back"),          # central listed -> centre-back wins
    ("D (R)", "full_back"),
    ("D/WB (L)", "full_back"),
    ("WB (R)", "full_back"),
    ("DM", "defensive_mid"),
    ("DM, M (C)", "defensive_mid"),
    ("M (C)", "central_mid"),
    ("M/AM (RC)", "central_mid"),       # central listed -> not a pure wide player
    ("M (L), AM (RLC)", "wide_attacker"),
    ("AM (R)", "wide_attacker"),
    ("M/AM (L), ST (C)", "wide_attacker"),
    ("ST (C)", "striker"),
])
def test_position_group(position, expected):
    assert stats.stats_position_group(position) == expected


def test_unparseable_position_falls_back_to_central_mid():
    assert stats.stats_position_group("") == "central_mid"
    assert stats.stats_position_group("???") == "central_mid"


# --- band placement ------------------------------------------------------

def test_band_boundaries_are_inclusive_at_the_threshold():
    band = stats.Band(weight=1, elite=0.60, strong=0.40, adequate=0.25)
    assert stats.place(band, 0.60) == "elite"
    assert stats.place(band, 0.59) == "strong"
    assert stats.place(band, 0.40) == "strong"
    assert stats.place(band, 0.39) == "adequate"
    assert stats.place(band, 0.25) == "adequate"
    assert stats.place(band, 0.24) == "weak"


def test_lower_is_better_metric_inverts_placement():
    """Poss Lost/90 is the one direction-flipped metric in the tables. A
    polarity bug here is silent and inverts a player's whole verdict."""
    band = stats.Band(weight=1, elite=8.0, strong=11.0, adequate=14.0, higher_is_better=False)
    assert stats.place(band, 6.0) == "elite"
    assert stats.place(band, 8.0) == "elite"
    assert stats.place(band, 10.0) == "strong"
    assert stats.place(band, 13.0) == "adequate"
    assert stats.place(band, 20.0) == "weak"


def test_poss_lost_is_configured_lower_is_better_in_every_group():
    for group, bands in stats.STAT_GROUP_BANDS.items():
        band = bands.get("Poss Lost/90")
        if band is not None:
            assert band.higher_is_better is False, f"{group} has Poss Lost/90 the wrong way round"


# --- scoring -------------------------------------------------------------

def test_elite_across_the_board_scores_higher_than_weak_across_the_board():
    elite = _stats(**{"xG/90": 0.9, "Gls/90": 0.9, "Shot/90": 5.0, "Shot %": 70,
                      "xA/90": 0.5, "Pres A/90": 20, "Hdrs W/90": 4.0})
    weak = _stats(**{"xG/90": 0.01, "Gls/90": 0.01, "Shot/90": 0.2, "Shot %": 5,
                     "xA/90": 0.0, "Pres A/90": 1, "Hdrs W/90": 0.1})

    elite_result = stats.score_output(elite, "striker")
    weak_result = stats.score_output(weak, "striker")

    assert elite_result.score == 100.0
    assert weak_result.score == 25.0
    assert elite_result.unscored_reason is None


def test_missing_metrics_are_skipped_not_scored_as_zero():
    """A column the export didn't supply must not drag the score down —
    otherwise a partial export reads as a bad player."""
    full = _stats(**{"xG/90": 0.6, "Gls/90": 0.65})
    partial = _stats(**{"xG/90": 0.6})

    assert stats.score_output(full, "striker").score == stats.score_output(partial, "striker").score
    assert stats.score_output(partial, "striker").metrics_used == 1


def test_weighting_favours_the_heavier_metric():
    """xG/90 is weight 3 for a striker, Hdrs W/90 is weight 1. Being elite
    at the heavy one must beat being elite at the light one."""
    heavy = _stats(**{"xG/90": 0.9, "Hdrs W/90": 0.1})
    light = _stats(**{"xG/90": 0.01, "Hdrs W/90": 4.0})

    assert stats.score_output(heavy, "striker").score > stats.score_output(light, "striker").score


def test_standout_and_weakest_metrics_are_identified():
    result = stats.score_output(
        _stats(**{"xG/90": 0.9, "Gls/90": 0.45, "Shot %": 5}), "striker"
    )
    assert result.standout == "xG/90"
    assert result.weakest == "Shot %"


# --- guards --------------------------------------------------------------

def test_below_the_minutes_floor_is_unscored_not_zero():
    result = stats.score_output(_stats(minutes=213, **{"xG/90": 0.9}), "striker")
    assert result.score is None
    assert result.unscored_reason == "insufficient_minutes"
    assert result.minutes == 213


def test_minutes_floor_boundary_is_scored():
    result = stats.score_output(
        _stats(minutes=stats.MINUTES_FLOOR, **{"xG/90": 0.9}), "striker"
    )
    assert result.score is not None


def test_missing_minutes_is_unscored():
    result = stats.score_output(_stats(minutes=None, **{"xG/90": 0.9}), "striker")
    assert result.score is None
    assert result.unscored_reason == "insufficient_minutes"


def test_goalkeepers_are_never_scored():
    """The export carries no goalkeeping metrics — no saves, save %, clean
    sheets. A GK would be scored on Pas % alone, which is worse than
    abstaining."""
    result = stats.score_output(_stats(minutes=3000, **{"Pas %": 90}), "goalkeeper")
    assert result.score is None
    assert result.unscored_reason == "goalkeeper"


def test_no_usable_metrics_is_unscored():
    result = stats.score_output(_stats(minutes=3000), "striker")
    assert result.score is None
    assert result.unscored_reason == "no_metrics"
