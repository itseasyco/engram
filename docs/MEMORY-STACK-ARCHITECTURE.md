# OpenClaw LACP Memory Stack - Complete 5-Layer Architecture

## Overview

The LACP Memory Stack is a comprehensive, production-grade system for persistent agent memory across sessions. Unlike traditional context windows, the 5-layer memory stack provides:

- **Layer 1: Session Memory** — Per-execution memory scaffolding (MEMORY.md, debugging.md, etc.)
- **Layer 2: Knowledge Graph** — Obsidian vault as persistent graph structure with semantic search
- **Layer 3: Ingestion Pipeline** — Automated content ingestion (transcripts, URLs, files → structured notes)
- **Layer 4: Code Intelligence** — AST-based code context graph with GitNexus (optional)
- **Layer 5: Agent Identity & Provenance** — SHA-256 hash-chained session receipts for audit trails

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    OpenClaw Agent (Session)                     │
└────────────────┬────────────────────────────────────────────────┘
                 │ openclaw-brain-stack (main orchestrator)
                 ├─────────────────────────┬──────────────────────┐
                 │                         │                      │
        ┌────────▼────────┐      ┌────────▼──────────┐   ┌───────▼────────┐
        │  Layer 1: SM    │      │  Layer 2: KG      │   │  Layer 3: IP   │
        │ (Session Mem)   │      │(Knowledge Graph)  │   │(Ingestion Pipe)│
        ├─────────────────┤      ├───────────────────┤   ├────────────────┤
        │ MEMORY.md       │      │ Obsidian Vault    │   │ inbox/queue/   │
        │ debugging.md    │◄────►│ (MCP wired)       │◄─►│ indexed.md     │
        │ patterns.md     │      │ + smart-conns     │   │                │
        │ architecture.md │      │ + qmd semantic    │   │ web_fetch      │
        │ preferences.md  │      │   search          │   │ pdf tools      │
        └────────┬────────┘      └────────┬──────────┘   └───────┬────────┘
                 │                        │                       │
        ┌────────▼────────────────────────▼───────┬────────────────▼────┐
        │  Layer 4: Code Intelligence (Optional)  │  Layer 5: Provenance │
        ├──────────────────────────────────────────┤──────────────────────┤
        │ GitNexus AST graph (--with-gitnexus)     │ SHA-256 Hash Chain   │
        │ - Symbols, call chains                  │ - Session receipts   │
        │ - Execution flows                       │ - Tamper detection   │
        │ - Impact analysis                       │ - Audit trails       │
        │ via: bin/openclaw-brain-code            │ via: openclaw-agent-id│
        └──────────────────────────────────────────┴──────────────────────┘
```

## Layer 1: Session Memory (Enhanced)

### Purpose
Scaffold per-session memory with 5 seed files that evolve throughout the project lifecycle.

### Seed Files

**1. MEMORY.md** — Long-term project memory
```markdown
# Project Memory

## Context
[Project overview, key decisions, stakeholders]

## Architecture
[High-level codebase structure, patterns]

## Active Issues
[Known blockers, TODOs, risks]

## Learnings
[Things that worked, lessons learned]
```

**2. debugging.md** — Debugging patterns and solutions
```markdown
# Debugging Patterns

## Common Issues
[Known error categories with solutions]

## Tools & Workflows
[Debugging commands, profiling techniques]

## Stack-Specific Patterns
[Language/framework-specific gotchas]
```

**3. patterns.md** — Architectural and code patterns
```markdown
# Architecture Patterns

## Design Patterns Used
[Factory, Observer, Command, etc.]

## Anti-Patterns to Avoid
[Known pitfalls]

## Module Organization
[How code is structured]
```

**4. architecture.md** — Codebase architecture
```markdown
# Architecture Overview

## Layers
[Frontend, API, Data, etc.]

## Data Flow
[Request → processing → response]

## Integration Points
[External services, APIs]
```

**5. preferences.md** — Agent/human preferences
```markdown
# Project Preferences

