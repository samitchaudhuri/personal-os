#!/usr/bin/env python3
"""Assemble a combined .pptx by merging Markdown- and PowerPoint-sourced slides.

Reads a **deck note** (``<deck> Deck.md`` in the vault). The note's **deck manifest**
table defines final slide order and source tags (``S1…Sn`` from Markdown sources,
``H1…Hm`` from PowerPoint sources, etc.). Frontmatter lists those sources under
``markdown_sources`` and ``pptx_sources``.

The first listed PowerPoint source *is* the output's starting point. Markdown slides
are generated into that file; PowerPoint-sourced slides get chrome stamped from the
deck manifest; Markdown slide chrome is validated against it. Then slide order is
rearranged to match the manifest.

Usage:
  combine-pptx.py "<brief.md>" "<png-dir>" "<out.pptx>" "<deck-note.md>" ["<theme.json>"]
"""

import importlib.util
import re
import sys
from pathlib import Path

import yaml
from pptx import Presentation

# Import the sibling generator (hyphenated filename → load by path).
_B2P_PATH = Path(__file__).resolve().parent / "brief-to-pptx.py"
_spec = importlib.util.spec_from_file_location("brief_to_pptx", _B2P_PATH)
b2p = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(b2p)

TOKEN_RE = re.compile(r"^(S\d+|[A-Z]+\d+)$")
BUILD_DIR = Path(__file__).resolve().parent.parent / "build"
VAULT_NOTES = Path(__file__).resolve().parent.parent.parent / "vault" / "Notes"


def parse_frontmatter(path):
    """Return the YAML frontmatter dict from a markdown note."""
    text = Path(path).read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    try:
        data = yaml.safe_load(text[3:end]) or {}
    except yaml.YAMLError as exc:
        b2p.fail(f"Invalid YAML frontmatter in {path}: {exc}")
    return data if isinstance(data, dict) else {}


def _normalize_source(entry, source_count, default_prefix, property_name):
    """Return ``{file, prefix}`` for one source-list entry."""
    if isinstance(entry, str):
        file_stem = entry.strip()
        if not file_stem:
            b2p.fail(f"{property_name} entries must not be empty strings.")
        prefix = default_prefix if source_count == 1 else None
        if prefix is None:
            b2p.fail(
                f"Multiple {property_name} require an explicit prefix per entry "
                f"(e.g. `- file: …` / `prefix: …`)."
            )
        return {"file": file_stem, "prefix": prefix}

    if isinstance(entry, dict):
        file_stem = (entry.get("file") or entry.get("stem") or "").strip()
        if not file_stem:
            b2p.fail(f"Each {property_name} entry needs a file stem (file: …).")
        prefix = (entry.get("prefix") or "").strip().upper()
        if not prefix:
            if source_count == 1:
                prefix = default_prefix
            else:
                b2p.fail(
                    f"{property_name} entry '{file_stem}' needs an explicit prefix "
                    f"when multiple sources are declared."
                )
        if not re.fullmatch(r"[A-Z]+", prefix):
            b2p.fail(f"{property_name} prefix must be uppercase letters (got {prefix!r}).")
        return {"file": file_stem, "prefix": prefix}

    b2p.fail(
        f"{property_name} entries must be a file stem string or a mapping "
        f"with file and optional prefix."
    )


def _parse_sources(manifest_path, key, default_prefix, required=True, legacy_key=None):
    fm = parse_frontmatter(manifest_path)
    raw = fm.get(key)
    if raw is None and legacy_key and fm.get(legacy_key):
        raw = [fm[legacy_key]]
    if not raw:
        if not required:
            return []
        b2p.fail(
            f"No '{key}' in frontmatter of {manifest_path} — declare sources, e.g.\n"
            f"  {key}:\n"
            f"    - file: ORAM Company Pitch\n"
            f"      prefix: {default_prefix}"
        )
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list) or not raw:
        b2p.fail(f"{key} in {manifest_path} must be a non-empty list.")

    sources = [_normalize_source(entry, len(raw), default_prefix, key) for entry in raw]
    prefixes = [s["prefix"] for s in sources]
    if len(set(prefixes)) != len(prefixes):
        b2p.fail(f"Duplicate {key} prefixes in {manifest_path}: {prefixes}")
    return sources


def parse_markdown_sources(manifest_path):
    """Marp slide sources declared in manifest frontmatter."""
    return _parse_sources(manifest_path, "markdown_sources", "S")


def parse_pptx_sources(manifest_path):
    """External ``.pptx`` sources declared in manifest frontmatter."""
    return _parse_sources(
        manifest_path, "pptx_sources", "H", legacy_key="hwbase"
    )


