"""Tests for the openclaw -> engram config migration."""
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "bin"))
sys.path.insert(0, str(REPO_ROOT / "plugin" / "lib"))

import importlib.util
from importlib.machinery import SourceFileLoader
_loader = SourceFileLoader(
    "engram_migrate_config",
    str(REPO_ROOT / "bin" / "engram-migrate-config"),
)
spec = importlib.util.spec_from_loader("engram_migrate_config", _loader)
mig = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mig)

import engram_config as ec


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
