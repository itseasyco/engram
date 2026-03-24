#!/usr/bin/env python3
"""Tests for the LCM ↔ LACP Cross-Reference Linker."""

import json
import os
import sys
import tempfile
import shutil

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from lcm_lacp_linker import LCMLACPLinker, link_summary_to_vault


class TestTopicExtraction:
    """Test topic extraction from LCM summaries."""

    def setup_method(self):
        self.linker = LCMLACPLinker()

    def test_extract_tags(self):
        summary = {"content": "This relates to #architecture and #deployment."}
        topics = self.linker.extract_topics(summary)
        assert "architecture" in topics
        assert "deployment" in topics

    def test_extract_wikilinks(self):
        summary = {"content": "See [[Finix Integration]] and [[Treasury Design]]."}
        topics = self.linker.extract_topics(summary)
        assert "Finix Integration" in topics
        assert "Treasury Design" in topics

    def test_extract_technical_terms(self):
        summary = {"content": "The easy-api and payment-session modules."}
        topics = self.linker.extract_topics(summary)
        found = [t for t in topics if "easy-api" in t or "payment-session" in t]
        assert len(found) >= 1

    def test_filter_stopwords(self):
        summary = {"content": "The system works. This is important. When ready."}
        topics = self.linker.extract_topics(summary)
        for t in topics:
            assert t not in {"The", "This", "When"}

    def test_deduplicate(self):
        summary = {"content": "#architecture #architecture [[architecture]]"}
        topics = self.linker.extract_topics(summary)
        lower_topics = [t.lower() for t in topics]
        assert lower_topics.count("architecture") == 1

    def test_max_30_topics(self):
        content = " ".join([f"#topic{i}" for i in range(50)])
        topics = self.linker.extract_topics({"content": content})
        assert len(topics) <= 30

    def test_empty_content(self):
        topics = self.linker.extract_topics({"content": ""})
        assert topics == []

    def test_short_terms_filtered(self):
        summary = {"content": "#ab #a #abc"}
        topics = self.linker.extract_topics(summary)
        for t in topics:
            assert len(t) > 2


class TestFindRelatedNotes:
    """Test finding related vault notes."""

    def setup_method(self):
        self.vault_dir = tempfile.mkdtemp()
        self.linker = LCMLACPLinker(vault_path=self.vault_dir)

        # Create test notes
        os.makedirs(os.path.join(self.vault_dir, "projects"), exist_ok=True)
        with open(os.path.join(self.vault_dir, "projects", "finix-integration.md"), "w") as f:
            f.write("# Finix Integration\nPayment processing via Finix API.\n")
        with open(os.path.join(self.vault_dir, "projects", "treasury-design.md"), "w") as f:
            f.write("# Treasury Design\nSettlement architecture for Brale.\n")
        with open(os.path.join(self.vault_dir, "projects", "unrelated.md"), "w") as f:
            f.write("# Unrelated Topic\nNothing about payments.\n")

    def teardown_method(self):
        shutil.rmtree(self.vault_dir)

    def test_find_by_filename(self):
        results = self.linker.find_related_notes(["finix"])
        titles = [r["title"] for r in results]
        assert "finix-integration" in titles

    def test_find_by_content(self):
        results = self.linker.find_related_notes(["Brale"])
        titles = [r["title"] for r in results]
        assert "treasury-design" in titles

    def test_score_ordering(self):
        results = self.linker.find_related_notes(["finix", "payment"])
        if len(results) >= 2:
            assert results[0]["score"] >= results[1]["score"]

    def test_max_results(self):
        results = self.linker.find_related_notes(["payment", "finix", "treasury"], max_results=1)
        assert len(results) <= 1

    def test_no_vault(self):
        linker = LCMLACPLinker(vault_path="/nonexistent/vault")
        results = linker.find_related_notes(["anything"])
        assert results == []

    def test_matched_topics_populated(self):
        results = self.linker.find_related_notes(["finix"])
        for r in results:
            if r["title"] == "finix-integration":
                assert len(r["matched_topics"]) >= 1


