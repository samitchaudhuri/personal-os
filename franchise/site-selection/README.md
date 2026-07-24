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

## Spec & tests (start here if it breaks)

Rule: run the tests before committing any change to this tool, and keep them
green. The tests are the executable spec.

Hard gate (pre-commit hook): a tracked hook blocks any commit that touches this
tool if its tests fail. Git hooks live outside version control, so install once
per clone:

```bash
bash franchise/site-selection/hooks/install.sh
```

The hook (`hooks/pre-commit`) only runs when `franchise/site-selection/` files
are staged, so unrelated commits are unaffected. Emergency bypass (discouraged):
`git commit --no-verify`.

The contract is written down in three places, closest-to-code first:

1. This README (field ownership, formulas below) + `config.yaml` (the exact numbers).
2. `tests/test_build.py` — the executable spec. It encodes golden values from a
   real Site Report and every compute rule, and runs without Google Drive.
3. Vault `Agent/Workflows/Site Selection Scoring.md` -> "Build automation" for
   the why/design.

Run the tests:

```bash
./.venv/bin/python -m unittest discover -s tests -v
```

What they pin down:

- Parser (`parse_report_text`) against `tests/fixtures/camden_report.txt`, a
  captured VT Site Report. If VisionTrack changes their PDF layout or a
  dependency drifts, the failing test names the exact field that broke.
- Compute rules: gate boundaries (`pass` <= afford_ceiling_hard, currently
  17000; `borderline` <= +10%; else `fail`; `TODO` when inputs missing), the
  four flags, placer weekend ratio/pattern, composite weighting, and that the
  weights sum to 1.0. `afford_preferred` (12500) and `afford_comfortable`
  (10000) are informational bands for reports, not gate cutoffs.

Formulas (also enforced by the tests):

- `allin_month = round((base_psf + nnn_psf) * sf_target / 12)`
- `gate_afford`: `pass` if `allin <= afford_ceiling_hard`; `borderline` if within
  `afford_borderline_pct` over it; else `fail`; `TODO` if `allin` unknown.
- `placer_weekend_ratio = avg(Sat,Sun) / avg(Mon..Fri)`; `placer_pattern =
  weekend-spike` if ratio > `placer.weekend_spike_ratio`, else `uniform`.
- `composite = neighbor*w_n + customer*w_c + resid*w_r + visibility*w_v`.

If you change a threshold in `config.yaml` or a rule in the code, update the
matching assertion in `tests/test_build.py` so the spec stays honest.

Refreshing the fixture (only if VT's real layout legitimately changed):
re-extract a Site Report's text to `tests/fixtures/camden_report.txt` with
pdfplumber, then update the golden values in `TestParseReport`.

## Adding a new candidate

1. Create `Candidates/<slug>/` in Drive; drop in `_page.md` and `Site Report*.pdf`.
2. Add the display name under `site_names` in `config.yaml` (keyed by `<slug>`).
3. Add a row to `manual_facts.csv` (identity, lease, co-tenants, notes; placer +
   scores when you have them).
4. Run `build_facts.py`; check the row and any `TODO`s.
