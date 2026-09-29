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
| L1 raw: `<site>/Site Report*.pdf` | Google Drive | you (download from VT) |
| Human input: `_comparison/manual_facts.csv` | Google Drive | you |
| Generated: `_comparison/combined_facts.csv` | Google Drive | this script |

## What is auto-extracted vs authored

- Auto (from L1): AI scores, and all demographics from the Site Report ring
  table (population, households, income, age bands, CAGR, daytime pop, $150k+ %,
  fitness centers).
- Authored (from `manual_facts.csv`): identity + lease economics + judgment that
  VT states ambiguously or not at all — `address, sf, gen, tier, open_mo,
  psf_ti, base_psf, nnn_psf`, the seven `placer_*` daily reads, the four
  `*_score` (1-7) values, and `co_tenants, notes`. The file's columns follow
  `MANUAL_PASSTHROUGH` in `build_facts.py`, which keeps the same order as
  `combined_facts.csv`; the build warns if the header drifts.
- Filled from the deal matrix: when `sf`, `base_psf`, `nnn_psf` or `psf_ti` is
  blank in `manual_facts.csv`, the build takes it from the site's
  highest-numbered `*Deal Matrix*.xlsx`, using the latest round that has a
  value. The manual value wins when both exist, and the build warns if they
  disagree, so a stale manual row shows up after each new counter.
- Computed (here): `total_rent`, `total_ti`, `gate_afford`, the four `flag_*`,
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
path (`drive_base` → `gdrive/private/ULC-personal/Development/Site Selection/Candidates`
via the repo symlink). Change behavior there, not in the code.

## Unit economics model per site

Each center's unit economics model is a copy of the current Baseline with only
its site cells changed, so the franchisor's assumptions stay identical across
sites and the results differ only by lease, tier and timing. The Baseline is an
unchanged copy of the franchisor's `ULC Unit Economic Model v.Sept26`, made with
`cp -X` and `chmod u+w`, with no local price overlay. When the franchisor issues
a new model, copy it over the Baseline, then run each site with `--rebuild`. `site_model.py`
writes those cells from the site's `combined_facts.csv` row and reads the
results back:

```bash
./.venv/bin/python site_model.py "SC Square"            # write, recalc, save, report
./.venv/bin/python site_model.py "SC Square" --dry-run  # print inputs + AppleScript only
```

The site name is the display name in `combined_facts.csv`, and it also titles
the copy, `ULC Unit Economic Model - <site>.xlsx` in `unit_model.models_dir`.
If the copy is missing, the script creates it from `unit_model.baseline` with
`cp -X`, which leaves Drive's item-id xattr behind. `--rebuild` first moves an
existing copy to `Archive/` with today's date in its name, for when a new
Baseline replaces the one the copy was built on.

The inputs are derived as follows:

- tier = `"Tier " + tier`
- start = `open_mo` minus 3 months, because the model's 3-Year IS treats its
  first three months as presales and `open_mo` is the opening month
- rent = `round(base_psf * sf / 12)` and NNN = `round(nnn_psf * sf / 12)`,
  with Python's half-to-even rounding, so SC Square's 10,860.5 becomes 10,860
- presales rent and NNN = zero or the full monthly amount, per site in
  `unit_model.presales_rent`
- deposit = the shared `unit_model.deposit`, 33,000
- net leasehold = `bo_net`

`unit_model.inputs` maps each input to its cells. Escalation stays the
Baseline's shared 3%, and rent abatement has no cell, so the script reports its
value, abated months times all-in rent, as upside outside the model.

Excel does the writing because openpyxl drops drawings, threaded comments and
dynamic-array metadata when it saves. The script opens the copy with `open -a`,
because AppleScript's `open workbook` silently fails on Drive paths. It then
sets calculation to manual before touching any cell, since a write under
automatic calc can crash Excel with AppleScript error -609. After the writes it
switches back to automatic, recalculates and saves. A target holding a formula
is left alone, such as `(PC) Inputs` B29 in v.Sept26, which points at
`(MSO) Inputs` B29. Finally openpyxl reads the cached values, checks that every
target holds the intended value, and reports EBITDA for the three model years
(C118:E118), peak cash (the minimum of row 128) and the payback month (I131).