## Agent Preferences
- Coding style: [tabs/spaces, naming conventions]
- Testing strategy: [unit/integration/e2e]
- Documentation style: [markdown, doxygen, etc.]

## Human Preferences
- Communication style: [detailed/concise]
- Review cadence: [after each session/weekly/etc.]
- Escalation triggers: [when to ask for help]
```

### Storage
```
~/.openclaw/projects/<project-slug>/memory/
├── MEMORY.md              (project-wide long-term memory)
├── debugging.md           (debugging patterns & solutions)
├── patterns.md            (architectural patterns)
├── architecture.md        (codebase architecture)
├── preferences.md         (agent/human preferences)
├── .memory-index.json     (metadata: last_updated, word_count, tags)
└── archive/               (previous session snapshots)
    ├── 2026-03-18.md
    ├── 2026-03-17.md
    └── ...
```

### Project Slug Format
```
Path: /Users/alice/repos/my-project
Slug: Users-alice-repos-my-project
(Replace `/` with `-`, remove leading/trailing `-`)
```

### Initialization
```bash
openclaw-brain-stack init \
  --project "/Users/andrew/repos/easy-api" \
  --agent "wren" \
  --with-obsidian
```

Creates:
- All 5 seed files in `~/.openclaw/projects/Users-andrew-repos-easy-api/memory/`
- Auto-populates from README.md, git history, recent commits
- Indexes into Obsidian vault (if `--with-obsidian` flag used)

## Layer 2: Knowledge Graph (Obsidian)

### Purpose
Persistent, semantic knowledge graph with bidirectional linking and full-text + vector search.

### Vault Structure
```
~/obsidian/vault/
├── 00_Index.md                       (vault map)
├── 01_Projects/
│   ├── easy-api/
│   │   ├── README.md                 (project root)
│   │   ├── Architecture.md           (from Layer 1)
│   │   ├── Sessions/
│   │   │   ├── 2026-03-18-session-1.md
│   │   │   └── 2026-03-18-session-2.md
│   │   └── Knowledge/
│   │       ├── [[API Design Patterns]]
│   │       ├── [[Database Schema]]
│   │       └── [[Deployment Checklist]]
│   └── ...
├── 02_Concepts/
│   ├── [[Design Patterns]]
│   ├── [[Testing Strategies]]
│   └── [[Performance Optimization]]
├── 03_People/
│   ├── Andrew (project lead)
│   ├── Niko (co-founder)
│   └── Jessica (team member)
├── 04_Systems/
│   ├── [[Supabase]]
│   ├── [[Stripe API]]
│   └── [[GitHub Actions]]
└── 05_Inbox/
    ├── 2026-03-18-transcripts/
    ├── 2026-03-18-urls/
    └── queue-generated/
        └── index.md
```

### MCP Wiring
```json
{
  "mcpServers": {
    "obsidian": {
      "command": "node ~/.openclaw/mcp/obsidian-mcp.js",
      "args": ["--vault-path", "~/obsidian/vault"]
    },
    "qmd": {
      "command": "qmd",
      "args": ["--vault", "~/obsidian/vault"]
    },
    "memory": {
      "command": "node ~/.openclaw/mcp/memory-graph.js"
    }
  }
}
```

### Auto-Indexing
Every project operation triggers:
```bash
qmd update && qmd embed  # BM25 + semantic indexing
```

Keeps knowledge graph continuously in sync with project memory.

### Querying
```bash
# BM25 keyword search (fast)
qmd search "database migration"

# Semantic search (understanding)
qmd query "how do we handle async errors?"

# Hybrid search with re-ranking
qmd search "testing strategy" --semantic --rerank
```

## Layer 3: Ingestion Pipeline

### Purpose
Automatically convert external content (transcripts, URLs, PDFs, audio) into structured, indexed notes.

### Input Formats
- **Markdown** — Raw markdown documents
- **Transcripts** — Meeting transcripts, call recordings
- **URLs** — Articles, docs, blog posts
- **PDF** — Papers, specs, reports
- **Audio** — Transcribed via Whisper

### Flow
```
Input (URL/PDF/Transcript/Audio)
  ↓
