"""Regression coverage for two user-reported issues:

1. "cannot play wing-backs" fired regardless of the formation actually in
   play — even a squad running 4-4-2 (which uses FB, not WB, in every one of
   the 6 modelled formations except 3-5-2/3-4-3/3-4-2-1) got told it couldn't
   do something it was never trying to do.
2. Recruitment priorities were hard-capped at 4 regardless of how many real,
   evidence-backed gaps the squad actually had.
"""

from fm_copilot import analyzer, roles
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


# A squad with no genuine wing-back — full-backs are capped defensive
# profiles (low pace/crossing/stamina), nowhere near WB_s/WB_a's 70-point
# strong threshold — but complete enough to fill a 4-4-2 or a 3-5-2 without
# any out-of-position fallback muddying the result.
NO_WINGBACK_SQUAD = [
    _make_player("GK1", "GK", Reflexes=15, Handling=15, Positioning=15,
                 **{"Aerial Reach": 15, "Command of Area": 15, "Communication": 15}),
    _make_player("RB1", "D/WB (R)", Marking=14, Tackling=14, Positioning=14, Pace=8, Crossing=6, Stamina=8),
    _make_player("LB1", "D/WB (L)", Marking=14, Tackling=14, Positioning=14, Pace=8, Crossing=6, Stamina=8),
    _make_player("CB1", "D (C)", Heading=14, Marking=14, Tackling=14, Positioning=14, Strength=14),
    _make_player("CB2", "D (C)", Heading=14, Marking=14, Tackling=14, Positioning=14, Strength=14),
    _make_player("RM1", "M/AM (R)", Crossing=14, Dribbling=14, Technique=14, **{"Off the Ball": 13}),
    _make_player("LM1", "M/AM (L)", Crossing=14, Dribbling=14, Technique=14, **{"Off the Ball": 13}),
    _make_player("DM1", "DM", Passing=14, Decisions=14, Teamwork=14, Tackling=13, **{"Work Rate": 13}),
    _make_player("RCM1", "M (C)", Passing=14, Decisions=14, Teamwork=14, **{"Work Rate": 13}, Stamina=13),
    _make_player("LCM1", "M (C)", Passing=14, Decisions=14, Teamwork=14, **{"Work Rate": 13}, Stamina=13),
    _make_player("ST1", "ST (C)", Finishing=16, **{"Off the Ball": 15}, Pace=14, Composure=14),
    _make_player("ST2", "ST (C)", Finishing=15, **{"Off the Ball": 14}, Pace=13, Composure=13),
]


def _tactical_flags(players: list[Player], formation: str) -> set[str]:
    player_scores = {p.name: roles.compute_role_scores(p) for p in players}
    coverage = roles.role_coverage(players)
    summary = analyzer._role_coverage_summary(players, player_scores, coverage)
    impossibilities = analyzer._tactical_impossibilities(players, summary, formation)
    return {i["flag"] for i in impossibilities}


def test_wingback_gap_not_flagged_for_a_formation_that_does_not_need_wingbacks():
    flags = _tactical_flags(NO_WINGBACK_SQUAD, "4-4-2")
    assert "cannot play wing-backs" not in flags, (
        "4-4-2 uses full-backs, not wing-backs — a squad with no strong WB "
        "shouldn't be told it can't do something 4-4-2 never asks of it"
    )


def test_wingback_gap_still_flagged_for_a_formation_that_needs_wingbacks():
    flags = _tactical_flags(NO_WINGBACK_SQUAD, "3-5-2")
    assert "cannot play wing-backs" in flags, (
        "3-5-2 genuinely needs wing-backs — the same squad should still be "
        "flagged when the formation in effect actually requires the role"
    )


def test_recruitment_priorities_are_not_hard_capped_at_four():
    # Full 11-slot 4-4-2 squad (so best_xi_for_formation doesn't need any
    # out-of-position fallback), but every player left at flat baseline
    # attributes — mediocre at every role, so structural weaknesses fire
    # broadly across defence/midfield/attack, plus the usual tactical
    # impossibilities (no direct outlet, no ball-winner, no midfield goal
    # threat, thin goalkeeping), genuinely producing more than 4 distinct,
    # deduplicated-by-role gaps rather than one contrived to hit a number.
    thin_squad = [
        _make_player("GK1", "GK"),
        _make_player("RB1", "D (R)"),
        _make_player("RCB1", "D (C)"),
        _make_player("LCB1", "D (C)"),
        _make_player("LB1", "D (L)"),
        _make_player("RM1", "M (R)"),
        _make_player("RCM1", "M (C)"),
        _make_player("LCM1", "M (C)"),
        _make_player("LM1", "M (L)"),
        _make_player("RST1", "ST (C)"),
        _make_player("LST1", "ST (C)"),
    ]
    player_scores = {p.name: roles.compute_role_scores(p) for p in thin_squad}
    coverage = roles.role_coverage(thin_squad)
    shape, _viability = analyzer._shape_analysis(thin_squad, player_scores, None)
    summary = analyzer._role_coverage_summary(thin_squad, player_scores, coverage)
    tactical = analyzer._tactical_impossibilities(thin_squad, summary, analyzer._effective_formation(shape))
    headline = analyzer._headline_facts(thin_squad)

    priorities = analyzer._recruitment_priorities(thin_squad, headline, shape, tactical)
    assert len(priorities) > 4, (
        f"expected more than 4 genuine priorities from a squad this thin, got {len(priorities)}: "
        f"{[p['role'] for p in priorities]}"
    )