class TestCrossReferences:
    """Test cross-reference creation."""

    def setup_method(self):
        self.linker = LCMLACPLinker()

    def test_create_refs(self):
        summary = {"summary_id": "sum_test123", "content": "Test."}
        notes = [
            {"path": "projects/finix.md", "title": "finix", "score": 3, "matched_topics": ["finix"]},
        ]
        refs = self.linker.create_cross_references(summary, notes)
        assert len(refs) == 1
        assert refs[0]["summary_id"] == "sum_test123"
        assert refs[0]["direction"] == "bidirectional"
        assert "link_hash" in refs[0]

    def test_ref_has_required_fields(self):
        summary = {"summary_id": "sum_xyz"}
        notes = [{"path": "a.md", "title": "a", "score": 1, "matched_topics": ["x"]}]
        refs = self.linker.create_cross_references(summary, notes)
        ref = refs[0]
        assert "summary_id" in ref
        assert "note_path" in ref
        assert "note_title" in ref
        assert "direction" in ref
        assert "confidence" in ref
        assert "created_at" in ref
        assert "link_hash" in ref

    def test_confidence_capped_at_1(self):
        summary = {"summary_id": "sum_test"}
        notes = [{"path": "a.md", "title": "a", "score": 100, "matched_topics": []}]
        refs = self.linker.create_cross_references(summary, notes)
        assert refs[0]["confidence"] <= 1.0

    def test_multiple_notes(self):
        summary = {"summary_id": "sum_multi"}
        notes = [
            {"path": "a.md", "title": "a", "score": 2, "matched_topics": ["x"]},
            {"path": "b.md", "title": "b", "score": 1, "matched_topics": ["y"]},
        ]
        refs = self.linker.create_cross_references(summary, notes)
        assert len(refs) == 2

    def test_facts_passed_through(self):
        summary = {"summary_id": "sum_facts"}
        notes = [{"path": "a.md", "title": "a", "score": 1, "matched_topics": []}]
        refs = self.linker.create_cross_references(summary, notes, facts=["Fact A", "Fact B"])
        assert refs[0]["facts"] == ["Fact A", "Fact B"]

    def test_links_stored_in_session(self):
        summary = {"summary_id": "sum_session"}
        notes = [{"path": "a.md", "title": "a", "score": 1, "matched_topics": []}]
        self.linker.create_cross_references(summary, notes)
        assert len(self.linker.get_links()) == 1


class TestLinkVerification:
    """Test cross-reference verification."""

    def setup_method(self):
        self.linker = LCMLACPLinker()

    def test_verify_valid_link(self):
        summary = {"summary_id": "sum_verify"}
        notes = [{"path": "a.md", "title": "a", "score": 1, "matched_topics": []}]
        refs = self.linker.create_cross_references(summary, notes)
        assert self.linker.verify_link(refs[0]) is True

    def test_verify_tampered_link(self):
        summary = {"summary_id": "sum_tamper"}
        notes = [{"path": "a.md", "title": "a", "score": 1, "matched_topics": []}]
        refs = self.linker.create_cross_references(summary, notes)
        refs[0]["link_hash"] = "tampered_hash_value"
        assert self.linker.verify_link(refs[0]) is False

    def test_verify_missing_hash(self):
        ref = {"summary_id": "x", "note_path": "a.md", "created_at": "2026-01-01"}
        assert self.linker.verify_link(ref) is False


