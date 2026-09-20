"""FM24 HTML export -> typed Player list.

Handles two export shapes that share ~90% of their column format: the
squad view (parse_squad) and the current-league view (parse_league, adds
Club + Apps columns). Column mapping is by header name, never by
position, because column availability depends on the view the user
configured in-game. Header aliases (FM's short codes like "Pac", "Wor",
"Tck") are resolved via ATTRIBUTE_ALIASES / FIELD_ALIASES below.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from bs4 import BeautifulSoup

TECHNICAL_ATTRIBUTES = [
    "Corners", "Crossing", "Dribbling", "Finishing", "First Touch",
    "Free Kick Taking", "Heading", "Long Shots", "Long Throws",
    "Marking", "Passing", "Penalty Taking", "Tackling", "Technique",
]

MENTAL_ATTRIBUTES = [
    "Aggression", "Anticipation", "Bravery", "Composure", "Concentration",
    "Decisions", "Determination", "Flair", "Leadership", "Off the Ball",
    "Positioning", "Teamwork", "Vision", "Work Rate",
]

PHYSICAL_ATTRIBUTES = [
    "Acceleration", "Agility", "Balance", "Jumping Reach",
    "Natural Fitness", "Pace", "Stamina", "Strength",
]

GOALKEEPING_ATTRIBUTES = [
    "Aerial Reach", "Command of Area", "Communication", "Eccentricity",
    "Handling", "Kicking", "One on Ones", "Reflexes", "Rushing Out",
    "Punching Tendency", "Throwing",
]

ALL_ATTRIBUTES = (
    TECHNICAL_ATTRIBUTES + MENTAL_ATTRIBUTES + PHYSICAL_ATTRIBUTES + GOALKEEPING_ATTRIBUTES
)  # 47

ATTRIBUTE_ALIASES: dict[str, list[str]] = {
    "Corners": ["cor"],
    "Crossing": ["cro"],
    "Dribbling": ["dri"],
    "Finishing": ["fin"],
    "First Touch": ["fir"],
    "Free Kick Taking": ["fre"],
    "Heading": ["hea"],
    "Long Shots": ["lon"],
    "Long Throws": ["lth", "l th"],
    "Marking": ["mar"],
    "Passing": ["pas"],
    "Penalty Taking": ["pen"],
    "Tackling": ["tck"],
    "Technique": ["tec"],
    "Aggression": ["agg"],
    "Anticipation": ["ant"],
    "Bravery": ["brv", "bra"],
    "Composure": ["cmp"],
    "Concentration": ["cnt"],
    "Decisions": ["dec"],
    "Determination": ["det"],
    "Flair": ["fla"],
    "Leadership": ["ldr"],
    "Off the Ball": ["otb"],
    "Positioning": ["pos"],
    "Teamwork": ["tea"],
    "Vision": ["vis"],
    "Work Rate": ["wor"],
    "Acceleration": ["acc"],
    "Agility": ["agi"],
    "Balance": ["bal"],
    "Jumping Reach": ["jum"],
    "Natural Fitness": ["nat"],
    "Pace": ["pac"],
    "Stamina": ["sta"],
    "Strength": ["str"],
    "Aerial Reach": ["aer"],
    "Command of Area": ["cmd"],
    "Communication": ["com"],
    "Eccentricity": ["ecc"],
    "Handling": ["han"],
    "Kicking": ["kic"],
    "One on Ones": ["1v1", "one on ones"],
    "Reflexes": ["ref"],
    "Rushing Out": ["rus", "tro"],
    "Punching Tendency": ["pun", "tendency to punch", "punching (tendency to punch)"],
    "Throwing": ["thr"],
}

# Field aliases deliberately do NOT include "pos" (that's Positioning's short
# code) — FM's Position column header is not abbreviated in default views.
FIELD_ALIASES: dict[str, list[str]] = {
    "name": ["name", "player"],
    "age": ["age"],
    "position": ["position"],
    "wage": ["wage"],
    "height": ["height", "hgt"],
    "contract_end": ["contract end", "expires", "contract"],
    "ca": ["ca"],
    "pa": ["pa", "potential"],
    "value": ["value", "transfer value"],
    "info": ["info", "inf"],
    "personality": ["personality"],
    "nationality": ["nationality", "nat"],
    "club": ["club"],
    "apps": ["apps"],
    "minutes": ["mins", "minutes"],
    "actual_playing_time": ["actual playing time"],
    "agreed_playing_time": ["agreed playing time"],
    "last_transfer_fee": ["last trans. fee", "last transfer fee"],
    "recurring_injury": ["rc injury", "recurring injury"],
}

# Some FM export views render the name column as an interactive "pick
# player" widget; the flattened text carries a trailing action label that
# isn't part of the name.
NAME_SUFFIXES_TO_STRIP = [" - pick player"]

# --- Match statistics (the "General Metrics" view) -----------------------
# Per-90 and ratio columns from FM's statistics views. Separate from the
# attribute columns above: attributes are FM's judgement of ability, these
# are what the player actually produced on the pitch. Column set and the
# header spellings are taken from the FM-mcp project's General Metrics view
# (https://github.com/stejackson94/FM-mcp), which already had them labelled
# against real exports.
STAT_METRICS = [
    "Gls", "Ast", "Tck/90", "Tck R", "Hdrs W/90", "Hdr %", "Int/90",
    "Poss Won/90", "Poss Lost/90", "Pres C/90", "Pres A/90", "Pas %",
    "Pr passes/90", "Crs A/90", "Cr C/A", "K Ps/90", "OP-KP/90", "xA/90",
    "Drb/90", "Shot/90", "Shot %", "xG/90", "Gls/90",
]

# Header spellings that differ between FM views. Canonical name on the
# right; everything is matched case-insensitively and whitespace-collapsed.
STAT_ALIASES: dict[str, str] = {
    "pres c": "Pres C/90",
    "pres a": "Pres A/90",
    "xg per 90": "xG/90",
    "xa per 90": "xA/90",
    "op-kp": "OP-KP/90",
    "pr passes": "Pr passes/90",
    "crs a": "Crs A/90",
    "k ps": "K Ps/90",
}

STATS_REQUIRED_COLUMNS = ["name", "minutes"]

REQUIRED_FIELDS = ["name", "age", "position", "wage", "height"]
RECOMMENDED_FIELDS = [
    "contract_end", "ca", "pa", "value", "info", "personality", "nationality",
    "minutes", "actual_playing_time", "agreed_playing_time", "last_transfer_fee",
    "recurring_injury",
]

# Club/Apps aren't needed for style-fit scoring, so they're not required —
# a league export missing them just can't power league-context benchmarking.
LEAGUE_REQUIRED_FIELDS = ["name", "position", "club", "apps"]

BLOCKING_STATUSES = {"Injured", "On Loan", "Unavailable", "Suspended"}


@dataclass
class PlayerStats:
    """What a player actually produced, as opposed to what their attributes
    say they should. Parsed from a separate FM stats export and attached to
    a Player by name."""

    name: str
    club: Optional[str]
    position: Optional[str]
    minutes: Optional[int]
    metrics: dict[str, float] = field(default_factory=dict)

    def metric(self, name: str) -> Optional[float]:
        """None means the export had no value for this metric — deliberately
        distinct from 0.0, which means the player genuinely produced none."""
        return self.metrics.get(name)


@dataclass
class Player:
    name: str
    age: int
    position: str
    height_cm: Optional[int]
    ca: Optional[int]
    pa: Optional[int]
    wage: Optional[int]
    contract_end: Optional[str]
    value_low: Optional[int]
    value_high: Optional[int]
    status: list[str] = field(default_factory=list)
    personality: Optional[str] = None
    nationality: Optional[str] = None
    attributes: dict[str, int] = field(default_factory=dict)
    club: Optional[str] = None
    apps_starts: Optional[int] = None
    apps_subs: Optional[int] = None
    minutes_played: Optional[int] = None
    actual_playing_time: Optional[str] = None
    agreed_playing_time: Optional[str] = None
    last_transfer_fee: Optional[int] = None
    recurring_injury: Optional[str] = None
    stats: Optional[PlayerStats] = None

    def attr(self, name: str) -> int:
        return self.attributes.get(name, 0)

    @property
    def is_goalkeeper(self) -> bool:
        return bool(re.match(r"^\s*GK\b", self.position, re.I))

    @property
    def is_available(self) -> bool:
        return not any(s in BLOCKING_STATUSES for s in self.status)


class ParseError(ValueError):
    pass


def _normalize(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


def _build_lookup() -> dict[str, list[tuple[str, str]]]:
    lookup: dict[str, list[tuple[str, str]]] = {}
    for canonical, aliases in FIELD_ALIASES.items():
        for a in aliases:
            lookup.setdefault(a, []).append(("field", canonical))
    for canonical, aliases in ATTRIBUTE_ALIASES.items():
        for a in [*aliases, _normalize(canonical)]:
            lookup.setdefault(a, []).append(("attr", canonical))
    return lookup


def _is_attribute_like(v: str) -> bool:
    """True for a bare 1-20 value or a scouted range like '11-15' (opposition
    exports show ranges instead of exact values for less-known players)."""
    v = v.strip()
    if v.isdigit():
        return 1 <= int(v) <= 20
    m = re.match(r"^(\d+)\s*-\s*(\d+)$", v)
    if m:
        lo, hi = int(m.group(1)), int(m.group(2))
        return 1 <= lo <= 20 and 1 <= hi <= 20
    return False


def _parse_int(v: Optional[str]) -> Optional[int]:
    if v is None:
        return None
    v = v.strip()
    if not v or v == "-":
        return None
    m = re.search(r"-?\d+", v)
    if not m:
        return None
    return int(m.group())


def _parse_attr(v: Optional[str]) -> Optional[int]:
    """Attribute value, tolerant of scouted ranges ('11-15' -> midpoint 13)
    that appear for less-known players in opposition/league exports."""
    if v is None:
        return None
    v = v.strip()
    if not v or v == "-":
        return None
    m = re.match(r"^(\d+)\s*-\s*(\d+)$", v)
    if m:
        lo, hi = int(m.group(1)), int(m.group(2))
        return round((lo + hi) / 2)
    m = re.search(r"-?\d+", v)
    if not m:
        return None
    return int(m.group())


def parse_wage(text: Optional[str]) -> Optional[int]:
    if not text:
        return None
    text = text.strip()
    if not text or text.lower() in {"n/a", "not disclosed", "-"}:
        return None
    m = re.search(r"([\d,]+(?:\.\d+)?)\s*(K|M)?", text, re.IGNORECASE)
    if not m or not m.group(1):
        return None
    try:
        num = float(m.group(1).replace(",", ""))
    except ValueError:
        return None
    suffix = (m.group(2) or "").upper()
    if suffix == "K":
        num *= 1_000
    elif suffix == "M":
        num *= 1_000_000
    return int(round(num))


def parse_budget(text: Optional[str], label: str, *, min_sane: int = 1_000) -> Optional[int]:
    """Like parse_wage, but for a user-typed budget figure (CLI flag or Colab
    field) rather than a value already printed by FM. People type these in
    every format imaginable — this warns rather than silently misreading
    when the number has no K/M unit and comes out suspiciously small, since
    that's almost always a missing "M" (e.g. "20" meant as "£20M")."""
    value = parse_wage(text)
    if value is not None and value < min_sane and not re.search(r"[km]", text, re.IGNORECASE):
        numeric = re.sub(r"[^\d.]", "", text).strip() or text.strip()
        print(
            f"[budget] WARNING: {label} '{text.strip()}' parsed as £{value:,} — "
            f"if you meant £{numeric}M or £{numeric}K, spell out the unit "
            f"(e.g. '£{numeric}M'), otherwise this is being taken literally."
        )
    return value


