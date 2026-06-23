#!/usr/bin/env node

/**
 * Verify oram-common matches layout baselines (brief-to-pptx.py + PDF theme tokens)
 * and that both color variants share identical layout/typography after merge.
 */

const fs = require("fs");
const path = require("path");

const { loadOramTheme } = require("./load-oram-theme");

const ROOT = path.join(__dirname, "..");
const COMMON_PATH = path.join(ROOT, "themes", "oram-common.json");

/** Mirrors tools/brief-to-pptx.py layout globals (light PPTX baseline). */
const BRIEF_TO_PPTX = {
  slide: { widthIn: 13.333, heightIn: 7.5 },
  layout: {
    marginIn: 0.7,
    chromeTopIn: 0.4,
    kickerHeightIn: 0.2,
    gapAfterKickerIn: 0.06,
    gapAfterTitleIn: 0.05,
    gapAfterDiagramIn: 0.08,
    takeawayBottomIn: 0.35,
    takeawayBandHeightIn: 0.85,
    diagramMaxHeightPx: 260,
    diagramMaxZoneFraction: 0.42,
  },
  font: "Helvetica Neue",
  typography: {
    pptx: {
      title: 26,
      kicker: 13,
      body: 18,
      heading: 20,
      takeaway: 17,
      number: 13,
      bodyLineSpacing: 1.15,
      takeawayTextInsetIn: 0.2,
    },
  },
};

/** PDF layout tokens (from themes/oram-common.json typography.marp + layout). */
const MARP_STYLE = {
  layout: {
    lineHeight: 1.22,
    diagramMaxHeightPx: 260,
    diagramMaxZoneFraction: 0.42,
  },
  typography: {
    marp: {
      bodyPx: 24,
      headings: { h1: 1.45, h2: 1.2, h3: 1.05 },
      labelScale: 0.55,
      labelLetterSpacingEm: 0.06,
      takeawayScale: 0.9,
      takeawayPaddingEm: 0.45,
      takeawayBottomPx: 40,
      takeawayInsetPx: 60,
      gapAfterTitleEm: 0.08,
      diagramMarginTopEm: 0.08,
      diagramMarginBottomEm: 0.1,
    },
  },
  columns: { gapPx: 28, leftPercent: 42 },
};

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

function pickSlice(merged) {
  return {
    font: merged.font,
    slide: merged.slide,
    layout: merged.layout,
    typography: merged.typography,
    mermaid: {
      theme: merged.mermaid.theme,
      htmlLabels: merged.mermaid.htmlLabels,
      fontFamily: merged.mermaid.fontFamily,
      flowchart: merged.mermaid.flowchart,
    },
    columns: merged.columns,
  };
}

function checkCommonVsPptx(common) {
  assertEqual("common.slide ↔ brief-to-pptx", common.slide, BRIEF_TO_PPTX.slide);
  assertEqual(
    "common.layout (pptx keys) ↔ brief-to-pptx",
    {
      marginIn: common.layout.marginIn,
      chromeTopIn: common.layout.chromeTopIn,
      kickerHeightIn: common.layout.kickerHeightIn,
      gapAfterKickerIn: common.layout.gapAfterKickerIn,
      gapAfterTitleIn: common.layout.gapAfterTitleIn,
      gapAfterDiagramIn: common.layout.gapAfterDiagramIn,
      takeawayBottomIn: common.layout.takeawayBottomIn,
      takeawayBandHeightIn: common.layout.takeawayBandHeightIn,
      diagramMaxHeightPx: common.layout.diagramMaxHeightPx,
      diagramMaxZoneFraction: common.layout.diagramMaxZoneFraction,
    },
    BRIEF_TO_PPTX.layout
  );
  assertEqual("common.font ↔ brief-to-pptx", common.font, BRIEF_TO_PPTX.font);
  assertEqual(
    "common.typography.pptx ↔ brief-to-pptx",
    common.typography.pptx,
    BRIEF_TO_PPTX.typography.pptx
  );
}

function checkCommonVsMarp(common) {
  assertEqual(
    "common.layout.lineHeight ↔ marp CSS",
    common.layout.lineHeight,
    MARP_STYLE.layout.lineHeight
  );
  assertEqual(
    "common.layout.diagramMaxHeightPx ↔ marp CSS",
    common.layout.diagramMaxHeightPx,
    MARP_STYLE.layout.diagramMaxHeightPx
  );
  assertEqual(
    "common.typography.marp ↔ marp CSS",
    common.typography.marp,
    MARP_STYLE.typography.marp
  );
  assertEqual("common.columns ↔ marp CSS", common.columns, MARP_STYLE.columns);
}

function checkVariantParity() {
  const light = pickSlice(loadOramTheme("oram-light"));
  const dark = pickSlice(loadOramTheme("oram-dark"));
  assertEqual("oram-light ↔ oram-dark layout slice", light, dark);
}

const common = readJson(COMMON_PATH);

checkCommonVsPptx(common);
checkCommonVsMarp(common);
checkVariantParity();

if (process.exitCode) {
  process.exit(process.exitCode);
}

console.log("All ORAM layout checks passed.");
