# Engram

**By [Easy Labs](https://itseasy.co)**

Persistent agent memory, mycelium-powered knowledge graph, safety hooks, code intelligence, provenance tracking, and video/audio ingestion. 10 MCP tools and 15 user-facing CLI commands for Claude Code and compatible agents.

Inspired by [LACP](https://github.com/0xNyk/lacp) by [@0xNyk](https://github.com/0xNyk) — the original local agent context protocol that showed agents could have persistent memory.

[![npm](https://img.shields.io/npm/v/@easylabs/engram)](https://www.npmjs.com/package/@easylabs/engram)

![MIT License](https://img.shields.io/badge/license-MIT-blue.svg)
![OpenClaw >= 0.23.0](https://img.shields.io/badge/openclaw-%3E%3D0.23.0-green.svg)
![Node >= 22](https://img.shields.io/badge/node-%3E%3D22-green.svg)
![Python >= 3.9](https://img.shields.io/badge/python-%3E%3D3.9-yellow.svg)

---

## Overview

Engram brings persistent agent memory into your development workflow. It gives your agents session memory that survives across conversations, a knowledge graph backed by Obsidian, safety hooks that block dangerous operations before they execute, and a hash-chained provenance trail for every session.

The plugin implements a 5-layer memory system: per-project session memory with daily structure, an Obsidian-backed knowledge graph with QMD semantic search, an ingestion pipeline for external content (including video and audio via insanely-fast-whisper), AST-level code intelligence, and cryptographic provenance receipts. These layers work together so that every agent session starts with institutional context and ends with auditable evidence of what happened.

Engram is for teams and individuals who run agents on real codebases and need guardrails (blocking `npm publish`, `git reset --hard`, secrets access), persistent memory (facts that carry between sessions), and a clear audit trail. It is local-first by default -- all data stays on your machine.

**Key capabilities:**

- Execution hooks (session context injection, pretool guard, quality gate, write validation)
- Risk-based policy routing with three tiers (safe / review / critical) and cost ceilings
- Per-project session memory with daily folder structure and per-agent session files
- Session auto-capture hook (fires automatically on `/new` and `/reset`)
- Obsidian-backed knowledge graph with QMD semantic search
- Video and audio ingestion via ffmpeg + insanely-fast-whisper transcription
- Vault doctor: scan orphans, fix frontmatter, add tags, rename hash files
- Vault migration tool for restructuring existing vaults into Engram-compatible layout
- 8-step curator maintenance cycle (inbox processing, consolidation, wikilinks, staleness, conflicts, schema, index, health)
- Code intelligence via AST analysis, call graphs, and impact analysis
- Cryptographic provenance tracking (SHA-256 hash-chained receipts)
- Configurable safety profiles from autonomous to full-audit
- **10 MCP tools** for memory query, fact promotion, ingestion, guard status, vault management, graph indexing, brain resolution, memory KPIs, vault optimization, and session saving
- **15 user-facing CLI commands** organized into memory, guard, vault, brain, and ingest groups
- Node.js interactive wizard with arrow-key navigation (powered by @clack/prompts)

---

## Quick Start

### Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| OpenClaw | >= 0.23.0 | Core runtime |
| Node.js | >= 22 | CLI and wizard |
| Python | >= 3.9 | Hook handlers and lib modules |
| Bash | >= 4.0 | CLI tools are bash/python scripts |
| QMD | required | Semantic search and memory backend — installed by wizard |
| Obsidian | (optional) | Knowledge graph vault (Layer 2) |
| ffmpeg | (optional) | Video/audio ingestion (Layer 3) |
| insanely-fast-whisper | (optional) | GPU-accelerated audio transcription |

### Install

**Global install (recommended):**

```bash
npm install -g @easylabs/engram
```

**One-shot (no install):**

```bash
npx @easylabs/engram
```

**From the repo:**

```bash
git clone https://github.com/itseasyco/engram
cd engram
bash INSTALL.sh
```

### First-time Setup

```bash
engram wizard       # Interactive setup
engram doctor       # Verify installation
```

### Uninstall

```bash
engram uninstall
```

This removes the plugin extension directory, managed hooks, and gateway config entries. Vault data and LACP memory files are preserved. Pass `--yes` to skip confirmation.

---

## MCP Tools (10 tools)

Engram exposes 10 tools via the Model Context Protocol that agents can call directly during sessions.

| Tool | Description |
|---|---|
| `engram_memory_query` | Query session memory and LACP facts with semantic search (uses QMD when available) |
| `engram_promote_fact` | Promote a session observation to persistent scored fact |
| `engram_ingest` | Ingest transcripts, URLs, PDFs, files, video, and audio into the knowledge graph |
| `engram_guard_status` | Check guard rule status, recent blocks, and allowlist entries |
| `engram_vault_status` | Report on Obsidian vault health, note counts, and index freshness |
| `engram_graph_index` | Trigger knowledge graph re-indexing with optional QMD semantic search |
| `engram_brain_resolve` | Resolve a query against contradictions/supersessions in knowledge notes |
| `engram_memory_kpi` | Return memory system KPIs: fact count, schema coverage, staleness, contradictions |
| `engram_vault_optimize` | Apply memory-centric graph physics defaults (link distance, repel, node sizing, color groups) |
| `engram_save_session` | Save session memory to daily folder structure with per-agent session files |

---

## CLI Reference

The `engram` command is the main entry point. Commands are organized into five groups: memory, guard, vault, brain, and ingest.

### Top-level Commands

| Command | Description |
|---|---|
| `engram wizard` | Interactive setup wizard (Node.js UI with arrow-key navigation) |
| `engram wizard --section <name>` | Run a specific wizard section: `vault`, `engine`, `profile`, `mode`, `guard`, `dependencies`, `all` |
| `engram status` | System overview (mode, mutations, vault, tools) |
| `engram doctor` | Full diagnostics across plugin, all 5 layers, MCP, and tests |
| `engram uninstall` | Remove Engram (preserves vault data); pass `--yes` to skip confirmation |
| `engram -v` / `engram --version` | Print version |

### Memory Commands

| Command | Description |
|---|---|
| `engram memory query <topic>` | Search memory for facts matching a topic |
| `engram memory promote` | Promote session facts to persistent memory |
| `engram memory status` | Show memory system status |

### Guard Commands

| Command | Description |
|---|---|
| `engram guard rules` | List all guard rules with their status |
| `engram guard blocks` | View recent blocks from the audit log |
| `engram guard toggle <rule-id>` | Enable or disable a specific rule |
| `engram guard level <rule-id> <level>` | Set block level (block/warn/log) for a rule |
| `engram guard allow "<cmd>"` | Add a command to the global allowlist |
| `engram guard deny "<cmd>"` | Remove a command from all allowlists |
| `engram guard config` | Interactive guard configuration |
| `engram guard defaults --level <level>` | Set global default block level |
| `engram guard reset` | Reset to factory defaults |

### Vault Commands

| Command | Description |
|---|---|
| `engram vault status` | Vault health and statistics |
| `engram vault audit` | Full audit (broken links, orphans) |
| `engram vault backup` | Backup vault |
| `engram vault restore` | Restore vault from backup |
| `engram vault optimize` | Apply memory-centric graph physics defaults |
| `engram vault kpi` | Vault quality KPIs (fact count, schema coverage, staleness, contradictions) |
| `engram vault heal` | Vault doctor: scan orphans, fix frontmatter, add tags, rename hash files |
| `engram vault migrate` | Structure migration with wikilink preservation |

### Brain Commands

| Command | Description |
|---|---|
| `engram brain expand` | Re-summarize, deduplicate, and compress memory layers |
| `engram brain expand --consolidate` | Run mycelium consolidation pass |
| `engram brain expand --curator-cycle` | Run full 8-step curator maintenance cycle |
| `engram brain resolve` | Resolve contradictions/supersessions in knowledge notes |
| `engram brain code` | AST analysis, symbol lookup, call graphs, impact analysis |
| `engram brain graph` | Initialize, index, and query the knowledge graph |

### Ingest Command

| Command | Description |
|---|---|
| `engram ingest <type> <source>` | Ingest content (transcript, url, pdf, file, video, video-batch, audio) |

---

## How the Memory System Works

Engram implements a continuous memory lifecycle across agent sessions.

### The Five Layers

```
Layer 1: Session Memory     ~/.openclaw/projects/<slug>/memory/
Layer 2: Knowledge Graph    ~/obsidian/vault/ (Obsidian + QMD)
Layer 3: Ingestion Pipeline engram ingest (transcripts, URLs, PDFs, video, audio)
Layer 4: Code Intelligence  engram brain code (AST, call graphs, impact)
Layer 5: Provenance         ~/.openclaw/provenance/ (hash-chained receipts)
```

### The Memory Lifecycle

```
  Agent works on a task
       |
       v
  Session memory accumulates (Layer 1)
  Per-project data in ~/.openclaw/projects/<slug>/memory/
       |
       v
  Facts get promoted to persistent memory (engram_promote_fact)
  Scored, categorized, deduplicated
       |
       v
  Knowledge gets indexed in vault/graph (Layer 2)
  Organized into projects / engineering / knowledge / inbox
       |
       v
  Session saved to daily structure (engram_save_session or auto-capture hook)
  vault/memory/YYYY-MM-DD/<agent-id>-<session>.md
       |
       v
  Next session starts
  session-start hook fires (Layer 1 + 2)
  Injects top relevant facts + git context into the agent's system message
       |
       v
  Agent has institutional memory from previous sessions
```

### Session Memory

Every project gets its own memory directory at `~/.openclaw/projects/<slug>/memory/`. The `session-start` hook reads the current git context (branch, recent commits, modified files) and injects it as a system message when a new session begins.

### Session Auto-Capture

Engram includes a managed hook (`engram-session-capture`) that fires automatically when you issue `/new` or `/reset` in OpenClaw. It reads the session transcript, extracts key decisions and facts, writes a per-agent session file to `vault/memory/YYYY-MM-DD/`, and updates the daily index.

### Knowledge Graph

The Obsidian vault is organized into the Engram taxonomy:

```
vault/
  home/           # Master index, vault overview
  memory/         # Daily session memory (YYYY-MM-DD folders)
  projects/       # Per-repo/per-project knowledge
  engineering/    # Architecture, decisions, active work
  knowledge/      # Concepts, learnings, agent knowledge
  inbox/          # Incoming notes awaiting curator processing
  reference/      # External docs, API references
  people/         # Team members, contacts
  archive/        # Archived/deprecated content
  _metadata/      # Vault config, taxonomy
```

### Vault Doctor

The vault doctor scans every note in your vault and fixes what it can:

- Find orphans (notes with zero backlinks)
- Add/fix YAML frontmatter (title, category, tags, dates, status)
- Auto-detect tags from content
- Rename hash-named files to prose-style titles
- Detect category and suggest/execute moves to correct folders

```bash
engram vault heal
engram vault heal --dry-run    # Preview changes without writing
```

### Vault Migration

For existing vaults that need restructuring into the Engram-compatible layout:

```bash
engram vault migrate /path/to/vault --dry-run   # Preview
engram vault migrate /path/to/vault              # Execute
```

### Lossless Context Integration

When `contextEngine` is set to `lossless-claw`, the plugin integrates with the LCM (Lossless Context Manager) backend. LCM's DAG compaction works alongside Engram's fact injection: LCM compresses conversational context while Engram injects curated facts at session start.

---

## Safety Profiles

Seven profiles control which hooks fire and how they behave.

| Profile | Hooks Enabled | Block Behavior | Use Case |
|---|---|---|---|
| **autonomous** | session-start, pretool-guard, stop-quality-gate, write-validate | All hooks warn but never block; agent keeps working | Daily driver, autonomous agents, unattended operation |
| **balanced** | session-start, stop-quality-gate | No guard or write validation | General development, moderate-risk tasks (default) |
| **context-only** | session-start | No safety gates at all | Lightest touch, just inject git context |
| **guard-rail** | pretool-guard, stop-quality-gate | Blocks dangerous commands, catches incomplete work | Safety without context injection overhead |
| **minimal-stop** | stop-quality-gate | Only detects premature agent stops | Low-risk development and testing |
| **hardened-exec** | session-start, pretool-guard, stop-quality-gate, write-validate | All hooks block; violations require explicit approval | Production deploys, high-stakes work |
| **full-audit** | session-start, pretool-guard, stop-quality-gate, write-validate | All hooks block; verbose logging; full provenance | Compliance, audit trails, debugging hook behavior |

Set the profile during install or change it later in `~/.openclaw/extensions/engram/config/.engram.env`.

---

## Guard System

The pretool-guard hook intercepts tool calls before execution and checks them against a configurable set of rules.

### How It Works

1. The agent attempts to run a command (e.g., `npm publish`)
2. `pretool-guard.py` loads `guard-rules.json` (mtime-cached for performance)
3. The command is checked against allowlists first (global + repo-specific) -- if matched, it passes
4. Then checked against all enabled rules via regex patterns
5. For a matched rule, the block level is resolved: repo override > rule-specific > global default
6. Action is taken based on block level:
   - `block` -- command is rejected (exit 1)
   - `warn` -- warning is logged, command proceeds (exit 0)
   - `log` -- silently logged, command proceeds (exit 0)
7. Every match is written to `guard-blocks.jsonl` for audit

### Built-in Rules (16 rules)

| Rule ID | Pattern | Category |
|---|---|---|
| `npm-publish` | npm/yarn/pnpm/cargo publish | destructive |
| `curl-pipe-interpreter` | curl \| python, wget \| node, etc. | destructive |
| `chmod-777` | chmod 777 (overly permissive) | destructive |
| `git-reset-hard` | git reset --hard | destructive |
| `git-clean-force` | git clean -f | destructive |
| `docker-privileged` | docker run --privileged | destructive |
| `fork-bomb` | Fork bomb pattern | destructive |
| `scp-rsync-root` | scp/rsync to /root | destructive |
| `data-exfiltration` | curl --data @.env, @.ssh, etc. | destructive |
| `env-files` | .env file access | protected-path |
| `config-toml` | config.toml access | protected-path |
| `secrets-directory` | secrets/ directory access | protected-path |
| `claude-settings` | .claude/settings.json | protected-path |
| `authorized-keys` | authorized_keys | protected-path |
| `pem-key-files` | .pem, .key files | protected-path |
| `gnupg-directory` | .gnupg/ directory | protected-path |

### Per-Repo Overrides

```json
{
  "repo_overrides": {
    "/path/to/my-repo": {
      "block_level": "warn",
      "rules_override": {
        "npm-publish": { "enabled": false },
        "git-reset-hard": { "block_level": "warn" }
      },
      "command_allowlist": [
        { "pattern": "docker run --privileged", "reason": "Needed for CI builds" }
      ]
    }
  }
}
```

### Using `engram guard`

```bash
engram guard rules                                # List all rules
engram guard blocks                               # Recent blocks
engram guard toggle npm-publish                   # Toggle a rule
engram guard level git-reset-hard warn            # Set block level
engram guard allow "git reset --hard HEAD~1" --reason "Common dev workflow"
engram guard deny "git reset --hard HEAD~1"       # Remove from allowlist
engram guard config                               # Interactive configuration
engram guard defaults --level warn                # Set global default
engram guard reset                                # Factory defaults
```

---

## Automation & Ingestion

Engram supports multiple patterns for getting external data into the knowledge graph, including text, documents, and video/audio media.

### Video and Audio Ingestion

Engram can ingest video and audio files by extracting audio via ffmpeg and transcribing with Whisper.

```bash
# Ingest a video file
engram ingest video ~/obsidian/vault ./meeting-recording.mp4 \
  --speaker "Team Standup" --date "2026-03-23"

# Ingest audio
engram ingest audio ~/obsidian/vault ./voice-memo.mp3 \
  --title "Architecture Discussion"

# Batch-process a directory
engram ingest video-batch ~/obsidian/vault ./recordings/ \
  --date-from-filename --parallel 4
```

### Manual Ingestion

```bash
engram ingest transcript ~/obsidian/vault ./call-notes.txt --speaker "Bob"
engram ingest url ~/obsidian/vault "https://example.com/article" --title "Overview"
engram ingest pdf ~/obsidian/vault ./whitepaper.pdf --title "System Design"
engram ingest file ~/obsidian/vault ./meeting-notes.md --title "Sprint Retro"
```

### Curator Maintenance Cycle

The curator engine runs an 8-step maintenance cycle on your vault:

1. Process inbox (route queue-agent, queue-human, queue-cicd, queue-session)
2. Run mycelium consolidation (spreading activation, memory decay, path reinforcement)
3. Weave wikilinks (connect related notes)
4. Staleness scan (flag outdated content)
5. Conflict resolution (detect contradictions)
6. Schema enforcement (validate frontmatter)
7. Index update (rebuild graph index)
8. Health report (summary of vault state)

```bash
engram brain expand --curator-cycle
```

---

## Configuration

### Plugin Config

**Location:** `~/.openclaw/extensions/engram/config/.engram.env`

Environment-style config for the plugin. Set during install by the wizard.

### Guard Rules

**Location:** `~/.openclaw/extensions/engram/config/guard-rules.json`

Controls all 16 guard rules, block levels, allowlists, and per-repo overrides. See [Guard System](#guard-system) for the full schema.

### Key Config Properties

| Property | Type | Default | Description |
|---|---|---|---|
| `enabled` | boolean | true | Enable/disable the plugin |
| `profile` | string | `"balanced"` | Safety profile |
| `obsidianVault` | string | `~/obsidian/vault` | Path to Obsidian knowledge vault |
| `codeGraphEnabled` | boolean | false | Enable AST analysis, call graphs, impact analysis |
| `provenanceEnabled` | boolean | true | Enable hash-chained cryptographic receipts |
| `contextEngine` | string/null | null | `"lossless-claw"` for LCM integration, null for file-based |
| `promotionThreshold` | number | 70 | Minimum score for auto-promotion (0-100) |

---

## Coming Soon

The following features exist in the codebase but are not fully wired or tested end-to-end:

- **Connected mode** — `engram connect` / `engram disconnect` for joining shared vaults. The underlying `sync_daemon.py`, `invites.py`, and `heartbeat.py` modules are implemented but not tested in multi-user scenarios.
- **Connectors** — `engram connector` for GitHub, Slack, Email, filesystem, webhooks, and cron-based fetching. Connector modules exist at `plugin/lib/connectors/` but have not been tested against live external services.
- **File watcher** — `engram watch` for auto-ingestion of files dropped into monitored directories.
- **Obsidian-headless sync** — Multi-machine vault sync via `ob` CLI for connected/curator modes.
- **Pretool guard delivery** — The `before_tool_call` hook depends on OpenClaw gateway lifecycle events not yet exposed in all runtimes. The guard code works; delivery depends on the gateway version.

---

## Troubleshooting

### "plugin not found"

Check that `package.json` exists in the plugin directory with `"openclaw": { "extensions": ["./index.ts"] }` and the gateway config has the plugin entry under `plugins.installs`.

### "missing register/activate export"

The `index.ts` must export a default object with a `register(api)` method.

### SDK not found

The installer should create a symlink at `~/.openclaw/extensions/engram/node_modules/openclaw`. If missing:

```bash
ls ~/.openclaw/extensions/*/node_modules/openclaw
ln -s <detected_path> ~/.openclaw/extensions/engram/node_modules/openclaw
```

### Hooks not showing in `openclaw hooks list`

Expected behavior. Engram registers hooks as lifecycle listeners via `api.on()`, which do not appear in `openclaw hooks list`. Verify by running `engram doctor`.

### Run diagnostics

```bash
engram doctor       # Full diagnostics across all 5 layers
engram wizard       # Re-run wizard to fix configuration
```

---

## Using Hooks with Claude Code

Two of the four hooks can be wired directly into Claude Code via its native hooks system in `~/.claude/settings.json`:

```json
{
  "hooks": {
    "session_initialization": [
      {
        "command": "python3 ~/.openclaw/extensions/engram/plugin/hooks/handlers/session-start.py",
        "timeout": 10000
      }
    ],
    "agent_stop": [
      {
        "command": "python3 ~/.openclaw/extensions/engram/plugin/hooks/handlers/stop-quality-gate.py",
        "timeout": 5000
      }
    ]
  }
}
```

**Works with Claude Code today:**
- `session-start` — injects git context and LACP memory
- `stop-quality-gate` — catches premature stops and rationalization patterns

**Requires OpenClaw (not available in Claude Code):**
- `pretool-guard` — intercepts tool calls before execution
- `write-validate` — validates file writes before they happen

---

## Video / Audio Transcription

Engram ingests video and audio files via ffmpeg + [insanely-fast-whisper](https://github.com/Vaibhavs10/insanely-fast-whisper):

```bash
# Install
pipx install insanely-fast-whisper==0.0.15 --force --pip-args="--ignore-requires-python"

# Use with Engram
engram ingest video /Volumes/Vault ~/recordings/meeting.mp4 --title "Q1 Planning"
```

| Setup | ~Time for 1 hour of audio | Notes |
|-------|--------------------------|-------|
| NVIDIA A100 / 4090 | ~1 min | Best performance |
| NVIDIA T4 / 3060 | ~3-5 min | Use `--batch-size 12` if you hit OOM |
| Mac (Apple Silicon) | ~5-10 min | Auto-sets `--device-id mps --batch-size 4` |
| CPU only | ~20-40 min | Use `openai-whisper` instead |

---

## Contributing

### Repo Structure

```
engram/
  package.json               # @easylabs/engram
  openclaw.plugin.json       # Plugin manifest (hooks, profiles, config schema, bins)
  INSTALL.sh                 # Install script (consumed by wizard output)
  bin/
    engram                   # Main CLI entry point (bash router)
    wizard.mjs               # Node.js interactive wizard (@clack/prompts)
  plugin/
    index.ts                 # Gateway entry point (hook + tool registration)
    bin/                     # CLI tools (engram-*)
    config/                  # Guard rules, example configs
    hooks/
      handlers/              # Python hook scripts
      managed/               # Auto-capture hook
      profiles/              # 7 safety profile JSONs
      tests/                 # Hook unit tests (pytest)
    lib/                     # Python modules
      mycelium.py            # Spreading activation, FSRS memory model
      curator.py             # 8-step curator maintenance cycle
      vault_doctor.py        # Orphan scan, frontmatter fix, tag detection
      vault_migrate.py       # Vault structure migration
      connectors/            # GitHub, Slack, Email, filesystem, webhook, cron
      tests/                 # Lib unit tests
```

### Running Tests

```bash
cd plugin && python -m pytest -v               # Everything
cd plugin && python -m pytest hooks/tests/ -v   # Hook tests
cd plugin && python -m pytest lib/tests/ -v     # Lib tests
```

---

## Dependencies

**Required (installed automatically):**

| Dependency | What it enables |
|-----------|-----------------|
| QMD | Semantic search, memory backend, context injection |
| poppler (pdftotext) | PDF text extraction for ingestion |

**Optional (offered during setup):**

| Dependency | What it enables |
|-----------|-----------------|
| ffmpeg | Video/audio processing for media ingestion |
| insanely-fast-whisper | GPU-accelerated audio transcription |
| GitNexus | Multi-language AST, call graphs, complexity analysis |
| lossless-claw | Native LCM SQLite context engine |
| obsidian-headless (ob) | Multi-machine vault sync for connected/curator modes |

---

## License

MIT
