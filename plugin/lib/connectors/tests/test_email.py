"""Tests for email connector."""

from email.message import EmailMessage
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from lib.connectors.email import EmailConnector
from lib.connectors.base import RawData


def _make_connector(**overrides):
    cfg = {
        "id": "email-test",
        "type": "email",
        "trust_level": "medium",
        "mode": "pull",
        "landing_zone": "queue-human",
        "config": {
            "provider": "imap",
            "imap_host": "imap.example.com",
            "imap_port": 993,
            "username": "test@example.com",
            "password": "secret",
            "folders": ["INBOX"],
            "sender_policy": "allowlist",
            "sender_allowlist": [
                {"address": "andrew@easylabs.io", "trust_override": "high"},
                "niko@easylabs.io",
            ],
            **overrides,
        },
    }
    return EmailConnector(cfg)


class TestEmailAuth:
    def test_gog_auth_no_binary(self):
        conn = _make_connector(provider="gog")
        with patch("shutil.which", return_value=None):
            assert conn.authenticate() is False


class TestEmailParsing:
    def test_parse_allowed_sender(self):
        conn = _make_connector()
        msg = EmailMessage()
        msg["From"] = "Andrew <andrew@easylabs.io>"
        msg["Subject"] = "Architecture Update"
        msg["Date"] = "Sat, 21 Mar 2026 10:00:00 -0000"
        msg["Message-ID"] = "<test-1@easylabs.io>"
        msg.set_content("We should adopt event sourcing.")

        raw = conn._parse_email(msg, "INBOX")
        assert raw is not None
        assert raw.payload["from"] == "andrew@easylabs.io"
        assert raw.payload["subject"] == "Architecture Update"
        assert "event sourcing" in raw.payload["body"]

    def test_reject_disallowed_sender(self):
        conn = _make_connector()
        msg = EmailMessage()
        msg["From"] = "hacker@evil.com"
        msg["Subject"] = "Spam"
        msg["Message-ID"] = "<spam-1@evil.com>"
        msg.set_content("Buy now!")

        raw = conn._parse_email(msg, "INBOX")
        assert raw is None

    def test_deduplicate_by_message_id(self):
        conn = _make_connector()
        msg = EmailMessage()
        msg["From"] = "andrew@easylabs.io"
        msg["Subject"] = "Test"
        msg["Message-ID"] = "<dup-1@easylabs.io>"
        msg.set_content("test")

        raw1 = conn._parse_email(msg, "INBOX")
        raw2 = conn._parse_email(msg, "INBOX")
        assert raw1 is not None
        assert raw2 is None

    def test_subject_filter_match(self):
        conn = _make_connector(subject_filters=["Architecture", "Decision"])
        msg = EmailMessage()
        msg["From"] = "andrew@easylabs.io"
        msg["Subject"] = "Architecture Decision: Event Sourcing"
        msg["Message-ID"] = "<filter-1@easylabs.io>"
        msg.set_content("We decided...")

        raw = conn._parse_email(msg, "INBOX")
        assert raw is not None

    def test_subject_filter_no_match(self):
        conn = _make_connector(subject_filters=["Architecture"])
        msg = EmailMessage()
        msg["From"] = "andrew@easylabs.io"
        msg["Subject"] = "Lunch plans"
        msg["Message-ID"] = "<filter-2@easylabs.io>"
        msg.set_content("Pizza?")

        raw = conn._parse_email(msg, "INBOX")
        assert raw is None


class TestEmailTransform:
    def test_transform_with_trust_override(self):
        conn = _make_connector()
        raw = RawData(
            source_id="<t1@easylabs.io>",
            payload={
                "from": "andrew@easylabs.io",
                "from_name": "Andrew",
                "subject": "Treasury Design",
                "body": "Here is the design...",
                "date": "2026-03-21",
                "folder": "INBOX",
                "message_id": "<t1@easylabs.io>",
            },
            sender="andrew@easylabs.io",
            metadata={
                "folder": "INBOX",
                "trust_override": "high",
                "landing_zone_override": None,
            },
        )
        note = conn.transform(raw)
        assert note.title == "Email: Treasury Design"
        assert note.trust_level == "high"
        assert "Andrew" in note.body
        assert note.source_connector == "email-test"

    def test_transform_default_trust(self):
        conn = _make_connector()
        raw = RawData(
            source_id="<t2@easylabs.io>",
            payload={
                "from": "niko@easylabs.io",
                "from_name": "Niko",
                "subject": "Meeting Notes",
                "body": "Notes from today...",
                "date": "2026-03-21",
                "folder": "INBOX",
                "message_id": "<t2@easylabs.io>",
            },
            sender="niko@easylabs.io",
            metadata={"folder": "INBOX", "trust_override": None, "landing_zone_override": None},
        )
        note = conn.transform(raw)
        assert note.trust_level == "medium"


class TestEmailHealth:
    def test_health_check_imap_no_connection(self):
        conn = _make_connector()
        status = conn.health_check()
        assert status.healthy is False  # no IMAP connection established
        assert status.extra["provider"] == "imap"
