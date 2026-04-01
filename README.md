# Engram

**Persistent memory, safety hooks, and code intelligence for AI agents.**

By [Easy Labs](https://itseasy.co) | Inspired by [LACP](https://github.com/0xNyk/lacp) by [@0xNyk](https://github.com/0xNyk)

[![npm](https://img.shields.io/npm/v/@easylabs/engram)](https://www.npmjs.com/package/@easylabs/engram)
![MIT License](https://img.shields.io/badge/license-MIT-blue.svg)
![Node >= 22](https://img.shields.io/badge/node-%3E%3D22-green.svg)
![Python >= 3.9](https://img.shields.io/badge/python-%3E%3D3.9-yellow.svg)

---

## What Is Engram?

Engram gives AI agents memory that persists between sessions, guardrails that block dangerous operations, and a knowledge graph that grows over time. Every session starts with institutional context and ends with an auditable provenance trail.

**10 MCP tools** for in-session use. **~20 CLI commands** for management. Works with Claude Code, OpenClaw, and compatible agent runtimes.

### Core Capabilities

| Area | What It Does |
|------|-------------|
| **Memory** | Per-project session memory, fact promotion, daily capture, semantic search via QMD |
| **Safety** | 16 guard rules, 7 safety profiles, risk-based policy routing, cost ceilings |
| **Knowledge** | Obsidian-backed graph, wikilinks, curator maintenance, vault doctor |
| **Ingestion** | Transcripts, URLs, PDFs, video/audio (ffmpeg + Whisper) |
| **Code Intelligence** | Dead code detection, blast radius, hotspots, architecture analysis via GitNexus |
| **Provenance** | SHA-256 hash-chained receipts for every session |
| **Maintenance** | Workspace cleanup, bloat detection, stray file analysis |

---

## Quick Start

```bash
# Install
npm install -g @easylabs/engram

# Setup
engram wizard       # Interactive setup
engram doctor       # Verify installation

# Uninstall (preserves vault data)
engram uninstall
```

<details>
<summary><strong>Alternative install methods</strong></summary>

```bash
# One-shot (no install)
npx @easylabs/engram

# From source
git clone https://github.com/itseasyco/engram
cd engram && bash INSTALL.sh
```

</details>

### Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Node.js | >= 22 | CLI and wizard |
| Python | >= 3.9 | Hooks and lib modules |
| QMD | required | Semantic search — installed by wizard |
| Obsidian | optional | Knowledge graph vault |
| ffmpeg | optional | Video/audio ingestion |
| GitNexus | optional | Code intelligence |

---

## How Memory Works

Engram implements a 5-layer memory system. Each layer builds on the previous one.

```
                      ┌─────────────────────────┐
                      │   Layer 5: Provenance    │  SHA-256 hash chains
                      ├─────────────────────────┤
                      │  Layer 4: Code Intel     │  AST, call graphs, impact
                      ├─────────────────────────┤
                      │  Layer 3: Ingestion      │  Video, audio, PDFs, URLs
                      ├─────────────────────────┤
                      │  Layer 2: Knowledge      │  Obsidian vault + QMD
                      ├─────────────────────────┤
                      │  Layer 1: Session Memory │  Per-project, daily files
                      └─────────────────────────┘
```

### The Lifecycle

```
Agent works → Session memory accumulates (Layer 1)
                    ↓
           Facts get promoted (scored, categorized, deduplicated)
                    ↓
           Knowledge indexed in vault/graph (Layer 2)
                    ↓
           Session saved to daily structure
                    ↓
           Next session starts → session-start hook injects
           top facts + git context → Agent has institutional memory
```

### Session Auto-Capture

A managed hook fires on `/new` and `/reset` in OpenClaw. It reads the transcript, extracts decisions and facts, writes a per-agent session file, and updates the daily index.

---

## CLI Reference

### System

| Command | Description |
|---|---|
| `engram wizard` | Interactive setup (arrow-key UI) |
| `engram wizard --section <name>` | Run specific section: vault, engine, profile, mode, guard, dependencies |
| `engram status` | System overview |
| `engram doctor` | Full diagnostics across all 5 layers |
| `engram uninstall [--yes]` | Remove Engram (preserves vault data) |

### Memory

| Command | Description |
|---|---|
| `engram memory query <topic>` | Search memory for facts |
| `engram memory promote` | Promote session facts to persistent memory |
| `engram memory status` | Memory system dashboard |

### Guard

| Command | Description |
|---|---|
| `engram guard rules` | List all rules with status |
| `engram guard blocks` | Recent blocks from audit log |
| `engram guard toggle <id>` | Enable/disable a rule |
| `engram guard level <id> <level>` | Set block level (block/warn/log) |
| `engram guard allow "<cmd>"` | Add to allowlist |
| `engram guard deny "<cmd>"` | Remove from allowlist |
| `engram guard config` | Interactive configuration |
| `engram guard defaults --level <level>` | Set global default |
| `engram guard reset` | Factory defaults |

### Vault

| Command | Description |
|---|---|
| `engram vault status` | Vault health and statistics |
| `engram vault audit` | Full audit (broken links, orphans) |
| `engram vault backup` | Backup vault |
| `engram vault restore` | Restore from backup |
| `engram vault optimize` | Apply memory-centric graph physics |
| `engram vault kpi` | Quality KPIs (fact count, staleness, contradictions) |
| `engram vault heal [--dry-run]` | Scan orphans, fix frontmatter, rename hash files |
| `engram vault migrate <path> [--dry-run]` | Structure migration with wikilink preservation |

### Brain

| Command | Description |
|---|---|
| `engram brain expand` | Re-summarize, deduplicate, compress |
| `engram brain expand --consolidate` | Mycelium consolidation pass |
| `engram brain expand --curator-cycle` | Full 8-step curator maintenance |
| `engram brain resolve` | Resolve contradictions in knowledge notes |
| `engram brain code` | AST analysis, symbol lookup, call graphs |
| `engram brain graph` | Initialize, index, and query the knowledge graph |

### Code

| Command | Description |
|---|---|
| `engram code report [--repo <name>]` | Full code health report (strengths, improvements, issues) |
| `engram code dead-code [--repo <name>]` | Find exported functions with no callers |
| `engram code hotspots [--repo <name>]` | Find files with too many functions |
| `engram code blast-radius [--repo <name>]` | Find functions with the most callers |
| `engram code orphans [--repo <name>]` | Find source files nothing imports |
| `engram code architecture [--repo <name>]` | Architecture cluster analysis |

All code commands support `--output <path>` to save the report to a file and `--all` to run across all indexed repos.

### Ingest

| Command | Description |
|---|---|
| `engram ingest transcript <source>` | Ingest a text transcript |
| `engram ingest url <source>` | Ingest a web page |
| `engram ingest pdf <source>` | Ingest a PDF document |
| `engram ingest file <source>` | Ingest a markdown/text file |
| `engram ingest video <source>` | Ingest video (ffmpeg + Whisper) |
| `engram ingest video-batch <dir>` | Batch-process a directory of videos |
| `engram ingest audio <source>` | Ingest audio (ffmpeg + Whisper) |

### Agent

| Command | Description |
|---|---|
| `engram agent create` | Scaffold a new agent workspace from templates |

### Maintenance

| Command | Description |
|---|---|
| `engram tune-up [--dry-run]` | Workspace cleanup: bloat, stray files, old logs |
| `engram tune-up --agent <name>` | Clean a specific agent workspace |
| `engram repo init` | Generate repositories.json from GitNexus registry |

---

## MCP Tools

10 tools exposed via the Model Context Protocol for in-session use by agents.

| Tool | What It Does |
|---|---|
| `engram_memory_query` | Query session memory and facts with semantic search |
| `engram_promote_fact` | Promote an observation to persistent scored fact |
| `engram_ingest` | Ingest transcripts, URLs, PDFs, files, video, audio |
| `engram_guard_status` | Check guard rules, recent blocks, allowlists |
| `engram_vault_status` | Vault health, note counts, index freshness |
| `engram_graph_index` | Trigger knowledge graph re-indexing |
| `engram_brain_resolve` | Resolve contradictions in knowledge notes |
| `engram_memory_kpi` | Memory KPIs: fact count, schema coverage, staleness |
| `engram_vault_optimize` | Apply graph physics defaults (link distance, repel, colors) |
| `engram_save_session` | Save session to daily folder with per-agent files |

---

## Safety Profiles

Seven profiles control which hooks fire and how.

| Profile | What's Enabled | Use Case |
|---|---|---|
| **autonomous** | All hooks — warn only, never block | Unattended operation, daily driver |
| **balanced** | session-start, quality-gate | General development (default) |
| **context-only** | session-start only | Lightest touch — just inject context |
| **guard-rail** | pretool-guard, quality-gate | Safety without context overhead |
| **minimal-stop** | quality-gate only | Low-risk development |
| **hardened-exec** | All hooks — all block | Production deploys, high-stakes work |
| **full-audit** | All hooks — block + verbose logging | Compliance, audit trails |

Set during install or change in `~/.openclaw/extensions/engram/config/.engram.env`.

---

## Guard System

The pretool-guard intercepts commands before execution and checks them against configurable rules.

### How It Works

1. Agent attempts a command (e.g., `npm publish`)
2. Command checked against allowlists first (global + repo-specific)
3. If no allowlist match, checked against enabled rules via regex
4. Block level resolved: repo override > rule-specific > global default
5. Action taken: **block** (reject), **warn** (log + proceed), or **log** (silent)
6. Every match written to `guard-blocks.jsonl` for audit

### Built-in Rules (16)

| Category | Rules |
|---|---|
| **Destructive** | npm/yarn/pnpm/cargo publish, curl pipe to interpreter, chmod 777, git reset --hard, git clean -f, docker --privileged, fork bombs, scp/rsync to /root, data exfiltration |
| **Protected Paths** | .env files, config.toml, secrets/, .claude/settings.json, authorized_keys, .pem/.key files, .gnupg/ |

### Per-Repo Overrides

```json
{
  "repo_overrides": {
    "/path/to/my-repo": {
      "block_level": "warn",
      "rules_override": { "npm-publish": { "enabled": false } },
      "command_allowlist": [
        { "pattern": "docker run --privileged", "reason": "CI builds" }
      ]
    }
  }
}
```

---

## Video & Audio Ingestion

Engram ingests media files via ffmpeg + [insanely-fast-whisper](https://github.com/Vaibhavs10/insanely-fast-whisper).

```bash
engram ingest video ./meeting.mp4 --speaker "Team Standup" --date "2026-03-23"
engram ingest audio ./voice-memo.mp3 --title "Architecture Discussion"
engram ingest video-batch ./recordings/ --date-from-filename --parallel 4
```

| Hardware | ~Time for 1h Audio | Notes |
|---|---|---|
| NVIDIA A100 / 4090 | ~1 min | Best performance |
| NVIDIA T4 / 3060 | ~3-5 min | `--batch-size 12` if OOM |
| Apple Silicon | ~5-10 min | Auto-sets `--device-id mps` |
| CPU only | ~20-40 min | Use `openai-whisper` instead |

<details>
<summary><strong>Whisper installation</strong></summary>

```bash
pipx install insanely-fast-whisper==0.0.15 --force --pip-args="--ignore-requires-python"
```

</details>

---

## Knowledge Graph Structure

The Obsidian vault follows the Engram taxonomy:

```
vault/
  home/           Master index
  memory/         Daily session memory (YYYY-MM-DD/)
  projects/       Per-repo knowledge
  engineering/    Architecture, decisions, active work
  knowledge/      Concepts, learnings
  inbox/          Incoming notes awaiting processing
  reference/      External docs, API references
  people/         Team members, contacts
  archive/        Deprecated content
  _metadata/      Vault config, taxonomy
```

### Curator Maintenance Cycle

The curator runs 8 steps: inbox processing, mycelium consolidation, wikilink weaving, staleness scan, conflict resolution, schema enforcement, index update, and health report.

```bash
engram brain expand --curator-cycle
```

---

## Using with Claude Code

Two hooks can be wired directly into Claude Code via `~/.claude/settings.json`:

```json
{
  "hooks": {
    "session_initialization": [{
      "command": "python3 ~/.openclaw/extensions/engram/plugin/hooks/handlers/session-start.py",
      "timeout": 10000
    }],
    "agent_stop": [{
      "command": "python3 ~/.openclaw/extensions/engram/plugin/hooks/handlers/stop-quality-gate.py",
      "timeout": 5000
    }]
  }
}
```

| Hook | Platform | Status |
|---|---|---|
| `session-start` | Claude Code + OpenClaw | Injects git context + memory |
| `stop-quality-gate` | Claude Code + OpenClaw | Catches premature stops |
| `pretool-guard` | OpenClaw only | Intercepts tool calls |
| `write-validate` | OpenClaw only | Validates file writes |

---

## Configuration

| File | Purpose |
|---|---|
| `~/.openclaw/extensions/engram/config/.engram.env` | Plugin config (set by wizard) |
| `~/.openclaw/extensions/engram/config/guard-rules.json` | Guard rules, allowlists, overrides |

### Key Properties

| Property | Default | Description |
|---|---|---|
| `profile` | `balanced` | Safety profile |
| `obsidianVault` | `~/obsidian/vault` | Path to knowledge vault |
| `codeGraphEnabled` | `false` | AST analysis, call graphs |
| `provenanceEnabled` | `true` | Hash-chained receipts |
| `contextEngine` | `null` | `lossless-claw` for LCM integration |
| `promotionThreshold` | `70` | Minimum score for auto-promotion (0-100) |

---

## Dependencies

| Dependency | Required | What It Enables |
|---|---|---|
| QMD | Yes | Semantic search, memory backend |
| poppler (pdftotext) | Yes | PDF text extraction |
| ffmpeg | No | Video/audio processing |
| insanely-fast-whisper | No | GPU-accelerated transcription |
| GitNexus | No | Code intelligence (AST, call graphs) |
| lossless-claw | No | LCM SQLite context engine |
| obsidian-headless (ob) | No | Multi-machine vault sync |

---

## Troubleshooting

<details>
<summary><strong>"plugin not found"</strong></summary>

Check that `package.json` exists in the plugin directory with `"openclaw": { "extensions": ["./index.ts"] }` and the gateway config has the entry under `plugins.installs`.

</details>

<details>
<summary><strong>"missing register/activate export"</strong></summary>

The `index.ts` must export a default object with a `register(api)` method.

</details>

<details>
<summary><strong>SDK not found</strong></summary>

The installer creates a symlink at `~/.openclaw/extensions/engram/node_modules/openclaw`. If missing:

```bash
ls ~/.openclaw/extensions/*/node_modules/openclaw
ln -s <detected_path> ~/.openclaw/extensions/engram/node_modules/openclaw
```

</details>

<details>
<summary><strong>Hooks not showing in `openclaw hooks list`</strong></summary>

Expected behavior. Engram registers hooks as lifecycle listeners via `api.on()`, not as standalone hooks. Run `engram doctor` to verify.

</details>

**General fix:** `engram doctor` to diagnose, `engram wizard` to reconfigure.

---

## Coming Soon

- **Connected mode** — `engram connect` / `engram disconnect` for shared vaults
- **Connectors** — GitHub, Slack, Email, filesystem, webhooks, cron fetching
- **File watcher** — `engram watch` for auto-ingestion of new files
- **Obsidian-headless sync** — Multi-machine vault sync via `ob` CLI

---

## Contributing

### Repo Structure

```
engram/
  package.json                 @easylabs/engram
  openclaw.plugin.json         Plugin manifest
  INSTALL.sh                   Install script
  bin/
    engram                     Main CLI router (bash)
    wizard.mjs                 Interactive wizard (@clack/prompts)
  plugin/
    index.ts                   Gateway entry point (hook + tool registration)
    bin/                       CLI tools (engram-*)
    config/                    Guard rules, example configs
    hooks/
      handlers/                Python hook scripts
      managed/                 Auto-capture hook
      profiles/                7 safety profile JSONs
    lib/                       Python modules
      mycelium.py              Spreading activation, FSRS memory model
      curator.py               8-step curator maintenance cycle
      vault_doctor.py          Orphan scan, frontmatter fix
      vault_migrate.py         Vault structure migration
      connectors/              GitHub, Slack, Email, filesystem, webhook, cron
    templates/
      agent-template/          Agent workspace scaffolding
```

### Running Tests

```bash
cd plugin && python -m pytest -v               # All tests
cd plugin && python -m pytest hooks/tests/ -v   # Hook tests
cd plugin && python -m pytest lib/tests/ -v     # Lib tests
```

---

## License

MIT
