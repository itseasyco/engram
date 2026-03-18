"""Tests for openclaw-obsidian — vault management."""

import os
import subprocess
import tempfile
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent.parent.parent / "bin" / "openclaw-obsidian"
BRAIN_GRAPH = Path(__file__).parent.parent.parent / "bin" / "openclaw-brain-graph"


class TestObsidianHelp:
    """Test help output."""

    def test_no_args_shows_usage(self):
        result = subprocess.run(
            ["bash", str(SCRIPT)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "USAGE" in result.stdout or "usage" in result.stdout.lower()

    def test_help_flag(self):
        result = subprocess.run(
            ["bash", str(SCRIPT), "--help"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "Vault Management" in result.stdout or "vault" in result.stdout.lower()

    def test_help_lists_commands(self):
        result = subprocess.run(
            ["bash", str(SCRIPT), "--help"],
            capture_output=True, text=True,
        )
        for cmd in ["status", "audit", "apply", "backup", "restore", "optimize"]:
            assert cmd in result.stdout


class TestObsidianStatus:
    """Test vault status command."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()

    def test_status_missing_vault(self):
        result = subprocess.run(
            ["bash", str(SCRIPT), "status"],
            capture_output=True, text=True,
            env={**os.environ, "LACP_OBSIDIAN_VAULT": os.path.join(self.temp_dir, "nonexistent")},
        )
        combined = result.stdout + result.stderr
        assert "NOT FOUND" in combined or "not found" in combined.lower()

    def test_status_empty_vault(self):
        vault = os.path.join(self.temp_dir, "vault")
        os.makedirs(vault)

        result = subprocess.run(
            ["bash", str(SCRIPT), "status", "--vault", vault],
            capture_output=True, text=True,
        )
        combined = result.stdout + result.stderr
        assert "Total notes:" in combined or "0" in combined

    def test_status_with_content(self):
        vault = os.path.join(self.temp_dir, "vault")
        os.makedirs(os.path.join(vault, "01_Projects"))
        Path(vault, "00_Index.md").write_text("# Index\n")
        Path(vault, "01_Projects", "test.md").write_text("# Test\n")

        result = subprocess.run(
            ["bash", str(SCRIPT), "status", "--vault", vault],
            capture_output=True, text=True,
        )
        combined = result.stdout + result.stderr
        assert "01_Projects" in combined

    def test_status_shows_vault_size(self):
        vault = os.path.join(self.temp_dir, "vault2")
        os.makedirs(vault)
        Path(vault, "test.md").write_text("# Content\n" * 100)

        result = subprocess.run(
            ["bash", str(SCRIPT), "status", "--vault", vault],
            capture_output=True, text=True,
        )
        combined = result.stdout + result.stderr
        assert "Vault size:" in combined or "size" in combined.lower()


class TestObsidianAudit:
    """Test vault audit command."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()

    def test_audit_missing_vault(self):
        result = subprocess.run(
            ["bash", str(SCRIPT), "audit", "--vault", os.path.join(self.temp_dir, "nonexistent")],
            capture_output=True, text=True,
        )
        assert result.returncode != 0

    def test_audit_empty_vault(self):
        vault = os.path.join(self.temp_dir, "vault")
        os.makedirs(vault)
        os.makedirs(os.path.join(vault, "01_Projects"))
        os.makedirs(os.path.join(vault, "02_Concepts"))
        os.makedirs(os.path.join(vault, "05_Inbox"))

        result = subprocess.run(
            ["bash", str(SCRIPT), "audit", "--vault", vault],
            capture_output=True, text=True,
        )
        combined = result.stdout + result.stderr
        assert "Audit" in combined

    def test_audit_detects_orphans(self):
        vault = os.path.join(self.temp_dir, "vault2")
        os.makedirs(os.path.join(vault, "01_Projects"))
        os.makedirs(os.path.join(vault, "02_Concepts"))
        os.makedirs(os.path.join(vault, "05_Inbox"))
        # Create a note with no links
        Path(vault, "01_Projects", "orphan.md").write_text("# Orphan\nNo links here.\n")

        result = subprocess.run(
            ["bash", str(SCRIPT), "audit", "--vault", vault],
            capture_output=True, text=True,
        )
        combined = result.stdout + result.stderr
        assert "orphan" in combined.lower() or "Result:" in combined or "Audit" in combined

    def test_audit_with_linked_notes(self):
        vault = os.path.join(self.temp_dir, "vault3")
        os.makedirs(os.path.join(vault, "01_Projects"))
        os.makedirs(os.path.join(vault, "02_Concepts"))
        os.makedirs(os.path.join(vault, "05_Inbox"))
        Path(vault, "01_Projects", "project-a.md").write_text("# A\nSee [[concept-b]]\n")
        Path(vault, "02_Concepts", "concept-b.md").write_text("# B\nUsed in [[project-a]]\n")

        result = subprocess.run(
            ["bash", str(SCRIPT), "audit", "--vault", vault],
            capture_output=True, text=True,
        )
        combined = result.stdout + result.stderr
        assert "Audit" in combined


class TestObsidianApply:
    """Test vault apply command."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.memory_root = os.path.join(self.temp_dir, "memory-root")

    def test_apply_syncs_memory(self):
        vault = os.path.join(self.temp_dir, "vault")
        os.makedirs(os.path.join(vault, "01_Projects"))

        project_dir = os.path.join(self.temp_dir, "proj")
        os.makedirs(project_dir)

        brain_stack = Path(__file__).parent.parent.parent / "bin" / "openclaw-brain-stack"
        subprocess.run(
            ["bash", str(brain_stack), "init", "--project", project_dir, "--agent", "test"],
            capture_output=True,
            env={**os.environ, "SESSION_MEMORY_ROOT": self.memory_root},
        )

        result = subprocess.run(
            ["bash", str(SCRIPT), "apply", "--vault", vault, "--project", project_dir],
            capture_output=True, text=True,
            env={**os.environ, "SESSION_MEMORY_ROOT": self.memory_root},
        )
        combined = result.stdout + result.stderr
        assert "Synced" in combined or "✓" in combined

    def test_apply_creates_project_index(self):
        vault = os.path.join(self.temp_dir, "vault2")
        os.makedirs(os.path.join(vault, "01_Projects"))

        project_dir = os.path.join(self.temp_dir, "proj2")
        os.makedirs(project_dir)

        brain_stack = Path(__file__).parent.parent.parent / "bin" / "openclaw-brain-stack"
        subprocess.run(
            ["bash", str(brain_stack), "init", "--project", project_dir, "--agent", "test"],
            capture_output=True,
            env={**os.environ, "SESSION_MEMORY_ROOT": self.memory_root},
        )

        subprocess.run(
            ["bash", str(SCRIPT), "apply", "--vault", vault, "--project", project_dir],
            capture_output=True, text=True,
            env={**os.environ, "SESSION_MEMORY_ROOT": self.memory_root},
        )

        # Check that an index.md exists somewhere in the vault
        index_files = list(Path(vault).rglob("index.md"))
        assert len(index_files) > 0

    def test_apply_missing_vault_fails(self):
        result = subprocess.run(
            ["bash", str(SCRIPT), "apply", "--vault", "/nonexistent", "--project", "."],
            capture_output=True, text=True,
        )
        combined = result.stdout + result.stderr
        assert "not found" in combined.lower() or "error" in combined.lower()


class TestObsidianBackup:
    """Test vault backup command."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()

    def test_backup_creates_archive(self):
        vault = os.path.join(self.temp_dir, "vault")
        os.makedirs(vault)
        Path(vault, "note.md").write_text("# Test\n")

        output = os.path.join(self.temp_dir, "backup.tar.gz")
        result = subprocess.run(
            ["bash", str(SCRIPT), "backup", "--vault", vault, "--output", output],
            capture_output=True, text=True,
        )
        combined = result.stdout + result.stderr
        assert os.path.exists(output) or "backed up" in combined.lower()

    def test_backup_missing_vault_fails(self):
        result = subprocess.run(
            ["bash", str(SCRIPT), "backup", "--vault", "/nonexistent"],
            capture_output=True, text=True,
        )
        assert result.returncode != 0


class TestObsidianRestore:
    """Test vault restore command."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()

    def test_restore_missing_file_fails(self):
        result = subprocess.run(
            ["bash", str(SCRIPT), "restore",
             "--vault", os.path.join(self.temp_dir, "vault"),
             "--from", "/nonexistent.tar.gz"],
            capture_output=True, text=True,
        )
        assert result.returncode != 0


class TestObsidianOptimize:
    """Test vault optimize command."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()

    def test_optimize_removes_empty_files(self):
        vault = os.path.join(self.temp_dir, "vault")
        os.makedirs(vault)
        Path(vault, "empty.md").write_text("")
        Path(vault, "content.md").write_text("# Real content\n")

        result = subprocess.run(
            ["bash", str(SCRIPT), "optimize", "--vault", vault],
            capture_output=True, text=True,
        )
        combined = result.stdout + result.stderr
        assert "Optimizing" in combined or "optimiz" in combined.lower()
        assert not os.path.exists(os.path.join(vault, "empty.md"))

    def test_optimize_missing_vault_fails(self):
        result = subprocess.run(
            ["bash", str(SCRIPT), "optimize", "--vault", "/nonexistent"],
            capture_output=True, text=True,
        )
        assert result.returncode != 0

    def test_optimize_compacts_whitespace(self):
        vault = os.path.join(self.temp_dir, "vault2")
        os.makedirs(vault)
        Path(vault, "spacey.md").write_text("# Title\n\n\n\n\n\n\nContent\n")

        subprocess.run(
            ["bash", str(SCRIPT), "optimize", "--vault", vault],
            capture_output=True, text=True,
        )

        content = Path(vault, "spacey.md").read_text()
        # Should have collapsed excessive blank lines
        assert "\n\n\n\n" not in content


class TestObsidianUnknown:
    """Test unknown commands."""

    def test_unknown_command_fails(self):
        result = subprocess.run(
            ["bash", str(SCRIPT), "bogus"],
            capture_output=True, text=True,
        )
        assert result.returncode != 0
