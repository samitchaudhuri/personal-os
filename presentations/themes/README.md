# ORAM slide themes

One **layout** definition and two **color** variants (`oram-light`, `oram-dark`) drive Mermaid diagrams, PDF export, and PPTX/combine for a build.

Author-facing commands: [`../README.md`](../README.md). Pipeline detail: [`../BUILD.md`](../BUILD.md).

---

## Why

Slide appearance should not live in `.marp.md` as scattered CSS. Layout numbers and palette tokens live here as JSON; builds merge them at export time so PDF, PPTX, and diagrams stay aligned when you change one margin or accent color.

**Layout authority:** PPTX (`brief-to-pptx.py`) is canonical for chrome geometry. Marp PDF CSS is generated from the same `oram-common.json` `layout.*In` tokens (`marp-pdf-theme-render.js`). If PDF and PPTX disagree, fix the shared layout or the generator — not the PPTX output.

---

## What you set in the vault

| Key | Where | Values |
| --- | --- | --- |
| **`deck_theme:`** | Deck note (deck builds) or `.marp.md` (marp-only builds) | `oram-light` \| `oram-dark` |
| **`theme:`** (optional) | `.marp.md` only | Marp preview themes (`gaia`, etc.) — **not** the ORAM pipeline |

On a **deck build**, the deck note's `deck_theme:` wins. On a **marp-only build**, use `deck_theme:` on that `.marp.md`.

Example deck note:

```yaml
deck_theme: oram-light
deck_sources:
  - file: ORAM Software Slides
    prefix: S
    type: marp
    path: vault/Notes/ORAM Software Slides.marp.md
```

Example Marp source:

```yaml
---
marp: true
deck_theme: oram-light
---
```

At PDF export, the build injects Marp CLI `theme: oram-light` on the **export md** only — that name maps to custom CSS in `themes/pdf/`. You do not set that by hand in source files.

---

## Light vs dark

| Token | oram-light | oram-dark |
| --- | --- | --- |
| Background | `#ffffff` | `#141210` |
| Ink | `#1a1a1a` | `#F0EBE6` |
| Accent | `#9B5A3C` | `#E8A882` |
| Takeaway fill | `#F5EBE4` | `#3D3228` |

Layout (margins, type scale, diagram height cap) is **identical** across variants — see `oram-common.json`.

---

## How to change the design

1. **Switch variant for a deck** — change `deck_theme:` on the deck note (or marp file for marp-only builds), rebuild.
2. **Change brand colors** — edit `oram-light.json` / `oram-dark.json` (`colors` block).
3. **Change layout** — edit `oram-common.json` (`layout`, `typography`).
4. **Regenerate PDF CSS** — from `presentations/`:

   ```bash
   npm run themes:generate-pdf && npm run themes:check-all
   ```

5. Rebuild the deck.

Inspect a merged theme: `npm run themes:show -- oram-light`.

---

## What applies where

| Asset | PDF | PPTX | Combined `H#` slides |
| --- | --- | --- | --- |
| `oram-common.json` | layout | layout | chrome geometry |
| `oram-light` / `oram-dark` | colors | colors | chrome colors + slide background (see below) |
| `themes/pdf/*.css` | yes | no | no |
| `.marp.md` body | content | via brief | `S#` content only |

**Combined `H#` theming:** quick reference in [[Slide Deck Development#HW slide theming at combine]]; implementation in [`BUILD.md`](../BUILD.md#hw-slide-theming-at-combine).

Marp CSS is never read by the PPTX generator.

---

## Files in this folder

```
themes/
  oram-common.json    ← layout + typography (shared)
  oram-light.json     ← light colors + chrome toggles
  oram-dark.json      ← dark colors
  pdf/                ← generated Marp themes (do not hand-edit)
  includes/           ← reference copy of layout CSS (for diffing)
```

JSON schema detail and check scripts: [`../BUILD.md`](../BUILD.md).
