#!/bin/bash
# Claude Code SessionStart adapter for engram session-start
#
# Calls session-start.py and translates its systemMessage output
# into Claude Code's additionalContext format.

set -euo pipefail

ENGRAM_DIR="${ENGRAM_DIR:-$(dirname "$(dirname "$(dirname "$(realpath "$0")")")")}"
HANDLER="$ENGRAM_DIR/hooks/handlers/session-start.py"

if [ ! -f "$HANDLER" ]; then
  exit 0
fi

# Read Claude Code's SessionStart payload from stdin
INPUT=$(cat)

# Call session-start.py with the payload
RESULT=$(echo "$INPUT" | OPENCLAW_PLUGIN_DIR="$ENGRAM_DIR" \
  LACP_OBSIDIAN_VAULT="${LACP_OBSIDIAN_VAULT:-}" \
  CLAUDE_SESSION_ID="$(echo "$INPUT" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("session_id",""))' 2>/dev/null)" \
  python3 "$HANDLER" 2>/dev/null)

if [ -z "$RESULT" ]; then
  exit 0
fi

# Extract systemMessage and return as additionalContext
python3 -c "
import json, sys
try:
    data = json.loads('''$(echo "$RESULT" | sed "s/'/\\\\'/g")''')
    msg = data.get('systemMessage', '')
    if msg:
        # For SessionStart, stdout text becomes context for Claude
        print(msg)
except Exception:
    pass
"
