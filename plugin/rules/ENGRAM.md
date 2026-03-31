# Engram Memory Protocol

## Automatic Behaviors

These behaviors are enforced by engram hooks and should be followed by all agents.

### Session Start
- On session start, engram injects git context, test commands, and relevant memory facts automatically via hooks.
- Review the injected context before starting work.
- If GitNexus index is reported stale, run `npx gitnexus analyze` before making code changes.

### During Work
- **Query before coding**: Before starting any non-trivial task, use `engram_memory_query` to check if there are relevant decisions, patterns, or context from past sessions.
- **Promote immediately**: When you discover something important — an architectural decision, a bug pattern, a team preference, a convention — promote it to persistent memory using `engram_promote_fact` right away. Don't wait until the end of the session.
- **Categories for promotion**:
  - `decision` — architectural or design decisions with rationale
  - `pattern` — recurring patterns, anti-patterns, or conventions
  - `context` — project context, relationships between components
  - `preference` — team or user preferences for how things should be done
  - `bug` — bug patterns, root causes, and fixes

### Before Compaction / Context Limit
- When context is running low or before compaction:
  1. Identify any unpromoted learnings from this session
  2. Promote each important fact using `engram_promote_fact`
  3. Save your session using `engram_save_session` with a complete summary

### Session End
- Before stopping, always call `engram_save_session` with:
  - Your agent name
  - A summary of what happened
  - Key decisions made
  - Tasks completed and pending
  - Facts you promoted during the session
  - Files you modified
- The quality gate hook will block your stop if it detects incomplete work.

### Ingestion
- When the user shares documentation, URLs, PDFs, or video content that should be permanently remembered, use `engram_ingest` to store it in the knowledge vault.
- For video content, ask about the speaker name and preferred Whisper model.

### Guard Awareness
- If a command is blocked by the pretool guard, do NOT retry it or try to circumvent it.
- Use `engram_guard_status` to understand what rules are active and why something was blocked.
- If you believe a block is incorrect, explain to the user and let them decide.

### Knowledge Vault
- Use `engram_vault_status` periodically to check vault health.
- After intensive ingestion sessions, run `engram_graph_index` to update the knowledge graph.
- Use `engram_brain_resolve` when you find conflicting information in the vault.
