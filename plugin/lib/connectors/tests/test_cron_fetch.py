"""Tests for cron-fetch connector."""

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from lib.connectors.cron_fetch import CronFetchConnector
from lib.connectors.base import RawData


def _make_connector(**config_overrides):
    cfg = {
        "id": "test-fetch",
        "type": "cron_fetch",
        "trust_level": "medium",
        "mode": "pull",
        "landing_zone": "queue-human",
        "config": {
            "urls": [{"url": "https://example.com/api/data", "label": "Test API"}],
            "poll_interval_minutes": 15,
            **config_overrides,
        },
    }
    return CronFetchConnector(cfg)


class TestCronFetchAuth:
    def test_authenticate_with_urls(self):
        conn = _make_connector()
        assert conn.authenticate() is True

    def test_authenticate_no_urls(self):
        conn = _make_connector(urls=[])
        assert conn.authenticate() is False


class TestCronFetchPull:
    @patch.object(CronFetchConnector, "_fetch")
    def test_pull_returns_new_data(self, mock_fetch):
        mock_fetch.return_value = '{"status": "ok"}'
        conn = _make_connector()
        results = conn.pull()
        assert len(results) == 1
        assert results[0].payload["content_type"] == "json"
        assert results[0].payload["data"]["status"] == "ok"

    @patch.object(CronFetchConnector, "_fetch")
    def test_pull_skips_unchanged(self, mock_fetch):
        mock_fetch.return_value = '{"status": "ok"}'
        conn = _make_connector()
        first = conn.pull()
        assert len(first) == 1
        second = conn.pull()
        assert len(second) == 0

    @patch.object(CronFetchConnector, "_fetch")
    def test_pull_detects_change(self, mock_fetch):
        conn = _make_connector()
        mock_fetch.return_value = '{"v": 1}'
        conn.pull()
        mock_fetch.return_value = '{"v": 2}'
        results = conn.pull()
        assert len(results) == 1

    @patch.object(CronFetchConnector, "_fetch")
    def test_pull_handles_text_response(self, mock_fetch):
        mock_fetch.return_value = "plain text content"
        conn = _make_connector(response_format="text")
        results = conn.pull()
        assert len(results) == 1
        assert results[0].payload["content_type"] == "text"

    @patch.object(CronFetchConnector, "_fetch")
    def test_pull_handles_fetch_error(self, mock_fetch):
        mock_fetch.side_effect = Exception("timeout")
        conn = _make_connector()
        results = conn.pull()
        assert len(results) == 0


class TestCronFetchTransform:
    def test_transform_json(self):
        conn = _make_connector()
        raw = RawData(
            source_id="f1",
            payload={
                "url": "https://example.com/api",
                "label": "Test API",
                "content_type": "json",
                "data": {"status": "healthy"},
            },
        )
        note = conn.transform(raw)
        assert "Fetch: Test API" in note.title
        assert "healthy" in note.body
        assert note.source_url == "https://example.com/api"

    def test_transform_text(self):
        conn = _make_connector()
        raw = RawData(
            source_id="f2",
            payload={
                "url": "https://example.com/page",
                "label": "Page",
                "content_type": "text",
                "data": "Hello world",
            },
        )
        note = conn.transform(raw)
        assert "Hello world" in note.body


class TestCronFetchHealth:
    def test_health_check(self):
        conn = _make_connector()
        conn.start()
        status = conn.health_check()
        assert status.healthy is True
        assert status.extra["url_count"] == 1
