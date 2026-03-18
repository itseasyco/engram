# Session Memory Scaffolding

Per-project session memory auto-scaffolding for OpenClaw agents.

## Overview

Session memory scaffolding creates and manages per-project, per-agent memory structures. Each session gets its own memory directory with:
- **memory.md** — Long-form memory, decisions, patterns, preferences
- **context.json** — Structured session metadata and execution tracking

## Why Session Memory?

**Problem:** Agents accumulate knowledge within a project but lose it across sessions. This causes:
- Repeated investigation of the same issues
- Loss of architectural insights
- Forgotten preferences and gotchas
- No continuity across team members

**Solution:** Session memory creates a persistent, structured knowledge base per project that:
- Captures decisions and architectural patterns
- Tracks execution cost, gate decisions, and learnings
- Bridges sessions and enables knowledge sharing
- Integrates with agent workflows

## Relationship to MEMORY.md

| Aspect | MEMORY.md | Session Memory |
|--------|-----------|----------------|
| Scope | Agent-wide, global | Per-project, per-session |
| Content | Career memories, lessons | Project context, decisions, patterns |
| Lifetime | Long-term (months) | Session-bound (grows per session) |
| Location | `~/.openclaw/MEMORY.md` | `~/.openclaw-test/data/project-sessions/<project>/<agent>/<session>/` |
| Use case | Agent continuity | Project continuity |
| Shareable | No (personal) | Yes (team context) |

## Architecture

### Directory Structure

```
~/.openclaw-test/data/project-sessions/
├── easy-api/
│   ├── agent-a/
│   │   ├── 1234567890/
│   │   │   ├── memory.md
│   │   │   ├── context.json
│   │   │   └── .git/
│   │   └── 1234567891/
│   │       ├── memory.md
│   │       ├── context.json
│   │       └── .git/
│   └── claude-code/
│       ├── 1234567892/
│       │   ├── memory.md
│       │   ├── context.json
│       │   └── .git/
│       └── ...
├── easy-dashboard/
│   └── ...
└── ...
```

### File Formats

#### memory.md

Long-form markdown with sections for:

```markdown
# Project Memory — [project-name]

## Quick Reference
- **Codebase:** [path]
- **Agent:** [agent-id]
- **Channel:** [channel]
- **Last Updated:** [timestamp]

## Key Decisions
(Decisions made in this project)

## Architecture Patterns
(Codebase patterns to remember)

## Preferences
(Agent/human preferences for this project)

## Known Issues
(Gotchas, edge cases, tech debt)

## Recent Sessions
(Summary of recent work)
```

Agents append to this file to record learnings, discoveries, and insights.

#### context.json

Structured metadata for tracking execution:

```json
{
  "project": {
    "name": "easy-api",
    "slug": "easy-api",
    "path": "/path/to/easy-api"
  },
  "agent": {
    "id": "agent-a"
  },
  "session": {
    "id": "1234567890",
    "channel": "discord",
    "created_at": "2026-03-17T21:58:00Z"
  },
  "execution": {
    "cost_usd": 2.50,
    "gate_decisions": [
      "PR review: approved",
      "Tests: passed"
    ],
    "exit_code": 0,
    "learnings": [
      "Discovered new API pattern",
      "Fixed memory cleanup issue"
    ],
    "updated_at": "2026-03-17T22:00:00Z"
  }
}
```

## Usage

### Initialize a New Session

```bash
# Basic usage
openclaw-memory-init /path/to/project agent-a discord

# With explicit session ID
openclaw-memory-init /path/to/project claude-code webchat session-xyz
```

**Output:**
- Creates `~/.openclaw-test/data/project-sessions/<project>/<agent>/<session>/`
- Populates `memory.md` and `context.json`
- Initializes git repository
- Ready to use

**Example:**
```bash
$ openclaw-memory-init ~/easy-api agent-a discord
✓ Created memory.md
✓ Created context.json
✓ Initialized git repository

Session Memory Initialized
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Project:   easy-api
Agent:     agent-a
Channel:   discord
Session:   1234567890
Location:  /Users/andrew/.openclaw-test/data/project-sessions/easy-api/agent-a/1234567890
```

### Record Execution Results

```bash
# Basic execution result
openclaw-memory-append /path/to/session \
  --cost 2.50 \
  --exit-code 0

# With learnings and gate decisions
openclaw-memory-append /path/to/session \
  --cost 1.50 \
  --exit-code 0 \
  --learning "Discovered new API pattern" \
  --learning "Fixed memory cleanup issue" \
  --gate "PR review: approved" \
  --gate "Tests: passed"
```

**Outputs:**
- Updates `context.json` with cost, exit code, gate decisions
- Appends execution summary to `memory.md`
- Commits changes to git

**Example:**
```bash
$ openclaw-memory-append /path/to/session --cost 2.50 --exit-code 0
✓ Updated context.json
✓ Appended to memory.md
✓ Committed to git

Execution Results Recorded
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Cost:       $2.50
Exit Code:  0
```

### Integrate with Agents

In agent initialization:

```bash
# Create session memory
SESSION_DIR=$(openclaw-memory-init ~/my-project my-agent discord)

# Run agent work...
my-agent-command

# Record results
openclaw-memory-append "$SESSION_DIR" \
  --cost "$EXECUTION_COST" \
  --exit-code "$EXIT_CODE" \
  --learning "Discovered X" \
  --gate "Approved by reviewer"
```

## Configuration

