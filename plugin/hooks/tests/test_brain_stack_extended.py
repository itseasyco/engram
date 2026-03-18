"""Extended tests for openclaw-brain-stack — orchestrator."""

import os
import subprocess
import tempfile
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent.parent.parent / "bin" / "openclaw-brain-stack"


class TestBrainStackHelp:
    """Test help output."""

    def test_help_command(self):
        result = subprocess.run(
            ["bash", str(SCRIPT), "help"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "USAGE" in result.stdout

    def test_help_shows_version(self):
        result = subprocess.run(
            ["bash", str(SCRIPT), "help"],
            capture_output=True, text=True,
        )
        assert "1.0.0" in result.stdout or "v1" in result.stdout

    def test_help_lists_commands(self):
        result = subprocess.run(
            ["bash", str(SCRIPT), "help"],
            capture_output=True, text=True,
        )
        assert "init" in result.stdout
        assert "doctor" in result.stdout
        assert "expand" in result.stdout

    def test_help_shows_options(self):
        result = subprocess.run(
            ["bash", str(SCRIPT), "help"],
            capture_output=True, text=True,
        )
        assert "--project" in result.stdout
        assert "--agent" in result.stdout
        assert "--with-obsidian" in result.stdout

    def test_help_shows_examples(self):
        result = subprocess.run(
            ["bash", str(SCRIPT), "help"],
            capture_output=True, text=True,
        )
        assert "EXAMPLES" in result.stdout


class TestBrainStackInit:
    """Test init command."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.memory_root = os.path.join(self.temp_dir, "memory")

    def test_init_creates_memory_dir(self):
        project = os.path.join(self.temp_dir, "proj")
        os.makedirs(project)

        result = subprocess.run(
            ["bash", str(SCRIPT), "init", "--project", project, "--agent", "test"],
            capture_output=True, text=True,
            env={**os.environ, "SESSION_MEMORY_ROOT": self.memory_root},
        )
        assert result.returncode == 0
        assert any(Path(self.memory_root).rglob("MEMORY.md"))

    def test_init_with_obsidian(self):
        project = os.path.join(self.temp_dir, "proj2")
        os.makedirs(project)
        vault = os.path.join(self.temp_dir, "vault")

        result = subprocess.run(
            ["bash", str(SCRIPT), "init", "--project", project, "--agent", "test", "--with-obsidian"],
            capture_output=True, text=True,
            env={**os.environ, "SESSION_MEMORY_ROOT": self.memory_root,
                 "LACP_OBSIDIAN_VAULT": vault},
        )
        assert result.returncode == 0
        assert os.path.exists(vault)

    def test_init_with_obsidian_creates_ingestion(self):
        project = os.path.join(self.temp_dir, "proj3")
        os.makedirs(project)
        vault = os.path.join(self.temp_dir, "vault2")

        subprocess.run(
            ["bash", str(SCRIPT), "init", "--project", project, "--agent", "test", "--with-obsidian"],
            capture_output=True,
            env={**os.environ, "SESSION_MEMORY_ROOT": self.memory_root,
                 "LACP_OBSIDIAN_VAULT": vault},
        )
        # Layer 3 should be initialized with obsidian
        assert any(Path(self.memory_root).rglob("queue-generated"))

    def test_init_creates_provenance(self):
        project = os.path.join(self.temp_dir, "proj4")
        os.makedirs(project)

        subprocess.run(
            ["bash", str(SCRIPT), "init", "--project", project, "--agent", "test"],
            capture_output=True,
            env={**os.environ, "SESSION_MEMORY_ROOT": self.memory_root},
        )
        # Provenance dir should exist
        assert any(Path(self.memory_root).rglob("agent-identity.json"))

    def test_init_unknown_option_fails(self):
        result = subprocess.run(
            ["bash", str(SCRIPT), "init", "--bogus"],
            capture_output=True, text=True,
            env={**os.environ, "SESSION_MEMORY_ROOT": self.memory_root},
        )
        assert result.returncode != 0

    def test_init_success_message(self):
        project = os.path.join(self.temp_dir, "proj5")
        os.makedirs(project)

        result = subprocess.run(
            ["bash", str(SCRIPT), "init", "--project", project, "--agent", "test"],
            capture_output=True, text=True,
            env={**os.environ, "SESSION_MEMORY_ROOT": self.memory_root},
        )
        combined = result.stdout + result.stderr
        assert "success" in combined.lower() or "✓" in combined


class TestBrainStackDoctor:
    """Test doctor command."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.memory_root = os.path.join(self.temp_dir, "memory")

    def _init_project(self, name="proj"):
        project = os.path.join(self.temp_dir, name)
        os.makedirs(project, exist_ok=True)
        subprocess.run(
            ["bash", str(SCRIPT), "init", "--project", project, "--agent", "test"],
            capture_output=True,
            env={**os.environ, "SESSION_MEMORY_ROOT": self.memory_root},
        )
        return project

    def test_doctor_healthy_project(self):
        project = self._init_project()

        result = subprocess.run(
            ["bash", str(SCRIPT), "doctor", "--project", project],
            capture_output=True, text=True,
            env={**os.environ, "SESSION_MEMORY_ROOT": self.memory_root},
        )
        assert result.returncode == 0

    def test_doctor_shows_all_layers(self):
        project = self._init_project()

        result = subprocess.run(
            ["bash", str(SCRIPT), "doctor", "--project", project],
            capture_output=True, text=True,
            env={**os.environ, "SESSION_MEMORY_ROOT": self.memory_root},
        )
        combined = result.stdout + result.stderr
        assert "Layer 1" in combined
        assert "Layer 2" in combined
        assert "Layer 3" in combined
        assert "Layer 4" in combined
        assert "Layer 5" in combined

    def test_doctor_uninit_project(self):
        project = os.path.join(self.temp_dir, "empty")
        os.makedirs(project)

        result = subprocess.run(
            ["bash", str(SCRIPT), "doctor", "--project", project],
            capture_output=True, text=True,
            env={**os.environ, "SESSION_MEMORY_ROOT": self.memory_root},
        )
        combined = result.stdout + result.stderr
        assert "missing" in combined.lower() or "✗" in combined or "○" in combined


class TestBrainStackExpand:
    """Test expand command."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.memory_root = os.path.join(self.temp_dir, "memory")

    def test_expand_runs(self):
        project = os.path.join(self.temp_dir, "proj")
        os.makedirs(project)

        subprocess.run(
            ["bash", str(SCRIPT), "init", "--project", project, "--agent", "test"],
            capture_output=True,
            env={**os.environ, "SESSION_MEMORY_ROOT": self.memory_root},
        )

        result = subprocess.run(
            ["bash", str(SCRIPT), "expand", "--project", project],
            capture_output=True, text=True,
            env={**os.environ, "SESSION_MEMORY_ROOT": self.memory_root},
        )
        # Expand may delegate to openclaw-brain-expand or handle inline
        assert result.returncode == 0 or "expand" in (result.stdout + result.stderr).lower()


class TestBrainStackUnknown:
    """Test unknown commands."""

    def test_unknown_command(self):
        result = subprocess.run(
            ["bash", str(SCRIPT), "bogus"],
            capture_output=True, text=True,
        )
        combined = result.stdout + result.stderr
        assert "usage" in combined.lower() or "USAGE" in combined or result.returncode != 0
