#!/bin/bash
# Claude Code PreToolUse adapter for engram pretool-guard
#
# Reads Claude Code's tool_input JSON from stdin, calls pretool-guard.py
# in structured mode, and translates the verdict to Claude's format.
#
# Claude Code decisions: "allow", "deny", "ask"
# engram verdicts:       "allow", "block", "warn", "log"

set -euo pipefail

ENGRAM_DIR="${ENGRAM_DIR:-$(dirname "$(dirname "$(dirname "$(realpath "$0")")")")}"
GUARD_SCRIPT="$ENGRAM_DIR/hooks/handlers/pretool-guard.py"

if [ ! -f "$GUARD_SCRIPT" ]; then
  # Guard script not found — fail open (allow)
  exit 0
fi

# Read Claude Code's payload from stdin
INPUT=$(cat)

# Extract tool_input based on Claude Code's payload shape
# Claude sends: { tool_name, tool_input: { command, file_path, ... }, ... }
TOOL_INPUT=$(echo "$INPUT" | python3 -c "
import json, sys
data = json.load(sys.stdin)
# Normalize: Claude uses 'file_path' in Write/Edit/Read but 'path' sometimes
ti = data.get('tool_input', {})
if 'path' in ti and 'file_path' not in ti:
    ti['file_path'] = ti['path']
print(json.dumps({'tool_input': ti, 'tool_name': data.get('tool_name', '')}))
" 2>/dev/null)

if [ -z "$TOOL_INPUT" ]; then
  exit 0
fi

# Call the guard in structured mode
VERDICT=$(echo "$TOOL_INPUT" | python3 "$GUARD_SCRIPT" structured 2>/dev/null)

if [ -z "$VERDICT" ]; then
  exit 0
fi

# Translate verdict to Claude Code format
python3 -c "
import json, sys

verdict = json.loads('''$VERDICT''')
v = verdict.get('verdict', 'allow')

if v == 'block':
    print(json.dumps({
        'hookSpecificOutput': {
            'hookEventName': 'PreToolUse',
            'permissionDecision': 'deny',
            'permissionDecisionReason': verdict.get('message', 'Blocked by engram guard'),
        }
    }))
elif v == 'warn':
    print(json.dumps({
        'hookSpecificOutput': {
            'hookEventName': 'PreToolUse',
            'permissionDecision': 'ask',
            'permissionDecisionReason': verdict.get('message', 'Flagged by engram guard'),
        }
    }))
# allow and log: exit 0 with no output
"
