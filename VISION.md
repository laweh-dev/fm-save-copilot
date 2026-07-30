# Vision

The end state for this project is the Sporting Director role in full, not just a squad-analysis CLI: build and protect a squad's value, keep it compliant, define the playing identity, and produce the documentary output a real Sporting Director produces (squad audit, wage review, window plan, recruitment briefs, target dossiers, exit analysis, post-window review). Named market targets are explicitly part of that end state — the "profile-only" recruitment principle is a v0-v0.3 constraint, not a permanent one.

Everything built so far is the **Michael Edwards archetype** specifically — a department that builds independent, evidence-backed, named cases and puts them to the manager. Future direction, not scoped yet: a `--director-style` axis (Edwards/Monchi/Edu) that changes the *process*, not just the voice — coach-brief-driven or network-scouting models would behave differently, not just sound different.

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
| Window Plan | Core | 80% | per-signing budget fit (reconciliation is squad-wide today, not "does signing #2 still fit after #1") |
| Recruitment Brief | Core | 80% | same per-signing budget fit gap as Window Plan |
| Sale/Exit Analysis | Core | 80% | same per-signing budget fit gap as Window Plan/Recruitment Brief |
| Wage Structure Review | 2nd | 35% | club turnover (deferred — not exportable, needs scoping) |
| Post-Window Review | 2nd | 0% | persistence layer (no memory between runs yet) |
| Board Report | 2nd | 20% | turnover / PSR headroom data (deferred, as above) |
| Academy Pathway | Later | 10% | squad-status data, loan history |
| Loan Report | Later | 10% | loan performance data |
| Target Dossier | Milestone | 80% | release clause / agent info, prose scouting notes (both unexportable — likely stay a manual supplement) |

Playing identity (style-fit) and the coach-specifies/director-sources split are already close to done — not tracked as gaps here.

## Phase order

1. Persistence layer — unlocks every history-dependent line above (trend data, post-window review, "judged over three years").
2. ~~Squad Audit~~ — **done, 80%.**
3. ~~Market-file input + Target Dossier~~ — **done, 80%.** `--market` flag, matching engine, and the narrow named-player carve-out (Section 12 only), built ahead of its original place in this order since Window Plan needed it for a real cost ceiling.
4. ~~Window Plan~~ — **done, 80%.** `--transfer-budget`/`--wage-budget`, fallback profiles per priority, cost ceilings pulled from Target Dossier candidates, reconciliation block at the top of Section 7. Recruitment Brief rides along at 80% too — same underlying work.
5. ~~Sale/Exit Analysis~~ — **done, 80%.** Depreciation curve (age-value curve from the market pool, ratio-projected onto each exit candidate's real value) and replacement cost (reuses the Target Dossier matching engine, surfaced in Section 12 as a distinctly-tagged "replacement case" alongside recruitment candidates — only for exits that leave a genuine gap, not every sale).
6. **Core tier is at 80% across all four artifacts — the shipping bar is met.**
7. Wage Structure Review / Board Report — once turnover data is sourced.
8. Academy + Loan reports.
