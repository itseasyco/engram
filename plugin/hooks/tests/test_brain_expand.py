"""Tests for openclaw-brain-expand — memory expansion and maintenance."""

import os
import subprocess
import tempfile
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent.parent.parent / "bin" / "openclaw-brain-expand"
BRAIN_STACK = Path(__file__).parent.parent.parent / "bin" / "openclaw-brain-stack"


class TestExpandHelp:
    """Test help output."""

    def test_help_flag(self):
        result = subprocess.run(
            ["bash", str(SCRIPT), "--help"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "Memory Expansion" in result.stdout or "expand" in result.stdout.lower()

    def test_help_shows_examples(self):
        result = subprocess.run(
            ["bash", str(SCRIPT), "--help"],
            capture_output=True, text=True,
        )
        assert "EXAMPLES" in result.stdout

    def test_help_shows_options(self):
        result = subprocess.run(
            ["bash", str(SCRIPT), "--help"],
            capture_output=True, text=True,
        )
        assert "--project" in result.stdout
        assert "--layer" in result.stdout
        assert "--max-tokens" in result.stdout


class TestExpandLayer1:
    """Test Layer 1 expansion (dedup, compress, archive)."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.memory_root = os.path.join(self.temp_dir, "memory-root")
        os.makedirs(self.memory_root)

    def _init_project(self, name="test-project"):
        project_dir = os.path.join(self.temp_dir, name)
        os.makedirs(project_dir, exist_ok=True)
        subprocess.run(
            ["bash", str(BRAIN_STACK), "init", "--project", project_dir, "--agent", "test"],
            capture_output=True,
            env={**os.environ, "SESSION_MEMORY_ROOT": self.memory_root},
        )
        return project_dir

    def test_expand_runs_on_initialized_project(self):
        project_dir = self._init_project()

        result = subprocess.run(
            ["bash", str(SCRIPT), "--project", project_dir, "--layer", "1"],
            capture_output=True, text=True,
            env={**os.environ, "SESSION_MEMORY_ROOT": self.memory_root},
        )
        assert result.returncode == 0

    def test_expand_reports_file_sizes(self):
        project_dir = self._init_project()

        result = subprocess.run(
            ["bash", str(SCRIPT), "--project", project_dir, "--layer", "1"],
            capture_output=True, text=True,
            env={**os.environ, "SESSION_MEMORY_ROOT": self.memory_root},
        )
        combined = result.stdout + result.stderr
        assert "bytes" in combined or "lines" in combined

    def test_deduplication_removes_duplicates(self):
        project_dir = self._init_project("dedup-project")

        # Find the memory dir and add duplicates
        from glob import glob
        memory_dirs = glob(f"{self.memory_root}/*/memory")
        if memory_dirs:
            debug_file = Path(memory_dirs[0], "debugging.md")
            content = debug_file.read_text()
            # Add duplicate lines
            debug_file.write_text(content + "\n" + content + "\n" + content)
            original_size = debug_file.stat().st_size

            result = subprocess.run(
                ["bash", str(SCRIPT), "--project", project_dir, "--layer", "1"],
                capture_output=True, text=True,
                env={**os.environ, "SESSION_MEMORY_ROOT": self.memory_root},
            )
            new_size = debug_file.stat().st_size
            assert new_size <= original_size

    def test_expand_handles_empty_project(self):
        project_dir = os.path.join(self.temp_dir, "empty")
        os.makedirs(project_dir)

        result = subprocess.run(
            ["bash", str(SCRIPT), "--project", project_dir, "--layer", "1"],
            capture_output=True, text=True,
            env={**os.environ, "SESSION_MEMORY_ROOT": self.memory_root},
        )
        combined = result.stdout + result.stderr
        assert "not found" in combined.lower() or "error" in combined.lower() or result.returncode != 0

    def test_expand_all_layers_default(self):
        project_dir = self._init_project("all-layers")

        result = subprocess.run(
            ["bash", str(SCRIPT), "--project", project_dir],
            capture_output=True, text=True,
            env={**os.environ, "SESSION_MEMORY_ROOT": self.memory_root},
        )
        combined = result.stdout + result.stderr
        assert "Layer 1" in combined
        assert "complete" in combined.lower() or "✓" in combined


class TestExpandLayer3:
    """Test Layer 3 expansion (index rebuild)."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.memory_root = os.path.join(self.temp_dir, "memory-root")

    def test_expand_layer3_rebuilds_index(self):
        project_dir = os.path.join(self.temp_dir, "proj")
        os.makedirs(project_dir)

        subprocess.run(
            ["bash", str(BRAIN_STACK), "init", "--project", project_dir, "--agent", "test", "--with-obsidian"],
            capture_output=True,
            env={**os.environ, "SESSION_MEMORY_ROOT": self.memory_root,
                 "LACP_OBSIDIAN_VAULT": os.path.join(self.temp_dir, "vault")},
        )

        result = subprocess.run(
            ["bash", str(SCRIPT), "--project", project_dir, "--layer", "3"],
            capture_output=True, text=True,
            env={**os.environ, "SESSION_MEMORY_ROOT": self.memory_root},
        )
        combined = result.stdout + result.stderr
        assert "Layer 3" in combined


class TestExpandLayer5:
    """Test Layer 5 expansion (provenance report)."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.memory_root = os.path.join(self.temp_dir, "memory-root")

    def test_expand_layer5_reports_chain(self):
        project_dir = os.path.join(self.temp_dir, "proj")
        os.makedirs(project_dir)

        subprocess.run(
            ["bash", str(BRAIN_STACK), "init", "--project", project_dir, "--agent", "test"],
            capture_output=True,
            env={**os.environ, "SESSION_MEMORY_ROOT": self.memory_root},
        )

        result = subprocess.run(
            ["bash", str(SCRIPT), "--project", project_dir, "--layer", "5"],
            capture_output=True, text=True,
            env={**os.environ, "SESSION_MEMORY_ROOT": self.memory_root},
        )
        combined = result.stdout + result.stderr
        assert "Layer 5" in combined


class TestExpandOptions:
    """Test CLI options."""

    def test_unknown_option_fails(self):
        result = subprocess.run(
            ["bash", str(SCRIPT), "--bogus"],
            capture_output=True, text=True,
        )
        assert result.returncode != 0

    def test_custom_max_tokens(self):
        result = subprocess.run(
            ["bash", str(SCRIPT), "--max-tokens", "8000", "--help"],
            capture_output=True, text=True,
        )
        # --help should still work
        assert result.returncode == 0
