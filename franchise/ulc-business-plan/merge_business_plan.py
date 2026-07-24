#!/usr/bin/env python3
"""Merge ULC_Business_Plan_Staging.md into ULC_Sample Business Plan.docx.

Replaces text in yellow-highlighted runs only (consecutive yellow groups).
Non-highlighted runs are left unchanged.

Patches ``word/document.xml`` in place on a template copy (``zip -u``) so the
OOXML package stays byte-stable. Split yellow placeholders clear trailing runs
by removing the ``w:r`` block (Word rejects empty ``w:t`` nodes).
"""

from __future__ import annotations

import re
import shutil
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = f"{{{W_NS}}}"
YELLOW = frozenset({"yellow", "lightYellow", "darkYellow"})
WT_RE = re.compile(r"(<w:t(?:\s[^>]*)?>)(.*?)(</w:t>)", re.DOTALL)
WR_RE = re.compile(r"<w:r\b[^>]*>.*?</w:r>", re.DOTALL)

PLACEHOLDER_MAP: list[tuple[str, str]] = [
    ("[$Loan Amount$]", "loan_amount"),
    ("[$Total Project Cost$]", "total_project_cost"),
    ("[$Equity Contribution$]", "equity_contribution"),
    ("[$Estimated Revenue$]", "estimated_revenue"),
    ("[$Estimated EBITDA$]", "estimated_ebitda"),
    (
        "[insert relevant background: e.g., healthcare, wellness, business management]",
        "owner_background",
    ),
    ("[Owner/Managing Member Name]", "owner_name"),
    ("[LLC / S Corporation / etc.]", "entity_type_long"),
    ("[LLC/S-corp/etc.]", "entity_type_short"),
    ("[target opening month/year]", "target_opening"),
    ("[Insert Formation Date]", "formation_date"),
    ("[Insert City, State]", "insert_city_state"),
    ("[Insert City/Region]", "insert_city_region"),
    ("[Insert Range Min]", "insert_range_min"),
    ("[Insert Range Max]", "insert_range_max"),
    ("[Insert State]", "insert_state"),
    ("[City, State]", "city_state"),
    ("[X]", "breakeven_months"),
]

DEFAULT_BASE = Path(
    "/Users/samit/Library/CloudStorage/GoogleDrive-samit.chaudhuri@gmail.com/"
    "My Drive/Work/Franchise/Ultimate Longevity/Finance/Underwriting"
)


