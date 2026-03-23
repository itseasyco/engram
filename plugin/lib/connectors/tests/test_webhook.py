"""Tests for webhook connector."""

import hashlib
import hmac as hmac_mod
import json
from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from lib.connectors.webhook import WebhookConnector
from lib.connectors.base import RawData


def _make_connector(**overrides):
    cfg = {
        "id": "test-webhook",
        "type": "webhook",
        "trust_level": "medium",
        "mode": "push",
        "landing_zone": "queue-cicd",
        "config": {
            "path": "/hooks/test",
            "hmac_secret": "test-secret",
            "hmac_header": "X-Signature",
            "hmac_algorithm": "sha256",
            **overrides,
        },
    }
    return WebhookConnector(cfg)


class TestWebhookAuth:
    def test_authenticate_always_true(self):
        conn = _make_connector()
        assert conn.authenticate() is True

    def test_path_from_config(self):
        conn = _make_connector()
        assert conn.path == "/hooks/test"


class TestWebhookVerification:
    def test_valid_hmac(self):
        conn = _make_connector()
        body = b'{"event": "test"}'
        sig = hmac_mod.new(b"test-secret", body, hashlib.sha256).hexdigest()
        assert conn.verify_request(body, {"X-Signature": sig}) is True

    def test_invalid_hmac(self):
        conn = _make_connector()
        assert conn.verify_request(b"body", {"X-Signature": "bad"}) is False

    def test_missing_hmac_header(self):
        conn = _make_connector()
        assert conn.verify_request(b"body", {}) is False

    def test_ip_allowlist_accepts(self):
        conn = _make_connector(ip_allowlist=["10.0.0.0/8"])
        body = b'{"event": "test"}'
        sig = hmac_mod.new(b"test-secret", body, hashlib.sha256).hexdigest()
        assert conn.verify_request(body, {"X-Signature": sig}, source_ip="10.1.2.3") is True

    def test_ip_allowlist_rejects(self):
        conn = _make_connector(ip_allowlist=["10.0.0.0/8"])
        assert conn.verify_request(b"body", {}, source_ip="192.168.1.1") is False

    def test_no_hmac_secret_skips_verification(self):
        conn = _make_connector(hmac_secret="")
        assert conn.verify_request(b"body", {}) is True


class TestWebhookTransform:
    def test_default_transform(self):
        conn = _make_connector()
        conn.authenticate()
        raw = RawData(
            source_id="evt-1",
            payload={"event": "deploy", "status": "success"},
        )
        note = conn.transform(raw)
        assert "evt-1" in note.title
        assert "deploy" in note.body
        assert note.source_connector == "test-webhook"

    def test_title_template(self):
        conn = _make_connector(title_template="{event}: {status}")
        conn.authenticate()
        raw = RawData(
            source_id="evt-2",
            payload={"event": "build", "status": "failed"},
        )
        note = conn.transform(raw)
        assert note.title == "build: failed"

    def test_receive_extracts_source_id(self):
        conn = _make_connector()
        raw = conn.receive({"id": "hook-42", "data": "value"})
        assert raw.source_id == "hook-42"

    def test_receive_generates_id_if_missing(self):
        conn = _make_connector()
        raw = conn.receive({"data": "value"})
        assert len(raw.source_id) > 0
