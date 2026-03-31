#!/bin/bash
# Setup engram hooks for Claude Code
#
# Generates the hooks config with resolved paths and merges it
# into ~/.claude/settings.json or .claude/settings.json (project-level).
#
# Usage:
#   setup-claude-code.sh [--global|--project]
#   setup-claude-code.sh --print   # just print the config, don't install

set -euo pipefail

ENGRAM_DIR="${ENGRAM_DIR:-$(dirname "$(dirname "$(dirname "$(realpath "$0")")")")}"
SCOPE="${1:---global}"

# Resolve absolute paths to each adapter
SESSION_START="$ENGRAM_DIR/hooks/adapters/claude-session-start.sh"
PRETOOL_GUARD="$ENGRAM_DIR/hooks/adapters/claude-pretool-guard.sh"
WRITE_VALIDATE="$ENGRAM_DIR/hooks/adapters/claude-write-validate.sh"
STOP_GATE="$ENGRAM_DIR/hooks/adapters/claude-stop-quality-gate.sh"

# Generate the hooks JSON with real paths
HOOKS_JSON=$(python3 -c "
import json

hooks = {
    'hooks': {
        'SessionStart': [{
            'hooks': [{
                'type': 'command',
                'command': '$SESSION_START',
                'timeout': 15,
                'statusMessage': 'Injecting engram context...'
            }]
        }],
        'PreToolUse': [
            {
                'matcher': 'Bash',
                'hooks': [{
                    'type': 'command',
                    'command': '$PRETOOL_GUARD',
                    'timeout': 10,
                    'statusMessage': 'Checking guard rules...'
                }]
            },
            {
                'matcher': 'Read|Write|Edit',
                'hooks': [{
                    'type': 'command',
                    'command': '$PRETOOL_GUARD',
                    'timeout': 10,
                    'statusMessage': 'Checking guard rules...'
                }]
            }
        ],
        'PostToolUse': [{
            'matcher': 'Write|Edit',
            'hooks': [{
                'type': 'command',
                'command': '$WRITE_VALIDATE',
                'timeout': 10,
                'statusMessage': 'Validating write...'
            }]
        }],
        'Stop': [{
            'hooks': [{
                'type': 'command',
                'command': '$STOP_GATE',
                'timeout': 35,
                'statusMessage': 'Running quality gate...'
            }]
        }]
    }
}

print(json.dumps(hooks, indent=2))
")

if [ "$SCOPE" = "--print" ]; then
  echo "$HOOKS_JSON"
  exit 0
fi

# Determine target settings file
if [ "$SCOPE" = "--project" ]; then
  TARGET=".claude/settings.json"
  mkdir -p .claude
else
  TARGET="$HOME/.claude/settings.json"
  mkdir -p "$HOME/.claude"
fi

# Merge into existing settings (or create new)
if [ -f "$TARGET" ]; then
  python3 -c "
import json, sys

with open('$TARGET', 'r') as f:
    existing = json.load(f)

new_hooks = json.loads('''$HOOKS_JSON''')

# Merge hooks: append engram hooks to existing ones
if 'hooks' not in existing:
    existing['hooks'] = {}

for event, matchers in new_hooks['hooks'].items():
    if event not in existing['hooks']:
        existing['hooks'][event] = []
    # Check if engram hooks already installed (by command path)
    existing_cmds = set()
    for m in existing['hooks'][event]:
        for h in m.get('hooks', []):
            existing_cmds.add(h.get('command', ''))
    for matcher in matchers:
        for h in matcher.get('hooks', []):
            if h.get('command', '') not in existing_cmds:
                existing['hooks'][event].append(matcher)
                break

with open('$TARGET', 'w') as f:
    json.dump(existing, f, indent=2)
    f.write('\n')

print(f'Engram hooks merged into {\"$TARGET\"}')
"
else
  echo "$HOOKS_JSON" > "$TARGET"
  echo "Engram hooks written to $TARGET"
fi

echo ""
echo "Hooks installed:"
echo "  SessionStart  -> session-start.py (git context + LACP memory)"
echo "  PreToolUse    -> pretool-guard.py (block/warn dangerous ops)"
echo "  PostToolUse   -> write-validate.py (frontmatter validation)"
echo "  Stop          -> stop-quality-gate.py (incomplete work detection)"
