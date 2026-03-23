#!/usr/bin/env python3
"""
Session memory writer for Engram.

Writes session memories to a structured daily folder layout:

  vault/memory/
  ├── 2026-03-23/
  │   ├── index.md              ← Daily summary with wikilinks
  │   ├── wren-session-1430.md  ← Individual session file
  │   ├── zoe-session-1500.md
  │   └── ...
  └── 2026-03-22/
      └── ...

Each session file links back to the agent.
The daily index is regenerated whenever a new session is added.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def _get_mode() -> str:
    """Get current operating mode, default standalone."""
    try:
        from .mode import get_mode
        return get_mode()
    except ImportError:
        return os.environ.get("LACP_MODE", "standalone")


def _memory_root() -> Path:
    """Return the memory directory based on operating mode.

    Uses vault_paths resolver — curator can change locations via vault-schema.json.
    Standalone/curator: vault_paths.memory (default: 01_memory/)
    Connected: vault_paths.inbox_session (default: 05_Inbox/queue-session/)
    """
    try:
        from .vault_paths import resolve
        mode = _get_mode()
        if mode == "connected":
            return resolve("inbox_session")
        return resolve("memory")
    except (ImportError, KeyError):
        # Fallback if vault_paths not available
        vault = os.environ.get(
            "LACP_OBSIDIAN_VAULT",
            os.environ.get("OPENCLAW_VAULT", ""),
        )
        if not vault:
            openclaw_home = os.environ.get("OPENCLAW_HOME", os.path.expanduser("~/.openclaw"))
            vault = os.path.join(openclaw_home, "data", "knowledge")
        mode = _get_mode()
        if mode == "connected":
            return Path(vault) / "05_Inbox" / "queue-session"
        return Path(vault) / "01_memory"


def _sanitize_agent_name(name: str) -> str:
    """Clean agent name for use in filenames."""
    name = name.lower().strip()
    name = re.sub(r"[^a-z0-9_-]", "-", name)
    name = re.sub(r"-+", "-", name).strip("-")
    return name or "unknown"


def _today_str(now: Optional[datetime] = None) -> str:
    """Return today's date as YYYY-MM-DD."""
    dt = now or datetime.now(timezone.utc)
    return dt.strftime("%Y-%m-%d")


def _time_str(now: Optional[datetime] = None) -> str:
    """Return current time as HHMM."""
    dt = now or datetime.now(timezone.utc)
    return dt.strftime("%H%M")


def write_session_memory(
    agent_name: str,
    session_id: str = "",
    summary: str = "",
    facts_promoted: list[str] | None = None,
    tasks_completed: list[str] | None = None,
    tasks_pending: list[str] | None = None,
    key_decisions: list[str] | None = None,
    files_modified: list[str] | None = None,
    conversation_excerpt: str = "",
    channel: str = "",
    now: Optional[datetime] = None,
) -> dict:
    """
    Write a session memory file to the daily folder.

    Returns dict with paths and metadata.
    """
    dt = now or datetime.now(timezone.utc)
    today = _today_str(dt)
    time = _time_str(dt)
    agent_slug = _sanitize_agent_name(agent_name)

    # Create daily folder: 01_memory/YYYY-MM/YYYY-MM-DD/ (standalone)
    # or 05_Inbox/queue-session/ (connected, flat)
    month = dt.strftime("%Y-%m")
    mode = _get_mode()
    if mode == "connected":
        daily_dir = _memory_root()
    else:
        daily_dir = _memory_root() / month / today
    daily_dir.mkdir(parents=True, exist_ok=True)

    # Session filename
    filename = f"{agent_slug}-session-{time}.md"
    session_path = daily_dir / filename

    # Handle collision (same agent, same minute)
    counter = 1
    while session_path.exists():
        counter += 1
        filename = f"{agent_slug}-session-{time}-{counter}.md"
        session_path = daily_dir / filename

    # Build session file content
    facts_promoted = facts_promoted or []
    tasks_completed = tasks_completed or []
    tasks_pending = tasks_pending or []
    key_decisions = key_decisions or []
    files_modified = files_modified or []

    content = f"""---
title: "{agent_name} Session — {today} {time}"
category: memory
tags: [session, {agent_slug}, memory]
created: {dt.isoformat()}
author: {agent_slug}
source: session-memory
agent: {agent_name}
session_id: {session_id}
channel: {channel}
status: active
---

# {agent_name} — Session {time} UTC

"""

    if summary:
        content += f"## Summary\n\n{summary}\n\n"

    if key_decisions:
        content += "## Key Decisions\n\n"
        for d in key_decisions:
            content += f"- {d}\n"
        content += "\n"

    if tasks_completed:
        content += "## Completed\n\n"
        for t in tasks_completed:
            content += f"- [x] {t}\n"
        content += "\n"

    if tasks_pending:
        content += "## Pending\n\n"
        for t in tasks_pending:
            content += f"- [ ] {t}\n"
        content += "\n"

    if facts_promoted:
        content += "## Facts Promoted to Engram\n\n"
        for f in facts_promoted:
            content += f"- {f}\n"
        content += "\n"

    if files_modified:
        content += "## Files Modified\n\n"
        for f in files_modified:
            content += f"- `{f}`\n"
        content += "\n"

    if conversation_excerpt:
        content += f"## Conversation Excerpt\n\n{conversation_excerpt}\n\n"

    content += f"---\n*Session recorded by Engram*\n"

    session_path.write_text(content, encoding="utf-8")

    # Update daily index
    _update_daily_index(daily_dir, today)

    return {
        "session_path": str(session_path),
        "daily_index": str(daily_dir / "index.md"),
        "agent": agent_name,
        "date": today,
        "time": time,
        "facts_promoted": len(facts_promoted),
    }


