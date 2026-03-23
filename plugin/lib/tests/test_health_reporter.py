"""Tests for health reporter."""

from pathlib import Path

import pytest

from plugin.lib.health_reporter import (
    compute_graph_metrics,
    generate_health_report,
)


class TestComputeGraphMetrics:
    def _make_vault(self, tmp_path):
        (tmp_path / "02_Concepts").mkdir()
        (tmp_path / "04_Systems").mkdir()

        (tmp_path / "02_Concepts" / "auth.md").write_text(
            "---\ntitle: Auth\ncategory: concepts\ntags: [auth]\n"
            "last_traversed: 2026-03-20\ntraversal_count: 10\n---\n\n"
            "# Auth\n\nSee [[deploy]] for related.\n",
            encoding="utf-8",
        )
        (tmp_path / "02_Concepts" / "patterns.md").write_text(
            "---\ntitle: Patterns\ncategory: concepts\ntags: [patterns]\n---\n\n"
            "# Patterns\n\nSee [[auth]] and [[nonexistent]].\n",
            encoding="utf-8",
        )
        (tmp_path / "04_Systems" / "deploy.md").write_text(
            "---\ntitle: Deploy\ncategory: systems\ntags: [devops]\n---\n\n"
            "# Deploy\n\nSee [[auth]].\n",
            encoding="utf-8",
        )

    def test_counts_notes(self, tmp_path):
        self._make_vault(tmp_path)
        metrics = compute_graph_metrics(tmp_path)
        assert metrics["note_count"] == 3

    def test_counts_links(self, tmp_path):
        self._make_vault(tmp_path)
        metrics = compute_graph_metrics(tmp_path)
        assert metrics["link_count"] >= 3

    def test_detects_broken_links(self, tmp_path):
        self._make_vault(tmp_path)
        metrics = compute_graph_metrics(tmp_path)
        assert metrics["broken_link_count"] >= 1  # [[nonexistent]]

    def test_detects_orphans(self, tmp_path):
        self._make_vault(tmp_path)
        metrics = compute_graph_metrics(tmp_path)
        # patterns.md has no incoming links
        assert metrics["orphan_count"] >= 1

    def test_category_counts(self, tmp_path):
        self._make_vault(tmp_path)
        metrics = compute_graph_metrics(tmp_path)
        assert metrics["category_counts"]["concepts"] == 2
        assert metrics["category_counts"]["systems"] == 1


class TestGenerateHealthReport:
    def test_generates_report(self, tmp_path):
        (tmp_path / "02_Concepts").mkdir()
        (tmp_path / "02_Concepts" / "note.md").write_text(
            "---\ntitle: Note\ncategory: concepts\n---\n\n# Note\n"
        )
        result = generate_health_report(str(tmp_path), dry_run=False)
        assert result["health_score"] >= 0
        assert (tmp_path / "05_Inbox" / "curator-health-report.md").exists()

    def test_dry_run_no_file(self, tmp_path):
        (tmp_path / "02_Concepts").mkdir()
        (tmp_path / "02_Concepts" / "note.md").write_text("# Note\n")
        result = generate_health_report(str(tmp_path), dry_run=True)
        assert not (tmp_path / "05_Inbox" / "curator-health-report.md").exists()

    def test_healthy_vault(self, tmp_path):
        # Create a well-linked vault
        (tmp_path / "02_Concepts").mkdir()
        for i in range(5):
            links = " ".join(f"[[note-{j}]]" for j in range(5) if j != i)
            (tmp_path / "02_Concepts" / f"note-{i}.md").write_text(
                f"---\ntitle: Note {i}\ncategory: concepts\n"
                f"last_traversed: 2026-03-20\ntraversal_count: 10\n---\n\n"
                f"# Note {i}\n\n{links}\n"
            )
        result = generate_health_report(str(tmp_path), dry_run=True)
        assert result["health_score"] >= 70
