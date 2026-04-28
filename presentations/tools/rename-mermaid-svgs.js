#!/usr/bin/env node

const fs = require("fs");
const path = require("path");

function fail(message) {
  console.error(`Error: ${message}`);
  process.exit(1);
}

const [, , sourceMdPathArg, imagesDirArg] = process.argv;

if (!sourceMdPathArg || !imagesDirArg) {
  fail(
    'Usage: node presentations/tools/rename-mermaid-svgs.js "<source.mermaid.md>" "<images-dir>"'
  );
}

const sourceMdPath = path.resolve(process.cwd(), sourceMdPathArg);
const imagesDir = path.resolve(process.cwd(), imagesDirArg);

const prefixArg = process.argv[4];
if (!prefixArg) {
  fail("Expected prefix argument (e.g. mmdc)");
}

const prefixRegex = new RegExp(`^${prefixArg}-\\d+\\.svg$`, "i");

if (!fs.existsSync(sourceMdPath)) {
  fail(`Source markdown not found: ${sourceMdPath}`);
}

if (!fs.existsSync(imagesDir)) {
  fail(`Images directory not found: ${imagesDir}`);
}

const text = fs.readFileSync(sourceMdPath, "utf8");

const idRegex = /%%\s*id:\s*"?([A-Za-z0-9_-]+)"?/g;
const ids = [];

let match;
while ((match = idRegex.exec(text)) !== null) {
  ids.push(match[1]);
}

if (ids.length === 0) {
  fail(`No Mermaid diagram ids found in ${sourceMdPath}`);
}

const duplicateIds = ids.filter((id, index) => ids.indexOf(id) !== index);
if (duplicateIds.length > 0) {
  fail(`Duplicate Mermaid ids found: ${[...new Set(duplicateIds)].join(", ")}`);
}

const allSvgFiles = fs.readdirSync(imagesDir).filter((file) => file.endsWith(".svg"));

function extractTrailingNumber(file) {
  const match = file.match(/(\d+)\.svg$/);
  return match ? parseInt(match[1], 10) : Number.MAX_SAFE_INTEGER;
}

function isLikelyMermaidExport(file) {
  return prefixRegex.test(file);
}
let files = allSvgFiles.filter(isLikelyMermaidExport);

files.sort((a, b) => {
  const ai = extractTrailingNumber(a);
  const bi = extractTrailingNumber(b);

  if (ai !== bi) return ai - bi;
  return a.localeCompare(b);
});

console.log(`Source markdown : ${sourceMdPath}`);
console.log(`Images directory: ${imagesDir}`);
console.log(`Found ids       : ${ids.join(", ")}`);
console.log(`Matched files   : ${files.length}`);

files.forEach((file) => console.log(`  MATCH: ${file}`));

if (files.length !== ids.length) {
  fail(`Mismatch: ${files.length} exported SVG files vs ${ids.length} ids.`);
}

files.forEach((file, index) => {
  const id = ids[index];
  const src = path.join(imagesDir, file);
  const dst = path.join(imagesDir, `${id}.svg`);

  if (src === dst) {
    console.log(`${file} already named ${id}.svg`);
    return;
  }

  if (fs.existsSync(dst)) {
    fs.unlinkSync(dst);
  }

  fs.renameSync(src, dst);
  console.log(`${file} → ${id}.svg`);
});

console.log("Done.");
