#!/usr/bin/env python3
"""Tests for openclaw-lacp-promote CLI."""

import json
import os
import subprocess
import tempfile
import shutil

import pytest

BIN_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "bin")
PROMOTE_CMD = os.path.join(BIN_DIR, "openclaw-lacp-promote")


def run_cmd(args, env_override=None):
    """Run the CLI command and return result."""
    env = os.environ.copy()
    if env_override:
        env.update(env_override)
    result = subprocess.run(
        [PROMOTE_CMD] + args,
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )
    return result


class TestPromoteHelp:
    """Test help and version commands."""

    def test_help(self):
        result = run_cmd(["--help"])
        assert result.returncode == 0
        assert "openclaw-lacp-promote" in result.stdout

    def test_version(self):
        result = run_cmd(["--version"])
        assert "2.0.0" in result.stdout

    def test_no_args_shows_help(self):
        result = run_cmd([])
        assert result.returncode == 0


class TestPromoteAuto:
    """Test the auto promotion command."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.env = {
            "OPENCLAW_MEMORY_ROOT": os.path.join(self.tmpdir, "memory"),
            "OPENCLAW_VAULT_ROOT": os.path.join(self.tmpdir, "vault"),
            "OPENCLAW_PROMOTIONS_LOG": os.path.join(self.tmpdir, "logs", "promotions.jsonl"),
            "OPENCLAW_PROVENANCE_DIR": os.path.join(self.tmpdir, "provenance"),
        }

    def teardown_method(self):
        shutil.rmtree(self.tmpdir)

    def test_auto_requires_summary(self):
        result = run_cmd(["auto"], env_override=self.env)
        assert result.returncode != 0

    def test_auto_basic(self):
        result = run_cmd(
            ["auto", "--summary", "sum_test123", "--score", "85", "--category", "architectural-decision", "--project", "easy-api"],
            env_override=self.env,
        )
        assert result.returncode == 0
        assert "complete" in result.stdout.lower() or "complete" in result.stderr.lower()

    def test_auto_creates_memory_file(self):
        run_cmd(
            ["auto", "--summary", "sum_mem_test", "--score", "80", "--project", "easy-api"],
            env_override=self.env,
        )
        memory_file = os.path.join(self.tmpdir, "memory", "easy-api", "MEMORY.md")
        assert os.path.exists(memory_file)
        content = open(memory_file).read()
        assert "sum_mem_test" in content

    def test_auto_creates_promotions_log(self):
        run_cmd(
            ["auto", "--summary", "sum_log_test", "--score", "90", "--project", "test"],
            env_override=self.env,
        )
        log_file = os.path.join(self.tmpdir, "logs", "promotions.jsonl")
        assert os.path.exists(log_file)
        with open(log_file) as f:
            line = f.readline()
        data = json.loads(line)
        assert data["summary_id"] == "sum_log_test"
        assert "receipt_hash" in data

    def test_auto_receipt_has_hash(self):
        run_cmd(
            ["auto", "--summary", "sum_hash_test", "--score", "75", "--project", "test"],
            env_override=self.env,
        )
        log_file = os.path.join(self.tmpdir, "logs", "promotions.jsonl")
        with open(log_file) as f:
            data = json.loads(f.readline())
        assert len(data["receipt_hash"]) == 64

    def test_auto_creates_category_file(self):
        run_cmd(
            ["auto", "--summary", "sum_cat_test", "--score", "80",
             "--category", "domain-insight", "--project", "easy-api"],
            env_override=self.env,
        )
        cat_file = os.path.join(self.tmpdir, "memory", "easy-api", "domain-insight.md")
        assert os.path.exists(cat_file)


class TestPromoteManual:
    """Test the manual promotion command."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.env = {
            "OPENCLAW_MEMORY_ROOT": os.path.join(self.tmpdir, "memory"),
            "OPENCLAW_VAULT_ROOT": os.path.join(self.tmpdir, "vault"),
            "OPENCLAW_PROMOTIONS_LOG": os.path.join(self.tmpdir, "logs", "promotions.jsonl"),
            "OPENCLAW_PROVENANCE_DIR": os.path.join(self.tmpdir, "provenance"),
        }

    def teardown_method(self):
        shutil.rmtree(self.tmpdir)

    def test_manual_requires_summary_and_fact(self):
        result = run_cmd(["manual"], env_override=self.env)
        assert result.returncode != 0

    def test_manual_basic(self):
        result = run_cmd(
            ["manual", "--summary", "sum_man1", "--fact", "Brale is settlement layer",
             "--reasoning", "Affects treasury architecture", "--project", "easy-api"],
            env_override=self.env,
        )
        assert result.returncode == 0

    def test_manual_writes_fact(self):
        run_cmd(
            ["manual", "--summary", "sum_man2",
             "--fact", "Finix handles simple payment processing",
             "--project", "easy-api"],
            env_override=self.env,
        )
        memory_file = os.path.join(self.tmpdir, "memory", "easy-api", "MEMORY.md")
        content = open(memory_file).read()
        assert "Finix handles simple payment processing" in content

    def test_manual_score_is_100(self):
        run_cmd(
            ["manual", "--summary", "sum_man3", "--fact", "Test fact", "--project", "test"],
            env_override=self.env,
        )
        log_file = os.path.join(self.tmpdir, "logs", "promotions.jsonl")
        with open(log_file) as f:
            data = json.loads(f.readline())
        assert data["score"] == 100


