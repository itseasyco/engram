# OpenClaw LACP Fusion

Persistent 5-layer memory, execution safety, and cryptographic provenance for OpenClaw agents.

OpenClaw LACP Fusion is a plugin that brings the [LACP (Local Agent Control Plane)](https://github.com/0xNyk/lacp) architecture into OpenClaw. It gives your agents session memory that persists across conversations, a knowledge graph backed by Obsidian, safety hooks that block dangerous operations, and a tamper-proof provenance chain for every session.

## What You Get

- **Session memory** — Per-project, per-agent memory that survives across sessions (5 structured files + git-tracked changes)
- **Knowledge graph** — Obsidian vault integration for persistent, queryable knowledge
- **Ingestion pipeline** — Convert URLs, transcripts, and files into structured notes automatically
- **Code intelligence** — Optional AST-level code analysis via GitNexus
- **Cryptographic provenance** — SHA-256 hash-chained session history for audit trails
- **Execution safety** — Hooks that block dangerous commands, enforce quality gates, and validate writes
- **Policy routing** — 3-tier risk model (safe/review/critical) with cost ceilings and approval gates

## v2.0.0 — LCM Bidirectional Integration

v2.0.0 adds a bidirectional bridge between LACP persistent memory and LCM session context:

- **Context injection** — Inject relevant LACP facts into new sessions (`openclaw-lacp-context inject`)
- **Promotion scoring** — Auto-score and promote high-value LCM facts to LACP (`openclaw-lacp-promote`)
- **Cross-references** — Bidirectional links between LCM summaries and LACP vault notes
- **Graph enrichment** — Sync promoted facts to Obsidian graph (`openclaw-brain-graph sync --from-lcm`)
- **Multi-agent sharing** — Phase B stubs for cross-agent memory queries (`openclaw-lacp-share`)

See [docs/v2-lcm-integration.md](docs/v2-lcm-integration.md) for the full architecture.

## Quick Start

```bash
# Install
git clone https://github.com/itseasyco/openclaw-lacp-fusion.git
cd openclaw-lacp-fusion
bash INSTALL.sh

# Initialize memory for a project
~/.openclaw/plugins/openclaw-lacp-fusion/bin/openclaw-memory-init \
  --project my-project --agent my-agent --session session-001

# Check what was created
ls ~/.openclaw/data/project-sessions/my-project/my-agent/session-001/
# → MEMORY.md  debugging.md  patterns.md  architecture.md  preferences.md  context.json

# Select a safety profile
echo "balanced" > ~/.openclaw/plugins/openclaw-lacp-fusion/.profile
```

## Core Concepts

### The 5 Memory Layers

| Layer | What It Does | Key Tool |
|---|---|---|
| **1. Session Memory** | Per-project files that persist across agent sessions | `openclaw-memory-init` |
| **2. Knowledge Graph** | Obsidian vault for structured, linked knowledge | `openclaw-brain-graph` |
| **3. Ingestion** | Converts sources (URLs, transcripts, files) into notes | `openclaw-brain-ingest` |
| **4. Code Intelligence** | AST analysis of your codebase (optional) | `openclaw-brain-code` |
| **5. Provenance** | SHA-256 hash chain proving session continuity | `openclaw-provenance` |

### Execution Hooks

Four hooks run automatically during agent sessions:

| Hook | When | What |
|---|---|---|
| **session-start** | Session begins | Injects git context (branch, recent commits, modified files, test command) |
| **pretool-guard** | Before tool use | Blocks dangerous patterns (npm publish, rm -rf, chmod 777, data exfiltration) |
| **stop-quality-gate** | Agent tries to stop | Detects incomplete work, rationalization, uncaught test failures |
| **write-validate** | File write | Validates YAML frontmatter on knowledge base files |

### Safety Profiles

| Profile | Hooks Enabled | Use Case |
|---|---|---|
| `minimal-stop` | stop-quality-gate | Quick dev work, low-risk tasks |
| `balanced` | session-start + stop-quality-gate | General development (recommended) |
| `hardened-exec` | All 4 hooks | Production, high-security operations |

### Policy Routing

Tasks are classified into risk tiers with automatic enforcement:

| Tier | Cost Ceiling | Approval | Example |
|---|---|---|---|
| **safe** | $1.00 | None | Run tests, lint code |
| **review** | $10.00 | TTL-cached approval | Deploy to staging |
| **critical** | $100.00 | Per-run confirmation | Production migration |

## Usage Examples

### Initialize Project Memory

```bash
openclaw-memory-init --project my-app --agent zoe --session dev-001
```

Creates 5 seed files in `~/.openclaw/data/project-sessions/my-app/zoe/dev-001/`:
- `MEMORY.md` — Project-level memory and context
- `debugging.md` — Common issues and solutions
- `patterns.md` — Code patterns and conventions
- `architecture.md` — System design decisions
- `preferences.md` — Team and tooling preferences

### Ingest Knowledge

```bash
# Ingest a URL into your knowledge graph
openclaw-brain-ingest --url "https://docs.example.com/api" --title "API Reference" --apply --json

# Ingest a local file
openclaw-brain-ingest --file ./meeting-notes.md --title "Sprint Planning" --apply --json
```

### Query Knowledge Graph

```bash
# Explore your knowledge graph
openclaw-brain-graph --query "authentication flow" --json

# Expand knowledge connections
openclaw-brain-graph --expand --apply --json
```

### Run Gated Execution

```bash
# Safe task — runs immediately
openclaw-gated-run \
  --task "Run tests" --agent zoe --channel engineering \
  --estimated-cost-usd 0.50 -- npm test

# Review task — checks approval cache
openclaw-gated-run \
  --task "Deploy to staging" --agent zoe --channel engineering \
  --estimated-cost-usd 5.00 -- ./deploy-staging.sh

# Critical task — requires explicit confirmation
openclaw-gated-run \
  --task "Production migration" --agent zoe --channel engineering \
  --estimated-cost-usd 50.00 --confirm-budget -- ./migrate-production.sh
```

### Check Policy Routing

```bash
openclaw-route --agent zoe --channel engineering --task "deploy to production"
# → {"tier": "critical", "cost_ceiling_usd": 100.00, "approval_required": true, ...}
```

### Verify Provenance

```bash
# View provenance chain
openclaw-provenance --project my-app --agent zoe --show

# Verify chain integrity
openclaw-provenance --project my-app --agent zoe --verify
```

### Log Execution Results

```bash
openclaw-memory-append \
  --project my-app --agent zoe --session dev-001 \
  --cost 2.50 --exit-code 0 \
  --learnings "Deployed v2.1.0 — zero downtime migration worked"
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `OPENCLAW_HOME` | `~/.openclaw` | Plugin installation root |
| `OPENCLAW_VAULT_ROOT` | `/Volumes/Cortex` | Obsidian vault root for knowledge graph |
| `OPENCLAW_KNOWLEDGE_ROOT` | `~/.openclaw/knowledge` | Knowledge file directory |
| `OPENCLAW_HOOKS_PROFILE` | `balanced` | Active safety profile |
| `OPENCLAW_SESSION_ID` | (auto-generated) | Session identifier for approval caching |
| `OPENCLAW_WRITE_VALIDATE_PATHS` | (none) | Colon-separated paths for write validation |
| `OPENCLAW_TAXONOMY_PATH` | (none) | Path to taxonomy.json for category validation |
| `QUALITY_GATE_DEBUG` | `false` | Enable quality gate debug logging |
| `QUALITY_GATE_MAX_BLOCKS` | `3` | Circuit breaker — max blocks before allowing stop |

### Data Directories

```
~/.openclaw/
├── plugins/openclaw-lacp-fusion/
│   ├── hooks/handlers/          # Hook implementations
│   ├── hooks/profiles/          # Safety profile configs
│   ├── bin/                     # CLI tools
│   ├── data/approval-cache/     # TTL approval tokens
│   ├── data/project-sessions/   # Per-project memory
│   └── logs/                    # Execution audit logs
└── data/project-sessions/       # Session memory storage
```

## CLI Reference

| Command | Description |
|---|---|
| `openclaw-memory-init` | Initialize per-project session memory (5 seed files + git) |
| `openclaw-memory-append` | Log execution results to session memory |
| `openclaw-brain-ingest` | Ingest URLs, files, or transcripts into knowledge graph |
| `openclaw-brain-graph` | Query and expand knowledge graph |
| `openclaw-brain-code` | Code intelligence and AST analysis |
| `openclaw-brain-stack` | Manage the full memory stack (init, audit, scaffold, status) |
| `openclaw-provenance` | View and verify cryptographic session provenance |
| `openclaw-agent-id` | Manage persistent agent identity |
| `openclaw-route` | Check policy routing for a task |
| `openclaw-gated-run` | Execute a command with policy enforcement |
| `openclaw-verify` | Verify task completion (heuristic, test-based, LLM, or hybrid) |

All commands support `--help` and `--json` output.

For detailed usage, see [docs/COMPLETE-GUIDE.md](./docs/COMPLETE-GUIDE.md).

## Monitoring & Audit

All gated executions are logged to `logs/gated-runs.jsonl`:

```bash
# Watch executions in real-time
tail -f ~/.openclaw/plugins/openclaw-lacp-fusion/logs/gated-runs.jsonl | jq .

# Find blocked executions
grep '"blocked"' ~/.openclaw/plugins/openclaw-lacp-fusion/logs/gated-runs.jsonl | jq .
```

## Troubleshooting

### Obsidian vault not found

Set `OPENCLAW_VAULT_ROOT` to your vault path:

```bash
export OPENCLAW_VAULT_ROOT="$HOME/Documents/MyVault"
```

The knowledge graph features work without Obsidian — they just store notes as markdown files in `OPENCLAW_KNOWLEDGE_ROOT`.

### Memory directory permissions

```bash
# Fix permissions
chmod -R 755 ~/.openclaw/data/project-sessions/
chmod -R 755 ~/.openclaw/plugins/openclaw-lacp-fusion/
```

### Hook not executing

1. Check your active profile: `cat ~/.openclaw/plugins/openclaw-lacp-fusion/.profile`
2. Verify the hook is enabled in that profile (e.g., `minimal-stop` only enables stop-quality-gate)
3. Check handler files exist: `ls ~/.openclaw/plugins/openclaw-lacp-fusion/hooks/handlers/`

### Quality gate keeps blocking

The quality gate has a circuit breaker — after 3 blocks in the same session, it allows stop. If you need to override:

```bash
export QUALITY_GATE_MAX_BLOCKS=1
```

### Tests fail after installation

```bash
# Check prerequisites
python3 --version   # Need 3.9+
bash --version      # Need 5.0+
git --version       # Any version

# Run tests with verbose output
python3 -m pytest ~/.openclaw/plugins/openclaw-lacp-fusion/hooks/tests/ -v --tb=long
```

For more, see [plugin/hooks/TROUBLESHOOTING.md](./plugin/hooks/TROUBLESHOOTING.md).

## Requirements

- **OpenClaw:** 0.23.0+
- **Python:** 3.9+
- **Bash:** 5.0+
- **Git:** Any version

All prerequisites are checked automatically by `INSTALL.sh`.

## Testing

```bash
# Full test suite (122 tests)
python3 -m pytest ~/.openclaw/plugins/openclaw-lacp-fusion/hooks/tests/ -v

# Coverage report
python3 -m pytest tests/ --cov=. --cov-report=html
```

## Documentation

| Document | Description |
|---|---|
| [COMPLETE-GUIDE.md](./docs/COMPLETE-GUIDE.md) | Full user guide with all features |
| [POLICY-GUIDE.md](./docs/POLICY-GUIDE.md) | Policy configuration reference |
| [MEMORY-LAYERS-COMPLETE.md](./docs/MEMORY-LAYERS-COMPLETE.md) | Deep dive on 5 memory layers |
| [ROUTING-REFERENCE.md](./docs/ROUTING-REFERENCE.md) | Routing engine details |
| [DEPLOYMENT-TO-OPENCLAW.md](./docs/DEPLOYMENT-TO-OPENCLAW.md) | Integration steps |
| [FEATURE-PARITY.md](./FEATURE-PARITY.md) | LACP feature parity audit |

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md) for development setup, code style, and PR process.

## License

MIT License — see [LICENSE](./LICENSE).

## Attribution

Based on [LACP](https://github.com/0xNyk/lacp) by [0xNyk](https://github.com/0xNyk). Original architecture and concepts from LACP; adapted and extended for OpenClaw by the Easy Labs + OpenClaw Community team.
