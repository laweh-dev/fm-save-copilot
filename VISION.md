# Vision

The end state for this project is the Sporting Director role in full, not just a squad-analysis CLI: build and protect a squad's value, keep it compliant, define the playing identity, and produce the documentary output a real Sporting Director produces (squad audit, wage review, window plan, recruitment briefs, target dossiers, exit analysis, post-window review). Named market targets are explicitly part of that end state — the "profile-only" recruitment principle is a v0-v0.3 constraint, not a permanent one.

## Shipping bar

Ship to the public once the **core tier** reaches 80% against the vision — not 100%, and not uniformly across every artifact below. Peripheral/periodic artifacts can trail without blocking a release. Target Dossier is large enough (needs a whole market-data subsystem, and relaxes the no-named-targets rule) that it's tracked as its own milestone, not a gate on the first ship.

- **Core tier (blocks ship):** Squad Audit, Window Plan, Recruitment Brief, Sale/Exit Analysis — the artifacts a DoF actually touches every week or every window.
- **Second tier (tracked, doesn't block):** Wage Structure Review, Post-Window Review, Board Report.
- **Later tier:** Academy Pathway, Loan Report.
- **Separate milestone:** Target Dossier — needs market-file input and a deliberate relaxation of the "never name a player" rule.
- **Out of scope:** Coach succession (§2.5 of the role doc) — a human/org function, not a squad-data problem this tool can help with.

## Status

Rough, updated as we build — see `DATA_REQUIREMENTS.md` for exactly what FM data each line is waiting on.

| Artifact | Tier | Status | Blocking gap |
|---|---|---|---|
| Squad Audit | Core | 80% | contract-runway timeline visual (data exists, just needs a chart) |
| Window Plan | Core | 45% | budget input, fallback-per-priority |
| Recruitment Brief | Core | 70% | cost ceiling |
| Sale/Exit Analysis | Core | 35% | depreciation curve, replacement cost |
| Wage Structure Review | 2nd | 35% | club turnover (deferred — not exportable, needs scoping) |
| Post-Window Review | 2nd | 0% | persistence layer (no memory between runs yet) |
| Board Report | 2nd | 20% | turnover / PSR headroom data (deferred, as above) |
| Academy Pathway | Later | 10% | squad-status data, loan history |
| Loan Report | Later | 10% | loan performance data |
| Target Dossier | Milestone | 80% | release clause / agent info, prose scouting notes (both unexportable — likely stay a manual supplement) |

Playing identity (style-fit) and the coach-specifies/director-sources split are already close to done — not tracked as gaps here.

## Phase order

1. Persistence layer — unlocks every history-dependent line above (trend data, post-window review, "judged over three years").
2. Squad Audit → 80%.
3. Window Plan → 80% (needs a budget input).
4. Sale/Exit Analysis → 80%.
5. Ship (core tier at 80%).
6. ~~Market-file input + Target Dossier~~ — **done.** `--market` flag, matching engine, and the narrow named-player carve-out (Section 12 only) are built and verified.
7. Window Plan's budget input, using Target Dossier's real candidate values for the cost ceiling — next up.
8. Wage Structure Review / Board Report — once turnover data is sourced.
9. Academy + Loan reports.
