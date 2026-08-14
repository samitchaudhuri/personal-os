#!/usr/bin/env bash
# One-time installer: symlink the tracked pre-commit hook into .git/hooks.
# Run once per clone:  bash hooks/install.sh
# (Git hooks live outside version control, so each clone must install once.)
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
SRC="$REPO_ROOT/hooks/pre-commit"
DEST="$REPO_ROOT/.git/hooks/pre-commit"

chmod +x "$SRC"
if [ -e "$DEST" ] && [ ! -L "$DEST" ]; then
  echo "A non-symlink pre-commit hook already exists at $DEST; back it up first." >&2
  exit 1
fi
ln -sf "$SRC" "$DEST"
echo "Installed pre-commit hook: $DEST -> $SRC"
