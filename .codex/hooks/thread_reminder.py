"""Count unique Codex user turns and emit non-blocking UI reminders."""
import json
import os
from pathlib import Path
import sqlite3
import sys


def process(event, state_dir):
    if event.get("hook_event_name") != "UserPromptSubmit":
        return {}
    session = event.get("session_id")
    turn = event.get("turn_id")
    if not isinstance(session, str) or not session or not isinstance(turn, str) or not turn:
        raise ValueError("missing session_id or turn_id")
    state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    with sqlite3.connect(str(state_dir / "turns.sqlite3"), timeout=2) as db:
        db.execute("CREATE TABLE IF NOT EXISTS turns (session TEXT, turn TEXT, PRIMARY KEY (session, turn))")
        db.execute("BEGIN IMMEDIATE")
        inserted = db.execute("INSERT OR IGNORE INTO turns VALUES (?, ?)", (session, turn)).rowcount
        if not inserted:
            return {}
        count = db.execute("SELECT COUNT(*) FROM turns WHERE session = ?", (session,)).fetchone()[0]
    if count != 8 and not (count >= 10 and count % 2 == 0):
        return {}
    if count == 8:
        message = "Session reminder: 8 user turns. Consider wrapping up at the next useful boundary and starting a new task for unrelated work."
    else:
        message = "Session reminder: {} user turns. Please wrap up at the next safe boundary and start a new task. Save a short handoff first if needed.".format(count)
    return {
        "systemMessage": message,
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": message + " This is advisory: finish authorized work; do not interrupt it or require permission solely because of this reminder.",
        },
    }


def main():
    # State contains opaque IDs only, never prompt text or transcript contents.
    os.umask(0o077)
    base = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local" / "state")))
    state = Path(os.environ.get("CODEX_THREAD_REMINDER_STATE_DIR", str(base / "personal-os" / "codex-thread-reminder")))
    try:
        result = process(json.load(sys.stdin), state)
    except (ValueError, TypeError, AttributeError, OSError, sqlite3.Error):
        result = {"systemMessage": "Session reminder could not update its counter. Check the hook setup in Harness Cost Runbook; this turn is continuing."}
    if result:
        print(json.dumps(result))


if __name__ == "__main__":
    main()
