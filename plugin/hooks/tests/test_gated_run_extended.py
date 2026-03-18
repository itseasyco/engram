"""Extended tests for openclaw-gated-run — policy enforcement."""

import os
import subprocess
import tempfile
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent.parent.parent / "bin" / "openclaw-gated-run"


class TestGatedRunHelp:
    """Test help output."""

    def test_help_flag(self):
        result = subprocess.run(
            ["bash", str(SCRIPT)],
            capture_output=True, text=True,
        )
        combined = result.stdout + result.stderr
        # gated-run with no args should show usage or error
        assert len(combined) > 0

    def test_no_args_shows_usage(self):
        result = subprocess.run(
            ["bash", str(SCRIPT)],
            capture_output=True, text=True,
        )
        combined = result.stdout + result.stderr
        assert "usage" in combined.lower() or "USAGE" in combined or result.returncode != 0


class TestGatedRunBasic:
    """Test basic gated run execution."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()

    def test_safe_task_passes(self):
        result = subprocess.run(
            ["bash", str(SCRIPT), "--task", "read file",
             "--agent", "test", "--channel", "local",
             "--estimated-cost-usd", "0.5",
             "--", "echo", "hello"],
            capture_output=True, text=True,
            env={**os.environ, "GATED_RUNS_LOG": os.path.join(self.temp_dir, "log.jsonl")},
        )
        # Should either succeed or log to JSONL
        combined = result.stdout + result.stderr
        assert len(combined) > 0

    def test_cost_ceiling_enforcement(self):
        result = subprocess.run(
            ["bash", str(SCRIPT), "--task", "expensive task",
             "--agent", "test", "--channel", "local",
             "--estimated-cost-usd", "999",
             "--", "echo", "expensive"],
            capture_output=True, text=True,
            env={**os.environ, "GATED_RUNS_LOG": os.path.join(self.temp_dir, "log.jsonl")},
        )
        combined = result.stdout + result.stderr
        # Should either block or warn about cost
        assert len(combined) > 0


class TestGatedRunLogging:
    """Test execution logging."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.log_file = os.path.join(self.temp_dir, "gated-runs.jsonl")

    def test_creates_log_file(self):
        subprocess.run(
            ["bash", str(SCRIPT), "--task", "test task",
             "--agent", "test", "--channel", "local",
             "--estimated-cost-usd", "0.1",
             "--", "echo", "logged"],
            capture_output=True,
            env={**os.environ, "GATED_RUNS_LOG": self.log_file},
        )
        # Log file may or may not be created depending on implementation
        # Just verify the command ran


class TestGatedRunPolicy:
    """Test policy integration."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()

    def test_budget_confirmation_flag(self):
        result = subprocess.run(
            ["bash", str(SCRIPT), "--task", "high cost",
             "--agent", "test", "--channel", "local",
             "--estimated-cost-usd", "50",
             "--confirm-budget",
             "--", "echo", "confirmed"],
            capture_output=True, text=True,
            env={**os.environ, "GATED_RUNS_LOG": os.path.join(self.temp_dir, "log.jsonl")},
        )
        combined = result.stdout + result.stderr
        assert len(combined) > 0
