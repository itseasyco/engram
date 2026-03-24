"""
Connector registry: loads, manages lifecycle, and discovers connectors.

Loads connector configs from config/connectors.json, instantiates the
correct connector class per type, and provides start/stop/status/pull
operations across all active connectors.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

from .base import Connector, ConnectorStatus, RawData, VaultNote


# Built-in connector type -> module mapping
BUILTIN_CONNECTORS: dict[str, str] = {
    "filesystem": "plugin.lib.connectors.filesystem",
    "webhook": "plugin.lib.connectors.webhook",
    "cron_fetch": "plugin.lib.connectors.cron_fetch",
    "cron-fetch": "plugin.lib.connectors.cron_fetch",
    "github": "plugin.lib.connectors.github",
    "slack": "plugin.lib.connectors.slack",
    "email": "plugin.lib.connectors.email",
}

# Connector class name convention: <Type>Connector (e.g. FilesystemConnector)
# Each module must expose a class matching this pattern.

PLUGIN_DIR = Path(
    os.environ.get(
        "OPENCLAW_PLUGIN_DIR",
        Path.home() / ".openclaw" / "extensions" / "engram",
    )
)
CONFIG_DIR = PLUGIN_DIR / "config"
CONNECTORS_CONFIG = CONFIG_DIR / "connectors.json"

# Community connectors live under the openclaw extensions directory
EXTENSIONS_DIR = Path(
    os.environ.get("OPENCLAW_HOME", Path.home() / ".openclaw")
) / "extensions"


class ConnectorLoadError(Exception):
    """Raised when a connector cannot be loaded."""
    pass


class ConnectorRegistry:
    """
    Manages all connector instances.

    Loads from config/connectors.json, discovers community connectors,
    and provides lifecycle operations.
    """

    def __init__(self, config_path: Optional[str | Path] = None):
        self.config_path = Path(config_path) if config_path else CONNECTORS_CONFIG
        self.connectors: dict[str, Connector] = {}
        self._config: dict[str, Any] = {}

    def load_config(self) -> dict[str, Any]:
        """Load connectors.json and return the parsed config."""
        if not self.config_path.exists():
            self._config = {"connectors": []}
            return self._config
        try:
            self._config = json.loads(self.config_path.read_text())
        except (json.JSONDecodeError, OSError) as exc:
            raise ConnectorLoadError(f"Failed to read {self.config_path}: {exc}")
        return self._config

    def save_config(self):
        """Write current config back to disk."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(
            json.dumps(self._config, indent=2) + "\n"
        )

    def _resolve_connector_class(self, connector_type: str) -> type:
        """
        Find the Connector subclass for the given type.

        Checks built-in connectors first, then community connectors
        installed under extensions/.
        """
        # Built-in
        module_path = BUILTIN_CONNECTORS.get(connector_type)
        if module_path:
            try:
                mod = importlib.import_module(module_path)
            except ImportError as exc:
                raise ConnectorLoadError(
                    f"Failed to import built-in connector module {module_path}: {exc}"
                )
            class_name = (
                connector_type.replace("-", "_").replace("_", " ").title().replace(" ", "")
                + "Connector"
            )
            cls = getattr(mod, class_name, None)
            if cls is None:
                raise ConnectorLoadError(
                    f"Module {module_path} does not export class {class_name}"
                )
            return cls

        # Community: look for openclaw-lacp-connector-<type>
        community_dir = EXTENSIONS_DIR / f"openclaw-lacp-connector-{connector_type}"
        if community_dir.is_dir():
            return self._load_community_connector(community_dir, connector_type)

        raise ConnectorLoadError(
            f"Unknown connector type: {connector_type}. "
            f"Install with: openclaw plugins install openclaw-lacp-connector-{connector_type}"
        )

    def _load_community_connector(
        self, connector_dir: Path, connector_type: str
    ) -> type:
        """Load a community connector from its directory."""
        # Check for connector.json manifest
        manifest_path = connector_dir / "connector.json"
        if not manifest_path.exists():
            raise ConnectorLoadError(
                f"Community connector at {connector_dir} missing connector.json manifest"
            )

        try:
            manifest = json.loads(manifest_path.read_text())
        except (json.JSONDecodeError, OSError) as exc:
            raise ConnectorLoadError(f"Bad connector.json at {manifest_path}: {exc}")

        # Load the Python module
        index_py = connector_dir / "index.py"
        if not index_py.exists():
            raise ConnectorLoadError(
                f"Community connector at {connector_dir} missing index.py"
            )

        # Add to sys.path temporarily and import
        if str(connector_dir) not in sys.path:
            sys.path.insert(0, str(connector_dir))

        try:
            spec = importlib.util.spec_from_file_location(
                f"connector_{connector_type}", str(index_py)
            )
            if spec is None or spec.loader is None:
                raise ConnectorLoadError(f"Cannot create module spec from {index_py}")
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
        except Exception as exc:
            raise ConnectorLoadError(f"Failed to load {index_py}: {exc}")

        # Find the Connector subclass
        class_name = (
            connector_type.replace("-", "_").replace("_", " ").title().replace(" ", "")
            + "Connector"
        )
        cls = getattr(mod, class_name, None)
        if cls is None:
            # Fallback: find any Connector subclass
            for attr_name in dir(mod):
                attr = getattr(mod, attr_name)
                if (
                    isinstance(attr, type)
                    and issubclass(attr, Connector)
                    and attr is not Connector
                ):
                    cls = attr
                    break
        if cls is None:
            raise ConnectorLoadError(
                f"No Connector subclass found in {index_py}"
            )
        return cls

    def load_all(self) -> list[str]:
        """
        Load config and instantiate all connectors.

        Returns list of successfully loaded connector IDs.
        """
        self.load_config()
        loaded: list[str] = []
        errors: list[str] = []

        for entry in self._config.get("connectors", []):
            conn_id = entry.get("id", "unknown")
            conn_type = entry.get("type", "unknown")
            enabled = entry.get("enabled", True)

            if not enabled:
                continue

            try:
                cls = self._resolve_connector_class(conn_type)
                instance = cls(entry)
                self.connectors[conn_id] = instance
                loaded.append(conn_id)
            except ConnectorLoadError as exc:
                errors.append(f"{conn_id}: {exc}")
            except Exception as exc:
                errors.append(f"{conn_id}: unexpected error: {exc}")

        if errors:
            for err in errors:
                print(f"[connector-registry] WARN: {err}", file=sys.stderr)

        return loaded

    def start_all(self) -> dict[str, bool]:
        """Authenticate and start all loaded connectors. Returns {id: success}."""
        results: dict[str, bool] = {}
        for conn_id, conn in self.connectors.items():
            try:
                ok = conn.authenticate()
                if ok:
                    conn.start()
                results[conn_id] = ok
            except Exception as exc:
                conn.record_error(str(exc))
                results[conn_id] = False
        return results

    def stop_all(self):
        """Stop all connectors (clear registry)."""
        self.connectors.clear()

    def get(self, connector_id: str) -> Optional[Connector]:
        """Get a connector by ID."""
        return self.connectors.get(connector_id)

    def pull_all(self, vault_path: str | Path) -> list[Path]:
        """
        Run pull() on all pull/both-mode connectors, transform results,
        and write to vault.

        Returns list of written note paths.
        """
        written: list[Path] = []
        for conn_id, conn in self.connectors.items():
            if conn.mode not in ("pull", "both"):
                continue
            try:
                raw_items = conn.pull()
                conn.record_pull()
                for raw in raw_items:
                    note = conn.transform(raw)
                    path = note.write_to_vault(vault_path)
                    written.append(path)
                    conn.record_ingestion()
            except Exception as exc:
                conn.record_error(str(exc))
        return written

    def receive(
        self, connector_id: str, payload: dict[str, Any], vault_path: str | Path
    ) -> Optional[Path]:
        """
        Route an incoming webhook payload to the specified connector.

        Returns the written note path, or None if the connector is not found.
        """
        conn = self.connectors.get(connector_id)
        if conn is None:
            return None
        if conn.mode not in ("push", "both"):
            return None
        try:
            raw = conn.receive(payload)
            note = conn.transform(raw)
            path = note.write_to_vault(vault_path)
            conn.record_ingestion()
            return path
        except Exception as exc:
            conn.record_error(str(exc))
            return None

    def status_all(self) -> list[dict[str, Any]]:
        """Get health status for all connectors."""
        statuses: list[dict[str, Any]] = []
        for conn_id, conn in self.connectors.items():
            try:
                s = conn.health_check()
                statuses.append(s.to_dict())
            except Exception as exc:
                statuses.append({
                    "healthy": False,
                    "connector_id": conn_id,
                    "error": str(exc),
                })
        return statuses

    def add_connector(self, entry: dict[str, Any]) -> str:
        """Add a connector entry to the config (does not start it)."""
        conn_id = entry.get("id")
        if not conn_id:
            raise ValueError("Connector entry must have an 'id' field")
        # Check for duplicate
        for existing in self._config.get("connectors", []):
            if existing.get("id") == conn_id:
                raise ValueError(f"Connector with id '{conn_id}' already exists")
        self._config.setdefault("connectors", []).append(entry)
        self.save_config()
        return conn_id

    def remove_connector(self, connector_id: str) -> bool:
        """Remove a connector from config and stop it."""
        before = len(self._config.get("connectors", []))
        self._config["connectors"] = [
            c for c in self._config.get("connectors", [])
            if c.get("id") != connector_id
        ]
        removed = len(self._config.get("connectors", [])) < before
        if removed:
            self.save_config()
            self.connectors.pop(connector_id, None)
        return removed

    def list_available_types(self) -> list[dict[str, str]]:
        """List all available connector types (built-in + discovered community)."""
        types: list[dict[str, str]] = []

        # Built-in
        seen = set()
        for type_name in BUILTIN_CONNECTORS:
            canonical = type_name.replace("-", "_")
            if canonical not in seen:
                seen.add(canonical)
                tier = "native" if canonical in ("filesystem", "webhook", "cron_fetch") else "first-party"
                types.append({"type": type_name, "tier": tier})

        # Community
        if EXTENSIONS_DIR.is_dir():
            for d in EXTENSIONS_DIR.iterdir():
                if d.is_dir() and d.name.startswith("openclaw-lacp-connector-"):
                    ctype = d.name.replace("openclaw-lacp-connector-", "")
                    manifest = d / "connector.json"
                    if manifest.exists():
                        types.append({"type": ctype, "tier": "community"})

        return types
