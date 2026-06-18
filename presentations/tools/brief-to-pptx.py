#!/usr/bin/env python3
"""Build a .pptx from a generated PPT brief.

Deterministic local alternative to the Claude PowerPoint connector. Reads the
brief produced by marp-to-ppt-brief.js and renders one slide per "## Slide N"
section, placing each diagram full-width below the body text (the layout the
connector got wrong). Diagrams are embedded as PNGs (python-pptx cannot embed
SVG), so render PNGs first and pass their directory.

Usage:
  brief-to-pptx.py "<brief.md>" "<png-dir>" "<out.pptx>" ["<palette.json>"]

The optional palette JSON themes the slide chrome (parallel to the Mermaid
theme that themes the diagrams). Recognized keys: ink, accent, takeawayFill,
takeawayText. Missing keys fall back to the built-in defaults below.
"""

import json
import re
import struct
import sys
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Inches, Pt

# Palette defaults (matches the deck's restrained blue accent). Overridable via
# a pptx-themes/<name>.json file; see load_palette().
ACCENT = RGBColor(0x4A, 0x6F, 0xA5)
INK = RGBColor(0x1A, 0x1A, 0x1A)
TAKEAWAY_FILL = RGBColor(0xE8, 0xEE, 0xF6)
TAKEAWAY_TEXT = RGBColor(0x1A, 0x1A, 0x1A)


def load_palette(path):
    """Override the module-level color globals from a palette JSON file."""
    global ACCENT, INK, TAKEAWAY_FILL, TAKEAWAY_TEXT
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    mapping = {
        "ink": "INK",
        "accent": "ACCENT",
        "takeawayFill": "TAKEAWAY_FILL",
        "takeawayText": "TAKEAWAY_TEXT",
    }
    for key, name in mapping.items():
        if key in data and data[key]:
            globals()[name] = RGBColor.from_string(str(data[key]).lstrip("#"))

SLIDE_W = Inches(13.333)
SLIDE_H = Inches(7.5)
MARGIN = Inches(0.7)
CONTENT_W = SLIDE_W - 2 * MARGIN


def fail(msg):
    sys.stderr.write(f"Error: {msg}\n")
    sys.exit(1)


def png_size(path):
    with open(path, "rb") as f:
        head = f.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"Not a PNG: {path}")
    w, h = struct.unpack(">II", head[16:24])
    return w, h


def parse_brief(text):
    # Drop everything before the first slide section.
    idx = text.find("\n## Slide ")
    if idx == -1:
        fail("No '## Slide N' sections found in brief.")
    body = text[idx:]
    chunks = re.split(r"\n## Slide \d+\s*\n", body)
    chunks = [c for c in chunks if c.strip()]
    return [parse_slide(c) for c in chunks]


def _field(chunk, label):
    m = re.search(rf"^\*\*{label}:\*\*\s*(.+)$", chunk, re.MULTILINE)
    return m.group(1).strip() if m else None


def _block(chunk, label):
    # Capture a multi-line block starting at **Label:** until the next **Field:** or end.
    m = re.search(
        rf"^\*\*{label}:\*\*\s*\n(.*?)(?=\n\*\*[A-Z][a-z]+:\*\*|\Z)",
        chunk,
        re.MULTILINE | re.DOTALL,
    )
    return m.group(1).strip() if m else None


def parse_slide(chunk):
    slide = {
        "kicker": _field(chunk, "Kicker"),
        "title": _field(chunk, "Title"),
        "takeaway": _field(chunk, "Takeaway"),
        "body": _block(chunk, "Body"),
        "notes": _block(chunk, "Notes"),
        "diagram": None,
    }
    dm = re.search(r"^\*\*Diagram:\*\*\s*`([^`]+)`", chunk, re.MULTILINE)
    if dm:
        slide["diagram"] = Path(dm.group(1)).stem  # strip .svg
    return slide


def add_rich_text(paragraph, text, size=None, color=None):
    """Render inline **bold** markup into runs."""
    for i, part in enumerate(re.split(r"\*\*(.+?)\*\*", text)):
        if not part:
            continue
        run = paragraph.add_run()
        run.text = part
        run.font.bold = i % 2 == 1
        if size is not None:
            run.font.size = size
        if color is not None:
            run.font.color.rgb = color


def set_body(tf, body):
    tf.word_wrap = True
    first = True
    for raw in body.split("\n"):
        line = raw.rstrip()
        if not line:
            continue
        heading = re.match(r"^#{1,6}\s+(.*)$", line)
        bullet = line.startswith("- ")
        para = tf.paragraphs[0] if first else tf.add_paragraph()
        first = False
        para.space_after = Pt(4)
        para.level = 0
        if heading:
            # Markdown heading inside the body → bold lead-in (matches Obsidian).
            para.space_before = Pt(6)
            add_rich_text(para, heading.group(1), size=Pt(17), color=INK)
            for run in para.runs:
                run.font.bold = True
        elif bullet:
            add_rich_text(para, line[2:], size=Pt(16), color=INK)
            if para.runs:
                # Visual bullet via prefix (keeps layout deterministic across renderers).
                para.runs[0].text = "•  " + para.runs[0].text
        else:
            add_rich_text(para, line, size=Pt(16), color=INK)


