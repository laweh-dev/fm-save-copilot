# Changelog

Every entry here is also a git tag, so you can check out the exact code for any version with `git checkout <tag>`. See `V0-SUMMARY.md` for the detailed status writeup that accompanied v0.

## [Unreleased]

## [v0.2] - 2026-07-29

Adds a `--league PATH` flag (requires `--tactic`) that imports a current-league HTML export and converts each squad player's style-fit score into a weighted percentile rank against every league player at the same position, benchmarked with the same tier language ("Does very well" etc.). Statistics only — no opposition or league player is ever named in the report, keeping the "recruitment is profile-based, never named targets" rule intact. Benchmark weights every league player by appearances (starts count more than sub apps), so it self-corrects for pre-season automatically without a special case.

New `league_context.py` module (pure benchmarking math). `parser.py` refactored to share its column-parsing engine between `parse_squad()` and the new `parse_league()`, and fixed to handle scouted attribute ranges ("11-15") that appear for less-known opposition players. Extended status-code recognition with 9 new Info-column codes shared across both export types.

Verified against the real 1206-player, 19-club league export and the user's real squad, in free and API mode — confirmed Claude's prose uses league percentiles correctly (e.g. a keeper's absolute "Does well" score reading as 98th-percentile elite once benchmarked) without ever naming an opposition player.

## [v0.1] - 2026-07-29

Adds a `--tactic` flag: the manager can set one of 6 preset tactical directions (Control Possession & High Press, Gegenpress, Low Block & Fast Counters, Low Block & Waste Time, Low Block & Direct Long Passing, Tiki-Taka). Every player gets a style-fit score (0-100, banded into 4 tiers) alongside their existing role-fit score, computed per position group — the same style asks different things of a centre-back than a striker (e.g. under Low Block & Fast Counters, defenders are scored on positional discipline, attackers on pace). New `tactics.py` module. Woven into the existing Section 2 (Shape) and Section 7 (Recruitment) of the report rather than added as a new section. Omitting `--tactic` is a complete no-op — output is unchanged from v0.

Verified against a synthetic squad and the user's real save, in both free mode and API mode.

## [v0] - 2026-07-29

Initial release. Parses one FM24 squad HTML export, scores every player against 28 roles across 6 formations, and produces a Director of Football markdown briefing (Michael Edwards voice, via Claude) or a deterministic free-mode fallback with no API key. Full detail in `V0-SUMMARY.md`.
