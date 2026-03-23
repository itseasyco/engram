"""Tests for connector registry."""

import json
import tempfile
from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from lib.connectors.registry import ConnectorRegistry, ConnectorLoadError
from lib.connectors.base import Connector, ConnectorStatus, RawData, VaultNote


class TestRegistryLoadConfig:
    def test_load_empty_config(self, tmp_path):
        cfg_file = tmp_path / "connectors.json"
        cfg_file.write_text('{"connectors": []}')
        reg = ConnectorRegistry(config_path=cfg_file)
        config = reg.load_config()
        assert config["connectors"] == []

    def test_load_missing_config(self, tmp_path):
        reg = ConnectorRegistry(config_path=tmp_path / "nonexistent.json")
        config = reg.load_config()
        assert config["connectors"] == []

    def test_load_bad_json_raises(self, tmp_path):
        cfg_file = tmp_path / "connectors.json"
        cfg_file.write_text("not json{{{")
        reg = ConnectorRegistry(config_path=cfg_file)
        with pytest.raises(ConnectorLoadError):
            reg.load_config()


class TestRegistryAddRemove:
    def test_add_connector_entry(self, tmp_path):
        cfg_file = tmp_path / "connectors.json"
        cfg_file.write_text('{"connectors": []}')
        reg = ConnectorRegistry(config_path=cfg_file)
        reg.load_config()
        reg.add_connector({
            "id": "test-webhook",
            "type": "webhook",
            "config": {},
        })
        # Re-read from disk
        saved = json.loads(cfg_file.read_text())
        assert len(saved["connectors"]) == 1
        assert saved["connectors"][0]["id"] == "test-webhook"

    def test_add_duplicate_raises(self, tmp_path):
        cfg_file = tmp_path / "connectors.json"
        cfg_file.write_text('{"connectors": [{"id": "dupe", "type": "webhook"}]}')
        reg = ConnectorRegistry(config_path=cfg_file)
        reg.load_config()
        with pytest.raises(ValueError, match="already exists"):
            reg.add_connector({"id": "dupe", "type": "webhook"})

    def test_remove_connector(self, tmp_path):
        cfg_file = tmp_path / "connectors.json"
        cfg_file.write_text(json.dumps({
            "connectors": [
                {"id": "keep", "type": "webhook"},
                {"id": "remove-me", "type": "filesystem"},
            ]
        }))
        reg = ConnectorRegistry(config_path=cfg_file)
        reg.load_config()
        assert reg.remove_connector("remove-me") is True
        saved = json.loads(cfg_file.read_text())
        assert len(saved["connectors"]) == 1
        assert saved["connectors"][0]["id"] == "keep"

    def test_remove_nonexistent_returns_false(self, tmp_path):
        cfg_file = tmp_path / "connectors.json"
        cfg_file.write_text('{"connectors": []}')
        reg = ConnectorRegistry(config_path=cfg_file)
        reg.load_config()
        assert reg.remove_connector("ghost") is False


class TestRegistryStatusAll:
    def test_status_empty_registry(self, tmp_path):
        cfg_file = tmp_path / "connectors.json"
        cfg_file.write_text('{"connectors": []}')
        reg = ConnectorRegistry(config_path=cfg_file)
        reg.load_config()
        assert reg.status_all() == []
