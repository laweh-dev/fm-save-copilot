"""Tactical style-fit engine: how well each player suits a manager-chosen
playing style, independent of role-fit.

Position-aware: the same style asks different things of different
positions (e.g. under a low block, defenders need positional discipline,
attackers need raw pace), so every style is broken out across 8 position
groups rather than scored with one flat attribute table.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fm_copilot.parser import Player

EXCELS_THRESHOLD = 75.0
SOLID_THRESHOLD = 60.0
BELOW_PAR_THRESHOLD = 40.0

TIER_LABELS = {
    "excels": "Does very well",
    "solid": "Does well",
    "below_par": "Doesn't do well",
    "poor_fit": "Doesn't work at all",
}

TIER_WEIGHTS = {"KEY": 5, "PREF": 3, "OTHER": 1}

POSITION_GROUPS = ["GK", "FB", "CB", "DM", "CM", "AM", "WI", "ST"]

STYLE_LABELS = {
    "possession_press": "Control Possession & High Press",
    "gegenpress": "Gegenpress",
    "low_block_counter": "Low Block & Fast Counters",
    "low_block_timewaste": "Low Block & Waste Time",
    "low_block_direct": "Low Block & Direct Long Passing",
    "tiki_taka": "Tiki-Taka",
}

STYLE_ALIASES = {
    "possession_press": [
        "control possession and high press", "control possession & high press",
        "possession press", "possession and high press", "high press possession",
        "control possession", "high press",
    ],
    "gegenpress": ["gegenpress", "gegen press", "gegen-press", "gegenpressing"],
    "low_block_counter": [
        "low block and fast counters", "low block & fast counters",
        "low block counter", "low block counters", "fast counters", "counter attack",
    ],
    "low_block_timewaste": [
        "low block and waste time", "low block & waste time",
        "low block time waste", "waste time", "time wasting", "park the bus",
    ],
    "low_block_direct": [
        "low block and direct long passing", "low block & direct long passing",
        "low block direct", "direct long passing", "direct football", "route one",
    ],
    "tiki_taka": ["tiki-taka", "tiki taka", "tikitaka"],
}

# Weight tables: STYLE_WEIGHTS[style_key][position_group] = {"KEY": [...], "PREF": [...], "OTHER": [...]}
STYLE_WEIGHTS: dict[str, dict[str, dict[str, list[str]]]] = {
    "possession_press": {
        "GK": {"KEY": ["Passing", "Composure", "Decisions"], "PREF": ["Rushing Out", "First Touch", "Technique"], "OTHER": ["Vision", "Anticipation", "Communication"]},
        "FB": {"KEY": ["Passing", "Work Rate", "Positioning"], "PREF": ["Decisions", "Technique", "Anticipation"], "OTHER": ["Stamina", "First Touch", "Teamwork", "Aggression"]},
        "CB": {"KEY": ["Passing", "Composure", "Decisions"], "PREF": ["Positioning", "Technique", "Anticipation"], "OTHER": ["Marking", "Tackling", "Pace", "Aggression"]},
        "DM": {"KEY": ["Passing", "Technique", "Decisions"], "PREF": ["Work Rate", "Anticipation", "Positioning"], "OTHER": ["Stamina", "Teamwork", "Tackling", "Composure"]},
        "CM": {"KEY": ["Passing", "Work Rate", "Decisions"], "PREF": ["Technique", "First Touch", "Stamina"], "OTHER": ["Anticipation", "Teamwork", "Composure", "Off the Ball"]},
        "AM": {"KEY": ["Passing", "Technique", "Vision"], "PREF": ["Decisions", "First Touch", "Off the Ball"], "OTHER": ["Work Rate", "Anticipation", "Composure", "Flair"]},
        "WI": {"KEY": ["Technique", "Off the Ball", "Work Rate"], "PREF": ["Passing", "First Touch", "Decisions"], "OTHER": ["Dribbling", "Pace", "Stamina", "Anticipation"]},
        "ST": {"KEY": ["Work Rate", "First Touch", "Anticipation"], "PREF": ["Off the Ball", "Passing", "Decisions"], "OTHER": ["Composure", "Technique", "Finishing", "Stamina"]},
    },
    "gegenpress": {
        "GK": {"KEY": ["Reflexes", "Rushing Out", "Command of Area"], "PREF": ["Communication", "Concentration", "Anticipation"], "OTHER": ["Kicking", "Agility", "Decisions"]},
        "FB": {"KEY": ["Work Rate", "Aggression", "Stamina"], "PREF": ["Anticipation", "Tackling", "Acceleration"], "OTHER": ["Positioning", "Teamwork", "Pace", "Decisions"]},
        "CB": {"KEY": ["Aggression", "Anticipation", "Positioning"], "PREF": ["Tackling", "Work Rate", "Concentration"], "OTHER": ["Pace", "Bravery", "Decisions", "Marking"]},
        "DM": {"KEY": ["Work Rate", "Aggression", "Tackling"], "PREF": ["Anticipation", "Stamina", "Positioning"], "OTHER": ["Decisions", "Teamwork", "Bravery", "Passing"]},
        "CM": {"KEY": ["Work Rate", "Stamina", "Aggression"], "PREF": ["Anticipation", "Decisions", "Teamwork"], "OTHER": ["Tackling", "Determination", "Acceleration", "Pace"]},
        "AM": {"KEY": ["Work Rate", "Anticipation", "Off the Ball"], "PREF": ["Decisions", "Aggression", "Acceleration"], "OTHER": ["Passing", "Technique", "Stamina", "Determination"]},
        "WI": {"KEY": ["Work Rate", "Acceleration", "Pace"], "PREF": ["Anticipation", "Aggression", "Stamina"], "OTHER": ["Off the Ball", "Decisions", "Determination", "Dribbling"]},
        "ST": {"KEY": ["Work Rate", "Anticipation", "Aggression"], "PREF": ["Acceleration", "Determination", "Off the Ball"], "OTHER": ["Stamina", "Decisions", "Pace", "Finishing"]},
    },
    "low_block_counter": {
        "GK": {"KEY": ["Reflexes", "Handling", "Kicking"], "PREF": ["Concentration", "Command of Area", "Decisions"], "OTHER": ["Passing", "Communication", "Composure"]},
        "FB": {"KEY": ["Positioning", "Tackling", "Marking"], "PREF": ["Concentration", "Anticipation", "Pace"], "OTHER": ["Stamina", "Teamwork", "Acceleration", "Decisions"]},
        "CB": {"KEY": ["Positioning", "Tackling", "Marking"], "PREF": ["Concentration", "Anticipation", "Heading"], "OTHER": ["Bravery", "Strength", "Composure", "Decisions"]},
        "DM": {"KEY": ["Positioning", "Tackling", "Marking"], "PREF": ["Concentration", "Anticipation", "Decisions"], "OTHER": ["Teamwork", "Passing", "Composure", "Work Rate"]},
        "CM": {"KEY": ["Work Rate", "Decisions", "Passing"], "PREF": ["Positioning", "Tackling", "Marking"], "OTHER": ["Anticipation", "Teamwork", "Stamina", "Composure"]},
        "AM": {"KEY": ["Pace", "Off the Ball", "Decisions"], "PREF": ["Composure", "Acceleration", "Passing"], "OTHER": ["Technique", "Dribbling", "Vision", "Work Rate"]},
        "WI": {"KEY": ["Pace", "Acceleration", "Off the Ball"], "PREF": ["Dribbling", "Decisions", "Composure"], "OTHER": ["Work Rate", "Technique", "First Touch", "Anticipation"]},
        "ST": {"KEY": ["Pace", "Acceleration", "Off the Ball"], "PREF": ["Composure", "Finishing", "Decisions"], "OTHER": ["Anticipation", "Dribbling", "First Touch", "Work Rate"]},
    },
    "low_block_timewaste": {
        "GK": {"KEY": ["Command of Area", "Handling", "Communication"], "PREF": ["Concentration", "Composure", "Decisions"], "OTHER": ["Kicking", "Reflexes", "Aerial Reach"]},
        "FB": {"KEY": ["Positioning", "Tackling", "Marking"], "PREF": ["Concentration", "Determination", "Composure"], "OTHER": ["Teamwork", "Anticipation", "Strength", "Decisions"]},
        "CB": {"KEY": ["Positioning", "Tackling", "Marking"], "PREF": ["Concentration", "Determination", "Composure"], "OTHER": ["Bravery", "Strength", "Heading", "Decisions"]},
        "DM": {"KEY": ["Positioning", "Tackling", "Determination"], "PREF": ["Marking", "Concentration", "Composure"], "OTHER": ["Teamwork", "Decisions", "Strength", "Anticipation"]},
        "CM": {"KEY": ["Determination", "Decisions", "Teamwork"], "PREF": ["Positioning", "Composure", "Concentration"], "OTHER": ["Tackling", "Passing", "Work Rate", "Stamina"]},
        "AM": {"KEY": ["Decisions", "Composure", "Teamwork"], "PREF": ["Technique", "Passing", "Determination"], "OTHER": ["Off the Ball", "Vision", "Work Rate", "First Touch"]},
        "WI": {"KEY": ["Determination", "Work Rate", "Decisions"], "PREF": ["Composure", "Technique", "Teamwork"], "OTHER": ["Dribbling", "Pace", "Stamina", "First Touch"]},
        "ST": {"KEY": ["Composure", "Determination", "Strength"], "PREF": ["Decisions", "Teamwork", "Finishing"], "OTHER": ["Heading", "First Touch", "Work Rate", "Anticipation"]},
    },
    "low_block_direct": {
        "GK": {"KEY": ["Kicking", "Reflexes", "Handling"], "PREF": ["Command of Area", "Concentration", "Decisions"], "OTHER": ["Aerial Reach", "Communication", "Composure"]},
        "FB": {"KEY": ["Positioning", "Tackling", "Marking"], "PREF": ["Crossing", "Concentration", "Strength"], "OTHER": ["Heading", "Anticipation", "Stamina", "Decisions"]},
        "CB": {"KEY": ["Positioning", "Tackling", "Marking"], "PREF": ["Heading", "Strength", "Jumping Reach"], "OTHER": ["Concentration", "Bravery", "Decisions", "Passing"]},
        "DM": {"KEY": ["Positioning", "Tackling", "Marking"], "PREF": ["Strength", "Concentration", "Passing"], "OTHER": ["Heading", "Teamwork", "Decisions", "Aggression"]},
        "CM": {"KEY": ["Passing", "Positioning", "Work Rate"], "PREF": ["Tackling", "Marking", "Strength"], "OTHER": ["Decisions", "Teamwork", "Stamina", "Heading"]},
        "AM": {"KEY": ["Off the Ball", "Decisions", "Strength"], "PREF": ["Heading", "First Touch", "Composure"], "OTHER": ["Technique", "Passing", "Anticipation", "Work Rate"]},
        "WI": {"KEY": ["Crossing", "Pace", "Off the Ball"], "PREF": ["Acceleration", "Decisions", "Composure"], "OTHER": ["Dribbling", "Technique", "First Touch", "Work Rate"]},
        "ST": {"KEY": ["Heading", "Strength", "Jumping Reach"], "PREF": ["Bravery", "Off the Ball", "Composure"], "OTHER": ["Finishing", "First Touch", "Anticipation", "Balance"]},
    },
    "tiki_taka": {
        "GK": {"KEY": ["Passing", "Technique", "Composure"], "PREF": ["Decisions", "First Touch", "Vision"], "OTHER": ["Kicking", "Anticipation", "Communication"]},
        "FB": {"KEY": ["Passing", "Technique", "First Touch"], "PREF": ["Decisions", "Positioning", "Composure"], "OTHER": ["Work Rate", "Anticipation", "Teamwork", "Stamina"]},
        "CB": {"KEY": ["Passing", "Composure", "Technique"], "PREF": ["Decisions", "First Touch", "Positioning"], "OTHER": ["Marking", "Tackling", "Anticipation", "Vision"]},
        "DM": {"KEY": ["Passing", "Technique", "Vision"], "PREF": ["Decisions", "First Touch", "Composure"], "OTHER": ["Work Rate", "Teamwork", "Anticipation", "Positioning"]},
        "CM": {"KEY": ["Passing", "Technique", "Decisions"], "PREF": ["First Touch", "Vision", "Teamwork"], "OTHER": ["Composure", "Off the Ball", "Work Rate", "Dribbling"]},
        "AM": {"KEY": ["Passing", "Technique", "Vision"], "PREF": ["First Touch", "Decisions", "Flair"], "OTHER": ["Composure", "Off the Ball", "Teamwork", "Dribbling"]},
        "WI": {"KEY": ["Technique", "First Touch", "Dribbling"], "PREF": ["Passing", "Off the Ball", "Decisions"], "OTHER": ["Flair", "Work Rate", "Composure", "Anticipation"]},
        "ST": {"KEY": ["First Touch", "Technique", "Off the Ball"], "PREF": ["Passing", "Composure", "Decisions"], "OTHER": ["Finishing", "Dribbling", "Anticipation", "Work Rate"]},
    },
}


def resolve_style_key(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text.strip().lower())
    for key, label in STYLE_LABELS.items():
        if normalized == label.lower():
            return key
    for key, aliases in STYLE_ALIASES.items():
        if normalized in aliases:
            return key
    valid = "; ".join(f'"{label}"' for label in STYLE_LABELS.values())
    raise ValueError(f'Unrecognised tactical direction "{text}". Valid options: {valid}')


def classify_position_group(position: str) -> str:
    first = position.split(",")[0].strip().upper()
    match = re.match(r"^([A-Z/]+)\s*(?:\(([A-Z]+)\))?", first)
    if not match:
        return "CM"
    code, zone = match.group(1), match.group(2) or ""

    if code == "GK":
        return "GK"
    if "WB" in code:
        return "FB"
    if code == "D":
        if not zone or "C" in zone:
            return "CB"
        return "FB"
    if code == "DM":
        return "DM"
    if code == "M":
        return "WI" if zone and "C" not in zone else "CM"
    if code == "AM":
        return "WI" if zone and "C" not in zone else "AM"
    if code in ("ST", "FW", "AF"):
        return "ST"
    return "CM"


def compute_style_score(player: "Player", style_key: str) -> float:
    position_group = classify_position_group(player.position)
    weights = STYLE_WEIGHTS[style_key][position_group]
    raw_score = 0
    max_score = 0
    for tier, attrs in weights.items():
        w = TIER_WEIGHTS[tier]
        for attr in attrs:
            raw_score += player.attr(attr) * w
            max_score += 20 * w
    if max_score == 0:
        return 0.0
    return round(raw_score / max_score * 100, 1)


def style_tier(score: float) -> str:
    if score >= EXCELS_THRESHOLD:
        return TIER_LABELS["excels"]
    if score >= SOLID_THRESHOLD:
        return TIER_LABELS["solid"]
    if score >= BELOW_PAR_THRESHOLD:
        return TIER_LABELS["below_par"]
    return TIER_LABELS["poor_fit"]


def compute_squad_style_fit(players: list["Player"], style_key: str) -> dict:
    entries = []
    tier_counts = {label: 0 for label in TIER_LABELS.values()}
    for p in players:
        position_group = classify_position_group(p.position)
        score = compute_style_score(p, style_key)
        tier = style_tier(score)
        tier_counts[tier] += 1
        entries.append((p.name, position_group, score, tier))
    entries.sort(key=lambda e: e[2], reverse=True)
    return {
        "style_key": style_key,
        "style_label": STYLE_LABELS[style_key],
        "player_scores": entries,
        "tier_counts": tier_counts,
    }
