"""Player data -> deterministic facts. No LLM in this module.

Uses roles.py as the analytical spine: every downstream fact (tactical
impossibilities, recruitment priorities, exit candidates, ...) is derived
from role-fit scores, never guessed.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from fm_copilot import league_context, market_matching, roles, squad_audit as squad_audit_module, tactics
from fm_copilot.parser import Player

ROLE_GROUP = {
    "GK_d": "goalkeeper", "SK_s": "goalkeeper",
    "CD_d": "defence", "BPD_d": "defence", "FB_d": "defence", "FB_s": "defence",
    "WB_s": "defence", "WB_a": "defence", "IWB_s": "defence",
    "DM_d": "midfield", "DLP_d": "midfield", "DLP_s": "midfield",
    "BWM_s": "midfield", "CM_s": "midfield", "CM_a": "midfield", "BBM_s": "midfield",
    "AP_s": "attack", "AP_a": "attack", "RPM_s": "attack",
    "W_s": "attack", "W_a": "attack", "IW_s": "attack", "IW_a": "attack",
    "TM_s": "attack", "AF_a": "attack", "P_a": "attack", "SS_a": "attack", "DLF_s": "attack",
}

WIDE_SLOTS = {"RW", "LW", "RM", "LM", "AMR", "AML"}


def _mean(values: list[float]) -> float:
    values = list(values)
    return statistics.mean(values) if values else 0.0


def _best_role(scores: dict[str, float]) -> tuple[Optional[str], float]:
    if not scores:
        return (None, 0.0)
    role, score = max(scores.items(), key=lambda kv: kv[1])
    return (role, score)


def _position_code(position: str) -> str:
    first = position.split(",")[0].strip()
    code = re.split(r"[\s(]", first)[0].strip().upper()
    return code


def _position_group(position: str) -> str:
    code = _position_code(position)
    if code == "GK":
        return "goalkeeper"
    if code in {"D", "WB", "DF"}:
        return "defence"
    if code in {"DM", "M", "WM"}:
        return "midfield"
    if code in {"AM"}:
        return "midfield"
    if code in {"ST", "FW", "AF"}:
        return "attack"
    return "midfield"


def _match_known_formation(formation_text: str) -> Optional[str]:
    m = re.search(r"\d(?:-\d)+", formation_text)
    if not m:
        return None
    candidate = m.group()
    return candidate if candidate in roles.FORMATIONS else None


@dataclass
class SquadAnalysis:
    headline_facts: dict = field(default_factory=dict)
    shape_analysis: dict = field(default_factory=dict)
    role_coverage_summary: dict = field(default_factory=dict)
    tactical_impossibilities: list = field(default_factory=list)
    hidden_strengths: dict = field(default_factory=dict)
    wage_analysis: dict = field(default_factory=dict)
    decisive_players: dict = field(default_factory=dict)
    recruitment_priorities: list = field(default_factory=list)
    exit_candidates: list = field(default_factory=list)
    age_profile: dict = field(default_factory=dict)
    tactical_style_fit: Optional[dict] = None
    squad_audit: dict = field(default_factory=dict)
    target_dossier: Optional[list] = None
    window_budget: dict = field(default_factory=dict)


def _headline_facts(players: list[Player]) -> dict:
    def names(status: str) -> list[str]:
        return [p.name for p in players if status in p.status]

    available = [p for p in players if p.is_available]
    gks = [p for p in players if p.is_goalkeeper]
    gks_available = [p for p in gks if p.is_available]
    if len(gks_available) == 0:
        backup = "no fit goalkeeper available"
    elif len(gks_available) == 1:
        backup = "single senior keeper, no backup"
    else:
        backup = f"{len(gks_available)} available keepers, adequate cover"

    return {
        "total_players": len(players),
        "available_count": len(available),
        "injured": names("Injured"),
        "on_loan": names("On Loan"),
        "unavailable": names("Unavailable"),
        "suspended": names("Suspended"),
        "transfer_listed": names("Transfer Listed"),
        "unhappy": names("Unhappy"),
        "loanees_in": names("On Loan From"),
        "gk_total_count": len(gks),
        "gk_available_count": len(gks_available),
        "gk_backup_situation": backup,
    }


def _key_dependencies(players: list[Player], player_scores: dict) -> list[dict]:
    playmaking_roles = {"DLP_d", "DLP_s", "AP_s", "AP_a", "RPM_s", "CM_a"}
    dm_roles = ["DM_d", "BWM_s", "DLP_d"]
    physical = [p for p in players if p.attr("Strength") >= 13 and (p.height_cm or 0) >= 185]

    dependencies = []
    for p in players:
        if p.attr("Strength") >= 10:
            continue
        best_role, best_score = _best_role(player_scores[p.name])
        if best_role not in playmaking_roles:
            continue
        best_partner = None
        best_partner_score = -1.0
        for cand in physical:
            if cand.name == p.name:
                continue
            score = max(player_scores[cand.name].get(r, 0.0) for r in dm_roles)
            if score > best_partner_score:
                best_partner_score = score
                best_partner = cand
        if best_partner is not None:
            dependencies.append({
                "playmaker": p.name,
                "playmaker_role": best_role,
                "playmaker_score": best_score,
                "playmaker_strength": p.attr("Strength"),
                "enabler": best_partner.name,
                "enabler_score": round(best_partner_score, 1),
                "enabler_strength": best_partner.attr("Strength"),
                "enabler_height": best_partner.height_cm,
            })
    return dependencies


def _shape_analysis(players: list[Player], player_scores: dict, formation_override: Optional[str]) -> tuple[dict, list[dict]]:
    viability = roles.formation_viability(players)
    top = viability[0]
    top_formation = top["formation"]

    override_formation = None
    if formation_override:
        matched = _match_known_formation(formation_override)
        if matched:
            available = [p for p in players if p.is_available]
            override_xi = roles.best_xi_for_formation(available, matched)
            override_formation = {
                "requested_text": formation_override,
                "matched_shape": matched,
                **override_xi,
            }
        else:
            override_formation = {
                "requested_text": formation_override,
                "matched_shape": None,
            }

    shape = {
        "viability": viability,
        "top_formation": top_formation,
        "top_xi": top["xi"],
        "top_xi_total_score": top["total_score"],
        "top_xi_avg_score": top["avg_score"],
        "top_xi_structural_weaknesses": top["structural_weaknesses"],
        "key_dependencies": _key_dependencies(players, player_scores),
        "override_formation": override_formation,
    }
    return shape, viability


def _role_coverage_summary(players: list[Player], player_scores: dict, coverage: dict) -> dict:
    summary = {}
    for role in roles.ROLE_WEIGHTS:
        scored = sorted(
            ((p.name, player_scores[p.name].get(role, 0.0)) for p in players),
            key=lambda kv: kv[1],
            reverse=True,
        )
        summary[role] = {
            "capable_count": len(coverage[role]["capable"]),
            "strong_count": len(coverage[role]["strong"]),
            "elite_count": len(coverage[role]["elite"]),
            "top3": scored[:3],
        }
    return summary


def _top_score(summary: dict, role: str) -> float:
    top3 = summary[role]["top3"]
    return top3[0][1] if top3 else 0.0


def _tactical_impossibilities(players: list[Player], summary: dict) -> list[dict]:
    impossibilities = []

    wb_s, wb_a = summary["WB_s"]["strong_count"], summary["WB_a"]["strong_count"]
    if wb_s == 0 and wb_a == 0:
        impossibilities.append({
            "flag": "cannot play wing-backs",
            "evidence": (
                f"WB_s: 0 strong (top score {_top_score(summary, 'WB_s'):.1f}), "
                f"WB_a: 0 strong (top score {_top_score(summary, 'WB_a'):.1f})"
            ),
        })

    top5_finishing = sorted(players, key=lambda p: p.attr("Finishing"), reverse=True)[:5]
    avg_heading = _mean([p.attr("Heading") for p in top5_finishing])
    if summary["TM_s"]["strong_count"] == 0 and avg_heading < 10:
        impossibilities.append({
            "flag": "cannot go direct",
            "evidence": (
                f"TM_s: 0 strong (top score {_top_score(summary, 'TM_s'):.1f}); "
                f"top 5 finishers average heading {avg_heading:.1f}"
            ),
        })

    avg_tackling = _mean([p.attr("Tackling") for p in players])
    if summary["BWM_s"]["strong_count"] == 0 and avg_tackling < 11:
        impossibilities.append({
            "flag": "no ball-winning presence",
            "evidence": (
                f"BWM_s: 0 strong (top score {_top_score(summary, 'BWM_s'):.1f}); "
                f"squad average tackling {avg_tackling:.1f}"
            ),
        })

    ap_a, rpm_s, bbm_s = (
        summary["AP_a"]["strong_count"], summary["RPM_s"]["strong_count"], summary["BBM_s"]["strong_count"]
    )
    if ap_a == 0 and rpm_s == 0 and bbm_s == 0:
        impossibilities.append({
            "flag": "no midfield goal threat",
            "evidence": (
                f"AP_a top {_top_score(summary, 'AP_a'):.1f}, "
                f"RPM_s top {_top_score(summary, 'RPM_s'):.1f}, "
                f"BBM_s top {_top_score(summary, 'BBM_s'):.1f} — none strong (>=70)"
            ),
        })

    gk_count = sum(1 for p in players if p.is_goalkeeper)
    sk_strong = summary["SK_s"]["strong_count"]
    if gk_count < 2 or sk_strong == 0:
        impossibilities.append({
            "flag": "goalkeeper shortage",
            "evidence": f"{gk_count} recognised goalkeepers on the books, SK_s strong count {sk_strong}",
        })

    return impossibilities


def _hidden_strengths(players: list[Player], player_scores: dict, top_xi: dict) -> dict:
    def aerial(p: Player) -> float:
        return (p.attr("Heading") + p.attr("Jumping Reach")) / 2

    def delivery(p: Player) -> float:
        return (p.attr("Passing") + p.attr("Technique") + p.attr("Corners")) / 3

    top6_aerial = sorted(players, key=aerial, reverse=True)[:6]
    avg_height_top6 = _mean([p.height_cm or 0 for p in top6_aerial])
    top3_delivery = sorted(players, key=delivery, reverse=True)[:3]
    top_deliverer = top3_delivery[0] if top3_delivery else None

    set_piece_asset = bool(
        top_deliverer is not None
        and avg_height_top6 >= 189
        and (top_deliverer.attr("Passing") >= 14 or top_deliverer.attr("Corners") >= 14)
    )
    set_piece_asset_evidence = (
        f"top 6 aerial presence avg height {avg_height_top6:.0f}cm; "
        f"best deliverer {top_deliverer.name if top_deliverer else 'n/a'} "
        f"(pas {top_deliverer.attr('Passing') if top_deliverer else 0}, "
        f"cor {top_deliverer.attr('Corners') if top_deliverer else 0})"
    )

    players_by_name = {p.name: p for p in players}
    xi_heights = [
        players_by_name[name].height_cm or 0
        for name, _role, _score in top_xi.values()
        if name in players_by_name
    ]
    short_count = sum(1 for h in xi_heights if h < 175)
    set_piece_risk = short_count >= 3
    set_piece_risk_evidence = f"{short_count} best-XI players under 175cm"

    wide_slot_players = {
        slot: players_by_name[name]
        for slot, (name, _role, _score) in top_xi.items()
        if slot in WIDE_SLOTS and name in players_by_name
    }
    wide_pace = len(wide_slot_players) >= 2 and all(p.attr("Pace") >= 15 for p in wide_slot_players.values())
    wide_pace_evidence = ", ".join(
        f"{slot}: {p.name} (pace {p.attr('Pace')})" for slot, p in wide_slot_players.items()
    ) or "no wide slots in top XI"

    youth = [
        p for p in players
        if p.age <= 21 and _best_role(player_scores[p.name])[1] >= 65
    ]

    return {
        "set_piece_asset": {"flag": set_piece_asset, "evidence": set_piece_asset_evidence},
        "set_piece_defensive_risk": {"flag": set_piece_risk, "evidence": set_piece_risk_evidence},
        "wide_pace": {"flag": wide_pace, "evidence": wide_pace_evidence},
        "youth_pipeline": {
            "count": len(youth),
            "players": [(p.name, p.age, round(_best_role(player_scores[p.name])[1], 1)) for p in youth],
        },
    }


def _wage_analysis(players: list[Player], player_scores: dict) -> dict:
    waged = [p for p in players if p.wage]
    total_weekly = sum(p.wage for p in waged)

    top5_earners = sorted(waged, key=lambda p: p.wage, reverse=True)[:5]
    top5_earners_out = []
    for p in top5_earners:
        best_role, best_score = _best_role(player_scores[p.name])
        top5_earners_out.append({
            "player": p.name, "wage": p.wage, "best_role": best_role, "best_role_score": best_score,
        })

    outliers = []
    for p in waged:
        best_role, best_score = _best_role(player_scores[p.name])
        ratio = p.wage / max(best_score, 1)
        outliers.append((p, best_role, best_score, ratio))
    outliers.sort(key=lambda t: t[3], reverse=True)
    top5_outliers = outliers[:5]

    wage_outliers_out = []
    outlier_names = set()
    for p, best_role, best_score, ratio in top5_outliers:
        outlier_names.add(p.name)
        key_attrs = roles.ROLE_WEIGHTS[best_role]["KEY"] if best_role else []
        weakest = sorted(((a, p.attr(a)) for a in key_attrs), key=lambda kv: kv[1])[:3]
        wage_outliers_out.append({
            "player": p.name, "wage": p.wage, "best_role": best_role, "best_role_score": best_score,
            "ratio": round(ratio, 1), "weaknesses": weakest,
        })

    median_wage = statistics.median([p.wage for p in waged]) if waged else 0
    best_value = []
    for p in players:
        if p.age <= 23 and p.wage and p.wage < median_wage:
            best_role, best_score = _best_role(player_scores[p.name])
            if best_score >= 65:
                best_value.append({
                    "player": p.name, "age": p.age, "wage": p.wage,
                    "best_role": best_role, "best_role_score": best_score,
                    "value_ratio": round(best_score / max(p.wage, 1), 4),
                })
    best_value.sort(key=lambda d: d["value_ratio"], reverse=True)

    groups = {"goalkeeper": 0, "defence": 0, "midfield": 0, "attack": 0}
    for p in players:
        if p.wage:
            groups[_position_group(p.position)] += p.wage
    # fold goalkeeper wages into defence for the 3-bucket cost view
    position_cost = {
        "defence": groups["goalkeeper"] + groups["defence"],
        "midfield": groups["midfield"],
        "attack": groups["attack"],
    }
    flagged = [g for g, total in position_cost.items() if total_weekly and total / total_weekly > 0.45]

    return {
        "total_weekly": total_weekly,
        "total_yearly": total_weekly * 52,
        "top5_earners": top5_earners_out,
        "wage_outliers": wage_outliers_out,
        "wage_outlier_names": outlier_names,
        "best_value_contracts": best_value[:5],
        "position_cost": position_cost,
        "position_cost_flagged": flagged,
    }


def _decisive_players(players: list[Player], player_scores: dict, coverage: dict, top_xi: dict) -> dict:
    ceiling_player, ceiling_role, ceiling_score = None, None, -1.0
    for p in players:
        role, score = _best_role(player_scores[p.name])
        if score > ceiling_score:
            ceiling_player, ceiling_role, ceiling_score = p, role, score
    ceiling = {
        "player": ceiling_player.name if ceiling_player else None,
        "age": ceiling_player.age if ceiling_player else None,
        "role": ceiling_role, "score": ceiling_score,
        "is_young": bool(ceiling_player and ceiling_player.age <= 23),
    }

    structure_player, structure_count = None, -1
    for p in players:
        count = sum(1 for s in player_scores[p.name].values() if s >= 65)
        if count > structure_count:
            structure_player, structure_count = p, count
    structure = {
        "player": structure_player.name if structure_player else None,
        "roles_at_65plus": structure_count,
    }

    seniors = [p for p in players if p.age >= 24 and p.wage]
    floor_player, floor_ratio, floor_role, floor_score = None, -1.0, None, 0.0
    for p in seniors:
        role, score = _best_role(player_scores[p.name])
        ratio = score / max(p.wage, 1)
        if ratio > floor_ratio:
            floor_player, floor_ratio, floor_role, floor_score = p, ratio, role, score
    floor = {
        "player": floor_player.name if floor_player else None,
        "age": floor_player.age if floor_player else None,
        "role": floor_role, "score": floor_score,
        "wage": floor_player.wage if floor_player else None,
    }

    load_bearing = []
    for slot, (name, role, score) in top_xi.items():
        strong_list = coverage[role]["strong"]
        if len(strong_list) == 1 and strong_list[0] == name:
            alternatives = sorted(
                ((n, s.get(role, 0.0)) for n, s in player_scores.items() if n != name),
                key=lambda kv: kv[1], reverse=True,
            )
            next_best_name, next_best_score = alternatives[0] if alternatives else (None, 0.0)
            load_bearing.append({
                "player": name, "role": role, "slot": slot, "score": score,
                "next_best": next_best_name, "next_best_score": next_best_score,
            })

    return {"ceiling": ceiling, "structure": structure, "floor": floor, "load_bearing": load_bearing}


IMPOSSIBILITY_ROLE_MAP = {
    "cannot play wing-backs": ("WB_s", "defence"),
    "cannot go direct": ("TM_s", "attack"),
    "no ball-winning presence": ("BWM_s", "midfield"),
    "no midfield goal threat": ("AP_a", "midfield"),
    "goalkeeper shortage": ("SK_s", "goalkeeper"),
}


def _profile_for_role(role: str, age_range: str) -> dict:
    key_attrs = roles.ROLE_WEIGHTS[role]["KEY"]
    pref_attrs = roles.ROLE_WEIGHTS[role]["PREF"]
    floors = {a: 14 for a in key_attrs}
    floors.update({a: 12 for a in pref_attrs})
    return {"attribute_floors": floors, "age_range": age_range}


def _widen_age_range(age_range: str, by: int = 3) -> str:
    m = re.match(r"(\d+)\s*-\s*(\d+)", age_range)
    if not m:
        return age_range
    lo, hi = int(m.group(1)), int(m.group(2))
    return f"{max(16, lo - by)}-{min(40, hi + by)}"


def _fallback_profile_for_role(role: str, age_range: str) -> dict:
    # Deliberately looser than _profile_for_role: lower floors, wider age
    # range — the "if the primary target isn't gettable" plan B.
    key_attrs = roles.ROLE_WEIGHTS[role]["KEY"]
    pref_attrs = roles.ROLE_WEIGHTS[role]["PREF"]
    floors = {a: 12 for a in key_attrs}
    floors.update({a: 10 for a in pref_attrs})
    return {"attribute_floors": floors, "age_range": _widen_age_range(age_range)}


def _recruitment_priorities(
    players: list[Player], headline: dict, shape: dict, tactical: list[dict],
) -> list[dict]:
    priorities: list[dict] = []
    seen_roles: set[str] = set()

    for slot in shape["top_xi_structural_weaknesses"]:
        name, role, score = shape["top_xi"][slot]
        if role in seen_roles:
            continue
        seen_roles.add(role)
        priorities.append({
            "role": role, "slot": slot,
            "rationale": f"best available at {slot} is {name} scoring {score:.1f} at {role} — below the 60 capable threshold",
            "profile": _profile_for_role(role, "20-26"),
            "fallback_profile": _fallback_profile_for_role(role, "20-26"),
            "cost_ceiling": None,
        })

    counts: dict[str, int] = {"goalkeeper": 0, "defence": 0, "midfield": 0, "attack": 0}
    for p in players:
        if p.is_available:
            counts[_position_group(p.position)] += 1
    group_to_role = {"defence": "FB_s", "midfield": "BBM_s", "attack": "AF_a"}
    for group, count in counts.items():
        if group == "goalkeeper" or count != 1:
            continue
        role = group_to_role[group]
        if role in seen_roles:
            continue
        seen_roles.add(role)
        priorities.append({
            "role": role, "slot": group,
            "rationale": f"only one available body in {group} — single point of failure",
            "profile": _profile_for_role(role, "22-28"),
            "fallback_profile": _fallback_profile_for_role(role, "22-28"),
            "cost_ceiling": None,
        })

    for impossibility in tactical:
        mapping = IMPOSSIBILITY_ROLE_MAP.get(impossibility["flag"])
        if not mapping:
            continue
        role, _group = mapping
        if role in seen_roles:
            continue
        seen_roles.add(role)
        priorities.append({
            "role": role, "slot": impossibility["flag"],
            "rationale": f"resolves '{impossibility['flag']}' — {impossibility['evidence']}",
            "profile": _profile_for_role(role, "21-27"),
            "fallback_profile": _fallback_profile_for_role(role, "21-27"),
            "cost_ceiling": None,
        })

    if headline["gk_available_count"] < 2:
        role = "GK_d"
        if role not in seen_roles:
            seen_roles.add(role)
            priorities.append({
                "role": role, "slot": "GK",
                "rationale": f"{headline['gk_backup_situation']} — {headline['gk_available_count']} available keeper(s)",
                "profile": _profile_for_role(role, "26-33"),
                "fallback_profile": _fallback_profile_for_role(role, "26-33"),
                "cost_ceiling": None,
            })

    return priorities[:4]


def _exit_candidates(
    players: list[Player], player_scores: dict, coverage: dict,
    wage_outlier_names: set[str], today: date,
) -> list[dict]:
    candidates = []
    for p in players:
        best_role, best_score = _best_role(player_scores[p.name])
        depth = len(coverage[best_role]["capable"]) if best_role else 1
        age_penalty = 1.0 if p.age < 29 else 1.5 if p.age <= 30 else 2.0 if p.age <= 32 else 3.0
        wage = p.wage or 0
        sell_score = (age_penalty * wage) / max(best_score * max(depth, 1), 1)

        reasons = []
        if "Transfer Listed" in p.status:
            reasons.append("transfer listed")
        if "Unhappy" in p.status:
            reasons.append("mood management")
        if p.name in wage_outlier_names:
            reasons.append("wage vs contribution")
        if "Loan Listed" in p.status:
            reasons.append("loan-listed, no path back")
        if p.contract_end:
            m = re.search(r"(20\d{2})", p.contract_end)
            if m and int(m.group(1)) <= today.year + 1:
                reasons.append("contract cliff")

        candidates.append({
            "player": p.name, "age": p.age, "wage": wage,
            "best_role": best_role, "best_role_score": best_score,
            "sell_score": sell_score, "reasons": reasons,
            "auto_include": "Transfer Listed" in p.status,
            "value_low": p.value_low, "value_high": p.value_high,
            "has_replacement_case": False,
        })

    by_name = {c["player"]: c for c in candidates}
    for role, lists in coverage.items():
        strong = lists["strong"]
        if len(strong) >= 2:
            scored = sorted(((n, player_scores[n].get(role, 0.0)) for n in strong), key=lambda kv: kv[1])
            weakest_name = scored[0][0]
            c = by_name.get(weakest_name)
            if c and "duplicated profile" not in c["reasons"]:
                c["reasons"].append("duplicated profile")

    with_reasons = [c for c in candidates if c["reasons"]]
    with_reasons.sort(key=lambda c: (c["auto_include"], c["sell_score"]), reverse=True)
    selected = with_reasons[:6]

    if len(selected) < 4:
        remaining = [c for c in candidates if c not in selected]
        remaining.sort(key=lambda c: c["sell_score"], reverse=True)
        for c in remaining:
            if len(selected) >= 4:
                break
            if not c["reasons"]:
                c["reasons"] = ["aging + declining fit"]
            selected.append(c)

    return selected[:6]


def _build_value_curve(players: list["Player"]) -> dict[int, list[float]]:
    by_age: dict[int, list[float]] = {}
    for p in players:
        if p.value_low is not None and p.value_high is not None and p.age:
            by_age.setdefault(p.age, []).append((p.value_low + p.value_high) / 2)
    return by_age


def _windowed_median(by_age: dict[int, list[float]], age: int, window: int = 1, min_n: int = 5) -> Optional[float]:
    pooled: list[float] = []
    for a in range(age - window, age + window + 1):
        pooled.extend(by_age.get(a, []))
    if len(pooled) < min_n:
        return None
    return statistics.median(pooled)


def _project_exit_value(value_mid: float, age: int, by_age: dict[int, list[float]], years: int) -> Optional[float]:
    now = _windowed_median(by_age, age)
    future = _windowed_median(by_age, age + years)
    if now is None or future is None or now <= 0:
        return None
    return value_mid * (future / now)


def _attach_depreciation(exits: list[dict], by_age: dict[int, list[float]]) -> None:
    for c in exits:
        if c["value_low"] is None or c["value_high"] is None:
            c["value_now"] = None
            c["projected_value_1yr"] = None
            c["projected_value_2yr"] = None
            c["value_trend"] = None
            continue

        value_mid = (c["value_low"] + c["value_high"]) / 2
        proj_1yr = _project_exit_value(value_mid, c["age"], by_age, 1)
        proj_2yr = _project_exit_value(value_mid, c["age"], by_age, 2)

        c["value_now"] = value_mid
        c["projected_value_1yr"] = proj_1yr
        c["projected_value_2yr"] = proj_2yr

        reference = proj_1yr if proj_1yr is not None else proj_2yr
        if reference is None or value_mid <= 0:
            c["value_trend"] = None
        else:
            ratio = reference / value_mid
            c["value_trend"] = "rising" if ratio >= 1.05 else "declining" if ratio <= 0.95 else "stable"


def _age_profile(players: list[Player], player_scores: dict, top_xi: dict) -> dict:
    def bucket(age: int) -> str:
        if age < 21:
            return "U21"
        if age <= 24:
            return "21-24"
        if age <= 28:
            return "25-28"
        if age <= 32:
            return "29-32"
        return "33+"

    buckets: dict[str, list[Player]] = {"U21": [], "21-24": [], "25-28": [], "29-32": [], "33+": []}
    for p in players:
        buckets[bucket(p.age)].append(p)

    quality = {
        b: round(_mean([_best_role(player_scores[p.name])[1] for p in ps]), 1) if ps else 0.0
        for b, ps in buckets.items()
    }

    players_by_name = {p.name: p for p in players}
    group_ages: dict[str, list[int]] = {"goalkeeper": [], "defence": [], "midfield": [], "attack": []}
    for slot, (name, role, _score) in top_xi.items():
        player = players_by_name.get(name)
        if player:
            group_ages[ROLE_GROUP.get(role, "midfield")].append(player.age)
    aging_positions = [g for g, ages in group_ages.items() if sum(1 for a in ages if a >= 30) >= 2]

    youth_pipeline_positions = set()
    for p in players:
        if p.age <= 21:
            role, score = _best_role(player_scores[p.name])
            if score >= 65 and role:
                youth_pipeline_positions.add(ROLE_GROUP.get(role, "midfield"))

    return {
        "bucket_counts": {b: len(ps) for b, ps in buckets.items()},
        "bucket_quality": quality,
        "aging_positions": aging_positions,
        "youth_pipeline_positions": sorted(youth_pipeline_positions),
    }


def _attach_cost_ceilings(recruitment: list[dict], target_dossier: list[dict]) -> None:
    # target_dossier is built directly from `recruitment`, one entry per
    # priority in the same order — safe to zip rather than re-match by role.
    for priority, dossier_entry in zip(recruitment, target_dossier):
        candidates = dossier_entry["candidates"]
        values_low = [c["value_low"] for c in candidates if c["value_low"] is not None]
        values_high = [c["value_high"] for c in candidates if c["value_high"] is not None]
        if values_low and values_high:
            priority["cost_ceiling"] = {"low": min(values_low), "high": max(values_high)}


def _exit_replacement_priorities(
    exit_candidates: list[dict], audit: dict, decisive: dict,
) -> list[dict]:
    # Only build a market case for exits that actually leave a hole: Core/
    # Rotation tier (per the Squad Audit's own playing-time judgement) or a
    # load-bearing starter. A "duplicated profile" sale is excluded outright —
    # that reason exists specifically because an in-squad replacement already
    # covers the role, so a market case would be manufactured work, not a
    # real gap.
    tier_by_name = {e["player"]: e["tier"] for e in audit.get("entries", [])}
    load_bearing_names = {d["player"] for d in decisive.get("load_bearing", [])}

    priorities = []
    for c in exit_candidates:
        if not c.get("best_role"):
            continue
        if "duplicated profile" in c["reasons"]:
            continue
        tier = tier_by_name.get(c["player"])
        is_load_bearing = c["player"] in load_bearing_names
        if tier not in ("Core", "Rotation") and not is_load_bearing:
            continue

        age_lo, age_hi = max(16, c["age"] - 4), min(40, c["age"] + 4)
        priorities.append({
            "role": c["best_role"],
            "slot": c["player"],
            "rationale": (
                f"replacement case for {c['player']}'s exit — "
                f"{(tier or 'load-bearing').lower()} player scoring {c['best_role_score']:.1f} at {c['best_role']}"
            ),
            "profile": {"attribute_floors": {}, "age_range": f"{age_lo}-{age_hi}"},
        })
    return priorities


def _window_budget(
    recruitment: list[dict], exit_candidates: list[dict],
    transfer_budget: Optional[int], wage_budget: Optional[int],
) -> dict:
    exits_with_value = [c for c in exit_candidates if c.get("value_low") is not None]
    exit_proceeds_low = sum(c["value_low"] for c in exits_with_value) if exits_with_value else None
    exit_proceeds_high = sum(c["value_high"] for c in exits_with_value) if exits_with_value else None

    costed = [r for r in recruitment if r.get("cost_ceiling")]
    priority_cost_low = sum(r["cost_ceiling"]["low"] for r in costed) if costed else None
    priority_cost_high = sum(r["cost_ceiling"]["high"] for r in costed) if costed else None

    available_transfer_budget = None
    if transfer_budget is not None:
        available_transfer_budget = transfer_budget + (exit_proceeds_low or 0)

    # Reconciliation is deliberately conservative: available budget (transfer
    # budget + the low end of exit proceeds) against the high end of costed
    # priorities — a worst-case check, not an optimistic one.
    reconciliation = None
    if available_transfer_budget is not None and priority_cost_high is not None:
        reconciliation = available_transfer_budget - priority_cost_high

    return {
        "transfer_budget": transfer_budget,
        "wage_budget": wage_budget,
        "exit_proceeds_low": exit_proceeds_low,
        "exit_proceeds_high": exit_proceeds_high,
        "available_transfer_budget": available_transfer_budget,
        "priority_cost_low": priority_cost_low,
        "priority_cost_high": priority_cost_high,
        "priorities_costed": len(costed),
        "priorities_total": len(recruitment),
        "reconciliation": reconciliation,
    }


def analyze(
    players: list[Player],
    objective: Optional[str] = None,
    formation_override: Optional[str] = None,
    today: Optional[date] = None,
    tactical_style: Optional[str] = None,
    league_players: Optional[list[Player]] = None,
    market_players: Optional[list[Player]] = None,
    transfer_budget: Optional[int] = None,
    wage_budget: Optional[int] = None,
) -> SquadAnalysis:
    today = today or date.today()
    player_scores = {p.name: roles.compute_role_scores(p) for p in players}
    coverage = roles.role_coverage(players)

    shape, viability = _shape_analysis(players, player_scores, formation_override)
    top_xi = shape["top_xi"]

    print(f"[roles] Computed role scores for {len(players)} players x {len(roles.ROLE_WEIGHTS)} roles")
    print("[roles] Formation viability (best XI total score):")
    for result in viability:
        weak = ", ".join(result["structural_weaknesses"]) if result["structural_weaknesses"] else "none"
        print(
            f"[roles]   {result['formation']}: {result['total_score']:.0f} "
            f"(avg {result['avg_score']:.1f}) — weak slots: {weak}"
        )

    summary = _role_coverage_summary(players, player_scores, coverage)
    tactical = _tactical_impossibilities(players, summary)
    hidden = _hidden_strengths(players, player_scores, top_xi)
    wage = _wage_analysis(players, player_scores)
    decisive = _decisive_players(players, player_scores, coverage, top_xi)
    headline = _headline_facts(players)
    recruitment = _recruitment_priorities(players, headline, shape, tactical)
    exits = _exit_candidates(players, player_scores, coverage, wage["wage_outlier_names"], today)
    # Market pool gives a far denser age-value curve than the squad alone can
    # (35,973 players vs ~30) — prefer it when available, but the squad-only
    # fallback still works, just usually too sparse to produce a projection.
    value_curve = _build_value_curve(market_players if market_players else players)
    _attach_depreciation(exits, value_curve)
    age_profile = _age_profile(players, player_scores, top_xi)

    available_n = headline["available_count"]
    print(
        f"[analyzer] Available bodies: {available_n}/{len(players)} "
        f"(Injured: {len(headline['injured'])}, On loan: {len(headline['on_loan'])}, "
        f"Unavailable: {len(headline['unavailable'])}, Transfer listed: {len(headline['transfer_listed'])})"
    )
    print(f"[analyzer] Top formation: {shape['top_formation']} (avg {shape['top_xi_avg_score']:.1f})")
    weak = shape["top_xi_structural_weaknesses"]
    if weak:
        weak_desc = ", ".join(f"{s} (best {top_xi[s][2]:.1f})" for s in weak if s in top_xi)
        print(f"[analyzer] Weak slots in top XI: {weak_desc}")
    else:
        print("[analyzer] Weak slots in top XI: none")
    zero_strong = [r for r in roles.ROLE_WEIGHTS if summary[r]["strong_count"] == 0]
    print(f"[analyzer] Zero-strong roles: {', '.join(zero_strong) if zero_strong else 'none'}")
    print(
        "[analyzer] Tactical impossibilities: "
        + (", ".join(t["flag"] for t in tactical) if tactical else "none")
    )
    hidden_flags = [k.replace("_", " ") for k, v in hidden.items() if isinstance(v, dict) and v.get("flag")]
    print(f"[analyzer] Hidden strengths: {', '.join(hidden_flags) if hidden_flags else 'none material'}")
    lb_desc = ", ".join(f"{d['player']} at {d['role']}" for d in decisive["load_bearing"])
    print(f"[analyzer] Load-bearing players: {len(decisive['load_bearing'])}" + (f" ({lb_desc})" if lb_desc else ""))
    print(f"[analyzer] Recruitment priorities: {len(recruitment)}")
    print(f"[analyzer] Exit candidates: {len(exits)}")

    style_fit = None
    if tactical_style:
        style_fit = tactics.compute_squad_style_fit(players, tactical_style)
        counts = style_fit["tier_counts"]
        counts_desc = ", ".join(f"{n} {label.lower()}" for label, n in counts.items())
        print(f"[analyzer] Tactical style fit ({style_fit['style_label']}): {counts_desc}")

        if league_players:
            league_ctx = league_context.contextualize_style_fit(style_fit, league_players, tactical_style)
            style_fit["league_context"] = league_ctx
            print(
                f"[league] Style-fit benchmark ({style_fit['style_label']}): "
                f"{league_ctx['league_player_count']} players, {league_ctx['league_club_count']} clubs, "
                f"weighted by starts+subs"
            )
            if league_ctx["sparse_apps_warning"]:
                print(
                    "[league] WARNING: apps signal is sparse "
                    f"({league_ctx['apps_signal_ratio'] * 100:.0f}% of league players have any appearances) "
                    "— benchmark is behaving like an unweighted average, not just regular starters"
                )
    else:
        print("[analyzer] Tactical style: not specified")

    audit = squad_audit_module.compute_squad_audit(players)
    if audit["has_data"]:
        counts_desc = ", ".join(
            f"{n} {tier.lower()}" for tier, n in audit["tier_counts"].items() if n
        )
        print(f"[analyzer] Squad audit: {counts_desc}")
        if audit["unmapped_labels"]:
            print(f"[analyzer] WARNING: unrecognised playing-time labels (mapped to Filler): {', '.join(audit['unmapped_labels'])}")
    else:
        print("[analyzer] Squad audit: not available — add Actual Playing Time, Agreed Playing Time, Mins, and Last Trans. Fee columns to your squad view for the full audit")

    target_dossier = None
    if market_players:
        target_dossier = market_matching.build_target_dossier(
            recruitment, market_players, style_key=tactical_style, today=today,
        )
        for entry in target_dossier:
            names = ", ".join(c["player"] for c in entry["candidates"]) or "no candidates in range"
            print(f"[market] {entry['role']} ({entry['slot']}): {names}")
        _attach_cost_ceilings(recruitment, target_dossier)

        exit_priorities = _exit_replacement_priorities(exits, audit, decisive)
        if exit_priorities:
            exit_dossier = market_matching.build_target_dossier(
                exit_priorities, market_players, style_key=tactical_style, today=today,
                kind="exit_replacement",
            )
            target_dossier.extend(exit_dossier)
            replacement_names = {entry["slot"] for entry in exit_dossier}
            for c in exits:
                c["has_replacement_case"] = c["player"] in replacement_names
            print(f"[market] Replacement cases built for {len(exit_dossier)} exit(s): {', '.join(replacement_names)}")

    window_budget = _window_budget(recruitment, exits, transfer_budget, wage_budget)
    if transfer_budget is not None or wage_budget is not None:
        print(
            f"[window] Transfer budget: {transfer_budget if transfer_budget is not None else 'not specified'}, "
            f"wage budget: {wage_budget if wage_budget is not None else 'not specified'}/w, "
            f"priorities costed: {window_budget['priorities_costed']}/{window_budget['priorities_total']}"
        )

    return SquadAnalysis(
        headline_facts=headline,
        shape_analysis=shape,
        role_coverage_summary=summary,
        tactical_impossibilities=tactical,
        hidden_strengths=hidden,
        wage_analysis=wage,
        decisive_players=decisive,
        recruitment_priorities=recruitment,
        exit_candidates=exits,
        age_profile=age_profile,
        tactical_style_fit=style_fit,
        squad_audit=audit,
        target_dossier=target_dossier,
        window_budget=window_budget,
    )