Extract Content (web_fetch, pdf, audio transcription)
  ↓
Structure (LLM-guided chunking + tagging)
  ↓
Output to inbox/queue-generated/
  ↓
Auto-index into Obsidian (qmd update && qmd embed)
  ↓
Link to relevant project memory
```

### Commands

**Ingest Single File/URL:**
```bash
openclaw-brain-ingest \
  --input "https://example.com/article" \
  --type "url" \
  --project "easy-api" \
  --tags "research,payments"
```

**Continuous Ingestion (Polling):**
```bash
openclaw-brain-ingest --watch \
  --input-dir "/Volumes/Cortex/06-inbox" \
  --poll-interval "6h" \
  --auto-link
```

**Output Structure:**
```
inbox/queue-generated/
├── index.md                  (index of all ingested items)
├── 2026-03-18-url-1.md      (single ingested URL)
├── 2026-03-18-pdf-1.md      (PDF extracted + summary)
├── 2026-03-18-transcript-1.md (meeting transcript)
└── metadata/
    ├── 2026-03-18-url-1.json  (metadata: source, tags, links)
    └── ...
```

## Layer 4: Code Intelligence (Optional)

### Purpose
Build an AST-based knowledge graph of codebase structure, dependencies, and execution flows.

### When to Enable
```bash
openclaw-brain-stack init \
  --project "/Users/andrew/repos/easy-api" \
  --with-gitnexus
```

### What It Builds
- **Symbol Index** — All functions, classes, types, exports
- **Call Chains** — Which functions call what
- **Clusters** — Related code grouped by function
- **Execution Flows** — Expected request/response paths

### Storage
```
~/.openclaw/projects/<slug>/code-graph/
├── symbols.json         (all symbols + locations)
├── call-chains.json     (call graph)
├── clusters.json        (logical groupings)
├── execution-flows.json (request paths)
└── impact-analysis.json (change impact maps)
```

### Commands
```bash
# Analyze current codebase
openclaw-brain-code \
  --project "easy-api" \
  --analyze

# Impact analysis (what breaks if we change X?)
openclaw-brain-code \
  --project "easy-api" \
  --impact "src/api/payments.ts"

# Find all usages
openclaw-brain-code \
  --project "easy-api" \
  --find-usages "createPayment()"
```

## Layer 5: Agent Identity & Provenance

### Purpose
Cryptographic proof of execution continuity, preventing tampering or unauthorized modifications.

### Agent Identity

**Per (hostname, project) pair:**
```bash
openclaw-agent-id --show
# Output:
# Agent ID: a7d3e2f9c1b4a6d9...
# Hostname: mac-mini
# Project: /Users/andrew/repos/easy-api
# Created: 2026-03-18 09:30:00 UTC
# Signing Key: (securely stored in keychain)
```

**Commands:**
```bash
# Show current agent identity
openclaw-agent-id show

# List all registered agents
openclaw-agent-id list

# Register new agent (auto-done on first run)
openclaw-agent-id register

# Revoke agent (after machine loss/security event)
openclaw-agent-id revoke <agent-id>

# Refresh/touch session activity
openclaw-agent-id touch
```

### Provenance Chain

**Hash-Chained Session Receipts:**
```json
{
  "session_id": "2026-03-18-001",
  "agent_id": "a7d3e2f9c1b4a6d9...",
  "prev_hash": "abc123def456...",
  "execution": {
    "timestamp": "2026-03-18T10:30:00Z",
    "duration_seconds": 1234,
    "commands_executed": 42,
    "files_modified": 7,
    "cost_usd": 2.50
  },
  "signature": "signature_of(prev_hash + execution)",
  "next_hash": "def456ghi789..."
}
```

**Commands:**
```bash
# Start session (creates receipt with prev_hash)
openclaw-provenance start \
  --agent-id "a7d3e2f9c1b4a6d9..." \
  --project "easy-api"

