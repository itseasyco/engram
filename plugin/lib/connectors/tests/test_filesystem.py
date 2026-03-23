"""Tests for filesystem connector."""

import tempfile
from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from lib.connectors.filesystem import FilesystemConnector, _classify_file, _is_transcript


class TestFileClassification:
    def test_pdf(self, tmp_path):
        f = tmp_path / "doc.pdf"
        f.write_bytes(b"%PDF-1.4 dummy")
        assert _classify_file(f) == "pdf"

    def test_url_file(self, tmp_path):
        f = tmp_path / "link.url"
        f.write_text("[InternetShortcut]\nURL=https://example.com\n")
        assert _classify_file(f) == "url"

    def test_markdown(self, tmp_path):
        f = tmp_path / "note.md"
        f.write_text("# Hello\n\nSome notes.")
        assert _classify_file(f) == "file"

    def test_transcript_detection(self, tmp_path):
        f = tmp_path / "meeting.md"
        f.write_text(
            "Speaker: Alice\n[00:01] Hello\nSpeaker: Bob\n[00:02] Hi there\nQ: How?\nA: Like this."
        )
        assert _classify_file(f) == "transcript"


class TestFilesystemConnector:
    def _make_connector(self, watch_paths):
        return FilesystemConnector({
            "id": "test-fs",
            "type": "filesystem",
            "trust_level": "high",
            "mode": "pull",
            "landing_zone": "queue-agent",
            "config": {
                "watch_paths": watch_paths,
                "extensions": [".md", ".txt"],
                "ignore_patterns": ["*.tmp", ".DS_Store"],
            },
        })

    def test_authenticate_with_valid_path(self, tmp_path):
        conn = self._make_connector([str(tmp_path)])
        assert conn.authenticate() is True

    def test_authenticate_with_no_valid_paths(self):
        conn = self._make_connector(["/nonexistent/path/abc123"])
        assert conn.authenticate() is False

    def test_pull_discovers_new_file(self, tmp_path):
        (tmp_path / "note.md").write_text("# Hello")
        conn = self._make_connector([str(tmp_path)])
        results = conn.pull()
        assert len(results) == 1
        assert results[0].payload["file_name"] == "note.md"

    def test_pull_skips_seen_file(self, tmp_path):
        (tmp_path / "note.md").write_text("# Hello")
        conn = self._make_connector([str(tmp_path)])
        first = conn.pull()
        assert len(first) == 1
        second = conn.pull()
        assert len(second) == 0

    def test_pull_skips_ignored_patterns(self, tmp_path):
        (tmp_path / "good.md").write_text("ok")
        (tmp_path / "bad.tmp").write_text("skip")
        (tmp_path / ".DS_Store").write_text("skip")
        conn = self._make_connector([str(tmp_path)])
        results = conn.pull()
        assert len(results) == 1
        assert results[0].payload["file_name"] == "good.md"

    def test_pull_skips_wrong_extension(self, tmp_path):
        (tmp_path / "image.png").write_bytes(b"PNG")
        conn = self._make_connector([str(tmp_path)])
        results = conn.pull()
        assert len(results) == 0

    def test_transform_file(self, tmp_path):
        f = tmp_path / "note.md"
        f.write_text("# My Note\n\nContent here.")
        conn = self._make_connector([str(tmp_path)])
        results = conn.pull()
        note = conn.transform(results[0])
        assert note.title == "note"
        assert note.source_connector == "test-fs"
        assert note.trust_level == "high"

    def test_health_check(self, tmp_path):
        conn = self._make_connector([str(tmp_path)])
        conn.start()
        status = conn.health_check()
        assert status.healthy is True
        assert str(tmp_path) in status.extra["watch_paths"]
