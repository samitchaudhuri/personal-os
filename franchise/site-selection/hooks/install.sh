#!/usr/bin/env bash
# Back-compat wrapper. Canonical installer: bash hooks/install.sh
set -euo pipefail
REPO_ROOT="$(git rev-parse --show-toplevel)"
exec "$REPO_ROOT/hooks/install.sh"
