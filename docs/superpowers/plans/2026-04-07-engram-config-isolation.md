# Engram Config Isolation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move Engram's config out of `~/.openclaw/openclaw.json` and into a host-agnostic `~/.engram/config.json` so Claude Code, Codex, and OpenClaw all share one source of truth — and so a benchmark run can be isolated by setting `$ENGRAM_HOME` to a throwaway dir.

**Architecture:** Introduce one Python module (`engram_config.py`) as the single resolver, with a `$ENGRAM_HOME` env var (default `~/.engram`) and a JSON file at `$ENGRAM_HOME/config.json`. Refactor the three existing parallel resolvers (`vault_paths.py`, `mode.py`, `bin/wizard.mjs`/`INSTALL.sh`) to delegate to this module. Add a migration script that lifts the existing `plugins.entries.engram.config` block out of `openclaw.json` (with full backups) and writes it to `~/.engram/config.json`. The wizard then writes there directly. QMD collection registration and the optional `lcm.db` move are bolted onto the migration step.

**Tech Stack:** Python 3.11+ stdlib (json, pathlib, os, shutil), pytest, bash, jq, Node 20+ (`@clack/prompts` already vendored in `bin/wizard.mjs`).

**Branching:** All work happens in worktree `.worktrees/config-isolation` on branch `feat/v4.0-engram-config-isolation` (already created from `feat/v4.0-business-superintelligence` @ `a16deab`). Do NOT rebase onto master until v4.0 ships.

---

## File Structure

**Create:**
- `plugin/lib/engram_config.py` — single resolver module. Owns the schema, reads `$ENGRAM_HOME/config.json`, layers env > file > defaults, exposes `EngramConfig` dataclass and `load()` / `save()` helpers.
- `plugin/lib/tests/test_engram_config.py` — pytest tests for the resolver, isolated via `monkeypatch.setenv("ENGRAM_HOME", str(tmp_path))`.
- `plugin/lib/tests/test_engram_config_migrate.py` — pytest tests for the migration logic against synthetic `~/.openclaw/` fixtures.
- `bin/engram-migrate-config` — Python CLI that runs migration with `--dry-run`, `--source`, and `--target` flags. Stand-alone, importable for tests.
- `docs/engram-config.md` — short user-facing doc explaining `$ENGRAM_HOME`, config file location, and how to point Claude Code / Codex / OpenClaw at it.

**Modify:**
- `plugin/lib/mode.py` — gut `_read_config_file()`, `_read_env_config()`, `get_mode()`, `get_config()` and delegate to `engram_config.load()`. Keep the public surface (`ModeConfig`, `get_config`, `get_mode`, `is_*`, `check_mutation_allowed`, `get_inbox_queue_path`) so callers don't break. Drop all `LACP_` and `OPENCLAW_` env-var fallbacks (per memory: feedback_no_lacp_refs).
- `plugin/lib/vault_paths.py` — replace `_vault_root()` with a call to `engram_config.load().vault_path`. Keep `resolve()`, `vault`, `all_paths()` API.
- `bin/engram` — rewrite `cmd_status()` (line 256) to import from `~/.engram/extensions/engram/lib/engram_config` (or fallback to repo path during dev). Drop `_source_env_config()` and the openclaw.json clean-up shim around line 722.
- `bin/wizard.mjs` — change the `engram` block writer to emit `~/.engram/config.json` as flat JSON (no `plugins.entries.engram.config` nesting). Stop writing to `/tmp/engram-wizard-config.json` for the engram-config payload (keep it for the agents/workspaces payload that `INSTALL.sh` consumes).
- `INSTALL.sh` — replace `update_gateway_config()` (line 1245) with a `write_engram_config()` function that writes `~/.engram/config.json` directly. Replace the two `_run_init_task` jq pokes at lines 1435 + 1442 (contextEngine, codeGraphEnabled) to target `~/.engram/config.json`. Leave a thin "host pointer" updater that puts `{"engramConfig": "~/.engram/config.json"}` into `openclaw.json` so OpenClaw still discovers Engram, but the actual config lives outside.
- `plugin/openclaw.plugin.json` — add a top-level `"engramConfigPath": "~/.engram/config.json"` hint so OpenClaw's loader knows where to look. Do NOT touch `configSchema` (keep it as the canonical schema reference for now).

**Test:**
- `plugin/lib/tests/test_engram_config.py`
- `plugin/lib/tests/test_engram_config_migrate.py`
- `plugin/lib/tests/test_mode_delegation.py` — verifies `mode.get_config()` returns values sourced from `engram_config` (regression guard for the refactor).

**Schema** (the canonical shape of `~/.engram/config.json`):

```json
{
  "schemaVersion": 1,
  "profile": "autonomous",
  "vaultPath": "/Volumes/Cortex",
  "knowledgeRoot": "/Users/andrewfisher/.engram/knowledge",
  "automationRoot": "/Users/andrewfisher/.engram/automation",
  "mode": "standalone",
  "mutationsEnabled": true,
  "agentRole": "developer",
  "curator": {
    "url": null,
    "token": null
  },
  "features": {
    "localFirst": true,
    "provenanceEnabled": true,
    "codeGraphEnabled": true,
    "contextEngine": "lossless-claw"
  },
  "policy": {
    "tier": "review",
    "approvalCacheTtlMinutes": 60,
    "costCeilingHourlyUsd": null,
    "costCeilingDailyUsd": null
  },
  "lcm": {
    "queryBatchSize": 32,
    "promotionThreshold": 5,
    "autoDiscoveryInterval": "daily"
  },
  "qmd": {
    "collections": []
  },
  "hosts": {
    "openclaw": "~/.openclaw",
    "claudeCode": "~/.claude",
    "codex": "~/.codex"
  }
}
```

---

## Tasks

### Task 1: Scaffold `engram_config.py` with failing tests

**Files:**
- Create: `plugin/lib/engram_config.py`
- Create: `plugin/lib/tests/test_engram_config.py`

- [ ] **Step 1: Write the failing tests**

