# FM Save Copilot v0 — Status Summary

Internal reference: what shipped, what was deliberately left out, and what real-world testing surfaced as the honest next priorities. Written after building v0 and validating it against one synthetic squad and one real save (Brighton & Hove Albion, 26 players).

## What v0 does

- **Single command, single job.** `python -m fm_copilot squad.html --out report.md` — one FM24 squad HTML export in, one markdown briefing out. No UI, no interactive prompts.
- **Column-name-based parsing**, not position-based — tolerant of different FM view configurations, with an alias table for short-code headers (`Pac`, `Wor`, `Tck`, etc.).
- **Role-fit engine**: every player scored against all 28 supported FM roles (weighted KEY/PREF/OTHER attribute tiers), plus best-XI and structural-weakness detection across all 6 candidate formations (4-2-3-1, 4-3-3, 3-5-2, 3-4-3, 4-4-2, 3-4-2-1).
- **Fully deterministic analyzer** (no LLM) producing: headline availability facts, best-supported shape + key dependencies, per-role coverage (capable/strong/elite), tactical impossibilities with numeric evidence, hidden strengths (set pieces, wide pace, youth pipeline), wage analysis (top earners, overpaid outliers, best-value contracts, position-cost split), decisive players (ceiling/structure/floor/load-bearing), recruitment priorities, exit candidates, and age profile.
- **Recruitment is profile-based only** — "sign a ball-winning midfielder, tackling 14+, work rate 15+, age 21-27," never a named real player. No market data is used or required.
- **Two operating modes**, both fully working:
  - *API mode* — Claude writes the 9-section prose briefing in a hardcoded Michael Edwards voice, grounded entirely in the analyzer's output.
  - *Free mode* — no API key required; same analysis rendered as deterministic markdown tables. The tool never leaves the user with nothing.
- **Validation gates** print at each pipeline stage (`[parser]`, `[roles]`, `[analyzer]`) so missing/dropped data is visible immediately, not buried in the final report.
- API key never touches the repo — `config.yaml` / `.env` gitignored, free mode is the safe fallback.

## What v0 deliberately does not do

This was scoped tightly on purpose — these are not bugs, they're the line we drew:

- **No market file input, no named market targets.** Recruitment section is role + attribute floors + rationale, full stop. Nothing named that isn't in the squad export.
- **No UI, dashboard, wizard, charts, or images.** Markdown report is the entire product.
- **No multiple DoF personas.** Michael Edwards voice is the only voice, hardcoded in `prompts/edwards.md`, not user-editable via config.
- **No five-file context system.** Explicitly deferred to v1.
- **No transfer history log** — the tool has no memory between runs.
- **No league-tier or manager-disagreement mechanics.**
- **No multi-window transfer roadmap** — the 12-18 month outlook lives as prose in Section 9, not a structured plan.
- **Role weights are hardcoded in `roles.py`**, football-sensible but not identical to FM's internal match-engine formulas, and not user-editable without touching code.

## What real-world testing surfaced (not planned scope cuts — friction we hit)

Building against a synthetic squad caught the architecture bugs. Running it against a real save caught the actual operational risk: **FM's HTML export format is not fixed** — it varies by view configuration and possibly by FM version/skin. Specifically:

- The real export's name column was headered **"Player"**, not "Name" — the parser hard-failed on first run until this alias was added.
- The name cells carried trailing junk text (`"Thomas McGill - Pick Player"`) from what looks like an interactive "pick player" widget flattened into plain text on export — required a targeted strip rule.
- Several attribute/field headers used abbreviations not in the original alias table: `Bra` (not `Brv`) for Bravery, `TRO` (not `Rus`) for Rushing Out, `Inf` (not `Info`), `Potential` spelled out instead of `PA`.
- The Info/status column was compressed to undocumented 3-letter codes (`Sus`, `Lst`, `Inj`, `Ret`, `Wnt`, `Ask`, `Frt`) rather than full words. Only three (`Inj`, `Sus`, `Lst`) were mapped with confidence; `Ret`, `Wnt`, `Ask`, `Frt` are still unrecognized and silently produce no status flag rather than a guessed (and possibly wrong) one.

None of this broke the architecture — every fix was a targeted addition to an alias table — but it confirms the header-mapping layer is the single most fragile part of v0, and it will keep needing reactive patches as it meets more real exports.

## Recommended pivot priorities for v1

Roughly in order of leverage:

1. **Harden the parsing layer before adding features.** Add a "column diagnostics" mode — print raw headers found vs. what matched/didn't, before the hard-fail — so a new FM view or skin is a two-minute fix instead of a debugging session. Consider cataloguing known FM skins/locales rather than patching alias-by-alias as exports arrive.
2. **Market file input + named market targets.** This is the single biggest capability gap between v0 and a tool someone would use every window — v0 is diagnostic-only today, it never says who to actually sign.
3. **Five-file context system**, as originally planned, to give the DoF persistent memory of prior windows/decisions instead of a one-shot snapshot.
4. **Club name extraction** — reports currently always title as "SQUAD REVIEW" since no club identifier is parsed out of the export.
5. **An automated regression test suite** against a small library of real (anonymized) export samples, so header-format drift gets caught by CI instead of by the next person running it against their save.
6. **Transfer history / trajectory log** — track squad state across saves so Section 9's outlook can eventually be checked against what actually happened.

## Known-good state

- Free mode: verified end-to-end against a real 26-player save. Parser coverage 47/47 attributes, 100% wage/value/height/contract coverage, correct status detection post-fix.
- API mode: prompt assembly (player cards, full roster, squad-analysis markdown) verified to build without error against the same real save; full narrative generation confirmed working by the user directly.
