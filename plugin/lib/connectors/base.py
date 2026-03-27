"""Base connector class and VaultNote dataclass."""

from __future__ import annotations

import hashlib
import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class TrustLevel(str, Enum):
    VERIFIED = "verified"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ConnectorMode(str, Enum):
    PULL = "pull"
    PUSH = "push"
    BOTH = "both"


@dataclass
class ConnectorStatus:
    """Health status returned by health_check()."""

    healthy: bool
    connector_id: str
    connector_type: str
    last_pull_time: Optional[str] = None
    last_error: Optional[str] = None
    error_count: int = 0
    notes_ingested: int = 0
    uptime_seconds: float = 0.0
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = {
            "healthy": self.healthy,
            "connector_id": self.connector_id,
            "connector_type": self.connector_type,
            "last_pull_time": self.last_pull_time,
            "last_error": self.last_error,
            "error_count": self.error_count,
            "notes_ingested": self.notes_ingested,
            "uptime_seconds": self.uptime_seconds,
        }
        d.update(self.extra)
        return d


@dataclass
class VaultNote:
    """
    Universal output format for connectors.

    Every connector transforms external data into one or more VaultNote
    objects. The registry writes these to the appropriate inbox queue folder
    as Markdown files with YAML frontmatter.
    """

    title: str
    body: str
    source_connector: str       # connector id that produced this note
    source_type: str            # connector type (github, slack, etc.)
    source_id: str              # unique id from the source (PR number, message ts, etc.)
    trust_level: str = "medium"
    landing_zone: str = "queue-human"  # subfolder under inbox/

    # Frontmatter fields
    category: str = ""
    tags: list[str] = field(default_factory=list)
    author: str = ""
    source_url: str = ""
    created: str = ""
    status: str = "active"
    extra_frontmatter: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.created:
            self.created = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        # Low trust always gets unverified status
        if self.trust_level == TrustLevel.LOW.value:
            self.status = "unverified"

    @property
    def slug(self) -> str:
        """Generate a filesystem-safe slug for the note filename."""
        raw = f"{self.source_connector}_{self.source_id}"
        h = hashlib.md5(raw.encode()).hexdigest()[:8]
        safe_title = "".join(
            c if c.isalnum() or c in "-_ " else "" for c in self.title
        )[:60].strip().replace(" ", "-").lower()
        return f"{safe_title}-{h}" if safe_title else h

    def to_markdown(self) -> str:
        """Render the note as Markdown with YAML frontmatter."""
        fm: dict[str, Any] = {
            "title": self.title,
            "created": self.created,
            "updated": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "author": self.author or self.source_connector,
            "source": self.source_type,
            "source_connector": self.source_connector,
            "source_id": self.source_id,
            "trust_level": self.trust_level,
            "status": self.status,
        }
        if self.category:
            fm["category"] = self.category
        if self.tags:
            fm["tags"] = self.tags
        if self.source_url:
            fm["source_url"] = self.source_url
        fm.update(self.extra_frontmatter)

        # Render YAML frontmatter manually (avoid PyYAML dependency)
        lines = ["---"]
        for k, v in fm.items():
            if isinstance(v, list):
                lines.append(f"{k}:")
                for item in v:
                    lines.append(f"  - {item}")
            elif isinstance(v, bool):
                lines.append(f"{k}: {'true' if v else 'false'}")
            elif isinstance(v, (int, float)):
                lines.append(f"{k}: {v}")
            else:
                lines.append(f"{k}: {v}")
        lines.append("---")
        lines.append("")
        lines.append(f"# {self.title}")
        lines.append("")
        lines.append(self.body)
        lines.append("")
        lines.append("---")
        lines.append(f"Ingested by connector: {self.source_connector}")
        lines.append("")
        return "\n".join(lines)

    def write_to_vault(self, vault_path: str | Path) -> Path:
        """Write this note to the appropriate inbox queue folder."""
        try:
            from .vault_paths import resolve
            queue_dir = resolve("inbox") / self.landing_zone
        except (ImportError, KeyError):
            vault = Path(vault_path)
            queue_dir = vault / "inbox" / self.landing_zone
        queue_dir.mkdir(parents=True, exist_ok=True)
        out = queue_dir / f"{self.slug}.md"
        # Handle collision
        if out.exists():
            ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
            out = queue_dir / f"{self.slug}-{ts}.md"
        out.write_text(self.to_markdown(), encoding="utf-8")
        return out


