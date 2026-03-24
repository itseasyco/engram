"""
Reactive loop for the curator engine.

Watches the vault filesystem for changes and triggers:
1. Fast-classify on new inbox items (queue-* folders)
2. Conflict detection on new conflict files
3. Fast-promote for high-trust sources

Uses the watchdog library for cross-platform filesystem monitoring.
Falls back to polling if watchdog is not available.
"""

import logging
import os
import time
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger("curator.reactive")

try:
    from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileModifiedEvent
    from watchdog.observers import Observer

    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False


# ---------------------------------------------------------------------------
# Event handler
# ---------------------------------------------------------------------------

class CuratorEventHandler:
    """
    Handle filesystem events relevant to the curator.

    Tracks new files in queue-* folders and conflict files.
    Calls the appropriate handler function for each event type.
    """

    def __init__(
        self,
        vault_path: Path,
        on_inbox_item: Optional[Callable] = None,
        on_conflict_detected: Optional[Callable] = None,
    ):
        self.vault_path = vault_path
        self.on_inbox_item = on_inbox_item
        self.on_conflict_detected = on_conflict_detected
        self._processed = set()

    def handle_created(self, src_path: str):
        """Handle a new file creation event."""
        path = Path(src_path)

        if not path.suffix == ".md":
            return

        if src_path in self._processed:
            return
        self._processed.add(src_path)

        # Limit memory for processed set
        if len(self._processed) > 10000:
            self._processed.clear()

        try:
            rel = path.relative_to(self.vault_path).as_posix()
        except ValueError:
            return

        # Check if it's an inbox item
        if "/queue-" in rel and self.on_inbox_item:
            logger.info("New inbox item: %s", rel)
            self.on_inbox_item(path)

        # Check if it's a conflict file
        if "(conflict " in path.name and self.on_conflict_detected:
            logger.info("Conflict file detected: %s", rel)
            self.on_conflict_detected(path)


# ---------------------------------------------------------------------------
# Watchdog-based watcher
# ---------------------------------------------------------------------------

if WATCHDOG_AVAILABLE:
    class _WatchdogHandler(FileSystemEventHandler):
        """Adapter from watchdog events to CuratorEventHandler."""

        def __init__(self, curator_handler: CuratorEventHandler):
            super().__init__()
            self.curator_handler = curator_handler

        def on_created(self, event):
            if not event.is_directory:
                self.curator_handler.handle_created(event.src_path)


# ---------------------------------------------------------------------------
# Polling fallback
# ---------------------------------------------------------------------------

def _poll_for_changes(vault_path: Path, handler: CuratorEventHandler, interval: float = 5.0):
    """
    Poll-based fallback for when watchdog is not available.

    Scans queue-* folders and vault root for new .md files.
    """
    known_files = set()

    # Initial scan
    inbox = vault_path / "05_Inbox"
    if inbox.exists():
        for queue_dir in inbox.iterdir():
            if queue_dir.is_dir() and queue_dir.name.startswith("queue-"):
                for f in queue_dir.glob("*.md"):
                    known_files.add(str(f))

    for f in vault_path.rglob("*(conflict *.md"):
        known_files.add(str(f))

    logger.info("Polling watcher started (interval=%.1fs, known=%d)", interval, len(known_files))

    while True:
        time.sleep(interval)
        current_files = set()

        if inbox.exists():
            for queue_dir in inbox.iterdir():
                if queue_dir.is_dir() and queue_dir.name.startswith("queue-"):
                    for f in queue_dir.glob("*.md"):
                        current_files.add(str(f))

        for f in vault_path.rglob("*(conflict *.md"):
            current_files.add(str(f))

        new_files = current_files - known_files
        for new_file in new_files:
            handler.handle_created(new_file)

        known_files = current_files


# ---------------------------------------------------------------------------
# Default handlers
# ---------------------------------------------------------------------------

def _default_inbox_handler(file_path: Path):
    """Default handler for new inbox items: fast-classify and promote if high-trust."""
    from .inbox_processor import classify_note

    vault_path = file_path
    # Walk up to find vault root (contains 05_Inbox)
    for parent in file_path.parents:
        if (parent / "05_Inbox").exists():
            vault_path = parent
            break

    classification = classify_note(file_path, vault_path)
    logger.info(
        "Fast-classified %s: category=%s trust=%s promote=%s",
        file_path.name,
        classification["category"],
        classification["trust_level"],
        classification["auto_promote"],
    )

    if classification["auto_promote"]:
        from .inbox_processor import process_inbox
        # Process just this queue folder
        # For simplicity, process the entire inbox (idempotent)
        process_inbox(str(vault_path), dry_run=False)


def _default_conflict_handler(file_path: Path):
    """Default handler for conflict files: attempt auto-merge."""
    from .conflict_resolver import resolve_conflicts

    vault_path = file_path
    for parent in file_path.parents:
        if (parent / ".obsidian").exists() or (parent / "05_Inbox").exists():
            vault_path = parent
            break

    result = resolve_conflicts(str(vault_path), dry_run=False)
    logger.info(
        "Conflict resolution: merged=%d escalated=%d",
        result["auto_merged"],
        result["escalated"],
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def start_reactive_watcher(
    vault_path: Optional[str] = None,
    on_inbox_item: Optional[Callable] = None,
    on_conflict_detected: Optional[Callable] = None,
    use_polling: bool = False,
    poll_interval: float = 5.0,
) -> Optional[object]:
    """
    Start the reactive filesystem watcher.

    Args:
        vault_path: root of the Obsidian vault.
        on_inbox_item: callback for new inbox items. Default: fast-classify.
        on_conflict_detected: callback for conflict files. Default: auto-merge.
        use_polling: force polling mode even if watchdog is available.
        poll_interval: polling interval in seconds (only for polling mode).

    Returns:
        Observer instance (watchdog) or None (polling runs in current thread).
    """
    if vault_path is None:
        vault_path = os.environ.get(
            "LACP_OBSIDIAN_VAULT",
            os.path.expanduser("~/obsidian/vault"),
        )

    vault = Path(vault_path)
    if not vault.exists():
        logger.error("Vault not found: %s", vault)
        return None

    if on_inbox_item is None:
        on_inbox_item = _default_inbox_handler
    if on_conflict_detected is None:
        on_conflict_detected = _default_conflict_handler

    handler = CuratorEventHandler(
        vault_path=vault,
        on_inbox_item=on_inbox_item,
        on_conflict_detected=on_conflict_detected,
    )

    if WATCHDOG_AVAILABLE and not use_polling:
        watchdog_handler = _WatchdogHandler(handler)
        observer = Observer()
        observer.schedule(watchdog_handler, str(vault), recursive=True)
        observer.start()
        logger.info("Watchdog reactive watcher started on %s", vault)
        return observer
    else:
        logger.info("Using polling fallback (watchdog %s)",
                     "not installed" if not WATCHDOG_AVAILABLE else "bypassed")
        # Polling blocks the current thread
        _poll_for_changes(vault, handler, interval=poll_interval)
        return None
