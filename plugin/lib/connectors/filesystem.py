"""
Filesystem connector (Tier 1 -- Native).

Watches configured directories for new or changed files and transforms
them into VaultNote objects. Adapted from openclaw-ingest-watch.

Config keys:
  - watch_paths: list of directory paths to watch
  - extensions: list of file extensions to accept (e.g. [".md", ".txt", ".pdf"])
  - ignore_patterns: list of glob patterns to ignore (e.g. ["*.tmp", ".DS_Store"])
  - poll_interval_seconds: how often to scan (default: 60)
"""

from __future__ import annotations

import fnmatch
import os
import plistlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .base import Connector, ConnectorStatus, RawData, VaultNote, TrustLevel


# Transcript detection patterns (from openclaw-ingest-watch)
TRANSCRIPT_PATTERNS = [
    re.compile(r"^Speaker\s*:", re.MULTILINE),
    re.compile(r"^\[?\d{1,2}:\d{2}", re.MULTILINE),
    re.compile(r"^Q\s*:", re.MULTILINE),
    re.compile(r"^A\s*:", re.MULTILINE),
    re.compile(r"\[\d{2}:\d{2}:\d{2}\]", re.MULTILINE),
]


def _is_transcript(file_path: Path) -> bool:
    """Heuristic: does the file look like a transcript?"""
    try:
        text = file_path.read_text(errors="ignore")[:4096]
    except OSError:
        return False
    hits = sum(1 for pat in TRANSCRIPT_PATTERNS if pat.search(text))
    return hits >= 2


def _classify_file(file_path: Path) -> str:
    """Return the file type: transcript, pdf, url, or file."""
    suffix = file_path.suffix.lower()
    if suffix in (".url", ".webloc"):
        return "url"
    if suffix == ".pdf":
        return "pdf"
    if suffix in (".md", ".txt"):
        if _is_transcript(file_path):
            return "transcript"
        return "file"
    return "file"


def _extract_url(file_path: Path) -> str:
    """Extract a URL from a .url or .webloc file."""
    suffix = file_path.suffix.lower()
    if suffix == ".webloc":
        try:
            with open(file_path, "rb") as f:
                plist = plistlib.load(f)
            return plist.get("URL", "")
        except Exception:
            pass
    if suffix == ".url":
        try:
            text = file_path.read_text(errors="ignore")
            for line in text.splitlines():
                if line.strip().upper().startswith("URL="):
                    return line.split("=", 1)[1].strip()
        except OSError:
            pass
    # Fallback: find any URL in the file
    try:
        text = file_path.read_text(errors="ignore")[:2048]
        m = re.search(r"https?://[^\s<>\"]+", text)
        if m:
            return m.group(0)
    except OSError:
        pass
    return ""


class FilesystemConnector(Connector):
    """
    Watch local directories for new files and ingest them as vault notes.

    Maintains a set of already-seen file paths (by mtime + size hash)
    to avoid re-ingesting unchanged files.
    """

    type = "filesystem"

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self._watch_paths: list[str] = self.connector_config.get("watch_paths", [])
        self._extensions: list[str] = self.connector_config.get(
            "extensions", [".md", ".txt", ".pdf", ".url", ".webloc"]
        )
        self._ignore_patterns: list[str] = self.connector_config.get(
            "ignore_patterns", ["*.tmp", ".DS_Store", "*.swp", "*~"]
        )
        self._seen: dict[str, float] = {}  # path -> mtime

    def authenticate(self) -> bool:
        """Verify that at least one watch path exists."""
        valid = 0
        for wp in self._watch_paths:
            p = Path(os.path.expanduser(wp)).resolve()
            if p.is_dir():
                valid += 1
        return valid > 0

    def pull(self) -> list[RawData]:
        """Scan watch paths for new or changed files."""
        results: list[RawData] = []

        for wp in self._watch_paths:
            dir_path = Path(os.path.expanduser(wp)).resolve()
            if not dir_path.is_dir():
                continue

            for entry in dir_path.iterdir():
                if not entry.is_file():
                    continue
                if entry.parent.name == "processed":
                    continue
                if not self._extension_match(entry):
                    continue
                if self._is_ignored(entry):
                    continue

                abs_str = str(entry.resolve())
                try:
                    mtime = entry.stat().st_mtime
                except OSError:
                    continue

                # Skip if we've already seen this file at this mtime
                if abs_str in self._seen and self._seen[abs_str] >= mtime:
                    continue

                self._seen[abs_str] = mtime
                file_type = _classify_file(entry)

                payload: dict[str, Any] = {
                    "file_path": abs_str,
                    "file_name": entry.name,
                    "file_type": file_type,
                    "file_size": entry.stat().st_size,
                }

                if file_type == "url":
                    url = _extract_url(entry)
                    if url:
                        payload["url"] = url

                results.append(RawData(
                    source_id=abs_str,
                    payload=payload,
                    sender=f"filesystem:{wp}",
                ))

        return results

    def transform(self, raw_data: RawData) -> VaultNote:
        """Convert a file discovery into a VaultNote."""
        p = raw_data.payload
        file_path = Path(p["file_path"])
        file_type = p.get("file_type", "file")
        file_name = p.get("file_name", file_path.name)

        if file_type == "url":
            url = p.get("url", "")
            title = f"Link: {file_path.stem}"
            body = f"Source URL: [{url}]({url})\n\nImported from: `{file_name}`"
            tags = ["link", "imported"]
        elif file_type == "transcript":
            title = f"Transcript: {file_path.stem}"
            try:
                content = file_path.read_text(errors="ignore")
            except OSError:
                content = "(could not read file)"
            body = content
            tags = ["transcript", "imported"]
        elif file_type == "pdf":
            title = f"PDF: {file_path.stem}"
            body = f"PDF imported from: `{file_name}`\n\n(PDF text extraction pending)"
            tags = ["pdf", "imported"]
        else:
            title = file_path.stem
            try:
                content = file_path.read_text(errors="ignore")[:4000]
            except OSError:
                content = "(could not read file)"
            body = content
            tags = ["imported"]

        return VaultNote(
            title=title,
            body=body,
            source_connector=self.id,
            source_type=self.type,
            source_id=raw_data.source_id,
            trust_level=self.trust_level,
            landing_zone=self.landing_zone,
            tags=tags,
            category=file_type,
            source_url=p.get("url", ""),
        )

    def health_check(self) -> ConnectorStatus:
        status = self.base_status(healthy=True)
        valid_paths = []
        for wp in self._watch_paths:
            p = Path(os.path.expanduser(wp)).resolve()
            if p.is_dir():
                valid_paths.append(str(p))
            else:
                status.healthy = False
        status.extra["watch_paths"] = valid_paths
        status.extra["seen_files"] = len(self._seen)
        return status

    def _extension_match(self, entry: Path) -> bool:
        if not self._extensions:
            return True
        return entry.suffix.lower() in self._extensions

    def _is_ignored(self, entry: Path) -> bool:
        for pattern in self._ignore_patterns:
            if fnmatch.fnmatch(entry.name, pattern):
                return True
        return False