```python
# plugin/lib/tests/test_engram_config.py
"""Tests for engram_config — single source of truth for Engram config."""

import json
import os
import sys
from pathlib import Path

import pytest

# Make plugin/lib importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import engram_config as ec


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    """Point ENGRAM_HOME at a throwaway dir and clear leaky env vars."""
    monkeypatch.setenv("ENGRAM_HOME", str(tmp_path))
    for var in (
        "LACP_OBSIDIAN_VAULT",
        "OPENCLAW_VAULT",
        "OPENCLAW_HOME",
        "LACP_MODE",
        "LACP_CURATOR_URL",
        "LACP_CURATOR_TOKEN",
        "LACP_MUTATIONS_ENABLED",
        "LACP_AGENT_ROLE",
    ):
        monkeypatch.delenv(var, raising=False)
    # Reset module-level cache
    ec._cache.clear()
    return tmp_path


def test_default_config_when_no_file(isolated_home):
    cfg = ec.load()
    assert cfg.mode == "standalone"
    assert cfg.mutations_enabled is True
    assert cfg.vault_path == str(isolated_home / "knowledge")
    assert cfg.curator_url is None
    assert cfg.features["contextEngine"] == "lossless-claw"


def test_loads_existing_config_file(isolated_home):
    cfg_path = isolated_home / "config.json"
    cfg_path.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "vaultPath": "/Volumes/Cortex",
                "mode": "standalone",
                "mutationsEnabled": True,
                "features": {"contextEngine": "lossless-claw"},
            }
        )
    )
    ec._cache.clear()
    cfg = ec.load()
    assert cfg.vault_path == "/Volumes/Cortex"


def test_engram_home_overrides_default(tmp_path, monkeypatch):
    monkeypatch.setenv("ENGRAM_HOME", str(tmp_path / "alt"))
    ec._cache.clear()
    cfg = ec.load()
    assert cfg.engram_home == tmp_path / "alt"
    assert cfg.vault_path == str(tmp_path / "alt" / "knowledge")


def test_save_then_load_round_trip(isolated_home):
    cfg = ec.load()
    written = ec.save({"vaultPath": "/tmp/test-vault", "mode": "curator"})
    assert written.exists()
    ec._cache.clear()
    cfg2 = ec.load()
    assert cfg2.vault_path == "/tmp/test-vault"
    assert cfg2.mode == "curator"


def test_invalid_mode_raises(isolated_home):
    with pytest.raises(ValueError):
        ec.save({"mode": "bogus"})


def test_save_creates_parent_dirs(tmp_path, monkeypatch):
    target = tmp_path / "deep" / "nested" / "engram"
    monkeypatch.setenv("ENGRAM_HOME", str(target))
    ec._cache.clear()
    ec.save({"vaultPath": "/x"})
    assert (target / "config.json").exists()


def test_no_lacp_env_vars_referenced(isolated_home, monkeypatch):
    """Regression: engram_config must not honor any LACP_* env var."""
    monkeypatch.setenv("LACP_OBSIDIAN_VAULT", "/should/be/ignored")
    monkeypatch.setenv("LACP_MODE", "curator")
    ec._cache.clear()
    cfg = ec.load()
    assert "/should/be/ignored" not in cfg.vault_path
    assert cfg.mode == "standalone"
```

- [ ] **Step 2: Run tests to verify they fail**

Run from repo root: `python -m pytest plugin/lib/tests/test_engram_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'engram_config'`

- [ ] **Step 3: Implement the minimal module to pass the tests**

```python
# plugin/lib/engram_config.py
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run from repo root: `python -m pytest plugin/lib/tests/test_engram_config.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add plugin/lib/engram_config.py plugin/lib/tests/test_engram_config.py
git commit -m "feat(engram): add host-agnostic engram_config resolver

Single source of truth for Engram config at \$ENGRAM_HOME/config.json.
No LACP_/OPENCLAW_ env var coupling. Tests cover defaults, file load,
ENGRAM_HOME override, save round-trip, invalid mode, and the no-LACP
regression."
```

---

### Task 2: Refactor `mode.py` to delegate to `engram_config`

**Files:**
- Modify: `plugin/lib/mode.py` (full rewrite of resolver internals)
- Create: `plugin/lib/tests/test_mode_delegation.py`

- [ ] **Step 0: Run impact analysis (project CLAUDE.md mandate)**

```
gitnexus_impact({target: "get_config", direction: "upstream"})
gitnexus_impact({target: "ModeConfig", direction: "upstream"})
```

Expected: report the blast radius (which `bin/engram` callers, MCP tools,
and test files import these). The refactor preserves the public API, so
risk should be LOW. If HIGH or CRITICAL, stop and surface to user.

- [ ] **Step 1: Write the failing test**

```python
# plugin/lib/tests/test_mode_delegation.py
"""Verify mode.get_config() reads from engram_config, not legacy sources."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import engram_config as ec
import mode


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("ENGRAM_HOME", str(tmp_path))
    for var in (
        "LACP_OBSIDIAN_VAULT", "OPENCLAW_VAULT", "OPENCLAW_HOME",
        "LACP_MODE", "LACP_CURATOR_URL", "LACP_CURATOR_TOKEN",
        "LACP_MUTATIONS_ENABLED", "LACP_AGENT_ROLE",
    ):
        monkeypatch.delenv(var, raising=False)
    ec._cache.clear()
    return tmp_path


def test_mode_reads_from_engram_config(isolated):
    (isolated / "config.json").write_text(
        json.dumps({
            "vaultPath": "/test/vault",
            "mode": "curator",
            "mutationsEnabled": False,
            "curator": {"url": "https://curator.example", "token": "abc"},
        })
    )
    ec._cache.clear()
    cfg = mode.get_config()
    assert cfg.mode == "curator"
    assert cfg.vault_path == "/test/vault"
    assert cfg.curator_url == "https://curator.example"
    assert cfg.curator_token == "abc"
    assert cfg.mutations_enabled is False


def test_mode_ignores_openclaw_legacy_files(isolated, tmp_path, monkeypatch):
    fake_openclaw = tmp_path / "fake-openclaw"
    (fake_openclaw / "config").mkdir(parents=True)
    (fake_openclaw / "config" / "mode.json").write_text(
        json.dumps({"mode": "connected", "vault_path": "/should/be/ignored"})
    )
    monkeypatch.setenv("OPENCLAW_HOME", str(fake_openclaw))
    ec._cache.clear()
    cfg = mode.get_config()
    assert cfg.mode == "standalone"
    assert "/should/be/ignored" not in cfg.vault_path


def test_check_mutation_allowed_in_connected(isolated):
    ec.save({"mode": "connected"})
    allowed, reason = mode.check_mutation_allowed("brain-expand")
    assert allowed is False
    assert "connected mode" in reason
```

- [ ] **Step 2: Run test to verify it fails**

Run from repo root: `python -m pytest plugin/lib/tests/test_mode_delegation.py -v`
Expected: FAIL — current `mode.py` reads `~/.openclaw/config/mode.json`, so the second test will see the wrong vault path / mode.

- [ ] **Step 3: Rewrite `mode.py` to delegate**

```python
# plugin/lib/mode.py
#!/usr/bin/env python3
"""
Mode helpers for engram.

Thin wrapper around engram_config — exists only to preserve the
ModeConfig public API that bin/engram and other callers expect.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import engram_config as ec

VALID_MODES = ec.VALID_MODES

MUTATION_COMMANDS = frozenset({
    "brain-expand",
    "brain-resolve",
    "obsidian-optimize",
})

INBOX_REDIRECT_COMMANDS = frozenset({
    "brain-ingest",
})


@dataclass(frozen=True)
class ModeConfig:
    mode: str
    curator_url: str
    curator_token: str
    mutations_enabled: bool
    vault_path: str
    agent_role: str

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "curator_url": self.curator_url,
            "curator_token": self.curator_token,
            "mutations_enabled": self.mutations_enabled,
            "vault_path": self.vault_path,
            "agent_role": self.agent_role,
        }


def get_mode() -> str:
    return ec.load().mode


def get_config() -> ModeConfig:
    cfg = ec.load()
    return ModeConfig(
        mode=cfg.mode,
        curator_url=cfg.curator_url or "",
        curator_token=cfg.curator_token or "",
        mutations_enabled=cfg.mutations_enabled,
        vault_path=cfg.vault_path,
        agent_role=cfg.agent_role,
    )


def set_mode(
    mode: str,
    *,
    curator_url: str | None = None,
    curator_token: str | None = None,
    vault_path: str | None = None,
    agent_role: str | None = None,
) -> Path:
    if mode not in VALID_MODES:
        raise ValueError(f"Invalid mode: {mode!r}. Must be one of {VALID_MODES}")

    updates: dict = {"mode": mode, "mutationsEnabled": mode != "connected"}
    if curator_url is not None:
        updates.setdefault("curator", {})["url"] = curator_url
    if curator_token is not None:
        updates.setdefault("curator", {})["token"] = curator_token
    if vault_path is not None:
        updates["vaultPath"] = vault_path
    if agent_role is not None:
        updates["agentRole"] = agent_role
    return ec.save(updates)


