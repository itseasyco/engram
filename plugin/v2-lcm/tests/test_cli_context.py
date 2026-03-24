#!/usr/bin/env python3
"""Tests for openclaw-lacp-context CLI."""

import os
import subprocess
import tempfile
import shutil

import pytest

BIN_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "bin")
CONTEXT_CMD = os.path.join(BIN_DIR, "openclaw-lacp-context")


def run_cmd(args, env_override=None):
    """Run the CLI command and return result."""
    env = os.environ.copy()
    if env_override:
        env.update(env_override)
    result = subprocess.run(
        [CONTEXT_CMD] + args,
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )
    return result


class TestContextHelp:
    """Test help and version commands."""

    def test_help(self):
        result = run_cmd(["--help"])
        assert result.returncode == 0
        assert "openclaw-lacp-context" in result.stdout

    def test_version(self):
        result = run_cmd(["--version"])
        assert "2." in result.stdout  # version 2.x

    def test_no_args_shows_help(self):
        result = run_cmd([])
        assert result.returncode == 0
        assert "COMMANDS" in result.stdout


class TestContextInject:
    """Test the inject command."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.memory_dir = os.path.join(self.tmpdir, "memory", "easy-api")
        self.vault_dir = os.path.join(self.tmpdir, "vault", "easy-api")
        os.makedirs(self.memory_dir, exist_ok=True)
        os.makedirs(self.vault_dir, exist_ok=True)

        # Create test memory files
        with open(os.path.join(self.memory_dir, "MEMORY.md"), "w") as f:
            f.write("# easy-api Memory\n\n")
            f.write("Finix is the payment processor.\n")
            f.write("Brale handles stablecoin settlement.\n")
            f.write("Auth0 manages authentication.\n")

        with open(os.path.join(self.memory_dir, "patterns.md"), "w") as f:
            f.write("# Patterns\n\n")
            f.write("Routes follow /v1/api/<domain>/<resource> convention.\n")

        self.env = {
            "OPENCLAW_MEMORY_ROOT": os.path.join(self.tmpdir, "memory"),
            "OPENCLAW_VAULT_ROOT": os.path.join(self.tmpdir, "vault"),
        }

    def teardown_method(self):
        shutil.rmtree(self.tmpdir)

    def test_inject_requires_project(self):
        result = run_cmd(["inject"], env_override=self.env)
        assert result.returncode != 0

    def test_inject_basic(self):
        result = run_cmd(["inject", "--project", "easy-api"], env_override=self.env)
        assert result.returncode == 0
        assert "Injecting" in result.stderr or "Injecting" in result.stdout

    def test_inject_with_topic(self):
        result = run_cmd(
            ["inject", "--project", "easy-api", "--topic", "payment"],
            env_override=self.env,
        )
        assert result.returncode == 0

    def test_inject_json_format(self):
        result = run_cmd(
            ["inject", "--project", "easy-api", "--format", "json"],
            env_override=self.env,
        )
        assert result.returncode == 0

    def test_inject_markdown_format(self):
        result = run_cmd(
            ["inject", "--project", "easy-api", "--format", "markdown"],
            env_override=self.env,
        )
        assert result.returncode == 0

    def test_inject_empty_project(self):
        result = run_cmd(
            ["inject", "--project", "nonexistent-project"],
            env_override=self.env,
        )
        # Should succeed but with empty results
        assert result.returncode == 0


class TestContextQuery:
    """Test the query command."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.memory_dir = os.path.join(self.tmpdir, "memory", "easy-api")
        os.makedirs(self.memory_dir, exist_ok=True)

        with open(os.path.join(self.memory_dir, "MEMORY.md"), "w") as f:
            f.write("Finix is the payment processor.\n")
            f.write("Settlement happens daily via Brale.\n")

        self.env = {
            "OPENCLAW_MEMORY_ROOT": os.path.join(self.tmpdir, "memory"),
            "OPENCLAW_VAULT_ROOT": os.path.join(self.tmpdir, "vault"),
        }

    def teardown_method(self):
        shutil.rmtree(self.tmpdir)

    def test_query_requires_topic(self):
        result = run_cmd(["query"], env_override=self.env)
        assert result.returncode != 0

    def test_query_basic(self):
        result = run_cmd(["query", "--topic", "payment"], env_override=self.env)
        assert result.returncode == 0

    def test_query_with_project(self):
        result = run_cmd(
            ["query", "--topic", "payment", "--project", "easy-api"],
            env_override=self.env,
        )
        assert result.returncode == 0


class TestContextList:
    """Test the list command."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.memory_dir = os.path.join(self.tmpdir, "memory", "easy-api")
        os.makedirs(self.memory_dir, exist_ok=True)

        with open(os.path.join(self.memory_dir, "MEMORY.md"), "w") as f:
            f.write("# Memory\nSome facts.\n")

        self.env = {
            "OPENCLAW_MEMORY_ROOT": os.path.join(self.tmpdir, "memory"),
            "OPENCLAW_VAULT_ROOT": os.path.join(self.tmpdir, "vault"),
        }

    def teardown_method(self):
        shutil.rmtree(self.tmpdir)

    def test_list_requires_project(self):
        result = run_cmd(["list"], env_override=self.env)
        assert result.returncode != 0

    def test_list_basic(self):
        result = run_cmd(["list", "--project", "easy-api"], env_override=self.env)
        assert result.returncode == 0
        assert "Layer 1" in result.stdout or "Layer 1" in result.stderr

    def test_list_nonexistent_project(self):
        result = run_cmd(["list", "--project", "fake-project"], env_override=self.env)
        assert result.returncode == 0
        assert "not initialized" in result.stdout or "not initialized" in result.stderr
