#!/usr/bin/env python3
"""
Heartbeat system for openclaw-lacp-fusion.

Curator side: write_heartbeat() after each cycle.
Connected side: check_heartbeat() to detect outages.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, UTC, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

HEARTBEAT_FILENAME = ".curator-heartbeat.json"
# Default cycle interval in hours (used to compute missed heartbeats)
DEFAULT_CYCLE_HOURS = 4
# Number of missed heartbeats before alert
ALERT_THRESHOLD = 3


@dataclass
class OutageRecord:
    start: str
    end: Optional[str] = None
    files_queued_during_outage: int = 0
    reconciliation_status: str = "pending"  # pending | in_progress | completed


@dataclass
class HeartbeatData:
    last_seen: str
    status: str  # healthy | degraded | recovering
    cycle_duration_seconds: float = 0.0
    notes_processed: int = 0
    next_cycle: str = ""
    missed_heartbeats: int = 0
    outage_log: list[dict] = field(default_factory=list)


def _heartbeat_path(vault_path: str = "") -> Path:
    if not vault_path:
        vault_path = os.environ.get("LACP_OBSIDIAN_VAULT", "")
    if not vault_path:
        vault_path = os.environ.get("OPENCLAW_VAULT", "")
    if not vault_path:
        openclaw_home = os.environ.get("OPENCLAW_HOME", os.path.expanduser("~/.openclaw"))
        vault_path = os.path.join(openclaw_home, "data", "knowledge")
    return Path(vault_path) / HEARTBEAT_FILENAME


def write_heartbeat(
    vault_path: str = "",
    *,
    cycle_duration_seconds: float = 0.0,
    notes_processed: int = 0,
    cycle_interval_hours: float = DEFAULT_CYCLE_HOURS,
) -> Path:
    """Write heartbeat file to the shared vault (curator side)."""
    path = _heartbeat_path(vault_path)
    now = datetime.now(UTC)

    # Load existing data to preserve outage_log
    existing_outage_log: list[dict] = []
    existing_missed: int = 0
    if path.exists():
        try:
            old = json.loads(path.read_text(encoding="utf-8"))
            existing_outage_log = old.get("outage_log", [])
            existing_missed = old.get("missed_heartbeats", 0)
        except (json.JSONDecodeError, OSError):
            pass

    # If we had missed heartbeats, close the outage
    if existing_missed >= ALERT_THRESHOLD:
        outage_record = {
            "start": _estimate_outage_start(existing_missed, cycle_interval_hours),
            "end": now.isoformat(),
            "files_queued_during_outage": 0,  # Will be updated during reconciliation
            "reconciliation_status": "pending",
        }
        existing_outage_log.append(outage_record)

    heartbeat = HeartbeatData(
        last_seen=now.isoformat(),
        status="recovering" if existing_missed >= ALERT_THRESHOLD else "healthy",
        cycle_duration_seconds=cycle_duration_seconds,
        notes_processed=notes_processed,
        next_cycle=(now + timedelta(hours=cycle_interval_hours)).isoformat(),
        missed_heartbeats=0,
        outage_log=existing_outage_log,
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(heartbeat), indent=2) + "\n", encoding="utf-8")
    return path


def _estimate_outage_start(missed: int, interval_hours: float) -> str:
    """Estimate when the outage started based on missed heartbeats."""
    now = datetime.now(UTC)
    start = now - timedelta(hours=missed * interval_hours)
    return start.isoformat()


def check_heartbeat(
    vault_path: str = "",
    *,
    cycle_interval_hours: float = DEFAULT_CYCLE_HOURS,
) -> dict:
    """
    Check curator heartbeat (connected node side).

    Returns a status dict:
      - status: "healthy" | "warning" | "outage" | "no_heartbeat"
      - last_seen: ISO timestamp or None
      - missed_heartbeats: int
      - message: human-readable status
    """
    path = _heartbeat_path(vault_path)

    if not path.exists():
        return {
            "status": "no_heartbeat",
            "last_seen": None,
            "missed_heartbeats": 0,
            "message": "No heartbeat file found. Curator may not be configured.",
        }

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        return {
            "status": "no_heartbeat",
            "last_seen": None,
            "missed_heartbeats": 0,
            "message": f"Failed to read heartbeat: {e}",
        }

    last_seen_str = data.get("last_seen", "")
    if not last_seen_str:
        return {
            "status": "no_heartbeat",
            "last_seen": None,
            "missed_heartbeats": 0,
            "message": "Heartbeat file exists but has no last_seen timestamp.",
        }

    last_seen = datetime.fromisoformat(last_seen_str)
    now = datetime.now(UTC)
    elapsed = now - last_seen
    expected_interval = timedelta(hours=cycle_interval_hours)
    missed = max(0, int(elapsed / expected_interval) - 1)

    if missed == 0:
        status = "healthy"
        ago = _format_elapsed(elapsed)
        message = f"Curator healthy (last seen: {ago} ago)"
    elif missed < ALERT_THRESHOLD:
        status = "warning"
        ago = _format_elapsed(elapsed)
        message = f"Curator heartbeat delayed ({missed} missed, last seen: {ago} ago)"
    else:
        status = "outage"
        ago = _format_elapsed(elapsed)
        message = f"Curator heartbeat missed ({missed} missed, last seen: {ago} ago)"

    return {
        "status": status,
        "last_seen": last_seen_str,
        "missed_heartbeats": missed,
        "message": message,
        "outage_log": data.get("outage_log", []),
    }


def update_outage_reconciliation(
    vault_path: str = "",
    *,
    files_queued: int = 0,
    reconciliation_status: str = "completed",
) -> bool:
    """Update the most recent outage record after reconciliation."""
    path = _heartbeat_path(vault_path)
    if not path.exists():
        return False

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False

    outage_log = data.get("outage_log", [])
    if not outage_log:
        return False

    # Update the most recent outage
    outage_log[-1]["files_queued_during_outage"] = files_queued
    outage_log[-1]["reconciliation_status"] = reconciliation_status
    data["outage_log"] = outage_log

    if reconciliation_status == "completed":
        data["status"] = "healthy"

    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return True


def _format_elapsed(td: timedelta) -> str:
    """Format a timedelta as human-readable string."""
    total_seconds = int(td.total_seconds())
    if total_seconds < 60:
        return f"{total_seconds}s"
    if total_seconds < 3600:
        return f"{total_seconds // 60}m"
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    if minutes:
        return f"{hours}h {minutes}m"
    return f"{hours}h"
