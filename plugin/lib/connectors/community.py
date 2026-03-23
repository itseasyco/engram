"""
Community connector discovery and loading.

Community connectors are distributed as npm packages following the naming
convention `openclaw-lacp-connector-<type>`. They are installed via:

    openclaw plugins install openclaw-lacp-connector-<type>

This installs the package into OPENCLAW_HOME/extensions/. Each package must
contain:
  - connector.json  Manifest describing the connector (type, trust level, etc.)
  - index.py        Python module with a Connector subclass

Discovery scans the extensions directory for matching package names, validates
their manifest, and loads the Python class so the registry can instantiate it.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


COMMUNITY_PACKAGE_PREFIX = "openclaw-lacp-connector-"

# Required fields in connector.json
MANIFEST_REQUIRED_FIELDS = {"id", "type", "version", "trust_level", "mode", "required_config"}

# Valid values for manifest fields
VALID_TRUST_LEVELS = {"verified", "high", "medium", "low"}
VALID_MODES = {"pull", "push", "both"}


class CommunityConnectorError(Exception):
    """Raised when a community connector cannot be discovered or loaded."""
    pass


@dataclass
class ConnectorManifest:
    """
    Parsed and validated connector.json manifest.

    All community connectors must ship a connector.json at the package root.
    """

    id: str
    type: str
    version: str
    trust_level: str
    mode: str
    required_config: list[str]
    landing_zone: str = "queue-human"
    description: str = ""
    author: str = ""
    homepage: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConnectorManifest":
        """Parse and validate a manifest dict."""
        missing = MANIFEST_REQUIRED_FIELDS - set(data.keys())
        if missing:
            raise CommunityConnectorError(
                f"connector.json missing required fields: {sorted(missing)}"
            )

        trust_level = data["trust_level"]
        if trust_level not in VALID_TRUST_LEVELS:
            raise CommunityConnectorError(
                f"connector.json: invalid trust_level '{trust_level}'. "
                f"Must be one of: {sorted(VALID_TRUST_LEVELS)}"
            )

        mode = data["mode"]
        if mode not in VALID_MODES:
            raise CommunityConnectorError(
                f"connector.json: invalid mode '{mode}'. "
                f"Must be one of: {sorted(VALID_MODES)}"
            )

        required_config = data["required_config"]
        if not isinstance(required_config, list):
            raise CommunityConnectorError(
                "connector.json: required_config must be a list of strings"
            )

        known = {
            "id", "type", "version", "trust_level", "mode",
            "required_config", "landing_zone", "description", "author", "homepage",
        }
        extra = {k: v for k, v in data.items() if k not in known}

        return cls(
            id=data["id"],
            type=data["type"],
            version=data["version"],
            trust_level=trust_level,
            mode=mode,
            required_config=required_config,
            landing_zone=data.get("landing_zone", "queue-human"),
            description=data.get("description", ""),
            author=data.get("author", ""),
            homepage=data.get("homepage", ""),
            extra=extra,
        )

    @classmethod
    def from_file(cls, path: Path) -> "ConnectorManifest":
        """Load and validate a connector.json file from disk."""
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CommunityConnectorError(f"Failed to read {path}: {exc}")
        return cls.from_dict(data)

    def to_dict(self) -> dict[str, Any]:
        """Serialize manifest back to a dict."""
        d: dict[str, Any] = {
            "id": self.id,
            "type": self.type,
            "version": self.version,
            "trust_level": self.trust_level,
            "mode": self.mode,
            "required_config": self.required_config,
            "landing_zone": self.landing_zone,
        }
        if self.description:
            d["description"] = self.description
        if self.author:
            d["author"] = self.author
        if self.homepage:
            d["homepage"] = self.homepage
        d.update(self.extra)
        return d


@dataclass
class DiscoveredConnector:
    """
    A community connector found on disk, ready to be loaded.

    Holds the manifest metadata and the path to the package directory.
    The actual Python class is loaded lazily via load_class().
    """

    manifest: ConnectorManifest
    package_dir: Path
    _cls: Optional[type] = field(default=None, repr=False)

    @property
    def connector_type(self) -> str:
        return self.manifest.type

    @property
    def version(self) -> str:
        return self.manifest.version

    def load_class(self) -> type:
        """
        Import and return the Connector subclass from index.py.

        The class name is derived from the connector type following the
        convention <Type>Connector (e.g. NotionConnector, LinearConnector).
        Falls back to scanning the module for any Connector subclass if the
        expected name is not found.
        """
        if self._cls is not None:
            return self._cls

        index_py = self.package_dir / "index.py"
        if not index_py.exists():
            raise CommunityConnectorError(
                f"Community connector '{self.connector_type}' at "
                f"{self.package_dir} is missing index.py"
            )

        module_name = f"_community_connector_{self.connector_type.replace('-', '_')}"

        if str(self.package_dir) not in sys.path:
            sys.path.insert(0, str(self.package_dir))

        try:
            spec = importlib.util.spec_from_file_location(module_name, str(index_py))
            if spec is None or spec.loader is None:
                raise CommunityConnectorError(
                    f"Cannot create module spec from {index_py}"
                )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)  # type: ignore[union-attr]
        except CommunityConnectorError:
            raise
        except Exception as exc:
            raise CommunityConnectorError(
                f"Failed to load {index_py}: {exc}"
            ) from exc

        # Derive expected class name: "notion" -> "NotionConnector"
        class_name = (
            self.connector_type.replace("-", "_")
            .replace("_", " ")
            .title()
            .replace(" ", "")
            + "Connector"
        )

        # Deferred import to avoid circular dependency at module level
        from lib.connectors.base import Connector as _Connector  # type: ignore[import]

        cls = getattr(mod, class_name, None)
        if cls is None:
            # Fallback: find the first Connector subclass in the module
            for attr_name in dir(mod):
                attr = getattr(mod, attr_name)
                if (
                    isinstance(attr, type)
                    and issubclass(attr, _Connector)
                    and attr is not _Connector
                ):
                    cls = attr
                    break

        if cls is None:
            raise CommunityConnectorError(
                f"No Connector subclass found in {index_py}. "
                f"Expected class name: {class_name}"
            )

        self._cls = cls
        return cls


def discover(extensions_dir: Path) -> list[DiscoveredConnector]:
    """
    Scan extensions_dir for installed community connectors.

    Returns a list of DiscoveredConnector objects for every valid package
    directory that follows the `openclaw-lacp-connector-<type>` naming
    convention and contains a valid connector.json manifest.

    Invalid packages (missing or malformed manifest) are skipped with a
    warning printed to stderr rather than raising, so one broken connector
    does not prevent others from loading.
    """
    found: list[DiscoveredConnector] = []

    if not extensions_dir.is_dir():
        return found

    for entry in sorted(extensions_dir.iterdir()):
        if not entry.is_dir():
            continue
        if not entry.name.startswith(COMMUNITY_PACKAGE_PREFIX):
            continue

        manifest_path = entry / "connector.json"
        if not manifest_path.exists():
            import sys as _sys
            print(
                f"[community] WARNING: {entry.name} has no connector.json, skipping",
                file=_sys.stderr,
            )
            continue

        try:
            manifest = ConnectorManifest.from_file(manifest_path)
        except CommunityConnectorError as exc:
            import sys as _sys
            print(
                f"[community] WARNING: {entry.name} manifest error: {exc}, skipping",
                file=_sys.stderr,
            )
            continue

        found.append(DiscoveredConnector(manifest=manifest, package_dir=entry))

    return found


def discover_types(extensions_dir: Path) -> list[dict[str, str]]:
    """
    Return a list of type-info dicts for all discovered community connectors.

    Each dict has at least: type, tier, version, description.
    Used by the registry's list_available_types() to include community entries.
    """
    result: list[dict[str, str]] = []
    for dc in discover(extensions_dir):
        result.append(
            {
                "type": dc.connector_type,
                "tier": "community",
                "version": dc.version,
                "description": dc.manifest.description,
                "author": dc.manifest.author,
            }
        )
    return result


def load_connector_class(
    connector_type: str, extensions_dir: Path
) -> type:
    """
    Find and load the Connector subclass for a community connector type.

    Raises CommunityConnectorError if the type is not installed or fails to load.
    """
    package_dir = extensions_dir / f"{COMMUNITY_PACKAGE_PREFIX}{connector_type}"
    if not package_dir.is_dir():
        raise CommunityConnectorError(
            f"Community connector '{connector_type}' is not installed. "
            f"Install with: openclaw plugins install {COMMUNITY_PACKAGE_PREFIX}{connector_type}"
        )

    manifest_path = package_dir / "connector.json"
    try:
        manifest = ConnectorManifest.from_file(manifest_path)
    except CommunityConnectorError as exc:
        raise CommunityConnectorError(
            f"Cannot load '{connector_type}': {exc}"
        ) from exc

    dc = DiscoveredConnector(manifest=manifest, package_dir=package_dir)
    return dc.load_class()
