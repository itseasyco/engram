#!/bin/bash
# Claude Code Stop adapter for engram stop-quality-gate
#
# Calls stop-quality-gate.py and blocks the stop if it detects
# incomplete work, rationalization patterns, or failed tests.
#
# Claude Code Stop hook:
#   exit 0 = allow stop
#   exit 2 = block stop (stderr shown as reason)

set -euo pipefail

ENGRAM_DIR="${ENGRAM_DIR:-$(dirname "$(dirname "$(dirname "$(realpath "$0")")")")}"
HANDLER="$ENGRAM_DIR/hooks/handlers/stop-quality-gate.py"

if [ ! -f "$HANDLER" ]; then
  exit 0
fi

# Read Claude Code's Stop payload from stdin
INPUT=$(cat)

# Build the payload the quality gate expects
# Claude Code provides: session_id, transcript_path, cwd
PAYLOAD=$(python3 -c "
import json, sys
data = json.load(sys.stdin)
print(json.dumps({
    'session_id': data.get('session_id', ''),
    'transcript_path': data.get('transcript_path', ''),
    'cwd': data.get('cwd', ''),
}))
" <<< "$INPUT" 2>/dev/null)

if [ -z "$PAYLOAD" ]; then
  exit 0
fi

# Call stop-quality-gate.py
RESULT=$(echo "$PAYLOAD" | OPENCLAW_PLUGIN_DIR="$ENGRAM_DIR" \
  python3 "$HANDLER" 2>/tmp/engram-stop-gate-stderr)
EXIT_CODE=$?

if [ $EXIT_CODE -eq 1 ]; then
  # Quality gate blocked the stop
  REASON=$(python3 -c "
import json, sys
try:
    data = json.loads(sys.stdin.read())
    print(data.get('reason', 'Quality gate detected incomplete work'))
except Exception:
    print('Quality gate detected incomplete work')
" <<< "$RESULT" 2>/dev/null)
  echo "$REASON" >&2
  exit 2
fi

exit 0
