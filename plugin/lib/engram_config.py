#!/usr/bin/env python3
"""
engram_config — single source of truth for Engram configuration.

Resolution order:
  1. ENGRAM_HOME env var (default ~/.engram)
  2. $ENGRAM_HOME/config.json (if exists)
  3. Built-in defaults

This module is host-agnostic. It does NOT read openclaw.json, mode.json,
.engram.env, or any LACP_*/OPENCLAW_* env var. Migration from those legacy
sources is handled separately by bin/engram-migrate-config.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
VALID_MODES = ("standalone", "connected", "curator")

DEFAULTS: dict[str, Any] = {
    "schemaVersion": SCHEMA_VERSION,
    "profile": "autonomous",
    "vaultPath": None,           # filled at load() time relative to engram_home
    "knowledgeRoot": None,
    "automationRoot": None,
    "mode": "standalone",
    "mutationsEnabled": True,
    "agentRole": "developer",
    "curator": {"url": None, "token": None},
    "features": {
        "localFirst": True,
        "provenanceEnabled": True,
        "codeGraphEnabled": True,
        "contextEngine": "lossless-claw",
    },
    "policy": {
        "tier": "review",
        "approvalCacheTtlMinutes": 60,
        "costCeilingHourlyUsd": None,
        "costCeilingDailyUsd": None,
    },
    "lcm": {
        "queryBatchSize": 32,
        "promotionThreshold": 5,
        "autoDiscoveryInterval": "daily",
    },
    "qmd": {"collections": []},
    "hosts": {
        "openclaw": "~/.openclaw",
        "claudeCode": "~/.claude",
        "codex": "~/.codex",
    },
}

_cache: dict[str, Any] = {}


@dataclass(frozen=True)
class EngramConfig:
    engram_home: Path
    config_path: Path
    schema_version: int
    profile: str
    vault_path: str
    knowledge_root: str
    automation_root: str
    mode: str
    mutations_enabled: bool
    agent_role: str
    curator_url: str | None
    curator_token: str | None
    features: dict[str, Any] = field(default_factory=dict)
    policy: dict[str, Any] = field(default_factory=dict)
    lcm: dict[str, Any] = field(default_factory=dict)
    qmd: dict[str, Any] = field(default_factory=dict)
    hosts: dict[str, str] = field(default_factory=dict)


def engram_home() -> Path:
    return Path(os.environ.get("ENGRAM_HOME", os.path.expanduser("~/.engram")))


def config_path() -> Path:
    return engram_home() / "config.json"


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


_LEGACY_KEY_ALIASES = {
    # Old flat keys that might appear in hand-edited or partially-migrated
    # config files. Aliased on read so in-flight installs keep working.
    "obsidianVault": "vaultPath",
    "policyTier": ("policy", "tier"),
    "contextEngine": ("features", "contextEngine"),
    "curatorUrl": ("curator", "url"),
    "curatorToken": ("curator", "token"),
}


def _apply_aliases(data: dict) -> dict:
    out = dict(data)
    for legacy, new in _LEGACY_KEY_ALIASES.items():
        if legacy not in out:
            continue
        value = out.pop(legacy)
        if isinstance(new, tuple):
            cursor = out
            for part in new[:-1]:
                cursor = cursor.setdefault(part, {})
            cursor.setdefault(new[-1], value)
        else:
            out.setdefault(new, value)
    return out


def _read_file() -> dict:
    path = config_path()
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return _apply_aliases(raw)
    except (json.JSONDecodeError, OSError):
        return {}


def _resolve_paths(merged: dict, home: Path) -> dict:
    if not merged.get("vaultPath"):
        merged["vaultPath"] = str(home / "knowledge")
    if not merged.get("knowledgeRoot"):
        merged["knowledgeRoot"] = str(home / "knowledge")
    if not merged.get("automationRoot"):
        merged["automationRoot"] = str(home / "automation")
    return merged


def load() -> EngramConfig:
    if "config" in _cache:
        return _cache["config"]

    home = engram_home()
    file_data = _read_file()
    merged = _deep_merge(DEFAULTS, file_data)
    merged = _resolve_paths(merged, home)

    cfg = EngramConfig(
        engram_home=home,
        config_path=config_path(),
        schema_version=merged.get("schemaVersion", SCHEMA_VERSION),
        profile=merged["profile"],
        vault_path=merged["vaultPath"],
        knowledge_root=merged["knowledgeRoot"],
        automation_root=merged["automationRoot"],
        mode=merged["mode"],
        mutations_enabled=bool(merged["mutationsEnabled"]),
        agent_role=merged["agentRole"],
        curator_url=merged["curator"].get("url"),
        curator_token=merged["curator"].get("token"),
        features=merged["features"],
        policy=merged["policy"],
        lcm=merged["lcm"],
        qmd=merged["qmd"],
        hosts=merged["hosts"],
    )
    _cache["config"] = cfg
    return cfg


def save(updates: dict[str, Any]) -> Path:
    """Merge `updates` into the on-disk config and persist atomically."""
    if "mode" in updates and updates["mode"] not in VALID_MODES:
        raise ValueError(
            f"Invalid mode {updates['mode']!r}. Must be one of {VALID_MODES}"
        )

    existing = _read_file()
    merged = _deep_merge(existing or {}, updates)
    merged.setdefault("schemaVersion", SCHEMA_VERSION)

    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
    _cache.clear()
    return path


def to_dict(cfg: EngramConfig | None = None) -> dict:
    cfg = cfg or load()
    return {
        "schemaVersion": cfg.schema_version,
        "profile": cfg.profile,
        "vaultPath": cfg.vault_path,
        "knowledgeRoot": cfg.knowledge_root,
        "automationRoot": cfg.automation_root,
        "mode": cfg.mode,
        "mutationsEnabled": cfg.mutations_enabled,
        "agentRole": cfg.agent_role,
        "curator": {"url": cfg.curator_url, "token": cfg.curator_token},
        "features": cfg.features,
        "policy": cfg.policy,
        "lcm": cfg.lcm,
        "qmd": cfg.qmd,
        "hosts": cfg.hosts,
    }
