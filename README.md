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
4. Pick your options from the dropdowns (tactical style, formation, etc. — see [What you can configure](#what-you-can-configure)).
5. Click **Generate** — your report opens right in the notebook and downloads automatically.

That's it. Nothing to install, nothing to configure on your computer.

---

## Step 1: Export your squad from FM24

Both options above need this file first.

1. Open your save and go to the **Squad** screen.
2. Right-click the column headers and build (or load) a view that includes every attribute column — see [Required columns](#required-columns) below for the exact list. If you're not sure, add *every* attribute column you can find; extra columns don't hurt.
3. Use the game's **Print** option (usually a printer icon) and choose **Web Page** as the format.
4. Save the file somewhere you'll remember — you'll upload or select it in the next step.

The exact menu wording varies slightly by FM version; any recent guide to "exporting FM squad to HTML" online will get you to the same place.

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
  --out report.html
```

---

## What you can configure

Same options whether you're in the browser or the terminal — in Colab these are dropdowns, on the CLI they're flags.

| What | Options | Optional? |
|---|---|---|
| **Objective** | Any one-line description, e.g. "PL survival, first season up" | Yes — the report writes more generally if skipped |
| **Formation** | `4-2-3-1` · `4-3-3` · `3-5-2` · `3-4-3` · `4-4-2` · `3-4-2-1`, or auto-detect | Yes — auto-detects your best-supported shape if skipped |
| **Tactical direction** | `Control Possession & High Press` · `Gegenpress` · `Low Block & Fast Counters` · `Low Block & Waste Time` · `Low Block & Direct Long Passing` · `Tiki-Taka` | Yes — skip it and the report just won't score players against a specific style |
| **League context** | Upload a second export of your division's players | Yes — needs a tactical direction to be set first |
| **Report type** | Free mode (tables only) or full narrative (needs an API key) | — |

**Tactical direction** scores every player on how well their attributes suit that style of play — a technically gifted midfielder might be great for Tiki-Taka but hopeless for a Gegenpress. **League context** takes that further: upload an export of your league's players (same format as your squad, exported the same way) and it'll tell you not just how good a player is in isolation, but how that compares to the actual standard of your division.

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

Nice to have but not required: Contract End, CA, PA, Value, Info, Personality, Nationality. FM's short column codes (`Pac`, `Wor`, `Tck`, etc.) are recognized automatically alongside the full names.

If a required column is missing, the tool tells you exactly which one before doing anything else.

---

## What's in the report

Nine sections always, a tenth if you set a tactical direction:

1. Headline Verdict — the state of the squad in plain terms
2. The Shape — your best XI, drawn on a pitch, plus what formation actually suits your players
3. What This Squad Cannot Do — honest limitations, with the numbers behind them
4. Hidden Strengths and Exploitable Edges
5. The Wage Bill — who's worth it, who isn't
6. Decisive Players — who you can't afford to lose
7. Recruitment Priorities — profiles to target, never named market players
8. Exits — who to sell and why
9. What Good Looks Like — where the squad heads over 12-18 months
10. How We Compare to the League — *(only if you set a tactical direction)*

Delivered as a single `.html` file — tables, charts, everything self-contained, nothing else to install. Open it in any browser, or use the browser's Print function if you want a PDF.

---

## Known limitations

- Squad-only recruitment advice — Section 7 always describes a *profile* (role + attribute floors), never a real player from the transfer market.
- Role-fit and style-fit weightings are football-sensible judgment calls, not FM's exact internal formulas.
- Status flags (injured, transfer-listed, etc.) and contract-cliff detection rely on text matching against your export — non-English saves may not be recognized.
- League-context benchmarking applies to tactical style-fit only, not the underlying role-fit scores.
- Charts are static images (no hover/interactivity) — this is a document to read or print, not a live dashboard.
