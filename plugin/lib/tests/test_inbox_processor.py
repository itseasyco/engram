"""Tests for inbox processor."""

from pathlib import Path

import pytest

from plugin.lib.inbox_processor import (
    classify_note,
    process_inbox,
    _infer_category,
    _infer_trust_from_queue,
)


def _make_note(tmp_path, queue_name, filename, frontmatter="", body="# Note\n\nContent."):
    """Create a note in a queue folder."""
    inbox = tmp_path / "05_Inbox" / queue_name
    inbox.mkdir(parents=True, exist_ok=True)
    content = ""
    if frontmatter:
        content = f"---\n{frontmatter}\n---\n\n"
    content += body
    note = inbox / filename
    note.write_text(content, encoding="utf-8")
    return note


class TestInferTrustFromQueue:
    def test_agent_queue_returns_high(self, tmp_path):
        path = tmp_path / "05_Inbox" / "queue-agent" / "note.md"
        assert _infer_trust_from_queue(path) == "high"

    def test_cicd_queue_returns_verified(self, tmp_path):
        path = tmp_path / "05_Inbox" / "queue-cicd" / "note.md"
        assert _infer_trust_from_queue(path) == "verified"

    def test_human_queue_returns_medium(self, tmp_path):
        path = tmp_path / "05_Inbox" / "queue-human" / "note.md"
        assert _infer_trust_from_queue(path) == "medium"

    def test_external_queue_returns_low(self, tmp_path):
        path = tmp_path / "05_Inbox" / "queue-external" / "note.md"
        assert _infer_trust_from_queue(path) == "low"

    def test_unknown_queue_returns_medium(self, tmp_path):
        path = tmp_path / "05_Inbox" / "queue-misc" / "note.md"
        assert _infer_trust_from_queue(path) == "medium"


class TestInferCategory:
    def test_deployment_keywords_map_to_systems(self):
        assert _infer_category("Deployment Guide", "kubernetes docker pipeline", []) == "systems"

    def test_pattern_keywords_map_to_concepts(self):
        assert _infer_category("Error Handling Pattern", "best practice convention", []) == "concepts"

    def test_roadmap_keywords_map_to_planning(self):
        assert _infer_category("Q2 Roadmap", "milestone timeline objective", []) == "planning"

    def test_no_keywords_defaults_to_concepts(self):
        assert _infer_category("Random Note", "some random content here", []) == "concepts"

    def test_tags_contribute_to_classification(self):
        assert _infer_category("Note", "plain content", ["infrastructure", "monitoring"]) == "systems"


class TestClassifyNote:
    def test_frontmatter_category_used(self, tmp_path):
        note = _make_note(
            tmp_path, "queue-agent", "test.md",
            frontmatter='category: systems\ntags: [auth, security]\ntitle: "Auth System"',
        )
        result = classify_note(note, tmp_path)
        assert result["category"] == "systems"
        assert result["target_folder"] == "04_Systems"

    def test_agent_queue_auto_promotes(self, tmp_path):
        note = _make_note(tmp_path, "queue-agent", "test.md")
        result = classify_note(note, tmp_path)
        assert result["trust_level"] == "high"
        assert result["auto_promote"] is True

    def test_external_queue_held(self, tmp_path):
        note = _make_note(tmp_path, "queue-external", "test.md")
        result = classify_note(note, tmp_path)
        assert result["trust_level"] == "low"
        assert result["auto_promote"] is False
        assert result["needs_review"] is True

    def test_project_specific_folder(self, tmp_path):
        note = _make_note(
            tmp_path, "queue-cicd", "pr-summary.md",
            frontmatter='category: projects\nproject: easy-api\ntitle: "PR Summary"',
        )
        result = classify_note(note, tmp_path)
        assert result["target_folder"] == "01_Projects/easy-api"

    def test_category_inferred_from_content(self, tmp_path):
        note = _make_note(
            tmp_path, "queue-agent", "test.md",
            body="# Database Migration Strategy\n\nThis architecture pattern uses design principles.",
        )
        result = classify_note(note, tmp_path)
        assert result["category"] in ("concepts", "systems")


class TestProcessInbox:
    def test_empty_vault(self, tmp_path):
        result = process_inbox(str(tmp_path), dry_run=True)
        assert result["processed"] == 0

    def test_promotes_high_trust_notes(self, tmp_path):
        _make_note(tmp_path, "queue-agent", "pattern.md", body="# Auth Pattern\n\nContent.")
        result = process_inbox(str(tmp_path), dry_run=False)
        assert result["promoted"] == 1
        # File should be moved out of inbox
        assert not (tmp_path / "05_Inbox" / "queue-agent" / "pattern.md").exists()

    def test_holds_low_trust_notes(self, tmp_path):
        _make_note(tmp_path, "queue-external", "untrusted.md", body="# External\n\nContent.")
        result = process_inbox(str(tmp_path), dry_run=False)
        assert result["held"] == 1
        # File should remain in inbox
        assert (tmp_path / "05_Inbox" / "queue-external" / "untrusted.md").exists()

    def test_dry_run_does_not_move(self, tmp_path):
        _make_note(tmp_path, "queue-agent", "pattern.md", body="# Pattern\n\nContent.")
        result = process_inbox(str(tmp_path), dry_run=True)
        assert result["promoted"] == 1
        # File should still be in inbox
        assert (tmp_path / "05_Inbox" / "queue-agent" / "pattern.md").exists()

    def test_skips_index_files(self, tmp_path):
        _make_note(tmp_path, "queue-agent", "index.md", body="# Index")
        _make_note(tmp_path, "queue-agent", "real-note.md", body="# Real Note")
        result = process_inbox(str(tmp_path), dry_run=True)
        assert result["processed"] == 1

    def test_multiple_queues_processed(self, tmp_path):
        _make_note(tmp_path, "queue-agent", "a.md", body="# A")
        _make_note(tmp_path, "queue-cicd", "b.md", body="# B")
        _make_note(tmp_path, "queue-human", "c.md", body="# C")
        result = process_inbox(str(tmp_path), dry_run=True)
        assert result["processed"] == 3
