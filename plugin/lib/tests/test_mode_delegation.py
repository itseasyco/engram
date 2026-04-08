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
