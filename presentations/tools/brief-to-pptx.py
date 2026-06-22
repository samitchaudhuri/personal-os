#!/usr/bin/env python3
"""Build a .pptx from a generated PPT brief.

Deterministic local alternative to the Claude PowerPoint connector. Reads the
brief produced by marp-to-ppt-brief.js and renders one slide per "## Slide N"
section, placing each diagram full-width below the body text (the layout the
connector got wrong). Diagrams are embedded as PNGs (python-pptx cannot embed
SVG), so render PNGs first and pass their directory.

Usage:
  brief-to-pptx.py "<brief.md>" "<png-dir>" "<out.pptx>" ["<palette.json>"]

The optional theme JSON themes the slide chrome (parallel to the Mermaid theme
that themes the diagrams). Recognized keys: font, background, ink, accent,
takeawayFill, takeawayText, showKicker, showSlideNumber, showTakeawayBand, and
sizes (title/kicker/body/heading/takeaway/number). Missing keys fall back to the
built-in defaults below, so older 4-color palettes still work.
"""

import json
import re
import struct
import sys
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE, MSO_SHAPE_TYPE
from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE, PP_ALIGN
from pptx.util import Emu, Inches, Pt

# Theme defaults (matches the deck's restrained blue accent on white). Every key
# is overridable via a pptx-themes/<name>.json file; see load_theme(). The whole
# chrome — colors, font, background, which elements show, and type sizes — is
# theme-driven so the deck can switch light/dark by pointing at another file.
ACCENT = RGBColor(0x4A, 0x6F, 0xA5)
INK = RGBColor(0x1A, 0x1A, 0x1A)
TAKEAWAY_FILL = RGBColor(0xE8, 0xEE, 0xF6)
TAKEAWAY_TEXT = RGBColor(0x1A, 0x1A, 0x1A)
BACKGROUND = RGBColor(0xFF, 0xFF, 0xFF)
FONT = None  # None → PowerPoint default; a theme sets e.g. "Helvetica Neue".
SHOW_KICKER = True
SHOW_SLIDE_NUMBER = True
SHOW_TAKEAWAY_BAND = True
SIZES = {"title": 28, "kicker": 13, "body": 16, "heading": 17, "takeaway": 15, "number": 13}


def load_theme(path):
    """Override the module-level chrome globals from a theme JSON file."""
    global ACCENT, INK, TAKEAWAY_FILL, TAKEAWAY_TEXT, BACKGROUND, FONT
    global SHOW_KICKER, SHOW_SLIDE_NUMBER, SHOW_TAKEAWAY_BAND, SIZES
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    colors = {
        "ink": "INK",
        "accent": "ACCENT",
        "takeawayFill": "TAKEAWAY_FILL",
        "takeawayText": "TAKEAWAY_TEXT",
        "background": "BACKGROUND",
    }
    for key, name in colors.items():
        if data.get(key):
            globals()[name] = RGBColor.from_string(str(data[key]).lstrip("#"))
    if data.get("font"):
        FONT = str(data["font"])
    toggles = {
        "showKicker": "SHOW_KICKER",
        "showSlideNumber": "SHOW_SLIDE_NUMBER",
        "showTakeawayBand": "SHOW_TAKEAWAY_BAND",
    }
    for key, name in toggles.items():
        if key in data:
            globals()[name] = bool(data[key])
    sizes = data.get("sizes")
    if isinstance(sizes, dict):
        SIZES = {**SIZES, **{k: int(v) for k, v in sizes.items() if v}}

SLIDE_W = Inches(13.333)
SLIDE_H = Inches(7.5)
MARGIN = Inches(0.7)
CONTENT_W = SLIDE_W - 2 * MARGIN

# Vertical chrome — tuned to match Marp PDF (tight h1→diagram gap, 300px diagram cap).
CHROME_TOP = Inches(0.4)
KICKER_H = Inches(0.2)
GAP_AFTER_KICKER = Inches(0.06)
GAP_AFTER_TITLE = Inches(0.1)
GAP_AFTER_DIAGRAM = Inches(0.12)
TAKEAWAY_BOTTOM = Inches(0.35)
MAX_DIAGRAM_H = Inches(300 / 96)  # ``section img { max-height: 300px }`` in the deck CSS


