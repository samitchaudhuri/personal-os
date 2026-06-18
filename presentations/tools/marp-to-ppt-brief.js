#!/usr/bin/env node

// Generate a PowerPoint-connector brief from a Marp deck.
// The Marp file is the single source of truth. Per-deck design intent lives in
// the deck frontmatter under `ppt_design:` (a YAML block scalar) so it survives
// regeneration. This script is deterministic: edit the .marp.md and rerun.

const fs = require("fs");
const path = require("path");

function fail(message) {
  console.error(`Error: ${message}`);
  process.exit(1);
}

const [, , inputArg, outputArg] = process.argv;
if (!inputArg || !outputArg) {
  fail('Usage: node tools/marp-to-ppt-brief.js "<deck.marp.md>" "<out.ppt-brief.md>"');
}

const inputPath = path.resolve(process.cwd(), inputArg);
const outputPath = path.resolve(process.cwd(), outputArg);
if (!fs.existsSync(inputPath)) fail(`Input not found: ${inputPath}`);

const deckName = path.basename(inputPath).replace(/\.marp\.md$/, "");
const text = fs.readFileSync(inputPath, "utf8");

// --- Frontmatter ---
let frontmatter = "";
let body = text;
const fmMatch = text.match(/^---\n([\s\S]*?)\n---\n?/);
if (fmMatch) {
  frontmatter = fmMatch[1];
  body = text.slice(fmMatch[0].length);
}

function extractFrontmatterBlock(fm, key) {
  const blockRe = new RegExp(`(?:^|\\n)${key}:\\s*\\|\\s*\\n([\\s\\S]*?)(?=\\n\\S|$)`);
  const blockMatch = fm.match(blockRe);
  if (blockMatch) {
    const lines = blockMatch[1].split("\n");
    const indents = lines.filter((l) => l.trim()).map((l) => l.match(/^\s*/)[0].length);
    const min = indents.length ? Math.min(...indents) : 0;
    return lines.map((l) => l.slice(min)).join("\n").trim();
  }
  const lineMatch = fm.match(new RegExp(`(?:^|\\n)${key}:\\s*(.+)`));
  return lineMatch ? lineMatch[1].trim() : null;
}

const designText = extractFrontmatterBlock(frontmatter, "ppt_design");

// --- Strip Marp-only constructs that do not belong in the brief ---
body = body.replace(/<style>[\s\S]*?<\/style>/g, "");

// --- Split into slides on lines that are exactly `---` ---
const slideChunks = body
  .split(/\n---\s*\n/)
  .map((s) => s.trim())
  .filter((s) => s.length);