# End session (signs + seals receipt, advances hash)
openclaw-provenance end \
  --session-id "2026-03-18-001" \
  --exit-code 0 \
  --files-modified 7

# Verify chain integrity
openclaw-provenance verify \
  --project "easy-api" \
  --since "2026-03-01"

# Export audit trail
openclaw-provenance export \
  --project "easy-api" \
  --format "jsonl" \
  --output "audit-trail.jsonl"
```

## Complete CLI Reference

### Brain Stack (Main Orchestrator)

```bash
# Initialize project memory + knowledge graph
openclaw-brain-stack init \
  --project "/Users/andrew/repos/easy-api" \
  --agent "wren" \
  [--with-obsidian] \
  [--with-gitnexus] \
  [--auto-ingest]

# Health check (all 5 layers)
openclaw-brain-stack doctor \
  --project "easy-api" \
  [--verbose]

# Expand memory (re-summarize, deduplicate)
openclaw-brain-stack expand \
  --project "easy-api" \
  --layer "1" \
  [--max-tokens 5000]
```

### Knowledge Graph (Layer 2)

```bash
# Initialize Obsidian vault
openclaw-brain-graph init \
  --vault-path "~/obsidian/vault" \
  [--github-sync]

# Sync project memory into graph
openclaw-brain-graph sync \
  --project "easy-api" \
  --vault-path "~/obsidian/vault"

# Find connections
openclaw-brain-graph find-connections \
  --query "payment processing" \
  [--max-depth 3]
```

### Ingestion Pipeline (Layer 3)

```bash
# Ingest single item
openclaw-brain-ingest \
  --input "URL|/path/to/file" \
  --type "url|markdown|pdf|audio" \
  --project "easy-api" \
  [--tags "tag1,tag2"]

# Watch and ingest directory
openclaw-brain-ingest \
  --watch \
  --input-dir "/Volumes/Cortex/06-inbox" \
  --poll-interval "6h" \
  --auto-link

# Manually trigger poll (for testing)
openclaw-brain-ingest --poll-now
```

### Code Intelligence (Layer 4)

```bash
# Analyze codebase AST
openclaw-brain-code \
  --project "easy-api" \
  --analyze \
  [--output "code-graph.json"]

# Impact analysis
openclaw-brain-code \
  --project "easy-api" \
  --impact "src/api/payments.ts"

# Find all references
openclaw-brain-code \
  --project "easy-api" \
  --find-usages "createPayment"
```

### Agent Identity (Layer 5a)

```bash
# Show current identity
openclaw-agent-id show

# List all agents
openclaw-agent-id list [--project "easy-api"]

# Register new agent
openclaw-agent-id register [--project "easy-api"]

# Revoke agent
openclaw-agent-id revoke <agent-id>

# Touch (refresh activity timestamp)
openclaw-agent-id touch
```

### Provenance (Layer 5b)

```bash
# Start session (creates receipt)
openclaw-provenance start \
  --agent-id "..." \
  --project "easy-api"

# End session (signs + seals)
openclaw-provenance end \
  --session-id "2026-03-18-001" \
  --exit-code 0 \
  --files-modified 7

# Verify chain
openclaw-provenance verify \
  --project "easy-api" \
  [--since "2026-03-01"] \
  [--until "2026-03-31"]

# Export audit trail
openclaw-provenance export \
  --project "easy-api" \
  --format "jsonl|csv|pdf" \
  --output "path/to/file"

# Check tamper status
openclaw-provenance status \
  --project "easy-api"
```

## Configuration

### .openclaw-lacp.env
```bash
# Layer 1: Session Memory
SESSION_MEMORY_ROOT=~/.openclaw/projects
MEMORY_SCAFFOLD_WITH_GIT=true
MEMORY_ARCHIVE_KEEP_DAYS=90