def parse_value(text: Optional[str]) -> tuple[Optional[int], Optional[int]]:
    if not text:
        return (None, None)
    tokens = re.findall(r"([\d,]+(?:\.\d+)?)\s*(K|M)?", text)
    tokens = [t for t in tokens if t[0]]
    if not tokens:
        return (None, None)

    def to_num(tok: tuple[str, str]) -> int:
        num = float(tok[0].replace(",", ""))
        if tok[1] == "K":
            num *= 1_000
        elif tok[1] == "M":
            num *= 1_000_000
        return int(round(num))

    if len(tokens) >= 2:
        return (to_num(tokens[0]), to_num(tokens[1]))
    val = to_num(tokens[0])
    return (val, val)


def parse_height(text: Optional[str]) -> Optional[int]:
    if not text:
        return None
    text = text.strip()
    m = re.search(r"(\d+)\s*cm", text, re.I)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d+)\s*'\s*(\d+)", text)
    if m:
        feet, inches = int(m.group(1)), int(m.group(2))
        return round(feet * 30.48 + inches * 2.54)
    m = re.match(r"^(\d{3})$", text)
    if m:
        return int(m.group(1))
    return None


def parse_apps(text: Optional[str]) -> tuple[Optional[int], Optional[int]]:
    """'44 (3)' -> (44, 3) [starts, sub appearances]. Bare '50' -> (50, 0)."""
    if not text:
        return (None, None)
    text = text.strip()
    if not text or text == "-":
        return (None, None)
    m = re.match(r"^(\d+)\s*(?:\((\d+)\))?$", text)
    if not m:
        return (None, None)
    starts = int(m.group(1))
    subs = int(m.group(2)) if m.group(2) else 0
    return (starts, subs)


