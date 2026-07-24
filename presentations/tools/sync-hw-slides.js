#!/usr/bin/env node

/**
 * Promote Charan's canonical HW deck from Google Drive into oram repo staging.
 * Manual step — not run on every build (local staging may have diagram edits).
 */

const crypto = require("crypto");
const fs = require("fs");
const path = require("path");
const readline = require("readline");
const { spawnSync } = require("child_process");

const REPO_ROOT = path.join(__dirname, "..", "..");
const PRESENTATIONS_DIR = path.join(__dirname, "..");
const STAGING_DIR = path.join(
  REPO_ROOT,
  "project_repos/oram/docs/presentations"
);
const STAGING_PPTX = path.join(STAGING_DIR, "ORAM Hardware Slides.pptx");
const STAGING_README = path.join(STAGING_DIR, "README.md");
const DEFAULT_UPSTREAM = path.join(
  process.env.HOME,
  "Library/CloudStorage/GoogleDrive-samit.chaudhuri@gmail.com/My Drive/Shared/oram/ORAM Hardware Slides.pptx"
);
const EXPECTED_SLIDES = 7;

const upstream = process.env.HW_SLIDES_UPSTREAM || DEFAULT_UPSTREAM;
const force = process.argv.includes("--force");
const dryRun = process.argv.includes("--dry-run");

function fail(message) {
  console.error(`Error: ${message}`);
  process.exit(1);
}

function sha256(filePath) {
  const hash = crypto.createHash("sha256");
  hash.update(fs.readFileSync(filePath));
  return hash.digest("hex");
}

function countSlides(pptxPath) {
  const venvPython = path.join(PRESENTATIONS_DIR, ".venv/bin/python");
  const python =
    process.env.PYTHON || (fs.existsSync(venvPython) ? venvPython : "python3");
  const snippet =
    "from pptx import Presentation; import sys; print(len(Presentation(sys.argv[1]).slides))";
  const result = spawnSync(python, ["-c", snippet, pptxPath], {
    encoding: "utf8",
  });
  if (result.status !== 0) {
    console.warn(
      "Warning: could not count slides (is python-pptx installed?). Skipping check."
    );
    return null;
  }
  return Number.parseInt(String(result.stdout).trim(), 10);
}

function ask(question) {
  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
  });
  return new Promise((resolve) => {
    rl.question(question, (answer) => {
      rl.close();
      resolve(answer.trim().toLowerCase());
    });
  });
}

function updateReadmeSyncedAt(isoDate) {
  const date = isoDate.slice(0, 10);
  let text = "";
  if (fs.existsSync(STAGING_README)) {
    text = fs.readFileSync(STAGING_README, "utf8");
  } else {
    text = `# ORAM Hardware Slides (staging)

Build input for the combined ORAM Company Pitch deck.

**Last synced from Drive:** (never)
`;
  }

  if (/\*\*Last synced from Drive:\*\* .+/m.test(text)) {
    text = text.replace(
      /\*\*Last synced from Drive:\*\* .+/m,
      `**Last synced from Drive:** ${date}`
    );
  } else {
    text += `\n**Last synced from Drive:** ${date}\n`;
  }

  fs.writeFileSync(STAGING_README, text);
}

async function main() {
  if (!fs.existsSync(upstream)) {
    fail(`Upstream not found: ${upstream}`);
  }

  fs.mkdirSync(STAGING_DIR, { recursive: true });

  const upstreamHash = sha256(upstream);
  const upstreamSlides = countSlides(upstream);
  if (upstreamSlides !== null && upstreamSlides !== EXPECTED_SLIDES) {
    console.warn(
      `Warning: upstream has ${upstreamSlides} slides (expected ${EXPECTED_SLIDES}).`
    );
  }

  if (fs.existsSync(STAGING_PPTX)) {
    const stagingHash = sha256(STAGING_PPTX);
    if (stagingHash === upstreamHash) {
      console.log("Staging already matches upstream. Nothing to do.");
      return;
    }

    console.log("Staging differs from upstream (local edits or older copy).");
    if (!force) {
      if (dryRun) {
        console.log("Dry run: would prompt to overwrite staging.");
        return;
      }
      const answer = await ask("Overwrite staging with upstream? [y/N] ");
      if (answer !== "y" && answer !== "yes") {
        console.log("Aborted. Staging unchanged.");
        return;
      }
    }
  } else {
    console.log("No staging copy yet; creating from upstream.");
  }

  if (dryRun) {
    console.log(`Dry run: would copy\n  ${upstream}\n→ ${STAGING_PPTX}`);
    return;
  }

  fs.copyFileSync(upstream, STAGING_PPTX);
  updateReadmeSyncedAt(new Date().toISOString());

  const stagingSlides = countSlides(STAGING_PPTX);
  console.log(`Copied to ${STAGING_PPTX}`);
  if (stagingSlides !== null) {
    console.log(`Slide count: ${stagingSlides}`);
  }
  console.log(
    "Commit in oram repo when ready: git -C project_repos/oram add docs/presentations/"
  );
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
