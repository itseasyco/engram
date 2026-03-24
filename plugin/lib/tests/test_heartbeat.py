"""Tests for plugin.lib.heartbeat -- heartbeat system."""

import json
import sys
from datetime import datetime, UTC, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from lib.heartbeat import (
    write_heartbeat,
    check_heartbeat,
    update_outage_reconciliation,
    HEARTBEAT_FILENAME,
    ALERT_THRESHOLD,
)


class TestWriteHeartbeat:
    def test_creates_heartbeat_file(self, tmp_path):
        vault = str(tmp_path / "vault")
        Path(vault).mkdir()
        path = write_heartbeat(vault, cycle_duration_seconds=42, notes_processed=18)
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["status"] == "healthy"
        assert data["cycle_duration_seconds"] == 42
        assert data["notes_processed"] == 18
        assert data["missed_heartbeats"] == 0

    def test_preserves_outage_log(self, tmp_path):
        vault = str(tmp_path / "vault")
        Path(vault).mkdir()
        # Write initial heartbeat
        write_heartbeat(vault)
        # Manually add outage_log entry
        hb_path = Path(vault) / HEARTBEAT_FILENAME
        data = json.loads(hb_path.read_text())
        data["outage_log"] = [{"start": "2026-01-01T00:00:00", "end": "2026-01-01T06:00:00", "files_queued_during_outage": 5, "reconciliation_status": "completed"}]
        hb_path.write_text(json.dumps(data))
        # Write another heartbeat
        write_heartbeat(vault)
        data2 = json.loads(hb_path.read_text())
        assert len(data2["outage_log"]) == 1


class TestCheckHeartbeat:
    def test_no_file_returns_no_heartbeat(self, tmp_path):
        result = check_heartbeat(str(tmp_path))
        assert result["status"] == "no_heartbeat"

    def test_recent_heartbeat_is_healthy(self, tmp_path):
        vault = str(tmp_path / "vault")
        Path(vault).mkdir()
        write_heartbeat(vault)
        result = check_heartbeat(vault)
        assert result["status"] == "healthy"
        assert result["missed_heartbeats"] == 0

    def test_old_heartbeat_triggers_warning(self, tmp_path):
        vault = str(tmp_path / "vault")
        Path(vault).mkdir()
        write_heartbeat(vault)
        # Backdate the heartbeat
        hb_path = Path(vault) / HEARTBEAT_FILENAME
        data = json.loads(hb_path.read_text())
        old_time = (datetime.now(UTC) - timedelta(hours=9)).isoformat()
        data["last_seen"] = old_time
        hb_path.write_text(json.dumps(data))
        result = check_heartbeat(vault, cycle_interval_hours=4)
        assert result["status"] == "warning"
        assert result["missed_heartbeats"] >= 1

    def test_very_old_heartbeat_triggers_outage(self, tmp_path):
        vault = str(tmp_path / "vault")
        Path(vault).mkdir()
        write_heartbeat(vault)
        hb_path = Path(vault) / HEARTBEAT_FILENAME
        data = json.loads(hb_path.read_text())
        old_time = (datetime.now(UTC) - timedelta(hours=20)).isoformat()
        data["last_seen"] = old_time
        hb_path.write_text(json.dumps(data))
        result = check_heartbeat(vault, cycle_interval_hours=4)
        assert result["status"] == "outage"
        assert result["missed_heartbeats"] >= ALERT_THRESHOLD


class TestOutageReconciliation:
    def test_update_reconciliation(self, tmp_path):
        vault = str(tmp_path / "vault")
        Path(vault).mkdir()
        write_heartbeat(vault)
        hb_path = Path(vault) / HEARTBEAT_FILENAME
        # Simulate outage recovery (heartbeat with missed >= ALERT_THRESHOLD)
        data = json.loads(hb_path.read_text())
        data["missed_heartbeats"] = ALERT_THRESHOLD
        hb_path.write_text(json.dumps(data))
        # Write recovery heartbeat (this should close the outage)
        write_heartbeat(vault)
        data2 = json.loads(hb_path.read_text())
        assert len(data2["outage_log"]) == 1
        assert data2["outage_log"][-1]["reconciliation_status"] == "pending"
        # Now reconcile
        update_outage_reconciliation(vault, files_queued=7, reconciliation_status="completed")
        data3 = json.loads(hb_path.read_text())
        assert data3["outage_log"][-1]["files_queued_during_outage"] == 7
        assert data3["outage_log"][-1]["reconciliation_status"] == "completed"
        assert data3["status"] == "healthy"
