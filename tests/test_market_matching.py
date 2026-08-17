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
