#!/usr/bin/env node

const fs = require("fs");
const path = require("path");

const {
  loadOramTheme,
  toMermaidConfig,
  toPptxPalette,
} = require("./load-oram-theme");

const ROOT = path.join(__dirname, "..");
const THEMES_DIR = path.join(ROOT, "themes");
const VARIANTS = ["oram-light", "oram-dark"];

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, "utf8"));
}

function assertEqual(label, actual, expected) {
  const a = JSON.stringify(actual);
  const e = JSON.stringify(expected);
  if (a !== e) {
    console.error(`FAIL ${label}`);
    console.error(" expected:", e);
    console.error("   actual:", a);
    process.exitCode = 1;
    return false;
  }
  console.log(`ok ${label}`);
  return true;
}

function checkPptxVariant(variant) {
  const variantFile = readJson(path.join(THEMES_DIR, `${variant}.json`));
  const merged = loadOramTheme(variant);
  const palette = toPptxPalette(merged);

  assertEqual(`${variant} → pptx palette`, palette, {
    name: variant,
    font: merged.font,
    background: variantFile.colors.background,
    ink: variantFile.colors.ink,
    accent: variantFile.colors.accent,
    takeawayFill: variantFile.colors.takeawayFill,
    takeawayText: variantFile.colors.takeawayText,
    showKicker: variantFile.chrome.showKicker,
    showSlideNumber: variantFile.chrome.showSlideNumber,
    showTakeawayBand: variantFile.chrome.showTakeawayBand,
    sizes: merged.typography.pptx,
  });
}

function checkMermaidVariant(variant) {
  const variantFile = readJson(path.join(THEMES_DIR, `${variant}.json`));
  const config = toMermaidConfig(loadOramTheme(variant));

  assertEqual(
    `${variant} → mermaid themeVariables`,
    config.themeVariables,
    variantFile.mermaid.themeVariables
  );
}

function checkMermaidStructureParity() {
  const light = toMermaidConfig(loadOramTheme("oram-light"));
  const dark = toMermaidConfig(loadOramTheme("oram-dark"));
  const { themeVariables: _lightVars, ...lightStructure } = light;
  const { themeVariables: _darkVars, ...darkStructure } = dark;

  assertEqual("mermaid structure light ↔ dark", lightStructure, darkStructure);
}

for (const variant of VARIANTS) {
  checkPptxVariant(variant);
  checkMermaidVariant(variant);
}
checkMermaidStructureParity();

if (process.exitCode) {
  process.exit(process.exitCode);
}

console.log("All ORAM theme checks passed.");
