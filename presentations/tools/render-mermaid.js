#!/usr/bin/env node

const fs = require("fs");
const path = require("path");
const { resolveDeckPaths } = require("./resolve-deck-sources");
const { run } = require("./run-child");

function fail(message) {
  console.error(`Error: ${message}`);
  process.exit(1);
}

const format = (process.argv[2] || "svg").toLowerCase();
const paths = resolveDeckPaths();

if (format === "svg") {
  run("mmdc", [
    "-i",
    paths.mermaidExtractPath,
    "-o",
    path.join(paths.attachmentsDir, "mmdc.svg"),
    "--backgroundColor",
    "transparent",
  ]);
} else if (format === "png") {
  fs.rmSync(paths.pngDir, { recursive: true, force: true });
  fs.mkdirSync(paths.pngDir, { recursive: true });

  run("mmdc", [
    "-i",
    paths.mermaidExtractPath,
    "-o",
    path.join(paths.pngDir, "mmdc.png"),
    "-s",
    "3",
    "--backgroundColor",
    "transparent",
  ]);
} else {
  fail(`Unknown format "${format}". Expected svg or png.`);
}