def _title_box_height(title):
    """Estimate title textbox height from line count at the theme title size."""
    line_h_in = SIZES["title"] / 72 * 1.3
    chars_per_line = 44
    lines = max(1, -(-len(title) // chars_per_line))
    return Inches(line_h_in * lines + 0.04)


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
        if FONT:
            run.font.name = FONT
        if size is not None:
            run.font.size = size
        if color is not None:
            run.font.color.rgb = color


def set_body(tf, body):
    """Render brief body markdown into a fixed-height text frame.

    Marp PDF uses tight list spacing (``li { margin: 0.025em }``). PowerPoint's
    default paragraph spacing is much looser; without explicit line spacing and
    minimal ``space_after`` on bullets, body text overflows the vertical budget.
    """
    tf.word_wrap = True
    tf.auto_size = MSO_AUTO_SIZE.NONE
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = Pt(0)

    lines = [raw.rstrip() for raw in body.split("\n") if raw.strip()]
    first = True
    for i, line in enumerate(lines):
        heading = re.match(r"^#{1,6}\s+(.*)$", line)
        bullet = line.startswith("- ")
        is_last = i == len(lines) - 1
        para = tf.paragraphs[0] if first else tf.add_paragraph()
        first = False
        para.level = 0
        para.line_spacing = 1.15  # between Marp ``line-height: 1.22`` and single-spaced
        if heading:
            para.space_before = Pt(4)
            para.space_after = Pt(3)
            add_rich_text(para, heading.group(1), size=Pt(SIZES["heading"]), color=INK)
            for run in para.runs:
                run.font.bold = True
        elif bullet:
            para.space_before = Pt(0)
            para.space_after = Pt(2 if not is_last else 3)
            add_rich_text(para, line[2:], size=Pt(SIZES["body"]), color=INK)
            if para.runs:
                # Visual bullet via prefix (keeps layout deterministic across renderers).
                para.runs[0].text = "•  " + para.runs[0].text
        else:
            para.space_before = Pt(0)
            para.space_after = Pt(3 if is_last else 2)
            add_rich_text(para, line, size=Pt(SIZES["body"]), color=INK)


def pick_blank_layout(prs):
    """Choose the best blank-like layout for generated slides.

    A fresh ``Presentation()`` has a blank at index 6 with only footer/date
    placeholders. Externally-authored bases name a layout ``Blank`` but still attach
    a slide-number placeholder — and index 6 is *not* blank (often a Title
    layout). Prefer an explicitly named Blank layout, then any layout without
    title placeholders, before falling back to index 6.
    """
    from pptx.enum.shapes import PP_PLACEHOLDER

    title_types = {PP_PLACEHOLDER.TITLE, PP_PLACEHOLDER.CENTER_TITLE}

    for layout in prs.slide_layouts:
        if layout.name.strip().lower() == "blank":
            return layout

    for layout in prs.slide_layouts:
        if len(layout.placeholders) == 0:
            return layout

    without_title = [
        layout
        for layout in prs.slide_layouts
        if not any(ph.placeholder_format.type in title_types for ph in layout.placeholders)
    ]
    if without_title:
        return min(without_title, key=lambda layout: len(layout.placeholders))

    try:
        return prs.slide_layouts[6]
    except IndexError:
        return prs.slide_layouts[-1]


def clear_slide_placeholders(slide):
    """Remove inherited layout placeholders so generated chrome is not obscured."""
    for ph in list(slide.placeholders):
        el = ph.element
        el.getparent().remove(el)


def find_slide_number_shape(slide):
    """Return the top-right chrome textbox that holds the slide number.

    Assumes PowerPoint source slides were hand-fitted with the same number placement as
    ``render_slide`` (numeric text, upper-right band). Picks the rightmost match.
    """
    top_max = int(SLIDE_H * 0.18)
    right_min = int(SLIDE_W * 0.75)
    best = None
    best_left = -1
    for shape in slide.shapes:
        if not shape.has_text_frame:
            continue
        text = shape.text_frame.text.strip()
        if not re.fullmatch(r"\d{1,3}", text):
            continue
        if shape.top > top_max:
            continue
        if shape.left + shape.width < right_min:
            continue
        if shape.left > best_left:
            best_left = shape.left
            best = shape
    return best


def update_slide_number(slide, number):
    """Set the slide-number chrome text to ``number`` (combined-deck position)."""
    if not SHOW_SLIDE_NUMBER:
        return False
    shape = find_slide_number_shape(slide)
    if shape is None:
        return False
    text = str(number)
    tf = shape.text_frame
    para = tf.paragraphs[0]
    para.alignment = PP_ALIGN.RIGHT
    if para.runs:
        para.runs[0].text = text
        for run in para.runs[1:]:
            run.text = ""
    else:
        para.add_run().text = text
    for extra in tf.paragraphs[1:]:
        for run in extra.runs:
            run.text = ""
    return True


def _set_shape_text(shape, text, uppercase=False):
    """Replace a textbox with ``text``, preserving formatting on the first run."""
    if not shape or not shape.has_text_frame:
        return False
    text = text.upper() if uppercase else text
    tf = shape.text_frame
    para = tf.paragraphs[0]
    if para.runs:
        para.runs[0].text = text
        for run in para.runs[1:]:
            run.text = ""
    else:
        para.text = text
    for extra in tf.paragraphs[1:]:
        for run in extra.runs:
            run.text = ""
    return True


def find_kicker_shape(slide):
    """Top-left chrome label (Narrative Role / kicker band)."""
    top_max = int(SLIDE_H * 0.16)
    left_max = int(MARGIN + Inches(0.3))
    best = None
    best_top = 10**9
    for shape in slide.shapes:
        if not shape.has_text_frame:
            continue
        if shape.top > top_max or shape.left > left_max:
            continue
        text = shape.text_frame.text.strip()
        if re.fullmatch(r"\d{1,3}", text):
            continue
        if shape.height > int(Inches(0.45)):
            continue
        if shape.top < best_top:
            best_top = shape.top
            best = shape
    return best


def _shape_key(shape):
    """Stable identity for a shape (``id()`` is not reliable across pptx iterators)."""
    return (shape.top, shape.left, shape.width, shape.height)


def find_title_shape(slide):
    """Title textbox below the kicker, above the body zone."""
    top_max = int(SLIDE_H * 0.28)
    left_max = int(MARGIN + Inches(0.3))
    skip_keys = set()
    for finder in (find_slide_number_shape, find_kicker_shape):
        found = finder(slide)
        if found:
            skip_keys.add(_shape_key(found))
    best = None
    best_top = -1
    for shape in slide.shapes:
        if _shape_key(shape) in skip_keys or not shape.has_text_frame:
            continue
        if shape.top > top_max or shape.left > left_max:
            continue
        if shape.text_frame.text.strip().lower().startswith("takeaway"):
            continue
        if shape.height < int(Inches(0.35)):
            continue
        if shape.top > best_top:
            best_top = shape.top
            best = shape
    return best


def find_takeaway_shape(slide):
    """Bottom takeaway band (rounded rectangle or textbox)."""
    bottom_min = int(SLIDE_H * 0.62)
    best = None
    best_top = -1
    for shape in slide.shapes:
        if not shape.has_text_frame:
            continue
        if shape.top < bottom_min:
            continue
        text = shape.text_frame.text.strip().lower()
        if "takeaway" in text or shape.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE:
            if shape.top > best_top:
                best_top = shape.top
                best = shape
    return best


def update_slide_kicker(slide, role):
    if not SHOW_KICKER:
        return False
    return _set_shape_text(find_kicker_shape(slide), role, uppercase=True)


def update_slide_title(slide, title):
    return _set_shape_text(find_title_shape(slide), title)


def update_slide_takeaway(slide, takeaway):
    if not SHOW_TAKEAWAY_BAND:
        return False
    shape = find_takeaway_shape(slide)
    if not shape:
        return False
    tf = shape.text_frame
    para = tf.paragraphs[0]
    para.alignment = PP_ALIGN.LEFT
    if len(para.runs) >= 2:
        para.runs[1].text = takeaway
        for run in para.runs[2:]:
            run.text = ""
    elif para.runs:
        if para.runs[0].text.strip().lower().startswith("takeaway"):
            para.runs[0].text = "Takeaway:  "
            if len(para.runs) == 1:
                para.add_run()
            para.runs[1].text = takeaway
        else:
            _set_shape_text(shape, f"Takeaway:  {takeaway}")
    else:
        lead = para.add_run()
        lead.text = "Takeaway:  "
        lead.font.bold = True
        para.add_run().text = takeaway
    return True


def normalize_chrome_text(text):
    """Normalize manifest/Marp chrome strings for comparison."""
    if not text:
        return ""
    t = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    t = t.replace("—", "-").replace("–", "-")
    t = re.sub(r"\s+", " ", t).strip()
    return t


def validate_markdown_chrome(tag, brief_slide, spine_row):
    """Return mismatch messages when Marp/brief chrome differs from the manifest."""
    mismatches = []
    exp_role = normalize_chrome_text(spine_row.get("role", "")).upper()
    got_role = normalize_chrome_text(brief_slide.get("kicker") or "").upper()
    if exp_role != got_role:
        mismatches.append(f"role/kicker: manifest {exp_role!r} vs Marp {got_role!r}")

    exp_title = normalize_chrome_text(spine_row.get("title", ""))
    got_title = normalize_chrome_text(brief_slide.get("title") or "")
    if exp_title != got_title:
        mismatches.append(f"title: manifest {exp_title!r} vs Marp {got_title!r}")

    exp_tw = normalize_chrome_text(spine_row.get("takeaway", ""))
    got_tw = normalize_chrome_text(brief_slide.get("takeaway") or "")
    if exp_tw != got_tw:
        mismatches.append(f"takeaway: manifest {exp_tw!r} vs Marp {got_tw!r}")

    return mismatches


def stamp_pptx_slide_chrome(slide, spine_row):
    """Write deck-manifest role/title/takeaway onto PowerPoint slide chrome. Returns missing fields."""
    missing = []
    if spine_row.get("role") and not update_slide_kicker(slide, spine_row["role"]):
        missing.append("kicker/role")
    if spine_row.get("title") and not update_slide_title(slide, spine_row["title"]):
        missing.append("title")
    if spine_row.get("takeaway") and not update_slide_takeaway(slide, spine_row["takeaway"]):
        missing.append("takeaway")
    return missing


def render_slide(prs, blank, s, number, png_dir):
    """Render one parsed slide dict onto a new slide appended to ``prs``.

    ``number`` is the value shown top-right — the standalone index when called
    from build(), or the final combined position when called by the combine
    step. Returns the created slide.
    """
    slide = prs.slides.add_slide(blank)
    clear_slide_placeholders(slide)

    # Slide background — lets a dark theme flip bg + ink together.
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = BACKGROUND

    top = CHROME_TOP

    # Slide number, top-right, aligned with the kicker line.
    if SHOW_SLIDE_NUMBER:
        num_w = Inches(1.2)
        nbox = slide.shapes.add_textbox(Emu(SLIDE_W - MARGIN - num_w), top, num_w, KICKER_H)
        npara = nbox.text_frame.paragraphs[0]
        npara.alignment = PP_ALIGN.RIGHT
        nrun = npara.add_run()
        nrun.text = str(number)
        nrun.font.size = Pt(SIZES["number"])
        nrun.font.bold = True
        nrun.font.color.rgb = ACCENT
        if FONT:
            nrun.font.name = FONT

    if s["kicker"] and SHOW_KICKER:
        box = slide.shapes.add_textbox(MARGIN, top, CONTENT_W, KICKER_H)
        tf = box.text_frame
        tf.auto_size = MSO_AUTO_SIZE.NONE
        tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = Pt(0)
        p = tf.paragraphs[0]
        r = p.add_run()
        r.text = s["kicker"].upper()
        r.font.size = Pt(SIZES["kicker"])
        r.font.bold = True
        r.font.color.rgb = ACCENT
        if FONT:
            r.font.name = FONT
        top = Emu(top + KICKER_H + GAP_AFTER_KICKER)

    if s["title"]:
        title_h = _title_box_height(s["title"])
        box = slide.shapes.add_textbox(MARGIN, top, CONTENT_W, title_h)
        tf = box.text_frame
        tf.auto_size = MSO_AUTO_SIZE.NONE
        tf.word_wrap = True
        tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = Pt(0)
        p = tf.paragraphs[0]
        r = p.add_run()
        r.text = s["title"]
        r.font.size = Pt(SIZES["title"])
        r.font.bold = True
        r.font.color.rgb = INK
        if FONT:
            r.font.name = FONT
        top = Emu(top + title_h + GAP_AFTER_TITLE)

    # Vertical budget: content lives between `top` and the takeaway band.
    show_takeaway = bool(s["takeaway"]) and SHOW_TAKEAWAY_BAND
    takeaway_h = Inches(0.85) if show_takeaway else Inches(0.0)
    zone_top = top
    zone_bottom = Emu(SLIDE_H - TAKEAWAY_BOTTOM - takeaway_h)
    zone_h = zone_bottom - zone_top

    # Flow: diagram then body — matches Marp slide order (title → diagram → bullets).
    cursor = zone_top
    if s["diagram"]:
        png = Path(png_dir) / f"{s['diagram']}.png"
        if not png.exists():
            fail(f"Diagram PNG not found: {png}")
        pw, ph = png_size(png)
        ratio = pw / ph
        max_h = min(int(zone_h * 0.55), int(MAX_DIAGRAM_H))
        w = CONTENT_W
        h = int(CONTENT_W / ratio)
        if h > max_h:
            h = max_h
            w = int(max_h * ratio)
        left = Emu(MARGIN + (CONTENT_W - w) // 2)
        slide.shapes.add_picture(str(png), left, cursor, width=Emu(w), height=Emu(h))
        cursor = Emu(cursor + h + GAP_AFTER_DIAGRAM)

    if s["body"]:
        box = slide.shapes.add_textbox(MARGIN, cursor, CONTENT_W, Emu(zone_bottom - cursor))
        set_body(box.text_frame, s["body"])

    if show_takeaway:
        band = slide.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE,
            MARGIN,
            Emu(SLIDE_H - TAKEAWAY_BOTTOM - takeaway_h),
            CONTENT_W,
            takeaway_h,
        )
        band.fill.solid()
        band.fill.fore_color.rgb = TAKEAWAY_FILL
        band.line.fill.background()
        band.shadow.inherit = False
        tf = band.text_frame
        tf.word_wrap = True
        tf.auto_size = MSO_AUTO_SIZE.NONE
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        tf.margin_left = Inches(0.2)
        tf.margin_right = Inches(0.2)
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.LEFT
        lead = p.add_run()
        lead.text = "Takeaway:  "
        lead.font.bold = True
        lead.font.size = Pt(SIZES["takeaway"])
        lead.font.color.rgb = ACCENT
        if FONT:
            lead.font.name = FONT
        add_rich_text(p, s["takeaway"], size=Pt(SIZES["takeaway"]), color=TAKEAWAY_TEXT)

    if s["notes"]:
        slide.notes_slide.notes_text_frame.text = s["notes"]

    return slide


def build(brief_path, png_dir, out_path, theme_path=None):
    if theme_path:
        load_theme(theme_path)
    text = Path(brief_path).read_text(encoding="utf-8")
    slides = parse_brief(text)

    prs = Presentation()
    prs.slide_width = SLIDE_W
    prs.slide_height = SLIDE_H
    blank = pick_blank_layout(prs)

    for i, s in enumerate(slides, start=1):
        render_slide(prs, blank, s, i, png_dir)

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    prs.save(out_path)
    print(f"Wrote {out_path} ({len(slides)} slides).")


if __name__ == "__main__":
    if len(sys.argv) not in (4, 5):
        fail('Usage: brief-to-pptx.py "<brief.md>" "<png-dir>" "<out.pptx>" ["<palette.json>"]')
    theme = sys.argv[4] if len(sys.argv) == 5 else None
    build(sys.argv[1], sys.argv[2], sys.argv[3], theme)
