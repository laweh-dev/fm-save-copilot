# Data requirements

What each `VISION.md` artifact needs, and whether we already have it. Use this to check what's actually exportable from FM24 before we build against it.

**Legend:** ✓ have it · ⚠️ have the data source, haven't built the feature · ✗ missing, need to find or manually enter

## Check these next — highest remaining leverage

1. ~~Add an "Apps" column to your Squad view in FM.~~ **Done** — plus `Mins`, `Actual Playing Time`, `Agreed Playing Time`, and `Last Trans. Fee`, which closed all three original Squad Audit blockers (see §5.1 below).
2. **FM's Finances screens (turnover, P&L, player trading/transfer history) — not exportable.** Confirmed: can't be printed from the Finances screen. **Deferred** — turnover-dependent lines (Wage Structure Review peer/turnover comparison, Board Report PSR headroom, §2.3 solvency) are on hold until we scope exactly what's needed and how it'd be provided (likely manual entry, not a file).
3. ~~Check Scouting → Player Search / Shortlist for the same export mechanism as the league file.~~ **Done — confirmed working.** 35,973 players across 4,219 clubs (a genuine global market pool, not just one division), same 59-column format as the league file, parsed correctly with **zero code changes** (`parse_league()` already handled it). This was the single biggest blocker on Target Dossier — it's gone.

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
| Club turnover / revenue | ⏸ Deferred | Not exportable from the Finances screen. Revisit once we've scoped what's actually needed and how to provide it |

## §5.3 Window Plan

| Data point | Status | Notes |
|---|---|---|
| Recruitment priorities, exits | ✓ | Sections 7-8 already |
| Transfer + wage budget available | ⚠️ | Not in any player export, and not exportable from Finances either — becomes a direct user input (two numbers: transfer budget, weekly wage room), not a parsed file |

## §5.4 Recruitment Brief

| Data point | Status | Notes |
|---|---|---|
| Everything else needed | ✓ | Essentially done already (Section 7) |
| Cost ceiling per priority | ⚠️ | Same budget input as §5.3 |

## §5.5 Target Dossier — market data confirmed working

| Data point | Status | Notes |
|---|---|---|
| Market player pool (attributes, position, age, club, wage, value, contract) | ✓ | Confirmed — same format as the league export, 35,973 players across 4,219 clubs, zero code changes needed to parse it |
| Scouted attribute confidence (ranges vs exact values) | ✓ | Already handled — our parser resolves "11-15"-style scouted ranges to a midpoint (fixed during the league-context work) |
| Scouting report text / recommendation | ✗ | Prose scout notes are read in-game, not exported to a grid — likely stays a manual supplement, not something we parse |
| Release clause / agent info | ✗ | Not present in this export's columns |
| Walk-away price / valuation comparables | — | Derived from value + wage + age now that the market pool exists, not a separate export |
| Recruitment-brief-to-market matching engine | ✗ | The data exists; the feature that scores real market players against a recruitment profile doesn't exist yet — this is the actual remaining work |

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
