# Slide build infrastructure

Reference for **commands, env vars, pipelines, and tools**. Slide authors normally use VS Code tasks (see [`README.md`](README.md)); this doc supports debugging and pipeline changes.

**Maintainer:** When you add or change build behavior (scripts under `tools/`, npm tasks, env vars, theme application, HW combine/staging), update **this file** in the same change. When author-facing HW/combine **policy** changes, update [[Slide Deck Development#HW slide theming at combine]] in the same change — pointers only in [`themes/README.md`](themes/README.md), not a second copy of policy.

---

## Entry points

`tools/resolve-deck-sources.js` reads one env var and returns all paths.

| Env var | When set | `buildMode` | Output prefix | Marp input | Theme from |
| --- | --- | --- | --- | --- | --- |
| **`DECK_NOTE`** | Path to `<deck> Deck.md` | `deck` | filename (`<name> Deck.md`) | `deck_sources` → marp entry | Deck note `deck_theme:` |
| **`MARP_INPUT`** | Path to `.marp.md` | `marp` | Marp filename stem | That file | Marp `deck_theme:` |

Without either var, scripts fail with a clear message. There is no default deck in `package.json`.

Optional **`THEME`** env overrides `deck_theme:` for one run.

Inspect resolution:

```bash
cd presentations
DECK_NOTE="../vault/Notes/ORAM Company Pitch Deck.md" node tools/resolve-deck-sources.js
MARP_INPUT="../vault/Notes/ORAM Software Slides.marp.md" node tools/resolve-deck-sources.js
```

---

## VS Code tasks (`.vscode/tasks.json`)

All build tasks use `tools/run-active-file.js`: pass `${file}`, set `DECK_NOTE` or `MARP_INPUT` from the filename, then run the npm script.

| Task | Open file | Runs |
| --- | --- | --- |
| Slides: Build PDF | `.marp.md` or ` Deck.md` | `build-slides` |
| Slides: Build PPTX | `.marp.md` or ` Deck.md` | `build-pptx` |
| Slides: Build Combined PPTX | ` Deck.md` only | `build-combined` |
| Slides: PPT brief + assets | `.marp.md` or ` Deck.md` | `build-ppt` |
| Slides: Extract Mermaid | `.marp.md` or ` Deck.md` | `slides:extract` |
| Slides: Finish (MEP fallback) | `.marp.md` or ` Deck.md` | `slides:finish` |
| Slides: Sync HW slides | (any) | `slides:sync-hw` |

Combine is blocked for `.marp.md` in `run-active-file.js` (`--deck-only`) and in `run-deck-python.js` (`requireDeckMode`).

### Hardware slide staging

Combined decks read HW PowerPoint from paths declared in deck note `deck_sources` (e.g. `project_repos/oram/docs/presentations/ORAM Hardware Slides.pptx`). Author workflow: [[Slide Deck Development#HW slide staging]].

```bash
cd presentations && npm run slides:sync-hw
```

VS Code task: **Slides: Sync HW slides**. Implementation: `tools/sync-hw-slides.js`. See `project_repos/oram/docs/presentations/README.md`.

### HW slide theming at combine

Author-facing policy and conventions: [[Slide Deck Development#HW slide theming at combine]]. This section adds implementation detail.

When you build with `deck_theme: oram-dark` or `THEME=oram-dark`, combine stamps **PowerPoint-sourced** slides (`H#`) using tokens from `themes/oram-*.json` (via `build/*.pptx-theme.json`).

| Element | Light / dark behavior |
| --- | --- |
| Slide canvas | Recolored to theme `background` |
| Slide chrome (kicker, title, slide number, takeaway band) | Stamped from theme each build — edit manifest, not PowerPoint |
| Text on transparent diagram labels | Recolored to `ink` |
| Text on opaque badges / callouts | Recolored to `ink` when font is Automatic or theme default; explicit accent/RGB skipped |
| Diagram strokes (black / automatic) | Recolored to `ink` when stroke already exists; borderless shapes unchanged |
| Diagram fills and images | Left as authored |
| HW tables | Fully themed: cell fills, text, and borders from `table.*` tokens |

**Implementation** (`brief-to-pptx.py` → `apply_slide_chrome(..., mode="stamp")`, then transparent/opaque text recolor, `recolor_automatic_diagram_lines()`, and `recolor_table_shapes()`):
**Tables:** row 0 and column 0 → `headerFill` + `headerText` (shared frame); data cells alternate `background` with `table.bandFill` per `table.stripe` (theme default) or deck note `table_stripe:` (per-tag map). All cell borders → `table.headerFill` (same as the header frame) via `tblBorders` on `tblPr` plus per-cell `tcPr`. Combine removes the staged `tableStyleId` (otherwise PowerPoint applies the deck default tx1 grid). Author staged `.pptx` with **no manual cell fills**.

**Automatic text on opaque badges:** runs with no font color, or theme-default slots (`tx1`, `dk1`, `lt1`), get `ink`. Explicit RGB or accent scheme colors are skipped.

**Automatic diagram strokes:** only shapes that already have a visible stroke get recolored: `solidFill` with theme-default scheme slots or light-mode defaults (`#000000`, `#1a1a1a`, `#2A2420`). Shapes with no stroke, `noFill`, or unset line color are left alone (combine does not add borders). Explicit accent or custom RGB strokes are skipped. Alpha on a default-black stroke is preserved. Groups recursed; chrome, tables, charts, and pictures skipped.

Task tracker: `oram-deck-hw-diagram-colors` on ORAM Project (`vault/Notes/ORAM Project.md`).

---

## Top-level npm scripts

Run from repo root: `npm --prefix presentations run <script>`, or from `presentations/`: `npm run <script>`.

| Script | Pipeline | Primary output |
| --- | --- | --- |
| `build-slides` | clean → extract → render SVG → rename → replace → apply-pdf-theme → pdf | `build/<prefix>.marp.export.pdf` |
| `build-ppt` | clean → extract → render SVG → rename → brief | `build/<prefix>.ppt-brief.md` + SVGs |
| `build-pptx` | extract → render PNG → rename → brief → write-pptx-theme → pptx | `build/<prefix>.marp.export.pptx` |
| `build-combined` | extract → render PNG → rename → brief → write-pptx-theme → combine | `build/<prefix>.combined.pptx` |

### Individual steps

| Script | Tool | Purpose |
| --- | --- | --- |
| `slides:clean` | shell | Remove transient `mmdc*.svg` in Attachments |
| `slides:extract` | `extract-mermaid.js` | Mermaid blocks → `build/<prefix>.mermaid.md` |
| `slides:render-mermaid` | `render-mermaid.js svg` | `mmdc` → Attachments |
| `slides:render-png` | `render-mermaid.js png` | `mmdc` → `build/png/` |
| `slides:rename` | `rename-mermaid-svgs.js` | `mmdc-N.svg` → `<id>.svg` |
| `slides:rename-png` | `rename-mermaid-svgs.js mmdc png` | Same for PNGs |
| `slides:replace` | `replace-mermaid-with-svgs.js` | Inject SVG refs → export md |
| `slides:apply-pdf-theme` | `generate-marp-pdf-themes.js` + `apply-marp-pdf-theme.js` | Set Marp CLI `theme:` on export md |
| `slides:pdf` | `render-marp-pdf.js` | Marp CLI → PDF |
| `slides:brief` | `marp-to-ppt-brief.js` | PPT connector brief |
| `slides:write-pptx-theme` | `write-pptx-theme.js` | `build/<prefix>.pptx-theme.json` |
| `slides:pptx` | `run-deck-python.js brief` | Local PPTX |
| `slides:combine` | `run-deck-python.js combine` | Combined PPTX from deck manifest |
| `slides:sync-hw` | `sync-hw-slides.js` | Drive → `oram` HW staging (manual) |
| `slides:finish` | rename + replace + apply-pdf-theme + pdf | MEP fallback |
| `themes:generate-pdf` | `generate-marp-pdf-themes.js` | Regenerate `themes/pdf/*.css` |
| `themes:check` | `check-oram-theme.js` | JSON merge sanity |
| `themes:check-layout` | `check-oram-layout.js` + Python | Layout parity |
| `themes:check-pdf` | `check-oram-pdf-themes.js` | Generated CSS vs JSON |
| `themes:check-all` | all checks | Run after theme edits |
| `themes:show` | `load-oram-theme.js [variant]` | Print merged theme |

---

## Tool map

```
resolve-deck-sources.js   ← DECK_NOTE | MARP_INPUT → all paths
load-oram-theme.js        ← deck_theme: → merged JSON (common + variant)

extract-mermaid.js        ← mermaid + theme → .mermaid.md
render-mermaid.js         ← mmdc wrapper (svg | png)
rename-mermaid-svgs.js    ← mmdc-N → diagram id
replace-mermaid-with-svgs.js
apply-marp-pdf-theme.js   ← inject Marp theme on export md only
render-marp-pdf.js        ← marp CLI
marp-to-ppt-brief.js
write-pptx-theme.js
run-deck-python.js        ← brief-to-pptx.py | combine-pptx.py
run-child.js              ← spawn helper

brief-to-pptx.py          ← local PPTX; apply_slide_chrome() for SW create + HW stamp
combine-pptx.py           ← manifest-driven merge

generate-marp-pdf-themes.js / marp-pdf-theme-render.js
check-oram-*.js / check-oram-pptx-layout.py
```

---

## Theme resolution (code path)

```
THEME env (optional override)
  ↓ else
deck_theme: on themeSourcePath
  (deck note when DECK_NOTE; .marp.md when MARP_INPUT)
  ↓
merge( oram-common.json , oram-{variant}.json )
  ↓
extract-mermaid (Mermaid config)
apply-marp-pdf-theme (Marp CLI theme name on export md)
write-pptx-theme / brief-to-pptx / combine (PPTX palette + layout)
```

Source files use **`deck_theme:`** for ORAM tokens. Export md gets Marp CLI **`theme: oram-light|oram-dark`** injected at build (points at `themes/pdf/*.css`). Optional Marp **`theme:`** on source `.marp.md` (e.g. `gaia`) is for preview only.

Design tokens and JSON schemas: [`themes/README.md`](themes/README.md).

---

## Pipelines (diagrams)

### Diagrams (both routes)

```
.marp.md → extract-mermaid → mmdc → rename → SVG (PDF) or PNG (PPTX)
```

### PDF

```
.marp.md → replace → export.md → apply-pdf-theme → marp CLI → PDF
```

### PPTX

```
.marp.md → brief.md → brief-to-pptx.py → .pptx
```

### Combined deck (deck mode only)

```
deck note manifest + deck_sources
  → brief from marp
  → combine-pptx.py (validate S#, stamp H#, reorder)
  → .combined.pptx
```

---

## JSON theme files

| File | Contents |
| --- | --- |
| `themes/oram-common.json` | Layout, typography, Mermaid structural config (no colors) |
| `themes/oram-light.json` | Colors + chrome toggles + `pdf.marpTheme` |
| `themes/oram-dark.json` | Dark palette only (merged over common) |

After editing JSON: `npm run themes:generate-pdf && npm run themes:check-all`.

Full schema examples: see files on disk; parity checks live in `check-oram-*.js`.

---

## Folder layout

```
presentations/
├── BUILD.md              ← this file
├── README.md             ← author entry point
├── package.json          ← npm scripts only
├── themes/               ← ORAM tokens + generated PDF CSS
├── tools/                ← scripts above
├── build/                ← generated (gitignored)
└── .venv/                ← python-pptx (gitignored)
```

---

## Maintenance notes

- `build/` is regenerable; never commit outputs.
- `slides:clean` removes transient `mmdc*.svg`; orphaned `<id>.svg` after diagram deletion → remove by hand from Attachments.
- PPTX path does not read Marp CSS — layout comes from `oram-common.json` via Python `load_layout()`. **PPTX is canonical** for chrome geometry; Marp PDF CSS is generated from the same `layout.*In` tokens.
- PDF layout CSS is inlined into `themes/pdf/*.css` (Marp does not resolve external `@import` in theme-set).