def parse_minutes(text: Optional[str]) -> Optional[int]:
    """'3,330' -> 3330. '-' -> None."""
    if not text:
        return None
    text = text.strip()
    if not text or text == "-":
        return None
    m = re.match(r"^([\d,]+)$", text)
    if not m:
        return None
    return int(m.group(1).replace(",", ""))


# Some FM views compress the Info column to narrow fixed-width codes
# instead of full words (e.g. "Inj" instead of "Injured"). Matched only
# against the whole (stripped) cell — never as a substring — since a
# short code is too short to safely substring-match against arbitrary
# longer text. Shared across squad and league exports since these are
# genuine player statuses regardless of which view they appear in.
SHORT_STATUS_CODES: dict[str, str] = {
    "inj": "Injured",
    "sus": "Suspended",
    "lst": "Transfer Listed",
    "yth": "Youth",
    "wnt": "Wanted",
    "trn": "Transfer Arranged",
    "esc": "Work Permit Exception",
    "ret": "Retiring",
    "ask": "Asked to Leave",
    "neu": "Non-EU",
    "rst": "Rested",
    "wp": "Requires Work Permit",
}


def parse_status(text: Optional[str]) -> list[str]:
    if not text:
        return []
    lowered = text.lower().strip()
    statuses: list[str] = []
    if "on loan from" in lowered:
        statuses.append("On Loan From")
    elif "on loan" in lowered:
        statuses.append("On Loan")
    if "injured" in lowered or "injury" in lowered:
        statuses.append("Injured")
    if "suspended" in lowered:
        statuses.append("Suspended")
    if "unavailable" in lowered:
        statuses.append("Unavailable")
    if "transfer listed" in lowered:
        statuses.append("Transfer Listed")
    if "loan listed" in lowered:
        statuses.append("Loan Listed")
    if "unhappy" in lowered:
        statuses.append("Unhappy")
    if "not needed" in lowered:
        statuses.append("Not needed")
    if not statuses and lowered in SHORT_STATUS_CODES:
        statuses.append(SHORT_STATUS_CODES[lowered])
    return statuses