def is_standalone() -> bool:
    return get_mode() == "standalone"


def is_connected() -> bool:
    return get_mode() == "connected"


def is_curator() -> bool:
    return get_mode() == "curator"


def check_mutation_allowed(command_name: str) -> tuple[bool, str]:
    cfg = get_config()
    if cfg.mode in ("standalone", "curator"):
        return True, ""
    if command_name in MUTATION_COMMANDS:
        return False, (
            f"{command_name} is blocked in connected mode. "
            f"Vault mutations are managed by the curator at {cfg.curator_url}."
        )
    if command_name in INBOX_REDIRECT_COMMANDS:
        return True, "redirected_to_inbox"
    return True, ""


def get_inbox_queue_path(agent_id: str = "") -> str:
    cfg = get_config()
    queue_name = f"queue-{agent_id}" if agent_id else "queue-agent"
    try:
        from vault_paths import resolve
        return str(resolve("inbox") / queue_name)
    except (ImportError, KeyError):
        import os
        return os.path.join(cfg.vault_path, "inbox", queue_name)
```

- [ ] **Step 4: Run both test files to verify they pass**

Run from repo root: `python -m pytest plugin/lib/tests/test_engram_config.py plugin/lib/tests/test_mode_delegation.py -v`
Expected: 10 passed.

- [ ] **Step 5: Run the broader test suite to catch regressions**

Run from repo root: `python -m pytest plugin/lib/tests/ -v --ignore=plugin/lib/tests/test_graph_db.py --ignore=plugin/lib/tests/test_calendar_watcher.py`
Expected: existing tests still pass (the two ignored ones need a live Neo4j / Google API).

- [ ] **Step 6: Commit**

```bash
git add plugin/lib/mode.py plugin/lib/tests/test_mode_delegation.py
git commit -m "refactor(engram): delegate mode.py to engram_config

ModeConfig public API preserved for bin/engram callers, but every
read now goes through engram_config — no more ~/.openclaw/config/mode.json
or .engram.env reads, no more LACP_* env-var fallbacks."
```

---

### Task 3: Refactor `vault_paths.py` to delegate to `engram_config`

**Files:**
- Modify: `plugin/lib/vault_paths.py`

- [ ] **Step 0: Run impact analysis**

```
gitnexus_impact({target: "_vault_root", direction: "upstream"})
gitnexus_impact({target: "resolve", direction: "upstream"})
```

Expected: identify all callers of `vault_paths.resolve()` and
`vault_paths.vault.*`. Public API is preserved; risk should be LOW.

- [ ] **Step 1: Write a quick test asserting vault_root comes from engram_config**

Append to `plugin/lib/tests/test_engram_config.py`:

```python
def test_vault_paths_uses_engram_config(isolated_home, monkeypatch):
    import importlib
    import vault_paths
    importlib.reload(vault_paths)
    (isolated_home / "config.json").write_text(
        '{"vaultPath": "/v", "schemaVersion": 1}'
    )
    ec._cache.clear()
    importlib.reload(vault_paths)
    assert str(vault_paths.root()) == "/v"
    assert str(vault_paths.resolve("memory")) == "/v/memory"
```

- [ ] **Step 2: Run it to verify it fails**

Run from repo root: `python -m pytest plugin/lib/tests/test_engram_config.py::test_vault_paths_uses_engram_config -v`
Expected: FAIL — `vault_paths._vault_root()` still reads `LACP_OBSIDIAN_VAULT` / `OPENCLAW_VAULT`.

- [ ] **Step 3: Patch `vault_paths.py` to delegate**

Replace `_vault_root()` (lines 81-90) with:

```python
def _vault_root() -> Path:
    """Resolve the vault root path via engram_config."""
    from engram_config import load
    return Path(load().vault_path)
```

Also delete the now-unused `import os` reference if nothing else needs it (it's still used elsewhere in the file, so leave it).

The schema-loading section (`_schema_path()`, `_load_schema()`) stays — it reads `vault-schema.json` from the plugin install dir, which is still legitimately a plugin-data concern, not a host-config concern. Update `_schema_path()` to look under `$ENGRAM_HOME/extensions/engram/config/vault-schema.json` first, falling back to the legacy path:

```python
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
```

- [ ] **Step 4: Run the test to verify it passes**

Run from repo root: `python -m pytest plugin/lib/tests/test_engram_config.py -v`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add plugin/lib/vault_paths.py plugin/lib/tests/test_engram_config.py
git commit -m "refactor(engram): vault_paths delegates to engram_config

Vault root now comes from engram_config.load().vault_path. The
vault-schema.json lookup prefers \$ENGRAM_HOME/extensions/engram but
falls back to ~/.openclaw/extensions/engram so installs in flight
keep working."
```

---

### Task 4: Migration script — port legacy config out of openclaw.json

**Files:**
- Create: `bin/engram-migrate-config`
- Create: `plugin/lib/tests/test_engram_config_migrate.py`

- [ ] **Step 1: Write the failing tests**

