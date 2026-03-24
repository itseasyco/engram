"""Tests for mode guards on mutation commands."""

import json
import os
import subprocess
from pathlib import Path

import pytest

BIN_DIR = Path(__file__).resolve().parent.parent
BRAIN_RESOLVE = str(BIN_DIR / "openclaw-brain-resolve")
OBSIDIAN_OPTIMIZE = str(BIN_DIR / "openclaw-obsidian-optimize")


class TestBrainResolveBlocked:
    def test_connected_mode_blocks_resolve(self, tmp_path):
        env = os.environ.copy()
        env["LACP_MODE"] = "connected"
        env["OPENCLAW_HOME"] = str(tmp_path)
        result = subprocess.run(
            [
                "python3", BRAIN_RESOLVE,
                "--id", "test",
                "--resolution", "validated",
                "--reason", "test",
                "--vault", str(tmp_path),
                "--json",
            ],
            capture_output=True, text=True, env=env,
        )
        assert result.returncode == 10
        payload = json.loads(result.stdout)
        assert payload["ok"] is False
        assert payload["error"] == "mode_blocked"

    def test_standalone_allows_resolve(self, tmp_path):
        env = os.environ.copy()
        env["LACP_MODE"] = "standalone"
        env["OPENCLAW_HOME"] = str(tmp_path)
        # Will fail with vault_missing (exit 2) but NOT mode_blocked (exit 10)
        result = subprocess.run(
            [
                "python3", BRAIN_RESOLVE,
                "--id", "test",
                "--resolution", "validated",
                "--reason", "test",
                "--vault", "/tmp/nonexistent-guard-test",
                "--json",
            ],
            capture_output=True, text=True, env=env,
        )
        assert result.returncode == 2  # vault_missing, not 10


class TestObsidianOptimizeBlocked:
    def test_connected_mode_blocks_optimize(self, tmp_path):
        env = os.environ.copy()
        env["LACP_MODE"] = "connected"
        env["OPENCLAW_HOME"] = str(tmp_path)
        result = subprocess.run(
            [
                "python3", OBSIDIAN_OPTIMIZE,
                "--vault", str(tmp_path),
                "--json",
            ],
            capture_output=True, text=True, env=env,
        )
        assert result.returncode == 10
        payload = json.loads(result.stdout)
        assert payload["ok"] is False
        assert payload["error"] == "mode_blocked"
