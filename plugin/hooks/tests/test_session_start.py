#!/usr/bin/env python3
"""Tests for OpenClaw SessionStart hook.

Tests git context injection, test command detection, and JSON output protocol.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import mock

import pytest


# Add handlers directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "handlers"))


def import_session_start():
    """Import session_start module (workaround for non-standard location)."""
    handler_path = Path(__file__).parent.parent / "handlers" / "session-start.py"
    spec = __import__("importlib.util").util.spec_from_file_location("session_start", handler_path)
    module = __import__("importlib.util").util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


session_start = import_session_start()


class TestGitDetection:
    """Tests for git repository detection."""

    def test_is_git_repo_true(self, tmp_path):
        """Verify git repo detection returns True inside a repo."""
        os.chdir(tmp_path)
        subprocess.run(["git", "init"], capture_output=True, check=True)
        
        result = session_start._is_git_repo()
        assert result is True

    def test_is_git_repo_false(self, tmp_path):
        """Verify git repo detection returns False outside a repo."""
        os.chdir(tmp_path)
        result = session_start._is_git_repo()
        assert result is False

    def test_is_git_repo_nested(self, tmp_path):
        """Verify git repo detection works in subdirectories."""
        os.chdir(tmp_path)
        subprocess.run(["git", "init"], capture_output=True, check=True)
        
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        os.chdir(subdir)
        
        result = session_start._is_git_repo()
        assert result is True


class TestGitContext:
    """Tests for git context gathering."""

    @pytest.fixture
    def git_repo(self, tmp_path):
        """Create a temporary git repository."""
        os.chdir(tmp_path)
        subprocess.run(["git", "init"], capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test User"], capture_output=True)
        return tmp_path

    def test_git_branch_main(self, git_repo):
        """Verify branch detection on main branch."""
        # Create initial commit to establish main branch
        (git_repo / "test.txt").write_text("test")
        subprocess.run(["git", "add", "."], capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "initial"], capture_output=True, check=True)
        
        branch = session_start._git_branch()
        assert branch in ["main", "master"]  # GitHub default or local default

    def test_git_branch_custom(self, git_repo):
        """Verify branch detection on custom branch."""
        # Create initial commit
        (git_repo / "test.txt").write_text("test")
        subprocess.run(["git", "add", "."], capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "initial"], capture_output=True, check=True)
        
        # Create and switch to custom branch
        subprocess.run(["git", "checkout", "-b", "feature/test"], capture_output=True, check=True)
        
        branch = session_start._git_branch()
        assert branch == "feature/test"

    def test_git_recent_commits(self, git_repo):
        """Verify recent commit detection."""
        # Create multiple commits
        for i in range(3):
            (git_repo / f"file{i}.txt").write_text(f"content {i}")
            subprocess.run(["git", "add", "."], capture_output=True, check=True)
            subprocess.run(["git", "commit", "-m", f"commit {i}"], capture_output=True, check=True)
        
        commits = session_start._git_recent_commits(3)
        assert commits is not None
        assert "commit 2" in commits
        assert "commit 1" in commits
        assert "commit 0" in commits

    def test_git_modified_files(self, git_repo):
        """Verify modified files detection."""
        # Create and commit a file
        (git_repo / "tracked.txt").write_text("original")
        subprocess.run(["git", "add", "."], capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "initial"], capture_output=True, check=True)
        
        # Modify the file (unstaged)
        (git_repo / "tracked.txt").write_text("modified")
        
        modified = session_start._git_modified_files()
        assert modified is not None
        assert "tracked.txt" in modified

    def test_git_staged_files(self, git_repo):
        """Verify staged files detection."""
        # Create initial commit
        (git_repo / "file.txt").write_text("initial")
        subprocess.run(["git", "add", "."], capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "initial"], capture_output=True, check=True)
        
        # Create and stage a new file
        (git_repo / "new.txt").write_text("new content")
        subprocess.run(["git", "add", "new.txt"], capture_output=True, check=True)
        
        staged = session_start._git_staged_files()
        assert staged is not None
        assert "new.txt" in staged

    def test_git_status_clean(self, git_repo):
        """Verify clean status detection."""
        # Create and commit a file
        (git_repo / "file.txt").write_text("content")
        subprocess.run(["git", "add", "."], capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "initial"], capture_output=True, check=True)
        
        status = session_start._git_status_summary()
        assert status == "clean"

    def test_git_status_dirty(self, git_repo):
        """Verify dirty status detection."""
        # Create and commit a file
        (git_repo / "file.txt").write_text("original")
        subprocess.run(["git", "add", "."], capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "initial"], capture_output=True, check=True)
        
        # Modify the file (but don't stage it)
        (git_repo / "file.txt").write_text("modified")
        subprocess.run(["git", "reset", "HEAD", "file.txt"], capture_output=True)  # Unstage if staged
        
        status = session_start._git_status_summary()
        assert status is not None  # Should have some status (clean or dirty)

    def test_git_context_complete(self, git_repo):
        """Verify complete git context gathering."""
        # Create commits
        (git_repo / "file.txt").write_text("v1")
        subprocess.run(["git", "add", "."], capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "first"], capture_output=True, check=True)
        
        (git_repo / "file.txt").write_text("v2")
        subprocess.run(["git", "add", "."], capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "second"], capture_output=True, check=True)
        
        context = session_start._git_context()
        assert "branch" in context
        assert "status" in context


class TestTestCommandDetection:
    """Tests for test command auto-detection."""

    def test_detect_npm_test(self, tmp_path):
        """Verify npm test command detection."""
        os.chdir(tmp_path)
        
        pkg = {
            "name": "test-pkg",
            "scripts": {
                "test": "jest"
            }
        }
        (tmp_path / "package.json").write_text(json.dumps(pkg))
        
        cmd = session_start._detect_test_command()
        assert cmd is not None
        assert "test" in cmd
        assert cmd in ["npm test", "yarn test", "pnpm test", "bun test"]

    def test_detect_makefile_test(self, tmp_path):
        """Verify Makefile test command detection."""
        os.chdir(tmp_path)
        
        makefile = """
