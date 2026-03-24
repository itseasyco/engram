"""Tests for wikilink weaver."""

from pathlib import Path

import pytest

from plugin.lib.wikilink_weaver import (
    _title_similarity,
    _tag_overlap,
    _content_keyword_overlap,
    compute_relatedness,
    _add_backlink_to_content,
    _remove_broken_links,
    weave_wikilinks,
)


class TestTitleSimilarity:
    def test_identical_titles(self):
        assert _title_similarity("Auth System", "Auth System") == 1.0

    def test_no_overlap(self):
        assert _title_similarity("Auth System", "Deploy Pipeline") == 0.0

    def test_partial_overlap(self):
        score = _title_similarity("Auth System Architecture", "Auth Flow Design")
        assert 0 < score < 1

    def test_stopwords_ignored(self):
        score = _title_similarity("The Big System", "A Big System")
        assert score > 0.5


class TestTagOverlap:
    def test_identical_tags(self):
        assert _tag_overlap(["auth", "security"], ["auth", "security"]) == 1.0

    def test_no_overlap(self):
        assert _tag_overlap(["auth"], ["deploy"]) == 0.0

    def test_partial_overlap(self):
        score = _tag_overlap(["auth", "security", "api"], ["auth", "api", "testing"])
        assert 0.3 < score < 0.7

    def test_empty_tags(self):
        assert _tag_overlap([], ["auth"]) == 0.0


class TestContentKeywordOverlap:
    def test_similar_content(self):
        body_a = "authentication system uses tokens and sessions for security validation"
        body_b = "authentication tokens provide security through session validation"
        score = _content_keyword_overlap(body_a, body_b)
        assert score > 0.3

    def test_unrelated_content(self):
        body_a = "kubernetes deployment pipeline monitoring grafana"
        body_b = "quarterly roadmap objectives hiring growth strategy"
        score = _content_keyword_overlap(body_a, body_b)
        assert score < 0.1


class TestComputeRelatedness:
    def test_identical_notes(self):
        note = {"title": "Auth System", "tags": ["auth"], "body": "authentication system"}
        score = compute_relatedness(note, note)
        assert score > 0.5

    def test_unrelated_notes(self):
        note_a = {"title": "Auth System", "tags": ["auth"], "body": "tokens sessions security"}
        note_b = {"title": "Deploy Pipeline", "tags": ["devops"], "body": "kubernetes docker containers"}
        score = compute_relatedness(note_a, note_b)
        assert score < 0.2


class TestAddBacklink:
    def test_adds_related_section(self):
        content = "---\ntitle: Test\n---\n\n# Test\n\nContent here."
        result = _add_backlink_to_content(content, "other-note")
        assert "[[other-note]]" in result
        assert "## Related Notes" in result

    def test_appends_to_existing_section(self):
        content = "# Test\n\n## Related Notes\n\n- [[existing-note]]\n"
        result = _add_backlink_to_content(content, "new-note")
        assert "[[new-note]]" in result
        assert "[[existing-note]]" in result

    def test_skips_already_linked(self):
        content = "# Test\n\nSee [[other-note]] for details."
        result = _add_backlink_to_content(content, "other-note")
        assert result == content


class TestRemoveBrokenLinks:
    def test_removes_broken_link(self):
        content = "See [[existing]] and [[deleted-note]] for details."
        modified, removed = _remove_broken_links(content, {"existing"})
        assert "[[existing]]" in modified
        assert "[[deleted-note]]" not in modified
        assert "deleted-note" in removed

    def test_preserves_valid_links(self):
        content = "See [[note-a]] and [[note-b]]."
        modified, removed = _remove_broken_links(content, {"note-a", "note-b"})
        assert modified == content
        assert removed == []

    def test_handles_aliased_links(self):
        content = "See [[target|display text]]."
        modified, removed = _remove_broken_links(content, set())
        assert "display text" in modified
        assert "[[" not in modified


class TestWeaveWikilinks:
    def _make_vault(self, tmp_path):
        """Create a small vault with related and unrelated notes."""
        (tmp_path / "01_Projects").mkdir()
        (tmp_path / "02_Concepts").mkdir()

        (tmp_path / "01_Projects" / "auth-system.md").write_text(
            "---\ntitle: Auth System\ntags: [auth, security, tokens]\n---\n\n"
            "# Auth System\n\nUses tokens and sessions for authentication.\n",
            encoding="utf-8",
        )
        (tmp_path / "02_Concepts" / "auth-patterns.md").write_text(
            "---\ntitle: Authentication Patterns\ntags: [auth, patterns, security]\n---\n\n"
            "# Authentication Patterns\n\nToken-based authentication and session management.\n",
            encoding="utf-8",
        )
        (tmp_path / "02_Concepts" / "deploy-pipeline.md").write_text(
            "---\ntitle: Deploy Pipeline\ntags: [devops, kubernetes, docker]\n---\n\n"
            "# Deploy Pipeline\n\nContainer orchestration and kubernetes deployments.\n",
            encoding="utf-8",
        )

    def test_links_related_notes(self, tmp_path):
        self._make_vault(tmp_path)
        result = weave_wikilinks(str(tmp_path), relatedness_threshold=0.15, dry_run=True)
        assert result["links_added"] > 0
        # Auth notes should be linked to each other
        added_pairs = [(d["a"], d["b"]) for d in result["added_details"]]
        auth_linked = any(
            ("auth-system" in a and "auth-patterns" in b)
            or ("auth-patterns" in a and "auth-system" in b)
            for a, b in added_pairs
        )
        assert auth_linked

    def test_dry_run_preserves_files(self, tmp_path):
        self._make_vault(tmp_path)
        original = (tmp_path / "01_Projects" / "auth-system.md").read_text()
        weave_wikilinks(str(tmp_path), relatedness_threshold=0.15, dry_run=True)
        assert (tmp_path / "01_Projects" / "auth-system.md").read_text() == original

    def test_removes_broken_links(self, tmp_path):
        self._make_vault(tmp_path)
        # Add a broken link to auth-system.md
        auth_path = tmp_path / "01_Projects" / "auth-system.md"
        content = auth_path.read_text()
        content += "\nSee [[nonexistent-note]] for details.\n"
        auth_path.write_text(content)
        result = weave_wikilinks(str(tmp_path), dry_run=False, remove_broken=True)
        assert result["links_removed"] >= 1
