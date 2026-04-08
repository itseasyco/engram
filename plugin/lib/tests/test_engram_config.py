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
