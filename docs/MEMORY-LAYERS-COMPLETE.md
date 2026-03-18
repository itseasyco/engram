# OpenClaw LACP Fusion: Complete 5-Layer Memory Architecture

## Overview

The OpenClaw LACP Fusion plugin implements a complete 5-layer memory system for agent knowledge continuity, knowledge graph management, content ingestion, code intelligence, and tamper-proof audit trails.

**Status:** Phases 1-4 complete (149 tests passing), Phase 5 layers fully implemented.

## Architecture

```
┌────────────────────────────────────────────────────────────────┐
│ Layer 5: Agent Identity & Provenance (openclaw-agent-id,      │
│          openclaw-provenance)                                   │
│ Persistent agent IDs • Hash-chained receipts • Audit trails   │
├────────────────────────────────────────────────────────────────┤
│ Layer 4: Code Intelligence (openclaw-brain-code)              │
│ AST analysis • Symbol indexing • Call graphs • Impact analysis │
├────────────────────────────────────────────────────────────────┤
│ Layer 3: Ingestion Pipeline (openclaw-brain-ingest)           │
│ Transcript/URL/PDF/File → Structured notes • Auto-indexing   │
├────────────────────────────────────────────────────────────────┤
│ Layer 2: Knowledge Graph (openclaw-brain-graph)               │
│ Obsidian vault • Smart-connections MCP • QMD semantic search  │
├────────────────────────────────────────────────────────────────┤
│ Layer 1: Session Memory (ENHANCED)                             │
│ 5 seed files • ~openclaw-memory-init~ • openclaw-memory-append│
└────────────────────────────────────────────────────────────────┘
```

## Layer 1: Enhanced Session Memory

**Status:** ✅ Complete with 5 seed file templates

### 5 Seed Files

Each new session initializes these files:

#### 1. MEMORY.md — Project Knowledge
```markdown
# Project Memory — [project-name]

## Quick Reference
- Codebase path
- Agent identifier
- Channel
- Last updated

## Key Decisions
(Major decisions made in this project)

## Architecture Patterns
(Codebase patterns to remember)

## Preferences
(Agent/human preferences)

## Known Issues
(Gotchas, edge cases, tech debt)

## Recent Sessions
(Summary of recent work)
```

**Use case:** Agent captures learnings, decisions, patterns as they work

#### 2. debugging.md — Troubleshooting Guide
```markdown
# Debugging & Troubleshooting — [project-name]

## Common Issues
- Issue: [Brief Title]
  - Symptoms: ...
  - Root Cause: ...
  - Solution: ...
  - Prevention: ...

## Debugging Techniques
(Project-specific approaches)

## Performance Issues
(Baseline → current → optimization)

## Known Regressions
(ID, version, workaround)
```

**Use case:** Document bugs, workarounds, performance optimization techniques

#### 3. patterns.md — Code Patterns
```markdown
# Architectural & Code Patterns — [project-name]

## Project Patterns
- Naming conventions
- Directory structure
- Design patterns used

## Code Organization
- Module dependencies
- Data flow
- Request/response cycle

## Testing Patterns
(Unit/integration/E2E approaches)

## Error Handling
(Exception types, propagation, recovery)

## Performance Patterns
(Caching, batching, rate limiting, async)

## Security Patterns
(Auth, authorization, input validation)
```

**Use case:** Document recurring patterns so next agent knows the conventions

#### 4. architecture.md — System Design
```markdown
# Architecture Overview — [project-name]

## System Architecture
(High-level diagram + description)

## Core Components
- Component: [Name]
  - Purpose
  - Responsibilities
  - Interfaces
  - Dependencies

## Data Model
(Entity definitions, relationships, validation)

## API Surface
(Endpoints, inputs/outputs, errors)

## External Dependencies
(Libraries, versions, critical path)

## Scalability
(Bottlenecks, scaling strategy, limits)

## Deployment Architecture
(Environments, infrastructure, monitoring)
```

**Use case:** Understand system design without reading code

