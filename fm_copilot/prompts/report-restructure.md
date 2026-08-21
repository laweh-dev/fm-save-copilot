# FM Save Copilot — report restructure spec

## Context

The generated briefing is 5,800 words across 13 sections. It's accurate but it makes the reader assemble the decision themselves: the striker / wing-back / keeper gaps are discussed in sections 3, 7, 9 and 12, and the recruitment profiles are separated from the actual candidates by 3,000 words.

This is a **structural** problem, not a voice problem. `edwards.md` already says "tables are the default", "lead with the verdict", "be concise" — and the output ignores all three, because the 13-section schema in `_task_instructions` forces the duplication and the model is correctly obeying it. Fix the schema first; the voice rules will then bite.

Target: same underlying data, ~2,300 words, decision-first.

Reference artefact: `report_v2.html` (attached) — a hand-built example of the target output. Use it for structure and information density. Do not copy its CSS wholesale.

## Ground rules

- **If it's not in this spec, it doesn't exist.** No new analysis, no new fields on `SquadAnalysis`, no new CLI flags, no refactors of `analyzer.py` / `roles.py` / `parser.py`. Every number in the target output already exists in the current data model.
- Work in the five stages below, in order. Commit after each. Do not start stage N+1 before stage N runs clean.
- Free mode (`_free_mode_report`) must keep working at every stage. It shares the `_render_*` helpers, so it inherits most of this for free — but check it after each stage.
- Preserve the existing "printed on A4" quality bar: print styles, no emoji, no charts in the markdown layer.

---

## Stage 1 — Collapse the schema (report.py)

Rewrite `_task_instructions` and `SECTION_HEADERS` from 13 sections to 10. Mapping:

| New | Name | Source |
|---|---|---|
| 1 | HEADLINE VERDICT | old 1, cut to one verdict sentence + inline availability stat line |
| 2 | THE WINDOW | **new** — decision board (stage 2) |
| 3 | ORDER OF OPERATIONS | **new** — sequencing (stage 2) |
| 4 | THE SHAPE | old 2 + old 6 folded into a "Read" column on the XI table |
| 5 | WHAT THIS SQUAD CANNOT DO | old 3, plus a Fix column; absorbs load-bearing rows from old 6 |
| 6 | EDGES | old 4 |
| 7 | THE MONEY | old 5 + value-created block from old 11 |
| 8 | AGAINST THE DIVISION | old 10 (conditional on league context, as now) |
| 9 | TARGETS | old 7 + old 8 + old 12 merged (stage 3) |
| 10 | HOUSEKEEPING | old 11 mismatches + old 13 pipeline (conditional, as now) |

Sections 8 and 10 stay conditional on the same `has_style_fit` / `has_squad_audit` / `has_development_pipeline` flags that already gate them.

**Kill the prose invitations.** Count them in the current section blocks — there are roughly twelve ("2-3 sentences", "one line below the table", "close with one sentence", "one sentence on sequencing is welcome"). Each is individually reasonable; together they're most of the word count. Delete every one that isn't gated behind a hard condition.

The worst offender is in the Section 2 block: *"This judgment is genuinely a paragraph's job (it's reasoning, not a list), so it's the exception here, not the pattern."* That single sentence licensed a 400-word section. Remove it. Replace with a 3-bullet cap.

**Add a word budget** to the Rules list in `_task_instructions`: whole briefing 2,000–2,500 words; no section over 350; sections 5, 6 and 10 under 200. `generate()` already computes `word_count` — print a warning when it exceeds 2,800.

---

## Stage 2 — Decision board + sequencing (report.py)

Add `_render_decision_board(analysis) -> str`. This is Python assembly, not new analysis — every row already exists:

- **Sell** rows ← `analysis.exit_candidates` (player, wage, best_role_score, reasons, value_now / trend)
- **Buy** rows ← `analysis.recruitment_priorities` (role, rationale, cost_ceiling)
- **Protect / Hold** rows ← `analysis.decisive_players["ceiling"]` and `["load_bearing"]`
- **Fix** rows ← `analysis.squad_audit["mismatches"]`, filtered to Core/Rotation tier

Emit one table: `Call | Who | Number | Trigger | Why`. Python fills Call, Who and Number (derive Number from `value_low` for sells, `cost_ceiling` for buys, `£0` for fixes). The LLM writes only **Trigger** and **Why** — one clause each, hard cap.

Add `_render_sequencing(analysis) -> str` covering the ordering constraints. This is where the gate from stage 4 surfaces: any exit with a `gate` field must appear after its replacement signing in the order.

Feed both into `_squad_analysis_markdown` as pre-tabulated context, same as every other renderer. Add both to `_free_mode_report`.

---

## Stage 3 — Un-isolate the Target Dossier (report.py)

`SECTION_12_BLOCK` currently enforces *"Recruitment is profile-based only… Nowhere else, ever, names a market player."* That rule made sense when `--market` was optional. It now costs the reader 3,000 words between the profile (`Fin 14+, OtB 14+, Acc 14+`) and the name (Van Britsom).

Make it conditional on data you already branch on:

