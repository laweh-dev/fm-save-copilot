# Feedback Backlog

All 12 tickets below are live on [GitHub Issues](https://github.com/laweh-dev/fm-save-copilot/issues) as #2–#13.

Synthesis of everything in `/feedback` (`google_form.md`, `reddit_dms.md`, `reddit_thread_1.md` — 10 distinct reports across 3 sources) plus one issue we already fully root-caused through direct testing this session, flagged separately since it isn't sourced from user feedback. Each theme below is tagged to the component it lives in, per the v0 architecture described in `V0-SUMMARY.md`, and every root cause was verified against the current code before being written up — nothing here is guessed from the symptom alone.

**No tone/voice complaints were received in this batch.** Every report is either a bug or a feature request; worth noting since it's one of the three categories asked for.

---

## Synthesis

| Theme | Category | Frequency | Component |
|---|---|---|---|
| "Salary" not recognized as Wage column | Bug | **4 reports, 2 sources** — most frequent issue by far | `parser.py` (`FIELD_ALIASES`) |
| Market matching ignores candidate's real position | Bug | 1 report, but same defect class already fixed once elsewhere | `market_matching.py` |
| Exits can clear a whole position with no recruitment backstop | Bug | 1 report | `analyzer.py` |
| Budget affordability checks only the low end of value range | Bug | 1 report | `market_matching.py` |
| Non-English FM locale breaks parsing entirely | Bug / scoping | 1 report | `parser.py` |
| Colab errors buried under IPython traceback noise | Bug (quality-of-life) | 1 direct report, affects every error path | `colab/FM_Save_Copilot.ipynb` |
| Colab Step 0 can fail with a raw traceback | Bug (quality-of-life) | 1 report, low reproducibility | `colab/FM_Save_Copilot.ipynb` |
| No way to input actual assigned tactical roles | Feature request | 1 report | `tactics.py` / `roles.py` |
| No way to specify extra recruitment positions to search | Feature request | 1 report | `analyzer.py`, CLI/Colab |
| Attributeless FM skins export blank attribute columns | Bug / docs gap | 1 report | `parser.py`, `README.md` |
| Stats-based ("Moneyball") scoring idea | Feature request (large) | 1 report | new — `roles.py` is attribute-only today |
| *(internal)* Tactical-impossibility flags contradict recommended formation | Bug | sourced from direct testing, not feedback | `roles.py` / `analyzer.py` |

---

## Tickets

### 1. Parser doesn't recognize "Salary" as the Wage column (American English exports) ([#2](https://github.com/laweh-dev/fm-save-copilot/issues/2))

**Problem:** `FIELD_ALIASES["wage"]` only contains `"wage"` (`parser.py:103`). FM24 under American English language/region settings labels the column "Salary" instead of "Wage," so the export hard-fails on the very first pipeline stage — the most common failure mode we've seen by a wide margin.

**User quote / evidence:**
> "I had Salary instead of Wage. Probably a language setting (American English vs British English). After I made that change, I re-uploaded the file and it worked." — Google Form #3
>
> Also reported independently in Google Form #2, #4, and the Reddit DM — 4 reports total.

**Proposed fix:** Add `"salary"` to `FIELD_ALIASES["wage"]` in `parser.py`. One-line change; verify against a synthetic export with a "Salary" header.

**Effort estimate:** S

**Priority:** P0

---

### 2. Target Dossier / market matching ignores a candidate's real position ([#3](https://github.com/laweh-dev/fm-save-copilot/issues/3))

**Problem:** `market_matching.py`'s candidate pool is filtered by age only (`pool = [p for p in market_players if age_lo <= p.age <= age_hi]`, `market_matching.py:114`) before scoring by role-fit — nothing checks whether the candidate's actual listed FM position is even compatible with the role being searched. We already solved this exact class of bug for the squad's own Best XI selection (`roles.py::SLOT_ELIGIBILITY`, shipped v0.8.1) but never ported it to market-candidate search.

**User quote / evidence:**
> "Only had one issue, it's recommended me a CB for an AF lol." — Reddit Thread #4

**Proposed fix:** Filter `market_matching.py`'s candidate pool through the same family/side eligibility check already built in `roles.py` (parse the candidate's position string, require it to plausibly cover the target role's position family) before scoring, not just age.

**Effort estimate:** M — logic already exists, needs porting across a module boundary and re-verifying against real market data.

**Priority:** P0

---

### 3. Exit recommendations can clear out an entire position with no recruitment backstop ([#4](https://github.com/laweh-dev/fm-save-copilot/issues/4))

**Problem:** `_recruitment_priorities()` only raises a goalkeeper priority when `headline["gk_available_count"] < 2` (`analyzer.py:544`), and that count reflects current injury/loan/suspension status only — it has no idea the tool's own exit logic (`_exit_candidates()`) just flagged every keeper on the books for sale. A squad with 3 fit goalkeepers can get all 3 recommended for exit in Section 8 while Section 7 stays completely silent, because on paper `gk_available_count` is still 3.

**User quote / evidence:**
> "When I ran the DoF for my squad, it was telling me to sell all my goalkeepers, but didn't suggest anyone to bring in to replace them." — Reddit Thread #3

**Proposed fix:** After exit candidates are computed, re-check recruitment-priority-triggering counts against "available minus recommended-for-exit," not just current status flags. Goalkeeper is the concrete case reported, but the same gap likely applies wherever a position group has few bodies.

**Effort estimate:** M

**Priority:** P1

---

### 4. Budget affordability check only looks at the low end of a candidate's value range ([#5](https://github.com/laweh-dev/fm-save-copilot/issues/5))

**Problem:** `_rank_and_limit()` classifies a candidate as "affordable" whenever `value_low <= budget` (`market_matching.py:78`) — the bottom of FM's value estimate, not a realistic expected fee. A player valued e.g. "£5M–£40M" reads as affordable against an £11.5M per-priority budget purely because the low end clears it.

**User quote / evidence:**
> "the target dossier gave me players way outside the stated budget (I'm playing as Hull City with a budget of 46M)." — Reddit Thread #1

**Proposed fix:** Anchor affordability to the value midpoint (or `value_high`) instead of `value_low`, or require a more conservative margin. Note: budget-aware ranking itself shipped in v0.9 — this ticket is about tightening the affordability threshold that ranking uses, not adding the mechanism from scratch.

**Effort estimate:** S

**Priority:** P1

---

### 5. Column parsing is English-only — non-English FM locales fail entirely ([#6](https://github.com/laweh-dev/fm-save-copilot/issues/6))

**Problem:** `FIELD_ALIASES` only contains English column headers. A save with FM's language set to Spanish (or any non-English locale) exports headers the parser has never seen ("Nombre" instead of "Name," etc.), so parsing fails on multiple required columns at once instead of one. Same root cause as Ticket 1, at a much larger scale — `V0-SUMMARY.md` already flagged the header-mapping layer as "the single most fragile part" of the tool.

**User quote / evidence:**
> "it said there was an error because it couldn't find "Name" or "Appearances" of the players, so I figured it was because I had it in spanish, so I set the game to english" — Google Form #5

**Proposed fix:** Not a quick patch — needs a scoping decision: support N locales via translated alias tables, or clearly document "export in English" as a hard requirement (cheapest short-term fix). Recommend the latter now, the former only if non-English reports keep recurring.

**Effort estimate:** L (if localized) / S (if just documented as a requirement — recommend starting here)

**Priority:** P1

---

### 6. Colab error messages are buried under unrelated IPython traceback noise ([#7](https://github.com/laweh-dev/fm-save-copilot/issues/7))

**Problem:** Every error branch in the Step 6 generate cell prints one clear `[xxx] ERROR: ...` line and then does `raise SystemExit`. Colab/IPython's traceback formatter chokes on that pattern and dumps a large, unrelated internal traceback (`AttributeError: 'tuple' object has no attribute 'f_lineno'`, `TypeError: object of type 'NoneType' has no len()`) underneath the one line that actually matters. This happened to the Reddit DM reporter — the real cause (missing wage column) was there, just buried under noise that looks far scarier than the actual problem.

**User quote / evidence:**
> Full traceback in `reddit_dms.md`, the real cause (`[parser] ERROR: Missing required column(s): wage`) buried under ~40 lines of unrelated IPython internals.

**Proposed fix:** Replace `raise SystemExit` (6 occurrences in the generate cell) with a clean early-return pattern so Colab never tries to render a traceback at all — the printed `[xxx] ERROR:` line should be the last thing the user sees.

**Effort estimate:** S

**Priority:** P2

---

### 7. Colab Step 0 setup can fail with a raw, unhelpful traceback ([#8](https://github.com/laweh-dev/fm-save-copilot/issues/8))

**Problem:** Step 0's `git clone`/`git pull`/`pip install` calls all use `check=True` with no surrounding try/except, so any transient failure (network hiccup, dependency resolution) surfaces as a raw `CalledProcessError` traceback instead of a clear message.

**User quote / evidence:**
> "now the colab doesn't even lets me start, like the step 0 is bugged or something" — Google Form #5

**Proposed fix:** Wrap Step 0 in a try/except that prints an actionable message ("Setup failed — try Runtime > Restart runtime and run this cell again"). Won't fix an underlying transient cause, but turns a scary unreadable error into something a non-technical user can act on. Low confidence on the exact trigger — only one report, and it may not be reproducible.

**Effort estimate:** S

**Priority:** P2

---

### 8. No way to tell the tool your actual assigned tactical roles ([#9](https://github.com/laweh-dev/fm-save-copilot/issues/9))

**Problem:** The role-fit engine scores every player against all 28 generic FM roles and the algorithm picks whichever scores highest — it has no way to know that, in the user's actual save, a specific fullback is deployed as Wing-Back Attack rather than Full-Back Defend. Two tactically-identical setups can score very differently depending on which role variant the algorithm happens to prefer.

**User quote / evidence:**
> "DoF assumes what roles I play on the tactic. For example, it only considers my fullbacks to be fullback defense instead of something like wing back attack. So it would be nice to be able to set the roles, or add a screenshot of the tactic." — Google Form #1

**Proposed fix:** Needs a design decision before code — most likely a CLI/Colab input for per-slot role overrides (e.g. "RB: Wing Back Attack"), not parsing a tactic screenshot (a much bigger computer-vision problem than this tool currently takes on). Scope as a design conversation first, not a straight build.

**Effort estimate:** L

**Priority:** P2

---

### 9. No way to specify which positions you want recruitment coverage for ([#10](https://github.com/laweh-dev/fm-save-copilot/issues/10))

**Problem:** Recruitment priorities are entirely algorithm-derived and capped at 4 (`_recruitment_priorities()`) — there's no way for a user to say "I also want a look at LB and GK options" even if those aren't among the top 4 gaps the algorithm found.

**User quote / evidence:**
> "any way to target specific positions? For example it tells me I need a striker, but I'd also like recommendations for a LB and GK. Any way to specify?" — Reddit Thread #4

**Proposed fix:** New optional `--positions` (CLI) / field (Colab) accepting a list of roles to always include a Target Dossier search for, independent of whether the algorithm flagged them as a structural priority.

**Effort estimate:** M

**Priority:** P2

---

### 10. FM skins without visible attribute numbers export blank attribute columns ([#11](https://github.com/laweh-dev/fm-save-copilot/issues/11))

**Problem:** Some FM skins display attributes as star ratings or bars rather than numbers; exporting a view under one of those skins produces genuinely blank attribute cells, which silently tanks every role-fit score for the whole squad. The parser already logs attribute-coverage stats to the console, but nothing tells a non-technical user their skin is the actual cause.

**User quote / evidence:**
> "because when you print screen in FM24 with an attributeless skin, the attributes come up blank." — Reddit Thread #2

**Proposed fix:** Document the numeric-attribute-skin requirement explicitly in the README's export instructions, and add a louder warning (not just a coverage percentage buried in the console log) when attribute coverage is near-zero across the whole squad.

**Effort estimate:** S

**Priority:** P2

---

### 11. Feature idea — incorporate real match statistics ("Moneyball") alongside attributes ([#12](https://github.com/laweh-dev/fm-save-copilot/issues/12))

**Problem / idea:** Role-fit is 100% attribute-based today. A stats-driven layer (goals/assists/output, defensive actions, etc.) alongside attributes was suggested as a complementary signal — particularly valuable when attribute data is unreliable (see Ticket 10).

**User quote / evidence:**
> "It would be neat to combine this with a stats-based, Moneyball style approach." — Reddit Thread #2

**Proposed fix:** Not actionable yet — needs a scoping conversation on what match stats FM actually exports reliably before any design work starts.

**Effort estimate:** L

**Priority:** P3

---

### 12. *(Internal finding, not from /feedback)* Tactical-impossibility flags can contradict the recommended formation ([#13](https://github.com/laweh-dev/fm-save-copilot/issues/13))

**Problem:** `roles.py::formation_viability()` picks the top formation purely by summing role scores across all 11 slots, checking each slot only against `CAPABLE_THRESHOLD` (60). `analyzer.py::_tactical_impossibilities()` separately flags e.g. "cannot play wing-backs" using a stricter `STRONG_THRESHOLD` (70), applied squad-wide. The two never cross-check each other, so a formation requiring wing-backs (e.g. 3-4-2-1) can still be recommended as the top formation while the squad is independently flagged as unable to field a strong wing-back.

**Evidence:** Raised directly in conversation on 2026-08-07, root-caused in the same session — not sourced from `/feedback`, flagged here for completeness since it's already fully diagnosed and ready to scope.

**Proposed fix:** Three options discussed, roughly cheapest to most correct: (a) penalize/disqualify a formation relying on a squad-wide-flagged weak role family; (b) raise `best_xi_for_formation`'s weakness bar to match `STRONG_THRESHOLD` for key role families (WB/DM); (c) compute tactical impossibilities after formation selection, scoped to the actual chosen XI, instead of two independent squad-wide passes.

**Effort estimate:** M

**Priority:** P1

---

## Suggested first batch (highest impact-to-effort)

1. Ticket 1 (Salary alias) — trivial fix, kills the single most-reported issue outright.
2. Ticket 2 (market matching position eligibility) — same pattern as a fix we already shipped once, high trust impact.
3. Ticket 6 (Colab traceback noise) — makes every other bug easier for users to self-diagnose and report clearly going forward.
4. Ticket 4 (budget affordability anchor) — small change, directly addresses a "the tool lied to me" trust issue.
