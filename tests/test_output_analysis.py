"""Coverage for analyzer._output_analysis — the attribute-vs-output join.

The output score is absolute (stats.STAT_GROUP_BANDS), but the
*disagreement* between output and role-fit is computed on within-squad
percentile ranks, because the two scores are on different scales and
subtracting them directly would be meaningless. These tests pin that
behaviour, since it's the part a reader is most likely to misread.
"""

from fm_copilot import analyzer, roles
from fm_copilot.parser import Player, PlayerStats

from tests.test_analyzer import ALL_ATTRIBUTES


def _player(name: str, position: str, attr_level: int, minutes: int = 2000, **metrics: float) -> Player:
    return Player(
        name=name, age=25, position=position, height_cm=180, ca=None, pa=None,
        wage=10_000, contract_end="30/6/2028", value_low=1_000_000, value_high=2_000_000,
        attributes={a: attr_level for a in ALL_ATTRIBUTES},
        stats=PlayerStats(
            name=name, club="Test FC", position=position, minutes=minutes, metrics=dict(metrics)
        ),
    )


ELITE_STRIKER = {"xG/90": 0.9, "Gls/90": 0.9, "Shot/90": 5.0, "Shot %": 70}
WEAK_STRIKER = {"xG/90": 0.02, "Gls/90": 0.02, "Shot/90": 0.3, "Shot %": 8}


def _analyse(players: list[Player]) -> dict:
    player_scores = {p.name: roles.compute_role_scores(p) for p in players}
    return analyzer._output_analysis(players, player_scores)


def test_no_stats_anywhere_means_no_data():
    players = [_player("A", "ST (C)", 12)]
    players[0].stats = None
    assert _analyse(players)["has_data"] is False


def test_low_attributes_high_output_is_an_overperformer():
    players = [
        _player("Bargain", "ST (C)", 5, **ELITE_STRIKER),
        _player("Flatterer", "ST (C)", 18, **WEAK_STRIKER),
        _player("Middling", "ST (C)", 12, **{"xG/90": 0.40, "Gls/90": 0.45, "Shot/90": 2.5, "Shot %": 45}),
    ]
    result = _analyse(players)

    assert [e["player"] for e in result["overperformers"]] == ["Bargain"]
    assert [e["player"] for e in result["underperformers"]] == ["Flatterer"]


def test_high_attributes_and_high_output_is_confirmed_not_flagged():
    players = [
        _player("Genuine", "ST (C)", 18, **ELITE_STRIKER),
        _player("Poor", "ST (C)", 5, **WEAK_STRIKER),
    ]
    result = _analyse(players)

    assert "Genuine" in [e["player"] for e in result["confirmed"]]
    assert result["overperformers"] == []
    assert result["underperformers"] == []


def test_low_minutes_players_are_listed_unscored_not_ranked():
    players = [
        _player("Regular", "ST (C)", 12, minutes=2000, **ELITE_STRIKER),
        _player("Cameo", "ST (C)", 12, minutes=90, **ELITE_STRIKER),
    ]
    result = _analyse(players)

    scored_names = [e["player"] for e in result["scored"]]
    assert scored_names == ["Regular"]
    unscored = {e["player"]: e["reason"] for e in result["unscored"]}
    assert unscored["Cameo"] == "insufficient_minutes"


def test_goalkeepers_are_reported_as_unscorable():
    players = [
        _player("Keeper", "GK", 15, minutes=3000, **{"Pas %": 88}),
        _player("Striker", "ST (C)", 12, **ELITE_STRIKER),
    ]
    result = _analyse(players)

    unscored = {e["player"]: e["reason"] for e in result["unscored"]}
    assert unscored["Keeper"] == "goalkeeper"


def test_scored_entries_carry_both_scores_and_the_driving_metrics():
    players = [
        _player("Striker", "ST (C)", 12, **ELITE_STRIKER),
        _player("Other", "ST (C)", 12, **WEAK_STRIKER),
    ]
    entry = next(e for e in _analyse(players)["scored"] if e["player"] == "Striker")

    assert entry["output_score"] == 100.0
    assert entry["role_score"] > 0
    assert entry["group_label"] == "Striker"
    assert entry["standout"] in ELITE_STRIKER
    assert entry["minutes"] == 2000


def test_a_single_scored_player_produces_no_disagreement():
    """With one player there is no spread to rank against — the honest
    answer is no flags, not a self-referential 50th percentile."""
    result = _analyse([_player("Alone", "ST (C)", 12, **ELITE_STRIKER)])

    assert result["has_data"] is True
    assert result["overperformers"] == []
    assert result["underperformers"] == []
