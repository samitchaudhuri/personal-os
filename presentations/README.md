# presentations

Build layer for Marp slides that contain Mermaid diagrams. This folder lives **outside** the Obsidian vault and is backed up to its own git repo. It holds scripts, theme configs, and generated build artifacts; the slide **content** lives in the vault.

The human-facing how-to (preview, build, export to PDF / PowerPoint / Google Slides, troubleshooting) is the runbook in the vault: `vault/Notes/Marp Slide Development Runbook.md`. This README only documents the folder itself.

## Relationship to the vault

Scripts reach the vault through relative paths from this folder (`presentations/` and `vault/` are siblings under the repo root):

- Source decks: `../vault/Notes/<deck>.marp.md` (single source of truth)
- Rendered diagram SVGs: `../vault/Attachments/<id>.svg`
- PPT brief (for the PowerPoint route): generated to `build/<deck>.ppt-brief.md` (artifact — derived from the deck, not hand-edited)

## Structure

```
presentations/
├── package.json            # config.deck + npm build scripts
├── package-lock.json
├── mermaid-themes/         # Mermaid theme JSON injected at build — themes the diagrams (gaia, uncover)
│   ├── gaia.json
│   └── uncover.json
├── pptx-themes/            # slide-chrome palette for the local PPTX route — themes the slides
│   └── gaia.json
├── tools/                  # build scripts
│   ├── extract-mermaid.js          # pull Mermaid blocks → <deck>.mermaid.md (with theme)
│   ├── rename-mermaid-svgs.js      # mmdc-N.svg → <id>.svg (by diagram id)
│   ├── replace-mermaid-with-svgs.js# swap Mermaid blocks for SVG refs in export md
│   └── marp-to-ppt-brief.js        # derive <deck>.ppt-brief.md from the deck (PPT route)
├── build/                  # generated artifacts — gitignored
│   ├── <deck>.mermaid.md           # intermediate
│   ├── <deck>.marp.export.md       # intermediate (SVG refs)
│   ├── <deck>.marp.export.pdf      # PDF output (PDF route)
│   ├── <deck>.ppt-brief.md         # PPT brief (PPTX routes)
│   ├── <deck>.marp.export.pptx     # PPTX output (local route)
│   └── png/                        # raster diagrams for the local PPTX route
└── node_modules/           # gitignored
```

Only `package*.json`, `mermaid-themes/`, and `tools/` are tracked. `build/` and `node_modules/` are gitignored (see repo-root `.gitignore`).

## Commands

Run from the repo root (or use the Cursor tasks in `.vscode/tasks.json`):

```
npm --prefix presentations run build-slides   # PDF route
npm --prefix presentations run build-ppt       # PowerPoint route (SVGs + brief)
```

`build-slides` pipeline: clean → extract → render (mmdc) → rename → replace → pdf.
`build-ppt` pipeline: clean → extract → render (mmdc) → rename → brief (no PDF). Use `slides:brief` alone to regenerate just the brief from existing SVGs. See the runbook for the task names and the PowerPoint / Google Slides path.

## Targeting another deck

The deck name lives in one place: the `config.deck` field in `package.json`. Every script references `$npm_package_config_deck`. To build a different deck, change that field (the `.marp.md`, `.mermaid.md`, `.marp.export.md`, and `.ppt-brief.md` names all derive from it). The `config.theme` field (default `gaia`) selects both the Mermaid diagram theme and the matching `pptx-themes/<theme>.json` slide palette. Per-deck PPT design intent lives in the deck's `ppt_design:` frontmatter, which `marp-to-ppt-brief.js` reads into the brief's Design direction.

## Outputs and safekeeping

`build/` is gitignored and regenerable. Copy the PDF (and the `.pptx` from the PowerPoint route, if you save it here) out to your own safekeeping location. A tracked `exports/` folder can be added later if you want final decks versioned in the repo.

## Cleanup notes

`slides:clean` removes the transient `mmdc*.svg` render outputs in `vault/Attachments/`. The final `<id>.svg` files are overwritten on each `rename`, so a normal rebuild stays correct. If you **delete** a diagram from a deck, its old `<id>.svg` is orphaned in `vault/Attachments/` and must be removed by hand.

## Requirements

- `@marp-team/marp-cli` (declared in `devDependencies`; resolved from `node_modules/.bin`)
- `mmdc` (`@mermaid-js/mermaid-cli`) available on PATH (currently installed globally)
- Python venv for the local `.pptx` route: `.venv` with `python-pptx` (see `requirements.txt`; recreate with `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`)

## Local PPTX route (no Claude / no tokens)

`build-pptx` assembles a `.pptx` locally instead of using Claude's connector: extract → render PNG (`-s 3`) → rename → brief → `tools/brief-to-pptx.py`. Diagrams are placed **full-width** below the body. Output: `build/<deck>.marp.export.pptx`. Uses python-pptx; diagrams are rasterized to PNG (`build/png/`) because python-pptx cannot embed SVG.

### Theming the slides

Two theme layers, kept separate because they cover different things:

- **`mermaid-themes/<name>.json`** themes the **diagrams** (node fill, text, edge labels). Injected by `extract-mermaid.js`; its keys are Mermaid config, so don't add non-Mermaid keys here.
- **`pptx-themes/<name>.json`** themes the **slide chrome** in the local PPTX route (kicker/number/title accent, body ink, takeaway band). Read by `brief-to-pptx.py`. Recognized keys: `ink`, `accent`, `takeawayFill`, `takeawayText` (hex strings); any missing key falls back to the generator's built-in default.

The active theme name is `config.theme` in `package.json` (currently `gaia`); the PPTX route loads `pptx-themes/$theme.json`. To retheme the slides, edit that file and rerun `build-pptx` — no code change. The PDF route gets its colors from Marp's `gaia` theme + the deck CSS, so PDF and PPTX are themed independently; keep the two palettes in sync by hand if you want them to match.

## Deferred decisions / TODO

- **Port the local generator to PptxGenJS (Node)** to unify the toolchain and drop the Python venv. Deferred on purpose — the python-pptx version works; revisit only if the venv becomes friction. (Claude's connector used PptxGenJS with python-pptx as fallback; both are equivalent OOXML generators.)
- **Document in the runbook after visual validation:** the local PPTX route above, and the `--no-stdin` fix added to `slides:pdf` (it stops Marp's PDF export from hanging on stdin in non-interactive shells). Pending confirmation that the generated `.pptx` looks right.
