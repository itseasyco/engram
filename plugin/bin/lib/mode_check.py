#!/usr/bin/env python3
"""
Mode check helper for Python CLI scripts.

Usage:
    from lib.mode_check import guard_or_exit
    guard_or_exit("brain-resolve")
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Add plugin/lib to path
_lib_dir = str(Path(__file__).resolve().parent.parent.parent / "lib")
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from mode import check_mutation_allowed, get_config


def guard_or_exit(command_name: str, *, json_output: bool = False) -> str:
    """
    Check if the command is allowed. Exit with code 10 if blocked.

    Returns:
        "allowed" — command can proceed normally
        "redirected_to_inbox" — command should write to inbox instead of graph
    """
    allowed, reason = check_mutation_allowed(command_name)

    if not allowed:
        config = get_config()
        if json_output:
            payload = {
                "ok": False,
                "kind": command_name.replace("-", "_"),
                "error": "mode_blocked",
                "mode": config.mode,
                "reason": reason,
            }
            print(json.dumps(payload, indent=2))
        else:
            print(f"\033[0;31m[BLOCKED]\033[0m {reason}", file=sys.stderr)
            print(
                f"\033[0;31m[BLOCKED]\033[0m Run 'openclaw-lacp-connect status' for connection info.",
                file=sys.stderr,
            )
        sys.exit(10)

    return reason if reason else "allowed"
