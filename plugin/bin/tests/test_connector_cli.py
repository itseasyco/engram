"""Tests for the openclaw-connector CLI."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Resolve paths so we can import from plugin/lib without install
PLUGIN_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PLUGIN_DIR))

# We import the CLI module functions directly rather than invoking as subprocess
# so tests remain fast and do not depend on registry/connectors being installed.
# The registry is mocked for all tests that exercise command dispatch.

CLI_PATH = PLUGIN_DIR / "bin" / "openclaw-connector"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_registry(connectors: list[dict] | None = None):
    """Build a mock ConnectorRegistry pre-loaded with a config."""
    reg = MagicMock()
    reg._config = {"connectors": connectors or []}
    reg.config_path = Path("/tmp/test-connectors.json")
    reg.list_available_types.return_value = [
        {"type": "filesystem", "tier": "native"},
        {"type": "webhook", "tier": "native"},
        {"type": "github", "tier": "first-party"},
        {"type": "my-plugin", "tier": "community"},
    ]
    reg.load_all.return_value = []
    reg.start_all.return_value = []
    reg.status_all.return_value = []
    reg.pull_all.return_value = []
    return reg


# ---------------------------------------------------------------------------
# CLI is executable
# ---------------------------------------------------------------------------

class TestCLIExecutable:
    def test_cli_file_exists(self):
        assert CLI_PATH.exists(), f"CLI not found at {CLI_PATH}"

    def test_cli_is_executable(self):
        assert os.access(CLI_PATH, os.X_OK), f"CLI is not executable: {CLI_PATH}"

    def test_cli_has_python_shebang(self):
        first_line = CLI_PATH.read_text(encoding="utf-8").splitlines()[0]
        assert first_line.startswith("#!/usr/bin/env python"), (
            f"Expected Python shebang, got: {first_line!r}"
        )


# ---------------------------------------------------------------------------
# cmd_list
# ---------------------------------------------------------------------------

class TestCmdList:
    def test_list_no_connectors(self, capsys):
        from bin.openclaw_connector import cmd_list  # type: ignore[import]
        reg = _make_registry([])
        cmd_list(MagicMock(), reg)
        out = capsys.readouterr().out
        assert "No connectors configured" in out

    def test_list_shows_connectors(self, capsys):
        from bin.openclaw_connector import cmd_list  # type: ignore[import]
        reg = _make_registry([
            {
                "id": "watch-inbox",
                "type": "filesystem",
                "enabled": True,
                "trust_level": "high",
                "mode": "pull",
                "landing_zone": "queue-agent",
            }
        ])
        cmd_list(MagicMock(), reg)
        out = capsys.readouterr().out
        assert "watch-inbox" in out
        assert "filesystem" in out
        assert "high" in out
        assert "queue-agent" in out

    def test_list_shows_total_count(self, capsys):
        from bin.openclaw_connector import cmd_list  # type: ignore[import]
        connectors = [
            {"id": f"c{i}", "type": "webhook", "enabled": True,
             "trust_level": "medium", "mode": "push", "landing_zone": "queue-human"}
            for i in range(3)
        ]
        reg = _make_registry(connectors)
        cmd_list(MagicMock(), reg)
        out = capsys.readouterr().out
        assert "3 connector(s)" in out


# ---------------------------------------------------------------------------
# cmd_types
# ---------------------------------------------------------------------------

class TestCmdTypes:
    def test_types_shows_all_tiers(self, capsys):
        from bin.openclaw_connector import cmd_types  # type: ignore[import]
        reg = _make_registry()
        cmd_types(MagicMock(), reg)
        out = capsys.readouterr().out
        assert "native" in out
        assert "first-party" in out
        assert "community" in out
        assert "filesystem" in out
        assert "github" in out
        assert "my-plugin" in out


# ---------------------------------------------------------------------------
# cmd_add
# ---------------------------------------------------------------------------

class TestCmdAdd:
    def test_add_calls_registry(self, capsys):
        from bin.openclaw_connector import cmd_add  # type: ignore[import]
        reg = _make_registry()
        reg.add_connector.return_value = None

        args = MagicMock()
        args.id = "my-fs"
        args.type = "filesystem"
        args.trust = "high"
        args.mode = "pull"
        args.zone = "queue-agent"
        args.set = ["watch_path=/tmp/inbox"]

        cmd_add(args, reg)
        reg.add_connector.assert_called_once()
        call_arg = reg.add_connector.call_args[0][0]
        assert call_arg["id"] == "my-fs"
        assert call_arg["type"] == "filesystem"
        assert call_arg["trust_level"] == "high"
        assert call_arg["config"]["watch_path"] == "/tmp/inbox"

        out = capsys.readouterr().out
        assert "Added connector: my-fs" in out

    def test_add_json_config_value(self, capsys):
        from bin.openclaw_connector import cmd_add  # type: ignore[import]
        reg = _make_registry()
        reg.add_connector.return_value = None

        args = MagicMock()
        args.id = "json-conn"
        args.type = "webhook"
        args.trust = None
        args.mode = None
        args.zone = None
        args.set = ['extensions=["md","txt"]']

        cmd_add(args, reg)
        call_arg = reg.add_connector.call_args[0][0]
        assert call_arg["config"]["extensions"] == ["md", "txt"]

    def test_add_exits_on_duplicate(self):
        from bin.openclaw_connector import cmd_add  # type: ignore[import]
        reg = _make_registry()
        reg.add_connector.side_effect = ValueError("Connector 'dup' already exists")

        args = MagicMock()
        args.id = "dup"
        args.type = "filesystem"
        args.trust = None
        args.mode = None
        args.zone = None
        args.set = None

        with pytest.raises(SystemExit) as exc:
            cmd_add(args, reg)
        assert exc.value.code == 1


# ---------------------------------------------------------------------------
# cmd_remove
# ---------------------------------------------------------------------------

class TestCmdRemove:
    def test_remove_success(self, capsys):
        from bin.openclaw_connector import cmd_remove  # type: ignore[import]
        reg = _make_registry()
        reg.remove_connector.return_value = True

        args = MagicMock()
        args.id = "old-conn"

        cmd_remove(args, reg)
        out = capsys.readouterr().out
        assert "Removed connector: old-conn" in out

    def test_remove_not_found_exits(self):
        from bin.openclaw_connector import cmd_remove  # type: ignore[import]
        reg = _make_registry()
        reg.remove_connector.return_value = False

        args = MagicMock()
        args.id = "nonexistent"

        with pytest.raises(SystemExit) as exc:
            cmd_remove(args, reg)
        assert exc.value.code == 1


# ---------------------------------------------------------------------------
# cmd_test
# ---------------------------------------------------------------------------

class TestCmdTest:
    def test_test_connector_ok(self, capsys):
        from bin.openclaw_connector import cmd_test  # type: ignore[import]
        reg = _make_registry()
        conn = MagicMock()
        conn.type = "filesystem"
        conn.mode = "pull"
        conn.authenticate.return_value = True
        conn.pull.return_value = []
        conn.health_check.return_value = MagicMock(healthy=True)
        reg.get.return_value = conn

        args = MagicMock()
        args.id = "my-conn"

        cmd_test(args, reg)
        out = capsys.readouterr().out
        assert "Authentication successful" in out

    def test_test_connector_not_found_exits(self):
        from bin.openclaw_connector import cmd_test  # type: ignore[import]
        reg = _make_registry()
        reg.get.return_value = None

        args = MagicMock()
        args.id = "missing"

        with pytest.raises(SystemExit) as exc:
            cmd_test(args, reg)
        assert exc.value.code == 1

    def test_test_auth_failure_exits(self):
        from bin.openclaw_connector import cmd_test  # type: ignore[import]
        reg = _make_registry()
        conn = MagicMock()
        conn.type = "webhook"
        conn.mode = "push"
        conn.authenticate.return_value = False
        reg.get.return_value = conn

        args = MagicMock()
        args.id = "bad-conn"

        with pytest.raises(SystemExit) as exc:
            cmd_test(args, reg)
        assert exc.value.code == 1


# ---------------------------------------------------------------------------
# cmd_status
# ---------------------------------------------------------------------------

class TestCmdStatus:
    def test_status_no_connectors(self, capsys):
        from bin.openclaw_connector import cmd_status  # type: ignore[import]
        reg = _make_registry()
        reg.status_all.return_value = []

        cmd_status(MagicMock(), reg)
        out = capsys.readouterr().out
        assert "No connectors loaded" in out

    def test_status_shows_connector_info(self, capsys):
        from bin.openclaw_connector import cmd_status  # type: ignore[import]
        reg = _make_registry()
        reg.status_all.return_value = [
            {
                "healthy": True,
                "connector_id": "my-conn",
                "connector_type": "filesystem",
                "notes_ingested": 42,
                "error_count": 0,
                "last_pull_time": "2026-03-22T00:00:00Z",
                "last_error": None,
            }
        ]

        cmd_status(MagicMock(), reg)
        out = capsys.readouterr().out
        assert "my-conn" in out
        assert "filesystem" in out
        assert "42" in out

    def test_status_shows_last_error(self, capsys):
        from bin.openclaw_connector import cmd_status  # type: ignore[import]
        reg = _make_registry()
        reg.status_all.return_value = [
            {
                "healthy": False,
                "connector_id": "broken",
                "connector_type": "github",
                "notes_ingested": 0,
                "error_count": 3,
                "last_pull_time": None,
                "last_error": "connection refused",
            }
        ]

        cmd_status(MagicMock(), reg)
        out = capsys.readouterr().out
        assert "broken" in out
        assert "connection refused" in out


# ---------------------------------------------------------------------------
# cmd_pull
# ---------------------------------------------------------------------------

class TestCmdPull:
    def test_pull_all(self, capsys):
        from bin.openclaw_connector import cmd_pull  # type: ignore[import]
        reg = _make_registry()
        reg.pull_all.return_value = [
            Path("/vault/05_Inbox/queue-agent/note-1.md"),
            Path("/vault/05_Inbox/queue-agent/note-2.md"),
        ]

        args = MagicMock()
        args.id = None

        with patch("bin.openclaw_connector.resolve_vault_path", return_value="/vault"):
            cmd_pull(args, reg)

        out = capsys.readouterr().out
        assert "note-1.md" in out
        assert "2 note(s) written" in out

    def test_pull_single_connector(self, capsys, tmp_path):
        from bin.openclaw_connector import cmd_pull  # type: ignore[import]
        from lib.connectors.base import RawData, VaultNote  # type: ignore[import]

        reg = _make_registry()
        conn = MagicMock()
        conn.mode = "pull"
        raw = RawData(source_id="x1", payload={"title": "T", "body": "B"})
        conn.pull.return_value = [raw]
        note = VaultNote(
            title="T", body="B",
            source_connector="test", source_type="stub", source_id="x1",
        )
        conn.transform.return_value = note
        written_path = tmp_path / "05_Inbox" / "queue-human" / "t-abc.md"
        written_path.parent.mkdir(parents=True)
        written_path.write_text("# T\n")
        note_mock = MagicMock()
        note_mock.write_to_vault.return_value = written_path
        conn.transform.return_value = note_mock
        reg.get.return_value = conn

        args = MagicMock()
        args.id = "test-conn"

        with patch("bin.openclaw_connector.resolve_vault_path", return_value=str(tmp_path)):
            cmd_pull(args, reg)

        out = capsys.readouterr().out
        assert "Pulled 1 item(s)" in out

    def test_pull_push_only_exits(self):
        from bin.openclaw_connector import cmd_pull  # type: ignore[import]
        reg = _make_registry()
        conn = MagicMock()
        conn.mode = "push"
        reg.get.return_value = conn

        args = MagicMock()
        args.id = "push-only"

        with patch("bin.openclaw_connector.resolve_vault_path", return_value="/vault"):
            with pytest.raises(SystemExit) as exc:
                cmd_pull(args, reg)
        assert exc.value.code == 1

    def test_pull_missing_connector_exits(self):
        from bin.openclaw_connector import cmd_pull  # type: ignore[import]
        reg = _make_registry()
        reg.get.return_value = None

        args = MagicMock()
        args.id = "ghost"

        with patch("bin.openclaw_connector.resolve_vault_path", return_value="/vault"):
            with pytest.raises(SystemExit) as exc:
                cmd_pull(args, reg)
        assert exc.value.code == 1


# ---------------------------------------------------------------------------
# resolve_vault_path
# ---------------------------------------------------------------------------

class TestResolveVaultPath:
    def test_uses_lacp_obsidian_vault(self, monkeypatch):
        from bin.openclaw_connector import resolve_vault_path  # type: ignore[import]
        monkeypatch.setenv("LACP_OBSIDIAN_VAULT", "/Volumes/Cortex/vault")
        assert resolve_vault_path() == "/Volumes/Cortex/vault"

    def test_uses_openclaw_vault(self, monkeypatch):
        from bin.openclaw_connector import resolve_vault_path  # type: ignore[import]
        monkeypatch.delenv("LACP_OBSIDIAN_VAULT", raising=False)
        monkeypatch.setenv("OPENCLAW_VAULT", "/data/vault")
        assert resolve_vault_path() == "/data/vault"

    def test_falls_back_to_openclaw_home(self, monkeypatch):
        from bin.openclaw_connector import resolve_vault_path  # type: ignore[import]
        monkeypatch.delenv("LACP_OBSIDIAN_VAULT", raising=False)
        monkeypatch.delenv("OPENCLAW_VAULT", raising=False)
        monkeypatch.setenv("OPENCLAW_HOME", "/custom/openclaw")
        result = resolve_vault_path()
        assert result == "/custom/openclaw/data/knowledge"

    def test_default_to_home_dot_openclaw(self, monkeypatch):
        from bin.openclaw_connector import resolve_vault_path  # type: ignore[import]
        monkeypatch.delenv("LACP_OBSIDIAN_VAULT", raising=False)
        monkeypatch.delenv("OPENCLAW_VAULT", raising=False)
        monkeypatch.delenv("OPENCLAW_HOME", raising=False)
        result = resolve_vault_path()
        assert result.endswith("/.openclaw/data/knowledge")
