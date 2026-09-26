"""Coverage for briefing.py — "The Briefing", the 3-page A4 dashboard that
replaced the old 11-section HTML report (see
`Useful artefacts/Claude Code Prompt - The Briefing.md`).
"""

from fm_copilot import analyzer, briefing
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


# ---------------------------------------------------------------------------
# Formatting utilities
# ---------------------------------------------------------------------------

def test_ordinal_fixes_the_known_61th_bug():
    # The spec calls this out by name: "The current generator prints '61th';
    # fix this." 11/12/13 (and their hundreds) are the exception band that
    # a naive "last digit" rule gets wrong.
    cases = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th", 11: "11th", 12: "12th",
             13: "13th", 21: "21st", 61: "61st", 71: "71st", 100: "100th", 111: "111th"}
    for n, expected in cases.items():
        assert briefing._ordinal(n) == expected


def test_money_formats_match_the_spec_examples():
    assert briefing._fmt_money(73_000) == "£73K"
    assert briefing._fmt_money(7_000_000) == "£7.0M"
    assert briefing._fmt_money(0) == "Free"
    assert briefing._fmt_money_range(4_000, 35_000) == "£4–35K"
    assert briefing._fmt_money_ceiling(4_400_000) == "≤£4.4M"


# ---------------------------------------------------------------------------
# Component-level edge cases (empty Sell / empty Protect)
# ---------------------------------------------------------------------------

def test_action_board_and_segmented_bar_handle_empty_groups():
    # Directly exercising empty Sell/Protect groups (spec's explicit test
    # case) without fighting analyzer._exit_candidates' own "always
    # produce something" fallback design to coerce a real squad into
    # zero exits — the risk this guards against (division by zero on an
    # empty total, KeyErrors on missing groups) lives entirely in the
    # rendering functions themselves.
    groups = {"Fix": [], "Buy": [], "Sell": [], "Protect": []}
    bar_html = briefing._segmented_bar_html(groups)
    assert "0" in bar_html

    from types import SimpleNamespace
    analysis = SimpleNamespace(window_budget={}, exit_candidates=[], target_dossier=[])
    board_html = briefing._action_board_html(analysis, groups)
    assert "Sell · 0" in board_html
    assert "Protect · 0" in board_html

    phases_html = briefing._phases_strip_html(groups)
    assert "0 sales" in phases_html or "0 sale" in phases_html


# ---------------------------------------------------------------------------
# End-to-end smoke tests: every formation the tool can output
# ---------------------------------------------------------------------------

def _small_squad() -> list[Player]:
    return [
        _make_player("GK1", "GK", 28, Reflexes=15, Handling=15, Positioning=15,
                      **{"Aerial Reach": 15, "Command of Area": 15, "Communication": 15}),
        _make_player("RB1", "D/WB (R)", 26, Marking=14, Tackling=14, Positioning=14, Pace=13),
        _make_player("LB1", "D/WB (L)", 26, Marking=14, Tackling=14, Positioning=14, Pace=13),
        _make_player("CB1", "D (C)", 27, Heading=14, Marking=14, Tackling=14, Positioning=14, Strength=14),
        _make_player("CB2", "D (C)", 24, Heading=14, Marking=14, Tackling=14, Positioning=14, Strength=14),
        _make_player("CB3", "D (C)", 30, Heading=13, Marking=13, Tackling=13, Positioning=13, Strength=13),
        _make_player("DM1", "DM", 25, Passing=14, Decisions=14, Teamwork=14, Tackling=13, **{"Work Rate": 13}),
        _make_player("RM1", "M/AM (R)", 24, Crossing=14, Dribbling=14, Technique=14, **{"Off the Ball": 13}),
        _make_player("LM1", "M/AM (L)", 24, Crossing=14, Dribbling=14, Technique=14, **{"Off the Ball": 13}),
        _make_player("RCM1", "M (C)", 26, Passing=14, Decisions=14, Teamwork=14, **{"Work Rate": 13}, Stamina=13),
        _make_player("LCM1", "M (C)", 26, Passing=14, Decisions=14, Teamwork=14, **{"Work Rate": 13}, Stamina=13),
        _make_player("ST1", "ST (C)", 23, Finishing=16, **{"Off the Ball": 15}, Pace=14, Composure=14),
        _make_player("ST2", "ST (C)", 29, Finishing=15, **{"Off the Ball": 14}, Pace=13, Composure=13),
    ]


def test_generates_cleanly_for_every_modelled_formation():
    # The spec's own overflow-rules section names this explicitly: "Test
    # with ... a squad using a 3-5-2 or 4-2-3-1. The pitch lookup must
    # cover every formation the tool can output." Covering all 6, not just
    # the two named, since PITCH_COORDS is one flat lookup shared across
    # all of them (same failure mode either way).
    from fm_copilot import roles
    squad = _small_squad()
    for formation in roles.FORMATIONS:
        a = analyzer.analyze(squad, formation_override=formation)
        html = briefing.generate_briefing_html(a, squad)
        assert html.strip().endswith("</html>"), f"malformed output for {formation}"
        assert html.count('class="page"') == 3, f"expected 3 pages for {formation}"


def test_generates_cleanly_without_market_or_league_data():
    # No --market, no --tactic/--league — the common case, and the one
    # that exercises the role-score colour fallback (no percentile data)
    # and the "no Target Dossier" branch of Section 9 / need cards at once.
    squad = _small_squad()
    a = analyzer.analyze(squad)
    html = briefing.generate_briefing_html(a, squad)
    assert html.strip().endswith("</html>")
    assert "Against the division" not in html  # correctly hidden, not invented
