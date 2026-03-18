# Context Injection

## Overview

`openclaw-lacp-context` injects relevant LACP facts into LCM session context windows at session start. This ensures agents begin each session informed by accumulated organizational knowledge.

## How It Works

1. Loads Layer 1 facts (MEMORY.md, patterns.md, context.json)
2. Loads Layer 2 links (Obsidian vault wikilinks)
3. Scores facts by relevance to the current topic
4. Formats and outputs prompt-ready facts

## Commands

### inject

Inject relevant LACP facts at session start.

```bash
openclaw-lacp-context inject \
  --project easy-api \
  --agent wren \
  --depth 2 \
  --topic "embedded-checkout"
```

Options:
- `--project` (required): Project name
- `--agent`: Agent name (for filtering)
- `--depth`: Graph traversal depth (default: 2)
- `--topic`: Topic filter
- `--format`: Output format — `text`, `json`, `markdown` (default: text)

### query

Query facts interactively by topic.

```bash
openclaw-lacp-context query \
  --topic "settlement" \
  --min-score 75
```

Options:
- `--topic` (required): Topic to search
- `--project`: Scope to specific project
- `--min-score`: Minimum relevance score (default: 50)
- `--format`: Output format

### list

List available contexts for a project.

```bash
openclaw-lacp-context list --project easy-api
```

Shows Layer 1 and Layer 2 statistics.

## Configuration

Environment variables:
- `OPENCLAW_MEMORY_ROOT`: Layer 1 memory directory (default: `~/.openclaw/memory`)
- `OPENCLAW_VAULT_ROOT`: Layer 2 vault directory (default: `~/.openclaw/vault`)

## Integration

To inject context at every session start, add to your session-start hook:

```bash
# In session-start.py or equivalent
context = subprocess.run(
    ["openclaw-lacp-context", "inject",
     "--project", project_name,
     "--topic", session_topic,
     "--format", "markdown"],
    capture_output=True, text=True
)
# Prepend to LCM context window
```
