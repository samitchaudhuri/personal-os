#!/usr/bin/env node

const fs = require("fs");
const path = require("path");

const { loadOramTheme, resolveThemeName, toPptxPalette } = require("./load-oram-theme");
const { resolveDeckPaths } = require("./resolve-deck-sources");

const paths = resolveDeckPaths();
const variant = resolveThemeName({ themeSourcePath: paths.themeSourcePath });
const palette = toPptxPalette(loadOramTheme(variant));

fs.mkdirSync(path.dirname(paths.pptxThemePath), { recursive: true });
fs.writeFileSync(
  paths.pptxThemePath,
  `${JSON.stringify(palette, null, 2)}\n`,
  "utf8"
);
console.log(`Wrote ${paths.pptxThemePath} (${variant}).`);
