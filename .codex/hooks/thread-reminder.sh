#!/usr/bin/env bash
# Codex adapter. Shared harness documentation: Harness Cost Runbook.
set -euo pipefail
exec /usr/bin/python3 "$(cd "$(dirname "$0")" && pwd)/thread_reminder.py"