#### 5. preferences.md — Team Conventions
```markdown
# Agent & Project Preferences — [project-name]

## Agent Preferences for This Project
- Work style
- Documentation style
- Testing approach
- Code review focus

## Project-Specific Conventions
- Naming & paths
- Development workflow
- Configuration
- Tools & access

## Team Preferences
- Collaboration process
- Quality standards
- Time & schedule
```

**Use case:** Onboard new agents, establish team norms

### Usage

```bash
# Create session with all 5 seed files
openclaw-memory-init ~/my-project agent-a discord

# Session directory structure
~/.openclaw-test/data/project-sessions/my-project/agent-a/1234567890/
├── MEMORY.md              ← Key decisions, learnings
├── debugging.md           ← Common issues & solutions
├── patterns.md            ← Code patterns, conventions
├── architecture.md        ← System design
├── preferences.md         ← Team & agent preferences
├── context.json           ← Execution metadata
└── .git/                  ← Session git history

# Record execution results (works with all 5 files)
openclaw-memory-append ~/.openclaw-test/data/project-sessions/my-project/agent-a/1234567890 \
  --cost 2.50 \
  --exit-code 0 \
  --learning "Discovered new API pattern"
```

---

## Layer 2: Knowledge Graph

**Status:** ✅ Complete — `openclaw-brain-graph`

### Overview

Semantic knowledge graph for projects using Obsidian vault + QMD + smart-connections MCP.

### Directory Structure

```
my-project/.obsidian-vault/          (Obsidian vault)
├── inbox/                             (Incoming notes)
│   ├── agent-a-MEMORY.md
│   ├── agent-a-debugging.md
│   └── ...
├── inbox/queue-generated/             (Auto-ingested content)
│   ├── transcript_20260318...md
│   ├── url_20260318...md
│   └── index.md                       (Index of all ingested content)
├── projects/                          (Project-specific knowledge)
├── agents/                            (Agent learnings)
├── patterns/                          (Code patterns)
├── decisions/                         (ADRs, architectural decisions)
├── references/                        (External links, docs)
├── README.md                          (Vault overview)
├── .obsidian/                         (Obsidian config)
│   └── vault.json
└── .git/                              (Vault git history)
```

### Commands

```bash
# Initialize knowledge graph for a project
openclaw-brain-graph init ~/my-project --vault ~/my-vault

# Index session memory into graph
openclaw-brain-graph index ~/.openclaw-test/data/project-sessions/my-project/agent-a/1234567890 --update-qmd

# Search the graph semantically
openclaw-brain-graph query ~/.openclaw-test/data/project-sessions/my-project/agent-a/1234567890 "rate limiting issues"

# Generate MCP configuration
openclaw-brain-graph mcp-config ~/my-vault --output ~/.openclaw-test/config/mcp/obsidian.json

# Check graph status
openclaw-brain-graph status ~/my-vault --details
```

### MCP Integration

Generated MCP config includes:
- **obsidian:** Access Obsidian vault via MCP
- **smart-connections:** Semantic search via MCP
- **memory:** MCP memory server for context
- **qmd:** QMD search via MCP

```json
{
  "mcpServers": {
    "obsidian": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-obsidian", "<vault_path>"]
    },
    "smart-connections": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-smart-connections", "<vault_path>"]
    },
    "qmd": {
      "command": "bash",
      "args": ["-c", "qmd mcp --collection <project_slug>"]
    }
  }
}
```

### Workflow

```bash
# 1. Initialize graph for project
openclaw-brain-graph init ~/easy-api --vault /Volumes/Cortex/easy-api-vault

# 2. Agent works in session
openclaw-memory-init ~/easy-api agent-a discord
# ... agent edits MEMORY.md, debugging.md, etc.

# 3. Index session into graph
openclaw-brain-graph index ~/.openclaw-test/data/project-sessions/easy-api/agent-a/1234567890 --update-qmd

# 4. Search the graph
openclaw-brain-graph query ~/.openclaw-test/data/project-sessions/easy-api/agent-a/1234567890 "rate limiting performance"
# Result: [Relevant notes from vault]

# 5. Agent B in next session searches same graph
# Result: Finds Agent A's learnings
```

