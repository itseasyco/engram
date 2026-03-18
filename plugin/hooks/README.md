# OpenClaw LACP Hooks

Modular safety and quality hooks for OpenClaw agent sessions, adapted from LACP (Local Agent Control Plane).

## Overview

These hooks provide:

1. **Session-start hook** — Injects git context at the beginning of agent sessions
2. **PreToolUse guard** (coming) — Blocks dangerous operations before execution  
3. **Stop quality gate** (coming) — Detects incomplete work before agent stops
4. **Write validation** (coming) — Validates file schemas before writes

## Session-Start Hook

The `session-start.py` handler runs at the beginning of each OpenClaw session to inject contextual information about the current repository state.

### What It Does

- **Git branch detection** — Tells the agent what branch you're on
- **Recent commits** — Last 3 commits for context
- **Modified files** — Unstaged changes in the working directory
- **Staged files** — Changes added to the index
- **Repository status** — Clean vs dirty workspace
- **Test command detection** — Auto-detects the test runner (npm, cargo, make, pytest, etc.)
- **Test command caching** — Caches detected test command for the stop hook

### Output Format

The hook outputs valid JSON with a `systemMessage` key:

```json
{
  "systemMessage": "=== Git Context ===\nBranch: main\nStatus: clean\n\n=== Post-Compaction Reminder ===\n..."
}
```

This message is injected into the agent's system prompt, providing immediate visibility of:
- What branch you're on
- Whether there are uncommitted changes
- Recent work history
- How to run tests

### Supported Project Types

The hook auto-detects test commands for:

- **Node.js** — `package.json` (npm, yarn, pnpm, bun)
- **Rust** — `Cargo.toml` (cargo test)
- **Python** — `pyproject.toml` (pytest)
- **Go** — `go.mod` (go test)
- **Any project** — `Makefile` (make test)

### Configuration

The hook respects the following environment variables:

- `OPENCLAW_SESSION_ID` — Session ID for caching (falls back to `CLAUDE_SESSION_ID`)
- `PWD` — Current working directory (standard)

### Testing

Run the comprehensive test suite:

```bash
cd ~/.openclaw-test/plugins/lacp-hooks
python3 -m pytest tests/test_session_start.py -v
```

Tests cover:
- Git repository detection
- Branch detection (main, custom branches)
- Recent commit history
- Modified and staged files
- Repository status (clean, dirty, mixed)
- Test command auto-detection (all supported types)
- Payload parsing (JSON, empty, invalid)
- Context formatting
- Test command caching
- End-to-end execution

### Exit Behavior

- **Exit 0** — Success (outputs JSON with systemMessage)
- **Exit 1** — Hook error (logged but doesn't block session start)

### Graceful Degradation

The hook is designed to fail gracefully:
- If not in a git repository → no git context
- If test command can't be detected → skip test command message
- If git operations timeout (5s) → skip that operation
- Invalid input → empty context

## Hook Protocol

All OpenClaw hooks follow this protocol:

1. **Input:** JSON payload on stdin (may be empty)
2. **Output:** JSON on stdout with hook-specific format
3. **Exit code:** 0 = success, 1 = error (non-blocking)

## Integration with OpenClaw

These hooks are designed to integrate with OpenClaw's native event system:

- `SessionStart` event → `session-start.py` hook
- `PreToolUse` event → `pretool-guard.py` hook  
- `Stop` event → `stop-quality-gate.py` hook
- `Write` event → `write-validate.py` hook

## Files

```
handlers/
  ├── session-start.py        Session context injection
  ├── pretool-guard.py        (Coming) Dangerous pattern blocking
  ├── stop-quality-gate.py    (Coming) Quality gate
  └── write-validate.py       (Coming) Schema validation

tests/
  ├── test_session_start.py   Comprehensive tests
  ├── test_pretool_guard.py   (Coming)
  └── test_integration.py     (Coming)

README.md                      This file
plugin.json                    (Coming) Manifest
```

## Architecture Notes

### Adapted from LACP

This implementation is adapted from [LACP](https://github.com/protocolbuffers/lacp) `session_start.py` with changes for OpenClaw:

- Removed LACP-specific imports and config paths
- Added explicit OpenClaw session ID support
- Simplified test command caching (uses /tmp)
- Added matcher support (startup, compact)
- Improved error handling and logging

### Why This Approach?

1. **Local safety** — Everything runs locally, no cloud dependencies
2. **Modular** — Each hook is independent and can be enabled/disabled
3. **Tested** — Comprehensive unit and integration tests
4. **Graceful** — Failures don't break agent execution
5. **Observable** — Hook decisions are logged for audit trails

## Future Phases

- **Phase 2:** Policy gates (risk tiers, budget limits, context contracts)
- **Phase 3:** Evidence-based orchestration (E2E verification, PR gates)
- **Phase 4:** Multi-agent coordination and approval workflows

## Contributing

When adding new hooks or features:

1. Write tests first (`tests/test_*.py`)
2. Run all tests: `python3 -m pytest tests/ -v`
3. Ensure 85%+ code coverage
4. Update this README
5. Commit with clear message: `feat: <hook-name> — <description>`
