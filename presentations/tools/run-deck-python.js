#!/usr/bin/env node

const path = require("path");
const { resolveDeckPaths, requireDeckMode } = require("./resolve-deck-sources");
const { run } = require("./run-child");

function fail(message) {
  console.error(`Error: ${message}`);
  process.exit(1);
}

const tool = process.argv[2];
const paths = resolveDeckPaths();
const python = path.join(".venv", "bin", "python");

if (tool === "brief") {
  run(python, [
    "tools/brief-to-pptx.py",
    paths.pptBriefPath,
    paths.pngDir,
    paths.marpExportPptxPath,
    paths.pptxThemePath,
  ]);
} else if (tool === "combine") {
  requireDeckMode(paths, "Combine");
  run(python, [
    "tools/combine-pptx.py",
    paths.pptBriefPath,
    paths.pngDir,
    paths.combinedPptxPath,
    paths.deckNotePath,
    paths.pptxThemePath,
  ]);
} else {
  fail(`Unknown tool "${tool}". Expected brief or combine.`);
}
