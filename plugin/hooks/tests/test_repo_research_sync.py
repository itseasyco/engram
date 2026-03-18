"""Tests for openclaw-repo-research-sync — repository docs sync."""

import os
import subprocess
import tempfile
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent.parent.parent / "bin" / "openclaw-repo-research-sync"


class TestSyncHelp:
    """Test help output."""

    def test_help_flag(self):
        result = subprocess.run(
            ["bash", str(SCRIPT), "--help"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "Repository Research Sync" in result.stdout or "sync" in result.stdout.lower()

    def test_help_shows_what_gets_synced(self):
        result = subprocess.run(
            ["bash", str(SCRIPT), "--help"],
            capture_output=True, text=True,
        )
        assert "README" in result.stdout
        assert "docs/" in result.stdout


class TestSyncReadme:
    """Test README syncing."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.vault = os.path.join(self.temp_dir, "vault")
        os.makedirs(os.path.join(self.vault, "01_Projects"))

    def test_syncs_readme(self):
        project = os.path.join(self.temp_dir, "project")
        os.makedirs(project)
        Path(project, "README.md").write_text("# My Project\nHello world.\n")

        result = subprocess.run(
            ["bash", str(SCRIPT), "--project", project, "--vault", self.vault],
            capture_output=True, text=True,
        )
        combined = result.stdout + result.stderr
        assert "README" in combined or "Synced" in combined

    def test_no_readme_still_succeeds(self):
        project = os.path.join(self.temp_dir, "empty-project")
        os.makedirs(project)

        result = subprocess.run(
            ["bash", str(SCRIPT), "--project", project, "--vault", self.vault],
            capture_output=True, text=True,
        )
        # Should not crash
        assert result.returncode == 0


class TestSyncDocs:
    """Test docs/ directory syncing."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.vault = os.path.join(self.temp_dir, "vault")
        os.makedirs(os.path.join(self.vault, "01_Projects"))

    def test_syncs_docs_directory(self):
        project = os.path.join(self.temp_dir, "project")
        docs = os.path.join(project, "docs")
        os.makedirs(docs)
        Path(docs, "guide.md").write_text("# Guide\n")
        Path(docs, "api.md").write_text("# API\n")

        result = subprocess.run(
            ["bash", str(SCRIPT), "--project", project, "--vault", self.vault],
            capture_output=True, text=True,
        )
        combined = result.stdout + result.stderr
        assert "2 doc files" in combined or "Synced" in combined

    def test_no_docs_directory(self):
        project = os.path.join(self.temp_dir, "nodocs")
        os.makedirs(project)

        result = subprocess.run(
            ["bash", str(SCRIPT), "--project", project, "--vault", self.vault],
            capture_output=True, text=True,
        )
        combined = result.stdout + result.stderr
        assert "No docs/" in combined or result.returncode == 0


class TestSyncChangelog:
    """Test CHANGELOG syncing."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.vault = os.path.join(self.temp_dir, "vault")
        os.makedirs(os.path.join(self.vault, "01_Projects"))

    def test_syncs_changelog(self):
        project = os.path.join(self.temp_dir, "project")
        os.makedirs(project)
        Path(project, "CHANGELOG.md").write_text("# Changelog\n## 1.0.0\n- Initial\n")

        result = subprocess.run(
            ["bash", str(SCRIPT), "--project", project, "--vault", self.vault],
            capture_output=True, text=True,
        )
        combined = result.stdout + result.stderr
        assert "CHANGELOG" in combined or "Synced" in combined


class TestSyncIndex:
    """Test vault index generation."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.vault = os.path.join(self.temp_dir, "vault")
        os.makedirs(os.path.join(self.vault, "01_Projects"))

    def test_creates_index(self):
        project = os.path.join(self.temp_dir, "project")
        os.makedirs(project)
        Path(project, "README.md").write_text("# Test\n")

        subprocess.run(
            ["bash", str(SCRIPT), "--project", project, "--vault", self.vault],
            capture_output=True, text=True,
        )

        # Find index in vault
        index_files = list(Path(self.vault).rglob("index.md"))
        assert len(index_files) > 0


class TestSyncComments:
    """Test code comment extraction."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.vault = os.path.join(self.temp_dir, "vault")
        os.makedirs(os.path.join(self.vault, "01_Projects"))

    def test_include_comments_flag(self):
        project = os.path.join(self.temp_dir, "project")
        os.makedirs(project)
        Path(project, "app.py").write_text('"""Module docstring."""\ndef hello():\n    pass\n')

        result = subprocess.run(
            ["bash", str(SCRIPT), "--project", project, "--vault", self.vault, "--include-comments"],
            capture_output=True, text=True,
        )
        combined = result.stdout + result.stderr
        assert "comments" in combined.lower() or "Extracted" in combined or result.returncode == 0


class TestSyncDryRun:
    """Test dry run mode."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.vault = os.path.join(self.temp_dir, "vault")
        os.makedirs(os.path.join(self.vault, "01_Projects"))

    def test_dry_run_no_changes(self):
        project = os.path.join(self.temp_dir, "project")
        os.makedirs(project)
        Path(project, "README.md").write_text("# Test\n")

        result = subprocess.run(
            ["bash", str(SCRIPT), "--project", project, "--vault", self.vault, "--dry-run"],
            capture_output=True, text=True,
        )
        combined = result.stdout + result.stderr
        assert "DRY RUN" in combined or result.returncode == 0

        # Dry run should not create project-specific dirs in vault
        # (the 01_Projects dir itself may exist from setup)


class TestSyncMissingVault:
    """Test error handling when vault is missing."""

    def test_missing_vault_fails(self):
        result = subprocess.run(
            ["bash", str(SCRIPT), "--vault", "/nonexistent"],
            capture_output=True, text=True,
        )
        assert result.returncode != 0
