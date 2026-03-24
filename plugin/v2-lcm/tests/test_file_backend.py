#!/usr/bin/env python3
"""Tests for FileBackend with tmp directories."""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backends"))

from backends.file_backend import FileBackend


# ---------------------------------------------------------------------------
# Init
# ---------------------------------------------------------------------------

class TestFileBackendInit:
    """Constructor and config handling."""

    def test_init_with_defaults(self):
        backend = FileBackend({})
        assert backend._threshold == 70
        assert backend._files is None

    def test_init_with_custom_vault_path(self, tmp_path):
        vault = tmp_path / "vault"
        backend = FileBackend({"vaultPath": str(vault)})
        assert str(backend._vault_path) == str(vault)

    def test_init_with_custom_memory_root(self, tmp_path):
        memory = tmp_path / "memory"
        backend = FileBackend({"memoryRoot": str(memory)})
        assert str(backend._memory_root) == str(memory)

    def test_init_with_files_list(self):
        backend = FileBackend({"files": ["/a.md", "/b.md"]})
        assert backend._files == ["/a.md", "/b.md"]

    def test_init_files_none_by_default(self):
        backend = FileBackend({})
        assert backend._files is None

    def test_init_custom_threshold(self):
        backend = FileBackend({"promotionThreshold": 85})
        assert backend._threshold == 85


# ---------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------

class TestFileBackendAvailability:
    """is_available is always True."""

    def test_always_returns_true(self):
        assert FileBackend({}).is_available() is True

    def test_true_even_with_bad_paths(self):
        backend = FileBackend({"vaultPath": "/nonexistent", "memoryRoot": "/nonexistent"})
        assert backend.is_available() is True

    def test_backend_name(self):
        assert FileBackend({}).backend_name() == "file"


# ---------------------------------------------------------------------------
# fetch_summary
# ---------------------------------------------------------------------------

class TestFetchSummary:
    """fetch_summary searches explicit files, memory root, and vault."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path):
        self.memory = tmp_path / "memory"
        self.memory.mkdir()
        (self.memory / "session-abc.md").write_text(
            "# Session ABC\nThis is summary SUM-MEMORY-001.\n"
        )

        self.vault = tmp_path / "vault"
        self.vault.mkdir()
        (self.vault / "note.md").write_text(
            "Vault note referencing SUM-VAULT-001 here.\n"
        )
        (self.vault / "sum.json").write_text(json.dumps({
            "summary_id": "SUM-JSON-001",
            "content": "JSON summary about treasury",
        }))

        self.explicit = tmp_path / "explicit.md"
        self.explicit.write_text("Explicit file with SUM-EXPLICIT-001.\n")

        self.backend = FileBackend({
            "memoryRoot": str(self.memory),
            "vaultPath": str(self.vault),
            "files": [str(self.explicit)],
        })

    def test_finds_in_explicit_files(self):
        result = self.backend.fetch_summary("SUM-EXPLICIT-001")
        assert result != {}
        assert result["summary_id"] == "SUM-EXPLICIT-001"

    def test_finds_in_memory_root_md(self):
        result = self.backend.fetch_summary("SUM-MEMORY-001")
        assert result != {}
        assert result["summary_id"] == "SUM-MEMORY-001"

    def test_finds_in_vault_md(self):
        result = self.backend.fetch_summary("SUM-VAULT-001")
        assert result != {}
        assert result["summary_id"] == "SUM-VAULT-001"

    def test_finds_in_json_file(self):
        result = self.backend.fetch_summary("SUM-JSON-001")
        assert result != {}
        assert result["summary_id"] == "SUM-JSON-001"
        assert "treasury" in result.get("content", "")

    def test_returns_empty_when_not_found(self):
        assert self.backend.fetch_summary("NO-SUCH-SUMMARY") == {}


# ---------------------------------------------------------------------------
# discover_summaries
# ---------------------------------------------------------------------------

class TestDiscoverSummaries:
    """discover_summaries from various sources with filters."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path):
        self.memory = tmp_path / "memory"
        self.memory.mkdir()

        proj = self.memory / "easy-api"
        proj.mkdir()
        (proj / "s1.json").write_text(json.dumps({
            "summary_id": "s1", "content": "First summary",
            "timestamp": "2026-03-10T10:00:00Z",
        }))
        (proj / "s2.json").write_text(json.dumps({
            "summary_id": "s2", "content": "Second summary",
            "timestamp": "2026-03-18T10:00:00Z",
        }))
        (self.memory / "general.md").write_text(
            "# General Notes\n\nSome substantial content for testing discovery.\n"
        )

        self.vault = tmp_path / "vault"
        self.vault.mkdir()
        (self.vault / "vault-note.md").write_text(
            "# Vault Note\n\nSubstantial vault content that should be discovered.\n"
        )

        self.backend = FileBackend({
            "memoryRoot": str(self.memory),
            "vaultPath": str(self.vault),
            "files": [],
        })

    def test_from_memory_root(self):
        results = self.backend.discover_summaries({})
        assert len(results) >= 1

    def test_filtered_by_project(self):
        results = self.backend.discover_summaries({"project": "easy-api"})
        ids = [r.get("summary_id") for r in results]
        assert "s1" in ids and "s2" in ids

    def test_filtered_by_since(self):
        results = self.backend.discover_summaries({"since": "2026-03-15"})
        for r in results:
            ts = r.get("timestamp", "")
            if ts:
                assert ts >= "2026-03-15"

    def test_filtered_by_until(self):
        results = self.backend.discover_summaries({"until": "2026-03-12"})
        for r in results:
            ts = r.get("timestamp", "")
            if ts:
                assert ts <= "2026-03-12"

    def test_limit(self):
        results = self.backend.discover_summaries({"limit": 1})
        assert len(results) <= 1

    def test_empty_results_with_nonexistent_paths(self):
        backend = FileBackend({
            "vaultPath": "/nonexistent",
            "memoryRoot": "/also/nonexistent",
        })
        results = backend.discover_summaries({})
        assert results == []

    def test_sorted_by_timestamp_descending(self):
        results = self.backend.discover_summaries({})
        timestamps = [r.get("timestamp", "") for r in results]
        assert timestamps == sorted(timestamps, reverse=True)

    def test_deduplicates_by_summary_id(self):
        results = self.backend.discover_summaries({})
        ids = [r.get("summary_id") for r in results]
        assert len(ids) == len(set(ids))


