"""
Cron-fetch connector (Tier 1 -- Native).

Polls configured URLs on a schedule and transforms responses into vault
notes. Useful for RSS feeds, status pages, API endpoints.

Config keys:
  - urls: list of URL configs, each with:
      - url: the URL to fetch
      - headers: optional dict of HTTP headers
      - method: GET (default) or POST
      - body: optional request body (for POST)
      - label: human-readable name for this source
  - poll_interval_minutes: how often to poll (default: 30)
  - transform: optional path to custom transform script
  - response_format: "json" | "text" | "auto" (default: auto)
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from .base import Connector, ConnectorStatus, RawData, VaultNote


class CronFetchConnector(Connector):
    """Poll URLs on a schedule and transform responses into vault notes."""

    type = "cron_fetch"

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self._url_configs: list[dict[str, Any]] = self.connector_config.get("urls", [])
        self._poll_interval: int = self.connector_config.get("poll_interval_minutes", 30)
        self._response_format: str = self.connector_config.get("response_format", "auto")
        self._transform_path: str = self.connector_config.get("transform", "")
        self._custom_transform: Optional[Callable] = None
        self._last_hashes: dict[str, str] = {}  # url -> content hash

    def authenticate(self) -> bool:
        """Verify at least one URL is configured."""
        if self._transform_path:
            self._custom_transform = self._load_transform(self._transform_path)
        return len(self._url_configs) > 0

    def _load_transform(self, script_path: str) -> Optional[Callable]:
        """Load a custom transform function from a Python script."""
        p = Path(script_path)
        if not p.is_absolute():
            plugin_dir = Path(
                os.environ.get(
                    "OPENCLAW_PLUGIN_DIR",
                    Path.home() / ".openclaw" / "extensions" / "openclaw-lacp-fusion",
                )
            )
            p = plugin_dir / script_path
        if not p.exists():
            return None
        try:
            spec = importlib.util.spec_from_file_location("cron_transform", str(p))
            if spec is None or spec.loader is None:
                return None
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            fn = getattr(mod, "transform", None)
            return fn if callable(fn) else None
        except Exception:
            return None

    def pull(self) -> list[RawData]:
        """Fetch all configured URLs and return new/changed responses."""
        results: list[RawData] = []

        for url_cfg in self._url_configs:
            if isinstance(url_cfg, str):
                url_cfg = {"url": url_cfg}

            url = url_cfg.get("url", "")
            if not url:
                continue

            label = url_cfg.get("label", url)
            headers = url_cfg.get("headers", {})
            method = url_cfg.get("method", "GET").upper()
            body = url_cfg.get("body")

            try:
                content = self._fetch(url, headers, method, body)
            except Exception as exc:
                self.record_error(f"Fetch failed for {url}: {exc}")
                continue

            # Check if content changed since last fetch
            content_hash = hashlib.sha256(content.encode()).hexdigest()
            if url in self._last_hashes and self._last_hashes[url] == content_hash:
                continue  # unchanged
            self._last_hashes[url] = content_hash

            # Parse response
            payload: dict[str, Any] = {
                "url": url,
                "label": label,
                "content_type": self._response_format,
            }

            if self._response_format == "json" or (
                self._response_format == "auto" and self._looks_like_json(content)
            ):
                try:
                    payload["data"] = json.loads(content)
                    payload["content_type"] = "json"
                except json.JSONDecodeError:
                    payload["data"] = content
                    payload["content_type"] = "text"
            else:
                payload["data"] = content
                payload["content_type"] = "text"

            source_id = hashlib.md5(f"{url}:{content_hash[:16]}".encode()).hexdigest()[:12]

            results.append(RawData(
                source_id=source_id,
                payload=payload,
                sender=f"cron-fetch:{url}",
            ))

        return results

    def _fetch(
        self, url: str, headers: dict[str, str], method: str, body: Optional[str]
    ) -> str:
        """Fetch a URL using urllib (no external dependencies)."""
        req = urllib.request.Request(url, method=method)
        for k, v in headers.items():
            req.add_header(k, v)
        req.add_header("User-Agent", "openclaw-lacp-connector/1.0")

        data = body.encode() if body else None
        with urllib.request.urlopen(req, data=data, timeout=30) as resp:
            return resp.read().decode("utf-8", errors="replace")

    @staticmethod
    def _looks_like_json(content: str) -> bool:
        stripped = content.strip()
        return (stripped.startswith("{") and stripped.endswith("}")) or (
            stripped.startswith("[") and stripped.endswith("]")
        )

    def transform(self, raw_data: RawData) -> VaultNote:
        """Transform fetched content into a VaultNote."""
        payload = raw_data.payload

        if self._custom_transform is not None:
            try:
                result = self._custom_transform(payload)
                return VaultNote(
                    title=result.get("title", payload.get("label", "Fetched")),
                    body=result.get("body", str(payload.get("data", ""))),
                    source_connector=self.id,
                    source_type=self.type,
                    source_id=raw_data.source_id,
                    trust_level=self.trust_level,
                    landing_zone=self.landing_zone,
                    tags=result.get("tags", ["cron-fetch"]),
                    category=result.get("category", "fetch"),
                    source_url=payload.get("url", ""),
                )
            except Exception as exc:
                self.record_error(f"Custom transform failed: {exc}")

        # Default transform
        label = payload.get("label", payload.get("url", "Unknown"))
        data = payload.get("data", "")
        content_type = payload.get("content_type", "text")

        if content_type == "json":
            body = f"## Source\n\n[{label}]({payload.get('url', '')})\n\n## Data\n\n```json\n{json.dumps(data, indent=2)}\n```"
        else:
            body = f"## Source\n\n[{label}]({payload.get('url', '')})\n\n## Content\n\n{data}"

        return VaultNote(
            title=f"Fetch: {label}",
            body=body,
            source_connector=self.id,
            source_type=self.type,
            source_id=raw_data.source_id,
            trust_level=self.trust_level,
            landing_zone=self.landing_zone,
            tags=["cron-fetch"],
            category="fetch",
            source_url=payload.get("url", ""),
        )

    def health_check(self) -> ConnectorStatus:
        status = self.base_status(healthy=True)
        status.extra["url_count"] = len(self._url_configs)
        status.extra["poll_interval_minutes"] = self._poll_interval
        status.extra["tracked_urls"] = len(self._last_hashes)
        return status
