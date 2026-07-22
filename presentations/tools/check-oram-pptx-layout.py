#!/usr/bin/env python3
"""Verify brief-to-pptx.py load_layout() matches themes/oram-common.json."""

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMMON_PATH = ROOT / "themes" / "oram-common.json"
B2P_PATH = Path(__file__).resolve().parent / "brief-to-pptx.py"


def load_b2p():
    spec = importlib.util.spec_from_file_location("brief_to_pptx", B2P_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def approx(actual, expected, label):
    if abs(actual - expected) > 1e-6:
        sys.stderr.write(f"FAIL {label}: expected {expected}, got {actual}\n")
        return False
    print(f"ok {label}")
    return True


def length_inches(value):
    if hasattr(value, "inches"):
        return value.inches
    return value / 914400


def main():
    common = json.loads(COMMON_PATH.read_text(encoding="utf-8"))
    b2p = load_b2p()
    b2p.load_layout(COMMON_PATH)

    ok = True
    slide = common["slide"]
    layout = common["layout"]
    pptx = common["typography"]["pptx"]

    checks = [
        ("slide width", length_inches(b2p.SLIDE_W), slide["widthIn"]),
        ("slide height", length_inches(b2p.SLIDE_H), slide["heightIn"]),
        ("margin", length_inches(b2p.MARGIN), layout["marginIn"]),
        ("chrome top", length_inches(b2p.CHROME_TOP), layout["chromeTopIn"]),
        ("kicker height", length_inches(b2p.KICKER_H), layout["kickerHeightIn"]),
        ("gap after kicker", length_inches(b2p.GAP_AFTER_KICKER), layout["gapAfterKickerIn"]),
        ("gap after title", length_inches(b2p.GAP_AFTER_TITLE), layout["gapAfterTitleIn"]),
        ("gap after diagram", length_inches(b2p.GAP_AFTER_DIAGRAM), layout["gapAfterDiagramIn"]),
        ("takeaway bottom", length_inches(b2p.TAKEAWAY_BOTTOM), layout["takeawayBottomIn"]),
        ("takeaway band height", length_inches(b2p.TAKEAWAY_BAND_H), layout["takeawayBandHeightIn"]),
        ("max diagram height", length_inches(b2p.MAX_DIAGRAM_H), layout["diagramMaxHeightPx"] / 96),
        ("body height pad", length_inches(b2p.BODY_HEIGHT_PAD), layout["bodyHeightPadIn"]),
        ("title line height", b2p.TITLE_LINE_HEIGHT, layout["titleLineHeight"]),
        ("title box pad", length_inches(b2p.TITLE_BOX_PAD), layout["titleBoxPadIn"]),
        ("body line spacing", b2p.BODY_LINE_SPACING, pptx["bodyLineSpacing"]),
        ("takeaway text inset", length_inches(b2p.TAKEAWAY_TEXT_INSET), pptx["takeawayTextInsetIn"]),
        (
            "content width",
            length_inches(b2p.CONTENT_W),
            slide["widthIn"] - 2 * layout["marginIn"],
        ),
    ]

    for label, actual, expected in checks:
        if not approx(actual, expected, f"brief-to-pptx {label}"):
            ok = False

    if not ok:
        sys.exit(1)

    print("All brief-to-pptx layout checks passed.")


if __name__ == "__main__":
    main()
