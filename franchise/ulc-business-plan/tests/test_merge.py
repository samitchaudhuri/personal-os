"""Hermetic tests for ULC business plan merge.

Run: python3 -m unittest discover -s franchise/ulc-business-plan/tests
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL_DIR = os.path.dirname(HERE)
sys.path.insert(0, TOOL_DIR)

import merge_business_plan as mbp  # noqa: E402

W_NS = mbp.W_NS
W = mbp.W

MINIMAL_DOCUMENT_XML = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="{W_NS}" xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006">
  <w:body>
    <w:p>
      <w:r>
        <w:rPr><w:highlight w:val="yellow"/></w:rPr>
        <w:t>[$Loan Amount$]</w:t>
      </w:r>
    </w:p>
  </w:body>
</w:document>
"""

CONTENT_TYPES = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="urn:schemas-microsoft-com:office:document">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>
"""

RELS = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>
"""

MINIMAL_INPUT = """---
status: test
---

| field | placeholder | value |
| --- | --- | --- |
| `loan_amount` | `[$Loan Amount$]` | $428,000 |
| `total_project_cost` | `[$Total Project Cost$]` | $837,850 |
| `equity_contribution` | `[$Equity Contribution$]` | $0 |
| `estimated_revenue` | `[$Estimated Revenue$]` | $924,000 |
| `estimated_ebitda` | `[$Estimated EBITDA$]` | $276,000 |
| `owner_background` | placeholder | background text |
| `owner_name` | placeholder | Samit Chaudhuri |
| `entity_type_long` | placeholder | LLC |
| `entity_type_short` | placeholder | LLC |
| `target_opening` | placeholder | May 2027 |
| `formation_date` | placeholder | pending |
| `insert_city_state` | placeholder | Cupertino, CA |
| `insert_city_region` | placeholder | South Bay |
| `insert_range_min` | placeholder | $529,278 |
| `insert_range_max` | placeholder | $1,264,688 |
| `insert_state` | placeholder | California |
| `city_state` | placeholder | Cupertino, CA |
| `breakeven_months` | placeholder | 12-15 |
| `equity_percent` | `[XX]%` | 0% |
| `owner_experience_clause` | `who brings experience` | who bring experience |
| `market_demographics` | placeholder | demographics text |
"""

DOC_ROOT_RE = re.compile(rb"<w:document[^>]*>")
EMPTY_WT_RE = re.compile(r"<w:t(?:\s[^>]*)?></w:t>")


def write_minimal_docx(path: Path) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zout:
        zout.writestr("[Content_Types].xml", CONTENT_TYPES)
        zout.writestr("_rels/.rels", RELS)
        zout.writestr("word/document.xml", MINIMAL_DOCUMENT_XML.encode("utf-8"))


class TestApplyChanges(unittest.TestCase):
    def test_replaces_only_target_wt_node(self):
        xml = MINIMAL_DOCUMENT_XML
        patched = mbp.apply_changes(xml, {0: "$428,000"}, set())
        self.assertIn("$428,000", patched)
        self.assertNotIn("[$Loan Amount$]", patched)
        self.assertEqual(len(EMPTY_WT_RE.findall(patched)), 0)

    def test_preserve_trailing_space_adds_xml_space_attribute(self):
        xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            f'<w:document xmlns:w="{W_NS}"><w:body><w:p><w:r>'
            '<w:rPr><w:highlight w:val="yellow"/></w:rPr>'
            '<w:t>[Insert State]</w:t></w:r></w:p></w:body></w:document>'
        )
        patched = mbp.apply_changes(xml, {0: "California "}, set())
        self.assertIn('xml:space="preserve">California </w:t>', patched)


class TestMergeDocx(unittest.TestCase):
    def test_merge_preserves_package_and_replaces_yellow(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            template = tmp_path / "template.docx"
            output = tmp_path / "output.docx"
            input_md = tmp_path / "input.md"

            write_minimal_docx(template)
            input_md.write_text(MINIMAL_INPUT, encoding="utf-8")
            values = mbp.parse_input_md(input_md)

            count = mbp.merge_docx(template, output, values)
            self.assertEqual(count, 1)

            with zipfile.ZipFile(template) as zt, zipfile.ZipFile(output) as zo:
                tpl_doc = zt.read("word/document.xml")
                out_doc = zo.read("word/document.xml")
                for name in zt.namelist():
                    if name != "word/document.xml":
                        self.assertEqual(zt.read(name), zo.read(name))

            self.assertEqual(
                DOC_ROOT_RE.search(tpl_doc).group(0),
                DOC_ROOT_RE.search(out_doc).group(0),
            )
            out_text = out_doc.decode("utf-8")
            self.assertIn("$428,000", out_text)
            self.assertNotIn("[$Loan Amount$]", out_text)
            self.assertEqual(len(EMPTY_WT_RE.findall(out_text)), 0)


class TestWhiteTextMap(unittest.TestCase):
    def test_listed_white_phrase_replaced_and_other_white_text_kept(self):
        xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            f'<w:document xmlns:w="{W_NS}"><w:body><w:p>'
            '<w:r><w:t>(representing [XX]% of total costs)</w:t></w:r>'
            '<w:r><w:t>[X] stays white</w:t></w:r>'
            '</w:p></w:body></w:document>'
        )
        values = {"equity_percent": "0%"}
        patches, deletes, count = mbp.collect_changes(
            mbp.ET.fromstring(xml.encode("utf-8")), values
        )
        patched = mbp.apply_changes(xml, patches, deletes)
        self.assertEqual(count, 1)
        self.assertIn("(representing 0% of total costs)", patched)
        self.assertIn("[X] stays white", patched)


if __name__ == "__main__":
    unittest.main()