def _find_table(soup: BeautifulSoup):
    tables = soup.find_all("table")
    if not tables:
        raise ParseError("No <table> found in HTML export")
    for table in tables:
        rows = table.find_all("tr")
        if not rows:
            continue
        header_cells = rows[0].find_all(["th", "td"])
        header_texts = [_normalize(c.get_text(strip=True)) for c in header_cells]
        if "name" in header_texts:
            return table
    return max(tables, key=lambda t: len(t.find_all("tr")))


def _fmt_full(n: float) -> str:
    return f"£{n:,.0f}"


def _fmt_abbrev(n: float) -> str:
    if n >= 1_000_000:
        return f"£{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"£{n / 1_000:.0f}K"
    return f"£{n:.0f}"


def _load_table(path: str) -> tuple[list[str], list[list[str]]]:
    html = Path(path).read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(html, "lxml")
    table = _find_table(soup)
    rows = table.find_all("tr")
    if not rows:
        raise ParseError("Table has no rows")

    header_cells = rows[0].find_all(["th", "td"])
    headers = [c.get_text(strip=True) for c in header_cells]

    data_rows: list[list[str]] = []
    for tr in rows[1:]:
        cells = tr.find_all("td")
        if not cells:
            continue
        data_rows.append([c.get_text(strip=True) for c in cells])

    return headers, data_rows


