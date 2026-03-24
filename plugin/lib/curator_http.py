#!/usr/bin/env python3
"""
Curator HTTP surface for engram.

Minimal HTTP server with 3 endpoints, all behind token authentication:
  POST /validate — Validate an invite token, return vault config
  POST /health   — Return curator status, last cycle time, graph stats
  POST /notify   — Fast-path notification for high-priority inbox items

Usage:
  python3 -m lib.curator_http --port 9100 --token <admin-token>

Or programmatically:
  from .curator_http import create_server, run_server
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, UTC
from functools import partial
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Any, Optional

# Ensure lib is importable
_lib_dir = str(Path(__file__).resolve().parent)
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from heartbeat import check_heartbeat, HEARTBEAT_FILENAME
from invites import validate_token, redeem_token

logger = logging.getLogger(__name__)

DEFAULT_PORT = 9100


class CuratorHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the curator surface."""

    # Set by the server factory
    admin_token: str = ""
    vault_path: str = ""
    vault_name: str = "Company Brain"
    on_notify: Optional[Any] = None  # callback(file, priority)

    def log_message(self, format: str, *args: Any) -> None:
        logger.info(format % args)

    def _send_json(self, status_code: int, data: dict) -> None:
        body = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}

    def _check_auth(self) -> bool:
        auth = self.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            self._send_json(401, {"error": "missing_auth", "message": "Authorization header required"})
            return False
        token = auth[len("Bearer "):]
        if token != self.admin_token:
            self._send_json(403, {"error": "invalid_token", "message": "Invalid authentication token"})
            return False
        return True

    def do_POST(self) -> None:
        if not self._check_auth():
            return

        if self.path == "/validate":
            self._handle_validate()
        elif self.path == "/health":
            self._handle_health()
        elif self.path == "/notify":
            self._handle_notify()
        else:
            self._send_json(404, {"error": "not_found", "message": f"Unknown endpoint: {self.path}"})

    def _handle_validate(self) -> None:
        body = self._read_body()
        invite_token = body.get("token", "")
        if not invite_token:
            self._send_json(400, {"error": "missing_token", "message": "token field required"})
            return

        valid, invite, reason = validate_token(invite_token)
        if not valid:
            self._send_json(200, {"valid": False, "reason": reason})
            return

        # Return vault config for the joining node
        self._send_json(200, {
            "valid": True,
            "vault_name": self.vault_name,
            "role": invite.role,
            "ob_sync_config": {
                "vault_name": self.vault_name,
                "vault_path": "~/.openclaw/vault",
            },
        })

    def _handle_health(self) -> None:
        hb = check_heartbeat(self.vault_path)
        vault = Path(self.vault_path) if self.vault_path else None

        note_count = 0
        inbox_pending = 0
        if vault and vault.exists():
            note_count = sum(1 for _ in vault.rglob("*.md") if "/.obsidian/" not in _.as_posix())
            inbox_dir = vault / "05_Inbox"
            if inbox_dir.exists():
                inbox_pending = sum(1 for _ in inbox_dir.rglob("*.md"))

        self._send_json(200, {
            "status": hb.get("status", "unknown"),
            "last_cycle": hb.get("last_seen"),
            "notes": note_count,
            "inbox_pending": inbox_pending,
            "message": hb.get("message", ""),
        })

    def _handle_notify(self) -> None:
        body = self._read_body()
        file_path = body.get("file", "")
        priority = body.get("priority", "normal")

        if not file_path:
            self._send_json(400, {"error": "missing_file", "message": "file field required"})
            return

        # Call the notify callback if registered
        if self.on_notify:
            try:
                self.on_notify(file_path, priority)
            except Exception as e:
                logger.error("Notify callback failed: %s", e)

        self._send_json(200, {
            "accepted": True,
            "file": file_path,
            "priority": priority,
        })


def create_server(
    port: int = DEFAULT_PORT,
    admin_token: str = "",
    vault_path: str = "",
    vault_name: str = "Company Brain",
    on_notify: Optional[Any] = None,
) -> HTTPServer:
    """Create and configure the curator HTTP server."""
    CuratorHandler.admin_token = admin_token
    CuratorHandler.vault_path = vault_path
    CuratorHandler.vault_name = vault_name
    CuratorHandler.on_notify = on_notify

    server = HTTPServer(("0.0.0.0", port), CuratorHandler)
    return server


def run_server(
    port: int = DEFAULT_PORT,
    admin_token: str = "",
    vault_path: str = "",
    vault_name: str = "Company Brain",
) -> None:
    """Run the curator HTTP server (blocking)."""
    if not admin_token:
        admin_token = os.environ.get("LACP_CURATOR_TOKEN", "")
    if not admin_token:
        print("ERROR: --token or LACP_CURATOR_TOKEN required", file=sys.stderr)
        sys.exit(1)

    server = create_server(
        port=port,
        admin_token=admin_token,
        vault_path=vault_path,
        vault_name=vault_name,
    )
    logger.info("Curator HTTP surface listening on port %d", port)
    print(f"Curator HTTP surface listening on port {port}", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
        print("\nCurator HTTP surface stopped.", file=sys.stderr)


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO)

    p = argparse.ArgumentParser(description="Curator HTTP surface")
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--token", default=os.environ.get("LACP_CURATOR_TOKEN", ""))
    p.add_argument("--vault", default=os.environ.get("LACP_OBSIDIAN_VAULT", ""))
    p.add_argument("--vault-name", default="Company Brain")
    args = p.parse_args()

    run_server(
        port=args.port,
        admin_token=args.token,
        vault_path=args.vault,
        vault_name=args.vault_name,
    )
