"""Regression test for GitHub issue #3: market_matching.build_target_dossier()
filtered its candidate pool by age only, with no check against a candidate's
actual FM position — so a center-back could be shortlisted as a target for
an Advanced Forward search purely on attribute overlap.
"""

from datetime import date

from fm_copilot import market_matching
from fm_copilot.parser import Player

ALL_ATTRIBUTES = [
    "Reflexes", "Handling", "Positioning", "Aerial Reach", "Command of Area", "Communication",
    "One on Ones", "Concentration", "Decisions", "Anticipation", "Kicking", "Agility", "Composure",
    "Throwing", "Rushing Out", "Eccentricity", "Punching Tendency",
    "Heading", "Marking", "Tackling", "Strength", "Jumping Reach", "Aggression", "Bravery",
    "Teamwork", "Pace", "Acceleration", "Balance", "First Touch", "Crossing", "Dribbling",
    "Technique", "Off the Ball", "Work Rate", "Stamina", "Passing", "Vision", "Flair",
    "Long Shots", "Finishing", "Penalty Taking", "Determination", "Long Throws", "Corners",
    "Free Kick Taking",
]


def _make_player(name: str, position: str, age: int = 25, **attr_overrides: int) -> Player:
    attributes = {a: 10 for a in ALL_ATTRIBUTES}
    attributes.update(attr_overrides)
    return Player(
        name=name, age=age, position=position, height_cm=180, ca=None, pa=None,
        wage=10_000, contract_end="30/6/2028", value_low=1_000_000, value_high=2_000_000,
        attributes=attributes, club="Test FC",
    )


def test_positionally_ineligible_candidate_excluded_from_role_search():
    """A center-back (FM position 'D (C)') must never be shortlisted as a
    candidate for an Advanced Forward (AF_a) search, regardless of role-fit
    score. Attributes are deliberately tuned to score well on AF_a's weight
    table, so a pass here proves the exclusion is about position, not about
    the CB simply being a weak attacking prospect.
    """
    cb = _make_player(
        "Test CB", "D (C)",
        Finishing=18, **{"Off the Ball": 18}, Composure=18, Pace=18, Acceleration=18, Decisions=18,
    )

    priority = {
        "role": "AF_a",
        "slot": "attack",
        "rationale": "test priority",
        "profile": {"attribute_floors": {}, "age_range": "20-30"},
    }

    dossier = market_matching.build_target_dossier([priority], [cb], today=date(2026, 8, 17))
    candidate_names = [c["player"] for c in dossier[0]["candidates"]]

    assert "Test CB" not in candidate_names, (
        f"Expected the CB to be excluded from an AF_a search on positional grounds, "
        f"but got candidates: {candidate_names}"
    )


def _make_striker(name: str, age: int, value: int) -> Player:
    # Tuned to comfortably clear STRONG_THRESHOLD (70) on AF_a (scores ~75).
    p = _make_player(
        name, "ST (C)", age,
        Finishing=19, **{"Off the Ball": 19}, Acceleration=18, Pace=18, Composure=17,
        **{"First Touch": 15}, Decisions=14,
    )
    p.value_low = value
    p.value_high = value
    return p


def test_find_value_opportunities_flags_a_player_priced_below_their_score_band():
    """A market pool of similarly-scoring strikers, all priced in a tight
    band around £8M, plus one deliberately priced at £2M (75% below the
    going rate for that quality) — the underpriced one should be flagged,
    a normally-priced peer at the same quality should not.
    """
    market = [_make_striker(f"Peer {i}", 24, 8_000_000) for i in range(24)]
    bargain = _make_striker("Bargain Striker", 24, 2_000_000)
    market.append(bargain)

    opportunities = market_matching.find_value_opportunities(market, today=date(2026, 8, 21))
    flagged_names = {e["slot"] for e in opportunities}

    assert "Bargain Striker" in flagged_names, (
        f"expected the deliberately underpriced striker to be flagged, got: {flagged_names}"
    )
    assert "Peer 0" not in flagged_names, (
        "a normally-priced peer at the same quality band shouldn't be flagged as a bargain"
    )


def test_find_value_opportunities_returns_empty_with_too_small_a_pool():
    # Below VALUE_OPPORTUNITY_MIN_POOL (12) — not enough signal to trust a
    # value curve, should degrade to empty rather than guess.
    market = [_make_striker(f"Peer {i}", 24, 8_000_000) for i in range(10)]
    market.append(_make_striker("Bargain Striker", 24, 2_000_000))
    assert market_matching.find_value_opportunities(market, today=date(2026, 8, 21)) == []


def test_build_target_dossier_respects_a_custom_limit():
    market = [_make_player(f"Candidate {i}", "ST (C)", 24, Finishing=18 - i) for i in range(6)]
    priority = {
        "role": "AF_a", "slot": "attack", "rationale": "test priority",
        "profile": {"attribute_floors": {}, "age_range": "20-30"},
    }

    default_dossier = market_matching.build_target_dossier([priority], market, today=date(2026, 8, 21))
    wider_dossier = market_matching.build_target_dossier([priority], market, today=date(2026, 8, 21), limit=4)

    assert len(default_dossier[0]["candidates"]) == 3
    assert len(wider_dossier[0]["candidates"]) == 4


def test_score_cache_produces_identical_scores_to_an_uncached_lookup():
    from datetime import date as _date

    player = _make_player("Cached Player", "ST (C)", 24, Finishing=17, **{"Off the Ball": 16})
    uncached = market_matching._candidate(player, "AF_a", None, _date(2026, 8, 21))
    cache: dict = {}
    cached_first = market_matching._candidate(player, "AF_a", None, _date(2026, 8, 21), cache)
    cached_second = market_matching._candidate(player, "AF_a", None, _date(2026, 8, 21), cache)

    assert uncached["role_score"] == cached_first["role_score"] == cached_second["role_score"]
    assert len(cache) == 1