function stripTags(s) {
  return s
    .replace(/<[^>]+>/g, "")
    .replace(/&nbsp;/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

// Like stripTags, but preserve inline emphasis as Markdown so it survives into the brief.
function richText(s) {
  return s
    .replace(/<\/?(strong|b)\s*>/gi, "**")
    .replace(/<\/?(em|i)\s*>/gi, "*")
    .replace(/<[^>]+>/g, "")
    .replace(/&nbsp;/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function parseSlide(chunk) {
  const slide = {};

  const kicker = chunk.match(/<span class="label">([\s\S]*?)<\/span>/);
  slide.kicker = kicker ? stripTags(kicker[1]) : null;

  const title = chunk.match(/^#\s+(.+)$/m);
  slide.title = title ? title[1].trim() : null;

  slide.svg = null;
  const mermaid = chunk.match(/```mermaid([\s\S]*?)```/);
  if (mermaid) {
    const id = mermaid[1].match(/%%\s*id:\s*"?([\w-]+)"?/);
    if (id) slide.svg = `${id[1]}.svg`;
  }

  const takeaway = chunk.match(/<div class="takeaway">([\s\S]*?)<\/div>/);
  slide.takeaway = takeaway
    ? richText(takeaway[1])
        .replace(/^\*\*Takeaway:\*\*\s*/i, "")
        .replace(/^Takeaway:\s*/i, "")
        .trim()
    : null;

  const notes = chunk.match(/<!--([\s\S]*?)-->/);
  slide.notes = notes ? notes[1].trim() : null;

  slide.twocol = /class="cols"/.test(chunk);

  let b = chunk;
  b = b.replace(/<span class="label">[\s\S]*?<\/span>/g, "");
  b = b.replace(/^#\s+.+$/m, "");
  b = b.replace(/```mermaid[\s\S]*?```/g, "");
  b = b.replace(/<div class="takeaway">[\s\S]*?<\/div>/g, "");
  b = b.replace(/<!--[\s\S]*?-->/g, "");
  b = b.replace(/<\/?div[^>]*>/g, "");
  const lines = b.split("\n").map((l) => l.replace(/\s+$/, "")).filter((l) => l.trim());
  slide.body = lines.join("\n").trim();

  return slide;
}

const slides = slideChunks
  .map(parseSlide)
  .filter((s) => s.title || s.body || s.svg);

// --- Build the brief ---
const defaultDesign = [
  "- Clean, light, technical aesthetic. Generous whitespace, sans-serif.",
  "- Body text compact; one idea per slide.",
  "- Kicker label: small, uppercase, muted accent color.",
  '- Takeaway: full-width footer band, slightly emphasized background, bold lead-in word "Takeaway:".',
].join("\n");

let out = "";
out += `---\n`;
out += `generated_by: presentations/tools/marp-to-ppt-brief.js\n`;
out += `source: ${deckName}.marp.md\n`;
out += `---\n`;
out += `# PPT generation brief — ${deckName}\n\n`;
out += `> Generated artifact — do not hand-edit. Edit \`${deckName}.marp.md\` (content + diagrams) and its \`ppt_design:\` frontmatter, then regenerate.\n\n`;
out += `Paste this into Claude with the PowerPoint connector enabled, and attach the SVGs listed below.\n\n`;
out += `## Instructions for Claude\n\n`;
out += `- Build one slide per "## Slide N" section, in order.\n`;
out += `- Kicker: small uppercase label above the title. Title: the slide title. Body: the bullets and short paragraphs.\n`;
out += `- Render each "Takeaway:" as a single highlighted footer callout, not a bullet.\n`;
out += `- Put each "Notes:" block in the slide's speaker-notes pane, not on the slide.\n`;
out += `- Insert the named SVG (attached) as the slide's main visual. Do not recreate diagrams unless asked.\n`;
out += `- Diagrams are wide (landscape). Place each diagram **full-width** below the body, spanning the whole content area, and scale it to fill that width. Do not confine a diagram to a side column unless the slide is explicitly marked two-column. Never letterbox a wide diagram into a small box.\n`;
out += `- Follow the Design direction below for colors, type, and spacing.\n\n`;
out += `## Design direction\n\n`;
out += `${designText || defaultDesign}\n\n`;

out += `## Diagram assets\n\nAttach these from \`vault/Attachments/\`:\n\n`;
out += `| Slide | SVG file |\n| --- | --- |\n`;
slides.forEach((s, i) => {
  if (s.svg) out += `| ${i + 1} | \`${s.svg}\` |\n`;
});
out += `\n---\n\n`;

slides.forEach((s, i) => {
  out += `## Slide ${i + 1}\n\n`;
  if (s.kicker) out += `**Kicker:** ${s.kicker}\n`;
  if (s.title) out += `**Title:** ${s.title}\n`;
  if (s.svg) {
    out += `**Diagram:** \`${s.svg}\`${s.twocol ? " (layout: diagram + text, two-column)" : ""}\n`;
  } else if (s.twocol) {
    out += `**Layout:** two-column\n`;
  }
  out += `\n`;
  if (s.body) out += `**Body:**\n${s.body}\n\n`;
  if (s.takeaway) out += `**Takeaway:** ${s.takeaway}\n\n`;
  if (s.notes) out += `**Notes:**\n${s.notes}\n\n`;
  out += `---\n\n`;
});

fs.mkdirSync(path.dirname(outputPath), { recursive: true });
fs.writeFileSync(outputPath, out, "utf8");
console.log(`Wrote ${outputPath} (${slides.length} slides).`);
