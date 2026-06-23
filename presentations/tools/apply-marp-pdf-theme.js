#!/usr/bin/env node

const fs = require("fs");
const path = require("path");

const {
  loadOramTheme,
  resolveThemeName,
} = require("./load-oram-theme");
const { resolveDeckPaths } = require("./resolve-deck-sources");

function fail(message) {
  console.error(`Error: ${message}`);
  process.exit(1);
}

const paths = resolveDeckPaths();
const exportMarpPath = path.resolve(process.argv[2] || paths.marpExportPath);

if (!fs.existsSync(exportMarpPath)) {
  fail(`Export Marp file not found: ${exportMarpPath}`);
}

let variant;
try {
  variant = resolveThemeName();
} catch (err) {
  fail(err.message);
}

const merged = loadOramTheme(variant);
const marpTheme = merged.pdf?.marpTheme || variant;

let text = fs.readFileSync(exportMarpPath, "utf8");

// Layout and colors come from themes/pdf/*.css (phase 4+).
text = text.replace(/<style>[\s\S]*?<\/style>\s*\n?/i, "");

if (/^theme:\s*[^\n]+\s*$/m.test(text)) {
  text = text.replace(/^theme:\s*[^\n]+\s*$/m, `theme: ${marpTheme}`);
} else {
  text = text.replace(
    /^(---\n[\s\S]*?\n)(---\n)/,
    `$1theme: ${marpTheme}\n$2`
  );
}

fs.writeFileSync(exportMarpPath, text, "utf8");
console.log(`PDF Marp theme: ${marpTheme} (${variant}); removed inline <style>.`);
