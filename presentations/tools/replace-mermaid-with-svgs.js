#!/usr/bin/env node

const fs = require("fs");
const path = require("path");

function fail(message) {
  console.error(`Error: ${message}`);
  process.exit(1);
}

const [, , sourceMarpPathArg, outputMarpPathArg, svgRelativeDirArg] = process.argv;

if (!sourceMarpPathArg || !outputMarpPathArg || !svgRelativeDirArg) {
  fail(
    'Usage: node presentations/tools/replace-mermaid-with-svgs.js "<source.marp.md>" "<output.marp.export.md>" "<svg-relative-dir>"'
  );
}

const sourceMarpPath = path.resolve(process.cwd(), sourceMarpPathArg);
const outputMarpPath = path.resolve(process.cwd(), outputMarpPathArg);
const svgRelativeDir = svgRelativeDirArg.replace(/\/$/, "");

if (!fs.existsSync(sourceMarpPath)) {
  fail(`Source Marp file not found: ${sourceMarpPath}`);
}

const inputText = fs.readFileSync(sourceMarpPath, "utf8");

const mermaidFenceRegex = /```mermaid\s*\n([\s\S]*?)```/g;

let replacements = 0;

const outputText = inputText.replace(mermaidFenceRegex, (fullMatch, body) => {
  const idMatch = body.match(/^%%\s*id:\s*"?([^"\n]+)"?\s*$/m);

  if (!idMatch) {
    fail(`Mermaid block #${replacements + 1} is missing an id. Add: %% id: "diagram_name"`);
  }

  const id = idMatch[1].trim();
  replacements += 1;

  return `![](${svgRelativeDir}/${id}.svg)`;
});

if (replacements === 0) {
  fail("No Mermaid blocks found.");
}

fs.mkdirSync(path.dirname(outputMarpPath), { recursive: true });
fs.writeFileSync(outputMarpPath, outputText, "utf8");

console.log(`Replaced ${replacements} Mermaid block(s).`);
console.log(`Wrote ${outputMarpPath}.`);
