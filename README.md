# FM Save Copilot

Turn a Football Manager 2024 squad export into a **Director of Football briefing** — a written report that tells you what your squad can and can't do, who's overpaid, who to sell, and what profile of player to sign next. Written in the voice of a real football executive, backed by every attribute in your save.

No spreadsheets, no manual analysis. Export your squad from FM24, upload it, and get back a proper report with tables and charts you can open in any browser.

---

## Two ways to use it

| | Best for | What you need |
|---|---|---|
| **🌐 Browser (Colab)** | Everyone — no setup at all | A Google account |
| **💻 Your computer (CLI)** | People comfortable with Terminal | Python 3.10+ |

If you're not sure which to pick, use the browser option below.

---

## Option A: Run it in your browser (no install)

[![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/laweh-dev/fm-save-copilot/blob/main/colab/FM_Save_Copilot.ipynb)

1. Click the badge above. It opens a guided notebook in Google Colab (free, just needs a Google account).
2. Run each cell from top to bottom by clicking the ▶ button on the left of it.
3. When you get to "Upload your squad export," click the button and choose the file you exported in Step 1 below.
4. Pick your options from the dropdowns (tactical style, formation, budget, etc. — see [What you can configure](#what-you-can-configure)).
5. Click **Generate** — your report opens right in the notebook and downloads automatically.

That's it. Nothing to install, nothing to configure on your computer.

---

## Step 1: Export your squad (and optionally your league/market) from FM24

All options above need at least the squad file. We've done the fiddly part for you — this repo includes ready-made FM24 view files with every required column already set up, so you don't have to build a view by hand.

| File | What it's for |
|---|---|
| [`fm_views/Current Squad.fmf`](fm_views/Current%20Squad.fmf) | Your own squad — required |
| [`fm_views/Current League.fmf`](fm_views/Current%20League.fmf) | Every player in your division — optional, powers [league context](#what-you-can-configure). The same view/export also works as your **market** export (see below) — it's the same column format either way |

**To download a view file from GitHub:** click the file link above, then click the **Download raw file** button (or "⋮" → Download) on that page.

**To load it in FM24:**

1. Go to the **Squad** screen (for the squad view) or **Scouting → Player Search** / a league-wide search (for the league/market view).
2. Click the small menu icon above the column headers (usually near the current view's name — sometimes shown as "⋮" or a dropdown arrow).
3. Choose **Load View**, then browse to the `.fmf` file you downloaded.
4. The screen now shows every column the tool needs.

**To export it as HTML:**

1. With that view loaded, select all players — click one row then `Ctrl+A` (or `Cmd+A` on Mac), or right-click → **Select All**.
2. Right-click the selection → **Export** → **Web Page** (or use the game's Print option and choose Web Page as the format).
3. Save the file somewhere you'll remember — you'll upload or select it in the next step.

For **league context**: filter/search to show players across your whole division (not just your club) before exporting, so the export covers the opposition too.

For a **market export** (to power [Target Dossier](#what-you-can-configure), which names real transfer targets and replacement candidates): search more broadly — Scouting → Player Search across all the leagues you scout, or a saved shortlist — the wider the pool, the better the candidates it can surface. Same format as the league export, same `.fmf` view.

The exact menu wording varies slightly by FM version; if the `.fmf` files won't load, any recent guide to "loading a custom view in FM" or "exporting FM squad to HTML" online will get you to the same place, and you can build a view by hand instead — see [Required columns](#required-columns) below for the exact list needed.

---

## Option B: Run it on your computer (CLI)

For anyone comfortable with a terminal, or who wants to script it.

### Install

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Requires Python 3.10+.

### Run it

```
python -m fm_copilot squad.html --out report.html
```

That's the minimum — it'll produce a report immediately (see [Free mode vs full mode](#free-mode-vs-full-mode) below for what you get without an API key). Add options to tell it more about your situation:

```
python -m fm_copilot squad.html \
  --objective "PL survival, first season up" \
  --tactic "Gegenpress" \
  --league current-league.html \
  --market transfer-market.html \
  --transfer-budget "£15M" \
  --wage-budget "£45,000" \
  --out report.html
```

---

## What you can configure

Same options whether you're in the browser or the terminal — in Colab these are dropdowns and text boxes, on the CLI they're flags.

| What | Options | Optional? |
|---|---|---|
| **Objective** | Any one-line description, e.g. "PL survival, first season up" | Yes — the report writes more generally if skipped |
| **Formation** | `4-2-3-1` · `4-3-3` · `3-5-2` · `3-4-3` · `4-4-2` · `3-4-2-1`, or auto-detect | Yes — auto-detects your best-supported shape if skipped |
| **Tactical direction** | `Control Possession & High Press` · `Gegenpress` · `Low Block & Fast Counters` · `Low Block & Waste Time` · `Low Block & Direct Long Passing` · `Tiki-Taka` | Yes — skip it and the report just won't score players against a specific style |
| **League context** (`--league`) | Upload a second export of your division's players | Yes — needs a tactical direction to be set first |
| **Market context** (`--market`) | Upload a scouting/transfer-market export | Yes — unlocks Target Dossier (Section 12), the only place the report names real transfer targets and replacement candidates |
| **Transfer budget** (`--transfer-budget`) | e.g. `£15M` | Yes — without it, recruitment priorities show profiles without a spend ceiling |
| **Wage budget** (`--wage-budget`) | e.g. `£45,000` | Yes — independent of transfer budget; plenty of one and none of the other is normal |
| **Report type** | Free mode (tables only) or full narrative (needs an API key) | — |

**Tactical direction** scores every player on how well their attributes suit that style of play — a technically gifted midfielder might be great for Tiki-Taka but hopeless for a Gegenpress. **League context** takes that further: upload an export of your league's players (same format as your squad, exported the same way) and it'll tell you not just how good a player is in isolation, but how that compares to the actual standard of your division. **Market context** goes one step further again: upload a transfer-market export and the report will shortlist real, named candidates — both for your recruitment priorities and as replacement options for anyone flagged for exit — scored the same way as your own players and ranked by role-fit.

---

## Free mode vs full mode

You don't need an API key to get a report — the tool always gives you something useful:

- **Free mode** (no key needed): a full report with every table and chart, just without the written narrative. Deterministic — run it twice, get the same thing.
- **Full mode**: adds a proper written briefing in the voice of a Director of Football, citing your actual data throughout. Needs an [Anthropic API key](https://console.anthropic.com/) (a separate, paid API — not a Claude.ai subscription).

**In Colab:** add your key once via the 🔑 Secrets icon in the notebook's left sidebar (name it `ANTHROPIC_API_KEY`) — it's saved to your Google account, not the notebook, and works every future session.

**On the CLI:** copy `config.yaml.example` to `config.yaml` and paste your key in, or set it as an environment variable:

```
cp config.yaml.example config.yaml
```
```yaml
anthropic:
  api_key: sk-ant-...
  model: claude-sonnet-4-6
  max_tokens: 12000
```
```
export ANTHROPIC_API_KEY=sk-ant-...
```

`config.yaml` and `.env` are gitignored — never commit your API key.

---

## Required columns

The parser reads columns by name, so build your FM view with these included before exporting:

- **Name, Age, Position, Wage, Height** — the basics
- **All 47 attributes** — every Technical, Mental, and Physical attribute, plus all 11 Goalkeeping attributes (yes, even for outfield players — the columns just need to exist)

Nice to have but not required: Contract End, CA, PA, Value, Info, Personality, Nationality, and — for the **Squad Audit** section specifically — Apps, Mins, Actual Playing Time, Agreed Playing Time, Last Trans. Fee, and Rc Injury. All of these are already included in `fm_views/Current Squad.fmf`. FM's short column codes (`Pac`, `Wor`, `Tck`, etc.) are recognized automatically alongside the full names.

If a required column is missing, the tool tells you exactly which one before doing anything else. Missing optional columns just mean the section they power (e.g. Squad Audit) is skipped or shown as "not available" — the rest of the report is unaffected.

---

## What's in the report

Seven sections always, up to five more depending on what you provide:

1. Headline Verdict — the state of the squad in plain terms
2. The Shape — your best XI, drawn on a pitch, plus what formation actually suits your players
3. What This Squad Cannot Do — honest limitations, with the numbers behind them
4. Hidden Strengths and Exploitable Edges
5. The Wage Bill — who's worth it, who isn't
6. Decisive Players — who you can't afford to lose
7. Recruitment Priorities — profiles to target (plus a budget line and a looser fallback profile per priority, when you've set one)
8. Exits — who to sell and why, with a value-trend projection (rising/stable/declining) for each
9. What Good Looks Like — where the squad heads over 12-18 months
10. How We Compare to the League — *only if you set a tactical direction*
11. Squad Audit — *only if your export includes playing-time/purchase-value columns* — core/rotation/filler/saleable/exit tiers, value created, retention risks
12. Target Dossier — *only if you provide a market export* — real, named candidates against your recruitment priorities and any exit that leaves a genuine gap. **This is the only section that ever names a real market player** — every other section describes profiles, never a specific transfer target.

Delivered as a single `.html` file — tables, charts, everything self-contained, nothing else to install. Open it in any browser, or use the browser's Print function if you want a PDF.

---

## Known limitations

- Sections 7 (Recruitment) and 8 (Exits) always describe a *profile* or reasoning, never a named player — real transfer targets and replacement candidates only ever appear in Section 12, and only when you provide a market export.
- Role-fit and style-fit weightings are football-sensible judgment calls, not FM's exact internal formulas.
- Status flags (injured, transfer-listed, etc.) and contract-cliff detection rely on text matching against your export — non-English saves may not be recognized.
- League-context benchmarking applies to tactical style-fit only, not the underlying role-fit scores.
- Value-trend projections (Section 8) need enough same-age players in your market export to be confident — without `--market`, most projections will honestly show "insufficient data" rather than guess.
- Charts are static images (no hover/interactivity) — this is a document to read or print, not a live dashboard.

---

## Where this is headed

This tool is scoped against a full Sporting Director role, not just squad analysis — see `SPORTING_DIRECTOR_ROLE.md` for the source vision, `VISION.md` for the current scorecard against it, and `DATA_REQUIREMENTS.md` for exactly what FM data each piece still needs.
