"""Tests for engram_config — single source of truth for Engram config."""

import json
import os
import sys
from pathlib import Path

import pytest

# Make plugin/lib importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import engram_config as ec


@pytest.fixture(autouse=True)
def _clear_engram_config_cache():
    """Ensure every test starts with a clean engram_config cache."""
    ec._cache.clear()
    yield
    ec._cache.clear()


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
    cfg = ec.load()
    assert cfg.vault_path == "/Volumes/Cortex"


def test_engram_home_overrides_default(tmp_path, monkeypatch):
    monkeypatch.setenv("ENGRAM_HOME", str(tmp_path / "alt"))
    cfg = ec.load()
    assert cfg.engram_home == tmp_path / "alt"
    assert cfg.vault_path == str(tmp_path / "alt" / "knowledge")


def test_save_then_load_round_trip(isolated_home):
    cfg = ec.load()
    written = ec.save({"vaultPath": "/tmp/test-vault", "mode": "curator"})
    assert written.exists()
    cfg2 = ec.load()
    assert cfg2.vault_path == "/tmp/test-vault"
    assert cfg2.mode == "curator"


def test_invalid_mode_raises(isolated_home):
    with pytest.raises(ValueError):
        ec.save({"mode": "bogus"})


def test_save_creates_parent_dirs(tmp_path, monkeypatch):
    target = tmp_path / "deep" / "nested" / "engram"
    monkeypatch.setenv("ENGRAM_HOME", str(target))
    ec.save({"vaultPath": "/x"})
    assert (target / "config.json").exists()


def test_no_lacp_env_vars_referenced(isolated_home, monkeypatch):
    """Regression: engram_config must not honor any LACP_* env var."""
    monkeypatch.setenv("LACP_OBSIDIAN_VAULT", "/should/be/ignored")
    monkeypatch.setenv("LACP_MODE", "curator")
    cfg = ec.load()
    assert "/should/be/ignored" not in cfg.vault_path
    assert cfg.mode == "standalone"


def test_deep_merge_preserves_default_siblings(isolated_home):
    """User config overriding one feature key should NOT drop sibling defaults."""
    (isolated_home / "config.json").write_text(
        json.dumps({"features": {"contextEngine": "custom-engine"}})
    )
    cfg = ec.load()
    assert cfg.features["contextEngine"] == "custom-engine"
    # Siblings from DEFAULTS must survive the merge
    assert cfg.features["localFirst"] is True
    assert cfg.features["provenanceEnabled"] is True
    assert cfg.features["codeGraphEnabled"] is True


def test_legacy_flat_alias_obsidian_vault(isolated_home):
    """Legacy obsidianVault flat key should be aliased to vaultPath."""
    (isolated_home / "config.json").write_text(
        json.dumps({"obsidianVault": "/Volumes/Legacy"})
    )
    cfg = ec.load()
    assert cfg.vault_path == "/Volumes/Legacy"


def test_legacy_nested_alias_context_engine(isolated_home):
    """Legacy contextEngine flat key should be aliased to features.contextEngine."""
    (isolated_home / "config.json").write_text(
        json.dumps({"contextEngine": "legacy-engine", "policyTier": "strict"})
    )
    cfg = ec.load()
    assert cfg.features["contextEngine"] == "legacy-engine"
    assert cfg.policy["tier"] == "strict"


def test_canonical_key_wins_over_legacy_alias(isolated_home):
    """When both the legacy key and the canonical key exist, canonical wins."""
    (isolated_home / "config.json").write_text(
        json.dumps({
            "obsidianVault": "/Volumes/Legacy",
            "vaultPath": "/Volumes/Canonical",
        })
    )
    cfg = ec.load()
    assert cfg.vault_path == "/Volumes/Canonical"


def test_save_backs_up_malformed_existing_file(isolated_home, capsys):
    cfg_path = isolated_home / "config.json"
    cfg_path.write_text("{ this is not valid json ")
    ec.save({"vaultPath": "/new"})
    # Original bad file preserved as a .corrupt.* backup
    backups = list(isolated_home.glob("config.json.corrupt.*"))
    assert len(backups) == 1
    # New file is valid
    new_cfg = json.loads(cfg_path.read_text())
    assert new_cfg["vaultPath"] == "/new"
    # Warning was emitted to stderr
    captured = capsys.readouterr()
    assert "backed up malformed config" in captured.err


def test_load_propagates_os_error_on_unreadable_file(isolated_home):
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        pytest.skip("root can read any file")
    import stat
    cfg_path = isolated_home / "config.json"
    cfg_path.write_text('{"vaultPath": "/ok"}')
    os.chmod(cfg_path, 0)
    try:
        with pytest.raises(PermissionError):
            ec.load()
    finally:
        os.chmod(cfg_path, stat.S_IRUSR | stat.S_IWUSR)


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
