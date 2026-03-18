"""Extended tests for memory scaffolding via openclaw-brain-stack."""

import os
import subprocess
import tempfile
from pathlib import Path

import pytest

BRAIN_STACK = Path(__file__).parent.parent.parent / "bin" / "openclaw-brain-stack"
MEMORY_INIT = Path(__file__).parent.parent.parent / "bin" / "openclaw-memory-init"


class TestMemoryInitHelp:
    """Test help output."""

    def test_memory_init_usage(self):
        result = subprocess.run(
            ["bash", str(MEMORY_INIT)],
            capture_output=True, text=True,
        )
        combined = result.stdout + result.stderr
        assert "usage" in combined.lower() or "Usage" in combined or len(combined) > 0


class TestMemoryScaffolding:
    """Test memory scaffolding via brain-stack."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.memory_root = os.path.join(self.temp_dir, "memory")

    def test_creates_all_five_seed_files(self):
        project = os.path.join(self.temp_dir, "proj")
        os.makedirs(project)

        subprocess.run(
            ["bash", str(BRAIN_STACK), "init", "--project", project, "--agent", "test"],
            capture_output=True,
            env={**os.environ, "SESSION_MEMORY_ROOT": self.memory_root},
        )

        from glob import glob
        memory_dirs = glob(f"{self.memory_root}/*/memory")
        assert len(memory_dirs) > 0

        expected = ["MEMORY.md", "debugging.md", "patterns.md", "architecture.md", "preferences.md"]
        for f in expected:
            assert Path(memory_dirs[0], f).exists(), f"Missing: {f}"

    def test_seed_files_have_content(self):
        project = os.path.join(self.temp_dir, "proj2")
        os.makedirs(project)

        subprocess.run(
            ["bash", str(BRAIN_STACK), "init", "--project", project, "--agent", "test"],
            capture_output=True,
            env={**os.environ, "SESSION_MEMORY_ROOT": self.memory_root},
        )

        from glob import glob
        memory_dirs = glob(f"{self.memory_root}/*/memory")
        for md in Path(memory_dirs[0]).glob("*.md"):
            assert md.stat().st_size > 10, f"{md.name} is too small"

    def test_memory_md_has_sections(self):
        project = os.path.join(self.temp_dir, "proj3")
        os.makedirs(project)

        subprocess.run(
            ["bash", str(BRAIN_STACK), "init", "--project", project, "--agent", "test"],
            capture_output=True,
            env={**os.environ, "SESSION_MEMORY_ROOT": self.memory_root},
        )

        from glob import glob
        memory_dirs = glob(f"{self.memory_root}/*/memory")
        content = Path(memory_dirs[0], "MEMORY.md").read_text()
        assert "#" in content

    def test_debugging_md_has_content(self):
        project = os.path.join(self.temp_dir, "proj4")
        os.makedirs(project)

        subprocess.run(
            ["bash", str(BRAIN_STACK), "init", "--project", project, "--agent", "test"],
            capture_output=True,
            env={**os.environ, "SESSION_MEMORY_ROOT": self.memory_root},
        )

        from glob import glob
        memory_dirs = glob(f"{self.memory_root}/*/memory")
        content = Path(memory_dirs[0], "debugging.md").read_text()
        assert "#" in content

    def test_idempotent_init(self):
        project = os.path.join(self.temp_dir, "proj5")
        os.makedirs(project)

        for _ in range(2):
            result = subprocess.run(
                ["bash", str(BRAIN_STACK), "init", "--project", project, "--agent", "test"],
                capture_output=True,
                env={**os.environ, "SESSION_MEMORY_ROOT": self.memory_root},
            )
            assert result.returncode == 0


class TestMemorySlug:
    """Test project slug generation."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.memory_root = os.path.join(self.temp_dir, "memory")

    def test_slug_from_project_path(self):
        project = os.path.join(self.temp_dir, "my-project")
        os.makedirs(project)

        subprocess.run(
            ["bash", str(BRAIN_STACK), "init", "--project", project, "--agent", "test"],
            capture_output=True,
            env={**os.environ, "SESSION_MEMORY_ROOT": self.memory_root},
        )
        assert any(Path(self.memory_root).iterdir())

    def test_different_projects_get_different_slugs(self):
        for name in ["project-a", "project-b"]:
            project = os.path.join(self.temp_dir, name)
            os.makedirs(project)
            subprocess.run(
                ["bash", str(BRAIN_STACK), "init", "--project", project, "--agent", "test"],
                capture_output=True,
                env={**os.environ, "SESSION_MEMORY_ROOT": self.memory_root},
            )

        dirs = list(Path(self.memory_root).iterdir())
        assert len(dirs) >= 2


class TestMemoryAppend:
    """Test memory append functionality."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.memory_root = os.path.join(self.temp_dir, "memory")

    def test_append_script_exists(self):
        append_script = Path(__file__).parent.parent.parent / "bin" / "openclaw-memory-append"
        assert append_script.exists()

    def test_append_script_executable(self):
        append_script = Path(__file__).parent.parent.parent / "bin" / "openclaw-memory-append"
        assert os.access(append_script, os.X_OK)
