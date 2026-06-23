#!/usr/bin/env node

const fs = require("fs");
const path = require("path");

const { VALID_VARIANTS, loadOramTheme } = require("./load-oram-theme");
const { renderLayoutCss, renderVariantCss } = require("./marp-pdf-theme-render");

const ROOT = path.join(__dirname, "..");
const PDF_DIR = path.join(ROOT, "themes", "pdf");
const INCLUDE_DIR = path.join(ROOT, "themes", "includes");

function fail(message) {
  console.error(`Error: ${message}`);
  process.exit(1);
}

function read(filePath) {
  if (!fs.existsSync(filePath)) {
    fail(`Missing ${filePath}. Run npm run themes:generate-pdf.`);
  }
  return fs.readFileSync(filePath, "utf8");
}

function assertIncludes(label, haystack, needle) {
  if (!haystack.includes(needle)) {
    console.error(`FAIL ${label}: expected to include ${JSON.stringify(needle)}`);
    process.exitCode = 1;
    return false;
  }
  console.log(`ok ${label}`);
  return true;
}

const common = loadOramTheme("oram-light");
const layoutPath = path.join(INCLUDE_DIR, "oram-layout.css");
const layoutCss = read(layoutPath);
const expectedLayout = renderLayoutCss(
  {
    font: common.font,
    slide: common.slide,
    layout: common.layout,
    typography: common.typography,
    columns: common.columns,
  },
  "oram-light"
);

if (layoutCss.trimEnd() !== expectedLayout.trimEnd()) {
  console.error("FAIL oram-layout.css is stale. Run npm run themes:generate-pdf.");
  process.exitCode = 1;
} else {
  console.log("ok oram-layout.css matches generator");
}

assertIncludes(
  "layout body size",
  layoutCss,
  `font-size: ${common.typography.marp.bodyPx}px`
);

for (const variant of VALID_VARIANTS) {
  const merged = loadOramTheme(variant);
  const themePath = path.join(PDF_DIR, `${variant}.css`);
  const themeCss = read(themePath);
  const expected = renderVariantCss(variant, merged);

  if (themeCss.trimEnd() !== expected.trimEnd()) {
    console.error(`FAIL ${variant}.css is stale. Run npm run themes:generate-pdf.`);
    process.exitCode = 1;
    continue;
  }

  console.log(`ok ${variant}.css matches generator`);
  assertIncludes(`${variant} background`, themeCss, merged.colors.background);
  assertIncludes(`${variant} @theme`, themeCss, `@theme ${merged.pdf.marpTheme}`);
  assertIncludes(
    `${variant} marp base`,
    themeCss,
    `@import '${variant === "oram-dark" ? "uncover" : "gaia"}'`
  );
  assertIncludes(
    `${variant} inlined layout`,
    themeCss,
    `font-size: ${merged.typography.marp.bodyPx}px`
  );
  assertIncludes(`${variant} top-align section`, themeCss, "place-content: normal");
  assertIncludes(`${variant} hide marp header`, themeCss, "header,\nfooter");
  if (themeCss.includes("@import '../includes/oram-layout.css'")) {
    console.error(`FAIL ${variant}.css must inline layout (Marp cannot import outside theme-set).`);
    process.exitCode = 1;
  }
}

if (process.exitCode) {
  process.exit(process.exitCode);
}

console.log("All Marp PDF theme checks passed.");
