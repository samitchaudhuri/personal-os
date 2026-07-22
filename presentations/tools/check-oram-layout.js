#!/usr/bin/env node

/**
 * Verify oram-common matches layout baselines (brief-to-pptx.py + PDF theme tokens)
 * and that both color variants share identical layout/typography after merge.
 */

const fs = require("fs");
const path = require("path");

const { loadOramTheme } = require("./load-oram-theme");
const { renderLayoutCss } = require("./marp-pdf-theme-render");

const ROOT = path.join(__dirname, "..");
const COMMON_PATH = path.join(ROOT, "themes", "oram-common.json");

/** Mirrors tools/brief-to-pptx.py layout globals (light PPTX baseline). */
const BRIEF_TO_PPTX = {
  slide: { widthIn: 13.333, heightIn: 7.5 },
  layout: {
    marginIn: 0.7,
    chromeTopIn: 0.4,
    kickerHeightIn: 0.2,
    gapAfterKickerIn: 0.12,
    gapAfterTitleIn: 0.14,
    gapAfterDiagramIn: 0.08,
    titleLineHeight: 1.3,
    titleBoxPadIn: 0.04,
    takeawayBottomIn: 0.35,
    takeawayBandHeightIn: 0.85,
    diagramMaxHeightPx: 320,
    diagramMaxZoneFraction: 0.42,
    bodyHeightPadIn: 0.2,
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
    diagramMaxHeightPx: 320,
    diagramMaxZoneFraction: 0.42,
  },
  typography: {
    marp: {
      bodyPx: 24,
      headings: { h1: 1.45, h2: 1.2, h3: 1.05 },
      labelLetterSpacingEm: 0.06,
      takeawayScale: 0.9,
      takeawayPaddingEm: 0.45,
    },
  },
  columns: { gapPx: 28, leftPercent: 42 },
};

/** Title→diagram and diagram→body gaps come from layout.*In via marp-pdf-theme-render. */
function expectedMarpGapPx(inches, slide) {
  return inches * (720 / slide.heightIn);
}

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
      titleLineHeight: common.layout.titleLineHeight,
      titleBoxPadIn: common.layout.titleBoxPadIn,
      takeawayBottomIn: common.layout.takeawayBottomIn,
      takeawayBandHeightIn: common.layout.takeawayBandHeightIn,
      diagramMaxHeightPx: common.layout.diagramMaxHeightPx,
      diagramMaxZoneFraction: common.layout.diagramMaxZoneFraction,
      bodyHeightPadIn: common.layout.bodyHeightPadIn,
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

function checkMarpLayoutMatchesPptx(common) {
  const slice = {
    font: common.font,
    slide: common.slide,
    layout: common.layout,
    typography: common.typography,
    columns: common.columns,
  };
  const css = renderLayoutCss(slice, "oram-light");
  const px = (inches) =>
    Math.round(expectedMarpGapPx(inches, common.slide));

  function assertCssIncludes(label, needle) {
    if (!css.includes(needle)) {
      console.error(`FAIL ${label}: expected ${JSON.stringify(needle)}`);
      process.exitCode = 1;
      return;
    }
    console.log(`ok ${label}`);
  }

  assertCssIncludes(
    "marp section top ↔ layout.chromeTopIn",
    `padding-top: ${px(common.layout.chromeTopIn)}px;`
  );
  assertCssIncludes(
    "marp kicker height ↔ layout.kickerHeightIn",
    `min-height: ${px(common.layout.kickerHeightIn)}px;`
  );
  assertCssIncludes(
    "marp kicker gap ↔ layout.gapAfterKickerIn",
    `margin-bottom: ${px(common.layout.gapAfterKickerIn)}px;`
  );
  assertCssIncludes(
    "marp label size ↔ typography.pptx.kicker",
    `font-size: ${common.typography.pptx.kicker / common.typography.marp.bodyPx}em;`
  );
  assertCssIncludes(
    "marp h1 line-height ↔ layout.titleLineHeight",
    `line-height: ${common.layout.titleLineHeight};`
  );
  assertCssIncludes(
    "marp h1 pad ↔ layout.titleBoxPadIn",
    `padding: 0 0 ${px(common.layout.titleBoxPadIn)}px;`
  );
  assertCssIncludes(
    "marp h1 gap ↔ layout.gapAfterTitleIn",
    `margin: 0 0 ${px(common.layout.gapAfterTitleIn)}px;`
  );
  assertCssIncludes(
    "marp diagram gap ↔ layout.gapAfterDiagramIn",
    `margin: 0 0 ${px(common.layout.gapAfterDiagramIn)}px;`
  );
  assertCssIncludes(
    "marp takeaway bottom ↔ layout.takeawayBottomIn",
    `bottom: ${px(common.layout.takeawayBottomIn)}px;`
  );
  assertCssIncludes(
    "marp takeaway inset ↔ layout.marginIn",
    `left: ${px(common.layout.marginIn)}px;`
  );
}

function checkVariantParity() {
  const light = pickSlice(loadOramTheme("oram-light"));
  const dark = pickSlice(loadOramTheme("oram-dark"));
  assertEqual("oram-light ↔ oram-dark layout slice", light, dark);
}

const common = readJson(COMMON_PATH);

checkCommonVsPptx(common);
checkCommonVsMarp(common);
checkMarpLayoutMatchesPptx(common);
checkVariantParity();

if (process.exitCode) {
  process.exit(process.exitCode);
}

console.log("All ORAM layout checks passed.");