def resolve_markdown_sources(manifest_path):
    """Resolve ``vault/Notes/<file>.marp.md`` for each declared markdown source."""
    resolved = []
    for src in parse_markdown_sources(manifest_path):
        marp_path = VAULT_NOTES / f"{src['file']}.marp.md"
        if not marp_path.exists():
            b2p.fail(
                f"Marp source not found: {marp_path} "
                f"(markdown_sources in {manifest_path})"
            )
        resolved.append({**src, "path": marp_path})
    return resolved


def resolve_pptx_sources(manifest_path):
    """Resolve ``presentations/build/<file>.pptx`` for each declared source."""
    resolved = []
    for src in parse_pptx_sources(manifest_path):
        base_path = BUILD_DIR / f"{src['file']}.pptx"
        if not base_path.exists():
            b2p.fail(
                f"External slide deck not found: {base_path} "
                f"(pptx_sources in {manifest_path})"
            )
        resolved.append({**src, "path": base_path})
    return resolved


def parse_tag_prefix(tag):
    """Return the uppercase prefix from ``S3`` / ``H1``-style tags, else ``None``."""
    m = re.match(r"^([A-Z]+)(\d+)$", tag)
    return m.group(1) if m else None


def _manifest_header_indices(cells):
    """Column map if this header row starts a deck-manifest table, else ``None``.

    Skips summary tables (e.g. Half | Source | … listing file paths) that have
    ``Source`` but not ``Title`` or ``Narrative Role``.
    """
    cols = {}
    for i, c in enumerate(cells):
        key = c.lower().strip()
        if key == "source":
            cols["source"] = i
        elif "narrative role" in key or key == "role":
            cols["role"] = i
        elif key == "title":
            cols["title"] = i
        elif key == "takeaway":
            cols["takeaway"] = i
    if "source" not in cols:
        return None
    if "title" not in cols and "role" not in cols:
        return None
    return cols


def _normalize_source_tag(cell):
    return cell.strip().strip("`").strip()


def parse_spine_metadata(path):
    """Return ``{source_tag: {role, title, takeaway}}`` from the deck manifest table."""
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    best = {}
    cols = None
    meta = {}
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("|"):
            if cols is not None:
                if len(meta) > len(best):
                    best = meta
                cols = None
                meta = {}
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if all(re.fullmatch(r":?-+:?", c) for c in cells if c):
            continue
        if cols is None:
            cols = _manifest_header_indices(cells)
            continue
        if cols["source"] >= len(cells):
            continue
        tag = _normalize_source_tag(cells[cols["source"]])
        if not TOKEN_RE.match(tag):
            continue
        meta[tag] = {
            "role": cells[cols["role"]].strip() if "role" in cols and cols["role"] < len(cells) else "",
            "title": cells[cols["title"]].strip() if "title" in cols and cols["title"] < len(cells) else "",
            "takeaway": cells[cols["takeaway"]].strip() if "takeaway" in cols and cols["takeaway"] < len(cells) else "",
        }
    if cols is not None and len(meta) > len(best):
        best = meta
    if not best:
        b2p.fail(f"No deck manifest metadata found in {path} (table with Source column).")
    return best


def parse_manifest(path):
    """Return the ordered list of source tags from the deck manifest table."""
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    best = []
    cols = None
    tags = []
    saw_manifest_header = False
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("|"):
            if cols is not None:
                if len(tags) > len(best):
                    best = tags
                cols = None
                tags = []
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if all(re.fullmatch(r":?-+:?", c) for c in cells if c):
            continue
        if cols is None:
            cols = _manifest_header_indices(cells)
            if cols is not None:
                saw_manifest_header = True
            continue
        if cols["source"] >= len(cells):
            continue
        tag = _normalize_source_tag(cells[cols["source"]])
        if TOKEN_RE.match(tag):
            tags.append(tag)
    if cols is not None and len(tags) > len(best):
        best = tags
    if not saw_manifest_header:
        b2p.fail(f"No table with a 'Source' column found in {path}")
    if not best:
        b2p.fail(f"Found a 'Source' column but no source tags in {path}")
    return best


