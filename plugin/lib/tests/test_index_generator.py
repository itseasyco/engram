"""Tests for index generator."""

from pathlib import Path

import pytest

from plugin.lib.index_generator import (
    _count_notes,
    _note_title,
    generate_master_index,
    generate_folder_index,
    regenerate_indexes,
)


class TestCountNotes:
    def test_counts_md_files(self, tmp_path):
        d = tmp_path / "folder"
        d.mkdir()
        (d / "a.md").write_text("# A")
        (d / "b.md").write_text("# B")
        (d / "index.md").write_text("# Index")
        assert _count_notes(d) == 2

    def test_empty_folder(self, tmp_path):
        d = tmp_path / "empty"
        d.mkdir()
        assert _count_notes(d) == 0

    def test_nonexistent_folder(self, tmp_path):
        assert _count_notes(tmp_path / "nope") == 0

    def test_counts_recursively(self, tmp_path):
        d = tmp_path / "folder"
        (d / "sub").mkdir(parents=True)
        (d / "a.md").write_text("# A")
        (d / "sub" / "b.md").write_text("# B")
        assert _count_notes(d) == 2


class TestNoteTitle:
    def test_extracts_from_frontmatter(self, tmp_path):
        note = tmp_path / "test.md"
        note.write_text('---\ntitle: "My Great Note"\n---\n\n# Content\n')
        assert _note_title(note) == "My Great Note"

    def test_falls_back_to_filename(self, tmp_path):
        note = tmp_path / "my-great-note.md"
        note.write_text("# Content\n")
        assert _note_title(note) == "My Great Note"


class TestGenerateMasterIndex:
    def _make_vault(self, tmp_path):
        for folder in ["01_Projects", "02_Concepts", "04_Systems"]:
            (tmp_path / folder).mkdir()
        (tmp_path / "02_Concepts" / "auth.md").write_text(
            '---\ntitle: "Auth"\n---\n\n# Auth\n'
        )
        (tmp_path / "02_Concepts" / "patterns.md").write_text("# Patterns\n")
        (tmp_path / "04_Systems" / "deploy.md").write_text("# Deploy\n")

    def test_contains_section_table(self, tmp_path):
        self._make_vault(tmp_path)
        content = generate_master_index(tmp_path)
        assert "## Sections" in content
        assert "02_Concepts" in content
        assert "| 2 |" in content or "| 2|" in content

    def test_contains_recent_changes(self, tmp_path):
        self._make_vault(tmp_path)
        content = generate_master_index(tmp_path)
        assert "## Recent Changes" in content


class TestGenerateFolderIndex:
    def test_lists_notes(self, tmp_path):
        folder = tmp_path / "02_Concepts"
        folder.mkdir()
        (folder / "auth.md").write_text('---\ntitle: "Auth Patterns"\n---\n# Auth\n')
        (folder / "deploy.md").write_text("# Deploy\n")
        content = generate_folder_index(folder, tmp_path)
        assert "[[auth]]" in content
        assert "[[deploy]]" in content
        assert "2 notes" in content


class TestRegenerateIndexes:
    def test_creates_master_index(self, tmp_path):
        (tmp_path / "02_Concepts").mkdir()
        (tmp_path / "02_Concepts" / "note.md").write_text("# Note\n")
        result = regenerate_indexes(str(tmp_path), dry_run=False)
        assert result["master_index_updated"] is True
        assert (tmp_path / "00_Index.md").exists()

    def test_creates_folder_indexes(self, tmp_path):
        (tmp_path / "02_Concepts").mkdir()
        (tmp_path / "02_Concepts" / "note.md").write_text("# Note\n")
        result = regenerate_indexes(str(tmp_path), dry_run=False)
        assert "02_Concepts" in result["folder_indexes_updated"]
        assert (tmp_path / "02_Concepts" / "index.md").exists()

    def test_dry_run_no_files(self, tmp_path):
        (tmp_path / "02_Concepts").mkdir()
        (tmp_path / "02_Concepts" / "note.md").write_text("# Note\n")
        regenerate_indexes(str(tmp_path), dry_run=True)
        assert not (tmp_path / "00_Index.md").exists()