def _resolve_columns(headers: list[str], data_rows: list[list[str]]) -> tuple[dict[str, int], dict[str, int]]:
    lookup = _build_lookup()
    field_columns: dict[str, int] = {}
    attr_columns: dict[str, int] = {}
    ambiguous: dict[int, list[tuple[str, str]]] = {}

    for idx, raw in enumerate(headers):
        norm = _normalize(raw)
        if not norm:
            continue
        candidates = lookup.get(norm)
        if not candidates:
            continue
        if len(candidates) == 1:
            kind, canonical = candidates[0]
            if kind == "field" and canonical not in field_columns:
                field_columns[canonical] = idx
            elif kind == "attr" and canonical not in attr_columns:
                attr_columns[canonical] = idx
        else:
            ambiguous[idx] = candidates

    for idx, candidates in ambiguous.items():
        # "-" is a common "unscouted/unknown" placeholder in both numeric and
        # text columns, so it carries no type signal — exclude it before sniffing.
        sample = [r[idx] for r in data_rows if idx < len(r) and r[idx] and r[idx] != "-"]
        numeric = bool(sample) and all(_is_attribute_like(v) for v in sample[:10])
        chosen = None
        for kind, canonical in candidates:
            if kind == "attr" and numeric:
                chosen = (kind, canonical)
                break
            if kind == "field" and not numeric:
                chosen = (kind, canonical)
                break
        if chosen is None:
            chosen = candidates[0]
        kind, canonical = chosen
        if kind == "field" and canonical not in field_columns:
            field_columns[canonical] = idx
        elif kind == "attr" and canonical not in attr_columns:
            attr_columns[canonical] = idx

    return field_columns, attr_columns


