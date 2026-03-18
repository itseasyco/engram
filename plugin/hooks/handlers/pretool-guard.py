#!/usr/bin/env python3
"""
PreToolGuard Hook for OpenClaw

Blocks dangerous command patterns before execution:
- npm publish, git reset --hard, docker --privileged
- curl|python pipes, fork bombs, scp to /root
- Protected file access (.env, secrets, PEM keys)

Implements TTL-based approval caching (12h default) using OpenClaw session IDs.
"""

import hashlib
import json
import os
import re
import shlex
import sys
import time
from pathlib import Path
from typing import Optional, Tuple, Dict, List

# ============================================================================
# Configuration
# ============================================================================

DEFAULT_TTL_SECONDS = 12 * 3600  # 12 hours
APPROVAL_CACHE_DIR = Path.home() / ".openclaw" / "approval-cache"

# Dangerous command patterns (extracted from LACP)
DANGEROUS_PATTERNS = [
    (re.compile(r"\b(?:npm|yarn|pnpm|cargo)\s+publish\b", re.IGNORECASE),
     "npm publish, yarn publish, etc.",
     "BLOCKED: Publishing to registry requires explicit user approval. Ask the user first."),

    (re.compile(r"\b(?:curl|wget)\b.*\|\s*(?:python3?|node|ruby|perl)\b", re.IGNORECASE),
     "curl|python pipes (network-to-interpreter)",
     "BLOCKED: Piping network content to an interpreter is unsafe. Download first, review, then run."),

    (re.compile(r"\bchmod\s+(?:-R\s+)?777\b"),
     "chmod 777 (overly permissive)",
     "BLOCKED: chmod 777 is overly permissive. Use specific permissions (e.g. 755, 644)."),

    (re.compile(r"\bgit\s+reset\s+--hard\b", re.IGNORECASE),
     "git reset --hard",
     "BLOCKED: git reset --hard is destructive. Ask the user first."),

    (re.compile(r"\bgit\s+clean\s+-f", re.IGNORECASE),
     "git clean -f",
     "BLOCKED: git clean -f is destructive. Ask the user first."),

    (re.compile(r"\bdocker\s+run\b[^\n\r]*--privileged\b", re.IGNORECASE),
     "docker run --privileged",
     "BLOCKED: docker run --privileged is a security risk. Use specific capabilities instead."),

    (re.compile(r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:"),
     "fork bomb",
     "BLOCKED: Fork bomb detected."),

    (re.compile(r"\b(?:scp|rsync)\b.*[\s:/]/root(?:/|$|\s)", re.IGNORECASE),
     "scp/rsync to /root",
     "BLOCKED: scp/rsync to /root is restricted. Use a non-root target path."),

    (re.compile(r"\b(?:curl|wget)\b.*(?:-d|--data|--data-binary)\s+@[^\s]*(?:\.env|\.ssh|credentials|\.key|\.pem|secrets)", re.IGNORECASE),
     "data exfiltration from sensitive files",
     "BLOCKED: potential data exfiltration from sensitive file."),
]

# Protected file patterns (read/write protection)
PROTECTED_PATHS = re.compile(
    r"(\.env($|\.)|config\.toml($|\.)|(?:^|/)secret(?:s)?(?:/|$|\.)|\.claude/settings\.json$|authorized_keys$"
    r"|\.(pem|key)$|(^|/)\.gnupg(/|$))",
    re.IGNORECASE
)

# ============================================================================
# Session ID Resolution (OpenClaw-specific, replacing TMUX_PANE)
# ============================================================================


def _get_session_id() -> str:
    """
    Resolve OpenClaw session ID for approval caching scope.
    
    Priority:
    1. Explicit OPENCLAW_SESSION_ID environment variable
    2. Fallback to other terminal/window identifiers
    3. Fallback to CWD hash if no session available
    
    Returns a unique, stable session identifier.
    """
    # Explicit OpenClaw session ID
    explicit = os.getenv("OPENCLAW_SESSION_ID", "").strip()
    if explicit:
        return explicit

    # Try other terminal identifiers
    for key in ("TMUX_PANE", "WEZTERM_PANE", "ITERM_SESSION_ID", "TERM_SESSION_ID", "WINDOWID"):
        val = os.getenv(key, "").strip()
        if val:
            return f"{key}:{val}"

    # Fallback to CWD hash
    cwd = os.getcwd()
    digest = hashlib.sha1(cwd.encode("utf-8")).hexdigest()[:12]
    return f"cwd:{digest}"


# ============================================================================
# Approval Cache (TTL-based)
# ============================================================================


def _get_approval_key(session_id: str, pattern_name: str) -> str:
    """Generate unique key for approval cache entry."""
    key_data = f"{session_id}:{pattern_name}"
    digest = hashlib.sha256(key_data.encode()).hexdigest()[:16]
    return f"session_{digest}"


def _approval_cache_path(session_id: str, pattern_name: str) -> Path:
    """Get file path for approval cache entry."""
    key = _get_approval_key(session_id, pattern_name)
    return APPROVAL_CACHE_DIR / f"{key}.json"


def _is_approved(session_id: str, pattern_name: str, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> bool:
    """
    Check if a dangerous pattern was previously approved in this session.
    
    Returns True if approval exists and is still valid (within TTL).
    Returns False if no approval or approval expired.
    """
    cache_path = _approval_cache_path(session_id, pattern_name)
    if not cache_path.exists():
        return False

    try:
        cache_data = json.loads(cache_path.read_text())
        approved_at = cache_data.get("approved_at", 0)
        now = time.time()
        age = now - approved_at
        return age < ttl_seconds
    except Exception:
        return False


def _mark_approved(session_id: str, pattern_name: str) -> None:
    """Mark a pattern as approved in this session."""
    APPROVAL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = _approval_cache_path(session_id, pattern_name)
    cache_data = {
        "pattern": pattern_name,
        "session_id": session_id,
        "approved_at": int(time.time()),
        "approved_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "ttl_seconds": DEFAULT_TTL_SECONDS,
    }
    cache_path.write_text(json.dumps(cache_data, indent=2) + "\n")


# ============================================================================
# Payload Parsing
# ============================================================================


def _read_payload() -> Dict:
    """Read and parse JSON payload from stdin."""
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except Exception as e:
        print(f"WARNING: Failed to parse payload: {e}", file=sys.stderr)
        return {}


def _get_command(payload: Dict) -> str:
    """Extract command from tool payload."""
    # Handle OpenClaw tool_input format
    tool_input = payload.get("tool_input", {})
    cmd = tool_input.get("command", "")
    return str(cmd) if cmd else ""


def _get_file_path(payload: Dict) -> str:
    """Extract file path from tool payload."""
    tool_input = payload.get("tool_input", {})
    file_path = tool_input.get("file_path", "")
    if not file_path:
        return ""
    try:
        return str(Path(file_path).expanduser().resolve())
    except Exception:
        return str(file_path)


# ============================================================================
# Dangerous Pattern Detection
# ============================================================================


def _detect_dangerous_command(cmd: str, session_id: str) -> Optional[str]:
    """
    Check command against dangerous patterns.
    
    Returns:
        None if safe
        Error message string if dangerous and not approved
    """
    if not cmd.strip():
        return None

    for pattern, pattern_name, error_msg in DANGEROUS_PATTERNS:
        if pattern.search(cmd):
            # Check if already approved in this session
            if _is_approved(session_id, pattern_name):
                print(f"✓ Pattern '{pattern_name}' approved in this session (cached)", file=sys.stderr)
                return None

            return error_msg

    return None


def _detect_protected_file_access(file_path: str) -> Optional[str]:
    """
    Check if file path matches protected patterns.
    
    Returns:
        None if safe
        Error message if file is protected
    """
    if not file_path:
        return None

    if PROTECTED_PATHS.search(file_path):
        return f"BLOCKED: Protected file access: {file_path}\n" \
               f"This file contains sensitive data and cannot be modified via this interface."

    return None


# ============================================================================
# Main Guard Logic
# ============================================================================


def run_command_guard(payload: Dict) -> Tuple[int, Optional[str]]:
    """
    Guard for pre-tool-use commands.
    
    Returns: (exit_code, error_message_or_none)
      0 = allowed
      1 = blocked (dangerous)
      2 = error
    """
    cmd = _get_command(payload)
    session_id = _get_session_id()

    # Check dangerous patterns
    error = _detect_dangerous_command(cmd, session_id)
    if error:
        return 1, error

    return 0, None


def run_file_guard(payload: Dict) -> Tuple[int, Optional[str]]:
    """
    Guard for file write/read operations.
    
    Returns: (exit_code, error_message_or_none)
      0 = allowed
      1 = blocked (protected)
      2 = error
    """
    file_path = _get_file_path(payload)

    # Check protected files
    error = _detect_protected_file_access(file_path)
    if error:
        return 1, error

    return 0, None


# ============================================================================
# CLI Interface
# ============================================================================


def main() -> int:
    """Main entry point for hook."""
    if len(sys.argv) < 2:
        print("Usage: pretool-guard.py <command|file> [payload.json]", file=sys.stderr)
        print("  command - check command before execution", file=sys.stderr)
        print("  file    - check file before read/write", file=sys.stderr)
        return 2

    mode = sys.argv[1].strip().lower()
    payload = _read_payload()

    if mode == "command":
        exit_code, error = run_command_guard(payload)
        if error:
            print(error, file=sys.stderr)
        return exit_code

    elif mode == "file":
        exit_code, error = run_file_guard(payload)
        if error:
            print(error, file=sys.stderr)
        return exit_code

    else:
        print(f"Unknown mode: {mode}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
