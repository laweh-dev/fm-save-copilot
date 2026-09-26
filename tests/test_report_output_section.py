"""End-to-end coverage for Section 11 through both render paths.

The unit tests above cover scoring and the analyzer join; these cover the
part that only breaks when everything is wired together — the free-mode
markdown, the HTML render, and the Shape-table marker. Section 11 is also
conditional, so the no-stats case is asserted to stay exactly as it was.
"""

import copy

from fm_copilot import analyzer, html_report, report
from fm_copilot.parser import PlayerStats

from tests.test_analyzer import NO_WINGBACK_SQUAD

# One clear overperformer (weak attributes, elite output) and one clear
# underperformer (strong attributes, no output), so both blocks render.
STAT_LINES = {
    # A real stats export includes the keeper, who then has to be reported
    # as unscorable rather than quietly omitted.
    "GK1": {"Pas %": 78},
    "ST1":{"xG/90": 0.05, "Gls/90": 0.05, "Shot/90": 0.4, "Shot %": 9},
    "ST2": {"xG/90": 0.85, "Gls/90": 0.80, "Shot/90": 4.2, "Shot %": 62},
    "RCM1": {"Pr passes/90": 8.0, "Pas %": 90, "K Ps/90": 2.4, "xA/90": 0.30,
             "Poss Lost/90": 8.0, "Tck/90": 2.8, "Poss Won/90": 10.0},
    "LCM1": {"Pr passes/90": 1.5, "Pas %": 62, "K Ps/90": 0.2, "xA/90": 0.02,
             "Poss Lost/90": 22.0, "Tck/90": 0.4, "Poss Won/90": 2.0},
    "CB1": {"Hdrs W/90": 5.0, "Hdr %": 75, "Tck/90": 2.8, "Tck R": 84,
            "Int/90": 2.4, "Poss Won/90": 9.5, "Poss Lost/90": 6.0, "Pas %": 90},
    "CB2": {"Hdrs W/90": 1.0, "Hdr %": 40, "Tck/90": 0.8, "Tck R": 50,
            "Int/90": 0.4, "Poss Won/90": 3.0, "Poss Lost/90": 20.0, "Pas %": 65},
}


def _squad_with_stats():
    players = copy.deepcopy(NO_WINGBACK_SQUAD)
    for player in players:
        metrics = STAT_LINES.get(player.name)
        if metrics is None:
            continue
        player.stats = PlayerStats(
            name=player.name, club="Test FC", position=player.position,
            minutes=2000, metrics=dict(metrics),
        )
    return players


def _squad_without_stats():
    return copy.deepcopy(NO_WINGBACK_SQUAD)


def test_free_mode_report_renders_section_11_with_both_disagreement_blocks():
    players = _squad_with_stats()
    analysis = analyzer.analyze(players)

    text = report._free_mode_report(analysis, players, objective=None, formation_override=None)

    assert "## 11. OUTPUT VS ATTRIBUTES" in text
    assert "Outperforming their attributes" in text
    assert "Underperforming their attributes" in text
    assert "Not scored" in text  # the goalkeeper, at minimum


def test_section_11_is_absent_without_a_stats_export():
    players = _squad_without_stats()
    analysis = analyzer.analyze(players)

    text = report._free_mode_report(analysis, players, objective=None, formation_override=None)

    assert "OUTPUT VS ATTRIBUTES" not in text


def test_shape_table_carries_the_output_marker():
    players = _squad_with_stats()
    analysis = analyzer.analyze(players)

    shape_md = report._render_shape(
        analysis.shape_analysis, analysis.decisive_players,
        analysis.tactical_style_fit, analysis.output_analysis,
    )

    assert "Output above attributes" in shape_md or "Output below attributes" in shape_md


def test_html_report_renders_the_scatter_chart():
    players = _squad_with_stats()
    analysis = analyzer.analyze(players)
    text = report._free_mode_report(analysis, players, objective=None, formation_override=None)

    html = html_report.generate_html_report(text, analysis)

    assert 'id="11-output-vs-attributes"' in html
    assert "Output vs attributes" in html
    assert "<circle" in html


def test_llm_prompt_includes_the_section_11_instruction_only_when_stats_exist():
    with_stats = analyzer.analyze(_squad_with_stats())
    without_stats = analyzer.analyze(_squad_without_stats())

    assert "## 11. OUTPUT VS ATTRIBUTES" in report.build_user_message(
        with_stats, _squad_with_stats(), None, None
    )
    assert "## 11. OUTPUT VS ATTRIBUTES" not in report.build_user_message(
        without_stats, _squad_without_stats(), None, None
    )