def parse_input_md(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 3 or cells[0] == "`field`":
            continue
        field = cells[0]
        if not field.startswith("`"):
            continue
        key = field.strip("`")
        value = cells[2]
        if value in ("CHOOSE_ONE", "TBD", ""):
            raise ValueError(
                f"Unresolved input '{key}' in {path.name}: '{value}' "
                "(set a concrete value before merge)"
            )
        values[key] = value
    required = {k for _, k in PLACEHOLDER_MAP}
    missing = required - set(values.keys())
    if missing:
        raise ValueError(f"Missing fields in {path.name}: {sorted(missing)}")
    return values


def is_yellow_run(run: ET.Element) -> bool:
    rpr = run.find(f"{W}rPr")
    if rpr is None:
        return False
    hl = rpr.find(f"{W}highlight")
    if hl is None:
        return False
    val = hl.get(f"{W}val") or hl.get("val")
    return val in YELLOW


def run_text(run: ET.Element) -> str:
    return "".join((t.text or "") for t in run.findall(f"{W}t"))


def apply_replacements(text: str, values: dict[str, str]) -> str:
    out = text
    for placeholder, key in PLACEHOLDER_MAP:
        if placeholder in out:
            out = out.replace(placeholder, values[key])
    return out


def xml_escape_text(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def collect_changes(
    root: ET.Element, values: dict[str, str]
) -> tuple[dict[int, str], set[int], int]:
    """Return w:t patches, w:r deletions (by index), and changed paragraph count."""
    body = root.find(f"{W}body")
    if body is None:
        raise RuntimeError("Invalid docx: missing w:body")

    all_wts = list(root.iter(f"{W}t"))
    wt_to_index = {id(wt): idx for idx, wt in enumerate(all_wts)}
    all_runs = list(root.iter(f"{W}r"))
    run_to_index = {id(run): idx for idx, run in enumerate(all_runs)}

    patch_indices: dict[int, str] = {}
    delete_run_indices: set[int] = set()
    changed_paragraphs = 0

    for paragraph in body.findall(f"{W}p"):
        runs = list(paragraph.findall(f"{W}r"))
        if not runs:
            continue

        paragraph_changed = False
        i = 0
        while i < len(runs):
            if not is_yellow_run(runs[i]):
                i += 1
                continue

            group = [runs[i]]
            group_text = run_text(runs[i])
            j = i + 1
            while j < len(runs) and is_yellow_run(runs[j]):
                group.append(runs[j])
                group_text += run_text(runs[j])
                j += 1

            new_text = apply_replacements(group_text, values)
            if new_text != group_text:
                paragraph_changed = True
                wts = group[0].findall(f"{W}t")
                if wts:
                    patch_indices[wt_to_index[id(wts[0])]] = new_text
                for extra_run in group[1:]:
                    delete_run_indices.add(run_to_index[id(extra_run)])

            i = j

        if paragraph_changed:
            changed_paragraphs += 1

    return patch_indices, delete_run_indices, changed_paragraphs


def ensure_preserve_space_open_tag(open_tag: str, text: str) -> str:
    """Word collapses leading/trailing spaces in ``w:t`` without xml:space preserve."""
    if not (text.startswith(" ") or text.endswith(" ")):
        return open_tag
    if 'xml:space="preserve"' in open_tag:
        return open_tag
    if open_tag == "<w:t>":
        return '<w:t xml:space="preserve">'
    return open_tag[:-1] + ' xml:space="preserve">'


def apply_patches(xml: str, patch_indices: dict[int, str]) -> str:
    if not patch_indices:
        return xml

    parts: list[str] = []
    last = 0
    for i, match in enumerate(WT_RE.finditer(xml)):
        parts.append(xml[last : match.start()])
        open_tag = match.group(1)
        content = match.group(2)
        if i in patch_indices:
            content = xml_escape_text(patch_indices[i])
            open_tag = ensure_preserve_space_open_tag(open_tag, patch_indices[i])
        parts.append(f"{open_tag}{content}{match.group(3)}")
        last = match.end()
    parts.append(xml[last:])
    return "".join(parts)


def delete_runs(xml: str, delete_run_indices: set[int]) -> str:
    if not delete_run_indices:
        return xml

    spans = [(m.start(), m.end()) for m in WR_RE.finditer(xml)]
    for idx in sorted(delete_run_indices, reverse=True):
        start, end = spans[idx]
        xml = xml[:start] + xml[end:]
    return xml


def apply_changes(
    xml: str, patch_indices: dict[int, str], delete_run_indices: set[int]
) -> str:
    xml = apply_patches(xml, patch_indices)
    return delete_runs(xml, delete_run_indices)


def update_docx_document_xml(output: Path, patched_bytes: bytes) -> None:
    """Replace word/document.xml, preserving other members' bytes and compress type."""
    with zipfile.ZipFile(output, "r") as zin:
        entries = [(info, zin.read(info.filename)) for info in zin.infolist()]

    tmp_path = output.with_suffix(output.suffix + ".tmp")
    with zipfile.ZipFile(tmp_path, "w") as zout:
        for info, data in entries:
            if info.filename == "word/document.xml":
                data = patched_bytes
            new_info = zipfile.ZipInfo(filename=info.filename, date_time=info.date_time)
            new_info.compress_type = info.compress_type
            new_info.external_attr = info.external_attr
            new_info.internal_attr = info.internal_attr
            new_info.flag_bits = info.flag_bits & ~0x08  # clear data-descriptor bit
            zout.writestr(new_info, data)
    tmp_path.replace(output)


def merge_docx(template: Path, output: Path, values: dict[str, str]) -> int:
    shutil.copy2(template, output)

    with zipfile.ZipFile(template, "r") as zin:
        original_bytes = zin.read("word/document.xml")

    root = ET.fromstring(original_bytes)
    patch_indices, delete_run_indices, count = collect_changes(root, values)
    patched_xml = apply_changes(
        original_bytes.decode("utf-8"), patch_indices, delete_run_indices
    ).encode("utf-8")

    update_docx_document_xml(output, patched_xml)
    return count


def main(argv: list[str]) -> int:
    input_path = DEFAULT_BASE / "ULC_Business_Plan_Staging.md"
    template = DEFAULT_BASE / "ULC_Sample Business Plan.docx"
    output = DEFAULT_BASE / "Chaudhuri_ULC_Site1_Business_Plan.docx"

    if len(argv) > 1:
        input_path = Path(argv[1])
    if len(argv) > 2:
        template = Path(argv[2])
    if len(argv) > 3:
        output = Path(argv[3])

    values = parse_input_md(input_path)
    n = merge_docx(template, output, values)
    print(f"OK: merged {n} paragraph(s) with yellow edits")
    print(f"    input:    {input_path}")
    print(f"    template: {template}")
    print(f"    output:   {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
