"""Role-fit engine: the analytical spine everything else builds on.

Every player is scored against every supported FM24 role using a
KEY/PREF/OTHER weighted attribute table. Weights are hardcoded here,
football-sensible but not identical to FM's internal formulas.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from fm_copilot.parser import Player

CAPABLE_THRESHOLD = 60.0
STRONG_THRESHOLD = 70.0
ELITE_THRESHOLD = 75.0

TIER_WEIGHTS = {"KEY": 5, "PREF": 3, "OTHER": 1}

ROLE_WEIGHTS: dict[str, dict[str, list[str]]] = {
    # --- Goalkeepers ---
    "GK_d": {
        "KEY": ["Reflexes", "Handling", "Positioning", "Aerial Reach", "Command of Area", "Communication"],
        "PREF": ["One on Ones", "Concentration", "Decisions", "Anticipation", "Kicking"],
        "OTHER": ["Agility", "Composure", "Throwing", "Rushing Out", "Eccentricity"],
    },
    "SK_s": {
        "KEY": ["Reflexes", "Handling", "Rushing Out", "One on Ones", "Positioning"],
        "PREF": ["Aerial Reach", "Command of Area", "Communication", "Anticipation", "Decisions", "Kicking"],
        "OTHER": ["Agility", "Composure", "Concentration", "Throwing", "Acceleration", "Pace"],
    },

    # --- Defenders ---
    "CD_d": {
        "KEY": ["Heading", "Marking", "Tackling", "Positioning", "Strength", "Jumping Reach"],
        "PREF": ["Aggression", "Anticipation", "Bravery", "Concentration", "Decisions"],
        "OTHER": ["Composure", "Teamwork", "Pace", "Acceleration", "Agility", "Balance", "First Touch"],
    },
    "BPD_d": {
        "KEY": ["Heading", "Marking", "Tackling", "Positioning", "Passing", "Composure"],
        "PREF": ["Strength", "Jumping Reach", "Anticipation", "Decisions", "Vision", "Technique"],
        "OTHER": ["Aggression", "Bravery", "Concentration", "Teamwork", "First Touch", "Acceleration"],
    },
    "FB_d": {
        "KEY": ["Marking", "Tackling", "Positioning", "Anticipation"],
        "PREF": ["Concentration", "Decisions", "Teamwork", "Pace", "Stamina"],
        "OTHER": ["Heading", "Strength", "Acceleration", "Agility", "Composure", "Crossing"],
    },
    "FB_s": {
        "KEY": ["Marking", "Tackling", "Positioning", "Teamwork"],
        "PREF": ["Anticipation", "Decisions", "Crossing", "Stamina", "Work Rate", "Pace"],
        "OTHER": ["First Touch", "Passing", "Concentration", "Acceleration", "Agility", "Strength"],
    },
    "WB_s": {
        "KEY": ["Crossing", "Dribbling", "Technique", "Off the Ball", "Teamwork", "Work Rate", "Acceleration", "Pace", "Stamina"],
        "PREF": ["Tackling", "Anticipation", "Decisions", "Positioning"],
        "OTHER": ["First Touch", "Marking", "Passing", "Concentration", "Agility", "Balance"],
    },
    "WB_a": {
        "KEY": ["Crossing", "Dribbling", "Technique", "Off the Ball", "Acceleration", "Pace", "Stamina"],
        "PREF": ["First Touch", "Flair", "Work Rate", "Anticipation", "Decisions"],
        "OTHER": ["Tackling", "Marking", "Passing", "Positioning", "Agility", "Balance", "Finishing"],
    },
    "IWB_s": {
        "KEY": ["Passing", "Tackling", "Positioning", "Decisions", "Work Rate"],
        "PREF": ["Technique", "First Touch", "Anticipation", "Composure", "Vision", "Stamina"],
        "OTHER": ["Marking", "Teamwork", "Acceleration", "Pace", "Agility", "Crossing"],
    },

    # --- Defensive midfielders ---
    "DM_d": {
        "KEY": ["Tackling", "Positioning", "Marking", "Anticipation", "Concentration"],
        "PREF": ["Aggression", "Bravery", "Strength", "Decisions", "Teamwork"],
        "OTHER": ["Passing", "Composure", "Stamina", "Work Rate", "Jumping Reach", "First Touch"],
    },
    "DLP_d": {
        "KEY": ["Passing", "Technique", "Decisions", "Vision", "Composure"],
        "PREF": ["First Touch", "Anticipation", "Positioning", "Teamwork", "Concentration"],
        "OTHER": ["Tackling", "Marking", "Determination", "Flair", "Stamina", "Work Rate"],
    },
    "DLP_s": {
        "KEY": ["Passing", "Technique", "Decisions", "Vision", "First Touch"],
        "PREF": ["Composure", "Anticipation", "Teamwork", "Flair", "Off the Ball"],
        "OTHER": ["Tackling", "Positioning", "Determination", "Work Rate", "Stamina", "Dribbling"],
    },

    # --- Central midfielders ---
    "BWM_s": {
        "KEY": ["Tackling", "Aggression", "Anticipation", "Work Rate", "Stamina"],
        "PREF": ["Marking", "Bravery", "Concentration", "Determination", "Positioning", "Teamwork"],
        "OTHER": ["Passing", "Technique", "Composure", "Decisions", "Acceleration", "Pace", "Strength"],
    },
    "CM_s": {
        "KEY": ["Passing", "Decisions", "Teamwork", "Work Rate", "Stamina"],
        "PREF": ["First Touch", "Technique", "Vision", "Anticipation", "Tackling"],
        "OTHER": ["Composure", "Positioning", "Determination", "Dribbling", "Off the Ball", "Marking"],
    },
    "CM_a": {
        "KEY": ["Passing", "Decisions", "Off the Ball", "Technique", "Vision"],
        "PREF": ["First Touch", "Long Shots", "Composure", "Work Rate", "Anticipation"],
        "OTHER": ["Dribbling", "Finishing", "Flair", "Stamina", "Teamwork", "Determination"],
    },
    "BBM_s": {
        "KEY": ["Work Rate", "Stamina", "Tackling", "Passing", "Off the Ball"],
        "PREF": ["Determination", "Decisions", "Teamwork", "Aggression", "Acceleration", "Pace"],
        "OTHER": ["Technique", "First Touch", "Long Shots", "Composure", "Strength", "Anticipation"],
    },

    # --- Attacking midfielders ---
    "AP_s": {
        "KEY": ["Passing", "Technique", "Vision", "First Touch", "Decisions"],
        "PREF": ["Flair", "Composure", "Off the Ball", "Anticipation", "Teamwork"],
        "OTHER": ["Dribbling", "Long Shots", "Determination", "Work Rate", "Agility", "Balance"],
    },
    "AP_a": {
        "KEY": ["Passing", "Technique", "Vision", "First Touch", "Flair"],
        "PREF": ["Off the Ball", "Decisions", "Composure", "Dribbling", "Anticipation"],
        "OTHER": ["Long Shots", "Finishing", "Work Rate", "Agility", "Balance", "Determination"],
    },
    "RPM_s": {
        "KEY": ["Passing", "Technique", "Vision", "Decisions", "Stamina", "Work Rate"],
        "PREF": ["First Touch", "Composure", "Anticipation", "Off the Ball", "Teamwork"],
        "OTHER": ["Dribbling", "Tackling", "Flair", "Acceleration", "Pace", "Determination"],
    },

    # --- Wide attackers ---
    "W_s": {
        "KEY": ["Crossing", "Dribbling", "Technique", "Off the Ball"],
        "PREF": ["First Touch", "Passing", "Acceleration", "Pace", "Stamina", "Work Rate"],
        "OTHER": ["Flair", "Anticipation", "Composure", "Decisions", "Agility", "Balance"],
    },
    "W_a": {
        "KEY": ["Crossing", "Dribbling", "Technique", "Acceleration", "Pace"],
        "PREF": ["First Touch", "Passing", "Off the Ball", "Agility", "Stamina"],
        "OTHER": ["Finishing", "Flair", "Anticipation", "Composure", "Decisions", "Work Rate", "Balance"],
    },
    "IW_s": {
        "KEY": ["Dribbling", "Technique", "First Touch", "Off the Ball"],
        "PREF": ["Passing", "Vision", "Acceleration", "Pace", "Decisions"],
        "OTHER": ["Crossing", "Finishing", "Long Shots", "Flair", "Agility", "Balance", "Work Rate"],
    },
    "IW_a": {
        "KEY": ["Dribbling", "Technique", "Finishing", "Off the Ball", "Acceleration", "Pace"],
        "PREF": ["First Touch", "Passing", "Long Shots", "Flair", "Decisions"],
        "OTHER": ["Crossing", "Composure", "Vision", "Agility", "Balance", "Work Rate"],
    },

    # --- Strikers ---
    "TM_s": {
        "KEY": ["Heading", "Strength", "Jumping Reach", "Bravery"],
        "PREF": ["Balance", "First Touch", "Teamwork", "Off the Ball", "Aggression"],
        "OTHER": ["Passing", "Technique", "Composure", "Anticipation", "Finishing", "Decisions"],
    },
    "AF_a": {
        "KEY": ["Finishing", "Off the Ball", "Acceleration", "Pace", "Composure"],
        "PREF": ["First Touch", "Dribbling", "Anticipation", "Decisions", "Technique"],
        "OTHER": ["Heading", "Strength", "Balance", "Work Rate", "Determination", "Flair"],
    },
    "P_a": {
        "KEY": ["Finishing", "Composure", "Off the Ball", "Anticipation"],
        "PREF": ["Dribbling", "First Touch", "Heading", "Technique", "Decisions", "Acceleration", "Pace"],
        "OTHER": ["Determination", "Balance"],
    },
    "SS_a": {
        "KEY": ["Finishing", "Off the Ball", "Anticipation", "Composure", "Acceleration"],
        "PREF": ["First Touch", "Decisions", "Technique", "Long Shots", "Pace"],
        "OTHER": ["Dribbling", "Flair", "Determination", "Work Rate", "Vision", "Passing"],
    },
    "DLF_s": {
        "KEY": ["First Touch", "Passing", "Technique", "Off the Ball", "Composure"],
        "PREF": ["Vision", "Decisions", "Teamwork", "Heading", "Strength"],
        "OTHER": ["Finishing", "Dribbling", "Flair", "Anticipation", "Balance", "Work Rate"],
    },
}

ROLE_DISPLAY_NAMES = {
    "GK_d": "Goalkeeper Defend", "SK_s": "Sweeper Keeper Support",
    "CD_d": "Central Defender Defend", "BPD_d": "Ball Playing Defender Defend",
    "FB_d": "Full Back Defend", "FB_s": "Full Back Support",
    "WB_s": "Wing Back Support", "WB_a": "Wing Back Attack",
    "IWB_s": "Inverted Wing Back Support",
    "DM_d": "Defensive Midfielder Defend", "DLP_d": "Deep Lying Playmaker Defend",
    "DLP_s": "Deep Lying Playmaker Support",
    "BWM_s": "Ball Winning Midfielder Support", "CM_s": "Central Midfielder Support",
    "CM_a": "Central Midfielder Attack", "BBM_s": "Box to Box Midfielder Support",
    "AP_s": "Advanced Playmaker Support", "AP_a": "Advanced Playmaker Attack",
    "RPM_s": "Roaming Playmaker Support",
    "W_s": "Winger Support", "W_a": "Winger Attack",
    "IW_s": "Inverted Winger Support", "IW_a": "Inverted Winger Attack",
    "TM_s": "Target Man Support", "AF_a": "Advanced Forward Attack",
    "P_a": "Poacher Attack", "SS_a": "Shadow Striker Attack",
    "DLF_s": "Deep Lying Forward Support",
}

FORMATIONS: dict[str, list[tuple[str, list[str]]]] = {
    "4-2-3-1": [
        ("GK", ["GK_d", "SK_s"]), ("RB", ["FB_d", "FB_s"]), ("RCB", ["CD_d", "BPD_d"]),
        ("LCB", ["CD_d", "BPD_d"]), ("LB", ["FB_d", "FB_s"]),
        ("RDM", ["DM_d", "DLP_s", "DLP_d", "BWM_s"]), ("LDM", ["DM_d", "DLP_s", "DLP_d", "BWM_s"]),
        ("AM", ["AP_s", "AP_a", "RPM_s"]), ("RW", ["W_s", "W_a", "IW_s", "IW_a"]),
        ("LW", ["W_s", "W_a", "IW_s", "IW_a"]), ("ST", ["AF_a", "P_a", "DLF_s", "TM_s"]),
    ],
    "4-3-3": [
        ("GK", ["GK_d", "SK_s"]), ("RB", ["FB_d", "FB_s"]), ("RCB", ["CD_d", "BPD_d"]),
        ("LCB", ["CD_d", "BPD_d"]), ("LB", ["FB_d", "FB_s"]),
        ("DM", ["DM_d", "DLP_d", "BWM_s"]),
        ("RCM", ["CM_s", "CM_a", "BBM_s", "DLP_s"]), ("LCM", ["CM_s", "CM_a", "BBM_s", "DLP_s"]),
        ("RW", ["W_s", "W_a", "IW_s", "IW_a"]), ("LW", ["W_s", "W_a", "IW_s", "IW_a"]),
        ("ST", ["AF_a", "P_a", "DLF_s", "SS_a"]),
    ],
    "3-5-2": [
        ("GK", ["GK_d", "SK_s"]), ("RCB", ["CD_d", "BPD_d"]), ("CB", ["CD_d", "BPD_d"]),
        ("LCB", ["CD_d", "BPD_d"]), ("RWB", ["WB_s", "WB_a", "IWB_s"]), ("LWB", ["WB_s", "WB_a", "IWB_s"]),
        ("DM", ["DM_d", "DLP_d", "DLP_s", "BWM_s"]),
        ("RCM", ["CM_s", "CM_a", "BBM_s"]), ("LCM", ["CM_s", "CM_a", "BBM_s"]),
        ("RST", ["AF_a", "P_a", "DLF_s", "TM_s", "SS_a"]), ("LST", ["AF_a", "P_a", "DLF_s", "TM_s", "SS_a"]),
    ],
    "3-4-3": [
        ("GK", ["GK_d", "SK_s"]), ("RCB", ["CD_d", "BPD_d"]), ("CB", ["CD_d", "BPD_d"]),
        ("LCB", ["CD_d", "BPD_d"]), ("RWB", ["WB_s", "WB_a", "IWB_s"]), ("LWB", ["WB_s", "WB_a", "IWB_s"]),
        ("RCM", ["CM_s", "CM_a", "BBM_s", "BWM_s"]), ("LCM", ["CM_s", "CM_a", "BBM_s", "BWM_s"]),
        ("RW", ["W_s", "W_a", "IW_s", "IW_a"]), ("LW", ["W_s", "W_a", "IW_s", "IW_a"]),
        ("ST", ["AF_a", "P_a", "DLF_s", "TM_s", "SS_a"]),
    ],
    "4-4-2": [
        ("GK", ["GK_d", "SK_s"]), ("RB", ["FB_d", "FB_s"]), ("RCB", ["CD_d", "BPD_d"]),
        ("LCB", ["CD_d", "BPD_d"]), ("LB", ["FB_d", "FB_s"]),
        ("RM", ["W_s", "W_a", "IW_s", "IW_a"]),
        ("RCM", ["CM_s", "CM_a", "BBM_s", "DLP_s", "BWM_s"]), ("LCM", ["CM_s", "CM_a", "BBM_s", "DLP_s", "BWM_s"]),
        ("LM", ["W_s", "W_a", "IW_s", "IW_a"]),
        ("RST", ["AF_a", "P_a", "DLF_s", "TM_s", "SS_a"]), ("LST", ["AF_a", "P_a", "DLF_s", "TM_s", "SS_a"]),
    ],
    "3-4-2-1": [
        ("GK", ["GK_d", "SK_s"]), ("RCB", ["CD_d", "BPD_d"]), ("CB", ["CD_d", "BPD_d"]),
        ("LCB", ["CD_d", "BPD_d"]), ("RWB", ["WB_s", "WB_a", "IWB_s"]), ("LWB", ["WB_s", "WB_a", "IWB_s"]),
        ("RCM", ["CM_s", "DM_d", "DLP_d", "DLP_s", "BWM_s"]), ("LCM", ["CM_s", "DM_d", "DLP_d", "DLP_s", "BWM_s"]),
        ("AMR", ["AP_s", "AP_a", "RPM_s", "IW_a", "W_a"]), ("AML", ["AP_s", "AP_a", "RPM_s", "IW_a", "W_a"]),
        ("ST", ["AF_a", "P_a", "DLF_s", "TM_s", "SS_a"]),
    ],
}


# Which FM position families + sides can actually fill each formation slot.
# Attribute-based role scoring alone doesn't know a player has never played
# a position — a ball-winning DM can easily out-score a real fullback's
# attributes on FB_s's weight table. Sides of None means side-agnostic
# (goalkeepers, strikers — FM rarely tags a side for either).
SLOT_ELIGIBILITY: dict[str, tuple[set[str], Optional[set[str]]]] = {
    "GK": ({"GK"}, None),
    "RB": ({"D", "WB"}, {"R"}), "LB": ({"D", "WB"}, {"L"}),
    "RCB": ({"D"}, {"C"}), "LCB": ({"D"}, {"C"}), "CB": ({"D"}, {"C"}),
    "RWB": ({"D", "WB"}, {"R"}), "LWB": ({"D", "WB"}, {"L"}),
    "RDM": ({"DM"}, {"C"}), "LDM": ({"DM"}, {"C"}), "DM": ({"DM"}, {"C"}),
    "RCM": ({"M"}, {"C"}), "LCM": ({"M"}, {"C"}),
    "RM": ({"M", "AM"}, {"R"}), "LM": ({"M", "AM"}, {"L"}),
    "AM": ({"AM"}, {"C"}), "AMR": ({"AM"}, {"R"}), "AML": ({"AM"}, {"L"}),
    "RW": ({"AM", "M"}, {"R"}), "LW": ({"AM", "M"}, {"L"}),
    "ST": ({"ST"}, None), "RST": ({"ST"}, None), "LST": ({"ST"}, None),
}


def position_groups(position: str) -> list[tuple[set[str], set[str]]]:
    """'D/WB (L), M/AM (LC)' -> [({'D','WB'}, {'L'}), ({'M','AM'}, {'L','C'})].
    A bare family with no side in parens (e.g. 'DM') is always central.

    Public (not just an internal helper for _is_eligible below) — market_matching.py
    reuses it to gate market-candidate search by the same position vocabulary,
    rather than duplicating this parsing logic in a second module.
    """
    groups = []
    for part in position.split(","):
        part = part.strip()
        if not part:
            continue
        m = re.match(r"^([\w/]+)(?:\s*\(([RLC]+)\))?$", part)
        if not m:
            continue
        families = set(m.group(1).split("/"))
        sides = set(m.group(2)) if m.group(2) else {"C"}
        groups.append((families, sides))
    return groups


def _is_eligible(player: "Player", slot_name: str) -> bool:
    req_families, req_sides = SLOT_ELIGIBILITY.get(slot_name, (set(), None))
    for families, sides in position_groups(player.position):
        if families & req_families and (req_sides is None or sides & req_sides):
            return True
    return False


def role_eligible_families(role: str) -> set[str]:
    """Which FM position families (D/WB/DM/M/AM/ST/GK) can plausibly play a
    given role — derived from every slot that role appears in across all 6
    formations (see FORMATIONS/SLOT_ELIGIBILITY above), not a second
    hardcoded table, so it can't quietly drift out of sync with the Best XI
    eligibility rules. Some roles span more than one family (e.g. DLP_s
    fills both a DM slot in 4-2-3-1 and an M slot in 4-3-3) — that's a real
    property of the role, not a bug, so the union is the correct answer.
    """
    families: set[str] = set()
    for slots in FORMATIONS.values():
        for slot_name, eligible_roles in slots:
            if role in eligible_roles:
                slot_families, _slot_sides = SLOT_ELIGIBILITY.get(slot_name, (set(), None))
                families |= slot_families
    return families


def _role_score(player: "Player", role: str) -> float:
    weights = ROLE_WEIGHTS[role]
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


IDEAL_ATTRIBUTE_VALUES = {"KEY": 16, "PREF": 13, "OTHER": 11}


def ideal_attribute_values(role: str, n: int = 8) -> dict[str, int]:
    """Target attribute values for a role's top N most-weighted attributes —
    KEY tier -> 16, PREF -> 13, OTHER -> 11. Not a specific player's stats;
    a "what good looks like" benchmark derived straight from the role's own
    weight table (same tiers _role_score already uses), matching a common
    scouting-report convention. Used as the radar-chart benchmark line for
    Target Dossier candidates.
    """
    weights = ROLE_WEIGHTS[role]
    ordered = [(attr, tier) for tier in ("KEY", "PREF", "OTHER") for attr in weights.get(tier, [])]
    return {attr: IDEAL_ATTRIBUTE_VALUES[tier] for attr, tier in ordered[:n]}


def compute_role_scores(player: "Player") -> dict[str, float]:
    """Return {role_name: score} for all 28 roles."""
    return {role: _role_score(player, role) for role in ROLE_WEIGHTS}


def top_roles(player: "Player", n: int = 5) -> list[tuple[str, float]]:
    """Return [(role, score), ...] sorted desc."""
    scores = compute_role_scores(player)
    return sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:n]


def role_coverage(players: list["Player"]) -> dict[str, dict]:
    """Return {role: {'capable': [...], 'strong': [...], 'elite': [...]}}."""
    coverage = {role: {"capable": [], "strong": [], "elite": []} for role in ROLE_WEIGHTS}
    for player in players:
        scores = compute_role_scores(player)
        for role, score in scores.items():
            if score >= CAPABLE_THRESHOLD:
                coverage[role]["capable"].append(player.name)
            if score >= STRONG_THRESHOLD:
                coverage[role]["strong"].append(player.name)
            if score >= ELITE_THRESHOLD:
                coverage[role]["elite"].append(player.name)
    return coverage


def best_xi_for_formation(players: list["Player"], formation: str) -> dict:
    """
    Given available players and a formation string, return best XI:
    {position_slot: (player_name, role, score)}, plus total_score and
    structural_weaknesses. Greedy: fill each slot with the highest scorer
    at that slot's role, without repetition.

    Position-eligible players are always preferred — a player only gets
    slotted somewhere their listed FM position doesn't cover (see
    SLOT_ELIGIBILITY) as a last resort, when nobody eligible is left, and
    that placement is always flagged as a structural weakness regardless of
    its score: no natural option for that slot is a real coverage gap, not
    a stat-optimisation problem.
    """
    slots = FORMATIONS[formation]
    players_by_name = {p.name: p for p in players}
    player_scores = {p.name: compute_role_scores(p) for p in players}
    remaining = {p.name for p in players}

    xi: dict[str, tuple[str, str, float]] = {}
    structural_weaknesses: list[str] = []
    out_of_position_slots: list[str] = []
    total_score = 0.0

    for slot_name, eligible_roles in slots:
        best_eligible: Optional[tuple[str, str, float]] = None
        best_any: Optional[tuple[str, str, float]] = None
        for name in remaining:
            scores = player_scores[name]
            eligible = _is_eligible(players_by_name[name], slot_name)
            for role in eligible_roles:
                score = scores.get(role, 0.0)
                candidate = (name, role, score)
                if best_any is None or score > best_any[2]:
                    best_any = candidate
                if eligible and (best_eligible is None or score > best_eligible[2]):
                    best_eligible = candidate

        out_of_position = best_eligible is None
        chosen = best_eligible if best_eligible is not None else best_any
        if chosen is None:
            structural_weaknesses.append(slot_name)
            continue

        name, role, score = chosen
        xi[slot_name] = chosen
        remaining.discard(name)
        total_score += score
        if out_of_position:
            out_of_position_slots.append(slot_name)
            structural_weaknesses.append(slot_name)
        elif score < CAPABLE_THRESHOLD:
            structural_weaknesses.append(slot_name)

    return {
        "formation": formation,
        "xi": xi,
        "total_score": round(total_score, 1),
        "avg_score": round(total_score / len(slots), 1) if slots else 0.0,
        "structural_weaknesses": structural_weaknesses,
        "out_of_position_slots": out_of_position_slots,
    }


def formation_viability(players: list["Player"]) -> list[dict]:
    """
    Evaluate the 6 candidate formations against available players (not
    injured, not on loan out, not unavailable, not suspended). Return list
    sorted by total_score desc.
    """
    available = [p for p in players if p.is_available]
    results = []
    for formation in FORMATIONS:
        result = best_xi_for_formation(available, formation)
        results.append(result)
    results.sort(key=lambda r: r["total_score"], reverse=True)
    return results
