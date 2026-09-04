#!/usr/bin/env python3
"""Regenerate a membership-interest ledger PDF from its .xlsx source.

Manual entry into a table is error-prone, especially the computed columns
(running capital balance, current ownership %). This script keeps those
out of the spreadsheet entirely: the .xlsx holds only raw transaction rows
(who, when, how much), and this script derives the running balance and
ownership snapshot and lays them out in a PDF for the entity's minute-book
binder — a binder Craig (and eventually a lender/buyer's diligence team)
reads, so the PDF carries only the ledger itself: entity/formation info,
sole member and ownership %, current ownership, and capital transactions.
No maintainer-facing content (how to log a transaction, open items) goes
in it — that lives in the runbook instead.

Each entity's .xlsx has two sheets:

  Capital   — Date | Type (Contribution/Distribution) | Member | Amount | Doc | Notes
              One row per cash/property transfer between the LLC and a
              member. Running balance is computed here, not typed in.

  Transfers — Date | From Member | To Member | Percent | Doc | Notes
              One row per change in who owns what share. The first row is
              always the formation grant (From Member blank, To Member =
              the sole member, Percent = 100). Current ownership is the
              cumulative result of this sheet, not typed in.

Requires: openpyxl, reportlab — see scripts/requirements.txt; run via scripts/.venv
  (python3 -m venv scripts/.venv && scripts/.venv/bin/pip install -r scripts/requirements.txt)

Example:
  python scripts/build_membership_ledger.py --entity holdings
  python scripts/build_membership_ledger.py --all
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path
from xml.sax.saxutils import escape

try:
    import openpyxl
except ImportError:
    print("build_membership_ledger.py requires openpyxl: pip install openpyxl", file=sys.stderr)
    sys.exit(1)

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import landscape, letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
except ImportError:
    print("build_membership_ledger.py requires reportlab: pip install reportlab", file=sys.stderr)
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
        "stem": "MSC_HOLDINGS_MEMBERSHIP_LEDGER",
        "name": "MSC Holdings LLC",
        "state": "California",
        "articles": "B20260371831",
        "formed": date(2026, 8, 14),
        "sole_member": "Samit &amp; Mousumi Das Chaudhuri Living Trust",
        "sole_member_note": "acting through trustees Samit Chaudhuri and Mousumi Das Chaudhuri",
    },
    "sustain": {
        "folder": "MSC Sustain",
        "stem": "MSC_SUSTAIN_MEMBERSHIP_LEDGER",
        "name": "MSC Sustain LLC",
        "state": "California",
        "articles": "B20260371824",
        "formed": date(2026, 8, 14),
        "sole_member": "MSC Holdings LLC",
        "sole_member_note": (
            "itself owned 100% by the Samit &amp; Mousumi Das Chaudhuri Living Trust; "
            "trustees Samit Chaudhuri and Mousumi Das Chaudhuri act for it as this entity's member"
        ),
    },
}


def fmt_date(val) -> str:
    if val is None:
        return ""
    if isinstance(val, (datetime, date)):
        return val.strftime("%Y-%m-%d")
    return str(val)


def fmt_money(n) -> str:
    if n is None or n == "":
        return "$0"
    sign = "-" if float(n) < 0 else ""
    return f"{sign}${abs(float(n)):,.0f}"


def fmt_pct(n) -> str:
    if n is None:
        return ""
    n = float(n)
    return f"{n:.1f}%".replace(".0%", "%")


def read_rows(ws, expected_cols: int) -> list[tuple]:
    rows = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        row = row[:expected_cols]
        if all(c is None for c in row):
            continue
        rows.append(row)
    return rows


def compute_capital(rows: list[tuple]) -> tuple[list[list[str]], float]:
    """Returns (table rows incl. header, final balance)."""
    header = ["#", "Date", "Type", "Member", "Amount", "Balance", "Supporting document", "Notes"]
    table = [header]
    balance = 0.0
    for i, (dt, typ, member, amount, doc, notes) in enumerate(rows, start=1):
        amount = float(amount or 0)
        signed = amount if str(typ).strip().lower().startswith("contrib") or str(typ).strip().lower() == "formation" else -amount
        balance += signed
        table.append([
            str(i), fmt_date(dt), typ or "", member or "",
            fmt_money(amount), fmt_money(balance), doc or "—", notes or "",
        ])
    if len(rows) == 0:
        table.append(["—"] * 6 + ["*no transactions logged yet*"])
    return table, balance


def compute_ownership(rows: list[tuple]) -> list[list[str]]:
    """Returns current-ownership table rows incl. header."""
    ownership: dict[str, float] = {}
    for dt, frm, to, pct, doc, notes in rows:
        pct = float(pct or 0)
        if frm:
            ownership[frm] = ownership.get(frm, 0.0) - pct
        ownership[to] = ownership.get(to, 0.0) + pct

    table = [["Member", "Ownership %"]]
    for member, pct in ownership.items():
        if abs(pct) > 0.0001:
            table.append([member, fmt_pct(pct)])
    return table


def build_pdf(entity: dict, capital_rows: list[tuple], transfer_rows: list[tuple], pdf_path: Path) -> None:
    styles = getSampleStyleSheet()
    body = ParagraphStyle("body", parent=styles["Normal"], fontSize=9, leading=12)
    cell = ParagraphStyle("cell", parent=styles["Normal"], fontSize=8, leading=10)
    header_cell = ParagraphStyle("header_cell", parent=cell, fontName="Helvetica-Bold", textColor=colors.white)

    def wrap_table(rows: list[list[str]], col_widths: list[float]) -> Table:
        wrapped = [
            [Paragraph(escape(str(c)), header_cell if r == 0 else cell) for c in row]
            for r, row in enumerate(rows)
        ]
        t = Table(wrapped, colWidths=col_widths, repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2b2b2b")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f2f2")]),
        ]))
        return t

    ownership_rows = compute_ownership(transfer_rows)
    capital_rows_table, balance = compute_capital(capital_rows)

    doc = SimpleDocTemplate(
        str(pdf_path), pagesize=landscape(letter),
        leftMargin=0.6 * inch, rightMargin=0.6 * inch, topMargin=0.6 * inch, bottomMargin=0.6 * inch,
        title=f"{entity['name']} — Membership Interest Ledger",
    )

    flow = [
        Paragraph(f"{entity['name']} — Membership Interest Ledger", styles["Title"]),
        Spacer(1, 10),
        Paragraph(
            f"<b>Entity:</b> {entity['name']} ({entity['state']} LLC, Articles {entity['articles']}, "
            f"filed {fmt_date(entity['formed'])})", body,
        ),
        Paragraph(f"<b>Sole member:</b> {entity['sole_member']} — {entity['sole_member_note']}", body),
        Spacer(1, 16),
        Paragraph("Current ownership", styles["Heading2"]),
        wrap_table(ownership_rows, [4.5 * inch, 1.5 * inch]),
        Spacer(1, 16),
        Paragraph("Capital transactions", styles["Heading2"]),
        wrap_table(
            capital_rows_table,
            [0.3 * inch, 0.85 * inch, 0.75 * inch, 1.9 * inch, 0.7 * inch, 0.8 * inch, 1.9 * inch, 2.5 * inch],
        ),
        Spacer(1, 10),
        Paragraph(f"<b>Current capital account balance: {fmt_money(balance)}</b>", body),
    ]
    doc.build(flow)
    print(f"Wrote {pdf_path}")


def build_one(entity: dict, xlsx_path: Path, pdf_path: Path) -> None:
    if not xlsx_path.exists():
        print(f"Missing xlsx: {xlsx_path}", file=sys.stderr)
        sys.exit(1)

    wb = openpyxl.load_workbook(xlsx_path, data_only=True)
    capital_rows = read_rows(wb["Capital"], 6)
    transfer_rows = read_rows(wb["Transfers"], 6)

    build_pdf(entity, capital_rows, transfer_rows, pdf_path)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--entity", choices=sorted(ENTITIES), help="Regenerate one entity's ledger PDF using default gdrive paths")
    p.add_argument("--xlsx", type=Path, help="Ledger .xlsx source (with --xlsx, also pass --pdf and --entity for entity facts)")
    p.add_argument("--pdf", type=Path, help="Ledger .pdf to write")
    p.add_argument("--all", action="store_true", help="Regenerate both HoldCo and OpCo ledgers using default gdrive paths")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    if args.all:
        for entity in ENTITIES.values():
            entity_dir = GOV_DIR / entity["folder"]
            build_one(entity, entity_dir / f"{entity['stem']}.xlsx", entity_dir / f"{entity['stem']}.pdf")
        return

    if args.entity:
        entity = ENTITIES[args.entity]
        entity_dir = GOV_DIR / entity["folder"]
        xlsx = args.xlsx or entity_dir / f"{entity['stem']}.xlsx"
        pdf = args.pdf or entity_dir / f"{entity['stem']}.pdf"
        build_one(entity, xlsx, pdf)
        return

    print("Pass --entity <holdings|sustain>, --all, or --xlsx/--pdf with --entity for facts", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
