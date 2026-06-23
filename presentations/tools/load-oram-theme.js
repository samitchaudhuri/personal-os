#!/usr/bin/env node

const fs = require("fs");
const path = require("path");

const THEMES_DIR = path.join(__dirname, "..", "themes");
const VALID_VARIANTS = new Set(["oram-light", "oram-dark"]);

function isPlainObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function deepMerge(base, override) {
  if (!isPlainObject(base) || !isPlainObject(override)) {
    return override === undefined ? base : override;
  }

  const out = { ...base };
  for (const [key, value] of Object.entries(override)) {
    if (isPlainObject(value) && isPlainObject(out[key])) {
      out[key] = deepMerge(out[key], value);
    } else {
      out[key] = value;
    }
  }
  return out;
}

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, "utf8"));
}

function normalizeVariant(name) {
  if (!name) return null;
  const trimmed = String(name).trim();
  if (VALID_VARIANTS.has(trimmed)) return trimmed;
  if (trimmed === "uncover") return "oram-dark";
  if (trimmed === "gaia") return "oram-light";
  return null;
}

function readDeckThemeFromPath(sourcePath) {
  if (!sourcePath || !fs.existsSync(sourcePath)) return null;

  const text = fs.readFileSync(sourcePath, "utf8");
  const fmMatch = text.match(/^---\n([\s\S]*?)\n---/);
  if (!fmMatch) return null;

  const deckThemeMatch = fmMatch[1].match(
    /^deck_theme:\s*"?([A-Za-z0-9_-]+)"?\s*$/m
  );
  if (deckThemeMatch) {
    return normalizeVariant(deckThemeMatch[1]);
  }

  return null;
}

function resolveThemeName(options = {}) {
  if (options.theme) {
    const normalized = normalizeVariant(options.theme);
    if (!normalized) {
      throw new Error(
        `Unknown theme "${options.theme}". Expected oram-light or oram-dark.`
      );
    }
    return normalized;
  }

  if (process.env.THEME) {
    const normalized = normalizeVariant(process.env.THEME);
    if (!normalized) {
      throw new Error(
        `Unknown THEME env "${process.env.THEME}". Expected oram-light or oram-dark.`
      );
    }
    return normalized;
  }

  if (options.themeSourcePath) {
    const fromPath = readDeckThemeFromPath(options.themeSourcePath);
    if (fromPath) return fromPath;
    throw new Error(
      `Missing deck_theme: in ${options.themeSourcePath} (oram-light or oram-dark).`
    );
  }

  const { resolveDeckPaths } = require("./resolve-deck-sources");
  const paths = resolveDeckPaths();
  const variant = readDeckThemeFromPath(paths.themeSourcePath);
  if (!variant) {
    throw new Error(
      `Missing deck_theme: in ${paths.themeSourcePath} (oram-light or oram-dark).`
    );
  }
  return variant;
}

function loadOramTheme(variant) {
  const name = normalizeVariant(variant);
  if (!name) {
    throw new Error(
      `Unknown theme variant "${variant}". Expected oram-light or oram-dark.`
    );
  }

  const commonPath = path.join(THEMES_DIR, "oram-common.json");
  const variantPath = path.join(THEMES_DIR, `${name}.json`);

  if (!fs.existsSync(commonPath)) {
    throw new Error(`Missing theme file: ${commonPath}`);
  }
  if (!fs.existsSync(variantPath)) {
    throw new Error(`Missing theme file: ${variantPath}`);
  }

  return deepMerge(readJson(commonPath), readJson(variantPath));
}

/** Legacy flat palette for brief-to-pptx / combine (phase 3+). */
function toPptxPalette(merged) {
  return {
    name: merged.name,
    font: merged.font,
    background: merged.colors.background,
    ink: merged.colors.ink,
    accent: merged.colors.accent,
    takeawayFill: merged.colors.takeawayFill,
    takeawayText: merged.colors.takeawayText,
    showKicker: merged.chrome.showKicker,
    showSlideNumber: merged.chrome.showSlideNumber,
    showTakeawayBand: merged.chrome.showTakeawayBand,
    sizes: { ...merged.typography.pptx },
  };
}

/** Mermaid CLI config object (phase 2+). */
function toMermaidConfig(merged) {
  const mm = merged.mermaid;
  return {
    theme: mm.theme,
    htmlLabels: mm.htmlLabels,
    fontFamily: mm.fontFamily,
    themeVariables: { ...mm.themeVariables },
    flowchart: { ...mm.flowchart },
  };
}

/** Resolved Marp PDF theme name from merged ORAM theme. */
function toMarpPdfThemeName(variant) {
  const name = variant ? normalizeVariant(variant) : resolveThemeName();
  if (!name) {
    throw new Error(`Unknown theme variant for PDF: ${variant}`);
  }
  const merged = loadOramTheme(name);
  return merged.pdf?.marpTheme || name;
}

/** @deprecated Phase 4+ uses custom themes; kept for gaia/uncover alias tests. */
function toInterimMarpPdfTheme(variant) {
  return toMarpPdfThemeName(variant);
}

module.exports = {
  VALID_VARIANTS,
  deepMerge,
  loadOramTheme,
  normalizeVariant,
  readDeckThemeFromPath,
  resolveThemeName,
  toInterimMarpPdfTheme,
  toMarpPdfThemeName,
  toMermaidConfig,
  toPptxPalette,
};

if (require.main === module) {
  const [, , variantArg, formatArg] = process.argv;
  const variant = variantArg
    ? resolveThemeName({ theme: variantArg })
    : resolveThemeName({ theme: "oram-light" });
  const merged = loadOramTheme(variant);

  if (formatArg === "--pptx") {
    console.log(JSON.stringify(toPptxPalette(merged), null, 2));
  } else if (formatArg === "--mermaid") {
    console.log(JSON.stringify(toMermaidConfig(merged), null, 2));
  } else {
    console.log(JSON.stringify(merged, null, 2));
  }
}