class TestWriteLinks:
    """Test writing links to vault notes."""

    def setup_method(self):
        self.vault_dir = tempfile.mkdtemp()
        self.linker = LCMLACPLinker(vault_path=self.vault_dir)
        os.makedirs(os.path.join(self.vault_dir, "projects"), exist_ok=True)
        with open(os.path.join(self.vault_dir, "projects", "test.md"), "w") as f:
            f.write("# Test Note\nSome content.\n")

    def teardown_method(self):
        shutil.rmtree(self.vault_dir)

    def test_write_link_appends(self):
        result = self.linker.write_lcm_to_lacp_link("projects/test.md", "sum_xyz", "abc123")
        assert result is True
        content = open(os.path.join(self.vault_dir, "projects", "test.md")).read()
        assert "sum_xyz" in content
        assert "abc123" in content

    def test_write_link_nonexistent_file(self):
        result = self.linker.write_lcm_to_lacp_link("nonexistent.md", "sum_xyz", "abc")
        assert result is False


class TestSummaryNoteGeneration:
    """Test Obsidian note generation."""

    def setup_method(self):
        self.linker = LCMLACPLinker()

    def test_generates_markdown(self):
        summary = {
            "summary_id": "sum_note_test",
            "content": "Finix handles payments.",
            "project": "easy-api",
            "timestamp": "2026-03-18T10:00:00Z",
        }
        refs = [
            {
                "note_title": "Finix Integration",
                "confidence": 0.8,
                "matched_topics": ["finix", "payment"],
            }
        ]
        note = self.linker.generate_summary_note(summary, refs)
        assert "# LCM Summary: sum_note_test" in note
        assert "easy-api" in note
        assert "[[Finix Integration]]" in note
        assert "v2.1.0" in note

    def test_empty_refs(self):
        summary = {"summary_id": "sum_empty", "content": "Test.", "project": "test"}
        note = self.linker.generate_summary_note(summary, [])
        assert "## Cross-References" in note


class TestLogLinks:
    """Test link logging."""

    def setup_method(self):
        self.log_dir = tempfile.mkdtemp()
        self.log_path = os.path.join(self.log_dir, "linker.jsonl")
        self.linker = LCMLACPLinker(log_path=self.log_path)

    def teardown_method(self):
        shutil.rmtree(self.log_dir)

    def test_log_creates_file(self):
        refs = [{"summary_id": "sum_log", "note_path": "a.md", "link_hash": "abc"}]
        result = self.linker.log_links(refs)
        assert result is True
        assert os.path.exists(self.log_path)

    def test_log_content_is_jsonl(self):
        refs = [
            {"summary_id": "sum_1", "link_hash": "h1"},
            {"summary_id": "sum_2", "link_hash": "h2"},
        ]
        self.linker.log_links(refs)
        with open(self.log_path) as f:
            lines = f.readlines()
        assert len(lines) == 2
        for line in lines:
            parsed = json.loads(line)
            assert "summary_id" in parsed


class TestConvenienceFunction:
    """Test the link_summary_to_vault convenience function."""

    def setup_method(self):
        self.vault_dir = tempfile.mkdtemp()
        self.log_dir = tempfile.mkdtemp()
        self.log_path = os.path.join(self.log_dir, "linker.jsonl")

        # Create a vault note
        os.makedirs(os.path.join(self.vault_dir, "projects"), exist_ok=True)
        with open(os.path.join(self.vault_dir, "projects", "finix.md"), "w") as f:
            f.write("# Finix\nPayment processing.\n")

    def teardown_method(self):
        shutil.rmtree(self.vault_dir)
        shutil.rmtree(self.log_dir)

    def test_end_to_end(self):
        result = link_summary_to_vault(
            summary={
                "summary_id": "sum_e2e",
                "content": "Finix handles payment processing for all merchants.",
                "project": "easy-api",
            },
            vault_path=self.vault_dir,
            log_path=self.log_path,
        )
        assert "topics" in result
        assert "related_notes" in result
        assert "cross_references" in result
        assert "summary_note" in result
        assert "link_count" in result

    def test_empty_vault(self):
        empty_vault = tempfile.mkdtemp()
        result = link_summary_to_vault(
            summary={"summary_id": "sum_empty", "content": "Test."},
            vault_path=empty_vault,
            log_path=self.log_path,
        )
        assert result["link_count"] == 0
        shutil.rmtree(empty_vault)
