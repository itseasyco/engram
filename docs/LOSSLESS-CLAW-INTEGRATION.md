# Lossless-Claw Integration Guide

Comprehensive guide for integrating the lossless-claw (LCM) SQLite backend with OpenClaw LACP Fusion.

---

## What is lossless-claw?

Lossless-claw is the native LCM (Lossless Context Machine) storage engine. It uses a local SQLite database (`lcm.db`) to store session summaries, context windows, and agent interactions in a structured, queryable format.

Unlike the default file-based backend (which reads from Obsidian vault markdown files), lossless-claw provides:

- **Structured storage** -- session summaries live in a SQLite database with indexed columns for fast lookup.
- **DAG traversal** -- summaries form a directed acyclic graph via `parent_id` chains, enabling ancestry queries and context lineage tracking.
- **Auto-discovery** -- the `discover` command can scan the LCM database for new summaries without manual file management.
- **Batch queries** -- configurable batch sizes (`lcmQueryBatchSize`) for efficient bulk operations.

The database is stored at `~/.openclaw/lcm.db` by default and contains a `summaries` table with columns for `summary_id`, `content`, `project`, `parent_id`, `timestamp`, and metadata.

---

## How to Enable

### 1. Set `contextEngine` in your openclaw.json

Add the plugin configuration to your OpenClaw gateway config at `~/.openclaw/openclaw.json`:

```json
{
  "openclaw-lacp-fusion": {
    "enabled": true,
    "config": {
      "contextEngine": "lossless-claw",
      "lcmQueryBatchSize": 50,
      "promotionThreshold": 70,
      "autoDiscoveryInterval": "6h"
    }
  }
}
```

An example config file is available at:

```
plugin/config/example-openclaw-lacp.lossless-claw.json
```

### 2. Verify the LCM database exists

The LCM database must be present at `~/.openclaw/lcm.db`. If you have been running LCM sessions, this file should already exist. You can verify:

```bash
ls -la ~/.openclaw/lcm.db
sqlite3 ~/.openclaw/lcm.db ".tables"
```

You should see a `summaries` table (among others).

---

## Auto-Discovery Usage

Both `openclaw-lacp-promote` and `openclaw-lacp-context` support a `discover` subcommand that scans the LCM database for summaries.

### Discovering summaries for promotion

```bash
openclaw-lacp-promote discover --project easy-api --since 2026-03-01 --limit 20
```

This queries the LCM database for recent summaries matching the project filter, then outputs them as JSON for review or piping into the promotion pipeline.

### Discovering context for injection

```bash
openclaw-lacp-context discover --topic "settlement" --project easy-api --limit 10
```

This searches the LCM database for summaries relevant to the given topic, suitable for injecting into a new session's context window.

### Overriding the backend at runtime

If your config uses the file-based backend by default, you can override per-invocation:

```bash
openclaw-lacp-promote discover --backend lossless-claw --project easy-api
openclaw-lacp-context discover --backend lossless-claw --topic "treasury"
```

---

## Context Injection Workflow with LCM Backend

When the lossless-claw backend is active, the context injection flow works as follows:

1. **Session starts** -- the `session-start` hook fires.
2. **Context discovery** -- `openclaw-lacp-context auto-inject` queries the LCM database for summaries related to the current project and task.
3. **DAG traversal** -- the backend follows `parent_id` chains to gather ancestral context (not just the latest summary, but the lineage that led to it).
4. **Fact scoring** -- gathered facts are scored by relevance to the current topic.
5. **Injection** -- the top-N facts (controlled by `--max-facts`) are injected into the session's context window.
6. **Metadata logging** -- the injection event is recorded in `context.json` and `injections.jsonl`.

```
Session Start
    |
    v
LCM Database Query (summaries table)
    |
    v
DAG Traversal (follow parent_id chains)
    |
    v
Score & Rank Facts
    |
    v
Inject top-N into context window
    |
    v
Log injection metadata
```

---

