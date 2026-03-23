"""Tests for GitHub connector."""

import hashlib
import hmac as hmac_mod
from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from lib.connectors.github import GithubConnector


def _make_connector(**overrides):
    cfg = {
        "id": "github-test",
        "type": "github",
        "trust_level": "verified",
        "mode": "push",
        "landing_zone": "queue-cicd",
        "config": {
            "webhook_secret": "gh-secret-123",
            "repos": ["easy-labs/easy-api"],
            "events": ["pull_request", "push", "deployment", "release"],
            **overrides,
        },
    }
    return GithubConnector(cfg)


class TestGitHubAuth:
    def test_authenticate_with_secret(self):
        conn = _make_connector()
        assert conn.authenticate() is True

    def test_authenticate_without_secret(self):
        conn = _make_connector(webhook_secret="")
        assert conn.authenticate() is False


class TestGitHubWebhookVerification:
    def test_valid_signature(self):
        conn = _make_connector()
        body = b'{"action": "opened"}'
        sig = "sha256=" + hmac_mod.new(b"gh-secret-123", body, hashlib.sha256).hexdigest()
        assert conn.verify_webhook(body, sig) is True

    def test_invalid_signature(self):
        conn = _make_connector()
        assert conn.verify_webhook(b"body", "sha256=invalid") is False


class TestGitHubReceive:
    def test_accept_allowed_repo(self):
        conn = _make_connector()
        raw = conn.receive({
            "_event_type": "pull_request",
            "_delivery_id": "d1",
            "repository": {"full_name": "easy-labs/easy-api"},
            "sender": {"login": "andrew"},
        })
        assert raw.source_id.startswith("pull_request")

    def test_reject_disallowed_repo(self):
        conn = _make_connector()
        with pytest.raises(ValueError, match="not in allowlist"):
            conn.receive({
                "_event_type": "pull_request",
                "_delivery_id": "d2",
                "repository": {"full_name": "hacker/evil-repo"},
                "sender": {"login": "hacker"},
            })

    def test_reject_disallowed_event(self):
        conn = _make_connector(events=["push"])
        with pytest.raises(ValueError, match="not in accepted events"):
            conn.receive({
                "_event_type": "issues",
                "_delivery_id": "d3",
                "repository": {"full_name": "easy-labs/easy-api"},
                "sender": {"login": "andrew"},
            })

    def test_deduplicate_delivery(self):
        conn = _make_connector()
        payload = {
            "_event_type": "push",
            "_delivery_id": "dup-1",
            "repository": {"full_name": "easy-labs/easy-api"},
            "sender": {"login": "andrew"},
        }
        conn.receive(payload)
        with pytest.raises(ValueError, match="Duplicate"):
            conn.receive(payload)


class TestGitHubTransformPR:
    def test_pr_opened(self):
        conn = _make_connector()
        raw = conn.receive({
            "_event_type": "pull_request",
            "_delivery_id": "pr-1",
            "action": "opened",
            "repository": {"full_name": "easy-labs/easy-api"},
            "sender": {"login": "andrew"},
            "pull_request": {
                "number": 42,
                "title": "feat: add treasury send",
                "user": {"login": "andrew"},
                "body": "Implements the treasury send flow.",
                "state": "open",
                "merged": False,
                "base": {"ref": "main"},
                "head": {"ref": "feat/treasury-send"},
                "html_url": "https://github.com/easy-labs/easy-api/pull/42",
                "additions": 150,
                "deletions": 20,
                "changed_files": 5,
            },
        })
        note = conn.transform(raw)
        assert "PR #42" in note.title
        assert "treasury send" in note.title
        assert note.author == "andrew"
        assert "pull-request" in note.tags
        assert note.source_url == "https://github.com/easy-labs/easy-api/pull/42"

    def test_pr_merged(self):
        conn = _make_connector()
        raw = conn.receive({
            "_event_type": "pull_request",
            "_delivery_id": "pr-2",
            "action": "closed",
            "repository": {"full_name": "easy-labs/easy-api"},
            "sender": {"login": "andrew"},
            "pull_request": {
                "number": 42,
                "title": "feat: merged",
                "user": {"login": "andrew"},
                "state": "closed",
                "merged": True,
                "base": {"ref": "main"},
                "head": {"ref": "feat/x"},
                "html_url": "",
            },
        })
        note = conn.transform(raw)
        assert "merged" in note.tags


class TestGitHubTransformPush:
    def test_push_event(self):
        conn = _make_connector()
        raw = conn.receive({
            "_event_type": "push",
            "_delivery_id": "push-1",
            "ref": "refs/heads/main",
            "repository": {"full_name": "easy-labs/easy-api"},
            "sender": {"login": "andrew"},
            "pusher": {"name": "andrew"},
            "commits": [
                {"id": "abc1234567890", "message": "fix: handle timeout"},
                {"id": "def1234567890", "message": "test: add timeout tests"},
            ],
            "compare": "https://github.com/easy-labs/easy-api/compare/abc...def",
        })
        note = conn.transform(raw)
        assert "Push" in note.title
        assert "2 commits" in note.title
        assert "abc1234" in note.body
        assert "timeout" in note.body


class TestGitHubHealth:
    def test_health_with_secret(self):
        conn = _make_connector()
        conn.start()
        status = conn.health_check()
        assert status.healthy is True
        assert "easy-labs/easy-api" in status.extra["repos"]
