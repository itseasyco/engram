"""Tests for community connector discovery and loading."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pytest

# Allow import from plugin root
PLUGIN_DIR = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PLUGIN_DIR))

from lib.connectors.community import (
    CommunityConnectorError,
    ConnectorManifest,
    DiscoveredConnector,
    discover,
    discover_types,
    load_connector_class,
    COMMUNITY_PACKAGE_PREFIX,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_MANIFEST = {
    "id": "example",
    "type": "example",
    "version": "1.0.0",
    "trust_level": "medium",
    "mode": "pull",
    "required_config": ["api_token"],
    "landing_zone": "queue-human",
    "description": "Test connector",
    "author": "Tester",
    "homepage": "https://example.com",
}

MINIMAL_INDEX_PY = """\
from __future__ import annotations
from typing import Any
try:
    from lib.connectors.base import Connector, ConnectorStatus, RawData, VaultNote
except ImportError:
    from plugin.lib.connectors.base import Connector, ConnectorStatus, RawData, VaultNote

class ExampleConnector(Connector):
    type = "example"
    def authenticate(self) -> bool:
        return True
    def transform(self, raw_data: RawData) -> VaultNote:
        return VaultNote(
            title="T", body="", source_connector=self.id,
            source_type=self.type, source_id=raw_data.source_id,
        )
    def health_check(self) -> ConnectorStatus:
        return self.base_status(healthy=True)
