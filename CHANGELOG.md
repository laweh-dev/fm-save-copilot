# Changelog

Every entry here is also a git tag, so you can check out the exact code for any version with `git checkout <tag>`. See `V0-SUMMARY.md` for the detailed status writeup that accompanied v0.

## [Unreleased]

## [v0.9] - 2026-07-30

Target Dossier becomes genuinely budget-aware — previously budget had zero effect on which candidates were shortlisted (£10M and £300M produced identical results, since matching ranked purely by role-fit and only used the budget afterward for a summary figure). Candidates are now split into affordable (within a per-priority share of the budget) and stretch (clearly over it); affordable options rank first, and a stretch candidate only breaks through when they're a genuine step up, explicitly labeled "stretch target" everywhere shown rather than silently swapped in.

New market-opportunity signings: alongside the gap-driven recruitment priorities, the report now checks whether the market has a genuine upgrade (a real step up, not marginal) over an already-capable starting-XI incumbent, affordable within the full transfer budget — surfaced as a single, focused pick, not a coverage gap. Requires a transfer budget to be set, since affordability is the entire premise. Reuses the exact same Target Dossier engine and safety containment as the existing recruitment/exit-replacement kinds — Section 12 remains the only place a market player is ever named.

Verified against real squad and market data: £10M vs. £300M now produce materially different shortlists, a deliberately tiny budget correctly flags an otherwise-unaffordable elite option as a stretch target rather than hiding or silently prioritizing it, and the opportunity-signing pipeline was confirmed to run correctly end-to-end (the real test squad's biggest available gap was 5.6 points — correctly below the 10-point bar, so no opportunity was surfaced, the honest result rather than a bug). No budget set behaves exactly as before.

## [v0.8.2] - 2026-07-30

Ins-and-outs visuals for Section 8 (Exits), requested as a way to see who's coming in against who's going out without merging Recruitment and Exits into one section — that would have rippled section-number references through `edwards.md`, the task-instruction template, and the HTML accent-border map for little real benefit.

Two new charts injected at the top of Section 8 when a market export is provided: a leaderboard pairing panel ("Ivo Grbić → Daiya Maekawa", value pill showing the incoming candidate's value range) and a paired bar chart comparing outgoing vs. incoming role-fit scores directly, color-coded red/green. Both are built entirely from data already computed — the exit-to-replacement pairing Target Dossier already establishes — reusing the existing leaderboard/bar-chart components with no new chart infrastructure and no changes to `report.py`, `analyzer.py`, or `edwards.md`. Gracefully absent without `--market`, same as everything else Target-Dossier-dependent.

## [v0.8.1] - 2026-07-30

Two real bugs reported by early users of Target Dossier/Window Plan.

**Best XI was placing players out of position** — a defensive midfielder at right-back, an attacking midfielder in a centre-mid slot that didn't suit them. Root cause: `roles.best_xi_for_formation()` scored every player against every slot's role weights purely by attributes, with no check against the player's actual listed FM position — a DM with good tackling/positioning can easily out-score a real fullback on paper despite never having played there. Fixed with a new position-eligibility map (`roles.SLOT_ELIGIBILITY`) that parses FM's own position notation and always prefers a positionally-eligible player; a player only fills a slot outside their listed position as a last resort (so the pitch diagram is never left with a blank slot), and that placement is now always flagged as a structural weakness — no natural option for a slot is a real coverage gap, not a stat-optimisation call. Verified against real squad data across all 6 formations: zero out-of-position placements. A useful side effect: recruitment priorities are sharper now too, since a slot previously masked by a good-but-wrong-position score correctly surfaces as a real need.

**Budget input parsing was inconsistent** — `parse_wage`'s K/M suffix match was case-sensitive (took "15M" but not "15m"), and a bare number with no unit (e.g. "20" meaning "£20M") was silently read as twenty pounds, producing a nonsense reconciliation. Fixed the case-sensitivity, and added `parser.parse_budget()` specifically for user-typed CLI/Colab budget fields — it warns when a value parses suspiciously small with no unit present, rather than silently misreading it. CLI help text and the Colab notebook's budget fields now say explicitly to always spell out the unit.

## [v0.8] - 2026-07-30

Report visual/structural polish, prompted by feedback that 12 sections reads as an audit document rather than something a manager skims in two minutes and acts on. Purely a rendering-layer pass — no changes to report content, section order, `edwards.md`, or task instructions, so free-mode/API-mode content and the Target Dossier naming containment are untouched.

A new executive summary panel sits right after the stat tiles: 5-6 deterministic lines (shape, biggest risk, wage flag, top sell, top buy, budget verdict when set) computed straight from the analysis data — never from LLM prose — so it's identical in free mode and full mode, and each line jumps straight to its section. Squad Audit's "playing-time promise mismatches" table — the one genuinely long, pure-reference table in the report (27 rows in real test data) — is now collapsed by default via native `<details>`, print-safe via a small vanilla-JS handler. A generic semantic-tag mechanism colorizes exact-match known values (style-fit tiers, rising/stable/declining, Squad Audit tier names) as pills across three different tables at once. The pitch diagram's Best XI markers are now color-coded by role-score tier instead of flat navy. Target Dossier gets a leaderboard-style "top pick per need" highlight above its existing detail tables. The four "decision" sections (Recruitment, Exits, Squad Audit, Target Dossier) get a subtle accent border for page-skimming.

Caught during verification: collapsing the mismatches table was initially unconditional in free mode, which leaked raw `<details>` HTML into `.md` output — fixed by only requesting the collapsed rendering when the output format is actually HTML.

## [v0.7.1] - 2026-07-30

Public-readiness pass, prompted by asking what "ship" actually means now that the core tier is complete. Not a feature release — the code is unchanged; this closes the gap between what's built and what the public-facing surface (README, Colab, repo hygiene) actually says and offers.

The README was stale enough to be actively wrong: it claimed recruitment "never names a real market player" — false since v0.5's Target Dossier — and listed 9-10 sections when the report now has up to 12. Rewritten to match the current feature set, with `--market`/`--transfer-budget`/`--wage-budget` documented and Squad Audit/Target Dossier/Sale-Exit added to the section list.

The Colab notebook — the path the README recommends for "everyone" — had no way to reach Target Dossier or Window Plan; only Squad Audit and Sale/Exit's improvements worked there automatically (column-driven, no flag needed). Added a market-export upload step and transfer/wage budget fields, wired into the same `analyzer.analyze()` call the CLI uses.

Added an MIT `LICENSE` — there wasn't one on this public repo.

Verified with a genuinely fresh clone (not the working directory): installed from scratch per the README, ran both the minimal quickstart command and the fully-flagged example against the real squad/league/market files, and read the actual rendered output top to bottom.

## [v0.7] - 2026-07-30

Sale/Exit Analysis, completing the core tier — Squad Audit, Window Plan, Recruitment Brief, and Sale/Exit Analysis all sit at 80%, meeting the shipping bar in `VISION.md`.

A depreciation curve projects each exit candidate's value 1-2 years forward: `analyzer._build_value_curve()` pools value observations by age from the market pool (dense) or the squad itself (a sparser fallback), a windowed median requires at least 5 observations before trusting a curve point, and the projection is always a ratio applied to the candidate's own real value — never an invented baseline. Section 8 (Exits) gains Value now / +1yr / +2yr / Trend columns, with "insufficient data" shown honestly wherever the curve's too thin rather than a guess.

Replacement cost reuses the Target Dossier matching engine rather than building a new one, fed exit-derived priorities instead of recruitment ones. The design question this raised — should it name real players, like Target Dossier does? — was settled against the Michael Edwards archetype specifically: Edwards/Graham's model at Liverpool built specific, named, evidence-backed cases (Salah, not a wide-forward-shaped stats bucket), so replacement cost names real candidates too. That's done by extending Section 12 rather than opening a second named-player location — the "Section 12 is the only place a market player is ever named" invariant holds, with exit-driven entries tagged and rendered as a distinct "Replacement case" block. Section 8 stays reasoning-only and points to Section 12 by name rather than naming anyone itself. Only exits that leave a genuine gap get a case — Core/Rotation tier or load-bearing, never a "duplicated profile" sale, which by definition already has in-squad cover.

Verified end-to-end against the real squad and market files: gating logic checked by hand against tier/load-bearing data, both dossier kinds render distinctly in free mode and HTML, clean regression without `--market`, and a leakage check confirming no exit-replacement candidate is named anywhere outside the labeled Section 12 data block.

`VISION.md` also gets a one-line note flagging the Director-archetype idea (Edwards/Monchi/Edu — different processes, not just different voices) as an explicit future direction, out of scope for this build, which is Edwards-only by design.

## [v0.6] - 2026-07-30

Window Plan, completing the core-tier trio alongside Squad Audit and Recruitment Brief. New `--transfer-budget`/`--wage-budget` flags (parsed via the existing `parser.parse_wage()`, so `£15M`/`£45,000` shorthand just works). Every recruitment priority now carries a fallback profile — a deliberately looser plan B with a wider age range and lower attribute floors — and a cost ceiling, pulled from real Target Dossier candidate values when `--market` is set. Without `--market`, the cost simply reads "not known yet" rather than a guess.

A budget block now opens Section 7: transfer/wage budget, expected exit proceeds (from the exit candidates' own value data), and a conservative reconciliation (available budget vs. the worst-case cost across all priorities) when both figures are known. Not a new numbered section — this enriches Section 7, which already owned recruitment content.

Also fixed a gap from v0.5: `edwards.md`'s Structure and thin-context guidance never mentioned Section 12 (Target Dossier) by name, even though the section itself was live — corrected alongside the new budget-awareness rule.

Verified with and without both budget flags, with and without `--market`, reconciliation arithmetic checked by hand, fallback profiles confirmed genuinely looser than the primary profile (not a copy), HTML rendering screenshot-checked.

Window Plan and Recruitment Brief both move to 80% in `VISION.md`. The core tier now sits at 3/4 artifacts done — Sale/Exit Analysis is the only remaining gate on shipping.

## [v0.5] - 2026-07-30

New Section 12 "Target Dossier" — the first feature to name real market players, a deliberate and narrow exception to the "recruitment is profile-based, never named targets" rule that's held since v0. New `--market PATH` flag (same HTML format as `--league`, parsed via the existing `parser.parse_league()` — zero parser changes). New `market_matching.py`: for each of Section 7's recruitment priorities, filters the market pool by age range, scores every candidate by role-fit (style-fit as a tiebreaker when `--tactic` is set), and keeps the top 3 per priority with contract runway, walk-away value range, and wage.

The relaxation is contained deliberately narrowly: Section 7 keeps its existing profile-only instructions untouched, and `edwards.md` gets exactly one new sentence carving out Section 12 as the sole exception. `html_report.py` needed no new code — the existing generic table renderer already handles the candidate tables.

Verified against the real 35-player squad and the real 35,973-player market export: free mode, `.md` output, and HTML rendering (screenshot-checked) all correct; a regression check confirms Section 12 and all market-player data are completely absent from the prompt when `--market` is omitted; API-mode prompt assembly verified directly (the configured API key is currently invalid, so a live call wasn't possible).

Target Dossier moves from 15% to 80% in `VISION.md`. Remaining gap: release clause/agent info and prose scouting notes, neither of which FM exports to a grid — likely stays a manual supplement rather than something this tool parses.

## [v0.4] - 2026-07-30

New Section 11 "Squad Audit" — every player classified Core/Rotation/Filler/Saleable/Exit, driven by FM's own "Actual Playing Time" status (not re-derived from role scores), with a value-created figure (current value vs. last transfer fee), agreed-vs-actual playing-time mismatch flags, and recurring-injury risk (weighted toward Core/Rotation players, since a fragile first-choice player is a bigger planning problem than a fragile fringe one). New tier-count chart and a "value created" leaderboard.

Parses 5 new optional squad-export columns (`Mins`, `Actual Playing Time`, `Agreed Playing Time`, `Last Trans. Fee`, `Rc Injury`) — all recommended, never required, so exports without them keep working exactly as before. New `squad_audit.py` module; the tier mapping is grounded directly in the user's own stated playing-time philosophy per status, validated against a real 35-player export (all 13 "Surplus to Requirements" players landed correctly in Exit, zero unmapped labels).

Squad Audit moves from 40% to 80% in `VISION.md` — the shipping bar agreed for the core tier. Remaining gap is a contract-runway timeline visual, which is presentation on data already available, not a missing input.

## [v0.3] - 2026-07-29

HTML becomes the default report format (`--out report.html`) — a self-contained styled report, no extra software needed, `.md` still available on request. Includes hand-built inline SVG charts (formation viability, style-fit distribution, wage by position, age profile, absolute-vs-league-relative comparison), zero new dependencies. New Section 10 "How We Compare to the League" gives a standalone squad-wide read against the division, reusing data already computed in v0.1/v0.2. `edwards.md` tightened for an executive-communicator voice — leads with the verdict, caps attribute citations, groups minor players into one sentence — roughly 22% shorter in testing despite the new section.

Follow-up styling pass informed by analyzing an Opta Analyst reference article: name→verdict→number sentence order, bold player names on their decisive mention, a stat-tile strip for headline numbers, a dark ranked-leaderboard component for top-N moments (formation viability), and a hand-built SVG pitch diagram showing the Best XI positioned by formation slot (one coordinate map covering all 6 formations).

Two bugs found via screenshot verification and fixed: chart value labels clipping at the SVG edge on long values, and a stray "---" separator (that some API responses add after the title) rendering as an empty section card.

## [v0.2] - 2026-07-29

Adds a `--league PATH` flag (requires `--tactic`) that imports a current-league HTML export and converts each squad player's style-fit score into a weighted percentile rank against every league player at the same position, benchmarked with the same tier language ("Does very well" etc.). Statistics only — no opposition or league player is ever named in the report, keeping the "recruitment is profile-based, never named targets" rule intact. Benchmark weights every league player by appearances (starts count more than sub apps), so it self-corrects for pre-season automatically without a special case.

New `league_context.py` module (pure benchmarking math). `parser.py` refactored to share its column-parsing engine between `parse_squad()` and the new `parse_league()`, and fixed to handle scouted attribute ranges ("11-15") that appear for less-known opposition players. Extended status-code recognition with 9 new Info-column codes shared across both export types.

Verified against the real 1206-player, 19-club league export and the user's real squad, in free and API mode — confirmed Claude's prose uses league percentiles correctly (e.g. a keeper's absolute "Does well" score reading as 98th-percentile elite once benchmarked) without ever naming an opposition player.

## [v0.1] - 2026-07-29

Adds a `--tactic` flag: the manager can set one of 6 preset tactical directions (Control Possession & High Press, Gegenpress, Low Block & Fast Counters, Low Block & Waste Time, Low Block & Direct Long Passing, Tiki-Taka). Every player gets a style-fit score (0-100, banded into 4 tiers) alongside their existing role-fit score, computed per position group — the same style asks different things of a centre-back than a striker (e.g. under Low Block & Fast Counters, defenders are scored on positional discipline, attackers on pace). New `tactics.py` module. Woven into the existing Section 2 (Shape) and Section 7 (Recruitment) of the report rather than added as a new section. Omitting `--tactic` is a complete no-op — output is unchanged from v0.

Verified against a synthetic squad and the user's real save, in both free mode and API mode.

## [v0] - 2026-07-29

Initial release. Parses one FM24 squad HTML export, scores every player against 28 roles across 6 formations, and produces a Director of Football markdown briefing (Michael Edwards voice, via Claude) or a deterministic free-mode fallback with no API key. Full detail in `V0-SUMMARY.md`.