# ---------------------------------------------------------------------------
# find_context
# ---------------------------------------------------------------------------

class TestFindContext:
    """find_context keyword-based search."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path):
        self.memory = tmp_path / "memory"
        self.memory.mkdir()
        (self.memory / "treasury.md").write_text(
            "# Treasury Design\n\nSettlement flow for Brale integration and Finix payments.\n"
        )
        (self.memory / "marketing.md").write_text(
            "# Marketing Plan\n\nSocial media campaigns and content strategy.\n"
        )

        self.vault = tmp_path / "vault"
        self.vault.mkdir()
        (self.vault / "auth.md").write_text(
            "# Authentication\n\nAuth0 handles authentication for the dashboard.\n"
        )

        self.backend = FileBackend({
            "memoryRoot": str(self.memory),
            "vaultPath": str(self.vault),
            "files": [],
        })

    def test_keyword_search_in_vault(self):
        results = self.backend.find_context("authentication dashboard")
        assert len(results) >= 1

    def test_keyword_search_in_memory(self):
        results = self.backend.find_context("treasury settlement")
        assert len(results) >= 1
        ids = [r["summary_id"] for r in results]
        assert "treasury" in ids

    def test_keyword_search_in_explicit_files(self, tmp_path):
        explicit = tmp_path / "notes.md"
        explicit.write_text("Treasury operations and settlement details.\n")
        backend = FileBackend({
            "vaultPath": "/nonexistent",
            "memoryRoot": "/nonexistent",
            "files": [str(explicit)],
        })
        results = backend.find_context("treasury settlement")
        assert len(results) > 0

    def test_empty_task_returns_empty(self):
        assert self.backend.find_context("") == []

    def test_respects_limit(self):
        results = self.backend.find_context("treasury settlement authentication", limit=1)
        assert len(results) <= 1

    def test_source_is_file(self):
        results = self.backend.find_context("treasury")
        for r in results:
            assert r["source"] == "file"

    def test_results_sorted_by_score_descending(self):
        results = self.backend.find_context("treasury settlement Brale Finix")
        if len(results) > 1:
            scores = [r["relevance_score"] for r in results]
            assert scores == sorted(scores, reverse=True)

    def test_relevance_score_is_float(self):
        results = self.backend.find_context("treasury")
        for r in results:
            assert isinstance(r["relevance_score"], float)

    def test_no_matches(self):
        results = self.backend.find_context("quantum blockchain")
        assert results == []


# ---------------------------------------------------------------------------
# traverse_dag
# ---------------------------------------------------------------------------

class TestTraverseDag:
    """File backend traverse_dag returns single-node chain."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path):
        self.memory = tmp_path / "memory"
        self.memory.mkdir()
        (self.memory / "note.md").write_text(
            "# Note\n\nContent referencing SUM-TRAV-001 for testing.\n"
        )

        self.backend = FileBackend({
            "memoryRoot": str(self.memory),
            "vaultPath": str(tmp_path / "vault"),
            "files": [],
        })

    def test_returns_single_node_chain(self):
        result = self.backend.traverse_dag("SUM-TRAV-001")
        assert len(result["chain"]) == 1
        assert result["depth_reached"] == 0
        assert result["root"] != {}

    def test_returns_empty_for_missing(self):
        result = self.backend.traverse_dag("NONEXISTENT")
        assert result["chain"] == []
        assert result["root"] == {}
        assert result["depth_reached"] == -1

    def test_result_has_required_keys(self):
        result = self.backend.traverse_dag("SUM-TRAV-001")
        assert "root" in result
        assert "chain" in result
        assert "depth_reached" in result


