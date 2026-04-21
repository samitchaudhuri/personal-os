#!/usr/bin/env node

const fs = require('fs');
const path = require('path');

function fail(message) {
  console.error(`Error: ${message}`);
  process.exit(1);
}

const [, , inputPath, outputPath] = process.argv;

if (!inputPath || !outputPath) {
  fail('Expected input and output paths. Example: node tools/inject-mermaid-theme.js slides/talk.md build/talk.generated.md');
}

const themeDir = path.join(__dirname, '..', 'mermaid-themes');

function loadTheme(themeName) {
  const themePath = path.join(themeDir, `${themeName}.json`);
  if (!fs.existsSync(themePath)) {
    fail(`Theme file not found: ${themePath}`);
  }

  try {
    return JSON.parse(fs.readFileSync(themePath, 'utf8'));
  } catch (err) {
    fail(`Failed to parse theme JSON at ${themePath}: ${err.message}`);
  }
}

function toYaml(value, indent = 0) {
  const pad = ' '.repeat(indent);

  if (value === null) return 'null';

  if (Array.isArray(value)) {
    if (value.length === 0) return '[]';
    return value
      .map((item) => {
        const rendered = toYaml(item, indent + 2);
        if (rendered.includes('\n')) {
          return `${pad}- ${rendered.trimStart()}`;
        }
        return `${pad}- ${rendered}`;
      })
      .join('\n');
  }

  if (typeof value === 'object') {
    const entries = Object.entries(value);
    if (entries.length === 0) return '{}';

    return entries
      .map(([key, val]) => {
        const rendered = toYaml(val, indent + 2);
        if (
          typeof val === 'object' &&
          val !== null &&
          !(Array.isArray(val) && val.length === 0)
        ) {
          return `${pad}${key}:\n${rendered}`;
        }
        return `${pad}${key}: ${rendered}`;
      })
      .join('\n');
  }

  if (typeof value === 'string') {
    if (
      value === '' ||
      /[:#{}\[\],&*?|\-<>=!%@`]/.test(value) ||
      value.includes('\n')
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

const inputText = fs.readFileSync(inputPath, 'utf8');

/*
  Matches:
    ```mermaid
    ...
    ```
*/
const mermaidFenceRegex = /```mermaid\s*\n([\s\S]*?)```/g;

let replacements = 0;

const outputText = inputText.replace(mermaidFenceRegex, (fullMatch, body) => {
  const lines = body.split('\n');

  let themeName = null;
  const keptLines = [];

  for (const line of lines) {
    const themeMatch = line.match(/^%%\s*theme:\s*"?([A-Za-z0-9_-]+)"?\s*$/i);
    if (themeMatch) {
      themeName = themeMatch[1];
      continue;
    }

    keptLines.push(line);
  }

  if (!themeName) {
    return fullMatch;
  }

  const theme = loadTheme(themeName);
  const frontmatter = makeFrontmatter(theme);

  replacements += 1;
  return `\`\`\`mermaid\n${frontmatter}\n${keptLines.join('\n')}\n\`\`\``;
});

if (replacements === 0) {
  console.warn('Warning: No mermaid blocks with %% theme: ... were found.');
}

fs.mkdirSync(path.dirname(outputPath), { recursive: true });
fs.writeFileSync(outputPath, outputText, 'utf8');

console.log(`Wrote ${outputPath} with ${replacements} themed Mermaid diagram(s).`);