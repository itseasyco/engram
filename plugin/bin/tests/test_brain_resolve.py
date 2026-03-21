"""Tests for openclaw-brain-resolve."""

import json
import subprocess
import tempfile
from pathlib import Path

import pytest

SCRIPT = str(Path(__file__).resolve().parent.parent / "openclaw-brain-resolve")


def _make_vault_with_note(tmp_path, note_id="test-note-001", status="active"):
    """Create a minimal vault with one canonical note."""
    note = tmp_path / "concepts" / f"{note_id}.md"
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text(
        f"---\nid: {note_id}\ntype: concept\nlayer: 2\nstatus: {status}\nconfidence: 0.8\n---\n\n# Test Note\n\nSome content.\n",
        encoding="utf-8",
    )
    return note


class TestBrainResolveHelp:
    def test_help_exits_zero(self):
        result = subprocess.run(
            ["python3", SCRIPT, "--help"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "--resolution" in result.stdout


class TestBrainResolveMissingVault:
    def test_missing_vault_exits_2(self):
        result = subprocess.run(
            [
                "python3", SCRIPT,
                "--id", "nonexistent",
                "--resolution", "validated",
                "--reason", "test",
                "--vault", "/tmp/nonexistent-vault-abc123",
                "--json",
            ],
            capture_output=True, text=True,
        )
        assert result.returncode == 2
        payload = json.loads(result.stdout)
        assert payload["ok"] is False
        assert "vault_missing" in payload["error"]


class TestBrainResolveNotFound:
    def test_id_not_found_exits_3(self, tmp_path):
        _make_vault_with_note(tmp_path, note_id="other-note")
        result = subprocess.run(
            [
                "python3", SCRIPT,
                "--id", "nonexistent-id",
                "--resolution", "validated",
                "--reason", "test",
                "--vault", str(tmp_path),
                "--json",
            ],
            capture_output=True, text=True,
        )
        assert result.returncode == 3
        payload = json.loads(result.stdout)
        assert payload["ok"] is False
        assert "id_not_found" in payload["error"]


class TestBrainResolveValidated:
    def test_validated_updates_frontmatter(self, tmp_path):
        note = _make_vault_with_note(tmp_path, note_id="resolve-test-001")
        result = subprocess.run(
            [
                "python3", SCRIPT,
                "--id", "resolve-test-001",
                "--resolution", "validated",
                "--reason", "Confirmed via source",
                "--vault", str(tmp_path),
                "--json",
            ],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        assert payload["ok"] is True
        assert payload["updated_count"] == 1

        updated_text = note.read_text()
        assert "resolution_status: validated" in updated_text
        assert "status: active" in updated_text


class TestBrainResolveSuperseded:
    def test_superseded_sets_stale_and_ref(self, tmp_path):
        note = _make_vault_with_note(tmp_path, note_id="old-note-001")
        result = subprocess.run(
            [
                "python3", SCRIPT,
                "--id", "old-note-001",
                "--resolution", "superseded",
                "--superseded-by", "new-note-002",
                "--reason", "Replaced by updated version",
                "--vault", str(tmp_path),
                "--json",
            ],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        assert payload["ok"] is True

        updated_text = note.read_text()
        assert "resolution_status: superseded" in updated_text
        assert "status: stale" in updated_text
        assert "superseded_by: new-note-002" in updated_text


class TestBrainResolveDryRun:
    def test_dry_run_does_not_write(self, tmp_path):
        note = _make_vault_with_note(tmp_path, note_id="dryrun-001")
        original = note.read_text()
        result = subprocess.run(
            [
                "python3", SCRIPT,
                "--id", "dryrun-001",
                "--resolution", "archived",
                "--reason", "No longer relevant",
                "--vault", str(tmp_path),
                "--dry-run", "--json",
            ],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        assert payload["dry_run"] is True
        assert payload["updated_count"] == 1
        # File should NOT have changed
        assert note.read_text() == original