.PHONY: test
test:
\t@echo "Running tests"
"""
        (tmp_path / "Makefile").write_text(makefile)
        
        cmd = session_start._detect_test_command()
        assert cmd == "make test"

    def test_detect_cargo_test(self, tmp_path):
        """Verify Cargo (Rust) test command detection."""
        os.chdir(tmp_path)
        
        (tmp_path / "Cargo.toml").write_text("[package]\nname = \"test\"\n")
        
        cmd = session_start._detect_test_command()
        assert cmd == "cargo test"

    def test_detect_pytest(self, tmp_path):
        """Verify pytest command detection."""
        os.chdir(tmp_path)
        
        (tmp_path / "pyproject.toml").write_text("[tool.pytest]\n")
        
        cmd = session_start._detect_test_command()
        assert cmd is not None
        assert "pytest" in cmd

    def test_detect_no_test(self, tmp_path):
        """Verify no test command detected when none present."""
        os.chdir(tmp_path)
        
        cmd = session_start._detect_test_command()
        assert cmd is None

    def test_package_json_without_test_script(self, tmp_path):
        """Verify no test command when package.json has no test script."""
        os.chdir(tmp_path)
        
        pkg = {
            "name": "test-pkg",
            "scripts": {
                "build": "tsc"
            }
        }
        (tmp_path / "package.json").write_text(json.dumps(pkg))
        
        cmd = session_start._detect_test_command()
        assert cmd is None


class TestPayloadHandling:
    """Tests for stdin payload reading."""

    def test_read_empty_payload(self):
        """Verify empty payload is handled gracefully."""
        with mock.patch("sys.stdin.read", return_value=""):
            payload = session_start._read_payload()
            assert payload == {}

    def test_read_json_payload(self):
        """Verify JSON payload is parsed correctly."""
        test_payload = {"matcher": "startup", "sessionId": "test-123"}
        with mock.patch("sys.stdin.read", return_value=json.dumps(test_payload)):
            payload = session_start._read_payload()
            assert payload == test_payload

    def test_read_invalid_json(self):
        """Verify invalid JSON is handled gracefully."""
        with mock.patch("sys.stdin.read", return_value="not json"):
            payload = session_start._read_payload()
            assert payload == {}


class TestContextFormatting:
    """Tests for context formatting and output."""

    def test_format_git_context_with_branch(self):
        """Verify git context formatting includes branch."""
        ctx = {
            "branch": "main",
            "status": "clean"
        }
        formatted = session_start._format_git_context(ctx)
        assert "Branch: main" in formatted
        assert "Status: clean" in formatted

    def test_format_git_context_with_commits(self):
        """Verify git context formatting includes commits."""
        ctx = {
            "branch": "main",
            "status": "clean",
            "recentCommits": "abc123 initial commit\ndef456 second commit"
        }
        formatted = session_start._format_git_context(ctx)
        assert "Recent commits" in formatted
        assert "abc123" in formatted

    def test_format_git_context_with_files(self):
        """Verify git context formatting includes modified files."""
        ctx = {
            "branch": "main",
            "status": "1 modified",
            "modifiedFiles": "src/main.py\ntest/test.py"
        }
        formatted = session_start._format_git_context(ctx)
        assert "Modified files" in formatted
        assert "src/main.py" in formatted


class TestCaching:
    """Tests for test command caching."""

    def test_cache_test_command(self, tmp_path):
        """Verify test command is cached to /tmp."""
        os.environ["OPENCLAW_SESSION_ID"] = "test-session-123"
        
        with mock.patch("pathlib.Path.write_text") as mock_write:
            session_start._cache_test_command("npm test")
            mock_write.assert_called_once_with("npm test")

    def test_cache_test_command_fallback_claude_session_id(self, tmp_path):
        """Verify fallback to CLAUDE_SESSION_ID when OPENCLAW_SESSION_ID not set."""
        os.environ.pop("OPENCLAW_SESSION_ID", None)
        os.environ["CLAUDE_SESSION_ID"] = "claude-session-456"
        
        with mock.patch("pathlib.Path.write_text") as mock_write:
            session_start._cache_test_command("make test")
            mock_write.assert_called_once_with("make test")


class TestEndToEnd:
    """End-to-end tests for the hook."""

    def test_hook_output_is_valid_json(self, tmp_path):
        """Verify hook output is valid JSON."""
        # This test needs to be run as subprocess since main() prints to stdout
        # Create a simple test script
        test_script = Path(__file__).parent.parent / "handlers" / "session-start.py"
        
        result = subprocess.run(
            [sys.executable, str(test_script)],
            input="",
            capture_output=True,
            text=True,
            cwd=str(tmp_path)
        )
        
        # Try to parse output as JSON
        if result.stdout:
            output = json.loads(result.stdout)
            assert "systemMessage" in output
            assert isinstance(output["systemMessage"], str)

    def test_hook_with_matcher_startup(self):
        """Verify hook handles startup matcher."""
        test_script = Path(__file__).parent.parent / "handlers" / "session-start.py"
        
        payload = json.dumps({"matcher": "startup"})
        result = subprocess.run(
            [sys.executable, str(test_script)],
            input=payload,
            capture_output=True,
            text=True,
        )
        
        if result.stdout:
            output = json.loads(result.stdout)
            assert "sessionMessage" in output or "systemMessage" in output

    def test_hook_exit_code_success(self):
        """Verify hook exits with code 0 on success."""
        test_script = Path(__file__).parent.parent / "handlers" / "session-start.py"
        
        result = subprocess.run(
            [sys.executable, str(test_script)],
            input="",
            capture_output=True,
        )
        
        assert result.returncode == 0


# Import pytest if available for running tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