---

## Layer 3: Ingestion Pipeline

**Status:** ✅ Complete — `openclaw-brain-ingest`

### Overview

Converts external sources (transcripts, URLs, PDFs, files) into structured, indexed notes.

### Input Types

#### Transcript Ingestion
```bash
openclaw-brain-ingest transcript <vault-path> <transcript-file> \
  --speaker "John Doe" \
  --date "2026-03-18"

# Outputs: inbox/queue-generated/transcript_20260318...md
# With sections:
# - Metadata (speaker, date, source)
# - Content (full transcript)
# - Notes (empty, ready for agent input)
```

#### URL Ingestion
```bash
openclaw-brain-ingest url <vault-path> "https://example.com/article" \
  --title "Custom Title" \
  --tags "performance,optimization"

# Outputs: inbox/queue-generated/url_20260318...md
# With sections:
# - Metadata (URL, tags, ingestion time)
# - Content (fetched from URL)
# - Key Takeaways (empty, for agent)
# - Related (cross-references)
```

#### PDF Ingestion
```bash
openclaw-brain-ingest pdf <vault-path> ~/research.pdf \
  --title "Research Paper Summary"

# Outputs: inbox/queue-generated/pdf_20260318...md
# With sections:
# - Metadata (filename, source)
# - Content (extracted text)
# - Summary (for agent)
# - Key Sections (for agent)
# - Takeaways (for agent)
```

#### File Ingestion
```bash
openclaw-brain-ingest file <vault-path> ~/meeting-notes.md \
  --title "Q1 Planning Meeting"

# Outputs: inbox/queue-generated/file_20260318...md
# With sections:
# - Metadata (filename, type)
# - Content (file contents)
# - Analysis (for agent)
# - References (for agent)
```

### Indexing

```bash
# Rebuild inbox index and update QMD embeddings
openclaw-brain-ingest index <vault-path> --qmd

# Creates/updates: inbox/queue-generated/index.md
# Runs: qmd update && qmd embed
# Result: All notes become searchable
```

### Output Structure

```
inbox/queue-generated/
├── index.md                           (Auto-generated index)
├── transcript_20260318_104500_a1b2.md (Session transcript)
├── url_20260318_104501_c3d4.md        (Fetched article)
├── pdf_20260318_104502_e5f6.md        (Extracted PDF)
└── file_20260318_104503_g7h8.md       (Imported file)
```

### Workflow

```bash
# 1. Initialize vault with graph
openclaw-brain-graph init ~/my-project --vault ~/my-vault

# 2. Ingest various sources
openclaw-brain-ingest transcript ~/my-vault/inbox ~/call-transcript.txt --speaker "CEO" --date "2026-03-18"
openclaw-brain-ingest url ~/my-vault/inbox "https://arxiv.org/abs/2401.00000" --tags "ml,research"
openclaw-brain-ingest pdf ~/my-vault/inbox ~/whitepaper.pdf --title "Consensus Layer Design"

# 3. Index all ingested content
openclaw-brain-ingest index ~/my-vault --qmd

# 4. Now all sources are searchable
qmd search "consensus mechanism" -c my-project
# Result: [Notes from transcript, URL, PDF]
```

---

## Layer 4: Code Intelligence

**Status:** ✅ Complete — `openclaw-brain-code`

### Overview

AST-level analysis of codebases: symbol extraction, call graphs, impact analysis.

### Commands

```bash
# Analyze entire codebase
openclaw-brain-code analyze ~/my-project \
  --output analysis.json \
  --gitnexus  # Optional: include GitNexus analysis

# List all symbols
openclaw-brain-code symbols ~/my-project --pattern ".*Handler"

# Get call chain for a function
openclaw-brain-code calls ~/my-project "process_payment" --depth 3

# Impact analysis: what's affected by changing a file
openclaw-brain-code impact ~/my-project "src/payments/processor.py" --scope

# Export full analysis
openclaw-brain-code export ~/my-project analysis.json
```

### Output Examples

