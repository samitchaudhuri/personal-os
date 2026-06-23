#!/usr/bin/env node

const fs = require("fs");
const path = require("path");

const { VALID_VARIANTS, loadOramTheme } = require("./load-oram-theme");
const { renderLayoutCss, renderVariantCss } = require("./marp-pdf-theme-render");

const ROOT = path.join(__dirname, "..");
const PDF_DIR = path.join(ROOT, "themes", "pdf");
const INCLUDE_DIR = path.join(ROOT, "themes", "includes");

function writeIfChanged(filePath, content) {
  const next = `${content.trimEnd()}\n`;
  if (fs.existsSync(filePath)) {
    const current = fs.readFileSync(filePath, "utf8");
    if (current === next) return false;
  }
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, next, "utf8");
  return true;
}

function main() {
  const merged = loadOramTheme("oram-light");
  const commonOnly = {
    font: merged.font,
    slide: merged.slide,
    layout: merged.layout,
    typography: merged.typography,
    columns: merged.columns,
  };

  const layoutPath = path.join(INCLUDE_DIR, "oram-layout.css");
  const layoutWritten = writeIfChanged(
    layoutPath,
    renderLayoutCss(commonOnly, "oram-light")
  );

  let variantsWritten = 0;
  for (const variant of VALID_VARIANTS) {
    const theme = loadOramTheme(variant);
    const outPath = path.join(PDF_DIR, `${variant}.css`);
    if (writeIfChanged(outPath, renderVariantCss(variant, theme))) {
      variantsWritten += 1;
    }
  }

  console.log(
    `Marp PDF themes: ${layoutWritten ? "updated" : "unchanged"} layout, ${variantsWritten} variant file(s) updated in themes/pdf/ and themes/includes/.`
  );
}

main();
