# Site selection build (lever 2)

Config-driven builder for the ULC site-selection comparison workbook. Reads
VisionTrack L1 files + a human-authored `manual_facts.csv`, computes the derived
columns, and writes `combined_facts.csv`. This script is the **only** writer of
`combined_facts.csv`.

See the method + design note in the vault:
`Agent/Workflows/Site Selection Scoring.md` -> "Build automation (lever 2)".

## Layer boundaries (one writer each)

| Layer | Lives in | Written by |
| --- | --- | --- |
| Code + config (this folder) | git (`personal-os`) | you / agent |
| L1 raw: `<site>/_page.md`, `<site>/Site Report*.pdf` | Google Drive | you (paste/download from VT) |
| Human input: `_comparison/manual_facts.csv` | Google Drive | you |
| Generated: `_comparison/combined_facts.csv` | Google Drive | this script |

## What is auto-extracted vs authored

- Auto (from L1): AI scores, and all demographics from the Site Report ring
  table (population, households, income, age bands, CAGR, daytime pop, $150k+ %,
  fitness centers).
- Authored (from `manual_facts.csv`): identity + lease economics + judgment that
  VT states ambiguously or not at all — `address, territory, sf_target,
  base_psf, nnn_psf, generation, co_tenants, notes`, the seven `placer_*` daily
  reads, and the four `score_*` (1-7) values.
- Computed (here): `allin_month`, `gate_afford`, the four `flag_*`,
  `placer_weekend_ratio`, `placer_pattern`, `composite`.

A field the parser can't find is written as `TODO` (demographics) or left blank
(placer/scores), so gaps are visible rather than silently wrong.

## Setup

```bash
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
```

## Run

```bash
./.venv/bin/python build_facts.py            # writes combined_facts.csv
./.venv/bin/python build_facts.py --dry-run  # print to stdout, write nothing
```

`config.yaml` is the authoritative home for the tunable numbers (income/pop/age
cutoffs, affordability ceiling, the four weights, ring priority) and the Drive
path. Change behavior there, not in the code. Update `drive_base` per machine.

## Adding a new candidate

1. Create `Candidates/<slug>/` in Drive; drop in `_page.md` and `Site Report*.pdf`.
2. Add the display name under `site_names` in `config.yaml` (keyed by `<slug>`).
3. Add a row to `manual_facts.csv` (identity, lease, co-tenants, notes; placer +
   scores when you have them).
4. Run `build_facts.py`; check the row and any `TODO`s.
