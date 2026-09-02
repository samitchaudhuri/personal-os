#!/usr/bin/env python3
"""Fill a signed-ready Capital Contribution PDF from a ledger .xlsx row.

The Capital Contributions to LLC Agreement template (a fillable PDF form
from northwestregisteredagent.com) asks for the same numbers that are
already sitting in the entity's membership ledger .xlsx: prior member
valuations/percentages, the new contribution(s), and the resulting
valuations/percentages. Typing those into the paper form by hand duplicates
what's already in the spreadsheet and invites the two to drift.

This script treats the .xlsx Capital/Transfers sheets as the source of
truth: it picks the target contribution (the row whose Doc cell is still
"pending", or --date), replays the ledger's balance/ownership math up to
that point, and writes the before/contribution/after tables into the PDF's
form fields. Signature and Date fields are left blank -- those still get
filled by hand when the form is printed and signed.

Requires: openpyxl, pypdf (pip install openpyxl pypdf)

Example:
  python scripts/fill_capital_contribution.py --entity sustain
  python scripts/fill_capital_contribution.py \\
    --xlsx "<dir>/MSC_SUSTAIN_MEMBERSHIP_LEDGER.xlsx" \\
    --template "<dir>/MSC_SUSTAIN_CAPITAL_CONTRIBUTION_TEMPLATE_2026-08-31.pdf" \\
    --output "<dir>/MSC_SUSTAIN_CAPITAL_CONTRIBUTION_2026-08-31.pdf" \\
    --name "MSC Sustain LLC" --state California --formed 2026-08-14
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

try:
    import openpyxl
except ImportError:
    print("fill_capital_contribution.py requires openpyxl: pip install openpyxl", file=sys.stderr)
    sys.exit(1)

try:
    from pypdf import PdfReader, PdfWriter
except ImportError:
    print("fill_capital_contribution.py requires pypdf: pip install pypdf", file=sys.stderr)
    sys.exit(1)

# Reached via personal-os/gdrive (repo symlink) rather than the absolute
# CloudStorage path, so this works across machines/clones without editing.
GOV_DIR = (
    Path(__file__).resolve().parent.parent
    / "gdrive" / "private" / "ULC-personal" / "Governance" / "Entity Structure" / "Organizational Meeting"
)

# Per-entity facts that don't live in the ledger .xlsx (from the CA Articles
# of Organization, both filed 2026-08-14).
ENTITIES = {
    "holdings": {
        "folder": "MSC Holdings",
        "ledger_stem": "MSC_HOLDINGS_MEMBERSHIP_LEDGER",
        "template_stem": "MSC_HOLDINGS_CAPITAL_CONTRIBUTION_TEMPLATE_2026-08-31",
        "name": "MSC Holdings LLC",
        "state": "California",
        "formed": date(2026, 8, 14),
    },
    "sustain": {
        "folder": "MSC Sustain",
        "ledger_stem": "MSC_SUSTAIN_MEMBERSHIP_LEDGER",
        "template_stem": "MSC_SUSTAIN_CAPITAL_CONTRIBUTION_TEMPLATE_2026-08-31",
        "name": "MSC Sustain LLC",
        "state": "California",
        "formed": date(2026, 8, 14),
    },
}

# Form field names, in template layout order (northwestregisteredagent.com
# "LLC Add'l Capital Contribution" template). Determined by reading the
# PDF's AcroForm field rects. Signature/Date columns in the final table have
# no fields -- they're blank lines filled by hand at signing.
FIELD_ENTITY_NAME = "Text Field"
FIELD_STATE = "Text Field_1"
FIELD_FORMED_DATE = "Text Field_2"
FIELD_DAY, FIELD_MONTH, FIELD_YEAR = "Text Field_6", "Text Field_7", "Text Field_8"

BEFORE_ROWS = [
    ("Text Field_3", "Text Field_4", "Text Field_5"),
    ("Text Field_3_1", "Text Field_4_1", "Text Field_5_1"),
    ("Text Field_3_2", "Text Field_4_2", "Text Field_5_2"),
    ("Text Field_3_3", "Text Field_4_3", "Text Field_5_3"),
    ("Text Field_3_4", "Text Field_4_4", "Text Field_5_4"),
]
CONTRIBUTION_ROWS = [
    ("Text Field_3_5", "Text Field_9"),
    ("Text Field_3_6", "Text Field_9_1"),
    ("Text Field_3_7", "Text Field_9_2"),
    ("Text Field_3_8", "Text Field_9_3"),
    ("Text Field_3_9", "Text Field_9_4"),
]
AFTER_ROWS = [
    ("Text Field_10", "Text Field_11", "Text Field_12"),
    ("Text Field_10_1", "Text Field_11_1", "Text Field_12_1"),
    ("Text Field_10_2", "Text Field_11_2", "Text Field_12_2"),
    ("Text Field_10_3", "Text Field_11_3", "Text Field_12_3"),
    ("Text Field_10_4", "Text Field_11_4", "Text Field_12_4"),
]

MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def fmt_money(n: float) -> str:
    sign = "-" if n < 0 else ""
    return f"{sign}${abs(n):,.0f}"


def fmt_pct(n: float) -> str:
    return f"{n:.1f}%".replace(".0%", "%")


def fmt_long_date(d: date) -> str:
    return f"{MONTH_NAMES[d.month - 1]} {d.day}, {d.year}"


def to_date(val) -> date:
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    return datetime.strptime(str(val), "%Y-%m-%d").date()


def read_rows(ws, expected_cols: int) -> list[tuple]:
    rows = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        row = row[:expected_cols]
        if all(c is None for c in row):
            continue
        rows.append(row)
    return rows


def is_credit(typ) -> bool:
    t = str(typ).strip().lower()
    return t.startswith("contrib") or t == "formation"


def balances_before(capital_rows: list[tuple], before_date: date) -> dict[str, float]:
    balances: dict[str, float] = {}
    for dt, typ, member, amount, _doc, _notes in capital_rows:
        if to_date(dt) >= before_date:
            continue
        amount = float(amount or 0)
        signed = amount if is_credit(typ) else -amount
        balances[member] = balances.get(member, 0.0) + signed
    return balances


def ownership_as_of(transfer_rows: list[tuple], as_of: date) -> dict[str, float]:
    ownership: dict[str, float] = {}
    for dt, frm, to, pct, _doc, _notes in transfer_rows:
        if to_date(dt) > as_of:
            continue
        pct = float(pct or 0)
        if frm:
            ownership[frm] = ownership.get(frm, 0.0) - pct
        ownership[to] = ownership.get(to, 0.0) + pct
    return ownership


def find_target_date(capital_rows: list[tuple], explicit: date | None) -> date:
    if explicit:
        return explicit
    pending = [
        to_date(dt) for dt, _typ, _member, _amount, doc, _notes in capital_rows
        if str(doc or "").strip().lower().startswith("pending")
    ]
    if not pending:
        raise ValueError(
            "No Capital row has a 'pending' Doc cell and no --date was given -- "
            "pass --date YYYY-MM-DD for the contribution to fill."
        )
    return max(pending)


def build_fields(entity: dict, capital_rows: list[tuple], transfer_rows: list[tuple], target_date: date) -> dict[str, str]:
    target_rows = [
        r for r in capital_rows
        if to_date(r[0]) == target_date and str(r[1]).strip().lower().startswith("contrib")
    ]
    if not target_rows:
        raise ValueError(f"No Contribution row dated {target_date} found in the Capital sheet.")
    if len(target_rows) > len(CONTRIBUTION_ROWS):
        raise ValueError(f"{len(target_rows)} contribution rows on {target_date}, template only has {len(CONTRIBUTION_ROWS)}.")

    before = balances_before(capital_rows, target_date)
    ownership = ownership_as_of(transfer_rows, target_date)

    contributions: dict[str, float] = {}
    for _dt, _typ, member, amount, _doc, _notes in target_rows:
        contributions[member] = contributions.get(member, 0.0) + float(amount or 0)

    members: list[str] = []
    for m in list(before) + list(contributions):
        if m not in members:
            members.append(m)
    if len(members) > len(BEFORE_ROWS):
        raise ValueError(f"{len(members)} members involved, template only has {len(BEFORE_ROWS)} rows.")

    after = {m: before.get(m, 0.0) + contributions.get(m, 0.0) for m in members}

    fields = {
        FIELD_ENTITY_NAME: entity["name"],
        FIELD_STATE: entity["state"],
        FIELD_FORMED_DATE: fmt_long_date(entity["formed"]),
        FIELD_DAY: str(target_date.day),
        FIELD_MONTH: MONTH_NAMES[target_date.month - 1],
        FIELD_YEAR: f"{target_date.year % 100:02d}",
    }
    for (name_f, val_f, pct_f), member in zip(BEFORE_ROWS, members):
        fields[name_f] = member
        fields[val_f] = fmt_money(before.get(member, 0.0))
        fields[pct_f] = fmt_pct(ownership.get(member, 0.0))
    for (member_f, contrib_f), (member, amount) in zip(CONTRIBUTION_ROWS, contributions.items()):
        fields[member_f] = member
        fields[contrib_f] = fmt_money(amount)
    for (name_f, val_f, pct_f), member in zip(AFTER_ROWS, members):
        fields[name_f] = member
        fields[val_f] = fmt_money(after[member])
        fields[pct_f] = fmt_pct(ownership.get(member, 0.0))

    return fields


def fill_pdf(template_path: Path, output_path: Path, fields: dict[str, str]) -> None:
    reader = PdfReader(template_path)
    writer = PdfWriter()
    writer.append(reader)
    writer.update_page_form_field_values(writer.pages[0], fields, auto_regenerate=False)
    with open(output_path, "wb") as f:
        writer.write(f)
    print(f"Wrote {output_path}")
    print("Signature and Date fields are blank -- print, sign, and re-save at the same path.")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--entity", choices=sorted(ENTITIES), help="Use default gdrive paths/facts for this entity")
    p.add_argument("--xlsx", type=Path, help="Ledger .xlsx source")
    p.add_argument("--template", type=Path, help="Blank Capital Contribution template .pdf")
    p.add_argument("--output", type=Path, help="Filled .pdf to write")
    p.add_argument("--date", help="Contribution date YYYY-MM-DD (default: the 'pending' row's date)")
    p.add_argument("--name", help="Entity legal name (overrides --entity default)")
    p.add_argument("--state", help="State of formation (overrides --entity default)")
    p.add_argument("--formed", help="Formation date YYYY-MM-DD (overrides --entity default)")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    entity = dict(ENTITIES[args.entity]) if args.entity else {}
    if args.entity:
        entity_dir = GOV_DIR / entity["folder"]
        xlsx = args.xlsx or entity_dir / f"{entity['ledger_stem']}.xlsx"
        template = args.template or entity_dir / f"{entity['template_stem']}.pdf"
    else:
        xlsx, template = args.xlsx, args.template
    if args.name:
        entity["name"] = args.name
    if args.state:
        entity["state"] = args.state
    if args.formed:
        entity["formed"] = datetime.strptime(args.formed, "%Y-%m-%d").date()

    if not xlsx or not template:
        print("Pass --entity, or both --xlsx and --template (plus --name/--state/--formed).", file=sys.stderr)
        sys.exit(1)
    if not all(k in entity for k in ("name", "state", "formed")):
        print("Missing entity facts -- pass --entity or all of --name/--state/--formed.", file=sys.stderr)
        sys.exit(1)
    if not xlsx.exists():
        print(f"Missing xlsx: {xlsx}", file=sys.stderr)
        sys.exit(1)
    if not template.exists():
        print(f"Missing template: {template}", file=sys.stderr)
        sys.exit(1)

    wb = openpyxl.load_workbook(xlsx, data_only=True)
    capital_rows = read_rows(wb["Capital"], 6)
    transfer_rows = read_rows(wb["Transfers"], 6)

    explicit_date = datetime.strptime(args.date, "%Y-%m-%d").date() if args.date else None
    try:
        target_date = find_target_date(capital_rows, explicit_date)
        fields = build_fields(entity, capital_rows, transfer_rows, target_date)
    except ValueError as e:
        print(e, file=sys.stderr)
        sys.exit(1)

    if args.output:
        output = args.output
    else:
        stem = template.stem.split("_TEMPLATE")[0]
        output = template.parent / f"{stem}_{target_date}.pdf"

    fill_pdf(template, output, fields)


if __name__ == "__main__":
    main()