# ---------------------------------------------------------------------------
# _extract_keywords
# ---------------------------------------------------------------------------

class TestExtractKeywords:
    """Private _extract_keywords helper."""

    def setup_method(self):
        self.backend = FileBackend({})

    def test_filters_stopwords(self):
        keywords = self.backend._extract_keywords("the payment is for a settlement")
        assert "the" not in keywords
        assert "is" not in keywords

    def test_short_words_filtered(self):
        keywords = self.backend._extract_keywords("ab cd treasury")
        assert "ab" not in keywords
        assert "treasury" in keywords

    def test_multiple_words_extracted(self):
        keywords = self.backend._extract_keywords("payment processor handles settlement")
        assert "payment" in keywords
        assert "processor" in keywords
        assert "settlement" in keywords

    def test_empty_input(self):
        assert self.backend._extract_keywords("") == []


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

class TestLoadJsonFile:
    """Private _load_json_file helper."""

    def setup_method(self):
        self.backend = FileBackend({})

    def test_loads_valid_json(self, tmp_path):
        f = tmp_path / "valid.json"
        f.write_text(json.dumps({"key": "value"}))
        assert self.backend._load_json_file(str(f)) == {"key": "value"}

    def test_handles_invalid_json(self, tmp_path):
        f = tmp_path / "invalid.json"
        f.write_text("not json at all {{{")
        assert self.backend._load_json_file(str(f)) == {}

    def test_handles_missing_file(self):
        assert self.backend._load_json_file("/nonexistent/file.json") == {}

    def test_handles_non_dict_json(self, tmp_path):
        f = tmp_path / "array.json"
        f.write_text(json.dumps([1, 2, 3]))
        assert self.backend._load_json_file(str(f)) == {}


class TestParseMdAsSummary:
    """Private _parse_md_as_summary helper."""

    def setup_method(self):
        self.backend = FileBackend({})

    def test_parses_valid_md(self, tmp_path):
        f = tmp_path / "note.md"
        f.write_text("# Title\n\nSome content that is long enough to pass the minimum.\n")
        result = self.backend._parse_md_as_summary(str(f))
        assert result != {}
        assert result["summary_id"] == "note"
        assert result["source"] == "file"
        assert "timestamp" in result

    def test_skips_short_content(self, tmp_path):
        f = tmp_path / "tiny.md"
        f.write_text("hi")
        assert self.backend._parse_md_as_summary(str(f)) == {}

    def test_handles_missing_file(self):
        assert self.backend._parse_md_as_summary("/nonexistent/file.md") == {}

    def test_content_truncated_to_2000(self, tmp_path):
        f = tmp_path / "long.md"
        f.write_text("x" * 5000)
        result = self.backend._parse_md_as_summary(str(f))
        assert len(result["content"]) <= 2000
