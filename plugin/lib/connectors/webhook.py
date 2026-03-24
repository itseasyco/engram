"""
Webhook connector (Tier 1 -- Native).

Generic HTTP webhook receiver with HMAC signature verification,
IP allowlist, and custom transform scripts.

Config keys:
  - path: URL path this connector handles (e.g. "/hooks/sentry")
  - hmac_secret: shared secret for HMAC verification
  - hmac_header: HTTP header name containing the signature
  - hmac_algorithm: hash algorithm (default: sha256)
  - hmac_prefix: prefix to strip from signature (e.g. "sha256=")
  - ip_allowlist: list of allowed IP addresses/CIDRs
  - transform: path to a custom Python transform script (optional)
  - title_template: Python format string for note title (e.g. "{event}: {summary}")
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from .base import Connector, ConnectorStatus, RawData, VaultNote
from .trust import TrustVerifier, verify_hmac_signature


class WebhookConnector(Connector):
    """
    Receive webhook payloads via HTTP POST and transform into vault notes.

    The curator's HTTP surface routes incoming webhooks to this connector
    based on the configured path.
    """

    type = "webhook"

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self._path: str = self.connector_config.get("path", f"/hooks/{self.id}")
        self._hmac_secret: str = self.connector_config.get("hmac_secret", "")
        self._hmac_header: str = self.connector_config.get("hmac_header", "X-Hub-Signature-256")
        self._hmac_algorithm: str = self.connector_config.get("hmac_algorithm", "sha256")
        self._hmac_prefix: str = self.connector_config.get("hmac_prefix", "")
        self._transform_path: str = self.connector_config.get("transform", "")
        self._title_template: str = self.connector_config.get("title_template", "Webhook: {id}")
        self._custom_transform: Optional[Callable] = None
        self._trust_verifier = TrustVerifier.from_connector_config(self.connector_config)

    @property
    def path(self) -> str:
        return self._path

    def authenticate(self) -> bool:
        """Webhook connectors are always ready. Auth is per-request via HMAC."""
        # Load custom transform if configured
        if self._transform_path:
            self._custom_transform = self._load_transform_script(self._transform_path)
        return True

    def _load_transform_script(self, script_path: str) -> Optional[Callable]:
        """
        Load a custom transform function from a Python script.

        The script must define a function: transform(payload: dict) -> dict
        that returns a dict with keys: title, body, tags (optional), category (optional).
        """
        # Resolve relative to plugin config dir
        p = Path(script_path)
        if not p.is_absolute():
            plugin_dir = Path(
                os.environ.get(
                    "OPENCLAW_PLUGIN_DIR",
                    Path.home() / ".openclaw" / "extensions" / "engram",
                )
            )
            p = plugin_dir / script_path

        if not p.exists():
            return None

        try:
            spec = importlib.util.spec_from_file_location("custom_transform", str(p))
            if spec is None or spec.loader is None:
                return None
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            fn = getattr(mod, "transform", None)
            if callable(fn):
                return fn
        except Exception:
            pass
        return None

    def verify_request(
        self,
        body: bytes,
        headers: dict[str, str],
        source_ip: str = "",
    ) -> bool:
        """
        Verify an incoming webhook request.

        Checks HMAC signature (if configured) and IP allowlist.
        """
        # IP check
        if source_ip and not self._trust_verifier.check_ip(source_ip):
            self.record_error(f"IP rejected: {source_ip}")
            return False

        # HMAC check
        if self._hmac_secret:
            sig = headers.get(self._hmac_header, "")
            if not verify_hmac_signature(
                body,
                sig,
                self._hmac_secret,
                algorithm=self._hmac_algorithm,
                prefix=self._hmac_prefix,
            ):
                self.record_error("HMAC verification failed")
                return False

        return True

    def receive(self, payload: dict[str, Any]) -> RawData:
        """Accept an incoming webhook payload as RawData."""
        # Generate a source_id from the payload
        source_id = payload.get("id") or payload.get(
            "event_id"
        ) or datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")

        return RawData(
            source_id=str(source_id),
            payload=payload,
            sender=payload.get("sender", payload.get("source", "")),
        )

    def transform(self, raw_data: RawData) -> VaultNote:
        """Transform webhook payload into a VaultNote."""
        payload = raw_data.payload

        # Use custom transform if available
        if self._custom_transform is not None:
            try:
                result = self._custom_transform(payload)
                return VaultNote(
                    title=result.get("title", f"Webhook: {raw_data.source_id}"),
                    body=result.get("body", json.dumps(payload, indent=2)),
                    source_connector=self.id,
                    source_type=self.type,
                    source_id=raw_data.source_id,
                    trust_level=self.trust_level,
                    landing_zone=self.landing_zone,
                    tags=result.get("tags", ["webhook"]),
                    category=result.get("category", "webhook"),
                    source_url=result.get("source_url", ""),
                )
            except Exception as exc:
                self.record_error(f"Custom transform failed: {exc}")
                # Fall through to default transform

        # Default transform: dump payload as formatted JSON
        try:
            title = self._title_template.format(**payload, id=raw_data.source_id)
        except (KeyError, IndexError):
            title = f"Webhook: {raw_data.source_id}"

        body = f"## Payload\n\n```json\n{json.dumps(payload, indent=2)}\n```"

        return VaultNote(
            title=title,
            body=body,
            source_connector=self.id,
            source_type=self.type,
            source_id=raw_data.source_id,
            trust_level=self.trust_level,
            landing_zone=self.landing_zone,
            tags=["webhook"],
            category="webhook",
        )

    def health_check(self) -> ConnectorStatus:
        status = self.base_status(healthy=True)
        status.extra["path"] = self._path
        status.extra["hmac_configured"] = bool(self._hmac_secret)
        status.extra["custom_transform"] = self._transform_path or None
        return status
