#!/usr/bin/env node

const path = require("path");
const { run } = require("./run-child");

function fail(message) {
  console.error(`Error: ${message}`);
  process.exit(1);
}

const npmScript = process.argv[2];
const activeFile = process.argv[3];
const deckOnly = process.argv.includes("--deck-only");

if (!npmScript) {
  fail("Usage: node tools/run-active-file.js <npm-script> <active-file> [--deck-only]");
}

if (!activeFile) {
  fail(
    "No active file. Open a .marp.md or <deck> Deck.md file and run the task again."
  );
}

const base = path.basename(activeFile);

if (deckOnly) {
  if (!base.endsWith(" Deck.md")) {
    fail(`Combine requires a deck note (* Deck.md). Got: ${base}`);
  }
  process.env.DECK_NOTE = activeFile;
} else if (base.endsWith(".marp.md")) {
  process.env.MARP_INPUT = activeFile;
} else if (base.endsWith(" Deck.md")) {
  process.env.DECK_NOTE = activeFile;
} else {
  fail(
    `Active file must be *.marp.md or * Deck.md. Got: ${base}`
  );
}

run("npm", ["run", npmScript], { env: process.env });