@dataclass
class RawData:
    """
    Raw data from an external source, before transformation.

    Connectors produce RawData from pull() or receive(), then
    transform() converts it to a VaultNote.
    """

    source_id: str
    payload: dict[str, Any]
    timestamp: str = ""
    sender: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


class Connector(ABC):
    """
    Abstract base class for all connectors.

    Subclasses must implement authenticate(), transform(), and health_check().
    Pull-mode connectors must implement pull().
    Push-mode connectors must implement receive().
    Both-mode connectors must implement both.
    """

    id: str = ""
    type: str = ""
    trust_level: str = TrustLevel.MEDIUM.value
    mode: str = ConnectorMode.PULL.value
    landing_zone: str = "queue-human"

    def __init__(self, config: dict[str, Any]):
        """
        Initialize from a connector config entry (from connectors.json).

        Args:
            config: The full connector config dict including id, type,
                    trust_level, mode, landing_zone, and connector-specific
                    config under the "config" key.
        """
        self.id = config.get("id", self.id)
        self.type = config.get("type", self.type)
        self.trust_level = config.get("trust_level", self.trust_level)
        self.mode = config.get("mode", self.mode)
        self.landing_zone = config.get("landing_zone", self.landing_zone)
        self.connector_config = config.get("config", {})

        # Runtime state
        self._started_at: Optional[str] = None
        self._error_count: int = 0
        self._last_error: Optional[str] = None
        self._last_pull_time: Optional[str] = None
        self._notes_ingested: int = 0

        # Resolve env var references in config values
        self.connector_config = self._resolve_env_vars(self.connector_config)

    @staticmethod
    def _resolve_env_vars(config: dict[str, Any]) -> dict[str, Any]:
        """Replace ${ENV_VAR} references with actual environment values."""
        resolved = {}
        for k, v in config.items():
            if isinstance(v, str) and v.startswith("${") and v.endswith("}"):
                env_key = v[2:-1]
                resolved[k] = os.environ.get(env_key, "")
            elif isinstance(v, dict):
                resolved[k] = Connector._resolve_env_vars(v)
            elif isinstance(v, list):
                resolved[k] = [
                    os.environ.get(item[2:-1], "")
                    if isinstance(item, str) and item.startswith("${") and item.endswith("}")
                    else item
                    for item in v
                ]
            else:
                resolved[k] = v
        return resolved

    @abstractmethod
    def authenticate(self) -> bool:
        """
        Establish connection to the external source.

        Returns True if authentication succeeds, False otherwise.
        Called once during connector startup.
        """
        ...

    def pull(self) -> list[RawData]:
        """
        Fetch new data from source (for pull/both mode connectors).

        Returns a list of RawData objects representing new items since
        the last pull. Override in pull-mode connectors.
        """
        raise NotImplementedError(
            f"Connector {self.id} is mode={self.mode} but pull() not implemented"
        )

    def receive(self, payload: dict[str, Any]) -> RawData:
        """
        Handle incoming webhook/push payload (for push/both mode connectors).

        Returns a single RawData object. Override in push-mode connectors.
        """
        raise NotImplementedError(
            f"Connector {self.id} is mode={self.mode} but receive() not implemented"
        )

    @abstractmethod
    def transform(self, raw_data: RawData) -> VaultNote:
        """
        Convert raw external data into a VaultNote.

        This is where connector-specific formatting happens. Every
        connector must implement this.
        """
        ...

    @abstractmethod
    def health_check(self) -> ConnectorStatus:
        """
        Return connector status including health, last pull time, error count.

        Every connector must implement this.
        """
        ...

    def record_pull(self):
        """Record a successful pull timestamp."""
        self._last_pull_time = datetime.now(timezone.utc).isoformat()

    def record_error(self, error: str):
        """Record an error."""
        self._error_count += 1
        self._last_error = error

    def record_ingestion(self, count: int = 1):
        """Record notes ingested."""
        self._notes_ingested += count

    def base_status(self, healthy: bool) -> ConnectorStatus:
        """Build a ConnectorStatus with common fields pre-filled."""
        uptime = 0.0
        if self._started_at:
            started = datetime.fromisoformat(self._started_at)
            uptime = (datetime.now(timezone.utc) - started).total_seconds()
        return ConnectorStatus(
            healthy=healthy,
            connector_id=self.id,
            connector_type=self.type,
            last_pull_time=self._last_pull_time,
            last_error=self._last_error,
            error_count=self._error_count,
            notes_ingested=self._notes_ingested,
            uptime_seconds=uptime,
        )

    def start(self):
        """Mark connector as started."""
        self._started_at = datetime.now(timezone.utc).isoformat()