- **`has_target_dossier == False`** → Section 9 is profile-only. Current behaviour, unchanged.
- **`has_target_dossier == True`** → Section 9's table gains `Lead candidate` and `Case` columns. One lead per need, drawn from the top-ranked dossier entry. Exit replacement cases become rows in the same table, tagged `REPLACES <player>`.

The standing caveat (computed from role-fit/style-fit and FM's valuations, availability not modelled) moves to the foot of Section 9 and stays mandatory.

Keep the full dossier tables — including the succession index — but move them behind a `<details>` block when `is_html_output` is true, reusing the pattern already in `_render_squad_audit(collapse_mismatches=...)`. The detail stays available; it just stops being the main body of the report.

The "never name an opposition or league player" rule is separate and stays absolute.

---

## Stage 4 — Two correctness joins (report.py)

These are bugs, not formatting.

**4a. Exit ↔ load-bearing gate.** `_render_exits` and `_render_decisive` don't talk to each other. Section 6 flags Longstaff as load-bearing with next-best 68.4; Section 8 says sell him. The current output reconciles this only because the model happened to notice.

In `build_user_message` (or a small helper), cross-reference `exit_candidates` against `decisive_players["load_bearing"]` by player name. Any match gets `gate: "replacement must be contracted first"` on the exit row. Render it in the Number/Trigger cell of the decision board and enforce it in the sequencing order.

**4b. Saleable ↔ high style-fit conflict.** `squad_audit` tags McConnell Saleable/Fringe; `tactical_style_fit` has him at the 83rd percentile — the best-matched player in the squad for the chosen system. Both facts ship, 4,000 words apart, unreconciled.

Add a check: any player tiered Exit or Saleable whose league style-fit percentile is ≥ 70 gets flagged as a conflict row in Section 10, with both numbers side by side. Let the LLM write the resolution line; Python supplies the flag.

**4c. Declare which scale governs.** `_render_style_fit` emits absolute tiers (0/12/12/0) and league-relative tiers (1/3/3/17) with no statement of precedence, and the two tell materially different stories. Add one line to the renderer: when `league_context` is present, league-relative is authoritative and absolute scores are context only.

---

## Stage 5 — edwards.md

Six changes. The first is the important one.

1. **Invert the third philosophy bullet.** "Diagnostic before prescriptive. Sections 1-6 diagnose the squad. Sections 7-9 prescribe." This guarantees the manager reads 3,000 words before learning what to do, and directly contradicts the executive-communicator bullet two lines below it. Replace with: *decision first, evidence after — the diagnosis exists to justify the decision board, not to precede it.*

2. **Add a bullet grammar.** The concision rules describe a quality without giving a shape to write into. Specify: bolded claim → inline evidence → `→` action line. Two lines maximum per bullet.

3. **Require a comparator on every number.** "CD_d 70.3" is a datum; "70.3, next option 65.4" is an argument. No score, wage or valuation appears without the figure that gives it meaning — next-best, division median, budget, or prior-year value.

4. **Add a threshold-and-gate rule.** Every recommendation carries an accept-at figure and a precondition. "Sell Longstaff" is an opinion; "accept £4M+, only once the replacement is signed" is a decision. Derive thresholds from `value_low`/`value_high`, gates from stage 4a.

5. **Add "state each fact once."** The current output literally writes *"Both are already described in Section 3. The short version:"* and then restates it — the model knows it's repeating and does it anyway because the schema demands the row. Cross-reference by section number, never re-explain.

6. **Add a confidence rule.** Where a figure is missing or an outlier (Prömel's unknown valuation, Bengui Joao's 44.4 style score against a 60+ peer group), say so in the row rather than presenting it with the same confidence as everything else.

Also cut: the "an occasional short question can pivot between points" licence. It's an invitation to filler.

**Then clean the split.** `edwards.md` currently carries structure ("a 12th, Target Dossier, only appears when…") and `_task_instructions` currently carries voice ("lead with the verdict, cite 1-2 attributes"). Both files state the never-name-a-market-player rule in different words, and it will drift every time a section changes.

- `edwards.md` owns **voice, judgment, what counts as evidence**.
- `report.py` owns **section order, data shape, conditionals**.

Move the concision guidance out of the section blocks into the prompt. Move all "only appears when" logic out of the prompt into the blocks. Each rule lives in exactly one file.

---

## Stage 6 — html_report.py (last)

Read `html_report.py` first; it wasn't part of this review. None of it works until the markdown headers change, so do it after stages 1–5 are green.

From `report_v2.html`, port: the KPI strip under the masthead, coloured decision tags (buy / sell / hold), CSS percentile bars with a median rule for Section 8, and the wage-split bar for Section 7. Keep the existing palette and the A4 print styles.

---

## Acceptance

- Runs end-to-end on the existing sample export, API mode and free mode.
- Output is 2,000–2,500 words.
- A reader who stops after Section 3 knows every decision, its number, its trigger and its order.
- No fact stated in full more than once; repeats are cross-references.
- No load-bearing player recommended for sale without a gate on the row.
- No recommendation without a threshold.
- Every conditional section still drops cleanly when its data is absent.