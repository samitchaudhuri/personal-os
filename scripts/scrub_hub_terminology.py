#!/usr/bin/env python3
"""Replace vault 'hub' execution terminology with 'project'. Idempotent-ish."""

from __future__ import annotations

import re
import sys
from pathlib import Path

VAULT = Path("/Users/samit/Vaults/Samit Personal Vault")
REPO_AGENTS = Path("/Users/samit/work/personal-os/AGENTS.md")

# Protect unrelated "hub" uses before global passes
PROTECT = [
    ("Obsidian Hub", "\x00OBSIDIAN_HUB\x00"),
    ("publish.obsidian.md/hub/", "\x00OBSIDIAN_HUB_URL\x00"),
    ("healthspan hub", "\x00HEALTHSPAN_HUB\x00"),
    ("John Wayne (SNA) Hub", "\x00AIRPORT_HUB\x00"),
    ('"multi-hub"', "\x00MULTI_HOP_QUOTE\x00"),
]

REPLACEMENTS = [
    # Longer phrases first
    ("project hub notes", "project notes"),
    ("project hub note", "project note"),
    ("project hub paths", "project note paths"),
    ("project hub tasks", "project tasks"),
    ("project hub or", "project or"),
    ("paired project hub", "paired project"),
    ("No paired project hub", "No paired project"),
    ("Portfolio-only notes (no paired project yet)", "Portfolio-only notes (no paired project yet)"),
    ("When to add only a project hub", "When to add only a project"),
    ("Pull execution detail off the project hub", "Pull execution detail off the project"),
    ("between portfolio and project hub:", "between portfolio and project:"),
    ("The **project hub** carries", "The **project** carries"),
    ("parent project hub explicitly", "parent project explicitly"),
    ("parent project hub:", "parent project:"),
    ("Roadmap** and **tasks** live on the **project hub**", "Roadmap** and **tasks** live on the **project**"),
    ("both portfolio and project hub start", "both portfolio and project start"),
    ("| **Project hub** |", "| **Project** |"),
    ("| Project hub (Notes/) |", "| Project (Notes/) |"),
    ("| `#task/personal-os` | Personal OS project hub:", "| `#task/personal-os` | Personal OS project:"),
    ("project hubs (`Notes/* Project.md`)", "projects (`Notes/* Project.md`)"),
    ("project hubs", "projects"),
    ("project hub", "project"),
    ("Project hub —", "Project —"),
    ("Project hub:", "Project:"),
    ("Project hub", "Project"),
    ("Execution hub (Notes/)", "Execution project (Notes/)"),
    ("execution hub", "execution project"),
    ("[[Execution hub]]", "paired `Notes/* Project` note"),
    ("Working Sessions hub", "Working Sessions note"),
    ("job search hub", "job search project"),
    ("multi-week hub", "multi-week project"),
    ("Daily note hub rollup", "Daily note project rollup"),
    ("daily-note hub rollup", "daily-note project rollup"),
    ("### Hub rollup", "### Project rollup"),
    ("Historical hub rollup", "Historical project rollup"),
    ("Daily hub rollup", "Daily project rollup"),
    ("hub rollup", "project rollup"),
    ("Hub rollup", "Project rollup"),
    ("hub-only", "project-only"),
    ("hub tasks", "project tasks"),
    ("hub task", "project task"),
    ("hub truth", "project truth"),
    ("hub deadlines", "project deadlines"),
    ("hub sections", "project sections"),
    ("management second brain hub", "management second brain project"),
    ("on the Personal OS hub", "on the Personal OS project"),
    ("on the Management OS hub", "on the Management OS project"),
    ("Personal OS hub", "Personal OS project"),
    ("Management OS hub", "Management OS project"),
    ("promoted hub tasks", "promoted project tasks"),
    ("orphan hub tasks", "orphan project tasks"),
    ("promoted hub task", "promoted project task"),
    ("draft hub task", "draft project task"),
    ("Hub **Skills roadmap**", "Project **Skills roadmap**"),
    ("remove or merge on the hub", "remove or merge on the project"),
    ("duplicate on a project note", "duplicate on a project note"),
    ("duplicate on hub", "duplicate on the project"),
    ("do not duplicate on the hub", "do not duplicate on the project"),
    ("do not duplicate on hub", "do not duplicate on the project"),
    ("on the hub —", "on the project —"),
    ("on the hub,", "on the project,"),
    ("on the hub", "on the project"),
    ("vs. hubs", "vs. projects"),
    ("ad-hoc hub edits", "ad-hoc project edits"),
    ("new hub notes", "new project notes"),
    ("Keeping hubs here", "Keeping projects here"),
    ("touched a project or", "touched a project or"),
    ("unpaired hub", "unpaired project"),
    ("not real hubs", "not real projects"),
    ("[[Hub Name]]", "[[Project name]]"),
    ("**Hub:**", "**Project:**"),
    ("| Hub:", "| Project:"),
    ("Hub: [[", "Project: [["),
    ("**Hub ↔ artifact", "**Project ↔ artifact"),
    ("Hub ↔ artifact", "Project ↔ artifact"),
    ("artifact → hub", "artifact → project"),
    ("checkboxes on the hub", "checkboxes on the project"),
    ("the hub scannable", "the project scannable"),
    ("clutter the hub.", "clutter the project."),
    ("clutter the hub", "clutter the project"),
    ("BIC hub task", "BIC project task"),
    ("ULC hub (", "ULC project ("),
    ("| ULC hub |", "| ULC project |"),
    ("(hub task)", "(project task)"),
    ("Hub for **active job search**", "Project for **active job search**"),
    ("Hub: [[Charan", "Working sessions: [[Charan"),
    ("· hub tasks above", "· project tasks above"),
    ("🟡 → hub):", "🟡 → project):"),
    ("hubs, meetings", "projects, meetings"),
    ("optional link to hubs you built", "optional link to projects you built"),
    ("hubs are separate initiatives", "projects are separate initiatives"),
    ("| **`project`** | Your execution hub", "| **`project`** | Your execution project"),
    ("the program-level checkboxes on the hub", "the program-level checkboxes on the project"),
    ("working-session hubs", "working-session project notes"),
    ("project and working-session project notes", "projects and working-session notes"),
    ("read the Notes/ hub,", "read the Notes/ project,"),
    ("do not read the Notes/ hub", "do not read the Notes/ project"),
    ("explain hub truth", "explain project truth"),
    ("**Daily note hub rollup (reconcile with hubs):**", "**Daily note project rollup (reconcile with projects):**"),
    ("reconcile with hubs):", "reconcile with projects):"),
    ("past `vault/Daily/` hub rollup", "past `vault/Daily/` project rollup"),
    ("`vault/Daily/` hub rollup", "`vault/Daily/` project rollup"),
    ("after hub rollup", "after project rollup"),
    ("every **Reference projects** hub", "every **Reference project** in"),
    ("**Reference projects** hub,", "**Reference project** (Reference projects table),"),
    ("**Reference project** hub", "**Reference project**"),
    ("Reference project hub", "Reference project"),
    ("Notes/ **project**", "Notes/ **project**"),
    ("Notes/ project hub", "Notes/ project"),
    ("Initiative | Project hub", "Initiative | Project"),
    ("├── Notes/          # Goals, Backlog, project hubs", "├── Notes/          # Goals, Backlog, projects"),
    ("synthesized into another note (Working Sessions note).", "synthesized into another note (Working Sessions note)."),
    ("The hub [[Learning", "See [[Learning"),
    ("| Hub (above)", "| This note (above)"),
    ("| This hub;", "| This note;"),
    ("This hub;", "This note;"),
    ("still open on hub sections", "still open on project sections"),
    ("on [[ULC Evaluation]] hub.", "on [[ULC Evaluation]] project."),
    ("Meeting notes (canonical — do not duplicate on the project):", "Meeting notes (canonical — do not duplicate on the project):"),
    ("| Daily plan theme (May 26 eve) | Hub truth (Jun 2) |", "| Daily plan theme (May 26 eve) | Project truth (Jun 2) |"),
    ("under **Skills roadmap** on the **Management OS** project", "under **Skills roadmap** on the **Management OS** project"),
    ("Promoted from Maven **Adopted in my OS** (🟡 → project):", "Promoted from Maven **Adopted in my OS** (🟡 → project):"),
    # Standalone "hub" in agent docs (careful order — after compounds)
    (" so hub ", " so project "),
    (" hub,", " project,"),
    (" hub.", " project."),
    (" hub ", " project "),
]


