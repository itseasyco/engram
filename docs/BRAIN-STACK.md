# Brain Stack — Layer 2: Knowledge Graph

The Knowledge Graph layer provides persistent, searchable knowledge storage via Obsidian vault integration with MCP wiring for programmatic access.

## Architecture

```
Session Memory (Layer 1)
  ↓ auto-sync
Knowledge Graph (Layer 2)  ←→  Obsidian Vault
  ↓                              ↓
QMD Search  ←→  Smart-Connections MCP
```

## Vault Structure

```
~/obsidian/vault/
├── 00_Index.md              # Master index
├── 01_Projects/             # Per-project knowledge
│   └── <slug>/
│       ├── index.md
│       ├── MEMORY.md
│       ├── debugging.md
│       ├── patterns.md
│       ├── architecture.md
│       └── preferences.md
├── 02_Concepts/             # Cross-project concepts
├── 03_People/               # Contact & collaborator notes
├── 04_Systems/              # System/infrastructure docs
└── 05_Inbox/                # Ingestion queue
    └── queue-generated/
        ├── index.md
        └── <ingested-notes>.md
```

## Commands

### Initialize Knowledge Graph

```bash
openclaw-brain-graph init --vault-path ~/obsidian/vault
```

Creates the vault structure with all directories and 00_Index.md.

### Sync Project Memory

```bash
openclaw-brain-graph sync --project ~/repos/easy-api --vault-path ~/obsidian/vault
```

Copies session memory (Layer 1) into the vault under `01_Projects/<slug>/`.

### Find Connections

```bash
openclaw-brain-graph find-connections --query "payment processing" --max-depth 3
```

Traverses `[[wiki-links]]` to find related notes.

### Index Vault

```bash
openclaw-brain-graph index --project ~/repos/easy-api --update-qmd
```

Rebuilds vault index and optionally updates QMD embeddings.

### Query

```bash
openclaw-brain-graph query --project ~/repos/easy-api --search-term "auth middleware"
```

Searches vault content using keyword matching.

### Status

```bash
openclaw-brain-graph status --project ~/repos/easy-api --details
```

Shows vault statistics: note count, link count, orphans.

## MCP Integration

The knowledge graph wires into four MCP servers:

| Server | Purpose |
|--------|---------|
| `memory` | Persistent graph memory |
| `smart-connections` | Semantic search over vault |
| `qmd` | BM25 + embedding search |
| `obsidian` | Direct vault read/write |

### Configuration

Set in `.openclaw-lacp.env`:

```bash
LACP_OBSIDIAN_VAULT=~/obsidian/vault
KG_AUTO_SYNC=true
KG_EMBED_BACKEND=openai
KG_SEMANTIC_SEARCH_ENABLED=true
```

## Bidirectional Linking

Notes use `[[wiki-link]]` syntax for connections:

```markdown
# Payment Gateway

Related: [[Finix Integration]], [[Brale Settlement]]

This module handles...
```

The audit command (`openclaw-obsidian audit`) detects orphan notes and broken links.

## Integration with Other Layers

- **Layer 1 → Layer 2**: Session memory auto-syncs to vault on init
- **Layer 3 → Layer 2**: Ingested content lands in `05_Inbox/queue-generated/`
- **Layer 4 → Layer 2**: Code intelligence results can be indexed into vault
- **Layer 5 → Layer 2**: Provenance receipts can be exported to vault

## Vault Management

Use `openclaw-obsidian` for vault operations:

```bash
openclaw-obsidian status              # Vault statistics
openclaw-obsidian audit               # Check integrity
openclaw-obsidian apply --project .   # Sync memory to vault
openclaw-obsidian backup              # Create archive
openclaw-obsidian restore --from X    # Restore from backup
openclaw-obsidian optimize            # Cleanup & compact
```

## Troubleshooting

**Vault not found**: Set `LACP_OBSIDIAN_VAULT` or pass `--vault-path`.

**QMD not available**: Install QMD for semantic search. The graph works without it but search is keyword-only.

**Orphan notes**: Run `openclaw-obsidian audit` to find notes with no backlinks, then add `[[links]]` or delete orphans.