#### Symbol List
```json
[
  {
    "name": "PaymentProcessor",
    "occurrences": [
      {
        "type": "class",
        "file": "src/payments/processor.py",
        "lineno": 42,
        "methods": ["process", "validate", "settle"]
      }
    ],
    "count": 1
  }
]
```

#### Call Chain
```json
{
  "symbol": "process_payment",
  "callers": ["handle_webhook", "process_batch"],
  "callees": ["validate_amount", "settle_transaction", "log_audit"],
  "call_graph_depth": 3
}
```

#### Impact Analysis
```json
{
  "file": "src/payments/processor.py",
  "symbols_in_file": ["PaymentProcessor", "validate_amount", "settle_transaction"],
  "dependent_files": ["src/webhooks/stripe.py", "src/api/payments.py"],
  "affected_symbols": ["PaymentProcessor", "handle_webhook", "API.POST /payments"],
  "impact_radius": {
    "files": 2,
    "symbols": 3
  }
}
```

### GitNexus Integration (Optional)

```bash
# If GitNexus is installed (npm install -g gitnexus)
openclaw-brain-code analyze ~/my-project --gitnexus

# Includes advanced metrics:
# - Symbol clustering
# - Execution flow analysis
# - Architectural layering
# - Critical path identification
```

### Workflow

```bash
# 1. Analyze codebase
openclaw-brain-code analyze ~/easy-api --output analysis.json

# 2. Find affected code before making changes
openclaw-brain-code impact ~/easy-api "src/auth/token.py" --scope

# 3. Understand call chains
openclaw-brain-code calls ~/easy-api "validate_token" --depth 3

# 4. Document in architecture.md
# Result: Patterns layer in knowledge graph

# 5. Next agent can search graph for code patterns
qmd search "token validation" -c easy-api
```

---

## Layer 5: Agent Identity & Provenance

**Status:** ✅ Complete — `openclaw-agent-id`, `openclaw-provenance`

### Overview

Persistent agent identities and hash-chained session receipts for tamper-proof audit trails.

### Agent Identity

```bash
# Register agent for a project
openclaw-agent-id register easy-api --agent-name "Agent A"
# Output: easy-api-mac-mini-a1b2c3d4-260318

# Get current agent identity
openclaw-agent-id get easy-api --create  # Creates if missing

# List all agents
openclaw-agent-id list --project easy-api

# Revoke agent
openclaw-agent-id revoke easy-api-mac-mini-a1b2c3d4-260318
```

### Identity File

```json
{
  "agent_id": "easy-api-mac-mini-a1b2c3d4-260318",
  "project_slug": "easy-api",
  "agent_name": "Agent A",
  "hostname": "mac-mini",
  "machine_id": "a1b2c3d4e5f6g7h8",
  "registered_at": "2026-03-18T09:55:00Z",
  "public_key_fingerprint": "sha256:...",
  "status": "active",
  "sessions": []
}
```

Stored at: `~/.openclaw-test/identity/agents/<agent-id>.json` (chmod 0o600)

### Provenance Receipts

```bash
# Create receipt for a session (hash-chained)
openclaw-provenance receipt ~/.openclaw-test/data/project-sessions/easy-api/agent-a/1234567890 \
  agent-a \
  --prev-hash <previous-receipt-hash> \
  --output receipt.json

# Get full provenance chain
openclaw-provenance chain easy-api --verify --output chain.json

# Verify a receipt
openclaw-provenance verify receipt.json --strict

# Export audit trail
openclaw-provenance export easy-api audit-trail.json
```

### Receipt Structure

```json
{
  "receipt_version": "1.0",
  "timestamp": "2026-03-18T09:55:30Z",
  "agent_id": "easy-api-mac-mini-a1b2c3d4-260318",
  "session_id": "1234567890",
  "project_slug": "easy-api",
  "content_hash": "sha256:...",         ← Hash of all session files
  "previous_hash": "sha256:...",        ← Previous receipt (or 'genesis')
  "receipt_hash": "sha256:...",         ← This receipt's hash
  "chain_hash": "sha256:...",           ← Links to previous
  "metadata": {
    "cost_usd": 2.50,
    "exit_code": 0,
    "gate_decisions": ["PR review: approved"],
    "learnings": ["Fixed memory cleanup"]
  }
}
```

