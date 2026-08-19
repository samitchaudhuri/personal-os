#!/usr/bin/env bash
# Enforces AGENTS.md Cost Management "Long threads" rule mechanically,
# since relying on the model to self-track turn count has failed before.
set -euo pipefail

input=$(cat)
sid=$(echo "$input" | jq -r '.session_id // "unknown"')

counter_dir="${TMPDIR:-/tmp}/claude-thread-reminder"
mkdir -p "$counter_dir"
f="$counter_dir/$sid"

n=$(( $(cat "$f" 2>/dev/null || echo 0) + 1 ))
echo "$n" > "$f"

msg=""
if [ "$n" -eq 8 ]; then
  msg="This session has reached about 8 user exchanges. Per AGENTS.md's Cost Management guidance, tell the user now: suggest wrapping up or starting a new chat for anything not tightly coupled to this thread's context."
elif [ "$n" -ge 10 ] && [ $(( (n - 10) % 10 )) -eq 0 ]; then
  msg="This session has reached $n user exchanges, well past the ~10-turn threshold. Per AGENTS.md's Cost Management guidance, strongly tell the user now to wrap up or start a new chat."
fi

if [ -n "$msg" ]; then
  jq -n --arg msg "$msg" '{hookSpecificOutput: {hookEventName: "UserPromptSubmit", additionalContext: $msg}}'
fi