```python
# plugin/lib/tests/test_engram_config_migrate.py
"""Tests for the openclaw -> engram config migration."""
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "bin"))
sys.path.insert(0, str(REPO_ROOT / "plugin" / "lib"))

import importlib.util
spec = importlib.util.spec_from_file_location(
    "engram_migrate_config",
    REPO_ROOT / "bin" / "engram-migrate-config",
)
mig = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mig)


@pytest.fixture
def fake_openclaw(tmp_path):
    home = tmp_path / "openclaw"
    (home / "config").mkdir(parents=True)
    (home / "data" / "knowledge").mkdir(parents=True)

    gateway = home / "openclaw.json"
    gateway.write_text(json.dumps({
        "plugins": {
            "allow": ["engram"],
            "entries": {
                "engram": {
                    "enabled": True,
                    "config": {
                        "profile": "autonomous",
                        "obsidianVault": "/Volumes/Cortex",
                        "knowledgeRoot": str(home / "data" / "knowledge"),
                        "localFirst": True,
                        "provenanceEnabled": True,
                        "codeGraphEnabled": True,
                        "policyTier": "review",
                        "contextEngine": "lossless-claw",
                        "mode": "standalone",
                        "mutationsEnabled": "true",
                        "curatorUrl": None,
                    },
                }
            },
        }
    }))
    (home / "config" / "mode.json").write_text(json.dumps({
        "mode": "standalone", "mutations_enabled": True,
    }))
    return home


def test_migrate_writes_engram_config(fake_openclaw, tmp_path):
    target = tmp_path / "engram"
    result = mig.migrate(source=fake_openclaw, target=target, dry_run=False)
    cfg_file = target / "config.json"
    assert cfg_file.exists()
    data = json.loads(cfg_file.read_text())
    assert data["vaultPath"] == "/Volumes/Cortex"
    assert data["features"]["contextEngine"] == "lossless-claw"
    assert data["mode"] == "standalone"
    assert data["mutationsEnabled"] is True
    assert data["schemaVersion"] == 1
    assert result["wrote"] == str(cfg_file)


def test_migrate_creates_backup(fake_openclaw, tmp_path):
    target = tmp_path / "engram"
    mig.migrate(source=fake_openclaw, target=target, dry_run=False)
    backups = list((fake_openclaw).glob("openclaw.json.bak.*"))
    assert len(backups) == 1
    # Original gateway is untouched aside from any pointer rewrite
    gw = json.loads((fake_openclaw / "openclaw.json").read_text())
    assert "engram" in gw["plugins"]["entries"]


def test_migrate_dry_run_writes_nothing(fake_openclaw, tmp_path):
    target = tmp_path / "engram"
    result = mig.migrate(source=fake_openclaw, target=target, dry_run=True)
    assert not (target / "config.json").exists()
    assert result["dry_run"] is True
    assert result["preview"]["vaultPath"] == "/Volumes/Cortex"


def test_migrate_idempotent(fake_openclaw, tmp_path):
    target = tmp_path / "engram"
    mig.migrate(source=fake_openclaw, target=target, dry_run=False)
    first = (target / "config.json").read_text()
    mig.migrate(source=fake_openclaw, target=target, dry_run=False)
    second = (target / "config.json").read_text()
    assert first == second


def test_migrate_handles_missing_gateway(tmp_path, monkeypatch):
    target = tmp_path / "engram"
    src = tmp_path / "no-openclaw"
    src.mkdir()
    result = mig.migrate(source=src, target=target, dry_run=False)
    # File contains only what migrate explicitly persisted; defaults
    # are layered in by ec.load(), so verify via load() not raw json.
    monkeypatch.setenv("ENGRAM_HOME", str(target))
    ec._cache.clear()
    cfg = ec.load()
    assert cfg.mode == "standalone"
    assert result["source_found"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run from repo root: `python -m pytest plugin/lib/tests/test_engram_config_migrate.py -v`
Expected: FAIL — `bin/engram-migrate-config` doesn't exist yet.

- [ ] **Step 3: Implement `bin/engram-migrate-config`**

```python
#!/usr/bin/env python3
"""
engram-migrate-config — migrate Engram config out of openclaw.json
into ~/.engram/config.json.

Usage:
  engram-migrate-config [--source ~/.openclaw] [--target ~/.engram] [--dry-run]

Idempotent: if the target already has a config.json with the same
content this writes nothing. Always backs the source up first.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any

# Make engram_config importable when run from a checkout or installed plugin
_HERE = Path(__file__).resolve().parent
for candidate in (
    _HERE.parent / "plugin" / "lib",
    Path.home() / ".engram" / "extensions" / "engram" / "lib",
    Path.home() / ".openclaw" / "extensions" / "engram" / "lib",
):
    if (candidate / "engram_config.py").exists():
        sys.path.insert(0, str(candidate))
        break

import engram_config as ec  # noqa: E402

LEGACY_TO_NEW = {
    "profile": "profile",
    "obsidianVault": "vaultPath",
    "knowledgeRoot": "knowledgeRoot",
    "automationRoot": "automationRoot",
    "policyTier": ("policy", "tier"),
    "contextEngine": ("features", "contextEngine"),
    "localFirst": ("features", "localFirst"),
    "provenanceEnabled": ("features", "provenanceEnabled"),
    "codeGraphEnabled": ("features", "codeGraphEnabled"),
    "mode": "mode",
    "mutationsEnabled": "mutationsEnabled",
    "curatorUrl": ("curator", "url"),
    "curatorToken": ("curator", "token"),
    "agentRole": "agentRole",
}


def _coerce_bool(v: Any) -> Any:
    if isinstance(v, str) and v.lower() in ("true", "false"):
        return v.lower() == "true"
    return v


def _set_nested(out: dict, key: Any, value: Any) -> None:
    if isinstance(key, tuple):
        cursor = out
        for part in key[:-1]:
            cursor = cursor.setdefault(part, {})
        cursor[key[-1]] = value
    else:
        out[key] = value


def _read_legacy_engram_config(source: Path) -> dict:
    """Pull engram config out of openclaw.json and mode.json. Returns {} if absent."""
    found: dict = {}
    gateway = source / "openclaw.json"
    if gateway.exists():
        try:
            data = json.loads(gateway.read_text(encoding="utf-8"))
            entry = (
                data.get("plugins", {})
                    .get("entries", {})
                    .get("engram", {})
                    .get("config", {})
            )
            for legacy_key, new_key in LEGACY_TO_NEW.items():
                if legacy_key in entry:
                    _set_nested(found, new_key, _coerce_bool(entry[legacy_key]))
        except (json.JSONDecodeError, OSError):
            pass

    mode_file = source / "config" / "mode.json"
    if mode_file.exists():
        try:
            data = json.loads(mode_file.read_text(encoding="utf-8"))
            if "mode" in data and "mode" not in found:
                found["mode"] = data["mode"]
            if "mutations_enabled" in data and "mutationsEnabled" not in found:
                found["mutationsEnabled"] = bool(data["mutations_enabled"])
            if "vault_path" in data and "vaultPath" not in found:
                found["vaultPath"] = data["vault_path"]
        except (json.JSONDecodeError, OSError):
            pass

    return found


def _backup(path: Path) -> Path | None:
    if not path.exists():
        return None
    bak = path.with_suffix(path.suffix + f".bak.{int(time.time())}")
    shutil.copy2(path, bak)
    return bak


def migrate(
    *,
    source: Path,
    target: Path,
    dry_run: bool = False,
) -> dict:
    source = Path(source).expanduser()
    target = Path(target).expanduser()

    legacy = _read_legacy_engram_config(source)
    source_found = bool(legacy)

    # Build merged config: defaults + legacy values
    merged: dict = {"schemaVersion": ec.SCHEMA_VERSION}
    for k, v in legacy.items():
        merged[k] = v

    if dry_run:
        # Still resolve via _deep_merge so the preview matches save() output
        preview = ec._deep_merge(ec.DEFAULTS, merged)
        return {
            "dry_run": True,
            "source_found": source_found,
            "preview": preview,
            "would_write": str(target / "config.json"),
        }

    # Backup target if it already exists
    target_cfg = target / "config.json"
    pre_backup = _backup(target_cfg)

    # Backup gateway too (we never edit it here, but record the snapshot)
    gateway_backup = _backup(source / "openclaw.json")

    target.mkdir(parents=True, exist_ok=True)

    # Snapshot/restore ENGRAM_HOME so migrate() never leaks env into
    # the surrounding process or test session.
    prev_home = os.environ.get("ENGRAM_HOME")
    try:
        os.environ["ENGRAM_HOME"] = str(target)
        ec._cache.clear()
        written_path = ec.save(merged)
    finally:
        if prev_home is None:
            os.environ.pop("ENGRAM_HOME", None)
        else:
            os.environ["ENGRAM_HOME"] = prev_home
        ec._cache.clear()

    return {
        "dry_run": False,
        "source_found": source_found,
        "wrote": str(written_path),
        "target_backup": str(pre_backup) if pre_backup else None,
        "gateway_backup": str(gateway_backup) if gateway_backup else None,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Migrate Engram config to ~/.engram/config.json")
    p.add_argument("--source", default=os.path.expanduser("~/.openclaw"))
    p.add_argument("--target", default=os.path.expanduser("~/.engram"))
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)

    result = migrate(
        source=Path(args.source),
        target=Path(args.target),
        dry_run=args.dry_run,
    )
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run from repo root: `python -m pytest plugin/lib/tests/test_engram_config_migrate.py -v`
Expected: 5 passed.

- [ ] **Step 5: Make the script executable and dry-run it against the real install**

```bash
chmod +x bin/engram-migrate-config
./bin/engram-migrate-config --dry-run
```

Expected: prints a JSON preview showing `"vaultPath": "/Volumes/Cortex"` and `"source_found": true`. Verifies it sees the real engram config without writing anything.

- [ ] **Step 6: Commit**

```bash
git add bin/engram-migrate-config plugin/lib/tests/test_engram_config_migrate.py
git commit -m "feat(engram): add engram-migrate-config CLI

Lifts plugins.entries.engram.config out of openclaw.json (and any
legacy mode.json) into ~/.engram/config.json. Idempotent, supports
--dry-run, backs up both source and target before writing."
```

---

### Task 5: Run the migration against a throwaway copy of `~/.openclaw`

**Files:**
- No code changes — verification step only.

- [ ] **Step 1: Snapshot ~/.openclaw to a sandbox**

```bash
SANDBOX=$(mktemp -d -t engram-mig-XXXX)
cp -R ~/.openclaw "$SANDBOX/openclaw"
cp -R ~/.engram "$SANDBOX/engram-prev" 2>/dev/null || mkdir -p "$SANDBOX/engram-prev"
echo "Sandbox at $SANDBOX"
```

- [ ] **Step 2: Run the migration into the sandbox**

```bash
./bin/engram-migrate-config \
  --source "$SANDBOX/openclaw" \
  --target "$SANDBOX/engram-out"
```

Expected: prints `"wrote": ".../engram-out/config.json"` with `"source_found": true`.

- [ ] **Step 3: Verify the result**

```bash
python3 -c "
import json, os
cfg = json.load(open(os.path.expandvars('$SANDBOX/engram-out/config.json')))
print('vault:', cfg['vaultPath'])
print('mode:', cfg['mode'])
print('contextEngine:', cfg['features']['contextEngine'])
assert cfg['vaultPath'] == '/Volumes/Cortex', cfg['vaultPath']
assert cfg['features']['contextEngine'] == 'lossless-claw'
print('OK')
"
```

Expected: prints `OK`.

- [ ] **Step 4: Verify the source openclaw.json was NOT mutated**

```bash
diff -q ~/.openclaw/openclaw.json "$SANDBOX/openclaw/openclaw.json" && echo "unchanged"
```

Expected: prints `unchanged`. Migration only reads from the gateway; rewriting it is Task 7's job.

- [ ] **Step 5: Clean up the sandbox** (optional)

```bash
rm -rf "$SANDBOX"
```

No commit — verification only. If anything failed, fix it in Task 4 and re-run.

---

### Task 6: Run the real migration

**Files:**
- No code — runs the migration on the actual `~/.openclaw`/`~/.engram`.

- [ ] **Step 1: Dry-run against real paths**

```bash
./bin/engram-migrate-config --dry-run
```

Expected: JSON preview matches what `engram status` currently shows for vault, mode, mutations, contextEngine.

- [ ] **Step 2: Run for real**

```bash
./bin/engram-migrate-config
```

Expected: prints `"wrote": "/Users/.../.engram/config.json"`, plus a `gateway_backup` path.

- [ ] **Step 3: Sanity-check by reading via the new module**

```bash
python3 -c "
import sys
sys.path.insert(0, 'plugin/lib')
from engram_config import load
c = load()
print('vault:', c.vault_path)
print('mode:', c.mode)
print('mutations:', c.mutations_enabled)
print('home:', c.engram_home)
"
```

Expected: matches the previous `engram status` output (vault should be `/Volumes/Cortex`).

- [ ] **Step 4: Sanity-check `engram status` still works**

```bash
./bin/engram status
```

**NOTE:** This will FAIL until Task 7 patches `bin/engram` to import from the new path. That is expected — verify the failure is the import path error, not a config-resolution error, then move on.

No commit — pure environment change to `~/.engram/config.json`.

---

### Task 7: Point `bin/engram` and the install dirs at `engram_config`

**Files:**
- Modify: `bin/engram` (cmd_status at line 256, openclaw.json shim around line 722, `_source_env_config`)

- [ ] **Step 0: Run impact analysis**

```
gitnexus_impact({target: "cmd_status", direction: "upstream"})
gitnexus_impact({target: "_source_env_config", direction: "upstream"})
```

Expected: list every command that calls `_source_env_config`. Plan
deletes the function — ALL call sites must be removed in Step 2.

- [ ] **Step 1: Patch `cmd_status` import path**

In `bin/engram` line 267, change:

```bash
sys.path.insert(0, os.path.expanduser('~/.openclaw/extensions/engram/lib'))
```

to a multi-candidate path that prefers `$ENGRAM_HOME` and falls back to the legacy install during migration:

```bash
for p in [
    os.path.expanduser(os.environ.get('ENGRAM_HOME', '~/.engram') + '/extensions/engram/lib'),
    os.path.expanduser('~/.openclaw/extensions/engram/lib'),
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'plugin', 'lib'),
]:
    if os.path.isdir(p):
        sys.path.insert(0, p)
        break
```

Make the same change to any other inline `python3 -c` blocks in `bin/engram` that reference `~/.openclaw/extensions/engram/lib` (search the file with Grep first).

- [ ] **Step 2: Drop `_source_env_config` and the openclaw.json cleanup shim**

First locate every reference so nothing is left dangling:

```bash
grep -n "_source_env_config\|openclaw.json" bin/engram
```

Then:
- Delete the `_source_env_config()` function definition (around line 230) AND every call site reported by the grep above. Common callers: `cmd_status()`, `cmd_doctor()`. Each call line is `_source_env_config` on its own line — delete it.
- Delete the openclaw.json jq clean-up block around line 722. Engram never writes to that file again.

Re-run the grep after deletion — expected output: empty.

- [ ] **Step 3: Verify status works**

```bash
./bin/engram status
```

Expected: Mode/Mutations/Vault rows match the values in `~/.engram/config.json`.

- [ ] **Step 4: Symlink the lib dir into the new home so installed callers keep working**

For now, install copies live at `~/.openclaw/extensions/engram/lib`. Create a parallel install path at `~/.engram/extensions/engram/lib` that points at the same place (or copy):

```bash
mkdir -p ~/.engram/extensions/engram
ln -snf ~/.openclaw/extensions/engram/lib ~/.engram/extensions/engram/lib
ln -snf ~/.openclaw/extensions/engram/config ~/.engram/extensions/engram/config 2>/dev/null || true
```

This is a temporary bridge — Task 9 makes `INSTALL.sh` write the canonical install at `~/.engram/extensions/engram` and symlink back the other way for OpenClaw compatibility.

- [ ] **Step 5: Re-run engram status to confirm**

```bash
ENGRAM_HOME=~/.engram ./bin/engram status
```

Expected: same output.

- [ ] **Step 6: Commit**

```bash
git add bin/engram
git commit -m "refactor(engram): bin/engram resolves lib via ENGRAM_HOME

cmd_status now imports engram_config from \$ENGRAM_HOME/extensions/engram/lib
with a legacy ~/.openclaw fallback for in-flight installs. Drops the
.engram.env source-on-status shim and the openclaw.json cleanup poke."
```

---

### Task 8: Update wizard.mjs to write `~/.engram/config.json` directly

**Files:**
- Modify: `bin/wizard.mjs`

- [ ] **Step 1: Add a `writeEngramConfig()` helper near the top of wizard.mjs**

`mkdirSync`, `writeFileSync`, `HOME`, `OPENCLAW_HOME`, and `ENGRAM_HOME` are
already imported/declared at lines 22 and 29-31. Do NOT re-import or
re-declare them.

After the existing constants (around line 38), add:

```javascript
const ENGRAM_CONFIG_PATH = join(ENGRAM_HOME, 'config.json');

function writeEngramConfig(payload) {
  mkdirSync(ENGRAM_HOME, { recursive: true });
  const merged = {
    schemaVersion: 1,
    profile: payload.profile ?? 'autonomous',
    vaultPath: payload.vaultPath,
    knowledgeRoot: payload.knowledgeRoot ?? join(ENGRAM_HOME, 'knowledge'),
    automationRoot: payload.automationRoot ?? join(ENGRAM_HOME, 'automation'),
    mode: payload.mode ?? 'standalone',
    mutationsEnabled: payload.mutationsEnabled ?? true,
    agentRole: payload.agentRole ?? 'developer',
    curator: {
      url: payload.curatorUrl ?? null,
      token: payload.curatorToken ?? null,
    },
    features: {
      localFirst: payload.localFirst ?? true,
      provenanceEnabled: payload.provenanceEnabled ?? true,
      codeGraphEnabled: payload.codeGraphEnabled ?? true,
      contextEngine: payload.contextEngine ?? 'lossless-claw',
    },
    policy: {
      tier: payload.policyTier ?? 'review',
      approvalCacheTtlMinutes: 60,
    },
    lcm: {
      queryBatchSize: 32,
      promotionThreshold: 5,
      autoDiscoveryInterval: 'daily',
    },
    qmd: {
      collections: payload.qmdCollections ?? [],
    },
    hosts: {
      openclaw: payload.openclawHome ?? OPENCLAW_HOME,
      claudeCode: process.env.CLAUDE_HOME ?? join(HOME, '.claude'),
      codex: process.env.CODEX_HOME ?? join(HOME, '.codex'),
    },
  };
  writeFileSync(ENGRAM_CONFIG_PATH, JSON.stringify(merged, null, 2) + '\n', 'utf-8');
  return ENGRAM_CONFIG_PATH;
}
```

- [ ] **Step 2: Replace the wizard's "write to /tmp/engram-wizard-config.json" engram block**

Find the existing `writeFileSync(CONFIG_OUTPUT, ...)` call (search for `CONFIG_OUTPUT`). Split its payload: keep agents/workspaces/repositories/mcp paths in `/tmp/engram-wizard-config.json` (because INSTALL.sh still consumes them), but ALSO call `writeEngramConfig({...})` immediately afterward with the engram-specific fields (vault, mode, profile, contextEngine, etc.).

Add a `note(green('Wrote ' + ENGRAM_CONFIG_PATH))` after the call so the user can see where it landed.

- [ ] **Step 3: Quick smoke-test of wizard JSON output**

```bash
node -e "
import('./bin/wizard.mjs').catch(e => { console.error(e); process.exit(1); });
" 2>&1 | head -5
```

Expected: wizard imports without syntax errors. (We don't actually run interactive flow here.)

- [ ] **Step 4: Commit**

```bash
git add bin/wizard.mjs
git commit -m "feat(engram): wizard writes ~/.engram/config.json

Wizard now emits the engram config block as a flat ~/.engram/config.json
file matching the engram_config schema. /tmp/engram-wizard-config.json
still receives agent/workspace/MCP payloads for INSTALL.sh."
```

---

### Task 9: Update INSTALL.sh to stop nesting engram config in openclaw.json

**Files:**
- Modify: `INSTALL.sh` (functions `update_gateway_config` ~line 1245, lossless-claw / code-graph pokes ~lines 1435/1442, top-level `GATEWAY_CONFIG` constant ~line 42)

- [ ] **Step 1: Add ENGRAM_HOME constants near the top of INSTALL.sh**

After the existing `OPENCLAW_HOME` definition, add:

```bash
ENGRAM_HOME="${ENGRAM_HOME:-$HOME/.engram}"
ENGRAM_CONFIG="$ENGRAM_HOME/config.json"
```

- [ ] **Step 2: Replace `update_gateway_config` with `write_engram_config`**

Replace the entire `update_gateway_config()` function (lines 1245-1336) with two new functions:

```bash
write_engram_config() {
    log_step 5 "Writing Engram config"

    mkdir -p "$ENGRAM_HOME"
    if [ -f "$ENGRAM_CONFIG" ]; then
        cp "$ENGRAM_CONFIG" "$ENGRAM_CONFIG.bak.$(date +%s)"
        log_info "Engram config backed up"
    fi

    # Defaults so nothing trips set -u
    local WIZARD_CURATOR_URL_SAFE="${WIZARD_CURATOR_URL:-}"
    local WIZARD_CONTEXT_ENGINE_SAFE="${WIZARD_CONTEXT_ENGINE_RESOLVED:-lossless-claw}"

    local mutations_enabled="true"
    if [ "$WIZARD_MODE" = "connected" ]; then
        mutations_enabled="false"
    fi

    # Pre-expand host paths so we never emit literal "~" into JSON
    local OPENCLAW_HOME_SAFE="${OPENCLAW_HOME:-$HOME/.openclaw}"
    local CLAUDE_HOME_SAFE="${CLAUDE_HOME:-$HOME/.claude}"
    local CODEX_HOME_SAFE="${CODEX_HOME:-$HOME/.codex}"

    if [ "$HAS_JQ" = "true" ]; then
        jq -n \
            --arg vault "$DETECTED_VAULT" \
            --arg kr "$ENGRAM_HOME/knowledge" \
            --arg ar "$ENGRAM_HOME/automation" \
            --arg profile "$WIZARD_PROFILE" \
            --arg tier "$WIZARD_POLICY_TIER" \
            --argjson cg "$WIZARD_CODE_GRAPH" \
            --argjson prov "$WIZARD_PROVENANCE" \
            --argjson lf "$WIZARD_LOCAL_FIRST" \
            --arg ce "$WIZARD_CONTEXT_ENGINE_SAFE" \
            --arg mode "$WIZARD_MODE" \
            --argjson mut "$mutations_enabled" \
            --arg curatorUrl "$WIZARD_CURATOR_URL_SAFE" \
            --arg openclawHome "$OPENCLAW_HOME_SAFE" \
            --arg claudeHome "$CLAUDE_HOME_SAFE" \
            --arg codexHome "$CODEX_HOME_SAFE" '
            {
              schemaVersion: 1,
              profile: $profile,
              vaultPath: $vault,
              knowledgeRoot: $kr,
              automationRoot: $ar,
              mode: $mode,
              mutationsEnabled: $mut,
              agentRole: "developer",
              curator: {
                url: (if $curatorUrl == "" then null else $curatorUrl end),
                token: null
              },
              features: {
                localFirst: $lf,
                provenanceEnabled: $prov,
                codeGraphEnabled: $cg,
                contextEngine: (if $ce == "" then null else $ce end)
              },
              policy: {
                tier: $tier,
                approvalCacheTtlMinutes: 60
              },
              lcm: {
                queryBatchSize: 32,
                promotionThreshold: 5,
                autoDiscoveryInterval: "daily"
              },
              qmd: { collections: [] },
              hosts: {
                openclaw: $openclawHome,
                claudeCode: $claudeHome,
                codex: $codexHome
              }
            }' > "$ENGRAM_CONFIG"
        log_success "Wrote $ENGRAM_CONFIG"
    else
        log_warning "jq not installed — falling back to engram-migrate-config"
        python3 "$PLUGIN_PATH/../bin/engram-migrate-config" --target "$ENGRAM_HOME" || true
    fi
}

update_host_pointers() {
    # Leave a tiny pointer in openclaw.json so OpenClaw still discovers Engram,
    # but the actual config lives in ~/.engram/config.json.
    if [ "$HAS_JQ" != "true" ] || [ ! -f "$GATEWAY_CONFIG" ]; then
        return
    fi
    cp "$GATEWAY_CONFIG" "$GATEWAY_CONFIG.bak.$(date +%s)"
    local tmp
    tmp=$(mktemp)
    jq --arg cfg "$ENGRAM_CONFIG" '
      .plugins.allow = (
        if (.plugins.allow | index("engram")) then .plugins.allow
        else .plugins.allow + ["engram"]
        end
      )
      | .plugins.entries["engram"] = {
          "enabled": true,
          "configRef": $cfg
        }
    ' "$GATEWAY_CONFIG" > "$tmp" && mv "$tmp" "$GATEWAY_CONFIG"
    log_success "Updated openclaw.json to point at $ENGRAM_CONFIG"
}
```

- [ ] **Step 3: Update the call sites**

Find where `update_gateway_config` is called (search the file). Replace with:

```bash
write_engram_config
update_host_pointers
```

- [ ] **Step 4: Patch the lossless-claw / code-graph pokes (lines ~1435 and ~1442)**

Replace each `_run_init_task` line that uses `$GATEWAY_CONFIG` with one that targets `$ENGRAM_CONFIG` and the new flat schema:

```bash
_run_init_task "Lossless-claw config" \
  "tmp=\$(mktemp) && jq '.features.contextEngine = \"lossless-claw\"' '$ENGRAM_CONFIG' > \"\$tmp\" && mv \"\$tmp\" '$ENGRAM_CONFIG'" 5 || true
```

```bash
_run_init_task "Code graph config" \
  "tmp=\$(mktemp) && jq '.features.codeGraphEnabled = true' '$ENGRAM_CONFIG' > \"\$tmp\" && mv \"\$tmp\" '$ENGRAM_CONFIG'" 5 || true
```

- [ ] **Step 5: Update the install summary block (around line 1854)**

Find `echo "  Gateway: $GATEWAY_CONFIG"` and add a sibling line:

```bash
echo "  Engram config: $ENGRAM_CONFIG"
```

- [ ] **Step 6: Shellcheck the modified script**

```bash
shellcheck INSTALL.sh || true
```

Expected: no NEW errors introduced beyond pre-existing ones.

- [ ] **Step 7: Commit**

```bash
git add INSTALL.sh
git commit -m "feat(engram): INSTALL.sh writes ~/.engram/config.json

- Replaces update_gateway_config with write_engram_config that emits
  the new flat schema directly.
- Adds update_host_pointers that leaves a small {configRef} stub in
  openclaw.json so OpenClaw still finds Engram.
- Patches the lossless-claw/code-graph init tasks to target the new
  config path."
```

---

### Task 10: QMD collection registration on init

**Files:**
- Modify: `bin/engram-migrate-config` (add a post-write hook)
- Modify: `INSTALL.sh` (call qmd collection add in init step)

- [ ] **Step 1: Add a `_register_qmd_collections` helper to engram-migrate-config**

After the `migrate()` function, add:

```python
def register_qmd_collections(target: Path) -> list[str]:
    """Register the configured vault as a QMD collection if qmd is on PATH."""
    import shutil, subprocess
    if not shutil.which("qmd"):
        return []
    cfg_path = target / "config.json"
    if not cfg_path.exists():
        return []
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    vault = cfg.get("vaultPath")
    if not vault or not Path(vault).exists():
        return []
    name = "engram-vault"
    try:
        subprocess.run(
            ["qmd", "collection", "add", name, vault],
            check=False,
            capture_output=True,
        )
    except OSError:
        return []
    # Persist the collection name in config.qmd.collections
    qmd = cfg.setdefault("qmd", {})
    cols = qmd.setdefault("collections", [])
    if name not in cols:
        cols.append(name)
        cfg_path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    return [name]
```

Call it from `migrate()` at the end of the non-dry-run path:

```python
result["qmd_collections"] = register_qmd_collections(target)
```

- [ ] **Step 2: Add a tiny test that the registration is a no-op when qmd is missing**

Append to `plugin/lib/tests/test_engram_config_migrate.py`:

```python
def test_register_qmd_collections_no_qmd(fake_openclaw, tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", "")  # hide qmd
    target = tmp_path / "engram"
    result = mig.migrate(source=fake_openclaw, target=target, dry_run=False)
    assert result["qmd_collections"] == []
```

- [ ] **Step 3: Run the migration tests**

Run from repo root: `python -m pytest plugin/lib/tests/test_engram_config_migrate.py -v`
Expected: 6 passed.

- [ ] **Step 4: Commit**

```bash
git add bin/engram-migrate-config plugin/lib/tests/test_engram_config_migrate.py
git commit -m "feat(engram): register vault as QMD collection on migrate

migrate() now calls 'qmd collection add engram-vault <vault>' if qmd
is on PATH and persists the collection name into
config.qmd.collections. No-op when qmd is missing."
```

---

### Task 11: Optional `lcm.db` move with backup safety

**Files:**
- Modify: `bin/engram-migrate-config` (add `--move-lcm` flag)

- [ ] **Step 1: Add a guarded helper**

In `bin/engram-migrate-config`, add:

```python
def move_lcm_db(source: Path, target: Path) -> dict:
    """Move ~/.openclaw/lcm.db to ~/.engram/lcm.db with a pre-flight backup."""
    src_db = source / "lcm.db"
    if not src_db.exists():
        return {"moved": False, "reason": "no_source"}
    target.mkdir(parents=True, exist_ok=True)
    dst_db = target / "lcm.db"
    if dst_db.exists():
        return {"moved": False, "reason": "target_exists", "target": str(dst_db)}
    # Capture the original size BEFORE any copy so the post-copy
    # verification compares to a stable reference, not to the in-flight
    # source which could in theory be touched by another process.
    original_size = src_db.stat().st_size
    backup = src_db.with_suffix(f".db.bak.{int(time.time())}")
    shutil.copy2(src_db, backup)
    shutil.copy2(src_db, dst_db)
    if dst_db.stat().st_size != original_size or backup.stat().st_size != original_size:
        dst_db.unlink(missing_ok=True)
        return {
            "moved": False,
            "reason": "size_mismatch",
            "backup": str(backup),
            "expected": original_size,
        }
    src_db.unlink()
    return {
        "moved": True,
        "from": str(src_db),
        "to": str(dst_db),
        "backup": str(backup),
        "size": original_size,
    }
```

Wire it up behind a `--move-lcm` flag in `main()`:

```python
p.add_argument("--move-lcm", action="store_true", help="Move lcm.db from source to target (with backup)")
```

```python
if args.move_lcm and not args.dry_run:
    result["lcm"] = move_lcm_db(Path(args.source), Path(args.target))
```

- [ ] **Step 2: Test against the sandbox first**

```bash
SANDBOX=$(mktemp -d -t engram-lcm-XXXX)
mkdir -p "$SANDBOX/openclaw"
dd if=/dev/urandom of="$SANDBOX/openclaw/lcm.db" bs=1M count=1
./bin/engram-migrate-config --source "$SANDBOX/openclaw" --target "$SANDBOX/engram" --move-lcm
ls -la "$SANDBOX/engram/lcm.db" "$SANDBOX/openclaw/lcm.db.bak."*
```

Expected: target has the db, source has only the backup file.

- [ ] **Step 3: Decide whether to run on real `~/.openclaw/lcm.db`**

The user has authorized this move (`lcm.db` belongs to lossless-claw, not engram). Run only if the previous task succeeded against the sandbox. Run:

```bash
./bin/engram-migrate-config --move-lcm
```

Expected: prints `"lcm": {"moved": true, ...}`. Verify:

```bash
ls -la ~/.engram/lcm.db ~/.openclaw/lcm.db.bak.*
```

If lossless-claw stops working after this, restore from the backup:

```bash
cp ~/.openclaw/lcm.db.bak.* ~/.openclaw/lcm.db
```

- [ ] **Step 4: Commit**

```bash
git add bin/engram-migrate-config
git commit -m "feat(engram): add --move-lcm flag to migrate

Moves ~/.openclaw/lcm.db -> ~/.engram/lcm.db with a pre-flight
backup, post-copy size verification, and refusal to overwrite an
existing target. Behind a flag — never runs by default."
```

---

### Task 12: User-facing doc + AGENTS.md / CLAUDE.md update

**Files:**
- Create: `docs/engram-config.md`
- Modify: `AGENTS.md` and `CLAUDE.md` (append a short pointer)

- [ ] **Step 1: Write `docs/engram-config.md`**

```markdown
# Engram Config

Engram's configuration lives at `~/.engram/config.json`. This is the single
source of truth for the vault path, mode, curator endpoint, and feature
flags. It is host-agnostic — the same file is used whether you launched
Engram via Claude Code, Codex, or OpenClaw.

## Environment overrides

| Var            | Default       | Purpose                                  |
|----------------|---------------|------------------------------------------|
| `ENGRAM_HOME`  | `~/.engram`   | Where Engram stores config + extensions  |

Setting `ENGRAM_HOME=/tmp/lme-engram` lets you run Engram against an
isolated config without touching the real one — useful for benchmarks
(LongMemEval) and tests.

## Migrating from `~/.openclaw/openclaw.json`

```bash
./bin/engram-migrate-config --dry-run    # preview
./bin/engram-migrate-config              # write ~/.engram/config.json
./bin/engram-migrate-config --move-lcm   # also move lcm.db (with backup)
```

The migration:
- Reads `plugins.entries.engram.config` from `~/.openclaw/openclaw.json`
- Reads `~/.openclaw/config/mode.json` if present
- Writes `~/.engram/config.json` matching the schema in
  `plugin/lib/engram_config.py:DEFAULTS`
- Backs up both source and target before writing
- Is idempotent (re-running produces the same result)

## Schema

See `plugin/lib/engram_config.py` for the canonical defaults and
`plugin/openclaw.plugin.json` `configSchema` for field descriptions.

## Pointing hosts at it

OpenClaw learns about Engram via a tiny pointer in `~/.openclaw/openclaw.json`:

```json
{
  "plugins": {
    "entries": {
      "engram": { "enabled": true, "configRef": "~/.engram/config.json" }
    }
  }
}
```

Claude Code and Codex don't need any host-side config today — they pick up
Engram via its MCP server entry, which reads `~/.engram/config.json`
directly.
```

- [ ] **Step 2: Append a one-liner to AGENTS.md and CLAUDE.md**

In each, after the existing front-matter, add:

```markdown
## Engram config

Engram's config now lives at `~/.engram/config.json`. Use
`./bin/engram-migrate-config` to migrate from `~/.openclaw/openclaw.json`.
See `docs/engram-config.md`.
```

- [ ] **Step 3: Commit**

```bash
git add docs/engram-config.md AGENTS.md CLAUDE.md
git commit -m "docs(engram): document ~/.engram/config.json + ENGRAM_HOME"
```

---

### Task 13: End-to-end verification + LongMemEval isolation smoke test

**Files:**
- No code changes — verification gate before merge.

- [ ] **Step 1: Run the full Python test suite**

```bash
python -m pytest plugin/lib/tests/ -v \
  --ignore=plugin/lib/tests/test_graph_db.py \
  --ignore=plugin/lib/tests/test_calendar_watcher.py
```

Expected: all green. Investigate any new failures before continuing.

- [ ] **Step 2: Run `engram status` against the real config**

```bash
./bin/engram status
```

Expected: Vault row matches `jq -r .vaultPath ~/.engram/config.json`. Mode row matches `jq -r .mode ~/.engram/config.json`.

- [ ] **Step 3: Run `engram status` against an isolated $ENGRAM_HOME**

```bash
ISO=$(mktemp -d -t engram-iso-XXXX)
mkdir -p "$ISO/knowledge"
ENGRAM_HOME="$ISO" ./bin/engram status
```

Expected: Vault row shows `$ISO/knowledge`. Mode `standalone`. Mutations `True`. This proves the isolation we need for LongMemEval.

- [ ] **Step 4: Confirm `~/.openclaw/openclaw.json` engram entry is now a pointer**

```bash
jq '.plugins.entries.engram' ~/.openclaw/openclaw.json
```

Expected: `{"enabled": true, "configRef": "~/.engram/config.json"}` (no nested config block).

If the user has not yet re-run `INSTALL.sh`, the gateway will still hold the legacy nested block — that's fine, the migration script reads it but doesn't rewrite it. Note this in the PR description.

- [ ] **Step 5: gitnexus_detect_changes pre-commit scope check**

Run: `gitnexus_detect_changes({scope: "all"})` (per project CLAUDE.md). Verify only the files in this plan's File Structure are touched.

- [ ] **Step 6: Final commit if anything came up in verification**

```bash
git status
git diff
# Address findings, then:
git add -A
git commit -m "chore(engram): post-verification fixes from config-isolation E2E"
```

- [ ] **Step 7: Hand back to LongMemEval setup**

After this plan lands on `feat/v4.0-business-superintelligence`, the LongMemEval adapter setup can resume by setting `ENGRAM_HOME=~/.engram-lme` for the entire benchmark run — no more leakage into the real Cortex vault.

---

## Out of Scope (deliberately)

- Rewriting `plugin/openclaw.plugin.json` `configSchema` to mirror the new flat shape — keeping the legacy nested keys lets older OpenClaw versions still validate the pointer entry. We'll do this in a follow-up after v4.0 ships.
- Touching `~/.codex` or `~/.claude` config files. They don't currently hold engram config, and adding host-side discovery hooks is its own design problem.
- Renaming `LACP_*` env vars across the rest of the codebase. The `feedback_no_lacp_refs` memory says we shouldn't INTRODUCE new ones — existing references in unrelated modules are left untouched here to keep this plan focused.
- Replacing `bin/engram-context`, `bin/engram-brain-*`, etc. shell wrappers. They already shell out to Python via `~/.openclaw/extensions/engram/lib`; the symlink in Task 7 keeps them working without code changes.

## Risk Notes

- **Lossless-claw uses `~/.openclaw/lcm.db`.** Task 11 moves it. If lossless-claw is hard-coded to that path (likely — we didn't audit it), the move will break LCM until lossless-claw is patched. The pre-flight backup is the escape hatch. Run Task 11 LAST and only after the rest of the plan is verified green.
- **OpenClaw plugin loader may not understand `configRef`.** If the host pointer doesn't work, OpenClaw will fall back to "engram not configured" — the engram CLI itself still works because it reads `~/.engram/config.json` directly. Worst case: temporarily restore the gateway from `openclaw.json.bak.*`.
- **`engram_config._cache` is process-global.** Tests must clear it on every fixture. The fixtures in this plan do that — don't remove the `ec._cache.clear()` lines.
