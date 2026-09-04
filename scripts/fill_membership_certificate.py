#!/usr/bin/env python3
"""Fill a signed-ready LLC Membership Certificate PDF for a single-member entity.

The Northwest Registered Agent membership-certificate template (a fillable
PDF form from northwestregisteredagent.com) has two sections: the issuance
section at top (who the LLC is, who its member is, what date) and a
transfer/"if sold" section at bottom for a future sale of the interest. This
script only fills the issuance section -- the transfer section stays blank
until an actual sale happens. The "Named Member" and "witness" signature
fields are also left blank, same as fill_capital_contribution.py, for
signing by hand.

Requires: pypdf — see scripts/requirements.txt; run via scripts/.venv
  (python3 -m venv scripts/.venv && scripts/.venv/bin/pip install -r scripts/requirements.txt)

Example:
  python scripts/fill_membership_certificate.py --entity holdings
  python scripts/fill_membership_certificate.py --entity sustain
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

try:
    from pypdf import PdfReader, PdfWriter
except ImportError:
    print("fill_membership_certificate.py requires pypdf: pip install pypdf", file=sys.stderr)
    sys.exit(1)

# Reached via personal-os/gdrive (repo symlink) rather than the absolute
# CloudStorage path, so this works across machines/clones without editing.
GOV_DIR = (
    Path(__file__).resolve().parent.parent
    / "gdrive" / "private" / "ULC-personal" / "Governance" / "Entity Structure" / "Organizational Meeting"
)
# The blank NW template is entity-agnostic (byte-identical across entities),
# so it lives once at Entity Structure/Templates rather than per-entity.
TEMPLATE_STEM = "MEMBERSHIP_CERTIFICATE_TEMPLATE_2026-08-31"

ENTITIES = {
    "holdings": {
        "folder": "MSC Holdings",
        "output_stem": "MSC_HOLDINGS_MEMBERSHIP_CERTIFICATE",
        "name": "MSC Holdings LLC",
        "state": "California",
        "member": "Samit & Mousumi Das Chaudhuri Living Trust",
        "percent": 100,
        "as_of": date(2026, 8, 14),
    },
    "sustain": {
        "folder": "MSC Sustain",
        "output_stem": "MSC_SUSTAIN_MEMBERSHIP_CERTIFICATE",
        "name": "MSC Sustain LLC",
        "state": "California",
        "member": "MSC Holdings LLC",
        "percent": 100,
        "as_of": date(2026, 8, 14),
    },
}

# Form field names (both templates share identical field IDs). Determined by
# reading the PDF's AcroForm field rects against the rendered page image --
# see the top-of-page issuance section only; the bottom "if sold" transfer
# section and the two signature fields are left blank for hand signing.
FIELD_COMPANY_NAME = "text-76cead8a-f1ce-42a7-b57f-b27140c0b836"
FIELD_ORGANIZED_IN = "text-6fdcde5c-9f3e-4794-887d-e60a7f9fc73a"
FIELD_MEMBER_COUNT = "text-a2a340be-592d-40c9-bede-7a1c75de709c"
FIELD_ORGANIZED_DATE = "text-3a213a37-dd26-4302-875f-777050392bea"
FIELD_MEMBER_NAME = "text-c5da8b52-0bdd-4d88-ad30-48e36e84df60"
FIELD_MEMBER_PERCENT = "text-4722a8bd-a314-4e33-8f73-269ba36eb934"
FIELD_EXEC_DAY = "text-1abfa54c-6b5c-4a98-bb81-8ce92e334291"
FIELD_EXEC_MONTH = "text-08d66531-6320-4ae6-84d2-1c2f8818bd73"
FIELD_EXEC_YEAR = "text-7c5c529a-6fa3-4028-8d98-0de3f939c135"
# FIELD_NAMED_MEMBER_SIG / FIELD_WITNESS_SIG intentionally unfilled (hand-signed).

MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def build_fields(entity: dict) -> dict[str, str]:
    as_of = entity["as_of"]
    return {
        FIELD_COMPANY_NAME: entity["name"],
        FIELD_ORGANIZED_IN: entity["state"],
        FIELD_MEMBER_COUNT: "1",
        FIELD_ORGANIZED_DATE: as_of.strftime("%m/%d/%Y"),
        FIELD_MEMBER_NAME: entity["member"],
        FIELD_MEMBER_PERCENT: str(entity["percent"]),
        FIELD_EXEC_DAY: ordinal(as_of.day),
        FIELD_EXEC_MONTH: MONTH_NAMES[as_of.month - 1],
        FIELD_EXEC_YEAR: str(as_of.year),
    }


def fill_pdf(template_path: Path, output_path: Path, fields: dict[str, str]) -> None:
    reader = PdfReader(template_path)
    writer = PdfWriter()
    writer.append(reader)
    writer.update_page_form_field_values(writer.pages[0], fields, auto_regenerate=False)
    with open(output_path, "wb") as f:
        writer.write(f)
    print(f"Wrote {output_path}")
    print("Named Member and witness signature fields are blank -- print, sign, and re-save at the same path.")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--entity", choices=sorted(ENTITIES), required=True, help="Which entity to fill")
    p.add_argument("--template", type=Path, help="Blank Membership Certificate template .pdf (overrides default)")
    p.add_argument("--output", type=Path, help="Filled .pdf to write (overrides default)")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    entity = ENTITIES[args.entity]
    entity_dir = GOV_DIR / entity["folder"]
    template = args.template or GOV_DIR.parent / "Templates" / f"{TEMPLATE_STEM}.pdf"
    if not template.exists():
        print(f"Missing template: {template}", file=sys.stderr)
        sys.exit(1)

    fields = build_fields(entity)

    if args.output:
        output = args.output
    else:
        output = entity_dir / f"{entity['output_stem']}_{entity['as_of']}.pdf"

    fill_pdf(template, output, fields)


if __name__ == "__main__":
    main()