def _build_players(
    data_rows: list[list[str]], field_columns: dict[str, int], attr_columns: dict[str, int]
) -> tuple[list[Player], dict]:
    def get(row: list[str], idx: Optional[int]) -> str:
        if idx is None or idx >= len(row):
            return ""
        return row[idx]

    players: list[Player] = []
    attr_full_count = 0
    wage_count = 0
    value_count = 0
    height_count = 0
    contract_count = 0
    total_wage = 0
    status_counter: dict[str, int] = {}
    heights: list[int] = []
    apps_present_count = 0
    clubs: set[str] = set()

    for row in data_rows:
        name = get(row, field_columns.get("name"))
        lowered_name = name.lower()
        for suffix in NAME_SUFFIXES_TO_STRIP:
            if lowered_name.endswith(suffix):
                name = name[: -len(suffix)].strip()
                break
        if not name:
            continue

        age = _parse_int(get(row, field_columns.get("age"))) or 0
        position = get(row, field_columns.get("position"))
        height_cm = parse_height(get(row, field_columns.get("height")))
        ca = _parse_int(get(row, field_columns.get("ca")))
        pa = _parse_int(get(row, field_columns.get("pa")))
        wage = parse_wage(get(row, field_columns.get("wage")))
        contract_end = get(row, field_columns.get("contract_end")) or None
        value_low, value_high = parse_value(get(row, field_columns.get("value")))
        info_text = get(row, field_columns.get("info"))
        status = parse_status(info_text)
        personality = get(row, field_columns.get("personality")) or None
        nationality = get(row, field_columns.get("nationality")) or None
        club = get(row, field_columns.get("club")) or None
        apps_starts, apps_subs = parse_apps(get(row, field_columns.get("apps")))
        minutes_played = parse_minutes(get(row, field_columns.get("minutes")))
        actual_playing_time = get(row, field_columns.get("actual_playing_time")) or None
        agreed_playing_time = get(row, field_columns.get("agreed_playing_time")) or None
        last_transfer_fee = parse_wage(get(row, field_columns.get("last_transfer_fee")))
        recurring_injury = get(row, field_columns.get("recurring_injury")) or None
        if recurring_injury == "-":
            recurring_injury = None

        attributes: dict[str, int] = {}
        full = True
        for attr_name, idx in attr_columns.items():
            val = _parse_attr(get(row, idx))
            if val is None:
                full = False
                val = 0
            attributes[attr_name] = val
        if full:
            attr_full_count += 1

        if wage is not None:
            wage_count += 1
            total_wage += wage
        if value_low is not None:
            value_count += 1
        if height_cm is not None:
            height_count += 1
            heights.append(height_cm)
        if contract_end:
            contract_count += 1
        for s in status:
            status_counter[s] = status_counter.get(s, 0) + 1
        if club:
            clubs.add(club)
        if (apps_starts or 0) + (apps_subs or 0) > 0:
            apps_present_count += 1

        players.append(
            Player(
                name=name,
                age=age,
                position=position,
                height_cm=height_cm,
                ca=ca,
                pa=pa,
                wage=wage,
                contract_end=contract_end,
                value_low=value_low,
                value_high=value_high,
                status=status,
                personality=personality,
                nationality=nationality,
                attributes=attributes,
                club=club,
                apps_starts=apps_starts,
                apps_subs=apps_subs,
                minutes_played=minutes_played,
                actual_playing_time=actual_playing_time,
                agreed_playing_time=agreed_playing_time,
                last_transfer_fee=last_transfer_fee,
                recurring_injury=recurring_injury,
            )
        )

    stats = {
        "attr_columns_count": len(attr_columns),
        "attr_full_count": attr_full_count,
        "wage_count": wage_count,
        "value_count": value_count,
        "height_count": height_count,
        "contract_count": contract_count,
        "total_wage": total_wage,
        "status_counter": status_counter,
        "heights": heights,
        "apps_present_count": apps_present_count,
        "club_count": len(clubs),
    }
    return players, stats


def _parse_players_table(path: str, required_fields: list[str]) -> tuple[list[Player], dict[str, int], dict]:
    headers, data_rows = _load_table(path)
    field_columns, attr_columns = _resolve_columns(headers, data_rows)

    missing_fields = [f for f in required_fields if f not in field_columns]
    if missing_fields:
        raise ParseError(f"Missing required column(s): {', '.join(missing_fields)}")

    missing_attrs = [a for a in ALL_ATTRIBUTES if a not in attr_columns]
    if missing_attrs:
        raise ParseError(
            f"Missing required attribute column(s): {', '.join(missing_attrs)}"
        )

    players, stats = _build_players(data_rows, field_columns, attr_columns)
    return players, field_columns, stats