"""


def _make_package_dir(base: Path, connector_type: str, manifest: dict, index_src: str) -> Path:
    """Create a fake installed community connector package directory."""
    pkg_dir = base / f"{COMMUNITY_PACKAGE_PREFIX}{connector_type}"
    pkg_dir.mkdir(parents=True)
    (pkg_dir / "connector.json").write_text(json.dumps(manifest), encoding="utf-8")
    (pkg_dir / "index.py").write_text(index_src, encoding="utf-8")
    return pkg_dir


# ---------------------------------------------------------------------------
# ConnectorManifest
# ---------------------------------------------------------------------------

class TestConnectorManifest:
    def test_from_dict_valid(self):
        m = ConnectorManifest.from_dict(VALID_MANIFEST)
        assert m.id == "example"
        assert m.type == "example"
        assert m.version == "1.0.0"
        assert m.trust_level == "medium"
        assert m.mode == "pull"
        assert m.required_config == ["api_token"]
        assert m.landing_zone == "queue-human"
        assert m.description == "Test connector"

    def test_from_dict_minimal(self):
        data = {
            "id": "min",
            "type": "min",
            "version": "0.1.0",
            "trust_level": "low",
            "mode": "push",
            "required_config": [],
        }
        m = ConnectorManifest.from_dict(data)
        assert m.landing_zone == "queue-human"  # default
        assert m.description == ""

    def test_from_dict_missing_required_field_raises(self):
        data = {k: v for k, v in VALID_MANIFEST.items() if k != "version"}
        with pytest.raises(CommunityConnectorError, match="missing required fields"):
            ConnectorManifest.from_dict(data)

    def test_from_dict_invalid_trust_level_raises(self):
        data = {**VALID_MANIFEST, "trust_level": "super-trusted"}
        with pytest.raises(CommunityConnectorError, match="invalid trust_level"):
            ConnectorManifest.from_dict(data)

    def test_from_dict_invalid_mode_raises(self):
        data = {**VALID_MANIFEST, "mode": "stream"}
        with pytest.raises(CommunityConnectorError, match="invalid mode"):
            ConnectorManifest.from_dict(data)

    def test_from_dict_required_config_not_list_raises(self):
        data = {**VALID_MANIFEST, "required_config": "api_token"}
        with pytest.raises(CommunityConnectorError, match="required_config must be a list"):
            ConnectorManifest.from_dict(data)

    def test_from_dict_extra_fields_captured(self):
        data = {**VALID_MANIFEST, "custom_field": "hello"}
        m = ConnectorManifest.from_dict(data)
        assert m.extra["custom_field"] == "hello"

    def test_from_file_valid(self, tmp_path):
        p = tmp_path / "connector.json"
        p.write_text(json.dumps(VALID_MANIFEST), encoding="utf-8")
        m = ConnectorManifest.from_file(p)
        assert m.type == "example"

    def test_from_file_bad_json_raises(self, tmp_path):
        p = tmp_path / "connector.json"
        p.write_text("{not valid json}", encoding="utf-8")
        with pytest.raises(CommunityConnectorError, match="Failed to read"):
            ConnectorManifest.from_file(p)

    def test_from_file_missing_file_raises(self, tmp_path):
        p = tmp_path / "connector.json"
        with pytest.raises(CommunityConnectorError, match="Failed to read"):
            ConnectorManifest.from_file(p)

    def test_to_dict_round_trips(self):
        m = ConnectorManifest.from_dict(VALID_MANIFEST)
        d = m.to_dict()
        assert d["id"] == "example"
        assert d["trust_level"] == "medium"
        assert d["required_config"] == ["api_token"]

    def test_to_dict_omits_empty_optionals(self):
        data = {
            "id": "bare",
            "type": "bare",
            "version": "1.0.0",
            "trust_level": "high",
            "mode": "pull",
            "required_config": [],
        }
        m = ConnectorManifest.from_dict(data)
        d = m.to_dict()
        assert "description" not in d
        assert "author" not in d
        assert "homepage" not in d


# ---------------------------------------------------------------------------
# discover
# ---------------------------------------------------------------------------

class TestDiscover:
    def test_discover_empty_dir(self, tmp_path):
        result = discover(tmp_path)
        assert result == []

    def test_discover_nonexistent_dir(self, tmp_path):
        result = discover(tmp_path / "does-not-exist")
        assert result == []

    def test_discover_finds_valid_package(self, tmp_path):
        _make_package_dir(tmp_path, "example", VALID_MANIFEST, MINIMAL_INDEX_PY)
        result = discover(tmp_path)
        assert len(result) == 1
        assert result[0].connector_type == "example"
        assert result[0].version == "1.0.0"

    def test_discover_skips_non_connector_dirs(self, tmp_path):
        # A dir that doesn't start with the prefix should be ignored
        (tmp_path / "some-other-package").mkdir()
        result = discover(tmp_path)
        assert result == []

    def test_discover_skips_missing_manifest(self, tmp_path, capsys):
        pkg = tmp_path / f"{COMMUNITY_PACKAGE_PREFIX}no-manifest"
        pkg.mkdir()
        (pkg / "index.py").write_text("# empty\n")
        result = discover(tmp_path)
        assert result == []
        err = capsys.readouterr().err
        assert "no connector.json" in err

    def test_discover_skips_invalid_manifest(self, tmp_path, capsys):
        pkg = tmp_path / f"{COMMUNITY_PACKAGE_PREFIX}bad-manifest"
        pkg.mkdir()
        (pkg / "connector.json").write_text('{"id": "bad"}')  # missing required fields
        result = discover(tmp_path)
        assert result == []
        err = capsys.readouterr().err
        assert "manifest error" in err

    def test_discover_multiple_packages(self, tmp_path):
        for ctype in ("notion", "linear", "jira"):
            manifest = {**VALID_MANIFEST, "id": ctype, "type": ctype}
            _make_package_dir(tmp_path, ctype, manifest, MINIMAL_INDEX_PY)
        result = discover(tmp_path)
        assert len(result) == 3
        types = {dc.connector_type for dc in result}
        assert types == {"notion", "linear", "jira"}

    def test_discover_returns_sorted_by_name(self, tmp_path):
        for ctype in ("zzz", "aaa", "mmm"):
            manifest = {**VALID_MANIFEST, "id": ctype, "type": ctype}
            _make_package_dir(tmp_path, ctype, manifest, MINIMAL_INDEX_PY)
        result = discover(tmp_path)
        names = [dc.connector_type for dc in result]
        assert names == sorted(names)


# ---------------------------------------------------------------------------
# discover_types
# ---------------------------------------------------------------------------

class TestDiscoverTypes:
    def test_discover_types_returns_dicts(self, tmp_path):
        _make_package_dir(tmp_path, "notion", {**VALID_MANIFEST, "id": "notion", "type": "notion"}, MINIMAL_INDEX_PY)
        result = discover_types(tmp_path)
        assert len(result) == 1
        assert result[0]["type"] == "notion"
        assert result[0]["tier"] == "community"
        assert "version" in result[0]

    def test_discover_types_empty(self, tmp_path):
        assert discover_types(tmp_path) == []


# ---------------------------------------------------------------------------
# DiscoveredConnector.load_class
# ---------------------------------------------------------------------------

class TestDiscoveredConnectorLoadClass:
    def test_load_class_returns_connector_subclass(self, tmp_path):
        pkg_dir = _make_package_dir(tmp_path, "example", VALID_MANIFEST, MINIMAL_INDEX_PY)
        manifest = ConnectorManifest.from_dict(VALID_MANIFEST)
        dc = DiscoveredConnector(manifest=manifest, package_dir=pkg_dir)
        cls = dc.load_class()
        assert cls is not None
        assert cls.__name__ == "ExampleConnector"

    def test_load_class_cached_on_second_call(self, tmp_path):
        pkg_dir = _make_package_dir(tmp_path, "example", VALID_MANIFEST, MINIMAL_INDEX_PY)
        manifest = ConnectorManifest.from_dict(VALID_MANIFEST)
        dc = DiscoveredConnector(manifest=manifest, package_dir=pkg_dir)
        cls1 = dc.load_class()
        cls2 = dc.load_class()
        assert cls1 is cls2

    def test_load_class_missing_index_raises(self, tmp_path):
        pkg_dir = tmp_path / f"{COMMUNITY_PACKAGE_PREFIX}no-index"
        pkg_dir.mkdir()
        (pkg_dir / "connector.json").write_text(json.dumps(VALID_MANIFEST))
        manifest = ConnectorManifest.from_dict(VALID_MANIFEST)
        dc = DiscoveredConnector(manifest=manifest, package_dir=pkg_dir)
        with pytest.raises(CommunityConnectorError, match="missing index.py"):
            dc.load_class()

    def test_load_class_fallback_to_any_connector_subclass(self, tmp_path):
        # Class is named differently from expected convention
        alt_index = MINIMAL_INDEX_PY.replace("ExampleConnector", "MyWeirdConnector")
        pkg_dir = _make_package_dir(tmp_path, "example", VALID_MANIFEST, alt_index)
        manifest = ConnectorManifest.from_dict(VALID_MANIFEST)
        dc = DiscoveredConnector(manifest=manifest, package_dir=pkg_dir)
        cls = dc.load_class()
        assert cls.__name__ == "MyWeirdConnector"

    def test_load_class_no_connector_subclass_raises(self, tmp_path):
        bad_index = "class NotAConnector: pass\n"
        pkg_dir = _make_package_dir(tmp_path, "example", VALID_MANIFEST, bad_index)
        manifest = ConnectorManifest.from_dict(VALID_MANIFEST)
        dc = DiscoveredConnector(manifest=manifest, package_dir=pkg_dir)
        with pytest.raises(CommunityConnectorError, match="No Connector subclass found"):
            dc.load_class()

    def test_loaded_class_is_instantiable(self, tmp_path):
        pkg_dir = _make_package_dir(tmp_path, "example", VALID_MANIFEST, MINIMAL_INDEX_PY)
        manifest = ConnectorManifest.from_dict(VALID_MANIFEST)
        dc = DiscoveredConnector(manifest=manifest, package_dir=pkg_dir)
        cls = dc.load_class()
        instance = cls({"id": "test", "type": "example", "config": {"api_token": "tok"}})
        assert instance.authenticate() is True


# ---------------------------------------------------------------------------
# load_connector_class (top-level convenience function)
# ---------------------------------------------------------------------------

class TestLoadConnectorClass:
    def test_loads_installed_type(self, tmp_path):
        _make_package_dir(tmp_path, "example", VALID_MANIFEST, MINIMAL_INDEX_PY)
        cls = load_connector_class("example", tmp_path)
        assert cls.__name__ == "ExampleConnector"

    def test_raises_for_uninstalled_type(self, tmp_path):
        with pytest.raises(CommunityConnectorError, match="not installed"):
            load_connector_class("nonexistent", tmp_path)

    def test_raises_for_bad_manifest(self, tmp_path):
        pkg_dir = tmp_path / f"{COMMUNITY_PACKAGE_PREFIX}broken"
        pkg_dir.mkdir()
        (pkg_dir / "connector.json").write_text("{bad json}")
        with pytest.raises(CommunityConnectorError):
            load_connector_class("broken", tmp_path)
