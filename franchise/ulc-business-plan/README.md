# ULC lender business plan merge

Merges yellow-highlight inputs from the staging markdown into the ULC sample business plan template.

## How the plan is built

See vault note [[ULC Business Plan]] for the full picture (three source files → staging → template).

## Files (Google Drive `Finance/Funding Plan/`)

| File | Role |
| --- | --- |
| `ULC_FDD2026_Facts.md` | FDD capital and fees |
| `ULC_Economic_Projections.md` | Operating projections |
| `ULC_Funding_Plan_Details.md` | Manual package facts |
| `ULC_Business_Plan_Staging.md` | Temporary yellow-field assembly (merge input) |
| `ULC_Sample Business Plan.docx` | Read-only template |
| `Chaudhuri_ULC_Site1_Business_Plan.docx` | Generated output |

## Workflow

1. Refresh the three source files as needed.
2. Assemble `ULC_Business_Plan_Staging.md` from those sources.
3. Run merge (from repo root):

```bash
python3 franchise/ulc-business-plan/merge_business_plan.py
```

4. Open output in Word; confirm yellow fields filled, white text unchanged.
5. Export dated PDF → Brickhouse Dropbox → email Katelyn.

## Rules

- **Yellow-highlighted runs** are replaced from the placeholder map.
- White text changes only for the exact phrases in `WHITE_TEXT_MAP`: `[XX]%` from `equity_percent` and "who brings experience" from `owner_experience_clause`, and the demographics bracket from `market_demographics`. Each phrase must sit inside one run.
- Other non-yellow placeholders, such as the Excel template name, stay as-is.
- Template file is never modified; output is a fresh copy each run.
- Merge copies the template docx and patches yellow `w:t` nodes; emptied split runs are removed.

## Tests

```bash
python3 -m unittest discover -s franchise/ulc-business-plan/tests
```

## Vault cross-link

Workflow doc: `vault/Agent/Workflows/ULC Business Plan.md`
