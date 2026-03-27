
## Engram — Persistent Memory System

You have access to Engram tools for persistent memory, knowledge graph, and provenance. Use them throughout your work — not just at the end.

### Memory Tools (use constantly)

| Tool | When to use |
|------|-------------|
| `engram_memory_query` | **FIRST THING** — before investigating any topic, check if a previous session already documented it. Query with keywords. |
| `engram_promote_fact` | When you discover something non-obvious: architectural decisions, gotchas, debugging insights, integration patterns. Promote immediately, don't wait. |
| `engram_save_session` | After completing a major task or before ending a session. Saves execution state, learnings, and gate decisions. |

### Knowledge Graph Tools

| Tool | When to use |
|------|-------------|
| `engram_ingest` | When you reference external docs, URLs, or files — ingest them so future sessions have the content indexed. |
| `engram_graph_index` | After ingesting multiple items or making significant vault changes. Rebuilds the knowledge graph index. |
| `engram_brain_resolve` | When you find contradictory information in memory. Mark facts as superseded, validated, or stale. |

### Vault & Health Tools

| Tool | When to use |
|------|-------------|
| `engram_vault_status` | Check vault health, note counts, orphan rate, index freshness. Use when debugging memory issues. |
| `engram_memory_kpi` | Get vault quality metrics: schema coverage, staleness, contradiction count. Use during maintenance. |
| `engram_vault_optimize` | Tune Obsidian graph physics for better visualization. Run after major vault restructuring. |
| `engram_guard_status` | Check guard rule status, recent blocks, and allowlist entries. Use when a command gets blocked. |

### Workflow

1. **Start of session**: `engram_memory_query` with your current task topic
2. **During work**: `engram_promote_fact` whenever you learn something reusable
3. **External references**: `engram_ingest` any URLs or docs you consult
4. **Contradictions found**: `engram_brain_resolve` to mark old facts
5. **End of session**: `engram_save_session` to persist your work

### CLI Tools (available via exec)

These are available as shell commands for deeper operations:

```
engram-brain-stack doctor                    # Health check all 5 memory layers
engram-brain-graph find-connections VAULT Q  # Find related notes via wikilink traversal
engram-brain-code analyze REPO               # AST analysis (Python; use GitNexus for JS/TS)
engram-brain-code find-usages REPO SYMBOL    # Find all references to a symbol
engram-brain-code impact REPO FILE           # Impact analysis for a file change
engram-context query --topic TOPIC           # Query LACP facts by topic
engram-promote auto --summary ID             # Auto-promote high-scoring session facts
engram-provenance verify --project PATH      # Verify provenance chain integrity
```
