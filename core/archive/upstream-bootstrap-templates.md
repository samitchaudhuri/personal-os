# Upstream bootstrap templates (removed)

**Removed:** 2026-07-02  
**Last commit with templates:** `0c6e435` (before clean cut)

## What this was

Aman Khan's upstream **personal-os** bootstrap: on first `./setup.sh`, copy starter files from `core/templates/` into the repo root so a new clone could run without a vault.

| File | Purpose |
| --- | --- |
| `AGENTS.md` | MCP-first PM task agent (~18 KB): backlog dedup, `Tasks/`, categories P0–P3, writing tone rules |
| `gitignore` | Ignore personal `Tasks/`, `BACKLOG.md`, local `AGENTS.md` / `GOALS.md` |
| `config.yaml` | Optional MCP categories, priorities, dedup threshold |

## Why removed

This fork is **vault-centric** (Obsidian symlink, workflows in `vault/Agent/`). Keeping upstream templates:

- Duplicated live policy (`AGENTS.md` → `vault/Agent/Agents.md`)
- Added a nested Cursor rule (`core/templates/AGENTS.md`, ~18 KB when that path was in context)
- Required maintaining a second onboarding story we no longer use

## Replaced by

- Root **`AGENTS.md`** symlink → `vault/Agent/Agents.md`
- **`vault/README.md`** — vault structure and conventions
- **`vault/Agent/Workflows/`** — on-demand workflows (referenced from live `Agents.md`)
- Root **`.gitignore`** — already present; not copied from template

## Restore from git

```bash
# List files at last commit that had templates
git ls-tree -r 0c6e435 -- core/templates/

# View a specific file
git show 0c6e435:core/templates/AGENTS.md
git show 0c6e435:core/templates/gitignore
git show 0c6e435:core/templates/config.yaml
```

Upstream source: [amanaiproduct/personal-os](https://github.com/amanaiproduct/personal-os)
