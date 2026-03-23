#!/usr/bin/env python3
"""
Mode configuration for openclaw-lacp-fusion.

Three operating modes:
  - standalone: local vault, all commands active (default)
  - connected: synced vault, mutations blocked, inbox writes only
  - curator: canonical vault, runs consolidation, connectors, HTTP surface

Mode is determined by (in priority order):
  1. LACP_MODE environment variable
  2. ~/.openclaw/config/mode.json file
  3. Default: "standalone"
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

VALID_MODES = ("standalone", "connected", "curator")

# Commands that mutate the vault graph (blocked in connected mode)
MUTATION_COMMANDS = frozenset({
    "brain-expand",
    "brain-resolve",
    "obsidian-optimize",
})

# Commands that are redirected to inbox in connected mode (not blocked)
INBOX_REDIRECT_COMMANDS = frozenset({
    "brain-ingest",
})


@dataclass(frozen=True)
class ModeConfig:
    """Immutable snapshot of the current mode configuration."""
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


def _config_path() -> Path:
    """Return path to mode.json config file."""
    openclaw_home = os.environ.get("OPENCLAW_HOME", os.path.expanduser("~/.openclaw"))
    return Path(openclaw_home) / "config" / "mode.json"


def _read_config_file() -> dict:
    """Read mode.json, return empty dict if missing or malformed."""
    path = _config_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _write_config_file(data: dict) -> Path:
    """Write mode.json, creating parent directories if needed."""
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path


def get_mode() -> str:
    """Return the current operating mode string."""
    env_mode = os.environ.get("LACP_MODE", "").strip().lower()
    if env_mode in VALID_MODES:
        return env_mode
    config = _read_config_file()
    file_mode = config.get("mode", "").strip().lower()
    if file_mode in VALID_MODES:
        return file_mode
    return "standalone"


def get_config() -> ModeConfig:
    """Return a full ModeConfig snapshot from env + config file."""
    config = _read_config_file()
    mode = get_mode()

    curator_url = os.environ.get(
        "LACP_CURATOR_URL",
        config.get("curator_url", ""),
    )
    curator_token = os.environ.get(
        "LACP_CURATOR_TOKEN",
        config.get("curator_token", ""),
    )
    mutations_enabled_env = os.environ.get("LACP_MUTATIONS_ENABLED", "").strip().lower()
    if mutations_enabled_env in ("true", "false"):
        mutations_enabled = mutations_enabled_env == "true"
    else:
        mutations_enabled = config.get("mutations_enabled", mode != "connected")

    vault_path = os.environ.get(
        "LACP_OBSIDIAN_VAULT",
        os.environ.get(
            "OPENCLAW_VAULT",
            config.get("vault_path", ""),
        ),
    )
    if not vault_path:
        openclaw_home = os.environ.get("OPENCLAW_HOME", os.path.expanduser("~/.openclaw"))
        vault_path = os.path.join(openclaw_home, "data", "knowledge")

    agent_role = os.environ.get(
        "LACP_AGENT_ROLE",
        config.get("agent_role", "developer"),
    )

    return ModeConfig(
        mode=mode,
        curator_url=curator_url,
        curator_token=curator_token,
        mutations_enabled=mutations_enabled,
        vault_path=vault_path,
        agent_role=agent_role,
    )


def set_mode(
    mode: str,
    *,
    curator_url: Optional[str] = None,
    curator_token: Optional[str] = None,
    vault_path: Optional[str] = None,
    agent_role: Optional[str] = None,
) -> Path:
    """Persist mode configuration to mode.json. Returns the config file path."""
    if mode not in VALID_MODES:
        raise ValueError(f"Invalid mode: {mode!r}. Must be one of {VALID_MODES}")

    config = _read_config_file()
    config["mode"] = mode
    config["mutations_enabled"] = mode != "connected"

    if curator_url is not None:
        config["curator_url"] = curator_url
    if curator_token is not None:
        config["curator_token"] = curator_token
    if vault_path is not None:
        config["vault_path"] = vault_path
    if agent_role is not None:
        config["agent_role"] = agent_role

    return _write_config_file(config)


def is_standalone() -> bool:
    """Return True if running in standalone mode."""
    return get_mode() == "standalone"


def is_connected() -> bool:
    """Return True if running in connected mode."""
    return get_mode() == "connected"


def is_curator() -> bool:
    """Return True if running in curator mode."""
    return get_mode() == "curator"


def check_mutation_allowed(command_name: str) -> tuple[bool, str]:
    """
    Check if a mutation command is allowed in the current mode.

    Returns (allowed, reason). If not allowed, reason explains why.
    """
    config = get_config()

    if config.mode == "standalone":
        return True, ""

    if config.mode == "curator":
        return True, ""

    # Connected mode
    if command_name in MUTATION_COMMANDS:
        return False, (
            f"{command_name} is blocked in connected mode. "
            f"Vault mutations are managed by the curator at {config.curator_url}."
        )

    if command_name in INBOX_REDIRECT_COMMANDS:
        return True, "redirected_to_inbox"

    return True, ""


def get_inbox_queue_path(agent_id: str = "") -> str:
    """
    Return the inbox queue path for the current agent in connected mode.
    Falls back to 'queue-agent' if no agent_id provided.
    """
    config = get_config()
    queue_name = f"queue-{agent_id}" if agent_id else "queue-agent"
    return os.path.join(config.vault_path, "05_Inbox", queue_name)
