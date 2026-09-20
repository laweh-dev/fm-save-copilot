"""Regression coverage for user-reported export-parsing failures.

1. FM under American English language/region settings labels the Wage column
   "Salary". The parser only knew "Wage", so those exports hard-failed on the
   very first pipeline stage with "Missing required column(s): wage" — by far
   the most frequently reported issue (4 reports, 2 sources).
"""

from pathlib import Path

import pytest

from fm_copilot.parser import ALL_ATTRIBUTES, ParseError, parse_squad


def _write_export(tmp_path: Path, wage_header: str, wage_value: str = "£12,000 p/w") -> str:
    """A minimal but complete FM HTML export: every required field column plus
    all 47 attribute columns, so the only variable under test is the header
    used for wage."""
    headers = ["Name", "Age", "Position", wage_header, "Height", *ALL_ATTRIBUTES]
    values = ["Ste Jackson", "24", "DM (C)", wage_value, "183 cm", *["12"] * len(ALL_ATTRIBUTES)]

    html = (
        "<html><body><table>"
        "<tr>" + "".join(f"<th>{h}</th>" for h in headers) + "</tr>"
        "<tr>" + "".join(f"<td>{v}</td>" for v in values) + "</tr>"
        "</table></body></html>"
    )
    path = tmp_path / "export.html"
    path.write_text(html, encoding="utf-8")
    return str(path)


@pytest.mark.parametrize("wage_header", ["Wage", "Salary", "salary", " Salary "])
def test_wage_column_parsed_under_british_and_american_headers(tmp_path, wage_header):
    players = parse_squad(_write_export(tmp_path, wage_header))

    assert len(players) == 1
    assert players[0].wage == 12_000


def test_export_with_no_wage_column_at_all_still_fails_loudly(tmp_path):
    with pytest.raises(ParseError, match="wage"):
        parse_squad(_write_export(tmp_path, "Earnings"))