### Tamper Detection

**Receipt tampering detected by:**
- `content_hash` mismatch → Session files were modified
- `receipt_hash` mismatch → Receipt was modified
- `chain_hash` mismatch → Broken link in chain
- Missing `previous_hash` → Broken chain (strict mode)

**Example:**
```bash
# After modifying a session file
openclaw-provenance verify receipt.json --strict
# Output: ✗ Receipt verification failed: Receipt hash mismatch (tampering detected)
```

### Workflow

```bash
# 1. Agent starts session
AGENT_ID=$(openclaw-agent-id get easy-api --create)
openclaw-memory-init ~/easy-api $AGENT_ID discord

# 2. Agent works...
# ... edits MEMORY.md, debugging.md, etc.

# 3. Record execution with receipt
PREV_HASH=$(openclaw-provenance chain easy-api | jq -r '.[-1].receipt_hash')
openclaw-provenance receipt ~/.openclaw-test/data/project-sessions/easy-api/$AGENT_ID/1234567890 \
  $AGENT_ID \
  --prev-hash $PREV_HASH \
  --output receipt.json

# 4. Store receipt
mkdir -p ~/.openclaw-test/provenance/easy-api
cp receipt.json ~/.openclaw-test/provenance/easy-api/$(jq -r '.receipt_hash | .[0:16]' receipt.json).json

# 5. Verify chain integrity
openclaw-provenance chain easy-api --verify
# Output: Chain status: valid, Receipts: 5, ...

# 6. Export audit trail
openclaw-provenance export easy-api audit-trail.json
```

---

## Integration Across All 5 Layers

### Complete Workflow

```bash
# 1. Initialize session memory (Layer 1)
SESSION_DIR=$(openclaw-memory-init ~/easy-api agent-a discord)

# 2. Initialize knowledge graph (Layer 2)
openclaw-brain-graph init ~/easy-api --vault /Volumes/Cortex/easy-api-vault

# 3. Ingest sources into graph (Layer 3)
openclaw-brain-ingest transcript /Volumes/Cortex/easy-api-vault ~/meeting.txt --speaker "CEO"
openclaw-brain-ingest url /Volumes/Cortex/easy-api-vault "https://arxiv.org/abs/2401.00000" --tags "ml"

# 4. Index session memory into graph (Layer 2)
openclaw-brain-graph index $SESSION_DIR --update-qmd

# 5. Analyze codebase (Layer 4)
openclaw-brain-code analyze ~/easy-api --output analysis.json

# 6. Create provenance receipt (Layer 5)
AGENT_ID=$(openclaw-agent-id get easy-api)
openclaw-provenance receipt $SESSION_DIR $AGENT_ID

# 7. Append execution results (Layer 1)
openclaw-memory-append $SESSION_DIR \
  --cost 2.50 \
  --exit-code 0 \
  --learning "Discovered new API pattern" \
  --gate "PR review: approved"

# Result: Complete knowledge continuity across 5 layers
```

### Data Flow

```
Agent Session
    ↓
Layer 1: Session Memory (5 seed files)
    ↓
Layer 2: Knowledge Graph (Obsidian vault indexing)
    ↓
Layer 3: Ingestion (Transcript/URL/PDF/Files)
    ↓
Layer 4: Code Intelligence (AST analysis)
    ↓
Layer 5: Provenance (Hash-chained receipts)
    ↓
Searchable Knowledge Base + Tamper-Proof Audit Trail
```

---

## Testing

### Test Coverage

- **Layer 1:** 20+ tests (seed files, git tracking, append)
- **Layer 2:** 25+ tests (vault init, indexing, MCP config)
- **Layer 3:** 30+ tests (transcript/URL/PDF/file ingestion, indexing)
- **Layer 4:** 25+ tests (symbol extraction, call graphs, impact analysis)
- **Layer 5:** 35+ tests (agent identity, receipts, chain verification)