Enable/disable scaffolding via `~/.openclaw-test/config/memory/enable-scaffolding.json`:

```json
{
  "enabled": true,
  "auto_scaffold": true,
  "auto_git_init": true,
  "default_template": "~/.openclaw-test/templates/project-memory-scaffold.md",
  "session_base": "~/.openclaw-test/data/project-sessions",
  "agent_channel_pairs": [
    {
      "agent": "*",
      "channel": "*"
    }
  ]
}
```

**Options:**
- `enabled` — Master switch for scaffolding
- `auto_scaffold` — Auto-create session memory on first agent session
- `auto_git_init` — Initialize git in each session directory
- `default_template` — Path to memory.md template
- `session_base` — Root directory for all session memories
- `agent_channel_pairs` — List of agent/channel combos that get scaffolding (use `*` for wildcard)

## Best Practices

### What to Record

**In memory.md:**
- ✅ Architectural decisions (why we chose X over Y)
- ✅ Patterns and conventions in the codebase
- ✅ Agent/human preferences
- ✅ Known gotchas and edge cases
- ✅ Links to relevant docs/issues

**In context.json:**
- ✅ Execution cost (for budgeting)
- ✅ Gate decisions (approvals, reviews)
- ✅ Exit codes (success/failure)
- ✅ Learnings (key insights from this session)

### What NOT to Record

- ❌ Personal information or secrets
- ❌ API keys, tokens, credentials
- ❌ Customer-sensitive data
- ❌ Duplicate information (avoid copying from other docs)

### Session Lifecycle

1. **Initialize** — `openclaw-memory-init` creates new session
2. **Capture** — Agent updates memory.md with discoveries
3. **Record** — `openclaw-memory-append` logs results
4. **Review** — Next agent (or same agent in next session) reads memory
5. **Iterate** — Build on previous work; update memory with new insights

## Examples

### Example 1: Bug Fix Session

```bash
# Initialize
SESSION_DIR=$(openclaw-memory-init ~/easy-api agent-a discord)
cd "$SESSION_DIR"

# Agent edits memory.md with:
# - Description of the bug
# - Root cause analysis
# - The fix applied

# Record results
openclaw-memory-append "$SESSION_DIR" \
  --cost 1.25 \
  --exit-code 0 \
  --learning "Bug was in rate limiter cache invalidation logic" \
  --learning "Added test case to prevent regression" \
  --gate "PR approved by @maintainer"
```

### Example 2: Feature Development

```bash
# Initialize
SESSION_DIR=$(openclaw-memory-init ~/easy-dashboard claude-code discord)

# Multiple sessions:
# Session 1: Design review → record decision
openclaw-memory-append "$SESSION_DIR" \
  --cost 2.50 \
  --exit-code 0 \
  --learning "Chose React hooks over class components"

# Session 2: Implementation
openclaw-memory-append "$SESSION_DIR" \
  --cost 3.75 \
  --exit-code 0 \
  --learning "Discovered performance issue with useState"

# Session 3: Final review
openclaw-memory-append "$SESSION_DIR" \
  --cost 1.50 \
  --exit-code 0 \
  --gate "Code review: approved"
  --gate "Tests: 95% coverage"
```

### Example 3: Cross-Agent Handoff

```bash
# Agent A's session
SESSION_A=$(openclaw-memory-init ~/my-project agent-a discord)
openclaw-memory-append "$SESSION_A" \
  --cost 2.0 \
  --exit-code 0 \
  --learning "API endpoint structure follows OpenAPI 3.1"

# Agent B reads Agent A's memory.md
cat ~/.openclaw-test/data/project-sessions/my-project/agent-a/*/memory.md

# Agent B's session
SESSION_B=$(openclaw-memory-init ~/my-project agent-b slack)
# Agent B uses learnings from Agent A to inform their work
```

## Troubleshooting

### "Session directory does not exist"

**Problem:** `openclaw-memory-init` can't find the project path.

**Solution:** Ensure the path exists:
```bash
ls -la /path/to/project
openclaw-memory-init /absolute/path/to/project agent-id channel
```

### "Missing context.json or memory.md"

**Problem:** `openclaw-memory-append` can't find required files.

**Solution:** Ensure you pass the correct session directory:
```bash
# Correct
openclaw-memory-append ~/.openclaw-test/data/project-sessions/my-project/agent-a/1234567890

# Wrong
openclaw-memory-append ~/.openclaw-test/data/project-sessions/my-project
```

### Git commit fails

**Problem:** Git initialization disabled or permission issues.

**Solution:** 
```bash
# Re-initialize git manually
cd ~/.openclaw-test/data/project-sessions/my-project/agent-a/SESSION_ID
git init
git config user.email "wren@itseasy.co"
git config user.name "Wren (OpenClaw)"
git add .
git commit -m "init: session memory"
```

## Integration Points

Session memory works with:
- **MEMORY.md** — Agent-wide continuity (complementary, not replacement)
- **Project wikis** — Link to project-specific docs
- **Git history** — Each session tracked in its own git repo
- **QMD** — Session memories can be indexed and searched
- **Slack/Discord** — Share session memory summaries with teams

## Future Enhancements

Potential improvements (Phase 3.1):
- Auto-index session memories in QMD for search
- Auto-share execution summaries to Discord/Slack
- Merge memories from multiple agents working on same project
- Memory analytics (cost trends, decision frequency)
- Memory pruning (archive old sessions)
- Web UI for browsing project memories

---

**Created by Agent I - Phase 3 Session Memory Scaffolding**
