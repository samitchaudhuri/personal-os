#!/usr/bin/env python3
"""Regenerate a membership-interest ledger .md from its .xlsx source.

Manual entry into a markdown table is error-prone, especially the computed
columns (running capital balance, current ownership %). This script keeps
those out of the spreadsheet entirely: the .xlsx holds only raw transaction
rows (who, when, how much), and this script derives the running balance and
ownership snapshot and writes them into the .md, between two marker
comments. Everything outside the markers (entity info, instructions, open
items) is hand-written prose and is left untouched.

Each entity's .xlsx has two sheets:

  Capital   — Date | Type (Contribution/Distribution) | Member | Amount | Doc | Notes
              One row per cash/property transfer between the LLC and a
              member. Running balance is computed here, not typed in.

  Transfers — Date | From Member | To Member | Percent | Doc | Notes
              One row per change in who owns what share. The first row is
              always the formation grant (From Member blank, To Member =
              the sole member, Percent = 100). Current ownership is the
              cumulative result of this sheet, not typed in.

Requires: openpyxl (pip install openpyxl)

Example:
  python scripts/build_membership_ledger.py \\
    --xlsx "$GOV_DIR/MSC Holdings/MSC_HOLDINGS_MEMBERSHIP_LEDGER.xlsx" \\
    --md   "$GOV_DIR/MSC Holdings/MSC_HOLDINGS_MEMBERSHIP_LEDGER.md"

  # Or regenerate both entities using the default gdrive-symlink paths:
  python scripts/build_membership_ledger.py --all
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

try:
    import openpyxl
except ImportError:
    print("build_membership_ledger.py requires openpyxl: pip install openpyxl", file=sys.stderr)
    sys.exit(1)

START_MARKER = "<!-- LEDGER:AUTO:START -->"
END_MARKER = "<!-- LEDGER:AUTO:END -->"

# Reached via personal-os/gdrive (repo symlink) rather than the absolute
# CloudStorage path, so this works across machines/clones without editing.
GOV_DIR = (
    Path(__file__).resolve().parent.parent
    / "gdrive" / "private" / "ULC-personal" / "Governance" / "Entity Structure" / "Organizational Meeting"
)

ENTITIES = [
    ("MSC Holdings", "MSC_HOLDINGS_MEMBERSHIP_LEDGER"),
    ("MSC Sustain", "MSC_SUSTAIN_MEMBERSHIP_LEDGER"),
]


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


def build_capital_table(rows: list[tuple]) -> tuple[str, float]:
    lines = [
        "| # | Date | Type | Member | Amount | Capital account balance | Supporting document | Notes |",
        "|---|------|------|--------|--------|--------------------------|----------------------|-------|",
    ]
    balance = 0.0
    for i, (dt, typ, member, amount, doc, notes) in enumerate(rows, start=1):
        amount = float(amount or 0)
        signed = amount if str(typ).strip().lower().startswith("contrib") or str(typ).strip().lower() == "formation" else -amount
        balance += signed
        lines.append(
            f"| {i} | {fmt_date(dt)} | {typ or ''} | {member or ''} | {fmt_money(amount)} "
            f"| {fmt_money(balance)} | {doc or '—'} | {notes or ''} |"
        )
    if len(rows) == 0:
        lines.append("| — | — | — | — | — | — | — | *no transactions logged yet* |")
    return "\n".join(lines), balance


def build_ownership(rows: list[tuple]) -> tuple[str, str]:
    """Returns (current-ownership table, transfer-history table or '')."""
    ownership: dict[str, float] = {}
    history_lines = [
        "| # | Date | From | To | Percent | Supporting document | Notes |",
        "|---|------|------|----|---------|-----------------------|------|",
    ]
    for i, (dt, frm, to, pct, doc, notes) in enumerate(rows, start=1):
        pct = float(pct or 0)
        if frm:
            ownership[frm] = ownership.get(frm, 0.0) - pct
        ownership[to] = ownership.get(to, 0.0) + pct
        history_lines.append(
            f"| {i} | {fmt_date(dt)} | {frm or '— (formation grant)'} | {to or ''} "
            f"| {fmt_pct(pct)} | {doc or '—'} | {notes or ''} |"
        )

    current_lines = [
        "| Member | Ownership % |",
        "|--------|-------------|",
    ]
    for member, pct in ownership.items():
        if abs(pct) > 0.0001:
            current_lines.append(f"| {member} | {fmt_pct(pct)} |")

    # Only show transfer history as its own table when there's more than
    # the single formation grant — otherwise it's redundant with "current".
    history = "\n".join(history_lines) if len(rows) > 1 else ""
    return "\n".join(current_lines), history


def render_block(capital_rows: list[tuple], transfer_rows: list[tuple]) -> str:
    capital_table, balance = build_capital_table(capital_rows)
    ownership_table, history_table = build_ownership(transfer_rows)

    parts = [
        START_MARKER,
        "*Generated by `scripts/build_membership_ledger.py` from the paired .xlsx — do not hand-edit this block, edit the spreadsheet and regenerate.*",
        "",
        "### Current ownership",
        "",
        ownership_table,
        "",
        "### Capital transactions",
        "",
        capital_table,
        "",
        f"**Current capital account balance: {fmt_money(balance)}**",
    ]
    if history_table:
        parts += ["", "### Interest transfer history", "", history_table]
    parts.append(END_MARKER)
    return "\n".join(parts)


def update_md(md_path: Path, block: str) -> None:
    text = md_path.read_text()
    if START_MARKER not in text or END_MARKER not in text:
        raise ValueError(
            f"{md_path} has no {START_MARKER}/{END_MARKER} markers — add them where the "
            "generated tables should go, then rerun."
        )
    pre, rest = text.split(START_MARKER, 1)
    _, post = rest.split(END_MARKER, 1)
    md_path.write_text(pre + block + post)
    print(f"Wrote {md_path}")


def build_one(xlsx_path: Path, md_path: Path) -> None:
    if not xlsx_path.exists():
        print(f"Missing xlsx: {xlsx_path}", file=sys.stderr)
        sys.exit(1)
    if not md_path.exists():
        print(f"Missing md: {md_path}", file=sys.stderr)
        sys.exit(1)

    wb = openpyxl.load_workbook(xlsx_path, data_only=True)
    capital_rows = read_rows(wb["Capital"], 6)
    transfer_rows = read_rows(wb["Transfers"], 6)

    block = render_block(capital_rows, transfer_rows)
    update_md(md_path, block)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--xlsx", type=Path, help="Ledger .xlsx source")
    p.add_argument("--md", type=Path, help="Ledger .md to update in place")
    p.add_argument("--all", action="store_true", help="Regenerate both HoldCo and OpCo ledgers using default gdrive paths")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    if args.all:
        for folder, stem in ENTITIES:
            entity_dir = GOV_DIR / folder
            build_one(entity_dir / f"{stem}.xlsx", entity_dir / f"{stem}.md")
        return

    if not args.xlsx or not args.md:
        print("Pass --xlsx and --md, or use --all", file=sys.stderr)
        sys.exit(1)
    build_one(args.xlsx, args.md)


if __name__ == "__main__":
    main()