def parse_squad(path: str) -> list[Player]:
    players, field_columns, stats = _parse_players_table(path, REQUIRED_FIELDS)

    for label in RECOMMENDED_FIELDS:
        if label not in field_columns:
            print(f"[parser] WARNING: recommended column not found: {label}")

    n = len(players)
    print(f"[parser] Parsed {n} players")
    print(
        f"[parser] Attribute coverage: {stats['attr_columns_count']}/47 attributes present, "
        f"{stats['attr_full_count']}/{n} players with full attributes"
    )
    wage_yr = stats["total_wage"] * 52
    print(
        f"[parser] Wage coverage: {stats['wage_count']}/{n} players "
        f"({_fmt_full(stats['total_wage'])}/w total, {_fmt_abbrev(wage_yr)}/yr)"
    )
    print(f"[parser] Value coverage: {stats['value_count']}/{n} players")
    heights = stats["heights"]
    avg_height = round(sum(heights) / len(heights)) if heights else 0
    print(f"[parser] Height coverage: {stats['height_count']}/{n} players (avg {avg_height}cm)")

    status_counter = stats["status_counter"]
    status_order = [
        "Injured", "Suspended", "Unavailable", "Transfer Listed",
        "Loan Listed", "On Loan", "On Loan From", "Unhappy", "Not needed",
    ]
    status_parts = [
        f"{status_counter[s]} {s.lower()}" for s in status_order if status_counter.get(s)
    ]
    print(f"[parser] Status flags detected: {', '.join(status_parts) if status_parts else 'none'}")
    print(f"[parser] Contract end coverage: {stats['contract_count']}/{n} players")

    if n == 0:
        print("[parser] WARNING: 0 players parsed")
    elif n and stats["attr_full_count"] / n < 1.0:
        print(
            f"[parser] WARNING: attribute coverage below 100% "
            f"({stats['attr_full_count']}/{n} players with full attributes)"
        )
    if n and stats["wage_count"] / n < 0.5:
        print(f"[parser] WARNING: wage coverage below 50% ({stats['wage_count']}/{n} players)")

    return players


def parse_league(path: str) -> list[Player]:
    players, _field_columns, stats = _parse_players_table(path, LEAGUE_REQUIRED_FIELDS)

    n = len(players)
    print(f"[league] Parsed {n} players across {stats['club_count']} clubs")
    print(
        f"[league] Attribute coverage: {stats['attr_columns_count']}/47 attributes present, "
        f"{stats['attr_full_count']}/{n} players with full attributes"
    )
    apps_present = stats["apps_present_count"]
    ratio = apps_present / n if n else 0.0
    print(f"[league] Apps coverage: {apps_present}/{n} players with at least 1 appearance ({ratio * 100:.0f}%)")
    if n and ratio < 0.10:
        print(
            "[league] WARNING: apps data looks sparse — likely pre-season, "
            "benchmark will behave like an unweighted average"
        )
    if n == 0:
        print("[league] WARNING: 0 players parsed")

    return players


# ---------------------------------------------------------------------------
# Match statistics export
# ---------------------------------------------------------------------------

def _clean_stat_name(raw: str) -> str:
    """FM's statistics views render the name cell as "Name - Name". Left as
    it is, nothing would ever match the squad export. Only collapse when
    both halves are identical, so a genuine hyphenated club/name string
    isn't truncated."""
    name = raw.strip()
    lowered = name.lower()
    for suffix in NAME_SUFFIXES_TO_STRIP:
        if lowered.endswith(suffix):
            return name[: -len(suffix)].strip()
    if " - " in name:
        left, _, right = name.partition(" - ")
        if left.strip().lower() == right.strip().lower():
            return left.strip()
    return name


def _parse_stat_value(v: Optional[str]) -> Optional[float]:
    """Numeric metric value. Handles FM's "76%", "1,910" and "-"; returns
    None (not 0.0) for anything absent, because "no data" and "produced
    none" are different facts and the scoring treats them differently."""
    if v is None:
        return None
    v = v.strip().replace(",", "").replace("%", "")
    if not v or v == "-":
        return None
    m = re.search(r"-?\d+(?:\.\d+)?", v)
    if not m:
        return None
    return float(m.group())


def _parse_minutes_value(v: Optional[str]) -> Optional[int]:
    value = _parse_stat_value(v)
    return None if value is None else int(value)


