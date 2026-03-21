"""Tests for openclaw-memory-kpi."""

import json
import subprocess
from pathlib import Path

import pytest

SCRIPT = str(Path(__file__).resolve().parent.parent / "openclaw-memory-kpi")


def _make_vault(tmp_path, notes=None):
    """Create a vault with optional note specs."""
    if notes is None:
        notes = []
    for note in notes:
        path = tmp_path / note["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(note["content"], encoding="utf-8")
    return tmp_path


class TestMemoryKpiHelp:
    def test_help_exits_zero(self):
        result = subprocess.run(
            ["python3", SCRIPT, "--help"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "--vault" in result.stdout


class TestMemoryKpiMissingVault:
    def test_missing_vault_exits_2(self):
        result = subprocess.run(
            ["python3", SCRIPT, "--vault", "/tmp/nonexistent-kpi-vault-xyz", "--json"],
            capture_output=True, text=True,
        )
        assert result.returncode == 2
        payload = json.loads(result.stdout)
        assert payload["ok"] is False
        assert "vault_missing" in payload["error"]


class TestMemoryKpiEmptyVault:
    def test_empty_vault_returns_zeros(self, tmp_path):
        result = subprocess.run(
            ["python3", SCRIPT, "--vault", str(tmp_path), "--json"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        assert payload["ok"] is True
        assert payload["kpis"]["total_notes"] == 0
        assert payload["kpis"]["canonical_notes"] == 0


class TestMemoryKpiWithNotes:
    def test_counts_canonical_and_stale(self, tmp_path):
        vault = _make_vault(tmp_path, notes=[
            {
                "path": "concepts/note1.md",
                "content": "---\nid: n1\ntype: concept\nlayer: 2\nstatus: active\nconfidence: 0.9\nsource_urls:\n  - https://example.com\nlast_verified: 2026-01-01\nlinks:\n  - n2\n---\n\n# Note 1\n",
            },
            {
                "path": "concepts/note2.md",
                "content": "---\nid: n2\ntype: concept\nlayer: 2\nstatus: stale\nconfidence: 0.5\n---\n\n# Note 2\n",
            },
            {
                "path": "random/no-frontmatter.md",
                "content": "# Just a plain note\n\nNo frontmatter here.\n",
            },
        ])
        result = subprocess.run(
            ["python3", SCRIPT, "--vault", str(vault), "--json"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        kpis = payload["kpis"]
        assert kpis["total_notes"] == 3
        assert kpis["canonical_notes"] == 2  # both have layer/confidence
        assert kpis["stale_notes"] == 1
        assert kpis["source_backed_pct"] > 0  # note1 has source_urls


class TestMemoryKpiTextOutput:
    def test_text_format_works(self, tmp_path):
        _make_vault(tmp_path, notes=[
            {
                "path": "note.md",
                "content": "---\nid: x\nlayer: 1\nstatus: active\n---\n\nContent\n",
            },
        ])
        result = subprocess.run(
            ["python3", SCRIPT, "--vault", str(tmp_path)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "memory-kpi" in result.stdout
        assert "total_notes:" in result.stdout