def build(brief_path, png_dir, out_path, palette_path=None):
    if palette_path:
        load_palette(palette_path)
    text = Path(brief_path).read_text(encoding="utf-8")
    slides = parse_brief(text)

    prs = Presentation()
    prs.slide_width = SLIDE_W
    prs.slide_height = SLIDE_H
    blank = prs.slide_layouts[6]

    total = len(slides)
    for i, s in enumerate(slides, start=1):
        slide = prs.slides.add_slide(blank)
        top = Inches(0.45)

        # Auto slide number, top-right, aligned with the kicker line.
        num_w = Inches(1.2)
        nbox = slide.shapes.add_textbox(Emu(SLIDE_W - MARGIN - num_w), top, num_w, Inches(0.3))
        npara = nbox.text_frame.paragraphs[0]
        npara.alignment = PP_ALIGN.RIGHT
        nrun = npara.add_run()
        nrun.text = str(i)
        nrun.font.size = Pt(13)
        nrun.font.bold = True
        nrun.font.color.rgb = ACCENT

        if s["kicker"]:
            box = slide.shapes.add_textbox(MARGIN, top, CONTENT_W, Inches(0.3))
            p = box.text_frame.paragraphs[0]
            r = p.add_run()
            r.text = s["kicker"].upper()
            r.font.size = Pt(13)
            r.font.bold = True
            r.font.color.rgb = ACCENT
            top = Emu(top + Inches(0.4))

        if s["title"]:
            box = slide.shapes.add_textbox(MARGIN, top, CONTENT_W, Inches(0.9))
            p = box.text_frame.paragraphs[0]
            r = p.add_run()
            r.text = s["title"]
            r.font.size = Pt(28)
            r.font.bold = True
            r.font.color.rgb = INK
            top = Emu(top + Inches(0.95))

        # Vertical budget: content lives between `top` and the takeaway band.
        takeaway_h = Inches(0.85) if s["takeaway"] else Inches(0.0)
        zone_top = top
        zone_bottom = Emu(SLIDE_H - Inches(0.35) - takeaway_h)
        zone_h = zone_bottom - zone_top

        # Flow: diagram first (visual anchor), then body below — matches the Marp PDF.
        cursor = zone_top
        if s["diagram"]:
            png = Path(png_dir) / f"{s['diagram']}.png"
            if not png.exists():
                fail(f"Diagram PNG not found: {png}")
            pw, ph = png_size(png)
            ratio = pw / ph
            max_h = int(zone_h * 0.6)  # cap so the body keeps room below
            w = CONTENT_W
            h = int(CONTENT_W / ratio)
            if h > max_h:
                h = max_h
                w = int(max_h * ratio)
            left = Emu(MARGIN + (CONTENT_W - w) // 2)
            slide.shapes.add_picture(str(png), left, cursor, width=Emu(w), height=Emu(h))
            cursor = Emu(cursor + h + Inches(0.2))

        if s["body"]:
            box = slide.shapes.add_textbox(MARGIN, cursor, CONTENT_W, Emu(zone_bottom - cursor))
            set_body(box.text_frame, s["body"])

        if s["takeaway"]:
            band = slide.shapes.add_shape(
                MSO_SHAPE.ROUNDED_RECTANGLE,
                MARGIN,
                Emu(SLIDE_H - Inches(0.35) - takeaway_h),
                CONTENT_W,
                takeaway_h,
            )
            band.fill.solid()
            band.fill.fore_color.rgb = TAKEAWAY_FILL
            band.line.fill.background()
            band.shadow.inherit = False
            tf = band.text_frame
            tf.word_wrap = True
            tf.vertical_anchor = MSO_ANCHOR.MIDDLE
            tf.margin_left = Inches(0.2)
            tf.margin_right = Inches(0.2)
            p = tf.paragraphs[0]
            lead = p.add_run()
            lead.text = "Takeaway:  "
            lead.font.bold = True
            lead.font.size = Pt(15)
            lead.font.color.rgb = ACCENT
            add_rich_text(p, s["takeaway"], size=Pt(15), color=TAKEAWAY_TEXT)

        if s["notes"]:
            slide.notes_slide.notes_text_frame.text = s["notes"]

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    prs.save(out_path)
    print(f"Wrote {out_path} ({len(slides)} slides).")


if __name__ == "__main__":
    if len(sys.argv) not in (4, 5):
        fail('Usage: brief-to-pptx.py "<brief.md>" "<png-dir>" "<out.pptx>" ["<palette.json>"]')
    palette = sys.argv[4] if len(sys.argv) == 5 else None
    build(sys.argv[1], sys.argv[2], sys.argv[3], palette)