# Layer 2: Knowledge Graph
LACP_OBSIDIAN_VAULT=~/obsidian/vault
LACP_KNOWLEDGE_ROOT=~/.openclaw/data/knowledge
KG_AUTO_SYNC=true
KG_EMBED_BACKEND=openai  # or: local (ollama)

# Layer 3: Ingestion Pipeline
INGEST_WATCH_DIR=/Volumes/Cortex/06-inbox
INGEST_POLL_INTERVAL=6h
INGEST_AUTO_LINK=true
INGEST_CHUNK_SIZE=2000

# Layer 4: Code Intelligence (Optional)
CODE_GRAPH_ENABLED=false
CODE_GRAPH_WITH_GITNEXUS=false
CODE_GRAPH_ROOT=~/.openclaw/projects/<slug>/code-graph

# Layer 5: Provenance
AGENT_ID_STORE=~/.openclaw/agent-ids
PROVENANCE_ROOT=~/.openclaw/provenance
PROVENANCE_SIGNING_KEY_STORE=keychain
PROVENANCE_HASH_ALGORITHM=sha256
```

## Testing

### Unit Tests (pytest)
```bash
pytest plugin/memory/tests/ -v
```

### Integration Tests (bats)
```bash
bats plugin/memory/tests/integration.bats
```

### Layer-Specific Tests
```bash
# Layer 1: Session Memory
pytest plugin/memory/tests/test_layer1_session_memory.py -v

# Layer 2: Knowledge Graph
pytest plugin/memory/tests/test_layer2_knowledge_graph.py -v

# Layer 3: Ingestion
pytest plugin/memory/tests/test_layer3_ingestion.py -v

# Layer 4: Code Intelligence
pytest plugin/memory/tests/test_layer4_code_intelligence.py -v

# Layer 5: Provenance
pytest plugin/memory/tests/test_layer5_provenance.py -v
```

## Example Workflows

### New Project Setup
```bash
# 1. Initialize full memory stack
openclaw-brain-stack init \
  --project "$(pwd)" \
  --agent "wren" \
  --with-obsidian \
  --with-gitnexus

# 2. Create agent identity
openclaw-agent-id register

# 3. Start first provenance session
openclaw-provenance start \
  --agent-id "$(openclaw-agent-id show --json | jq -r .agent_id)" \
  --project "$(pwd)"
```

### Session Memory Usage
```bash
# During session: agent refers to project memory
cat ~/.openclaw/projects/Users-andrew-repos-easy-api/memory/MEMORY.md

# At end of session: update long-term memory
vim ~/.openclaw/projects/Users-andrew-repos-easy-api/memory/MEMORY.md

# Seal session
openclaw-provenance end \
  --session-id "2026-03-18-001" \
  --exit-code $?
```

### Knowledge Graph Queries
```bash
# Find related content
qmd search "payment settlement logic" -c vault

# Get semantic results
qmd query "how do we handle failed transactions?"

# Navigate project structure
qmd get "qmd://projects/easy-api/Architecture.md"
```

### Ingestion with Auto-Link
```bash
# Drop article in inbox
cp ~/Downloads/payments-article.pdf /Volumes/Cortex/06-inbox/

# Poll triggers ingest
openclaw-brain-ingest --poll-now

# Output appears in queue-generated/
cat ~/.openclaw/projects/.../memory/inbox/queue-generated/index.md
```

## Success Metrics

- ✅ All 5 layers functional and tested
- ✅ 200+ new tests (total 322+)
- ✅ Zero breaking changes to v1.0.0
- ✅ End-to-end integration tests
- ✅ Cryptographically verifiable provenance
- ✅ Obsidian vault auto-syncs
- ✅ Code intelligence optional but fully integrated
- ✅ All CLI commands have examples
- ✅ Documentation is 2000+ lines
