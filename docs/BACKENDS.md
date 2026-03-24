# Context Backends

OpenClaw LACP Fusion v2.2.0 supports two context backends: **LCMBackend** (lossless-claw) and **FileBackend** (file-based). The active backend is selected via the `contextEngine` config key.

---

## Architecture

```
                    +---------------------------+
                    |    CLI Commands            |
                    |  openclaw-lacp-promote     |
                    |  openclaw-lacp-context     |
                    +------------+--------------+
                                 |
                                 v
                    +---------------------------+
                    |   get_backend(config)      |
                    |   (Factory Function)       |
                    +------+----------+---------+
                           |          |
              contextEngine|          | contextEngine
              = "lossless- |          | = null
                claw"      |          |
                           v          v
              +------------+--+  +---+-----------+
              |  LCMBackend   |  |  FileBackend   |
              |  (SQLite DB)  |  |  (Vault Files) |
              +-------+------+  +-------+--------+
                      |                 |
                      v                 v
              +-------+------+  +-------+--------+
              |  lcm.db      |  |  ~/.openclaw/   |
              |  (SQLite)    |  |  vault/*.md     |
              |              |  |  memory/*.md    |
              +--------------+  +----------------+
```

---

## ContextBackend Abstract Interface

Both backends implement the same abstract interface, ensuring commands work identically regardless of which backend is active.

### Methods

| Method | Description | Returns |
|--------|-------------|---------|
| `discover_summaries(filters)` | Find summaries matching project/date filters | `list[dict]` |
| `find_context(task, project, limit)` | Find context relevant to a task/topic | `list[dict]` |
| `get_summary(summary_id)` | Retrieve a single summary by ID | `dict` or `None` |
| `get_ancestors(summary_id, depth)` | Traverse parent_id chain upward | `list[dict]` |
| `list_projects()` | List all known projects | `list[str]` |

### Filter dictionary

The `filters` parameter for `discover_summaries` accepts:

```python
{
    "project": "easy-api",      # Filter by project name
    "since": "2026-03-01",      # Filter by date (ISO format)
    "limit": 50,                # Max results to return
}
```

---

## LCMBackend

The LCMBackend reads from the LCM SQLite database. This is the recommended backend for production use when LCM is your primary session engine.

### How it works

1. Opens a read-only connection to `~/.openclaw/lcm.db`.
2. Queries the `summaries` table with SQL filters.
3. Traverses `parent_id` chains using recursive CTEs for DAG traversal.
4. Returns structured dictionaries with summary content, metadata, and lineage.

### SQLite queries

**Find summaries by project:**

```sql
SELECT summary_id, content, project, parent_id, timestamp
FROM summaries
WHERE project = ?
ORDER BY timestamp DESC
LIMIT ?;
```

**Find context by topic (keyword search):**

```sql
SELECT summary_id, content, project, parent_id, timestamp
FROM summaries
WHERE content LIKE '%' || ? || '%'
ORDER BY timestamp DESC
LIMIT ?;
```

**DAG traversal (ancestor chain):**

```sql
WITH RECURSIVE ancestors AS (
  SELECT * FROM summaries WHERE summary_id = ?
  UNION ALL
  SELECT s.* FROM summaries s
  JOIN ancestors a ON s.summary_id = a.parent_id
)
SELECT * FROM ancestors ORDER BY timestamp ASC;
```

### Configuration

```json
{
  "contextEngine": "lossless-claw",
  "lcmQueryBatchSize": 50
}
```

The `lcmQueryBatchSize` controls how many rows are fetched per query (range: 1-1000, default: 50).

---

## FileBackend

The FileBackend reads from the LACP vault and memory directories. This is the default backend and requires no LCM database.

### How it works

1. Scans `MEMORY_ROOT` (`~/.openclaw/memory/<project>/`) for markdown and JSON files.
2. Scans `VAULT_ROOT` (`~/.openclaw/vault/<project>/`) for Obsidian vault notes.
3. Parses markdown files to extract facts (bullet points, sentences with fact indicators).
4. Follows Obsidian wikilinks (`[[note-name]]`) for graph traversal.
5. Returns facts as flat lists without parent_id lineage.

### File sources

| Source | Path | Content |
|--------|------|---------|
| `MEMORY.md` | `~/.openclaw/memory/<slug>/MEMORY.md` | Promoted facts with receipts |
| Category files | `~/.openclaw/memory/<slug>/<category>.md` | Facts grouped by category |
| `context.json` | `~/.openclaw/memory/<slug>/context.json` | Last injection metadata |
| `patterns.md` | `~/.openclaw/memory/<slug>/patterns.md` | Reusable patterns |
| Vault notes | `~/.openclaw/vault/<slug>/**/*.md` | Obsidian knowledge graph |

### Configuration

```json
{
  "contextEngine": null
}
```

When `contextEngine` is `null` (or omitted), the file-based backend is used.

### Limitations

- No `discover` command support (no centralized index to scan).
- No parent_id lineage or DAG traversal.
- Relies on file system layout and naming conventions.
- Slower for large vaults (scans all markdown files on each query).

---

## When to Use Which

| Scenario | Recommended Backend |
|----------|-------------------|
| LCM is your primary session engine | `lossless-claw` |
| You want auto-discovery of summaries | `lossless-claw` |
| You need DAG traversal / lineage tracking | `lossless-claw` |
| You use Obsidian as your primary knowledge store | `file` (FileBackend) |
| You don't have an LCM database | `file` (FileBackend) |
| You want zero dependencies beyond the file system | `file` (FileBackend) |
| You are migrating incrementally | Start with `file`, add `lossless-claw` later |

---

## Config-Driven Selection

The backend is selected by the `contextEngine` key in your plugin config:

```json
{
  "openclaw-lacp-fusion": {
    "enabled": true,
    "config": {
      "contextEngine": "lossless-claw"
    }
  }
}
```

Valid values:

- `"lossless-claw"` -- use the LCMBackend (SQLite database)
- `null` -- use the FileBackend (vault/memory files)

---

## Factory Pattern via get_backend()

The backend is instantiated via a factory function that reads the config and returns the appropriate implementation:

```python
def get_backend(config: dict) -> ContextBackend:
    """
    Return the appropriate backend based on config.

    Args:
        config: Plugin config dict with 'contextEngine' key.

    Returns:
        LCMBackend if contextEngine is "lossless-claw",
        FileBackend otherwise.
    """
    engine = config.get("contextEngine")
    if engine == "lossless-claw":
        return LCMBackend(config)
    return FileBackend(config)
```

CLI scripts use this pattern internally. When you pass `--backend lossless-claw` or `--backend file`, the CLI overrides the config value before calling `get_backend()`.

---

## Runtime Override

Both `openclaw-lacp-promote` and `openclaw-lacp-context` accept a `--backend` flag to override the configured backend for a single invocation:

```bash
# Use LCM backend even if config says file-based
openclaw-lacp-promote discover --backend lossless-claw --project easy-api

# Use file backend even if config says lossless-claw
openclaw-lacp-context inject --backend file --project easy-api --topic "checkout"
```

This is useful for testing, debugging, or during a gradual migration between backends.
