#!/usr/bin/env node

const { spawnSync } = require("child_process");
const path = require("path");

const PRESENTATIONS_DIR = path.join(__dirname, "..");

function run(command, args, options = {}) {
  const result = spawnSync(command, args, {
    cwd: PRESENTATIONS_DIR,
    stdio: "inherit",
    ...options,
  });

  if (result.error) {
    console.error(result.error.message);
    process.exit(1);
  }

  if (result.status !== 0) {
    process.exit(result.status ?? 1);
  }
}

module.exports = { PRESENTATIONS_DIR, run };
