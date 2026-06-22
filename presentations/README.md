# presentations

Build layer for slide sources in the vault. Scripts, themes, and generated artifacts live here; slide **content** and deck **manifests** live in `../vault/Notes/`.

## Documentation map

| Doc | Role |
| --- | --- |
| `vault/Agent/Workflows/Slide Deck Development.md` | End-to-end deck workflow: deck note, manifest, sources, combine, iteration |
| `vault/Notes/Marp Slide Build Runbook.md` | Author/export one `.marp.md` (preview, Mermaid, PDF/PPTX) |
| **This README** | Canonical **command registry** — scripts, outputs, env vars, VS Code tasks |

Do not duplicate the full command reference in the vault docs; link here instead.

## Relationship to the vault

Paths are relative from `presentations/` (`vault/` is a sibling under the repo root):

| Path | Role |
| --- | --- |
| `../vault/Notes/<deck> Deck.md` | Deck note: manifest, slide detail, `markdown_sources` / `pptx_sources` |
| `../vault/Notes/<marp>.marp.md` | Markdown/Marp source (`config.marp` or `MARP` env) |
| `../vault/Attachments/<id>.svg` | Rendered diagram SVGs (PDF / brief routes) |
| `build/<deck>.*` | Generated intermediates and outputs (gitignored) |
| `build/<file>.pptx` | PowerPoint sources referenced by deck notes |

## Folder structure

```
presentations/
├── package.json            # config.deck, config.marp, config.theme, npm scripts
├── mermaid-themes/         # diagram themes (injected at extract)
├── pptx-themes/            # slide-chrome palette for local PPTX / combine
├── tools/                  # build scripts
├── build/                  # generated (gitignored)
└── .venv/                  # python-pptx for PPTX routes (gitignored)
```

## Commands (canonical)

Run from repo root unless noted.

### Top-level routes

| Script | Pipeline | Primary output |
| --- | --- | --- |
| `npm --prefix presentations run build-slides` | clean → extract → render SVG → rename → replace → pdf | `build/<deck>.marp.export.pdf` |
| `npm --prefix presentations run build-ppt` | clean → extract → render SVG → rename → brief | `build/<deck>.ppt-brief.md` + SVGs |
| `npm --prefix presentations run build-pptx` | extract → render PNG → rename → brief → pptx | `build/<deck>.marp.export.pptx` |
| `npm --prefix presentations run build-combined` | extract → render PNG → rename → brief → combine | `build/<deck>.combined.pptx` |

Deck workflow (when to use each route): `vault/Agent/Workflows/Slide Deck Development.md` § Step 4 — Build the deck.

### Individual steps

| Script | Purpose |
| --- | --- |
| `slides:clean` | Remove transient `mmdc*.svg` in Attachments |
| `slides:extract` | Mermaid blocks → `build/<deck>.mermaid.md` |
| `slides:render-mermaid` | SVG render (PDF route) |
| `slides:render-png` | PNG render at 3× (PPTX route) → `build/png/` |
| `slides:rename` | `mmdc-N.svg` → `<diagram-id>.svg` in Attachments |
| `slides:rename-png` | Same for PNGs in `build/png/` |
| `slides:replace` | Inject SVG refs → `build/<deck>.marp.export.md` |
| `slides:pdf` | Marp CLI → PDF |
| `slides:brief` | Derive `build/<deck>.ppt-brief.md` from Marp source |
| `slides:pptx` | Local PPTX from brief + PNGs |
| `slides:combine` | Merge sources per deck note manifest |
| `slides:finish` | rename + replace + pdf (MEP fallback step 3) |

### VS Code tasks (`.vscode/tasks.json`)

| Task | Runs |
| --- | --- |
| Slides: Build PDF (CLI - mmdc) | `build-slides` |
| Slides: Build PDF (active file) | `build-slides` + `DECK`/`MARP` from editor file |
| Slides: Build PPTX | `build-pptx` |
| Slides: Build PPTX (active file) | `build-pptx` + active file |
| Slides: Build Combined PPTX (HW + SW) | `build-combined` |
| Slides: Build Combined PPTX (active file) | `build-combined` + active file |
| Slides: PPT brief + assets (Claude route) | `build-ppt` |
| Slides: PPT brief + assets (active file) | `build-ppt` + active file |
| Slides: Extract Mermaid | `slides:extract` |
| Slides: Finish (MEP fallback) | `slides:finish` |

Marp authoring (preview, Mermaid conventions): `vault/Notes/Marp Slide Build Runbook.md`.

## Targeting a deck

Scripts resolve names from `presentations/package.json` `config` (overridable via env):

| Variable | Selects | Default (`config`) |
| --- | --- | --- |
| **`DECK`** | Deck note stem, build artifact prefix, combine identity | `deck` → `ORAM Company Pitch` |
| **`MARP`** | Marp source file `../vault/Notes/<marp>.marp.md` | `marp` → `ORAM Software Slides` |
| **`config.theme`** | `mermaid-themes/` + `pptx-themes/` palette | `oram-light` |

**Active file:** open `<deck> Deck.md` or `<marp>.marp.md` and run a **"… (active file)"** task. Deck note sets `DECK`; Marp file sets `MARP`; the other falls back to `config`.

**Headless/CLI:** bare `npm run …` uses `config.deck` + `config.marp`.

Derived filenames (`.mermaid.md`, `.ppt-brief.md`, `.combined.pptx`, etc.) use the resolved `DECK` name. Per-deck PPT design intent: `ppt_design:` in the Marp frontmatter → brief **Design direction**.

## Theming

| Layer | File | Used by |
| --- | --- | --- |
| Diagrams | `mermaid-themes/<name>.json` | `extract-mermaid.js`; also set `theme:` in Marp frontmatter |
| Slide chrome | `pptx-themes/<name>.json` | `brief-to-pptx.py`, `combine-pptx.py` via `config.theme` |

`pptx-themes` keys: `font`, `background`, `ink`, `accent`, `takeawayFill`, `takeawayText`, `showKicker`, `showSlideNumber`, `showTakeawayBand`, `sizes` (points). Missing keys fall back to generator defaults.

## Outputs and safekeeping

`build/` is gitignored and regenerable. Copy PDF/PPTX out for sharing. Do not hand-edit generated briefs or combined decks.

## Cleanup

`slides:clean` removes transient `mmdc*.svg` renders. Final `<id>.svg` files are overwritten on rename each build. Deleted diagrams leave orphaned SVGs in `vault/Attachments/` — remove by hand.

## Requirements

- Node: `npm install` in `presentations/` (`@marp-team/marp-cli` in devDependencies)
- **`mmdc`** on PATH (`@mermaid-js/mermaid-cli`)
- PPTX/combine: Python venv — `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`

## Deferred / TODO

- Port local generator to PptxGenJS to drop Python venv
- Fold diagram theme into `pptx-themes` for unified light/dark
