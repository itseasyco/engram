"""Tests for plugin.lib.invites -- invite token system."""

import json
import sys
from datetime import datetime, UTC, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from lib.invites import (
    generate_token,
    validate_token,
    redeem_token,
    revoke_token,
    list_tokens,
    TOKEN_PREFIX,
)


class TestGenerateToken:
    def test_generates_valid_format(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OPENCLAW_HOME", str(tmp_path))
        invite = generate_token("dev@example.com", role="developer")
        assert invite.token.startswith(TOKEN_PREFIX)
        assert len(invite.token) == len(TOKEN_PREFIX) + 32
        assert invite.email == "dev@example.com"
        assert invite.role == "developer"
        assert invite.redeemed is False

    def test_invalid_role_raises(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OPENCLAW_HOME", str(tmp_path))
        with pytest.raises(ValueError, match="Invalid role"):
            generate_token("x@x.com", role="admin")

    def test_persists_to_file(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OPENCLAW_HOME", str(tmp_path))
        invite = generate_token("a@b.com")
        path = tmp_path / "config" / "invites.json"
        assert path.exists()
        data = json.loads(path.read_text())
        assert len(data["invites"]) == 1
        assert data["invites"][0]["token"] == invite.token


class TestValidateToken:
    def test_valid_token(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OPENCLAW_HOME", str(tmp_path))
        invite = generate_token("a@b.com")
        valid, found, reason = validate_token(invite.token)
        assert valid is True
        assert reason == "valid"
        assert found.email == "a@b.com"

    def test_invalid_format(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OPENCLAW_HOME", str(tmp_path))
        valid, _, reason = validate_token("not_a_token")
        assert valid is False
        assert reason == "invalid_format"

    def test_not_found(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OPENCLAW_HOME", str(tmp_path))
        valid, _, reason = validate_token("inv_" + "a" * 32)
        assert valid is False
        assert reason == "not_found"

    def test_expired_token(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OPENCLAW_HOME", str(tmp_path))
        invite = generate_token("a@b.com", expires_hours=0)
        # Token expires immediately (0 hours)
        valid, _, reason = validate_token(invite.token)
        # With 0 hours it should still be valid at the exact moment
        # Use -1 to force expiration by manipulating the file
        path = tmp_path / "config" / "invites.json"
        data = json.loads(path.read_text())
        past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        data["invites"][0]["expires_at"] = past
        path.write_text(json.dumps(data))
        valid, _, reason = validate_token(invite.token)
        assert valid is False
        assert reason == "expired"


class TestRedeemToken:
    def test_redeem_works(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OPENCLAW_HOME", str(tmp_path))
        invite = generate_token("a@b.com")
        ok, reason = redeem_token(invite.token, redeemed_by="agent-001")
        assert ok is True
        assert reason == "redeemed"

    def test_double_redeem_single_use(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OPENCLAW_HOME", str(tmp_path))
        invite = generate_token("a@b.com", single_use=True)
        redeem_token(invite.token)
        valid, _, reason = validate_token(invite.token)
        assert valid is False
        assert reason == "already_redeemed"


class TestRevokeToken:
    def test_revoke_works(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OPENCLAW_HOME", str(tmp_path))
        invite = generate_token("a@b.com")
        ok, reason = revoke_token(invite.token)
        assert ok is True
        valid, _, reason = validate_token(invite.token)
        assert valid is False
        assert reason == "revoked"

    def test_revoke_not_found(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OPENCLAW_HOME", str(tmp_path))
        ok, reason = revoke_token("inv_" + "b" * 32)
        assert ok is False
        assert reason == "not_found"


class TestListTokens:
    def test_list_active(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OPENCLAW_HOME", str(tmp_path))
        generate_token("a@b.com")
        generate_token("c@d.com")
        tokens = list_tokens()
        assert len(tokens) == 2

    def test_list_excludes_expired_by_default(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OPENCLAW_HOME", str(tmp_path))
        invite = generate_token("a@b.com")
        # Manually expire it
        path = tmp_path / "config" / "invites.json"
        data = json.loads(path.read_text())
        past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        data["invites"][0]["expires_at"] = past
        path.write_text(json.dumps(data))
        assert len(list_tokens()) == 0
        assert len(list_tokens(include_expired=True)) == 1
