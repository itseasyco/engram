"""Tests for reactive watcher."""

from pathlib import Path

import pytest

from plugin.lib.reactive_watcher import CuratorEventHandler


class TestCuratorEventHandler:
    def test_inbox_callback_fired(self, tmp_path):
        vault = tmp_path
        (vault / "05_Inbox" / "queue-agent").mkdir(parents=True)

        received = []

        def on_inbox(path):
            received.append(path)

        handler = CuratorEventHandler(
            vault_path=vault,
            on_inbox_item=on_inbox,
        )

        note = vault / "05_Inbox" / "queue-agent" / "new-note.md"
        note.write_text("# New Note\n")
        handler.handle_created(str(note))

        assert len(received) == 1
        assert received[0] == note

    def test_conflict_callback_fired(self, tmp_path):
        vault = tmp_path

        received = []

        def on_conflict(path):
            received.append(path)

        handler = CuratorEventHandler(
            vault_path=vault,
            on_conflict_detected=on_conflict,
        )

        conflict = vault / "02_Concepts" / "note (conflict 2026-03-21).md"
        conflict.parent.mkdir(parents=True)
        conflict.write_text("# Conflict\n")
        handler.handle_created(str(conflict))

        assert len(received) == 1

    def test_ignores_non_md_files(self, tmp_path):
        vault = tmp_path

        received = []
        handler = CuratorEventHandler(
            vault_path=vault,
            on_inbox_item=lambda p: received.append(p),
        )

        handler.handle_created(str(vault / "05_Inbox" / "queue-agent" / "file.txt"))
        assert len(received) == 0

    def test_deduplicates_events(self, tmp_path):
        vault = tmp_path
        (vault / "05_Inbox" / "queue-agent").mkdir(parents=True)

        received = []
        handler = CuratorEventHandler(
            vault_path=vault,
            on_inbox_item=lambda p: received.append(p),
        )

        note = vault / "05_Inbox" / "queue-agent" / "note.md"
        note.write_text("# Note\n")
        handler.handle_created(str(note))
        handler.handle_created(str(note))

        assert len(received) == 1

    def test_no_callback_no_error(self, tmp_path):
        """Handler with no callbacks should not crash."""
        vault = tmp_path
        handler = CuratorEventHandler(vault_path=vault)
        # Should not raise
        handler.handle_created(str(vault / "05_Inbox" / "queue-agent" / "note.md"))