The regression check reruns today's v.Jul3 copies on a scratch copy of the old
Baseline. SC Square used a 46,967 deposit, 2.75 times its all-in rent, so it
needs that override; Junction kept 33,000:

```bash
./.venv/bin/python site_model.py "SC Square" --baseline "<Archive>/ULC Unit Economic Model - Baseline v.Jul3.xlsx" \
  --out "<scratch>/ULC Unit Economic Model - SC Square.xlsx" --start-offset 0 --presales-rent full --deposit 46967
```

It reproduced both copies to the dollar on 2026-09-28. SC Square came out at
2028 EBITDA 912,996, 2029 EBITDA 1,034,998, peak cash -982,085 and payback in
month 17. Junction came out at 836,548, 1,013,740, -1,001,998 and month 18.

One model quirk affects results: NNN escalation in the 3-Year IS (row 105)
counts years from `YEAR(TODAY())`, not from the model start as rent does, so
the same inputs give different NNN when recalculated in a later calendar year.

## Spec & tests (start here if it breaks)

Rule: run the tests before committing any change to this tool, and keep them
green. The tests are the executable spec.

Hard gate (pre-commit hook): a tracked hook blocks any commit that touches this
tool if its tests fail. Git hooks live outside version control, so install once
per clone:

```bash
bash hooks/install.sh
```

`bash franchise/site-selection/hooks/install.sh` still works; it installs the
same repo-root dispatcher. The hook only runs this tool's tests when
`franchise/site-selection/` files are staged, so unrelated commits are
unaffected. Emergency bypass (discouraged): `git commit --no-verify`.

The contract is written down in three places, closest-to-code first:

1. This README (field ownership, formulas below) + `config.yaml` (the exact numbers).
2. `tests/test_build.py` and `tests/test_site_model.py` — the executable spec.
   They encode golden values from a real Site Report, every compute rule and
   the model runner's derivations, and run without Google Drive or Excel.
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
- Deal matrix: the latest round with a value wins per term, the
  highest-numbered file wins per site, and manual values beat matrix values.
- Model runner: the input derivations with SC Square and Junction as golden
  values, the start month wrapping into the prior year, the cell map, the
  generated AppleScript's order of operations and quoting, and the result
  reader on a small workbook built in the test.

Formulas (also enforced by the tests):

- `total_rent = round((base_psf + nnn_psf) * sf / 12)`
- `total_ti = round(psf_ti * sf)`
- `gate_afford`: `pass` if `total_rent <= afford_ceiling_hard`; `borderline` if within
  `afford_borderline_pct` over it; else `fail`; `TODO` if `total_rent` unknown.
- `placer_weekend_ratio = avg(Sat,Sun) / avg(Mon..Fri)`; `placer_pattern =
  weekend-spike` if ratio > `placer.weekend_spike_ratio`, else `uniform`.
- `composite = neighbor*w_n + customer*w_c + resid*w_r + visibility*w_v`.

If you change a threshold in `config.yaml` or a rule in the code, update the
matching assertion in `tests/test_build.py` so the spec stays honest.

Refreshing the fixture (only if VT's real layout legitimately changed):
re-extract a Site Report's text to `tests/fixtures/camden_report.txt` with
pdfplumber, then update the golden values in `TestParseReport`.

## Adding a new candidate

1. Create `Candidates/<slug>/` in Drive; drop in `Site Report*.pdf`.
2. Add the display name under `site_names` in `config.yaml` (keyed by `<slug>`).
3. Add a row to `manual_facts.csv` (identity, lease, co-tenants, notes; placer +
   scores when you have them).
4. Run `build_facts.py`; check the row and any `TODO`s.
