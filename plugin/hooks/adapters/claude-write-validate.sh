#!/bin/bash
# Claude Code PostToolUse adapter for engram write-validate
#
# Runs after Write/Edit tool calls to validate YAML frontmatter
# on knowledge vault files. Returns validation feedback as context.
#
# PostToolUse hook:
#   exit 0 with stdout = context shown to Claude
#   exit 2 = error shown to Claude (stderr)

set -euo pipefail

ENGRAM_DIR="${ENGRAM_DIR:-$(dirname "$(dirname "$(dirname "$(realpath "$0")")")")}"
HANDLER="$ENGRAM_DIR/hooks/handlers/write-validate.py"

if [ ! -f "$HANDLER" ]; then
  exit 0
fi

# Read Claude Code's PostToolUse payload from stdin
INPUT=$(cat)

# Build the payload write-validate expects
# Claude Code provides: tool_name, tool_input: { file_path, content, ... }
PAYLOAD=$(python3 -c "
import json, sys
data = json.load(sys.stdin)
ti = data.get('tool_input', {})
# Normalize path field
if 'path' in ti and 'file_path' not in ti:
    ti['file_path'] = ti['path']
print(json.dumps({'tool_input': ti}))
" <<< "$INPUT" 2>/dev/null)

if [ -z "$PAYLOAD" ]; then
  exit 0
fi

# Call write-validate.py
RESULT=$(echo "$PAYLOAD" | OPENCLAW_PLUGIN_DIR="$ENGRAM_DIR" \
  LACP_OBSIDIAN_VAULT="${LACP_OBSIDIAN_VAULT:-}" \
  python3 "$HANDLER" 2>/dev/null)
EXIT_CODE=$?

if [ -z "$RESULT" ]; then
  exit 0
fi

# Parse result and provide feedback
python3 -c "
import json, sys
try:
    data = json.loads(sys.stdin.read())
    status = data.get('status', 'SKIP')
    issues = data.get('issues', [])

    if status == 'SKIP':
        pass  # No output needed
    elif status == 'PASS':
        pass  # No output needed
    elif status == 'WARN':
        print('[engram] Write validation warnings:')
        for issue in issues:
            print(f'  - {issue}')
    elif status == 'FAIL':
        print('[engram] Write validation FAILED:')
        for issue in issues:
            print(f'  - {issue}')
        print('Fix the frontmatter before proceeding.')
except Exception:
    pass
" <<< "$RESULT"