**Total:** 135+ new tests + 149 existing tests = 284+ total tests

### Running Tests

```bash
# All tests
pytest plugin/hooks/tests/ -v

# Specific layer
pytest plugin/hooks/tests/test_layer2_knowledge_graph.py -v

# With coverage
pytest plugin/hooks/tests/ --cov=. --cov-report=html
```

---

## Best Practices

### Layer 1: Session Memory
- ✅ Fill out all 5 seed files during session
- ✅ Use consistent markdown formatting
- ✅ Reference other seed files (e.g., "see patterns.md")
- ❌ Don't duplicate information between files
- ❌ Don't store secrets or credentials

### Layer 2: Knowledge Graph
- ✅ Run `openclaw-brain-graph index` after each major session
- ✅ Search graph before starting work ("DRY" principle)
- ✅ Keep vault under version control
- ❌ Don't commit large binary files
- ❌ Don't store API keys in vault

### Layer 3: Ingestion
- ✅ Ingest decision-making transcripts
- ✅ Ingest research URLs and PDFs
- ✅ Tag ingested content for easier search
- ❌ Don't ingest confidential customer data
- ❌ Don't rely on URL content (may change)

### Layer 4: Code Intelligence
- ✅ Analyze codebase before major refactors
- ✅ Use impact analysis to estimate risk
- ✅ Document patterns in architecture.md
- ❌ Don't modify analysis output directly
- ❌ Don't treat analysis as source of truth (verify with code)

### Layer 5: Provenance
- ✅ Create receipts at end of sessions
- ✅ Verify chains regularly
- ✅ Export audit trails for compliance
- ❌ Don't modify stored receipts
- ❌ Don't ignore verification failures

---

## Migration & Backward Compatibility

All layers are **backward compatible** with v1.0.0:

- **Layer 1:** Enhanced but doesn't break existing sessions
- **Layer 2:** Optional (can use without Layers 3-5)
- **Layer 3:** Optional ingestion pipeline
- **Layer 4:** Optional code analysis
- **Layer 5:** Optional audit trail (can add to existing projects)

Existing installations continue to work; new features are opt-in.

---

## Future Enhancements (Phase 3.1+)

- Auto-indexing of ingested content in QMD
- Automatic sharing of session summaries to Discord/Slack
- Memory merging from multiple agents on same project
- Memory analytics (cost trends, decision frequency)
- Automatic memory archival and cleanup
- Web UI for browsing project memories
- Integration with Linear/Jira for issue context
- Multi-vault federation (link vaults across projects)
- Template marketplace for seed files

---

## Troubleshooting

### "QMD not found"
```bash
npm install -g @qmd/cli
export PATH="$HOME/.bun/bin:$PATH"
qmd --version
```

### "GitNexus not available"
```bash
npm install -g gitnexus
npx gitnexus analyze
```

### "Provenance chain broken"
```bash
# Verify each receipt
for receipt in ~/.openclaw-test/provenance/my-project/*.json; do
  openclaw-provenance verify "$receipt" --strict
done
```

### "Obsidian vault not found"
```bash
# Reinitialize graph
openclaw-brain-graph init ~/my-project --vault ~/my-vault
```

---

## Summary Table

| Layer | Command | Purpose | Status |
|-------|---------|---------|--------|
| 1 | openclaw-memory-init | Session memory + 5 seed files | ✅ Enhanced |
| 1 | openclaw-memory-append | Record execution results | ✅ Existing |
| 2 | openclaw-brain-graph | Knowledge graph (Obsidian + QMD) | ✅ New |
| 3 | openclaw-brain-ingest | Ingest sources (transcript/URL/PDF/file) | ✅ New |
| 4 | openclaw-brain-code | Code intelligence (AST + impact) | ✅ New |
| 5 | openclaw-agent-id | Persistent agent identities | ✅ New |
| 5 | openclaw-provenance | Hash-chained audit trails | ✅ New |

---

**Total Implementation:** 7 scripts + 5 templates + 135+ tests + comprehensive documentation

**Ready for production deployment.**