def _resolve_stat_columns(headers: list[str]) -> tuple[dict[str, int], dict[str, int]]:
    """Map headers to (field columns, metric columns). Metric headers are
    matched on their canonical spelling first, then via STAT_ALIASES."""
    canonical_by_norm = {_normalize(m): m for m in STAT_METRICS}
    field_lookup: dict[str, str] = {}
    for canonical, aliases in FIELD_ALIASES.items():
        for a in aliases:
            field_lookup.setdefault(a, canonical)

    field_columns: dict[str, int] = {}
    metric_columns: dict[str, int] = {}
    for idx, raw in enumerate(headers):
        norm = _normalize(raw)
        if not norm:
            continue
        metric = canonical_by_norm.get(norm) or STAT_ALIASES.get(norm)
        if metric and metric not in metric_columns:
            metric_columns[metric] = idx
            continue
        # "Mins" resolves as a field (minutes), not a metric — the scoring
        # uses it as a sample-size gate rather than as a rated output.
        field = field_lookup.get(norm)
        if field and field not in field_columns:
            field_columns[field] = idx
    return field_columns, metric_columns


def parse_stats(path: str) -> dict[str, PlayerStats]:
    """Parse an FM match-statistics export, keyed by player name.

    Deliberately does not go through _parse_players_table: that requires all
    47 attribute columns, and a statistics view has none of them.
    """
    headers, data_rows = _load_table(path)
    field_columns, metric_columns = _resolve_stat_columns(headers)

    missing = [f for f in STATS_REQUIRED_COLUMNS if f not in field_columns]
    if missing:
        labels = {"name": "Player", "minutes": "Mins"}
        raise ParseError(
            "Stats export is missing required column(s): "
            + ", ".join(labels.get(f, f) for f in missing)
        )

    def get(row: list[str], idx: Optional[int]) -> str:
        if idx is None or idx >= len(row):
            return ""
        return row[idx]

    by_name: dict[str, PlayerStats] = {}
    for row in data_rows:
        name = _clean_stat_name(get(row, field_columns.get("name")))
        if not name:
            continue
        metrics = {}
        for metric, idx in metric_columns.items():
            value = _parse_stat_value(get(row, idx))
            if value is not None:
                metrics[metric] = value
        by_name[name] = PlayerStats(
            name=name,
            club=get(row, field_columns.get("club")) or None,
            position=get(row, field_columns.get("position")) or None,
            # Not _parse_int: FM comma-groups minutes ("1,910"), which that
            # would silently truncate to 1.
            minutes=_parse_minutes_value(get(row, field_columns.get("minutes"))),
            metrics=metrics,
        )

    n = len(by_name)
    print(f"[stats] Parsed match stats for {n} players")
    print(f"[stats] Metric coverage: {len(metric_columns)}/{len(STAT_METRICS)} metric columns present")
    absent = [m for m in STAT_METRICS if m not in metric_columns]
    if absent:
        print(f"[stats] WARNING: metric column(s) not found: {', '.join(absent)}")
    if n == 0:
        print("[stats] WARNING: 0 players parsed from the stats export")

    return by_name


def attach_stats(players: list[Player], stats_by_name: dict[str, PlayerStats]) -> dict:
    """Attach stats to squad players by name, reporting misses both ways.

    Name mismatches between two exports of the same save are the likely
    failure here, so neither direction is swallowed: a squad player with no
    stats row and a stats row matching no squad player are both surfaced.
    """
    matched = 0
    for player in players:
        found = stats_by_name.get(player.name)
        if found is not None:
            player.stats = found
            matched += 1

    squad_names = {p.name for p in players}
    result = {
        "matched": matched,
        "squad_without_stats": sorted(p.name for p in players if p.stats is None),
        "stats_without_squad": sorted(n for n in stats_by_name if n not in squad_names),
    }

    print(f"[stats] Matched {matched}/{len(players)} squad players to a stats row")
    if result["squad_without_stats"]:
        print(
            f"[stats] No stats row for {len(result['squad_without_stats'])} squad player(s): "
            + ", ".join(result["squad_without_stats"][:10])
            + (" ..." if len(result["squad_without_stats"]) > 10 else "")
        )
    if result["stats_without_squad"]:
        print(
            f"[stats] {len(result['stats_without_squad'])} stats row(s) matched no squad player "
            "(expected if the stats export covers more than your own squad)"
        )
    if players and matched == 0:
        print(
            "[stats] WARNING: nothing matched — the stats export is probably from a different save "
            "or a different club than the squad export"
        )

    return result
