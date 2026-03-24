"""Tests for plugin.lib.sync_daemon -- ob sync daemon management.

Note: These tests verify the code paths and generated configs without
actually starting/stopping system daemons. Integration tests require
a real ob binary and are run separately.
"""

import platform
import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from lib.sync_daemon import (
    DAEMON_LABEL,
    SYSTEMD_UNIT,
    DaemonStatus,
    _detect_platform,
    _generate_plist,
    _generate_unit,
    _plist_path,
    _unit_path,
)


class TestDetectPlatform:
    def test_darwin(self, monkeypatch):
        monkeypatch.setattr(platform, "system", lambda: "Darwin")
        plat, method = _detect_platform()
        assert plat == "macos"
        assert method == "launchd"

    def test_linux(self, monkeypatch):
        monkeypatch.setattr(platform, "system", lambda: "Linux")
        plat, method = _detect_platform()
        assert plat == "linux"
        assert method == "systemd"

    def test_unsupported(self, monkeypatch):
        monkeypatch.setattr(platform, "system", lambda: "Windows")
        plat, method = _detect_platform()
        assert plat == "unsupported"
        assert method == "none"


class TestGeneratePlist:
    def test_plist_contains_label(self):
        plist = _generate_plist("/path/to/vault")
        assert DAEMON_LABEL in plist
        assert "/path/to/vault" in plist
        assert "sync" in plist
        assert "--continuous" in plist

    def test_plist_is_valid_xml(self):
        plist = _generate_plist("/vault")
        assert plist.startswith("<?xml")
        assert "</plist>" in plist


class TestGenerateUnit:
    def test_unit_contains_service(self):
        unit = _generate_unit("/path/to/vault")
        assert "[Service]" in unit
        assert "/path/to/vault" in unit
        assert "sync --continuous" in unit
        assert "Restart=always" in unit


class TestDaemonStatus:
    def test_status_to_dict(self):
        s = DaemonStatus(running=True, pid=1234, platform="macos", method="launchd", message="ok")
        d = s.to_dict()
        assert d["running"] is True
        assert d["pid"] == 1234
        assert d["platform"] == "macos"
