#!/usr/bin/env bash
#
# env-source.sh — Source .engram.env config so env vars are available to all CLI scripts
#
# Source this from any bash script that needs vault/memory paths:
#   source "$(dirname "$0")/lib/env-source.sh"
#
# After sourcing, LACP_OBSIDIAN_VAULT and other vars from .engram.env
# will be exported (only if not already set in the environment).

_engram_env_file="${OPENCLAW_PLUGIN_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." 2>/dev/null && pwd)}/config/.engram.env"
if [[ -f "$_engram_env_file" ]]; then
    while IFS= read -r _engram_line; do
        _engram_line="${_engram_line%%#*}"
        _engram_line="${_engram_line#"${_engram_line%%[![:space:]]*}"}"
        [[ -z "$_engram_line" ]] && continue
        if [[ "$_engram_line" == *=* ]]; then
            _engram_key="${_engram_line%%=*}"
            _engram_val="${_engram_line#*=}"
            [[ -z "${!_engram_key:-}" ]] && export "$_engram_key=$_engram_val"
        fi
    done < "$_engram_env_file"
fi
unset _engram_env_file _engram_line _engram_key _engram_val
