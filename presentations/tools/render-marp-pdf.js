#!/usr/bin/env node

const { resolveDeckPaths } = require("./resolve-deck-sources");
const { run } = require("./run-child");

const paths = resolveDeckPaths();

run("marp", [
  paths.marpExportPath,
  "--pdf",
  "--pdf-notes",
  "--allow-local-files",
  "--no-stdin",
  "--theme-set",
  "themes/pdf",
]);