def protect(text: str) -> str:
    for orig, token in PROTECT:
        text = text.replace(orig, token)
    return text


def unprotect(text: str) -> str:
    for orig, token in PROTECT:
        text = text.replace(token, orig)
    return text


def scrub(text: str) -> str:
    text = protect(text)
    for old, new in REPLACEMENTS:
        if old != new:
            text = text.replace(old, new)
    text = unprotect(text)
    return text


def should_process(path: Path) -> bool:
    if path.suffix != ".md":
        return False
    if "References/Ultimate Longevity" in str(path):
        return False  # healthspan hub marketing copy
    if "@egiazarian" in path.name:
        return False
    return True


def main() -> int:
    targets: list[Path] = []
    if REPO_AGENTS.exists():
        targets.append(REPO_AGENTS)
    if VAULT.is_dir():
        targets.extend(p for p in sorted(VAULT.rglob("*.md")) if should_process(p))

    changed: list[Path] = []
    seen: set[Path] = set()
    for path in targets:
        path = path.resolve()
        if path in seen:
            continue
        seen.add(path)
        original = path.read_text(encoding="utf-8")
        updated = scrub(original)
        if updated != original:
            path.write_text(updated, encoding="utf-8")
            changed.append(path)

    for p in changed:
        print(p)
    print(f"\nUpdated {len(changed)} files.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
