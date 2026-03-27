#!/usr/bin/env python3
"""
Vault path resolver for Engram.

All vault paths are resolved through this module. Nothing is hardcoded.
The curator can update vault-schema.json to reorganize the vault structure,
and every component follows automatically.

Usage:
    from vault_paths import vault, resolve

    # Get a specific path
    memory_dir = vault.memory          # -> Path("/Volumes/Cortex/01_memory")
    inbox = vault.inbox_agent          # -> Path("/Volumes/Cortex/05_Inbox/queue-agent")

    # Or resolve by key
    path = resolve("memory")           # -> Path("/Volumes/Cortex/01_memory")
    path = resolve("inbox_session")    # -> Path("/Volumes/Cortex/05_Inbox/queue-session")
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional


# Default paths (used when vault-schema.json doesn't exist or is missing a key)
_DEFAULTS = {
    "index": "00_Index.md",
    "projects": "01_Projects",
    "concepts": "02_Concepts",
    "people": "03_People",
    "systems": "04_Systems",
    "inbox": "05_Inbox",
    "inbox_agent": "05_Inbox/queue-agent",
    "inbox_cicd": "05_Inbox/queue-cicd",
    "inbox_human": "05_Inbox/queue-human",
    "inbox_external": "05_Inbox/queue-external",
    "inbox_session": "05_Inbox/queue-session",
    "inbox_stale": "05_Inbox/review-stale",
    "planning": "06_Planning",
    "research": "07_Research",
    "strategy": "08_Strategy",
    "changelog": "09_Changelog",
    "changelog_branches": "09_Changelog/branches",
    "changelog_merged": "09_Changelog/merged",
    "changelog_releases": "09_Changelog/releases",
    "changelog_deploys": "09_Changelog/deploys",
    "changelog_environments": "09_Changelog/environments",
    "templates": "10_Templates",
    "memory": "01_memory",
    "archive": "99_Archive",
}

# Cache
_schema_cache: Optional[dict] = None
_schema_mtime: float = 0


def _vault_root() -> Path:
    """Resolve the vault root path."""
    vault = os.environ.get(
        "LACP_OBSIDIAN_VAULT",
        os.environ.get("OPENCLAW_VAULT", ""),
    )
    if not vault:
        openclaw_home = os.environ.get("OPENCLAW_HOME", os.path.expanduser("~/.openclaw"))
        vault = os.path.join(openclaw_home, "data", "knowledge")
    return Path(vault)


def _schema_path() -> Path:
    """Return path to vault-schema.json."""
    plugin_dir = os.environ.get(
        "OPENCLAW_PLUGIN_DIR",
        os.path.expanduser("~/.openclaw/extensions/openclaw-lacp-fusion"),
    )
    return Path(plugin_dir) / "config" / "vault-schema.json"


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
        vault.memory          -> Path("/Volumes/Cortex/01_memory")
        vault.inbox_agent     -> Path("/Volumes/Cortex/05_Inbox/queue-agent")
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
