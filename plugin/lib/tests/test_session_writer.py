"""Tests for session_writer — daily folder session memory."""

import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from session_writer import (
    write_session_memory,
    _update_daily_index,
    list_daily_sessions,
    _sanitize_agent_name,
)


class TestSanitizeAgentName:
    def test_lowercase(self):
        assert _sanitize_agent_name("Wren") == "wren"

    def test_spaces(self):
        assert _sanitize_agent_name("Agent K") == "agent-k"

    def test_special_chars(self):
        assert _sanitize_agent_name("wren@#$%") == "wren"

    def test_empty(self):
        assert _sanitize_agent_name("") == "unknown"


class TestWriteSessionMemory:
    def test_creates_daily_folder_and_file(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LACP_OBSIDIAN_VAULT", str(tmp_path))
        now = datetime(2026, 3, 23, 14, 30, 0, tzinfo=timezone.utc)

        result = write_session_memory(
            agent_name="Wren",
            session_id="sess-001",
            summary="Tested the Engram system end to end.",
            key_decisions=["Use relative imports for lib modules"],
            tasks_completed=["Guard TUI", "Video ingestion"],
            facts_promoted=["Payment architecture uses Finix + Brale"],
            now=now,
        )

        assert result["agent"] == "Wren"
        assert result["date"] == "2026-03-23"
        assert result["time"] == "1430"

        session_path = Path(result["session_path"])
        assert session_path.exists()
        assert "wren-session-1430.md" in session_path.name

        content = session_path.read_text()
        assert "Wren — Session 1430 UTC" in content
        assert "Tested the Engram system" in content
        assert "Use relative imports" in content
        assert "Guard TUI" in content
        assert "Payment architecture" in content

    def test_daily_index_created(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LACP_OBSIDIAN_VAULT", str(tmp_path))
        now = datetime(2026, 3, 23, 14, 30, 0, tzinfo=timezone.utc)

        write_session_memory(agent_name="Wren", summary="First session", now=now)

        index_path = tmp_path / "memory" / "2026-03-23" / "index.md"
        assert index_path.exists()

        content = index_path.read_text()
        assert "2026-03-23" in content
        assert "wren" in content.lower()
        assert "Sessions:" in content

    def test_multiple_agents_same_day(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LACP_OBSIDIAN_VAULT", str(tmp_path))
        now1 = datetime(2026, 3, 23, 9, 0, 0, tzinfo=timezone.utc)
        now2 = datetime(2026, 3, 23, 10, 0, 0, tzinfo=timezone.utc)
        now3 = datetime(2026, 3, 23, 11, 0, 0, tzinfo=timezone.utc)

        write_session_memory(agent_name="Wren", summary="Morning review", now=now1)
        write_session_memory(agent_name="Zoe", summary="Build pipeline", now=now2)
        write_session_memory(agent_name="Vijay", summary="QA run", now=now3)

        daily_dir = tmp_path / "memory" / "2026-03-23"
        files = [f.name for f in daily_dir.iterdir() if f.name != "index.md"]
        assert len(files) == 3
        assert "wren-session-0900.md" in files
        assert "zoe-session-1000.md" in files
        assert "vijay-session-1100.md" in files

        # Index should list all 3
        index = (daily_dir / "index.md").read_text()
        assert "Wren" in index or "wren" in index
        assert "Zoe" in index or "zoe" in index
        assert "Vijay" in index or "vijay" in index
        assert "session_count: 3" in index

    def test_collision_handling(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LACP_OBSIDIAN_VAULT", str(tmp_path))
        now = datetime(2026, 3, 23, 14, 30, 0, tzinfo=timezone.utc)

        r1 = write_session_memory(agent_name="Wren", summary="First", now=now)
        r2 = write_session_memory(agent_name="Wren", summary="Second", now=now)

        assert r1["session_path"] != r2["session_path"]
        assert Path(r1["session_path"]).exists()
        assert Path(r2["session_path"]).exists()


class TestListDailySessions:
    def test_empty_day(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LACP_OBSIDIAN_VAULT", str(tmp_path))
        result = list_daily_sessions("2026-03-23")
        assert result["exists"] is False
        assert result["sessions"] == []

    def test_lists_sessions(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LACP_OBSIDIAN_VAULT", str(tmp_path))
        now = datetime(2026, 3, 23, 14, 30, 0, tzinfo=timezone.utc)

        write_session_memory(agent_name="Wren", summary="Test", now=now)
        write_session_memory(agent_name="Zoe", summary="Build", now=now)

        result = list_daily_sessions("2026-03-23")
        assert result["exists"] is True
        assert result["count"] == 2
