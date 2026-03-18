#!/usr/bin/env python3
"""Tests for openclaw-lacp-share CLI (Phase B stubs)."""

import os
import subprocess

import pytest

BIN_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "bin")
SHARE_CMD = os.path.join(BIN_DIR, "openclaw-lacp-share")


def run_cmd(args):
    """Run the CLI command and return result."""
    result = subprocess.run(
        [SHARE_CMD] + args,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return result


class TestShareHelp:
    """Test help and version."""

    def test_help(self):
        result = run_cmd(["--help"])
        assert result.returncode == 0
        assert "Phase B" in result.stdout

    def test_version(self):
        result = run_cmd(["--version"])
        assert "2.0.0" in result.stdout


class TestShareStubs:
    """Test that all stub commands work and indicate Phase B."""

    def test_list_available_stub(self):
        result = run_cmd(["list-available", "--from", "wren"])
        assert result.returncode == 0
        assert "Phase B" in result.stdout or "Phase B" in result.stderr

    def test_query_stub(self):
        result = run_cmd(["query", "--from", "wren", "--topic", "settlement"])
        assert result.returncode == 0
        assert "Phase B" in result.stdout or "Phase B" in result.stderr

    def test_grant_access_stub(self):
        result = run_cmd(["grant-access", "--agent", "wren", "--to", "zoe"])
        assert result.returncode == 0
        assert "Phase B" in result.stdout or "Phase B" in result.stderr

    def test_unknown_command(self):
        result = run_cmd(["nonexistent"])
        assert result.returncode == 0  # shows help

    def test_stub_mentions_v2_1(self):
        result = run_cmd(["list-available", "--from", "test"])
        combined = result.stdout + result.stderr
        assert "v2.1.0" in combined or "Phase B" in combined