class TestPromoteList:
    """Test the list command."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.log_file = os.path.join(self.tmpdir, "logs", "promotions.jsonl")
        os.makedirs(os.path.dirname(self.log_file), exist_ok=True)

        # Pre-populate log
        entries = [
            {"summary_id": "sum_1", "category": "arch", "score": 85, "timestamp": "2026-03-18T10:00:00Z", "receipt_hash": "a" * 64},
            {"summary_id": "sum_2", "category": "ops", "score": 70, "timestamp": "2026-03-17T10:00:00Z", "receipt_hash": "b" * 64},
        ]
        with open(self.log_file, "w") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")

        self.env = {
            "OPENCLAW_PROMOTIONS_LOG": self.log_file,
        }

    def teardown_method(self):
        shutil.rmtree(self.tmpdir)

    def test_list_all(self):
        result = run_cmd(["list"], env_override=self.env)
        assert result.returncode == 0
        assert "Total: 2" in result.stdout or "Total: 2" in result.stderr

    def test_list_with_since(self):
        result = run_cmd(["list", "--since", "2026-03-18"], env_override=self.env)
        assert result.returncode == 0

    def test_list_no_log(self):
        env = {"OPENCLAW_PROMOTIONS_LOG": "/nonexistent/promotions.jsonl"}
        result = run_cmd(["list"], env_override=env)
        assert result.returncode == 0


class TestPromoteVerify:
    """Test the verify command."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.log_file = os.path.join(self.tmpdir, "logs", "promotions.jsonl")
        os.makedirs(os.path.dirname(self.log_file), exist_ok=True)

        self.test_hash = "a1b2c3d4e5f6" + "0" * 52
        entry = {
            "summary_id": "sum_verify",
            "receipt_hash": self.test_hash,
            "category": "test",
            "score": 90,
        }
        with open(self.log_file, "w") as f:
            f.write(json.dumps(entry) + "\n")

        self.env = {"OPENCLAW_PROMOTIONS_LOG": self.log_file}

    def teardown_method(self):
        shutil.rmtree(self.tmpdir)

    def test_verify_requires_hash(self):
        result = run_cmd(["verify"], env_override=self.env)
        assert result.returncode != 0

    def test_verify_found(self):
        result = run_cmd(
            ["verify", "--receipt-hash", self.test_hash],
            env_override=self.env,
        )
        assert result.returncode == 0
        assert "VERIFIED" in result.stdout or "VERIFIED" in result.stderr

    def test_verify_not_found(self):
        result = run_cmd(
            ["verify", "--receipt-hash", "nonexistent_hash"],
            env_override=self.env,
        )
        assert result.returncode != 0
