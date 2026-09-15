"""Run with /usr/bin/python3 .codex/hooks/check_thread_reminder.py."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor

hook = str(Path(__file__).with_name("thread-reminder.sh"))
with tempfile.TemporaryDirectory() as state:
    env = dict(os.environ, CODEX_THREAD_REMINDER_STATE_DIR=state)

    def run(turn, session="test", raw=None):
        event = dict(hook_event_name="UserPromptSubmit", session_id=session, turn_id=str(turn))
        result = subprocess.run(["/bin/bash", hook], input=json.dumps(event) if raw is None else raw,
                                text=True, capture_output=True, env=env, check=True)
        assert not result.stderr, result.stderr
        return json.loads(result.stdout) if result.stdout else {}

    warnings = []
    for turn in range(1, 15):
        result = run(turn)
        if result:
            warnings.append(turn)
            assert "systemMessage" in result and "decision" not in result
    assert warnings == [8, 10, 12, 14], warnings
    assert run(14) == {}
    assert run(1, "another-session") == {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        assert all(result == {} for result in pool.map(lambda _: run(15), range(6)))
    assert "16 user turns" in run(16)["systemMessage"]
    assert "could not update" in run(None, raw="not JSON")["systemMessage"]
    assert "could not update" in run(None, raw='{"hook_event_name":"UserPromptSubmit"}')["systemMessage"]
    assert run(None, raw='{"hook_event_name":"Stop"}') == {}
print("PASS: warning thresholds, UI output, persistence, deduplication, concurrency, session isolation, fail-open errors.")
