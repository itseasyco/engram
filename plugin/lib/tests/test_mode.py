"""Tests for plugin.lib.mode -- operating mode configuration."""

import json
import os
from pathlib import Path
from unittest import mock

import pytest

# Ensure plugin/lib is importable
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from lib.mode import (
    VALID_MODES,
    MUTATION_COMMANDS,
    INBOX_REDIRECT_COMMANDS,
    ModeConfig,
    get_mode,
    get_config,
    set_mode,
    is_standalone,
    is_connected,
    is_curator,
    check_mutation_allowed,
    get_inbox_queue_path,
    _config_path,
)


class TestGetMode:
    def test_default_is_standalone(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OPENCLAW_HOME", str(tmp_path))
        monkeypatch.delenv("LACP_MODE", raising=False)
        assert get_mode() == "standalone"

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("LACP_MODE", "connected")
        assert get_mode() == "connected"

    def test_env_curator(self, monkeypatch):
        monkeypatch.setenv("LACP_MODE", "curator")
        assert get_mode() == "curator"

    def test_invalid_env_falls_through(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OPENCLAW_HOME", str(tmp_path))
        monkeypatch.setenv("LACP_MODE", "bogus")
        assert get_mode() == "standalone"

    def test_config_file_mode(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OPENCLAW_HOME", str(tmp_path))
        monkeypatch.delenv("LACP_MODE", raising=False)
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "mode.json").write_text('{"mode": "connected"}')
        assert get_mode() == "connected"

    def test_env_takes_priority_over_file(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OPENCLAW_HOME", str(tmp_path))
        monkeypatch.setenv("LACP_MODE", "curator")
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "mode.json").write_text('{"mode": "connected"}')
        assert get_mode() == "curator"


class TestSetMode:
    def test_set_mode_writes_file(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OPENCLAW_HOME", str(tmp_path))
        monkeypatch.delenv("LACP_MODE", raising=False)
        path = set_mode("connected", curator_url="http://localhost:9100")
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["mode"] == "connected"
        assert data["curator_url"] == "http://localhost:9100"
        assert data["mutations_enabled"] is False

    def test_set_mode_curator_enables_mutations(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OPENCLAW_HOME", str(tmp_path))
        path = set_mode("curator")
        data = json.loads(path.read_text())
        assert data["mutations_enabled"] is True

    def test_set_mode_invalid_raises(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OPENCLAW_HOME", str(tmp_path))
        with pytest.raises(ValueError, match="Invalid mode"):
            set_mode("bogus")


class TestHelpers:
    def test_is_standalone(self, monkeypatch):
        monkeypatch.setenv("LACP_MODE", "standalone")
        assert is_standalone() is True
        assert is_connected() is False
        assert is_curator() is False

    def test_is_connected(self, monkeypatch):
        monkeypatch.setenv("LACP_MODE", "connected")
        assert is_connected() is True
        assert is_standalone() is False

    def test_is_curator(self, monkeypatch):
        monkeypatch.setenv("LACP_MODE", "curator")
        assert is_curator() is True


class TestCheckMutationAllowed:
    def test_standalone_allows_all(self, monkeypatch, tmp_path):
        monkeypatch.setenv("LACP_MODE", "standalone")
        monkeypatch.setenv("OPENCLAW_HOME", str(tmp_path))
        for cmd in MUTATION_COMMANDS:
            allowed, reason = check_mutation_allowed(cmd)
            assert allowed is True

    def test_connected_blocks_mutations(self, monkeypatch, tmp_path):
        monkeypatch.setenv("LACP_MODE", "connected")
        monkeypatch.setenv("OPENCLAW_HOME", str(tmp_path))
        for cmd in MUTATION_COMMANDS:
            allowed, reason = check_mutation_allowed(cmd)
            assert allowed is False
            assert "blocked" in reason

    def test_connected_redirects_ingest(self, monkeypatch, tmp_path):
        monkeypatch.setenv("LACP_MODE", "connected")
        monkeypatch.setenv("OPENCLAW_HOME", str(tmp_path))
        allowed, reason = check_mutation_allowed("brain-ingest")
        assert allowed is True
        assert reason == "redirected_to_inbox"

    def test_curator_allows_all(self, monkeypatch, tmp_path):
        monkeypatch.setenv("LACP_MODE", "curator")
        monkeypatch.setenv("OPENCLAW_HOME", str(tmp_path))
        for cmd in MUTATION_COMMANDS:
            allowed, reason = check_mutation_allowed(cmd)
            assert allowed is True


class TestGetConfig:
    def test_full_config_from_file(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OPENCLAW_HOME", str(tmp_path))
        monkeypatch.delenv("LACP_MODE", raising=False)
        monkeypatch.delenv("LACP_CURATOR_URL", raising=False)
        monkeypatch.delenv("LACP_CURATOR_TOKEN", raising=False)
        monkeypatch.delenv("LACP_OBSIDIAN_VAULT", raising=False)
        monkeypatch.delenv("OPENCLAW_VAULT", raising=False)
        monkeypatch.delenv("LACP_MUTATIONS_ENABLED", raising=False)
        monkeypatch.delenv("LACP_AGENT_ROLE", raising=False)
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "mode.json").write_text(json.dumps({
            "mode": "connected",
            "curator_url": "http://curator:9100",
            "curator_token": "tok_abc",
            "vault_path": "/shared/vault",
            "agent_role": "pm",
        }))
        cfg = get_config()
        assert cfg.mode == "connected"
        assert cfg.curator_url == "http://curator:9100"
        assert cfg.curator_token == "tok_abc"
        assert cfg.mutations_enabled is False
        assert cfg.vault_path == "/shared/vault"
        assert cfg.agent_role == "pm"
