# FM Save Copilot

A CLI that reads a single FM24 squad HTML export and produces a Michael Edwards-style Director of Football briefing as a markdown report.

## Install

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
  --out report.md
```

Options:
- `--objective "..."` — one-line club objective. Optional; if omitted the DoF writes at an abstract level.
- `--formation "..."` — override formation. Optional; if omitted the analyzer identifies the best-supported shape.
- `--out PATH` — output file. Default `report.md`.
- `--config PATH` — config file. Default `config.yaml`.

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
