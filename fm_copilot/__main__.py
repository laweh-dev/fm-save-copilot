"""CLI entry point: python -m fm_copilot <squad.html> [options]"""

from __future__ import annotations

import argparse
import sys

from fm_copilot import analyzer, config as config_module, parser as parser_module, report, tactics


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m fm_copilot",
        description="Turn an FM24 squad HTML export into a Director of Football briefing.",
    )
    parser.add_argument("squad_html", help="Path to the FM24 squad HTML export")
    parser.add_argument("--objective", default=None, help="One-line club objective")
    parser.add_argument("--formation", default=None, help="Formation override, e.g. '4-2-3-1 mid-block'")
    parser.add_argument(
        "--tactic", default=None,
        help="Tactical direction, e.g. 'Gegenpress'. Valid: " + ", ".join(tactics.STYLE_LABELS.values()),
    )
    parser.add_argument(
        "--league", default=None,
        help="Path to a current-league HTML export. Recalibrates style-fit against the standard of "
             "opposition in this league. Requires --tactic.",
    )
    parser.add_argument(
        "--market", default=None,
        help="Path to a scouting/transfer-market HTML export (same format as --league). Adds a "
             "Target Dossier section naming real candidates against each recruitment priority.",
    )
    parser.add_argument(
        "--transfer-budget", default=None,
        help="Transfer budget available this window, e.g. '£15M'. Optional — without it, "
             "recruitment priorities show profiles without a spend ceiling.",
    )
    parser.add_argument(
        "--wage-budget", default=None,
        help="Weekly wage budget headroom available, e.g. '£45,000'. Optional, independent of "
             "--transfer-budget.",
    )
    parser.add_argument(
        "--out", default="report.html",
        help="Output file (default: report.html — a styled report with charts). "
             "Pass a .md path for the plain-markdown output instead.",
    )
    parser.add_argument("--config", default="config.yaml", help="Config file (default: config.yaml)")
    args = parser.parse_args()

    tactical_style = None
    if args.tactic:
        try:
            tactical_style = tactics.resolve_style_key(args.tactic)
        except ValueError as exc:
            print(f"[tactics] ERROR: {exc}")
            return 1

    if args.league and not tactical_style:
        print(
            "[league] ERROR: --league requires --tactic — it recalibrates style-fit for a specific "
            "tactical direction, which needs to be set first."
        )
        return 1

    cfg = config_module.load_config(args.config)
    if cfg.free_mode:
        print("[config] No API key found — running in free mode (deterministic markdown, no DoF narrative)")
    else:
        print(f"[config] API key loaded — model {cfg.model}")

    try:
        players = parser_module.parse_squad(args.squad_html)
    except Exception as exc:
        print(f"[parser] ERROR: {exc}")
        return 1

    league_players = None
    if args.league:
        try:
            league_players = parser_module.parse_league(args.league)
        except Exception as exc:
            print(f"[league] ERROR: {exc}")
            return 1

    market_players = None
    if args.market:
        try:
            market_players = parser_module.parse_league(args.market)
        except Exception as exc:
            print(f"[market] ERROR: {exc}")
            return 1

    transfer_budget = parser_module.parse_wage(args.transfer_budget)
    wage_budget = parser_module.parse_wage(args.wage_budget)

    try:
        analysis = analyzer.analyze(
            players, args.objective, args.formation,
            tactical_style=tactical_style, league_players=league_players,
            market_players=market_players,
            transfer_budget=transfer_budget, wage_budget=wage_budget,
        )
    except Exception as exc:
        print(f"[analyzer] ERROR: {exc}")
        return 1

    try:
        report.generate(analysis, players, args.objective, args.formation, cfg, args.out)
    except Exception as exc:
        print(f"[report] ERROR: {exc}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
