#!/usr/bin/env node

const fs = require("fs");
const path = require("path");

function fail(message) {
  console.error(`Error: ${message}`);
  process.exit(1);
}

const {
  loadOramTheme,
  resolveThemeName,
  toMermaidConfig,
} = require("./load-oram-theme");
const { resolveDeckPaths } = require("./resolve-deck-sources");

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

const paths = resolveDeckPaths();
const inputPath = path.resolve(process.argv[2] || paths.marpPath);
const outputPath = path.resolve(process.argv[3] || paths.mermaidExtractPath);

if (!fs.existsSync(inputPath)) {
  fail(`Input Marp file not found: ${inputPath}`);
}

function makeFrontmatter(themeObject) {
  return `---\nconfig:\n${toYaml(themeObject, 2)}\n---`;
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

if (!inputText.match(/^---\n[\s\S]*?\n---/)) {
  fail("No Marp frontmatter found. Expected a top-level --- block.");
}

let variant;
try {
  variant = resolveThemeName();
} catch (err) {
  fail(err.message);
}

const theme = toMermaidConfig(loadOramTheme(variant));
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
  `Extracted ${diagrams.length} Mermaid diagram(s) from ${inputPath} using theme '${variant}'.`
);
console.log(`Wrote ${outputPath}.`);
