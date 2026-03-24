"""Tests for conflict resolver."""

from pathlib import Path

import pytest

from plugin.lib.conflict_resolver import (
    CONFLICT_PATTERN,
    find_conflict_files,
    attempt_auto_merge,
    resolve_conflicts,
)


class TestConflictPattern:
    def test_matches_standard_conflict(self):
        m = CONFLICT_PATTERN.match("auth-system (conflict 2026-03-21).md")
        assert m
        assert m.group(1) == "auth-system"
        assert m.group(2) == "2026-03-21"

    def test_matches_spaces_in_name(self):
        m = CONFLICT_PATTERN.match("my note (conflict 2026-01-15).md")
        assert m
        assert m.group(1) == "my note"

    def test_no_match_on_regular_file(self):
        assert CONFLICT_PATTERN.match("regular-note.md") is None

    def test_no_match_on_parenthetical(self):
        assert CONFLICT_PATTERN.match("note (draft).md") is None


class TestFindConflictFiles:
    def test_finds_conflict_files(self, tmp_path):
        (tmp_path / "02_Concepts").mkdir()
        (tmp_path / "02_Concepts" / "auth.md").write_text("# Auth", encoding="utf-8")
        (tmp_path / "02_Concepts" / "auth (conflict 2026-03-21).md").write_text(
            "# Auth (conflict)", encoding="utf-8",
        )
        conflicts = find_conflict_files(tmp_path)
        assert len(conflicts) == 1
        assert conflicts[0]["original_stem"] == "auth"
        assert conflicts[0]["original_exists"] is True

    def test_skips_obsidian_dir(self, tmp_path):
        obsidian = tmp_path / ".obsidian"
        obsidian.mkdir()
        (obsidian / "test (conflict 2026-03-21).md").write_text("x", encoding="utf-8")
        conflicts = find_conflict_files(tmp_path)
        assert len(conflicts) == 0


class TestAttemptAutoMerge:
    def test_identical_content(self):
        content = "---\ntitle: Test\n---\n\n# Test\n\nContent."
        success, merged, conflicts = attempt_auto_merge(content, content)
        assert success is True
        assert conflicts == []

    def test_non_overlapping_sections(self):
        original = (
            "---\ntitle: Test\n---\n\n# Test\n\n"
            "## Section A\n\nOriginal A content.\n\n"
            "## Section B\n\nOriginal B content.\n"
        )
        conflict = (
            "---\ntitle: Test\n---\n\n# Test\n\n"
            "## Section A\n\nOriginal A content.\n\n"
            "## Section B\n\nModified B content with new info.\n"
        )
        success, merged, conflicts = attempt_auto_merge(original, conflict)
        assert success is True
        assert "Modified B content" in merged
        assert conflicts == []

    def test_conflicting_sections_escalated(self):
        original = (
            "---\ntitle: Test\n---\n\n# Test\n\n"
            "## Section A\n\nCompletely different original text about topic alpha.\n"
        )
        conflict = (
            "---\ntitle: Test\n---\n\n# Test\n\n"
            "## Section A\n\nTotally rewritten content about topic beta with new direction.\n"
        )
        success, merged, conflicts = attempt_auto_merge(original, conflict)
        assert success is False
        assert len(conflicts) > 0

    def test_new_section_in_conflict(self):
        original = (
            "---\ntitle: Test\n---\n\n# Test\n\n"
            "## Section A\n\nContent A.\n"
        )
        conflict = (
            "---\ntitle: Test\n---\n\n# Test\n\n"
            "## Section A\n\nContent A.\n\n"
            "## Section B\n\nNew section added.\n"
        )
        success, merged, conflicts = attempt_auto_merge(original, conflict)
        assert success is True
        assert "Section B" in merged
        assert "New section added" in merged


class TestResolveConflicts:
    def test_auto_merges_non_overlapping(self, tmp_path):
        d = tmp_path / "02_Concepts"
        d.mkdir()
        (d / "note.md").write_text(
            "---\ntitle: Note\n---\n\n# Note\n\n## A\n\nOriginal.\n\n## B\n\nOriginal B.\n",
            encoding="utf-8",
        )
        (d / "note (conflict 2026-03-21).md").write_text(
            "---\ntitle: Note\n---\n\n# Note\n\n## A\n\nOriginal.\n\n## B\n\nUpdated B.\n",
            encoding="utf-8",
        )
        result = resolve_conflicts(str(tmp_path), dry_run=False)
        assert result["auto_merged"] == 1
        assert not (d / "note (conflict 2026-03-21).md").exists()

    def test_orphaned_conflict_renamed(self, tmp_path):
        d = tmp_path / "02_Concepts"
        d.mkdir()
        # Conflict file exists but original does not
        (d / "deleted (conflict 2026-03-21).md").write_text("# Content", encoding="utf-8")
        result = resolve_conflicts(str(tmp_path), dry_run=False)
        assert result["orphaned"] == 1
        assert (d / "deleted.md").exists()

    def test_dry_run_preserves(self, tmp_path):
        d = tmp_path / "02_Concepts"
        d.mkdir()
        (d / "note.md").write_text("# Note\n\n## A\n\nContent.\n", encoding="utf-8")
        (d / "note (conflict 2026-03-21).md").write_text("# Note\n\n## A\n\nContent.\n", encoding="utf-8")
        result = resolve_conflicts(str(tmp_path), dry_run=True)
        assert result["found"] == 1
        assert (d / "note (conflict 2026-03-21).md").exists()
