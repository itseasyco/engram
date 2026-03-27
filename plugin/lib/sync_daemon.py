#!/usr/bin/env python3
"""
ob sync daemon management for openclaw-lacp-fusion.

Manages `ob sync --continuous` as a background daemon:
  - macOS: launchd plist
  - Linux: systemd user unit

Provides start(), stop(), status() operations.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

DAEMON_LABEL = "io.openclaw.ob-sync"
SYSTEMD_UNIT = "openclaw-ob-sync.service"


@dataclass
class DaemonStatus:
    running: bool
    pid: Optional[int]
    platform: str  # "macos" | "linux" | "unsupported"
    method: str  # "launchd" | "systemd" | "none"
    message: str

    def to_dict(self) -> dict:
        return {
            "running": self.running,
            "pid": self.pid,
            "platform": self.platform,
            "method": self.method,
            "message": self.message,
        }


def _detect_platform() -> tuple[str, str]:
    """Detect OS and daemon method. Returns (platform, method)."""
    system = platform.system().lower()
    if system == "darwin":
        return "macos", "launchd"
    elif system == "linux":
        return "linux", "systemd"
    return "unsupported", "none"


def _ob_binary() -> str:
    """Find the ob binary path."""
    ob = shutil.which("ob")
    if ob:
        return ob
    # Common locations
    for candidate in [
        "/usr/local/bin/ob",
        os.path.expanduser("~/.npm-global/bin/ob"),
        os.path.expanduser("~/.local/bin/ob"),
    ]:
        if os.path.isfile(candidate):
            return candidate
    return "ob"  # Fall back, let PATH resolve


def _vault_path() -> str:
    """Resolve the vault path for the daemon."""
    from mode import get_config
    return get_config().vault_path


# ---------------------------------------------------------------------------
# macOS launchd
# ---------------------------------------------------------------------------

def _plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{DAEMON_LABEL}.plist"


def _generate_plist(vault_path: str) -> str:
    ob = _ob_binary()
    log_dir = Path.home() / ".openclaw" / "logs"
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{DAEMON_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{ob}</string>
        <string>sync</string>
        <string>--continuous</string>
        <string>--vault</string>
        <string>{vault_path}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{log_dir}/ob-sync.stdout.log</string>
    <key>StandardErrorPath</key>
    <string>{log_dir}/ob-sync.stderr.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:{Path.home()}/.npm-global/bin</string>
    </dict>
</dict>
</plist>
"""


