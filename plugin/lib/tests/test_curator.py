"""Tests for curator orchestrator."""

from pathlib import Path

import pytest

from plugin.lib.curator import run_curator_cycle


def _make_vault(tmp_path):
    """Create a minimal but functional vault for curator testing."""
    for folder in ["01_Projects", "02_Concepts", "04_Systems", "05_Inbox"]:
        (tmp_path / folder).mkdir(parents=True, exist_ok=True)
    for queue in ["queue-agent", "queue-cicd", "queue-human"]:
        (tmp_path / "05_Inbox" / queue).mkdir(parents=True, exist_ok=True)

    (tmp_path / "02_Concepts" / "auth.md").write_text(
        "---\ntitle: Auth Patterns\ncategory: concepts\ntags: [auth, security]\n"
        "created: 2026-03-01\nupdated: 2026-03-20\nauthor: andrew\nsource: human\n"
        "status: active\nlast_traversed: 2026-03-20\ntraversal_count: 10\n---\n\n"
        "# Auth Patterns\n\nToken-based authentication.\n",
        encoding="utf-8",
    )
    (tmp_path / "04_Systems" / "deploy.md").write_text(
        "---\ntitle: Deploy Pipeline\ncategory: systems\ntags: [devops]\n"
        "created: 2026-03-01\nupdated: 2026-03-20\nauthor: andrew\nsource: human\n"
        "status: active\nlast_traversed: 2026-03-20\ntraversal_count: 5\n---\n\n"
        "# Deploy Pipeline\n\nKubernetes deployment.\n",
        encoding="utf-8",
    )
    # Inbox note
    (tmp_path / "05_Inbox" / "queue-agent" / "new-pattern.md").write_text(
        "---\ntitle: New Pattern\ncategory: concepts\ntags: [patterns]\n---\n\n"
        "# New Pattern\n\nDiscovered a new approach.\n",
        encoding="utf-8",
    )


class TestRunCuratorCycle:
    def test_full_cycle_dry_run(self, tmp_path):
        _make_vault(tmp_path)
        result = run_curator_cycle(str(tmp_path), dry_run=True)
        assert "error" not in result
        assert result["dry_run"] is True
        assert len(result["steps_run"]) == 8
        # All steps should have results
        for step in ["inbox", "consolidation", "wikilinks", "staleness",
                      "conflicts", "schema", "indexes", "health"]:
            assert step in result["results"]

    def test_selective_steps(self, tmp_path):
        _make_vault(tmp_path)
        result = run_curator_cycle(str(tmp_path), dry_run=True, steps=["inbox", "health"])
        assert len(result["steps_run"]) == 2
        assert "inbox" in result["results"]
        assert "health" in result["results"]
        assert "consolidation" not in result["results"]

    def test_full_cycle_applies(self, tmp_path):
        _make_vault(tmp_path)
        result = run_curator_cycle(str(tmp_path), dry_run=False)
        assert result["dry_run"] is False
        # Inbox note should have been promoted
        inbox_result = result["results"]["inbox"]
        assert inbox_result["promoted"] >= 1
        # Health report should be written
        assert (tmp_path / "05_Inbox" / "curator-health-report.md").exists()
        # Heartbeat should be written
        assert (tmp_path / ".curator-heartbeat.json").exists()
        # Index should be generated
        assert (tmp_path / "00_Index.md").exists()

    def test_nonexistent_vault(self):
        result = run_curator_cycle("/tmp/nonexistent-vault-test-xyz")
        assert "error" in result

    def test_cycle_duration_tracked(self, tmp_path):
        _make_vault(tmp_path)
        result = run_curator_cycle(str(tmp_path), dry_run=True)
        assert "cycle_duration_seconds" in result
        assert result["cycle_duration_seconds"] >= 0
