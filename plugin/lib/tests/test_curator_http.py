"""Tests for plugin.lib.curator_http -- curator HTTP surface."""

import json
import sys
import threading
import urllib.request
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from lib.curator_http import create_server, DEFAULT_PORT
from lib.invites import generate_token


TEST_TOKEN = "test_admin_token_abc123"


@pytest.fixture()
def curator_server(tmp_path, monkeypatch):
    """Start a test curator server on a random high port."""
    monkeypatch.setenv("OPENCLAW_HOME", str(tmp_path))
    vault = tmp_path / "vault"
    vault.mkdir()
    # Create some notes
    (vault / "test.md").write_text("---\ntitle: test\n---\n# Test\n")
    inbox = vault / "05_Inbox" / "queue-agent"
    inbox.mkdir(parents=True)
    (inbox / "pending.md").write_text("# Pending\n")

    port = 19876  # High port unlikely to collide
    server = create_server(
        port=port,
        admin_token=TEST_TOKEN,
        vault_path=str(vault),
        vault_name="Test Brain",
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://localhost:{port}", vault
    server.shutdown()


def _post(url: str, data: dict, token: str = TEST_TOKEN) -> tuple[int, dict]:
    """Helper to POST JSON."""
    body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )
    try:
        resp = urllib.request.urlopen(req)
        return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


class TestAuth:
    def test_missing_auth(self, curator_server):
        base_url, _ = curator_server
        body = json.dumps({}).encode()
        req = urllib.request.Request(
            f"{base_url}/health",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(req)
            assert False, "Should have raised"
        except urllib.error.HTTPError as e:
            assert e.code == 401

    def test_invalid_token(self, curator_server):
        base_url, _ = curator_server
        status, data = _post(f"{base_url}/health", {}, token="wrong")
        assert status == 403


class TestHealthEndpoint:
    def test_health_returns_status(self, curator_server):
        base_url, _ = curator_server
        status, data = _post(f"{base_url}/health", {})
        assert status == 200
        assert "status" in data
        assert "notes" in data
        assert data["notes"] >= 1  # test.md + pending.md


class TestValidateEndpoint:
    def test_validate_missing_token(self, curator_server):
        base_url, _ = curator_server
        status, data = _post(f"{base_url}/validate", {})
        assert status == 400
        assert data["error"] == "missing_token"

    def test_validate_invalid_token(self, curator_server):
        base_url, _ = curator_server
        status, data = _post(f"{base_url}/validate", {"token": "inv_" + "x" * 32})
        assert status == 200
        assert data["valid"] is False

    def test_validate_valid_token(self, curator_server):
        base_url, _ = curator_server
        invite = generate_token("dev@test.com", role="developer")
        status, data = _post(f"{base_url}/validate", {"token": invite.token})
        assert status == 200
        assert data["valid"] is True
        assert data["role"] == "developer"
        assert data["vault_name"] == "Test Brain"


class TestNotifyEndpoint:
    def test_notify_missing_file(self, curator_server):
        base_url, _ = curator_server
        status, data = _post(f"{base_url}/notify", {})
        assert status == 400

    def test_notify_accepted(self, curator_server):
        base_url, _ = curator_server
        status, data = _post(f"{base_url}/notify", {"file": "05_Inbox/queue-agent/urgent.md", "priority": "high"})
        assert status == 200
        assert data["accepted"] is True
        assert data["priority"] == "high"


class TestNotFound:
    def test_unknown_endpoint(self, curator_server):
        base_url, _ = curator_server
        status, data = _post(f"{base_url}/unknown", {})
        assert status == 404
