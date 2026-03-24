"""Tests for openclaw-lacp-connect CLI."""

import json
import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = str(Path(__file__).resolve().parent.parent / "openclaw-lacp-connect")


class TestConnectHelp:
    def test_help_exits_zero(self):
        result = subprocess.run(
            ["python3", SCRIPT, "--help"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "openclaw-lacp-connect" in result.stdout
        assert "invite" in result.stdout
        assert "join" in result.stdout
        assert "status" in result.stdout


class TestConnectStatus:
    def test_status_standalone(self, tmp_path):
        env = os.environ.copy()
        env["LACP_MODE"] = "standalone"
        env["OPENCLAW_HOME"] = str(tmp_path)
        result = subprocess.run(
            ["python3", SCRIPT, "--json", "status"],
            capture_output=True, text=True, env=env,
        )
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        assert payload["ok"] is True
        assert payload["mode"] == "standalone"


class TestConnectInvite:
    def test_invite_requires_curator_mode(self, tmp_path):
        env = os.environ.copy()
        env["LACP_MODE"] = "standalone"
        env["OPENCLAW_HOME"] = str(tmp_path)
        result = subprocess.run(
            ["python3", SCRIPT, "--json", "invite", "--email", "dev@test.com"],
            capture_output=True, text=True, env=env,
        )
        assert result.returncode == 1

    def test_invite_in_curator_mode(self, tmp_path):
        env = os.environ.copy()
        env["LACP_MODE"] = "curator"
        env["OPENCLAW_HOME"] = str(tmp_path)
        result = subprocess.run(
            ["python3", SCRIPT, "--json", "invite", "--email", "dev@test.com", "--role", "developer"],
            capture_output=True, text=True, env=env,
        )
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        assert payload["ok"] is True
        assert payload["token"].startswith("inv_")
        assert payload["role"] == "developer"


class TestConnectSetRole:
    def test_set_role(self, tmp_path):
        env = os.environ.copy()
        env["OPENCLAW_HOME"] = str(tmp_path)
        env["LACP_MODE"] = "connected"
        result = subprocess.run(
            ["python3", SCRIPT, "--json", "set-role", "--role", "pm"],
            capture_output=True, text=True, env=env,
        )
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        assert payload["role"] == "pm"

    def test_set_role_invalid(self, tmp_path):
        env = os.environ.copy()
        env["OPENCLAW_HOME"] = str(tmp_path)
        env["LACP_MODE"] = "connected"
        result = subprocess.run(
            ["python3", SCRIPT, "--json", "set-role", "--role", "admin"],
            capture_output=True, text=True, env=env,
        )
        assert result.returncode == 1


class TestConnectDisconnect:
    def test_disconnect_not_connected(self, tmp_path):
        env = os.environ.copy()
        env["LACP_MODE"] = "standalone"
        env["OPENCLAW_HOME"] = str(tmp_path)
        result = subprocess.run(
            ["python3", SCRIPT, "--json", "disconnect"],
            capture_output=True, text=True, env=env,
        )
        assert result.returncode == 1


class TestConnectMembers:
    def test_members_requires_curator(self, tmp_path):
        env = os.environ.copy()
        env["LACP_MODE"] = "standalone"
        env["OPENCLAW_HOME"] = str(tmp_path)
        result = subprocess.run(
            ["python3", SCRIPT, "--json", "members"],
            capture_output=True, text=True, env=env,
        )
        assert result.returncode == 1

    def test_members_in_curator_mode(self, tmp_path):
        env = os.environ.copy()
        env["LACP_MODE"] = "curator"
        env["OPENCLAW_HOME"] = str(tmp_path)
        result = subprocess.run(
            ["python3", SCRIPT, "--json", "members"],
            capture_output=True, text=True, env=env,
        )
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        assert payload["ok"] is True
