#!/usr/bin/env bash
#
# mode-check.sh — Shared shell helper for mode-aware command blocking
#
# Source this from any bash script that needs mode guards:
#   source "$(dirname "$0")/lib/mode-check.sh"
#
# Then call:
#   mode_guard "brain-expand"
#
# Exit codes:
#   0 = allowed
#   10 = blocked (connected mode, mutation not allowed)

PLUGIN_LIB_DIR="${OPENCLAW_PLUGIN_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../lib" 2>/dev/null && pwd)}"

mode_guard() {
  local command_name="$1"
  local result
  result=$(python3 -c "
import sys, os
sys.path.insert(0, '${PLUGIN_LIB_DIR}')
from mode import check_mutation_allowed, get_mode
allowed, reason = check_mutation_allowed('${command_name}')
mode = get_mode()
if not allowed:
    print(f'BLOCKED|{reason}', end='')
    sys.exit(1)
elif reason == 'redirected_to_inbox':
    print(f'REDIRECT|{reason}', end='')
    sys.exit(0)
else:
    print(f'ALLOWED|{mode}', end='')
" 2>/dev/null)

  local exit_code=$?
  local status="${result%%|*}"
  local detail="${result#*|}"

  if [[ "$status" == "BLOCKED" ]]; then
    echo -e "\033[0;31m[BLOCKED]\033[0m $detail" >&2
    echo -e "\033[0;31m[BLOCKED]\033[0m Run 'openclaw-lacp-connect status' for connection info." >&2
    return 10
  fi

  # Export for callers that need to know
  export LACP_GUARD_STATUS="$status"
  export LACP_GUARD_DETAIL="$detail"
  return 0
}