def _launchd_start(vault_path: str) -> DaemonStatus:
    plist = _plist_path()
    plist.parent.mkdir(parents=True, exist_ok=True)
    log_dir = Path.home() / ".openclaw" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    plist.write_text(_generate_plist(vault_path), encoding="utf-8")

    result = subprocess.run(
        ["launchctl", "load", "-w", str(plist)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return DaemonStatus(
            running=False, pid=None, platform="macos", method="launchd",
            message=f"launchctl load failed: {result.stderr.strip()}",
        )

    return _launchd_status()


def _launchd_stop() -> DaemonStatus:
    plist = _plist_path()
    if not plist.exists():
        return DaemonStatus(
            running=False, pid=None, platform="macos", method="launchd",
            message="Daemon not installed (no plist found)",
        )

    subprocess.run(
        ["launchctl", "unload", "-w", str(plist)],
        capture_output=True, text=True,
    )
    plist.unlink(missing_ok=True)

    return DaemonStatus(
        running=False, pid=None, platform="macos", method="launchd",
        message="Daemon stopped and unloaded",
    )


def _launchd_status() -> DaemonStatus:
    result = subprocess.run(
        ["launchctl", "list", DAEMON_LABEL],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return DaemonStatus(
            running=False, pid=None, platform="macos", method="launchd",
            message="Daemon not running",
        )

    # Parse PID from launchctl list output
    pid = None
    for line in result.stdout.strip().splitlines():
        parts = line.split("\t")
        if len(parts) >= 1:
            try:
                pid = int(parts[0])
            except (ValueError, IndexError):
                pass
    running = pid is not None and pid > 0

    return DaemonStatus(
        running=running, pid=pid if running else None,
        platform="macos", method="launchd",
        message=f"Daemon running (PID {pid})" if running else "Daemon loaded but not running",
    )


# ---------------------------------------------------------------------------
# Linux systemd
# ---------------------------------------------------------------------------

def _unit_path() -> Path:
    return Path.home() / ".config" / "systemd" / "user" / SYSTEMD_UNIT


def _generate_unit(vault_path: str) -> str:
    ob = _ob_binary()
    return f"""[Unit]
Description=OpenClaw ob sync daemon
After=network.target

[Service]
Type=simple
ExecStart={ob} sync --continuous --vault {vault_path}
Restart=always
RestartSec=10
Environment=PATH=/usr/local/bin:/usr/bin:/bin

[Install]
WantedBy=default.target
"""


def _systemd_start(vault_path: str) -> DaemonStatus:
    unit = _unit_path()
    unit.parent.mkdir(parents=True, exist_ok=True)
    unit.write_text(_generate_unit(vault_path), encoding="utf-8")

    subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)
    result = subprocess.run(
        ["systemctl", "--user", "enable", "--now", SYSTEMD_UNIT],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return DaemonStatus(
            running=False, pid=None, platform="linux", method="systemd",
            message=f"systemctl enable failed: {result.stderr.strip()}",
        )

    return _systemd_status()


def _systemd_stop() -> DaemonStatus:
    subprocess.run(
        ["systemctl", "--user", "disable", "--now", SYSTEMD_UNIT],
        capture_output=True, text=True,
    )
    unit = _unit_path()
    unit.unlink(missing_ok=True)
    subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)

    return DaemonStatus(
        running=False, pid=None, platform="linux", method="systemd",
        message="Daemon stopped and disabled",
    )


def _systemd_status() -> DaemonStatus:
    result = subprocess.run(
        ["systemctl", "--user", "is-active", SYSTEMD_UNIT],
        capture_output=True, text=True,
    )
    active = result.stdout.strip() == "active"

    pid = None
    if active:
        pid_result = subprocess.run(
            ["systemctl", "--user", "show", SYSTEMD_UNIT, "--property=MainPID", "--value"],
            capture_output=True, text=True,
        )
        try:
            pid = int(pid_result.stdout.strip())
            if pid == 0:
                pid = None
        except ValueError:
            pass

    return DaemonStatus(
        running=active, pid=pid,
        platform="linux", method="systemd",
        message=f"Daemon running (PID {pid})" if active else "Daemon not running",
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def start(vault_path: str = "") -> DaemonStatus:
    """Start the ob sync daemon."""
    if not vault_path:
        vault_path = _vault_path()

    plat, method = _detect_platform()
    if method == "launchd":
        return _launchd_start(vault_path)
    elif method == "systemd":
        return _systemd_start(vault_path)
    return DaemonStatus(
        running=False, pid=None, platform=plat, method=method,
        message=f"Unsupported platform: {plat}. Manually run: ob sync --continuous --vault {vault_path}",
    )


def stop() -> DaemonStatus:
    """Stop the ob sync daemon."""
    plat, method = _detect_platform()
    if method == "launchd":
        return _launchd_stop()
    elif method == "systemd":
        return _systemd_stop()
    return DaemonStatus(
        running=False, pid=None, platform=plat, method=method,
        message=f"Unsupported platform: {plat}",
    )


def status() -> DaemonStatus:
    """Check the ob sync daemon status."""
    plat, method = _detect_platform()
    if method == "launchd":
        return _launchd_status()
    elif method == "systemd":
        return _systemd_status()
    return DaemonStatus(
        running=False, pid=None, platform=plat, method=method,
        message=f"Unsupported platform: {plat}",
    )
