# FM Save Copilot

A CLI that reads a single FM24 squad HTML export and produces a Michael Edwards-style Director of Football briefing as a styled HTML report (tables and charts, no extra software needed to view it — just a browser).

## Run it in your browser (no install)

[![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/laweh-dev/fm-save-copilot/blob/main/colab/FM_Save_Copilot.ipynb)

Upload your squad export, pick your options from dropdowns, and download the report — no Python, no terminal. See `colab/FM_Save_Copilot.ipynb`.

## Install (CLI)

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Requires Python 3.10+.

## Config

Copy the example config and add your Anthropic API key:

```
cp config.yaml.example config.yaml
```

```yaml
anthropic:
  api_key: sk-ant-...
  model: claude-sonnet-4-6
  max_tokens: 12000
```

Or set the key as an environment variable instead:

```
export ANTHROPIC_API_KEY=sk-ant-...
```

Key resolution order (first hit wins): `--config` path → `./config.yaml` → `ANTHROPIC_API_KEY` env var → `.env` file. If none are found, the tool runs in **free mode** (see below) — it never leaves you with nothing.

`config.yaml` and `.env` are gitignored. Never commit your API key.

## How to export the squad HTML from FM24

In-game: go to your **Squad** screen, set it to the view with the columns you want (see below), then use the game's **Print** / **Export** option and choose **Web Page** to save an HTML file. Any up-to-date community guide on exporting FM squad views to HTML/print will get you the same result — the exact menu wording varies slightly by FM version.

## Required and recommended columns

The parser maps columns by header name, not position, so build a custom squad view with these columns before exporting.

**Required** (missing any → hard fail with the column named):
- Name, Age, Position, Wage, Height (or "Hgt")
- All 47 individual attributes: every Technical, Mental, and Physical attribute, plus all 11 Goalkeeping attributes (goalkeeping columns must be present even though only goalkeepers' values matter).

**Recommended** (missing → warning, parsing continues):
- Contract End (or "Expires"), CA, PA, Value (or "Transfer Value"), Info, Personality, Nat (nationality)

FM's short column headers ("Pac", "Wor", "Tck", etc.) are recognized alongside the full attribute names.

## Example command

```
python -m fm_copilot squad.html \
  --objective "PL survival, first season up" \
  --formation "4-2-3-1 mid-block" \
  --out report.html
```

Options:
- `--objective "..."` — one-line club objective. Optional; if omitted the DoF writes at an abstract level.
- `--formation "..."` — override formation. Optional; if omitted the analyzer identifies the best-supported shape.
- `--tactic "..."` — tactical direction. Optional; if omitted no style-fit is computed. One of: `Control Possession & High Press`, `Gegenpress`, `Low Block & Fast Counters`, `Low Block & Waste Time`, `Low Block & Direct Long Passing`, `Tiki-Taka` (matched case-insensitively; common variants like "gegen press" also work). An unrecognized value fails immediately with the valid list, before the squad file is even read.
- `--league PATH` — path to a current-league HTML export (same format as the squad export, plus `Club` and `Apps` columns). Recalibrates style-fit against the actual standard of opposition in your league. **Requires `--tactic`** — fails immediately if given without it.
- `--out PATH` — output file. **Default `report.html`** — a styled report with tables and charts, open it in any browser. Pass a `.md` path (e.g. `--out report.md`) for the plain-markdown output instead.
- `--config PATH` — config file. Default `config.yaml`.

## The HTML report

The default output is a single self-contained `.html` file — no server, no extra install, nothing to configure. Open it in any browser. It includes:
- A styled version of every section, with real tables instead of raw markdown.
- A handful of charts where a picture clarifies faster than a table: formation viability, style-fit distribution (when `--tactic` is set), wage cost by position, age profile, and an absolute-vs-league-relative comparison (when `--league` is set). All charts are hand-built inline SVG — no charting library, no external requests, nothing that can fail to load.
- A jump-to-section nav at the top, and print-friendly styling if you want a PDF or paper copy — just use your browser's Print function.

The `.md` output still exists (pass `--out report.md`) and is byte-identical to what earlier versions produced, if you want the plain text for pasting elsewhere.

## Tactical direction & style-fit

When `--tactic` is set, every player gets a second score alongside role-fit: how well their attribute profile suits that playing style, scored 0-100 and banded into "Does very well" / "Does well" / "Doesn't do well" / "Doesn't work at all". This is position-aware — the same style demands different things of different positions (e.g. under Low Block & Fast Counters, defenders need positional discipline, attackers need raw pace), so a player can be a great fit for their role and a poor fit for the chosen style at the same time. The DoF report weaves this into Section 2 (Shape) and Section 7 (Recruitment) when present; omitting `--tactic` leaves the report unchanged from v0.

## League context

When `--league` is also set, style-fit scores get a second, contextual reading: each squad player's score is converted into a **weighted percentile rank** against every player in the league who plays the same position group, then re-expressed using the same tier language. "Does very well" in isolation might turn out to be merely "Does well" once benchmarked against a stronger league, or vice versa.

This is statistics only — **no opposition or league player is ever named in the report.** League data exists purely to recalibrate what a tier means for this standard of football; it's never a source of specific signing targets, which stays true to the "recruitment is profile-based, not named-player-based" rule from v0.

The benchmark weights every league player by appearances (starts count more than sub appearances; nobody is hard-excluded), so it self-corrects for pre-season automatically: if apps are near-zero league-wide, the weighting flattens out and the benchmark falls back to an unweighted read of the whole population, with a `[league] WARNING` printed to say so.

## Free mode

If no API key is found anywhere in the resolution order, the tool still writes a full report — just without DoF prose. Free mode renders every section of the analyzer's output directly as markdown tables and one-line captions instead of narrative paragraphs. It's deterministic: same input, same output, every time.

## v0 known limitations

- Squad-only. No market file input, no named market target recommendations — recruitment is profile-based (role + attribute floors), never a shortlist of real players.
- Role fit weights are internally hardcoded in `roles.py`, football-sensible but not identical to FM's internal formulas.
- Value ranges are parsed only from the standard "£X - £Y" / "£XM" formats FM exports.
- Status flags (injured, transfer-listed, etc.) are detected by substring match against the Info column — non-English exports will miss them.
- Contract cliff detection is a loose year-substring match, not real date arithmetic.
- No transfer history logging.
- No five-file context system — planned for v1.
- Style-fit weight tables (`tactics.py`) are hardcoded judgment calls, same caveat as role-fit weights.
- League-context benchmarking recalibrates style-fit only, not role-fit — the 28 FM roles from v0 are still evaluated in isolation regardless of `--league`.
- League-context position grouping is the same coarse 8-group classifier used for style-fit (`tactics.classify_position_group`), not exact FM role matching.
- The markdown-to-HTML conversion (`html_report.py`) is hand-rolled against the specific markdown subset this tool produces (headers, bullet lists, pipe tables, bold, horizontal rules) — it isn't a general-purpose markdown renderer.
- Charts are static SVG, not interactive (no tooltips/hover) — this is a generated document meant to be read or printed, not a dashboard.
