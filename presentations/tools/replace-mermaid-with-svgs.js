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

// Drop any slide carrying the local `<!-- _build: skip -->` hint so it is kept in
// the source deck but excluded from the exported PDF. Same convention the PPTX
// brief generator honors, so one marker skips a slide across every route.
const SKIP_SLIDE_RE = /<!--\s*_build:\s*skip\s*-->/;

function dropSkippedSlides(md) {
  const fmMatch = md.match(/^---\n[\s\S]*?\n---\n?/);
  const head = fmMatch ? fmMatch[0] : "";
  const rest = fmMatch ? md.slice(fmMatch[0].length) : md;
  const kept = rest.split(/\n---\s*\n/).filter((chunk) => !SKIP_SLIDE_RE.test(chunk));
  return head + kept.join("\n---\n");
}

const finalText = dropSkippedSlides(outputText);
const skipped = outputText.split(/\n---\s*\n/).length - finalText.split(/\n---\s*\n/).length;

fs.mkdirSync(path.dirname(outputMarpPath), { recursive: true });
fs.writeFileSync(outputMarpPath, finalText, "utf8");

console.log(`Replaced ${replacements} Mermaid block(s).`);
if (skipped > 0) console.log(`Skipped ${skipped} slide(s) marked _build: skip.`);
console.log(`Wrote ${outputMarpPath}.`);