## DAG Traversal (parent_id Chains)

Summaries in the LCM database are linked via `parent_id` references, forming a directed acyclic graph:

```
sum_001 (root session)
  |
  +-- sum_002 (follow-up session)
  |     |
  |     +-- sum_005 (deeper follow-up)
  |
  +-- sum_003 (parallel branch)
        |
        +-- sum_006
```

When the backend resolves context for a topic, it does not just return the single best-matching summary. It traverses the `parent_id` chain upward to gather the full lineage, giving the agent a richer understanding of how a decision evolved over multiple sessions.

The traversal depth is controlled by the `--depth` flag on `openclaw-lacp-context inject` (default: 2 levels).

### Example query pattern

```sql
-- Find a summary and its ancestors
WITH RECURSIVE ancestors AS (
  SELECT * FROM summaries WHERE summary_id = ?
  UNION ALL
  SELECT s.* FROM summaries s
  JOIN ancestors a ON s.summary_id = a.parent_id
)
SELECT * FROM ancestors ORDER BY timestamp ASC;
```

---

## Migration from File-Based to LCM

Switching from the file-based backend to lossless-claw requires a single config change. No data migration is needed because the two backends read from different sources.

### Before (file-based)

```json
{
  "openclaw-lacp-fusion": {
    "enabled": true,
    "config": {
      "contextEngine": null,
      "promotionThreshold": 70
    }
  }
}
```

### After (lossless-claw)

```json
{
  "openclaw-lacp-fusion": {
    "enabled": true,
    "config": {
      "contextEngine": "lossless-claw",
      "lcmQueryBatchSize": 50,
      "promotionThreshold": 70,
      "autoDiscoveryInterval": "6h"
    }
  }
}
```

The file-based backend continues to work for `inject`, `query`, and `list` commands (reading from `MEMORY_ROOT` and `VAULT_ROOT`). The `discover` subcommand is only available with the lossless-claw backend.

You can run both backends side by side during a transition period by using `--backend` to override per command.

---

## Troubleshooting

### Missing LCM database

**Symptom:** `LCM database not found at ~/.openclaw/lcm.db`

**Fix:** Ensure the LCM engine has been initialized and has run at least one session. The database is created automatically by LCM on first use. If you installed LCM in a non-standard location, check that the path is correct.

### Wrong database path

**Symptom:** `discover` returns no results even though you have sessions.

**Fix:** The backend looks for `~/.openclaw/lcm.db` by default. If your database is elsewhere, you may need to symlink it or configure the `lcmDbPath` in the backend initialization. Check:

```bash
find ~ -name "lcm.db" -maxdepth 4 2>/dev/null
```

### No summaries table

**Symptom:** SQLite error about missing table.

**Fix:** The database exists but was not initialized by LCM. Verify:

```bash
sqlite3 ~/.openclaw/lcm.db ".schema summaries"
```

If the table does not exist, the database may be from a different application. Ensure you are pointing at the correct LCM database.

### contextEngine not recognized

**Symptom:** `discover requires the lossless-claw backend`

**Fix:** The config is not being read, or `contextEngine` is set to `null`. Verify your `~/.openclaw/openclaw.json` has the correct structure:

```bash
cat ~/.openclaw/openclaw.json | jq '.plugins.entries["openclaw-lacp-fusion"].config.contextEngine'
```

Should output `"lossless-claw"`. If using the flat plugin config format, check:

```bash
cat ~/.openclaw/openclaw.json | jq '.["openclaw-lacp-fusion"].config.contextEngine'
```

### Auto-discovery returns stale results

**Symptom:** `discover` keeps returning old summaries.

**Fix:** Use the `--since` flag to filter by date:

```bash
openclaw-lacp-promote discover --project easy-api --since 2026-03-18
```

The `autoDiscoveryInterval` config key controls how often automatic discovery runs (valid values: `1h`, `2h`, `4h`, `6h`, `8h`, `12h`, `24h`). Adjust if needed.
