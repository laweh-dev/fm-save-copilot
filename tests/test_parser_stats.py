"""Coverage for parse_stats — the FM stats-export ingestion path.

Runs against a real FM24 stats export (tests/fixtures/fm_stats_export.html,
107 players, all 24 columns of the General Metrics view), so the awkward
parts are the genuine ones FM emits: a doubled name cell
("Javi Llabrés - Javi Llabrés"), comma-grouped minutes ("1,910"),
percentage ratios ("76%"), and "-" for a metric the player has no data for.
"""

from pathlib import Path

import pytest

from fm_copilot import parser as parser_module
from fm_copilot.parser import ParseError

FIXTURE = str(Path(__file__).parent / "fixtures" / "fm_stats_export.html")


@pytest.fixture(scope="module")
def parsed() -> dict:
    return parser_module.parse_stats(FIXTURE)


def test_parses_every_row(parsed):
    assert len(parsed) == 106


def test_doubled_name_cell_is_collapsed(parsed):
    """FM renders the name column as "Name - Name" in this view. Left
    uncollapsed, nothing would ever match the squad export."""
    assert "Javi Llabrés" in parsed
    assert "Javi Llabrés - Javi Llabrés" not in parsed


def test_comma_grouped_minutes_parse_as_int(parsed):
    assert parsed["Javi Llabrés"].minutes == 1910


def test_percentage_metrics_parse_as_bare_numbers(parsed):
    assert parsed["Javi Llabrés"].metric("Pas %") == pytest.approx(83.0)
    assert parsed["Javi Llabrés"].metric("Tck R") == pytest.approx(76.0)


def test_decimal_per_90_metrics_parse(parsed):
    player = parsed["Javi Llabrés"]
    assert player.metric("Tck/90") == pytest.approx(2.45)
    assert player.metric("xG/90") == pytest.approx(0.11)


def test_dash_means_absent_not_zero(parsed):
    """Ibrahim Osman's last column is "-". Reading that as 0.0 would score
    him as genuinely bad at it rather than as having no data."""
    assert parsed["Ibrahim Osman"].metric("Gls/90") is None


def test_club_and_position_are_captured(parsed):
    player = parsed["James McAtee"]
    assert player.club is not None and "Wolves" in player.club
    assert player.position == "M/AM (RC)"


def test_all_expected_metrics_present_in_fixture(parsed):
    player = parsed["Javi Llabrés"]
    missing = [m for m in parser_module.STAT_METRICS if m not in player.metrics]
    assert missing == []


def test_missing_required_column_raises(tmp_path):
    bad = tmp_path / "bad.html"
    bad.write_text(
        "<html><body><table>"
        "<tr><th>Player</th><th>Club</th></tr>"
        "<tr><td>Someone</td><td>A Club</td></tr>"
        "</table></body></html>"
    )
    with pytest.raises(ParseError, match="Mins"):
        parser_module.parse_stats(str(bad))


# --- attaching to a squad ------------------------------------------------

class _FakePlayer:
    def __init__(self, name):
        self.name = name
        self.stats = None


def test_attach_matches_by_name_and_reports_both_directions():
    squad = [_FakePlayer("Javi Llabrés"), _FakePlayer("Nobody In The Stats File")]
    stats_by_name = {
        "Javi Llabrés": parser_module.PlayerStats(
            name="Javi Llabrés", club="Stoke", position="M (L)", minutes=1910, metrics={"xG/90": 0.11}
        ),
        "Extra Player Not In Squad": parser_module.PlayerStats(
            name="Extra Player Not In Squad", club="Stoke", position="ST (C)", minutes=900, metrics={}
        ),
    }

    result = parser_module.attach_stats(squad, stats_by_name)

    assert squad[0].stats is not None
    assert squad[1].stats is None
    assert result["matched"] == 1
    assert result["squad_without_stats"] == ["Nobody In The Stats File"]
    assert result["stats_without_squad"] == ["Extra Player Not In Squad"]
