"""Tests for connector base class and VaultNote."""

import os
import json
import tempfile
from pathlib import Path

import pytest

# Allow import from parent
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from lib.connectors.base import (
    Connector,
    ConnectorStatus,
    RawData,
    VaultNote,
    TrustLevel,
    ConnectorMode,
)


class StubConnector(Connector):
    """Minimal concrete connector for testing."""

    type = "stub"

    def authenticate(self) -> bool:
        return True

    def transform(self, raw_data: RawData) -> VaultNote:
        return VaultNote(
            title=raw_data.payload.get("title", "Stub"),
            body=raw_data.payload.get("body", ""),
            source_connector=self.id,
            source_type=self.type,
            source_id=raw_data.source_id,
            trust_level=self.trust_level,
            landing_zone=self.landing_zone,
        )

    def health_check(self) -> ConnectorStatus:
        return self.base_status(healthy=True)


class TestVaultNote:
    def test_slug_generation(self):
        note = VaultNote(
            title="My Test Note",
            body="content",
            source_connector="test-conn",
            source_type="stub",
            source_id="abc-123",
        )
        assert "my-test-note" in note.slug
        assert len(note.slug) > 10

    def test_slug_uniqueness(self):
        note_a = VaultNote(
            title="Same Title", body="", source_connector="conn-a",
            source_type="stub", source_id="id-1",
        )
        note_b = VaultNote(
            title="Same Title", body="", source_connector="conn-b",
            source_type="stub", source_id="id-2",
        )
        assert note_a.slug != note_b.slug

    def test_to_markdown_has_frontmatter(self):
        note = VaultNote(
            title="PR Merged",
            body="Pull request #42 was merged.",
            source_connector="github-test",
            source_type="github",
            source_id="pr-42",
            tags=["cicd", "github"],
            trust_level="verified",
        )
        md = note.to_markdown()
        assert md.startswith("---\n")
        assert "title: PR Merged" in md
        assert "trust_level: verified" in md
        assert "tags:" in md
        assert "  - cicd" in md
        assert "# PR Merged" in md
        assert "Pull request #42 was merged." in md

    def test_low_trust_sets_unverified(self):
        note = VaultNote(
            title="Unknown", body="", source_connector="x",
            source_type="webhook", source_id="1",
            trust_level="low",
        )
        assert note.status == "unverified"

    def test_write_to_vault(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            note = VaultNote(
                title="Test Write",
                body="body content",
                source_connector="test",
                source_type="stub",
                source_id="w-1",
                landing_zone="queue-cicd",
            )
            path = note.write_to_vault(tmpdir)
            assert path.exists()
            assert "05_Inbox/queue-cicd" in str(path)
            content = path.read_text()
            assert "Test Write" in content

    def test_write_handles_collision(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            note = VaultNote(
                title="Collision", body="v1", source_connector="c",
                source_type="stub", source_id="same-id",
            )
            path1 = note.write_to_vault(tmpdir)
            # Write again -- should not overwrite
            note2 = VaultNote(
                title="Collision", body="v2", source_connector="c",
                source_type="stub", source_id="same-id",
            )
            path2 = note2.write_to_vault(tmpdir)
            assert path1 != path2
            assert path1.exists()
            assert path2.exists()


class TestConnectorBase:
    def test_init_from_config(self):
        cfg = {
            "id": "test-stub",
            "type": "stub",
            "trust_level": "high",
            "mode": "pull",
            "landing_zone": "queue-agent",
            "config": {"key": "value"},
        }
        conn = StubConnector(cfg)
        assert conn.id == "test-stub"
        assert conn.trust_level == "high"
        assert conn.mode == "pull"
        assert conn.connector_config["key"] == "value"

    def test_env_var_resolution(self, monkeypatch):
        monkeypatch.setenv("MY_SECRET", "s3cret")
        cfg = {
            "id": "env-test",
            "type": "stub",
            "config": {"token": "${MY_SECRET}", "plain": "hello"},
        }
        conn = StubConnector(cfg)
        assert conn.connector_config["token"] == "s3cret"
        assert conn.connector_config["plain"] == "hello"

    def test_env_var_missing_resolves_empty(self, monkeypatch):
        monkeypatch.delenv("NONEXISTENT_VAR", raising=False)
        cfg = {
            "id": "env-miss",
            "type": "stub",
            "config": {"token": "${NONEXISTENT_VAR}"},
        }
        conn = StubConnector(cfg)
        assert conn.connector_config["token"] == ""

    def test_authenticate(self):
        conn = StubConnector({"id": "auth-test", "type": "stub", "config": {}})
        assert conn.authenticate() is True

    def test_transform(self):
        conn = StubConnector({"id": "tx-test", "type": "stub", "config": {}})
        raw = RawData(source_id="r1", payload={"title": "Hello", "body": "World"})
        note = conn.transform(raw)
        assert note.title == "Hello"
        assert note.source_connector == "tx-test"

    def test_health_check(self):
        conn = StubConnector({"id": "hc-test", "type": "stub", "config": {}})
        conn.start()
        status = conn.health_check()
        assert status.healthy is True
        assert status.connector_id == "hc-test"

    def test_pull_not_implemented_on_push(self):
        conn = StubConnector({"id": "push-test", "type": "stub", "mode": "push", "config": {}})
        with pytest.raises(NotImplementedError):
            conn.pull()

    def test_error_tracking(self):
        conn = StubConnector({"id": "err-test", "type": "stub", "config": {}})
        conn.record_error("timeout")
        conn.record_error("refused")
        status = conn.health_check()
        assert status.error_count == 2
        assert status.last_error == "refused"


class TestRawData:
    def test_auto_timestamp(self):
        raw = RawData(source_id="x", payload={})
        assert raw.timestamp  # should be auto-filled
        assert "T" in raw.timestamp  # ISO format
