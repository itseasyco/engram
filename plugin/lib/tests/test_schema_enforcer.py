"""Tests for schema enforcer."""

from pathlib import Path

import pytest

from plugin.lib.schema_enforcer import (
    _add_missing_frontmatter,
    _infer_category_from_path,
    enforce_schema,
)


class TestInferCategoryFromPath:
    def test_projects_folder(self):
        assert _infer_category_from_path("01_Projects/easy-api/auth.md") == "projects"

    def test_concepts_folder(self):
        assert _infer_category_from_path("02_Concepts/patterns.md") == "concepts"

    def test_systems_folder(self):
        assert _infer_category_from_path("04_Systems/monitoring.md") == "systems"

    def test_unknown_folder(self):
        assert _infer_category_from_path("unknown/file.md") == "concepts"


class TestAddMissingFrontmatter:
    def test_no_frontmatter_creates_full(self, tmp_path):
        note = tmp_path / "02_Concepts" / "test.md"
        note.parent.mkdir(parents=True)
        note.write_text("# Test Note\n\nContent here.", encoding="utf-8")
        content = note.read_text()
        modified, added, issues = _add_missing_frontmatter(content, note, tmp_path)
        assert modified.startswith("---\n")
        assert "title:" in modified
        assert "category: concepts" in modified
        assert "status: active" in modified
        assert len(added) == 8  # All required fields

    def test_complete_frontmatter_unchanged(self, tmp_path):
        note = tmp_path / "02_Concepts" / "test.md"
        note.parent.mkdir(parents=True)
        fm = (
            "---\n"
            'title: "Test"\n'
            "category: concepts\n"
            "tags: [test]\n"
            "created: 2026-03-21\n"
            "updated: 2026-03-21\n"
            "author: andrew\n"
            "source: human\n"
            "status: active\n"
            "---\n\n# Test\n"
        )
        note.write_text(fm, encoding="utf-8")
        modified, added, issues = _add_missing_frontmatter(fm, note, tmp_path)
        assert added == []
        assert issues == []

    def test_partial_frontmatter_fills_gaps(self, tmp_path):
        note = tmp_path / "02_Concepts" / "test.md"
        note.parent.mkdir(parents=True)
        fm = "---\ntitle: Test\ncategory: concepts\n---\n\n# Test\n"
        note.write_text(fm, encoding="utf-8")
        modified, added, issues = _add_missing_frontmatter(fm, note, tmp_path)
        assert "tags:" in modified
        assert "status: active" in modified
        assert "author: curator" in modified
        assert len(added) > 0

    def test_invalid_status_flagged(self, tmp_path):
        note = tmp_path / "02_Concepts" / "test.md"
        note.parent.mkdir(parents=True)
        fm = (
            "---\ntitle: Test\ncategory: concepts\ntags: []\n"
            "created: 2026-03-21\nupdated: 2026-03-21\n"
            "author: x\nsource: x\nstatus: bogus\n---\n\n# Test\n"
        )
        note.write_text(fm, encoding="utf-8")
        modified, added, issues = _add_missing_frontmatter(fm, note, tmp_path)
        assert any("invalid_status" in i for i in issues)


class TestEnforceSchema:
    def _make_vault(self, tmp_path, notes):
        for folder, name, content in notes:
            d = tmp_path / folder
            d.mkdir(parents=True, exist_ok=True)
            (d / name).write_text(content, encoding="utf-8")

    def test_all_compliant(self, tmp_path):
        self._make_vault(tmp_path, [(
            "02_Concepts", "note.md",
            "---\ntitle: Note\ncategory: concepts\ntags: []\n"
            "created: 2026-03-21\nupdated: 2026-03-21\nauthor: a\nsource: b\nstatus: active\n"
            "---\n\n# Note\n",
        )])
        result = enforce_schema(str(tmp_path), dry_run=True)
        assert result["compliant"] == 1
        assert result["fixed"] == 0

    def test_fixes_missing_fields(self, tmp_path):
        self._make_vault(tmp_path, [(
            "02_Concepts", "note.md",
            "---\ntitle: Note\n---\n\n# Note\n",
        )])
        result = enforce_schema(str(tmp_path), dry_run=False)
        assert result["fixed"] == 1
        content = (tmp_path / "02_Concepts" / "note.md").read_text()
        assert "status: active" in content
        assert "author: curator" in content

    def test_dry_run_preserves(self, tmp_path):
        self._make_vault(tmp_path, [(
            "02_Concepts", "note.md",
            "# No frontmatter at all\n",
        )])
        original = (tmp_path / "02_Concepts" / "note.md").read_text()
        enforce_schema(str(tmp_path), dry_run=True)
        assert (tmp_path / "02_Concepts" / "note.md").read_text() == original

    def test_skips_index_files(self, tmp_path):
        self._make_vault(tmp_path, [
            ("02_Concepts", "index.md", "# Index\n"),
            ("02_Concepts", "real.md", "# No FM\n"),
        ])
        result = enforce_schema(str(tmp_path), dry_run=True)
        assert result["total"] == 1
