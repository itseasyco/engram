---
name: engram-session-capture
description: "Automatically capture session memory to Engram vault on /new or /reset"
metadata:
  openclaw:
    emoji: "🧠"
    events: ["command:new", "command:reset"]
    requires:
      bins: ["python3"]
---

# Engram Session Capture

Automatically extracts decisions, learnings, tasks, and key context from the session transcript and saves a structured memory file to the Engram vault.

## What It Does

When you issue `/new` or `/reset`:
1. Reads the session transcript (last N messages)
2. Extracts key decisions, tasks completed/pending, and notable facts
3. Writes a per-agent session file to `vault/memory/YYYY-MM-DD/`
4. Updates the daily index with wikilinks

## How It Works

No agent action needed. The capture happens automatically as a side effect of ending a session. The agent's name is derived from the session key.

## Requirements

- Python 3 must be installed
- Engram plugin must be installed (`~/.openclaw/extensions/engram/`)
