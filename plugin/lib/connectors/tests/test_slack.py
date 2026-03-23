"""Tests for Slack connector."""

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from lib.connectors.slack import SlackConnector
from lib.connectors.base import RawData


def _make_connector(**overrides):
    cfg = {
        "id": "slack-test",
        "type": "slack",
        "trust_level": "medium",
        "mode": "both",
        "landing_zone": "queue-human",
        "config": {
            "bot_token": "xoxb-test-token",
            "channels": ["C123ENGINEERING", "engineering"],
            "user_allowlist": ["U01ABC123"],
            "events": ["message", "reaction_added"],
            "min_reactions": 2,
            "bookmark_reactions": ["brain", "bookmark"],
            **overrides,
        },
    }
    return SlackConnector(cfg)


class TestSlackAuth:
    @patch.object(SlackConnector, "_slack_api")
    def test_authenticate_success(self, mock_api):
        mock_api.return_value = {"ok": True, "user_id": "U01"}
        conn = _make_connector()
        assert conn.authenticate() is True

    @patch.object(SlackConnector, "_slack_api")
    def test_authenticate_failure(self, mock_api):
        mock_api.return_value = {"ok": False, "error": "invalid_auth"}
        conn = _make_connector()
        assert conn.authenticate() is False

    def test_authenticate_no_token(self):
        conn = _make_connector(bot_token="")
        assert conn.authenticate() is False


class TestSlackReceive:
    def test_accept_message_from_allowed_user(self):
        conn = _make_connector()
        raw = conn.receive({
            "event": {
                "type": "message",
                "channel": "C123ENGINEERING",
                "user": "U01ABC123",
                "text": "Important architecture note",
                "ts": "1234567890.123456",
            }
        })
        assert raw.sender == "U01ABC123"

    def test_reject_message_from_disallowed_user(self):
        conn = _make_connector()
        with pytest.raises(ValueError, match="not in allowlist"):
            conn.receive({
                "event": {
                    "type": "message",
                    "channel": "C123ENGINEERING",
                    "user": "U99HACKER",
                    "text": "spam",
                    "ts": "1234567890.999",
                }
            })

    def test_reject_disallowed_channel(self):
        conn = _make_connector()
        with pytest.raises(ValueError, match="not in allowlist"):
            conn.receive({
                "event": {
                    "type": "message",
                    "channel": "C999RANDOM",
                    "user": "U01ABC123",
                    "text": "test",
                    "ts": "1234567890.111",
                }
            })

    def test_reject_non_bookmark_reaction(self):
        conn = _make_connector()
        with pytest.raises(ValueError, match="not a bookmark"):
            conn.receive({
                "event": {
                    "type": "reaction_added",
                    "channel": "C123ENGINEERING",
                    "user": "U01ABC123",
                    "reaction": "thumbsup",
                    "ts": "1234567890.222",
                }
            })

    def test_accept_bookmark_reaction(self):
        conn = _make_connector()
        raw = conn.receive({
            "event": {
                "type": "reaction_added",
                "channel": "C123ENGINEERING",
                "user": "U01ABC123",
                "reaction": "brain",
                "ts": "1234567890.333",
                "item": {"type": "message", "channel": "C123ENGINEERING", "ts": "111.222"},
            }
        })
        assert "brain" in raw.payload.get("reaction", "")


class TestSlackTransform:
    def test_transform_message(self):
        conn = _make_connector()
        conn._channel_name_cache["C123"] = "engineering"
        conn._user_name_cache["U01"] = "Andrew"
        raw = RawData(
            source_id="slack-C123-1234",
            payload={
                "type": "message",
                "text": "We should use event sourcing for the treasury module.",
                "user": "U01",
                "ts": "1234567890.123",
                "reactions": [{"name": "brain", "count": 3}],
            },
            sender="U01",
            metadata={"event_type": "message", "channel": "C123", "ts": "1234567890.123"},
        )
        note = conn.transform(raw)
        assert "event sourcing" in note.body
        assert "engineering" in note.title or "engineering" in note.body
        assert note.source_connector == "slack-test"

    def test_transform_reaction(self):
        conn = _make_connector()
        conn._channel_name_cache["C123"] = "engineering"
        conn._user_name_cache["U01"] = "Andrew"
        raw = RawData(
            source_id="slack-C123-1234",
            payload={
                "type": "reaction_added",
                "reaction": "brain",
                "user": "U01",
                "item": {"channel": "C123", "ts": "1111.2222"},
            },
            sender="U01",
            metadata={"event_type": "reaction_added", "channel": "C123", "ts": "1234"},
        )
        note = conn.transform(raw)
        assert "Bookmark" in note.title
        assert ":brain:" in note.body


class TestSlackHealth:
    def test_health_check(self):
        conn = _make_connector()
        conn.start()
        status = conn.health_check()
        assert status.healthy is True
        assert len(status.extra["channels"]) == 2
