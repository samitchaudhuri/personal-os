#!/usr/bin/env node

const fs = require("fs");
const path = require("path");

function fail(message) {
  console.error(`Error: ${message}`);
  process.exit(1);
}

const [, , inputPath, outputPath] = process.argv;

if (!inputPath || !outputPath) {
  fail(
    "Expected input and output paths. Example: node tools/extract-mermaid.js slides/slides.marp.md slides/slides.mermaid.md"
  );
}

const themeDir = path.join(__dirname, "..", "mermaid-themes");

function loadTheme(themeName) {
  const themePath = path.join(themeDir, `${themeName}.json`);

  if (!fs.existsSync(themePath)) {
    fail(`Theme file not found: ${themePath}`);
  }

  try {
    return JSON.parse(fs.readFileSync(themePath, "utf8"));
  } catch (err) {
    fail(`Failed to parse theme JSON at ${themePath}: ${err.message}`);
  }
}

function toYaml(value, indent = 0) {
  const pad = " ".repeat(indent);

  if (value === null) return "null";

  if (Array.isArray(value)) {
    if (value.length === 0) return "[]";

    return value
      .map((item) => {
        const rendered = toYaml(item, indent + 2);
        return rendered.includes("\n")
          ? `${pad}- ${rendered.trimStart()}`
          : `${pad}- ${rendered}`;
      })
      .join("\n");
  }

  if (typeof value === "object") {
    const entries = Object.entries(value);
    if (entries.length === 0) return "{}";

    return entries
      .map(([key, val]) => {
        const rendered = toYaml(val, indent + 2);

        if (
          typeof val === "object" &&
          val !== null &&
          !(Array.isArray(val) && val.length === 0)
        ) {
          return `${pad}${key}:\n${rendered}`;
        }

        return `${pad}${key}: ${rendered}`;
      })
      .join("\n");
  }

  if (typeof value === "string") {
    if (
      value === "" ||
      /[:#{}\[\],&*?|\-<>=!%@`]/.test(value) ||
      value.includes("\n")
    ) {
      return JSON.stringify(value);
    }

    return value;
  }

  return String(value);
}

function makeFrontmatter(themeObject) {
  return `---\nconfig:\n${toYaml(themeObject, 2)}\n---`;
}

function extractMarpTheme(inputText) {
  const frontmatterMatch = inputText.match(/^---\n([\s\S]*?)\n---/);

  if (!frontmatterMatch) {
    fail("No Marp frontmatter found. Expected a top-level --- block with theme: <name>.");
  }

  const frontmatter = frontmatterMatch[1];
  const themeMatch = frontmatter.match(/^theme:\s*"?([A-Za-z0-9_-]+)"?\s*$/m);

  if (!themeMatch) {
    fail("No global Marp theme found. Expected `theme: gaia` or similar in frontmatter.");
  }

  return themeMatch[1];
}

function extractDiagramId(body, index) {
  const idMatch = body.match(/^%%\s*id:\s*"?([^"\n]+)"?\s*$/m);

  if (!idMatch) {
    fail(`Mermaid diagram #${index + 1} is missing an id. Add: %% id: "diagram_name"`);
  }

  return idMatch[1].trim();
}

function stripPerDiagramTheme(body) {
  return body
    .split("\n")
    .filter((line) => !line.match(/^%%\s*theme:\s*"?([A-Za-z0-9_-]+)"?\s*$/i))
    .join("\n")
    .trim();
}

const inputText = fs.readFileSync(inputPath, "utf8");
const themeName = extractMarpTheme(inputText);
const theme = loadTheme(themeName);
const frontmatter = makeFrontmatter(theme);

const mermaidFenceRegex = /```mermaid\s*\n([\s\S]*?)```/g;

const diagrams = [];
const seenIds = new Set();

let match;
let index = 0;

while ((match = mermaidFenceRegex.exec(inputText)) !== null) {
  const rawBody = match[1];
  const id = extractDiagramId(rawBody, index);

  if (seenIds.has(id)) {
    fail(`Duplicate Mermaid diagram id found: ${id}`);
  }

  seenIds.add(id);

  const body = stripPerDiagramTheme(rawBody);

  diagrams.push(`\`\`\`mermaid\n${frontmatter}\n${body}\n\`\`\``);
  index += 1;
}

if (diagrams.length === 0) {
  fail("No Mermaid diagrams found.");
}

const outputText = diagrams.join("\n\n");

fs.mkdirSync(path.dirname(outputPath), { recursive: true });
fs.writeFileSync(outputPath, outputText, "utf8");

console.log(
  `Extracted ${diagrams.length} Mermaid diagram(s) from ${inputPath} using theme '${themeName}'.`
);
console.log(`Wrote ${outputPath}.`);
