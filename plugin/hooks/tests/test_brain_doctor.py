"""Tests for openclaw-brain-doctor — comprehensive health check."""

import os
import json
import subprocess
import tempfile
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent.parent.parent / "bin" / "openclaw-brain-doctor"


class TestDoctorHelp:
    """Test help and usage output."""

    def test_help_flag(self):
        result = subprocess.run(
            ["bash", str(SCRIPT), "--help"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "Health Check" in result.stdout or "health check" in result.stdout.lower()

    def test_help_command(self):
        result = subprocess.run(
            ["bash", str(SCRIPT), "help"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0

    def test_version_in_output(self):
        result = subprocess.run(
            ["bash", str(SCRIPT), "--help"],
            capture_output=True, text=True,
        )
        assert "1.0.0" in result.stdout

    def test_shows_usage_examples(self):
        result = subprocess.run(
            ["bash", str(SCRIPT), "--help"],
            capture_output=True, text=True,
        )
        assert "EXAMPLES" in result.stdout


class TestDoctorLayer1:
    """Test Layer 1 health checks."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.memory_root = os.path.join(self.temp_dir, "memory-root")
        os.makedirs(self.memory_root)

    def _init_project(self, project_dir):
        brain_stack = Path(__file__).parent.parent.parent / "bin" / "openclaw-brain-stack"
        subprocess.run(
            ["bash", str(brain_stack), "init", "--project", project_dir, "--agent", "test"],
            capture_output=True,
            env={**os.environ, "SESSION_MEMORY_ROOT": self.memory_root},
        )

    def test_layer1_all_files_present(self):
        project_dir = os.path.join(self.temp_dir, "test-project")
        os.makedirs(project_dir)
        self._init_project(project_dir)

        result = subprocess.run(
            ["bash", str(SCRIPT), "--project", project_dir, "--layer", "1"],
            capture_output=True, text=True,
            env={**os.environ, "SESSION_MEMORY_ROOT": self.memory_root},
        )
        combined = result.stdout + result.stderr
        assert "MEMORY.md" in combined
        assert "debugging.md" in combined
        assert "patterns.md" in combined

    def test_layer1_missing_files_detected(self):
        project_dir = os.path.join(self.temp_dir, "empty-project")
        os.makedirs(project_dir)

        result = subprocess.run(
            ["bash", str(SCRIPT), "--project", project_dir, "--layer", "1"],
            capture_output=True, text=True,
            env={**os.environ, "SESSION_MEMORY_ROOT": self.memory_root},
        )
        combined = result.stdout + result.stderr
        assert "missing" in combined.lower() or "✗" in combined

    def test_layer1_verbose_shows_paths(self):
        project_dir = os.path.join(self.temp_dir, "test-project2")
        os.makedirs(project_dir)
        self._init_project(project_dir)

        result = subprocess.run(
            ["bash", str(SCRIPT), "--project", project_dir, "--layer", "1", "--verbose"],
            capture_output=True, text=True,
            env={**os.environ, "SESSION_MEMORY_ROOT": self.memory_root},
        )
        combined = result.stdout + result.stderr
        assert "Memory root:" in combined or "Slug:" in combined

    def test_layer1_empty_file_warning(self):
        project_dir = os.path.join(self.temp_dir, "empty-files")
        os.makedirs(project_dir)
        self._init_project(project_dir)

        # Make one file empty
        from glob import glob
        memory_dirs = glob(f"{self.memory_root}/*/memory")
        if memory_dirs:
            Path(memory_dirs[0], "debugging.md").write_text("")

        result = subprocess.run(
            ["bash", str(SCRIPT), "--project", project_dir, "--layer", "1"],
            capture_output=True, text=True,
            env={**os.environ, "SESSION_MEMORY_ROOT": self.memory_root},
        )
        combined = result.stdout + result.stderr
        assert "empty" in combined.lower() or "○" in combined or "0 bytes" in combined


class TestDoctorLayer2:
    """Test Layer 2 health checks."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()

    def test_layer2_vault_missing(self):
        result = subprocess.run(
            ["bash", str(SCRIPT), "--layer", "2"],
            capture_output=True, text=True,
            env={**os.environ, "LACP_OBSIDIAN_VAULT": os.path.join(self.temp_dir, "nonexistent")},
        )
        combined = result.stdout + result.stderr
        assert "not found" in combined.lower() or "○" in combined

    def test_layer2_vault_present(self):
        vault = os.path.join(self.temp_dir, "vault")
        os.makedirs(vault)
        os.makedirs(os.path.join(vault, "01_Projects"))
        os.makedirs(os.path.join(vault, "02_Concepts"))
        os.makedirs(os.path.join(vault, "05_Inbox"))

        result = subprocess.run(
            ["bash", str(SCRIPT), "--layer", "2"],
            capture_output=True, text=True,
            env={**os.environ, "LACP_OBSIDIAN_VAULT": vault},
        )
        combined = result.stdout + result.stderr
        assert "✓" in combined

    def test_layer2_missing_structure_warned(self):
        vault = os.path.join(self.temp_dir, "vault2")
        os.makedirs(vault)
        # No subdirectories

        result = subprocess.run(
            ["bash", str(SCRIPT), "--layer", "2"],
            capture_output=True, text=True,
            env={**os.environ, "LACP_OBSIDIAN_VAULT": vault},
        )
        combined = result.stdout + result.stderr
        assert "missing" in combined.lower() or "○" in combined


class TestDoctorLayer3:
    """Test Layer 3 health checks."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.memory_root = os.path.join(self.temp_dir, "memory-root")

    def test_layer3_pipeline_missing(self):
        project_dir = os.path.join(self.temp_dir, "proj")
        os.makedirs(project_dir)

        result = subprocess.run(
            ["bash", str(SCRIPT), "--project", project_dir, "--layer", "3"],
            capture_output=True, text=True,
            env={**os.environ, "SESSION_MEMORY_ROOT": self.memory_root},
        )
        combined = result.stdout + result.stderr
        assert "missing" in combined.lower() or "✗" in combined

    def test_layer3_pipeline_present(self):
        project_dir = os.path.join(self.temp_dir, "proj2")
        os.makedirs(project_dir)

        brain_stack = Path(__file__).parent.parent.parent / "bin" / "openclaw-brain-stack"
        subprocess.run(
            ["bash", str(brain_stack), "init", "--project", project_dir, "--agent", "test", "--with-obsidian"],
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
        assert "queue-generated" in combined or "✓" in combined


class TestDoctorLayer5:
    """Test Layer 5 health checks."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.memory_root = os.path.join(self.temp_dir, "memory-root")
        self.provenance_root = os.path.join(self.temp_dir, "provenance")

    def test_layer5_no_chain(self):
        project_dir = os.path.join(self.temp_dir, "proj")
        os.makedirs(project_dir)

        result = subprocess.run(
            ["bash", str(SCRIPT), "--project", project_dir, "--layer", "5"],
            capture_output=True, text=True,
            env={**os.environ,
                 "SESSION_MEMORY_ROOT": self.memory_root,
                 "PROVENANCE_ROOT": self.provenance_root},
        )
        combined = result.stdout + result.stderr
        assert "Provenance" in combined or "Layer 5" in combined

    def test_layer5_with_chain(self):
        project_dir = os.path.join(self.temp_dir, "proj2")
        os.makedirs(project_dir)

        # Init the whole stack
        brain_stack = Path(__file__).parent.parent.parent / "bin" / "openclaw-brain-stack"
        subprocess.run(
            ["bash", str(brain_stack), "init", "--project", project_dir, "--agent", "test"],
            capture_output=True,
            env={**os.environ, "SESSION_MEMORY_ROOT": self.memory_root,
                 "PROVENANCE_ROOT": self.provenance_root},
        )

        result = subprocess.run(
            ["bash", str(SCRIPT), "--project", project_dir, "--layer", "5"],
            capture_output=True, text=True,
            env={**os.environ,
                 "SESSION_MEMORY_ROOT": self.memory_root,
                 "PROVENANCE_ROOT": self.provenance_root},
        )
        combined = result.stdout + result.stderr
        assert "Layer 5" in combined or "Provenance" in combined


class TestDoctorSummary:
    """Test full doctor summary."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.memory_root = os.path.join(self.temp_dir, "memory-root")

    def test_full_check_returns_zero_when_healthy(self):
        project_dir = os.path.join(self.temp_dir, "proj")
        os.makedirs(project_dir)

        brain_stack = Path(__file__).parent.parent.parent / "bin" / "openclaw-brain-stack"
        subprocess.run(
            ["bash", str(brain_stack), "init", "--project", project_dir, "--agent", "test", "--with-obsidian"],
            capture_output=True,
            env={**os.environ, "SESSION_MEMORY_ROOT": self.memory_root,
                 "LACP_OBSIDIAN_VAULT": os.path.join(self.temp_dir, "vault")},
        )

        result = subprocess.run(
            ["bash", str(SCRIPT), "--project", project_dir],
            capture_output=True, text=True,
            env={**os.environ, "SESSION_MEMORY_ROOT": self.memory_root,
                 "LACP_OBSIDIAN_VAULT": os.path.join(self.temp_dir, "vault")},
        )
        assert result.returncode == 0

    def test_summary_shows_timestamp(self):
        project_dir = os.path.join(self.temp_dir, "proj2")
        os.makedirs(project_dir)

        brain_stack = Path(__file__).parent.parent.parent / "bin" / "openclaw-brain-stack"
        subprocess.run(
            ["bash", str(brain_stack), "init", "--project", project_dir, "--agent", "test"],
            capture_output=True,
            env={**os.environ, "SESSION_MEMORY_ROOT": self.memory_root},
        )

        result = subprocess.run(
            ["bash", str(SCRIPT), "--project", project_dir],
            capture_output=True, text=True,
            env={**os.environ, "SESSION_MEMORY_ROOT": self.memory_root},
        )
        combined = result.stdout + result.stderr
        assert "Checked:" in combined or "2026" in combined

    def test_unknown_option_exits_nonzero(self):
        result = subprocess.run(
            ["bash", str(SCRIPT), "--invalid-flag"],
            capture_output=True, text=True,
        )
        assert result.returncode != 0


class TestDoctorConfig:
    """Test configuration checks."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()

    def test_config_section_present(self):
        result = subprocess.run(
            ["bash", str(SCRIPT)],
            capture_output=True, text=True,
            env={**os.environ, "SESSION_MEMORY_ROOT": os.path.join(self.temp_dir, "mem")},
        )
        combined = result.stdout + result.stderr
        assert "Configuration" in combined or "Config" in combined


class TestDoctorMCP:
    """Test MCP connectivity checks."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()

    def test_mcp_section_present(self):
        result = subprocess.run(
            ["bash", str(SCRIPT)],
            capture_output=True, text=True,
            env={**os.environ, "SESSION_MEMORY_ROOT": os.path.join(self.temp_dir, "mem")},
        )
        combined = result.stdout + result.stderr
        assert "MCP" in combined