def combine(brief_path, png_dir, out_path, manifest_path, theme_path=None):
    if theme_path:
        b2p.load_theme(theme_path)

    md_sources = resolve_markdown_sources(manifest_path)
    pptx_sources = resolve_pptx_sources(manifest_path)

    if len(md_sources) > 1:
        b2p.fail(
            "Multiple markdown_sources are declared but combine currently supports "
            "one Marp deck — use a single entry until multi-source merge is implemented."
        )
    if len(pptx_sources) > 1:
        b2p.fail(
            "Multiple pptx_sources are declared but combine currently supports "
            "one external deck — use a single entry until multi-source merge "
            "is implemented."
        )

    md = md_sources[0]
    md_prefix = md["prefix"]
    base = pptx_sources[0]
    base_path = base["path"]
    base_stem = base["file"]
    ext_prefix = base["prefix"]

    md_prefixes = {s["prefix"] for s in md_sources}
    pptx_prefixes = {s["prefix"] for s in pptx_sources}
    all_prefixes = md_prefixes | pptx_prefixes

    slides = b2p.parse_brief(Path(brief_path).read_text(encoding="utf-8"))
    order = parse_manifest(manifest_path)
    spine = parse_spine_metadata(manifest_path)

    md_tags = [t for t in order if parse_tag_prefix(t) in md_prefixes]
    ext_tags = [t for t in order if parse_tag_prefix(t) in pptx_prefixes]

    for tag in order:
        prefix = parse_tag_prefix(tag)
        if prefix and prefix not in all_prefixes:
            b2p.fail(
                f"Deck manifest tag {tag} uses prefix {prefix} but no matching entry "
                f"in markdown_sources or pptx_sources "
                f"(declared: {sorted(all_prefixes)})."
            )
        if tag not in spine:
            b2p.fail(f"Source tag {tag} missing from deck manifest in {manifest_path}.")

    chrome_errors = []
    for idx, slide in enumerate(slides, start=1):
        tag = f"{md_prefix}{idx}"
        mismatches = b2p.validate_markdown_chrome(tag, slide, spine[tag])
        if mismatches:
            chrome_errors.append(f"{tag}: " + "; ".join(mismatches))
    if chrome_errors:
        b2p.fail(
            "Markdown slide chrome does not match the deck manifest "
            f"(edit [[{md['file']}.marp]] or the deck manifest table):\n"
            + "\n".join(chrome_errors)
        )

    if len(md_tags) != len(slides):
        b2p.fail(
            f"Deck manifest lists {len(md_tags)} markdown slides ({md_prefix}#) but the "
            f"brief has {len(slides)}. Reconcile {manifest_path} with "
            f"{md['path'].name}."
        )

    prs = Presentation(base_path)
    prs.slide_width = b2p.SLIDE_W
    prs.slide_height = b2p.SLIDE_H
    blank = b2p.pick_blank_layout(prs)

    sld_id_lst = prs.slides._sldIdLst
    base_ids = list(sld_id_lst)
    n_ext = len(base_ids)
    if len(ext_tags) != n_ext:
        b2p.fail(
            f"Deck manifest lists {len(ext_tags)} PowerPoint slides ({ext_prefix}#) "
            f"but {base_path} has {n_ext} slides."
        )

    for idx, s in enumerate(slides, start=1):
        tag = f"{md_prefix}{idx}"
        final_pos = order.index(tag) + 1
        b2p.render_slide(prs, blank, s, final_pos, png_dir)

    missing_chrome = []
    for k in range(n_ext):
        tag = f"{ext_prefix}{k + 1}"
        final_pos = order.index(tag) + 1
        slide = prs.slides[k]
        row = spine[tag]
        if not b2p.update_slide_number(slide, final_pos):
            missing_chrome.append(f"{tag} (number)")
        for field in b2p.stamp_pptx_slide_chrome(slide, row):
            missing_chrome.append(f"{tag} ({field})")
    if missing_chrome:
        b2p.fail(
            f"Could not update slide chrome on PowerPoint slide(s): "
            f"{', '.join(missing_chrome)}. Each PowerPoint source slide needs chrome "
            f"textboxes matching the generated layout (number, kicker, title, takeaway)."
        )

    md_ids = list(sld_id_lst)[n_ext:]

    tag_to_el = {f"{ext_prefix}{k + 1}": el for k, el in enumerate(base_ids)}
    tag_to_el.update({f"{md_prefix}{k + 1}": el for k, el in enumerate(md_ids)})

    for el in list(sld_id_lst):
        sld_id_lst.remove(el)
    for tag in order:
        if tag not in tag_to_el:
            b2p.fail(f"Deck manifest source tag {tag} has no matching slide.")
        sld_id_lst.append(tag_to_el[tag])

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    prs.save(out_path)
    print(
        f"Wrote {out_path} ({len(order)} slides: {n_ext} PowerPoint + {len(slides)} "
        f"markdown; base={base_stem}.pptx [{ext_prefix}#], marp={md['file']}.marp.md "
        f"[{md_prefix}#], ordered per {Path(manifest_path).name})."
    )


if __name__ == "__main__":
    if len(sys.argv) not in (5, 6):
        b2p.fail(
            'Usage: combine-pptx.py "<brief.md>" "<png-dir>" "<out.pptx>" '
            '"<manifest.md>" ["<theme.json>"]'
        )
    theme = sys.argv[5] if len(sys.argv) == 6 else None
    combine(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], theme)
