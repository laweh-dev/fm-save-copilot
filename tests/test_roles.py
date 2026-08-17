"""Regression coverage for roles.py's position-eligibility logic (v0.8.1),
re-verified here because GitHub issue #3's fix renamed roles._position_groups
to roles.position_groups (made public for reuse in market_matching.py) —
this confirms that rename/refactor didn't change squad-side Best XI
selection behavior.
"""

from fm_copilot import roles
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
        attributes=attributes, club=None,
    )


def test_position_groups_parses_multi_family_and_side():
    groups = roles.position_groups("D/WB (L), M/AM (LC)")
    assert groups == [({"D", "WB"}, {"L"}), ({"M", "AM"}, {"L", "C"})]


def test_position_groups_bare_family_is_central():
    assert roles.position_groups("DM") == [({"DM"}, {"C"})]


def test_best_xi_never_places_a_defender_at_striker_over_a_real_striker():
    # A full-enough squad that every other 4-4-2 slot has a natural,
    # eligible occupant — isolates the thing actually being tested (does a
    # real striker beat a spare, well-attributed defender for the ST
    # slots?) from the separate out-of-position-fallback behavior covered
    # by the test below.
    squad = [
        _make_player("GK1", "GK", Reflexes=15, Handling=15, Positioning=15,
                      **{"Aerial Reach": 15, "Command of Area": 15, "Communication": 15}),
        _make_player("RB1", "D/WB (R)", Marking=14, Tackling=14, Positioning=14, Pace=13),
        _make_player("LB1", "D/WB (L)", Marking=14, Tackling=14, Positioning=14, Pace=13),
        _make_player("CB1", "D (C)", Heading=14, Marking=14, Tackling=14, Positioning=14, Strength=14),
        _make_player("CB2", "D (C)", Heading=14, Marking=14, Tackling=14, Positioning=14, Strength=14),
        # Spare defender, not needed to fill RCB/LCB — the actual temptation:
        # decent all-round attacking-adjacent stats, high enough that it could
        # plausibly out-score a real striker if position were ignored.
        _make_player("CB3", "D (C)", Composure=15, Pace=14, **{"Off the Ball": 12}, Finishing=10),
        _make_player("RM1", "M/AM (R)", Crossing=14, Dribbling=14, Technique=14, **{"Off the Ball": 13}),
        _make_player("LM1", "M/AM (L)", Crossing=14, Dribbling=14, Technique=14, **{"Off the Ball": 13}),
        _make_player("RCM1", "M (C)", Passing=14, Decisions=14, Teamwork=14, **{"Work Rate": 13}, Stamina=13),
        _make_player("LCM1", "M (C)", Passing=14, Decisions=14, Teamwork=14, **{"Work Rate": 13}, Stamina=13),
        _make_player("ST1", "ST (C)", Finishing=16, **{"Off the Ball": 15}, Pace=14, Composure=14),
        _make_player("ST2", "ST (C)", Finishing=15, **{"Off the Ball": 14}, Pace=13, Composure=13),
    ]
    result = roles.best_xi_for_formation(squad, "4-4-2")
    st_slots = {"RST", "LST"} & result["xi"].keys()
    starters_up_front = {result["xi"][slot][0] for slot in st_slots}
    assert starters_up_front == {"ST1", "ST2"}
    assert not result["out_of_position_slots"], "a fully-covered squad should need no out-of-position fallback"


def test_best_xi_falls_back_to_out_of_position_rather_than_leaving_a_slot_blank():
    """A squad with no natural fullback at all must still get an RB filled
    (never left blank on the pitch diagram) — but flagged as out of
    position and as a structural weakness, not silently treated as fine."""
    squad = [
        _make_player("GK1", "GK", Reflexes=15, Handling=15, Positioning=15,
                      **{"Aerial Reach": 15, "Command of Area": 15, "Communication": 15}),
        _make_player("CB1", "D (C)", Heading=15, Marking=15, Tackling=15, Positioning=15, Strength=15),
        _make_player("CB2", "D (C)", Heading=15, Marking=15, Tackling=15, Positioning=15, Strength=15),
        _make_player("ST1", "ST (C)", Finishing=16, **{"Off the Ball": 15}, Pace=15),
    ]
    result = roles.best_xi_for_formation(squad, "4-4-2")

    assert "RB" in result["xi"], "a slot with zero eligible players should still be filled, not left blank"
    assert "RB" in result["out_of_position_slots"]
    assert "RB" in result["structural_weaknesses"]
