"""Tests for openclaw-obsidian-optimize."""

import json
import subprocess
from pathlib import Path

import pytest

SCRIPT = str(Path(__file__).resolve().parent.parent / "openclaw-obsidian-optimize")


class TestObsidianOptimizeHelp:
    def test_help_exits_zero(self):
        result = subprocess.run(
            ["python3", SCRIPT, "--help"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "--vault" in result.stdout


class TestObsidianOptimizeMissingVault:
    def test_missing_vault_exits_2(self):
        result = subprocess.run(
            ["python3", SCRIPT, "--vault", "/tmp/nonexistent-opt-vault-xyz", "--json"],
            capture_output=True, text=True,
        )
        assert result.returncode == 2
        payload = json.loads(result.stdout)
        assert payload["ok"] is False
        assert "vault_missing" in payload["error"]


class TestObsidianOptimizeDryRun:
    def test_dry_run_does_not_write_file(self, tmp_path):
        result = subprocess.run(
            ["python3", SCRIPT, "--vault", str(tmp_path), "--dry-run", "--json"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        assert payload["ok"] is True
        assert payload["dry_run"] is True
        assert payload["graph"]["wrote"] is False
        # File should NOT exist
        graph_path = tmp_path / ".obsidian" / "graph.json"
        assert not graph_path.exists()


class TestObsidianOptimizeWrites:
    def test_writes_graph_json(self, tmp_path):
        result = subprocess.run(
            ["python3", SCRIPT, "--vault", str(tmp_path), "--json"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        assert payload["ok"] is True
        assert payload["graph"]["wrote"] is True
        assert payload["graph"]["profile"] == "openclaw-memory-v1"

        # Verify the file was written and contains expected keys
        graph_path = tmp_path / ".obsidian" / "graph.json"
        assert graph_path.exists()
        graph_data = json.loads(graph_path.read_text())
        assert "repelStrength" in graph_data
        assert graph_data["repelStrength"] == 10
        assert "colorGroups" in graph_data
        assert len(graph_data["colorGroups"]) == 7
        assert graph_data["linkDistance"] == 120


class TestObsidianOptimizeTextOutput:
    def test_text_format_works(self, tmp_path):
        result = subprocess.run(
            ["python3", SCRIPT, "--vault", str(tmp_path)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "obsidian-memory-optimize" in result.stdout
        assert "ok=true" in result.stdout
