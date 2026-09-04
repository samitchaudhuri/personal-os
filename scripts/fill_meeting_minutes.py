#!/usr/bin/env python3
"""Fill a signed-ready Annual/Organizational Meeting Minutes PDF.

The Northwest Registered Agent "Annual Meeting Minutes" template (a
fillable PDF form from northwestregisteredagent.com) is used here for each
entity's first (organizational) meeting -- confirming formation actions,
ratifying the Initial Resolutions/OA, and recording that no managers were
elected (both entities are member-managed). Several fields carry defaults
that still need Craig's sign-off (meeting time/location, chairman/secretary
assignment, whether to commit to a fixed next-annual-meeting date) -- see
the printed "Open items" list after running.

Signature lines (Secretary Signature, Member Signature) are left blank for
hand signing, same pattern as fill_membership_certificate.py and
fill_capital_contribution.py. Printed-name fields ARE filled, including the
Members block using Craig's suggested capacity wording.

Requires: pypdf — see scripts/requirements.txt; run via scripts/.venv
  (python3 -m venv scripts/.venv && scripts/.venv/bin/pip install -r scripts/requirements.txt)

Example:
  python scripts/fill_meeting_minutes.py --entity holdings
  python scripts/fill_meeting_minutes.py --entity sustain
"""

from __future__ import annotations

import argparse
import sys
import textwrap
from datetime import date
from pathlib import Path
from pypdf.generic import ArrayObject, FloatObject, NameObject, NumberObject, TextStringObject

try:
    from pypdf import PdfReader, PdfWriter
except ImportError:
    print("fill_meeting_minutes.py requires pypdf: pip install pypdf", file=sys.stderr)
    sys.exit(1)

GOV_DIR = (
    Path(__file__).resolve().parent.parent
    / "gdrive" / "private" / "ULC-personal" / "Governance" / "Entity Structure" / "Organizational Meeting"
)
# The blank NW template is entity-agnostic (byte-identical across entities),
# so it lives once at Entity Structure/Templates rather than per-entity.
TEMPLATE_STEM = "MEETING_MINUTES_TEMPLATE_2026-08-31"

MEETING_DATE = date(2026, 8, 14)
CHAIRMAN = "Samit Chaudhuri"
SECRETARY = "Mousumi Das Chaudhuri"

ENTITIES = {
    "holdings": {
        "folder": "MSC Holdings",
        "output_stem": "MSC_HOLDINGS_MEETING_MINUTES",
        "name": "MSC Holdings LLC",
        "present": [
            ("Samit Chaudhuri", ""),
            ("Mousumi Das Chaudhuri", ""),
        ],
        "members": [
            "Samit Chaudhuri, co-trustee of Samit & Mousumi Das Chaudhuri Living Trust, member, MSC Holdings LLC",
            "Mousumi Das Chaudhuri, co-trustee of Samit & Mousumi Das Chaudhuri Living Trust, member, MSC Holdings LLC",
        ],
    },
    "sustain": {
        "folder": "MSC Sustain",
        "output_stem": "MSC_SUSTAIN_MEETING_MINUTES",
        "name": "MSC Sustain LLC",
        "present": [
            ("Samit Chaudhuri", ""),
            ("Mousumi Das Chaudhuri", ""),
        ],
        "members": [
            "Samit Chaudhuri, co-trustee of Samit & Mousumi Das Chaudhuri Living Trust, member of MSC Holdings LLC, member, MSC Sustain LLC",
            "Mousumi Das Chaudhuri, co-trustee of Samit & Mousumi Das Chaudhuri Living Trust, member of MSC Holdings LLC, member, MSC Sustain LLC",
        ],
    },
}

OTHER_BUSINESS_LINES = [
    "The Members ratified and approved the Company's Articles of Organization,",
    "EIN application, Initial Resolutions, and Operating Agreement, and confirmed",
    "the initial capital contributions and membership interests as reflected in",
    "the Company's membership interest ledger.",
]

# Field names, determined by reading the PDF's AcroForm field rects against
# the rendered page images (4 pages). See module docstring for the parts of
# the template intentionally left blank (signatures, "if sold"-equivalent
# distribution table, manager-salary table -- no managers were elected).
FIELD_COMPANY_NAME = "Text Field"
FIELD_DAY = "Text Field_1"
FIELD_MONTH = "Text Field_2"
FIELD_YEAR_SUFFIX = "Text Field_3"
FIELD_TIME = "Text Field_4"
LOCATION_FIELDS = ["Text Field_5", "Text Field_5_1", "Text Field_5_2"]

PRESENT_NAME_FIELDS = [f"Text Field_6{s}" for s in ["", "_1", "_2", "_3", "_4", "_5", "_6"]]
PRESENT_ADDRESS_FIELDS = [f"Text Field_7{s}" for s in ["", "_1", "_2", "_3", "_4", "_5", "_6"]]

FIELD_CHAIRMAN = "Text Field_8"
FIELD_SECRETARY = "Text Field_8_1"

FIELD_GROSS_RECEIPTS = "Text Field_12"
FIELD_GROSS_PROFIT = "Text Field_12_1"
FIELD_NET_PROFIT = "Text Field_12_2"

FIELD_MANAGERS_LINE1 = "Text Field_15"

