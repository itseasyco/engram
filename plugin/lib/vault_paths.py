#!/usr/bin/env python3
"""
Vault path resolver for Engram.

All vault paths are resolved through this module. Nothing is hardcoded.
The curator can update vault-schema.json to reorganize the vault structure,
and every component follows automatically.

Usage:
    from vault_paths import vault, resolve

    # Get a specific path
    memory_dir = vault.memory          # -> Path("/Volumes/Cortex/memory")
    inbox = vault.inbox_agent          # -> Path("/Volumes/Cortex/inbox/queue-agent")

    # Or resolve by key
    path = resolve("memory")           # -> Path("/Volumes/Cortex/memory")
    path = resolve("inbox_session")    # -> Path("/Volumes/Cortex/inbox/queue-session")
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional


# Default paths (used when vault-schema.json doesn't exist or is missing a key)
_DEFAULTS = {
    "index": "index.md",
    "home": "home",
    "memory": "memory",
    "projects": "projects",
    "concepts": "concepts",
    "people": "people",
    "people_team": "people/team",
    "people_personal": "people/personal",
    "people_investors": "people/investors",
    "people_clients": "people/clients",
    "systems": "systems",
    "engineering": "engineering",
    "knowledge": "knowledge",
    "inbox": "inbox",
    "inbox_agent": "inbox/queue-agent",
    "inbox_cicd": "inbox/queue-cicd",
    "inbox_human": "inbox/queue-human",
    "inbox_external": "inbox/queue-external",
    "inbox_session": "inbox/queue-session",
    "inbox_stale": "inbox/review-stale",
    "planning": "planning",
    "research": "research",
    "strategy": "strategy",
    "sessions": "sessions",
    "reference": "reference",
    "health": "health",
    "changelog": "changelog",
    "changelog_branches": "changelog/branches",
    "changelog_merged": "changelog/merged",
    "changelog_releases": "changelog/releases",
    "changelog_deploys": "changelog/deploys",
    "changelog_environments": "changelog/environments",
    "templates": "templates",
    "archive": "archive",
    # v4.0: Entity graph + intelligence
    "organizations": "organizations",
    "strategy_goals": "strategy/goals",
    "strategy_decisions": "strategy/decisions",
    "strategy_synthesis": "strategy/synthesis",
    "meetings_briefings": "meetings/briefings",
    "meetings_team": "meetings/team",
    "meetings_investors": "meetings/investors",
    "meetings_clients": "meetings/clients",
    "metadata": "_metadata",
}

# Cache
_schema_cache: Optional[dict] = None
_schema_mtime: float = 0


def _vault_root() -> Path:
    """Resolve the vault root path via engram_config."""
    from engram_config import load
    return Path(load().vault_path)


def _schema_path() -> Path:
    """Return path to vault-schema.json. Prefer ENGRAM_HOME, fall back to legacy."""
    engram_home = os.environ.get("ENGRAM_HOME", os.path.expanduser("~/.engram"))
    new_path = Path(engram_home) / "extensions" / "engram" / "config" / "vault-schema.json"
    if new_path.exists():
        return new_path
    legacy = Path(
        os.environ.get(
            "OPENCLAW_PLUGIN_DIR",
            os.path.expanduser("~/.openclaw/extensions/engram"),
        )
    ) / "config" / "vault-schema.json"
    return legacy


def _load_schema() -> dict:
    """Load vault-schema.json with mtime caching."""
    global _schema_cache, _schema_mtime

    path = _schema_path()
    if not path.exists():
        return _DEFAULTS.copy()

    try:
        mtime = path.stat().st_mtime
        if _schema_cache is not None and mtime == _schema_mtime:
            return _schema_cache

        data = json.loads(path.read_text(encoding="utf-8"))
        paths = data.get("paths", {})

        # Merge with defaults (schema overrides defaults)
        merged = _DEFAULTS.copy()
        merged.update(paths)

        _schema_cache = merged
        _schema_mtime = mtime
        return merged
    except (json.JSONDecodeError, OSError):
        return _DEFAULTS.copy()


def resolve(key: str) -> Path:
    """Resolve a vault path by key. Returns absolute path."""
    schema = _load_schema()
    relative = schema.get(key)
    if relative is None:
        raise KeyError(f"Unknown vault path key: {key!r}. Available: {sorted(schema.keys())}")
    return _vault_root() / relative


def resolve_str(key: str) -> str:
    """Resolve a vault path by key as string."""
    return str(resolve(key))


def root() -> Path:
    """Return the vault root path."""
    return _vault_root()


def all_paths() -> dict[str, str]:
    """Return all configured paths as key -> absolute path strings."""
    schema = _load_schema()
    vault = _vault_root()
    return {k: str(vault / v) for k, v in schema.items()}


class _VaultAccessor:
    """Attribute-style access to vault paths.

    Usage:
        vault.memory          -> Path("/Volumes/Cortex/memory")
        vault.inbox_agent     -> Path("/Volumes/Cortex/inbox/queue-agent")
        vault.root            -> Path("/Volumes/Cortex")
    """

    def __getattr__(self, key: str) -> Path:
        if key == "root":
            return _vault_root()
        try:
            return resolve(key)
        except KeyError:
            raise AttributeError(f"No vault path for {key!r}")

    def __repr__(self) -> str:
        return f"VaultPaths(root={_vault_root()})"


# Singleton accessor
vault = _VaultAccessor()
