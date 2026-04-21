const fs = require('fs');
const path = require('path');

const DEFAULT_IMAGES_DIR = "/Users/samit/Google Drive/Obsidian/Samit Personal Vault/Attachments";

const [, , sourceMdPath, exportedFromMdPathArg, imagesDirArg] = process.argv;

if (!sourceMdPath) {
  console.error("Usage: node tools/rename-mermaid-svgs.js <source.md> [exported-from.md] [images-dir]");
  process.exit(1);
}

const exportedFromMdPath = exportedFromMdPathArg || sourceMdPath;
const imagesDir = imagesDirArg || DEFAULT_IMAGES_DIR;

if (!fs.existsSync(sourceMdPath)) {
  console.error(`Source markdown not found: ${sourceMdPath}`);
  process.exit(1);
}

if (!fs.existsSync(imagesDir)) {
  console.error(`Images directory not found: ${imagesDir}`);
  process.exit(1);
}

const text = fs.readFileSync(sourceMdPath, 'utf8');

// Extract ids in order from the source markdown
const idRegex = /%%\s*id:\s*"?([A-Za-z0-9_-]+)"?/g;

const ids = [];
let match;
while ((match = idRegex.exec(text)) !== null) {
  ids.push(match[1]);
}

let exportBase = path.basename(exportedFromMdPath, path.extname(exportedFromMdPath));
const prefix = `${exportBase}-`;

const allSvgFiles = fs.readdirSync(imagesDir).filter(f => f.endsWith('.svg'));

const files = allSvgFiles
  .filter(f => f.startsWith(prefix))
  .sort((a, b) => {
    const ai = parseInt(a.match(/-(\d+)\.svg$/)?.[1] || '0', 10);
    const bi = parseInt(b.match(/-(\d+)\.svg$/)?.[1] || '0', 10);
    return ai - bi;
  });

console.log(`Source markdown   : ${sourceMdPath}`);
console.log(`Exported from     : ${exportedFromMdPath}`);
console.log(`Images directory  : ${imagesDir}`);
console.log(`Export base       : ${exportBase}`);
console.log(`Expected prefix   : ${prefix}`);
console.log(`Found ids         : ${ids.length ? ids.join(', ') : '(none)'}`);
console.log(`Matched files     : ${files.length}`);
files.forEach(f => console.log(`  MATCH: ${f}`));

if (files.length !== ids.length) {
  console.warn(`Mismatch: ${files.length} exported files vs ${ids.length} ids in ${sourceMdPath}`);
}

files.forEach((file, i) => {
  if (!ids[i]) return;

  const src = path.join(imagesDir, file);
  const dst = path.join(imagesDir, `${ids[i]}.svg`);

  fs.renameSync(src, dst);
  console.log(`${file} → ${ids[i]}.svg`);
});