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
