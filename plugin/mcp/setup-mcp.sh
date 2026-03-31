#!/usr/bin/env bash
# setup-mcp.sh — register Engram as an MCP server for Claude Code / Codex
set -euo pipefail

# ── Resolve paths ──────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENGRAM_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SERVER_MJS="$SCRIPT_DIR/server.mjs"

# ── Resolve Obsidian vault path ────────────────────────────────────
resolve_vault() {
  # 1. Environment variable
  if [[ -n "${LACP_OBSIDIAN_VAULT:-}" ]]; then
    echo "$LACP_OBSIDIAN_VAULT"
    return
  fi

  # 2. config/.engram.env
  local env_file="$ENGRAM_DIR/config/.engram.env"
  if [[ -f "$env_file" ]]; then
    local val
    val="$(grep -E '^LACP_OBSIDIAN_VAULT=' "$env_file" 2>/dev/null | head -1 | cut -d= -f2-)"
    if [[ -n "$val" ]]; then
      echo "$val"
      return
    fi
  fi

  # 3. Default
  echo "$HOME/.openclaw/data/knowledge"
}

VAULT_PATH="$(resolve_vault)"

# ── Resolve absolute node path (nvm doesn't export to subprocesses) ─
NODE_BIN="$(command -v node 2>/dev/null || which node 2>/dev/null)"
if [[ -z "$NODE_BIN" ]]; then
  echo "Error: node not found in PATH" >&2
  exit 1
fi

# ── Build mcpServers JSON block ────────────────────────────────────
MCP_JSON=$(cat <<ENDJSON
{
  "mcpServers": {
    "engram": {
      "type": "stdio",
      "command": "$NODE_BIN",
      "args": ["$SERVER_MJS"],
      "env": {
        "ENGRAM_DIR": "$ENGRAM_DIR",
        "LACP_OBSIDIAN_VAULT": "$VAULT_PATH"
      }
    }
  }
}
ENDJSON
)

# ── Helpers ────────────────────────────────────────────────────────
merge_into() {
  local target="$1"
  mkdir -p "$(dirname "$target")"

  if [[ -f "$target" ]]; then
    # Merge mcpServers key into existing settings
    local tmp
    tmp="$(mktemp)"
    # Use python3 (available on macOS) for reliable JSON merge
    python3 -c "
import json, sys
with open('$target') as f:
    existing = json.load(f)
patch = json.loads('''$MCP_JSON''')
existing.setdefault('mcpServers', {})
existing['mcpServers'].update(patch['mcpServers'])
json.dump(existing, sys.stdout, indent=2)
print()
" > "$tmp"
    mv "$tmp" "$target"
  else
    echo "$MCP_JSON" | python3 -c "
import json, sys
data = json.load(sys.stdin)
json.dump(data, sys.stdout, indent=2)
print()
" > "$target"
  fi

  echo "Wrote engram MCP config to $target"
}

usage() {
  cat <<EOF
Usage: setup-mcp.sh [--global | --project | --print]

  --global   Merge into ~/.claude.json            (user-wide)
  --project  Merge into .mcp.json                (current repo)
  --print    Print the mcpServers JSON to stdout

NOTE: For Codex compatibility, create .codex/mcp.json in your repo with
the same mcpServers block. Use --print to get the JSON, then place it at
.codex/mcp.json manually.
EOF
}

# ── Main ───────────────────────────────────────────────────────────
MODE="${1:-}"

case "$MODE" in
  --print)
    echo "$MCP_JSON"
    echo ""
    echo "# Codex: save the above JSON to .codex/mcp.json in your repo."
    ;;
  --global)
    merge_into "$HOME/.claude.json"
    echo ""
    echo "# Codex: save the mcpServers JSON to .codex/mcp.json in your repo."
    ;;
  --project)
    merge_into ".mcp.json"
    echo ""
    echo "# Codex: save the mcpServers JSON to .codex/mcp.json in your repo."
    ;;
  *)
    usage
    exit 1
    ;;
esac
