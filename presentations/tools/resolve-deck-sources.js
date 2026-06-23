#!/usr/bin/env node

const fs = require("fs");
const path = require("path");

const PRESENTATIONS_DIR = path.join(__dirname, "..");
const REPO_ROOT = path.join(PRESENTATIONS_DIR, "..");
const BUILD_DIR = path.join(PRESENTATIONS_DIR, "build");

function fail(message) {
  console.error(`Error: ${message}`);
  process.exit(1);
}

function readFrontmatter(notePath) {
  if (!fs.existsSync(notePath)) {
    fail(`File not found: ${notePath}`);
  }
  const text = fs.readFileSync(notePath, "utf8");
  const match = text.match(/^---\n([\s\S]*?)\n---/);
  if (!match) {
    fail(`No YAML frontmatter in ${notePath}`);
  }
  return match[1];
}

function readFrontmatterField(frontmatter, key) {
  const match = frontmatter.match(
    new RegExp(`^${key}:\\s*"?([^"\\n]+)"?\\s*$`, "m")
  );
  return match ? match[1].trim() : null;
}

function parseDeckSources(frontmatter) {
  const sources = [];
  let current = null;
  let inSources = false;

  for (const line of frontmatter.split("\n")) {
    if (/^deck_sources:\s*$/.test(line)) {
      inSources = true;
      continue;
    }
    if (!inSources) continue;
    if (/^[A-Za-z0-9_]+:/.test(line)) break;

    const item = line.match(/^  - file:\s*(.+)\s*$/);
    if (item) {
      current = { file: item[1].trim() };
      sources.push(current);
      continue;
    }
    const kv = line.match(/^    (\w+):\s*(.+)\s*$/);
    if (kv && current) {
      current[kv[1]] = kv[2].trim();
    }
  }

  if (!sources.length) {
    fail("Deck note frontmatter has no deck_sources: list.");
  }
  return sources;
}

function inferSourceType(source) {
  if (source.type) return source.type;
  const p = (source.path || "").toLowerCase();
  if (p.endsWith(".marp.md")) return "marp";
  if (p.endsWith(".pptx")) return "pptx";
  fail(
    `deck_sources entry '${source.file}' needs type: marp or pptx (or a .marp.md / .pptx path).`
  );
}

function expandUser(p) {
  if (p.startsWith("~/")) {
    return path.join(process.env.HOME || "", p.slice(2));
  }
  return p;
}

function resolveSourcePath(pathStr, defaultRepoRelative) {
  const raw = (pathStr || "").trim() || (defaultRepoRelative || "").trim();
  if (!raw) fail("Source path is empty.");
  let p = expandUser(raw);
  if (!path.isAbsolute(p)) {
    p = path.join(REPO_ROOT, p);
  }
  return path.resolve(p);
}

function deckNameFromNotePath(deckNotePath) {
  const base = path.basename(deckNotePath, ".md");
  if (base.endsWith(" Deck")) {
    return base.slice(0, -" Deck".length);
  }

  fail(
    `Deck note must be named "<name> Deck.md" (got ${path.basename(deckNotePath)}).`
  );
}

function findMarpSourceForDeckNote(deckNotePath) {
  const sources = parseDeckSources(readFrontmatter(deckNotePath));
  const marp = sources.filter((s) => inferSourceType(s) === "marp");
  if (marp.length !== 1) {
    fail(
      `Deck note must declare exactly one marp source (found ${marp.length} in ${deckNotePath}).`
    );
  }
  const src = marp[0];
  const resolved = resolveSourcePath(
    src.path,
    `vault/Notes/${src.file}.marp.md`
  );
  if (!fs.existsSync(resolved)) {
    fail(`Marp source not found: ${resolved}`);
  }
  return { ...src, type: "marp", path: resolved };
}

function buildArtifactPaths(buildPrefix) {
  return {
    mermaidExtractPath: path.join(BUILD_DIR, `${buildPrefix}.mermaid.md`),
    marpExportPath: path.join(BUILD_DIR, `${buildPrefix}.marp.export.md`),
    pptBriefPath: path.join(BUILD_DIR, `${buildPrefix}.ppt-brief.md`),
    pptxThemePath: path.join(BUILD_DIR, `${buildPrefix}.pptx-theme.json`),
    marpExportPptxPath: path.join(BUILD_DIR, `${buildPrefix}.marp.export.pptx`),
    combinedPptxPath: path.join(BUILD_DIR, `${buildPrefix}.combined.pptx`),
  };
}

function resolveDeckMode(deckNotePath) {
  const resolvedNote = path.resolve(deckNotePath);
  const deck = deckNameFromNotePath(resolvedNote);
  const marpSource = findMarpSourceForDeckNote(resolvedNote);
  const artifacts = buildArtifactPaths(deck);

  return {
    buildMode: "deck",
    buildPrefix: deck,
    deck,
    deckNotePath: resolvedNote,
    marpPath: marpSource.path,
    marpFile: path.basename(marpSource.path).replace(/\.marp\.md$/, ""),
    themeSourcePath: resolvedNote,
    pngDir: path.join(BUILD_DIR, "png"),
    attachmentsDir: path.join(REPO_ROOT, "vault", "Attachments"),
    svgRelativeDir: "../../vault/Attachments",
    ...artifacts,
  };
}

function resolveMarpMode(marpPath) {
  const resolvedMarp = path.resolve(marpPath);
  if (!fs.existsSync(resolvedMarp)) {
    fail(`MARP_INPUT not found: ${resolvedMarp}`);
  }
  if (!resolvedMarp.endsWith(".marp.md")) {
    fail(`MARP_INPUT must be a .marp.md file: ${resolvedMarp}`);
  }

  const marpFile = path.basename(resolvedMarp).replace(/\.marp\.md$/, "");
  const artifacts = buildArtifactPaths(marpFile);

  return {
    buildMode: "marp",
    buildPrefix: marpFile,
    deck: null,
    deckNotePath: null,
    marpPath: resolvedMarp,
    marpFile,
    themeSourcePath: resolvedMarp,
    pngDir: path.join(BUILD_DIR, "png"),
    attachmentsDir: path.join(REPO_ROOT, "vault", "Attachments"),
    svgRelativeDir: "../../vault/Attachments",
    ...artifacts,
  };
}

function resolveDeckPaths() {
  const deckNoteEnv = process.env.DECK_NOTE;
  const marpInputEnv = process.env.MARP_INPUT;

  if (deckNoteEnv) {
    return resolveDeckMode(deckNoteEnv);
  }
  if (marpInputEnv) {
    return resolveMarpMode(marpInputEnv);
  }

  fail(
    "Set DECK_NOTE (path to <deck> Deck.md) or MARP_INPUT (path to .marp.md). " +
      "Open the source file and run a Slides: Build… VS Code task."
  );
}

function requireDeckMode(paths, action) {
  if (paths.buildMode !== "deck") {
    fail(
      `${action} requires a deck note. Open <deck> Deck.md and run Slides: Build Combined PPTX.`
    );
  }
}

module.exports = {
  BUILD_DIR,
  buildArtifactPaths,
  deckNameFromNotePath,
  findMarpSourceForDeckNote,
  parseDeckSources,
  readFrontmatter,
  readFrontmatterField,
  requireDeckMode,
  resolveDeckMode,
  resolveDeckPaths,
  resolveMarpMode,
  resolveSourcePath,
};

if (require.main === module) {
  console.log(JSON.stringify(resolveDeckPaths(), null, 2));
}