def _update_daily_index(daily_dir: Path, date_str: str) -> Path:
    """Regenerate the daily index.md with links to all session files."""
    index_path = daily_dir / "index.md"

    # Collect all session files
    session_files = sorted(
        f for f in daily_dir.iterdir()
        if f.suffix == ".md" and f.name != "index.md"
    )

    # Extract metadata from each session file
    sessions = []
    agents = set()
    total_facts = 0

    for sf in session_files:
        text = sf.read_text(encoding="utf-8")

        # Parse agent name from frontmatter
        agent_match = re.search(r"^agent:\s*(.+)$", text, re.MULTILINE)
        agent = agent_match.group(1).strip() if agent_match else sf.stem.split("-session-")[0]
        agents.add(agent)

        # Parse time from filename
        time_match = re.search(r"session-(\d{4})", sf.name)
        time_str = time_match.group(1) if time_match else "????"

        # Count facts promoted
        facts = text.count("## Facts Promoted")
        fact_lines = len(re.findall(r"^- .+$", text.split("## Facts Promoted")[1] if "## Facts Promoted" in text else "", re.MULTILINE))
        total_facts += fact_lines

        # Get summary (first line after ## Summary)
        summary_match = re.search(r"## Summary\n\n(.+?)(?:\n\n|\n##)", text, re.DOTALL)
        summary_preview = ""
        if summary_match:
            summary_preview = summary_match.group(1).strip()[:100]
            if len(summary_match.group(1).strip()) > 100:
                summary_preview += "..."

        sessions.append({
            "file": sf.name,
            "stem": sf.stem,
            "agent": agent,
            "time": time_str,
            "summary": summary_preview,
        })

    # Build index
    agent_list = ", ".join(sorted(agents))
    content = f"""---
title: "Daily Memory — {date_str}"
category: memory
tags: [daily, memory, index]
created: {date_str}
updated: {datetime.now(timezone.utc).isoformat()}
author: engram
source: session-memory
agents: [{agent_list}]
session_count: {len(sessions)}
facts_promoted: {total_facts}
status: active
---

# {date_str}

**Agents:** {agent_list}
**Sessions:** {len(sessions)}
**Facts promoted:** {total_facts}

## Sessions

"""

    for s in sessions:
        line = f"- **{s['time']} UTC** — [[{s['stem']}]] ({s['agent']})"
        if s["summary"]:
            line += f" — {s['summary']}"
        content += line + "\n"

    content += "\n---\n*Index generated by Engram*\n"

    index_path.write_text(content, encoding="utf-8")
    return index_path


def list_daily_sessions(date_str: Optional[str] = None) -> dict:
    """List all sessions for a given date (default: today)."""
    date_str = date_str or _today_str()
    daily_dir = _memory_root() / date_str

    if not daily_dir.exists():
        return {"date": date_str, "sessions": [], "exists": False}

    session_files = sorted(
        f.name for f in daily_dir.iterdir()
        if f.suffix == ".md" and f.name != "index.md"
    )

    return {
        "date": date_str,
        "sessions": session_files,
        "count": len(session_files),
        "exists": True,
        "index": str(daily_dir / "index.md"),
    }