FIELD_NEXT_MEETING_DATE = "Text Field_18"
FIELD_NO_ANNUAL_MEETINGS_YES = "Check Box"
FIELD_NO_ANNUAL_MEETINGS_NO = "Check Box_1"

OTHER_BUSINESS_FIELDS = [f"Text Field_21{s}" for s in ["", "_1", "_2", "_3"]]

FIELD_DATED = "Text Field_22"
FIELD_SECRETARY_PRINTED_NAME = "Text Field_23"
MEMBER_PRINTED_NAME_FIELDS = ["Text Field_23_1", "Text Field_23_2", "Text Field_23_3", "Text Field_23_4"]
# FIELD_SECRETARY_SIGNATURE / member Signature columns have no form fields --
# blank underlines on the template, filled by hand at signing.

# Craig's capacity wording ("co-trustee of ... Living Trust, member ...") is
# too long for the template's Printed Name column at normal size (it clips
# rather than wraps). Widen the field to the page's right margin, shrink the
# font, and wrap the text onto two lines ourselves -- the field's own height
# is untouched (2 lines fit at this font size), so nothing collides with the
# "Signature" / "Printed Name" labels painted just below it on the page.
MEMBER_FIELD_WRAP_WIDTH = 75
MEMBER_FIELD_FONT_SIZE = 6
MEMBER_FIELD_RIGHT_X = 562.0

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
    fields: dict[str, str] = {
        FIELD_COMPANY_NAME: entity["name"],
        FIELD_DAY: ordinal(MEETING_DATE.day),
        FIELD_MONTH: MONTH_NAMES[MEETING_DATE.month - 1],
        FIELD_YEAR_SUFFIX: f"{MEETING_DATE.year % 100:02d}",
        FIELD_TIME: "N/A",
        FIELD_CHAIRMAN: CHAIRMAN,
        FIELD_SECRETARY: SECRETARY,
        FIELD_GROSS_RECEIPTS: "N/A - formation year",
        FIELD_GROSS_PROFIT: "N/A - formation year",
        FIELD_NET_PROFIT: "N/A - formation year",
        FIELD_MANAGERS_LINE1: "None -- the Company is member-managed; no managers were elected.",
        FIELD_NO_ANNUAL_MEETINGS_NO: "/Yes",
        FIELD_DATED: MEETING_DATE.strftime("%B %d, %Y"),
        FIELD_SECRETARY_PRINTED_NAME: SECRETARY,
    }
    # Location lines left unfilled -- no confirmed meeting-location address on file.

    for (name, addr), name_f, addr_f in zip(entity["present"], PRESENT_NAME_FIELDS, PRESENT_ADDRESS_FIELDS):
        fields[name_f] = name
        if addr:
            fields[addr_f] = addr

    for line, field in zip(OTHER_BUSINESS_LINES, OTHER_BUSINESS_FIELDS):
        fields[field] = line

    for member_line, field in zip(entity["members"], MEMBER_PRINTED_NAME_FIELDS):
        fields[field] = "\n".join(textwrap.wrap(member_line, MEMBER_FIELD_WRAP_WIDTH))

    return fields


def widen_member_name_fields(writer: PdfWriter) -> None:
    """Widen + shrink-font the Member Printed Name fields so Craig's longer
    capacity wording fits without clipping. See MEMBER_FIELD_* constants."""
    for page in writer.pages:
        if "/Annots" not in page:
            continue
        for annot in page["/Annots"]:
            obj = annot.get_object()
            if obj.get("/T") not in MEMBER_PRINTED_NAME_FIELDS:
                continue
            rect = obj["/Rect"]
            obj[NameObject("/Rect")] = ArrayObject(
                [rect[0], rect[1], FloatObject(MEMBER_FIELD_RIGHT_X), rect[3]]
            )
            ff = int(obj.get("/Ff", 0))
            obj[NameObject("/Ff")] = NumberObject(ff | (1 << 12))  # multiline
            obj[NameObject("/DA")] = TextStringObject(f"/Helvetica {MEMBER_FIELD_FONT_SIZE} Tf 0 g")


def fill_pdf(template_path: Path, output_path: Path, fields: dict[str, str]) -> None:
    reader = PdfReader(template_path)
    writer = PdfWriter()
    writer.append(reader)
    widen_member_name_fields(writer)
    for page in writer.pages:
        writer.update_page_form_field_values(page, fields, auto_regenerate=False)
    with open(output_path, "wb") as f:
        writer.write(f)
    print(f"Wrote {output_path}")
    print("Open items -- confirm with Craig, then hand-fill/sign:")
    print("  - Meeting time/location (left blank -- no confirmed address on file)")
    print("  - Chairman/Secretary assignment (defaulted: Samit=Chairman, Mousumi=Secretary)")
    print("  - Item 8 next-annual-meeting choice (defaulted: checked 'No', no fixed annual meeting)")
    print("  - Secretary Signature and Member Signature lines (hand-signed)")
    print("  - Present-persons Address column (left blank -- no address on file)")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--entity", choices=sorted(ENTITIES), required=True, help="Which entity to fill")
    p.add_argument("--template", type=Path, help="Blank Meeting Minutes template .pdf (overrides default)")
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
        output = entity_dir / f"{entity['output_stem']}_{MEETING_DATE}.pdf"

    fill_pdf(template, output, fields)


if __name__ == "__main__":
    main()
