# Data requirements

What each `VISION.md` artifact needs, and whether we already have it. Use this to check what's actually exportable from FM24 before we build against it.

**Legend:** ✓ have it · ⚠️ have the data source, haven't built the feature · ✗ missing, need to find or manually enter

## Check these next — highest remaining leverage

1. ~~Add an "Apps" column to your Squad view in FM.~~ **Done** — plus `Mins`, `Actual Playing Time`, `Agreed Playing Time`, and `Last Trans. Fee`, which closed all three original Squad Audit blockers (see §5.1 below).
2. **Check FM's Finances screens (turnover, P&L, player trading/transfer history) for any export option.** These are almost certainly *not* grid views like the squad/league screens, so they probably don't support "export to web page" the same way — if so, this becomes manual entry (a CLI input) rather than a parsed file. Confirm either way before we build against it.
3. **Check Scouting → Player Search / Shortlist for the same export mechanism as the league file.** If it works the same way (build a view, export to web page), Target Dossier's biggest blocker disappears immediately.

---

## §5.1 Squad Audit

| Data point | Status | Notes |
|---|---|---|
| Age, position, contract end | ✓ | |
| Current wage | ✓ | |
| Market value (low/high) | ✓ | FM's "Value" / "Transfer Value" column |
| Role-fit / style-fit scores | ✓ | Computed by the tool, not an FM export |
| Minutes played, appearances (own squad) | ✓ | `Apps` + `Mins` columns, added and parsed — Section 11 of the report |
| Purchase value (proxy for book value) | ✓ | `Last Trans. Fee` column — used as our purchase-price proxy per the user's framing (the fee paid for their most recent move, assumed to be what we paid). Not true amortised book value (no depreciation schedule), but a real, useful proxy |
| Core/rotation/filler/saleable/exit label | ✓ | Derived from FM's own `Actual Playing Time` column — see the tier-mapping table in `fm_copilot/squad_audit.py` |
| Agreed vs. actual playing-time mismatch (retention risk flag) | ✓ | Bonus — `Agreed Playing Time` column enabled this beyond what was originally scoped |
| Recurring injury risk (history, not games-missed count) | ✓ | `Rc Injury` column — names the recurring issue (e.g. "Tight groin") when present, used as an availability-risk flag in Section 11, weighted higher for Core/Rotation tier |
| Contract-runway timeline (visual) | — | Data exists (`contract_end`); just needs a chart, not new FM data |

## §5.2 Wage Structure Review

| Data point | Status | Notes |
|---|---|---|
| Own squad wage bill | ✓ | |
| League-peer wage comparison | ⚠️ | Your league export already has a Wage column — the data's there, we just haven't built the comparison feature |
| Club turnover / revenue | ✗ | See "check first" #2 |

## §5.3 Window Plan

| Data point | Status | Notes |
|---|---|---|
| Recruitment priorities, exits | ✓ | Sections 7-8 already |
| Transfer budget available | ✗ | Not in any player export — will need a CLI input (`--budget`), not something to find in FM |

## §5.4 Recruitment Brief

| Data point | Status | Notes |
|---|---|---|
| Everything else needed | ✓ | Essentially done already (Section 7) |
| Cost ceiling per priority | ✗ | Same budget gap as §5.3 |

## §5.5 Target Dossier — the new one, now confirmed in scope

| Data point | Status | Notes |
|---|---|---|
| Market player pool (attributes, position, age, club, wage, value, contract) | ✗ | New export needed. Same shape as `Current League.fmf` — build a Scouting/Player Search view with the same columns, export the same way. See "check first" #3 |
| Scouted attribute confidence (ranges vs exact values) | ✓ | Already handled — our parser resolves "11-15"-style scouted ranges to a midpoint (fixed during the league-context work) |
| Scouting report text / recommendation | ✗ | Prose scout notes are read in-game, not exported to a grid — likely stays a manual supplement, not something we parse |
| Release clause / agent info | ? | Check whether a scouting/shortlist view can show these as columns |
| Walk-away price / valuation comparables | — | Derived from value + wage + age once the market pool exists, not a separate export |

## §5.6 Sale and Exit Analysis

| Data point | Status | Notes |
|---|---|---|
| Exit candidates + reasoning | ✓ | Section 8 already |
| Depreciation curve (value trend by age) | ⚠️ | Computable from age + value alone — feature not built yet, no new data needed |
| Replacement cost (who could replace them) | ✗ | Needs the market pool from §5.5 |

## §5.7 Post-Window Review

| Data point | Status | Notes |
|---|---|---|
| Everything structural | ✗ | Software gap, not a data gap — needs the persistence layer (re-running the tool after a window closes, diffed against the last run) |
| Transfer fees actually paid/received | ✗ | Same book-value gap as §5.1 — would sharpen this a lot if available |

## §5.8 Academy Pathway

| Data point | Status | Notes |
|---|---|---|
| Age, CA/PA | ✓ | |
| Youth status flag | ✓ | The "Yth" Info code |
| U18/U21 squad assignment specifically | ✗ | Age ≤ 21 is currently our proxy — check if FM's squad view has an actual squad/team column (First Team / U21 / U18) |
| Loan history for developing players | ✗ | Same as §5.9 |

## §5.9 Loan Report

| Data point | Status | Notes |
|---|---|---|
| Currently-on-loan status | ✓ | "On Loan" / "On Loan From" Info codes |
| Performance while out on loan (minutes, rating) | ✗ | Lives at the loan club, not your squad screen — check for a dedicated "Loanees"/"Out on Loan" report view that exports separately |

## §5.10 Board Report

| Data point | Status | Notes |
|---|---|---|
| Squad status, recruitment/exit summary | ✓ | Reuses everything else |
| PSR headroom, turnover | ✗ | Same as §5.2 / §2.3 |

## §6 Measurement / KPIs

| Metric | Status | Notes |
|---|---|---|
| Age profile health | ✓ | Already a report section |
| Net transfer spend vs league position | ✗ | Needs transfer fees (§5.1) + a league table, not currently parsed at all |
| Value creation | ✗ | Needs book value + persistence |
| Hit rate (signings reaching projected minutes) | ✗ | Needs minutes played + persistence |
| Wage-to-turnover ratio | ✗ | Needs turnover |
| Contract hygiene | ⚠️ | We flag contract cliffs already; not yet tracked as a trend over time |
