"""FM24 squad HTML export -> typed Player list.

Column mapping is by header name, never by position, because column
availability depends on the view the user configured in-game. Header
aliases (FM's short codes like "Pac", "Wor", "Tck") are resolved via
ATTRIBUTE_ALIASES / FIELD_ALIASES below.
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
}

# Some FM export views render the name column as an interactive "pick
# player" widget; the flattened text carries a trailing action label that
# isn't part of the name.
NAME_SUFFIXES_TO_STRIP = [" - pick player"]

REQUIRED_FIELDS = ["name", "age", "position", "wage", "height"]
RECOMMENDED_FIELDS = ["contract_end", "ca", "pa", "value", "info", "personality", "nationality"]

BLOCKING_STATUSES = {"Injured", "On Loan", "Unavailable", "Suspended"}


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


def _is_small_int(v: str) -> bool:
    v = v.strip()
    return v.isdigit() and 1 <= int(v) <= 20


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


def parse_wage(text: Optional[str]) -> Optional[int]:
    if not text:
        return None
    text = text.strip()
    if not text or text.lower() in {"n/a", "not disclosed", "-"}:
        return None
    m = re.search(r"([\d,]+(?:\.\d+)?)\s*(K|M)?", text)
    if not m or not m.group(1):
        return None
    try:
        num = float(m.group(1).replace(",", ""))
    except ValueError:
        return None
    suffix = m.group(2)
    if suffix == "K":
        num *= 1_000
    elif suffix == "M":
        num *= 1_000_000
    return int(round(num))


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


# Some FM views compress the Info column to narrow fixed-width codes
# instead of full words (e.g. "Inj" instead of "Injured"). Matched only
# against the whole (stripped) cell — never as a substring — since a
# 3-letter code is too short to safely substring-match against arbitrary
# longer text.
SHORT_STATUS_CODES: dict[str, str] = {
    "inj": "Injured",
    "sus": "Suspended",
    "lst": "Transfer Listed",
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


def parse_squad(path: str) -> list[Player]:
    html = Path(path).read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(html, "lxml")
    table = _find_table(soup)
    rows = table.find_all("tr")
    if not rows:
        raise ParseError("Table has no rows")

    header_cells = rows[0].find_all(["th", "td"])
    headers = [c.get_text(strip=True) for c in header_cells]

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

    data_rows: list[list[str]] = []
    for tr in rows[1:]:
        cells = tr.find_all("td")
        if not cells:
            continue
        data_rows.append([c.get_text(strip=True) for c in cells])

    for idx, candidates in ambiguous.items():
        sample = [r[idx] for r in data_rows if idx < len(r) and r[idx]]
        numeric = bool(sample) and all(_is_small_int(v) for v in sample[:10])
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

    missing_fields = [f for f in REQUIRED_FIELDS if f not in field_columns]
    if missing_fields:
        raise ParseError(f"Missing required column(s): {', '.join(missing_fields)}")

    missing_attrs = [a for a in ALL_ATTRIBUTES if a not in attr_columns]
    if missing_attrs:
        raise ParseError(
            f"Missing required attribute column(s): {', '.join(missing_attrs)}"
        )

    for label in RECOMMENDED_FIELDS:
        if label not in field_columns:
            print(f"[parser] WARNING: recommended column not found: {label}")

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

        attributes: dict[str, int] = {}
        full = True
        for attr_name, idx in attr_columns.items():
            val = _parse_int(get(row, idx))
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
            )
        )

    n = len(players)
    print(f"[parser] Parsed {n} players")
    print(
        f"[parser] Attribute coverage: {len(attr_columns)}/47 attributes present, "
        f"{attr_full_count}/{n} players with full attributes"
    )
    wage_yr = total_wage * 52
    print(
        f"[parser] Wage coverage: {wage_count}/{n} players "
        f"({_fmt_full(total_wage)}/w total, {_fmt_abbrev(wage_yr)}/yr)"
    )
    print(f"[parser] Value coverage: {value_count}/{n} players")
    avg_height = round(sum(heights) / len(heights)) if heights else 0
    print(f"[parser] Height coverage: {height_count}/{n} players (avg {avg_height}cm)")

    status_order = [
        "Injured", "Suspended", "Unavailable", "Transfer Listed",
        "Loan Listed", "On Loan", "On Loan From", "Unhappy", "Not needed",
    ]
    status_parts = [
        f"{status_counter[s]} {s.lower()}" for s in status_order if status_counter.get(s)
    ]
    print(f"[parser] Status flags detected: {', '.join(status_parts) if status_parts else 'none'}")
    print(f"[parser] Contract end coverage: {contract_count}/{n} players")

    if n == 0:
        print("[parser] WARNING: 0 players parsed")
    elif n and attr_full_count / n < 1.0:
        print(
            f"[parser] WARNING: attribute coverage below 100% "
            f"({attr_full_count}/{n} players with full attributes)"
        )
    if n and wage_count / n < 0.5:
        print(f"[parser] WARNING: wage coverage below 50% ({wage_count}/{n} players)")

    return players
