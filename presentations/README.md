# presentations

Build tooling for slide decks whose **content and manifests** live in `../vault/Notes/`.

## Who reads what

| You are… | Start here |
| --- | --- |
| **Authoring or building slides** | [[Slide Deck Development]] (combined decks) or [[Marp Slide Build Runbook]] (one Marp file) |
| **Changing colors or layout** | [`themes/README.md`](themes/README.md) |
| **Extending the pipeline** | [`BUILD.md`](BUILD.md) — update it when you change `tools/` or build behavior |

## Documentation map

Vault workflows and runbooks describe **what to author**; this folder holds **scripts and maintainer specs**.

```mermaid
flowchart TB
  subgraph vault [Vault - process]
    SDD["Slide Deck Development"]
    MSBR["Marp Slide Build Runbook"]
  end

  subgraph repo [presentations/ - execution]
    README["README.md"]
    BUILD["BUILD.md"]
    PKG["package.json"]
    TOOLS["tools/*.js + *.py"]
    THEMES["themes/*.json"]
  end

  SDD -->|"Step 4: VS Code task"| README
  SDD -->|"env / npm / impl detail"| BUILD
  MSBR -->|"Marp-only builds"| BUILD
  README --> BUILD
  BUILD --> PKG
  PKG --> TOOLS
  TOOLS --> THEMES
```

| Layer | Location | Role |
| --- | --- | --- |
| Workflow | [[Slide Deck Development]] | Combined decks: manifest, sources, build |
| Runbook | [[Marp Slide Build Runbook]] | Single `.marp.md`: preview, Mermaid, export |
| Quick start | `presentations/README.md` (this file) | Open file → VS Code task |
| Pipeline spec | [`BUILD.md`](BUILD.md) | Env vars, npm scripts, tool map (maintainers) |

## Why this folder exists

Slide sources (Marp markdown, PowerPoint, deck manifests) belong in the vault. This folder holds **scripts, themes, and generated output** so builds stay reproducible: Mermaid → SVG/PNG, Marp → PDF, brief → PPTX, manifest → combined deck.

## What lives where

| Location | Role |
| --- | --- |
| `vault/Notes/<deck> Deck.md` | Manifest, `deck_theme`, `deck_sources`, combine recipe |
| `vault/Notes/<name>.marp.md` | Slide content, Mermaid, speaker notes |
| `vault/Attachments/<id>.svg` | Rendered diagrams (PDF route) |
| `presentations/build/<prefix>.*` | Generated intermediates and outputs (gitignored) |
| `presentations/themes/` | ORAM layout + color tokens |
| `presentations/tools/` | Build scripts — see [`BUILD.md`](BUILD.md) |

## How to build

Open the file you are working on, then run the matching VS Code task:

| Open | Task | Output |
| --- | --- | --- |
| `<deck> Deck.md` | **Slides: Build PDF** / **PPTX** / **Combined PPTX** | `build/<deck>.*` |
| `.marp.md` | **Slides: Build PDF** / **PPTX** | `build/<marp-stem>.*` |

Combine requires the **deck note** open — not the Marp file alone.

Command names, env vars, and pipeline steps: [`BUILD.md`](BUILD.md).

## First-time setup

From repo root:

```bash
cd presentations && npm install
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

Also on PATH: **`mmdc`** (`@mermaid-js/mermaid-cli`).

## Conventions (quick reference)

**Deck note frontmatter:** `deck_theme:` (`oram-light` \| `oram-dark`), `deck_sources:` — plus manifest table in the body for combine. Output prefix from filename (`<name> Deck.md`).

**Marp frontmatter:** `marp: true`, `deck_theme:` (required when building from the Marp file). Optional Marp `theme:` (e.g. `gaia`) is for editor preview only.

Do not hand-edit files under `build/`. Copy PDF/PPTX out for sharing.
