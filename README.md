# Engram

**By [Easy Labs](https://itseasy.co)**

**v3.0.0-alpha.1** -- Persistent agent memory, mycelium-powered knowledge graph, safety hooks, code intelligence, provenance tracking, and video/audio ingestion. 10 MCP tools for Claude Code and compatible agents.

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
- Multi-agent memory sharing with role-based access
- Configurable safety profiles from autonomous to full-audit
- **10 MCP tools** for memory query, fact promotion, ingestion, guard status, vault management, graph indexing, brain resolution, memory KPIs, vault optimization, and session saving
- **30 CLI tools** for managing memory, guard rules, ingestion, vault health, and more
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
| Obsidian | (optional) | Knowledge graph vault (Layer 2) |
| qmd | (optional) | Semantic search indexing |
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

Run the setup wizard:

```bash
engram wizard
```

The wizard uses a Node.js interactive UI (powered by @clack/prompts) with arrow-key navigation. It walks you through:

1. **Obsidian vault** -- auto-detects vaults on your system, or type/browse to a path
2. **Context engine** -- choose `lossless-claw` (native LCM integration) or file-based (default)
3. **Safety profile** -- pick from 7 profiles (see [Safety Profiles](#safety-profiles))
4. **Operating mode** -- standalone, connected, or curator
5. **Guard configuration** -- block levels, rule toggling, allowlists
6. **Dependencies** -- GitNexus, lossless-claw, obsidian-headless checks

The wizard outputs config to a temp file that `INSTALL.sh` consumes to complete installation. If Node.js is unavailable, it falls back to legacy bash prompts.

After install, verify:

```bash
engram doctor
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

## How the Memory System Works

Engram implements a continuous memory lifecycle across agent sessions. Understanding this cycle is key to getting the most out of the plugin.

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

### 1. Session Memory

Every project gets its own memory directory at `~/.openclaw/projects/<slug>/memory/`. The `session-start` hook reads the current git context (branch, recent commits, modified files) and injects it as a system message when a new session begins. Execution results -- cost, gate decisions, exit codes, learnings -- are appended via `engram memory append`.

### 2. Session Auto-Capture Hook

Engram includes a managed hook (`engram-session-capture`) that fires automatically when you issue `/new` or `/reset` in OpenClaw. It:

1. Reads the session transcript (last N messages)
2. Extracts key decisions, tasks completed/pending, and notable facts
3. Writes a per-agent session file to `vault/memory/YYYY-MM-DD/`
4. Updates the daily index with wikilinks

No agent action needed -- capture happens as a side effect of ending a session.

### 3. Daily Session Memory Structure

Session memory is organized into a daily folder structure for easy browsing and automatic indexing:

```
vault/memory/
  2026-03-24/
    agent-a1b2c3-session-001.md
    agent-a1b2c3-session-002.md
    agent-d4e5f6-session-001.md
    _daily-index.md              # Auto-generated summary of all sessions that day
  2026-03-23/
    agent-a1b2c3-session-001.md
    _daily-index.md
```

Each session file contains the agent ID, project slug, start/end timestamps, key facts discovered, commands run, and a session summary. The `_daily-index.md` is auto-generated and links to all session files for that day.

### 4. Persistent Facts

Persistent facts are extracted from session data and stored via `engram memory context`. Facts have scores, categories, and timestamps. The `engram_promote_fact` tool handles promotion from raw session summaries to scored, persistent facts. Deduplication prevents redundant facts from accumulating. Confidence calibration tunes promotion thresholds over time.

### 5. Knowledge Graph

The Obsidian vault is organized into the Engram taxonomy:

```
vault/
  home/           # Master index, vault overview
  memory/         # Daily session memory (YYYY-MM-DD folders)
  projects/       # Per-repo/per-project knowledge
  engineering/    # Architecture, decisions, active work
  knowledge/      # Concepts, learnings, agent knowledge
  inbox/          # Incoming notes awaiting curator processing
    queue-agent/    # Agent-submitted facts
    queue-cicd/     # CI/CD events
    queue-human/    # Human-submitted (email, voice notes, research)
    queue-session/  # Auto-captured session memories (connected mode)
    review-stale/   # Curator-flagged for review
  reference/      # External docs, API references
  people/         # Team members, contacts
  health/         # Personal/team health tracking
  strategy/       # Business strategy, planning
  archive/        # Archived/deprecated content
  _metadata/      # Vault config, taxonomy
```

`engram brain graph` initializes and indexes the vault. `engram vault` manages vault status, backups, and optimization. QMD provides semantic search across the vault when available.

### 6. Vault Doctor

The vault doctor scans every note in your vault and fixes what it can:

- Find orphans (notes with zero backlinks)
- Add/fix YAML frontmatter (title, category, tags, dates, status)
- Auto-detect tags from content (#PRD, #research, #architecture, #meeting, etc.)
- Rename hash-named files to prose-style titles
- Detect category and suggest/execute moves to correct folders
- Run wikilink weaver to connect orphans

```bash
engram brain heal
engram brain heal --dry-run    # Preview changes without writing
```

### 7. Vault Migration

For existing vaults that need restructuring into the Engram-compatible layout, the vault migration tool scans your vault, proposes a clean structure, and migrates files with wikilink preservation:

```bash
# Preview migration plan
python3 plugin/lib/vault_migrate.py /path/to/vault --dry-run

# Execute migration
python3 plugin/lib/vault_migrate.py /path/to/vault
```

### 8. Lossless Context Integration

When `contextEngine` is set to `lossless-claw`, the plugin integrates with the LCM (Lossless Context Manager) backend. LCM's DAG compaction works alongside Engram's fact injection: LCM compresses conversational context while Engram injects curated facts at session start. The two systems are complementary -- LCM handles within-session context efficiency, while Engram handles cross-session knowledge persistence.

Configure the integration in your plugin config:

```json
{
  "contextEngine": "lossless-claw",
  "lcmQueryBatchSize": 50,
  "promotionThreshold": 70,
  "autoDiscoveryInterval": "6h"
}
```

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

Set the profile during install or change it later in `~/.openclaw/extensions/engram/config/.openclaw-lacp.env`.

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

The guard ships with rules for common dangerous patterns:

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

### Global Defaults vs Per-Repo Overrides

Global defaults are in `guard-rules.json` under `defaults`. Per-repo overrides let you relax or tighten rules for specific repositories:

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
# List all rules with their status
engram guard rules

# View recent blocks from the log
engram guard blocks
engram guard blocks --tail 20

# Enable or disable a rule
engram guard toggle npm-publish

# Set block level for a specific rule
engram guard level git-reset-hard warn

# Add a command to the global allowlist
engram guard allow "git reset --hard HEAD~1" --reason "Common dev workflow"

# Add a repo-specific allowlist entry
engram guard allow "docker run --privileged" --repo /path/to/ci-repo --reason "CI builds"

# Remove a command from all allowlists
engram guard deny "git reset --hard HEAD~1"

# Interactive configuration
engram guard config

# Configure overrides for a specific repo
engram guard config --repo /path/to/my-repo

# Set global default block level
engram guard defaults --level warn

# Reset to factory defaults
engram guard reset
```

---

## Automation & Ingestion

Engram supports multiple patterns for getting external data into the knowledge graph, including text, documents, and video/audio media.

### 1. Webhook to Agent to Ingest

A webhook receives meeting data and feeds transcripts to the agent for processing:

```bash
# Webhook handler receives a transcript file, then:
engram ingest transcript ~/obsidian/vault /tmp/meeting-2026-03-21.txt \
  --speaker "Alice" --date "2026-03-21"
```

The transcript is converted into a structured Obsidian note with metadata and placed in the `inbox/queue-generated/` directory.

### 2. Video and Audio Ingestion

Engram can ingest video and audio files by extracting audio via ffmpeg and transcribing with Whisper. Supported formats include mp4, mov, mkv, wav, mp3, m4a, flac, ogg, and more.

```bash
# Ingest a single video file
engram ingest video ~/obsidian/vault ./meeting-recording.mp4 \
  --speaker "Team Standup" --date "2026-03-23"

# Ingest a single audio file
engram ingest audio ~/obsidian/vault ./voice-memo.mp3 \
  --title "Architecture Discussion"

# Batch-process an entire directory of video files
engram ingest video-batch ~/obsidian/vault ./recordings/ \
  --date-from-filename --parallel 4

# Customize whisper model for better accuracy
engram ingest video ~/obsidian/vault ./presentation.mov \
  --whisper-model large --language en
```

The pipeline: ffmpeg extracts audio -> insanely-fast-whisper transcribes to text -> transcript is structured into an Obsidian note with timestamps, speaker labels, and metadata.

### 3. Cron-based Sweep

Set up a cron job to ingest files dropped into a directory:

```bash
# In crontab (runs every 6 hours):
0 */6 * * * for f in ~/inbox/*.txt; do engram ingest file ~/obsidian/vault "$f"; done
```

### 4. Manual Ingestion

Use `engram ingest` directly for one-off ingestion:

```bash
# Ingest a transcript
engram ingest transcript ~/obsidian/vault ./call-notes.txt --speaker "Bob" --date "2026-03-20"

# Ingest a URL
engram ingest url ~/obsidian/vault "https://example.com/article" --title "Architecture Overview"

# Ingest a PDF
engram ingest pdf ~/obsidian/vault ./whitepaper.pdf --title "System Design"

# Ingest any file
engram ingest file ~/obsidian/vault ./meeting-notes.md --title "Sprint Retro"

# Re-index the vault (optionally with QMD semantic indexing)
engram ingest index ~/obsidian/vault --qmd
```

### 5. Curator Maintenance Cycle

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

## CLI Reference

The `engram` command is the main entry point with the following subcommands:

### Top-level Commands

| Command | Description |
|---|---|
| `engram wizard` | Interactive setup wizard (Node.js UI with arrow-key navigation) |
| `engram wizard --section <name>` | Run a specific wizard section: `vault`, `engine`, `profile`, `mode`, `guard`, `dependencies`, `all` |
| `engram status` | Memory and context health dashboard (mode, mutations, vault, tools) |
| `engram doctor` | Health check across plugin, hooks, modules, guard config, and tests |
| `engram connect` | Join a shared vault (shortcut for `engram-connect join`) |
| `engram disconnect` | Leave the shared vault |
| `engram uninstall` | Remove Engram (preserves vault data); pass `--yes` to skip confirmation |
| `engram -v` / `engram --version` | Print version |

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

### Memory Commands

| Command | Description |
|---|---|
| `engram memory query <topic>` | Search memory for facts matching a topic |
| `engram memory promote` | Promote session facts to persistent memory |
| `engram memory status` | Show memory system status |
| `engram memory kpi` | Memory quality KPIs |

### Brain Commands

| Command | Description |
|---|---|
| `engram brain expand` | Re-summarize, deduplicate, and compress memory layers |
| `engram brain expand --curator-cycle` | Run full 8-step curator maintenance cycle |
| `engram brain expand --consolidate` | Run mycelium consolidation pass |
| `engram brain resolve` | Resolve contradictions/supersessions in knowledge notes |
| `engram brain kpi` | Vault quality metrics (aliases `engram-memory-kpi`) |
| `engram brain optimize` | Apply memory-centric graph physics defaults to vault |
| `engram brain code` | AST analysis, symbol lookup, call graphs, impact analysis |
| `engram brain graph` | Initialize, index, and query the knowledge graph |
| `engram brain ingest` | Ingest transcripts, URLs, PDFs, video, audio, files |
| `engram brain doctor` | Brain-specific diagnostics |
| `engram brain heal` | Vault doctor: scan orphans, fix frontmatter, add tags, rename hash files |

### Vault Commands

| Command | Description |
|---|---|
| `engram vault status` | Vault health and statistics |
| `engram vault audit` | Full audit (broken links, orphans) |
| `engram vault backup` | Backup vault |
| `engram vault restore` | Restore vault from backup |

### Ingestion & Watch

| Command | Description |
|---|---|
| `engram ingest <type> <vault> <source>` | Ingest content (file, transcript, url, pdf, video, video-batch) |
| `engram watch setup` | Configure file watcher for auto-ingestion |
| `engram watch run` | Run file watcher |
| `engram watch status` | Check watcher status |

### Connector Commands

| Command | Description |
|---|---|
| `engram connector list` | List available connectors |
| `engram connector add` | Add a connector |
| `engram connector remove` | Remove a connector |
| `engram connector test` | Test a connector |

### Additional CLI Tools (plugin/bin)

All 30 CLI tools use the `engram-*` prefix:

| Tool | Description |
|---|---|
| `engram-agent-id` | Persistent agent identity per (hostname, project) pair |
| `engram-brain-code` | AST analysis, symbol lookup, call graphs |
| `engram-brain-doctor` | Brain diagnostics |
| `engram-brain-expand` | Memory expansion, consolidation, curator cycle |
| `engram-brain-graph` | Knowledge graph init, index, query |
| `engram-brain-ingest` | Content ingestion pipeline |
| `engram-brain-resolve` | Contradiction/supersession resolution |
| `engram-brain-stack` | Brain stack inspection |
| `engram-calibrate` | Confidence calibration for promotion thresholds |
| `engram-connect` | Connected mode: join/leave shared vaults |
| `engram-connector` | External integration management |
| `engram-context` | Fact injection and query |
| `engram-dedup` | Semantic deduplication for promoted facts |
| `engram-gated-run` | Policy enforcement wrapper (cost ceilings, approval) |
| `engram-guard` | Guard rule management |
| `engram-ingest-watch` | File watcher for auto-ingestion |
| `engram-memory-append` | Append execution results to session memory |
| `engram-memory-init` | Scaffold per-project session memory structure |
| `engram-memory-kpi` | Memory quality KPIs |
| `engram-memory-status` | Memory system status |
| `engram-obsidian` | Vault management (status, audit, backup, restore) |
| `engram-obsidian-optimize` | Vault graph physics optimization |
| `engram-policies` | View and manage multi-agent sharing policies |
| `engram-promote` | Fact promotion to persistent memory |
| `engram-provenance` | SHA-256 hash-chained session receipts |
| `engram-repo-research-sync` | Mirror repo docs into the knowledge graph |
| `engram-route` | Risk-based policy routing for tasks |
| `engram-share` | Multi-agent memory sharing |
| `engram-validate` | Schema/format validation |
| `engram-verify` | Task verification (heuristic, test, LLM, hybrid modes) |

---

## Coming Soon

The following features exist in the codebase but are not fully wired or tested end-to-end. Use at your own risk.

### Pretool Guard Blocking (Partial)

The `before_tool_call` hook is registered in `index.ts` and shells out to `pretool-guard.py`, but the OpenClaw gateway's `before_tool_call` lifecycle event may not be fully supported in all runtimes yet. The guard code works; delivery depends on the gateway version.

### Connected Mode

The `engram-connect` CLI exists for joining and leaving shared vaults (`engram connect --token inv_abc123`). The underlying `sync_daemon.py`, `invites.py`, and `heartbeat.py` modules are implemented but have not been tested end-to-end against live multi-user scenarios.

### Curator Mode

The curator engine (`plugin/lib/curator.py`) implements the full 8-step maintenance cycle and can be triggered via `engram brain expand --curator-cycle`. The code is functional but has not been battle-tested in production vaults at scale.

### Obsidian-headless Shared Vault Sync

The wizard checks for `obsidian-headless` (`ob` CLI) and the status command reports its presence, but headless vault sync for multi-machine setups is not yet fully integrated.

### Connectors: GitHub, Slack, Email

Connector modules exist at `plugin/lib/connectors/` for GitHub (`github.py`), Slack (`slack.py`), Email (`email.py`), filesystem (`filesystem.py`), webhooks (`webhook.py`), and cron-based fetching (`cron_fetch.py`). These have not been tested against real external services. A community connector packaging system (`community.py`, `registry.py`, `trust.py`) is scaffolded but not production-ready.

---

## Customizing the Install Wizard

### What the Wizard Configures

The `engram wizard` command sets up:

- Plugin directory at `~/.openclaw/extensions/engram/`
- Gateway registration in `~/.openclaw/openclaw.json`
- `package.json` with required fields (`type: "module"`, `openclaw.extensions`)
- `index.ts` entry point (hook registration shim)
- SDK symlink in `node_modules/`
- All configuration files under `config/`
- Safety profile selection
- Obsidian vault path (auto-detected or user-specified)

### Advanced Options

During the wizard you can configure:

- **Guard level**: Set the global default block level (block/warn/log)
- **Rule toggling**: Enable or disable individual guard rules
- **Operating mode**: Standalone, connected, or curator
- **Policy tier**: Default risk tier for unmatched tasks (safe/review/critical)
- **Code graph**: Enable or disable AST analysis and call graphs
- **Provenance**: Enable or disable hash-chained cryptographic receipts
- **Context engine**: Choose between file-based and lossless-claw backends
- **Cost ceilings**: Per-tier spending limits in USD

### Re-running the Wizard

To change settings after install:

```bash
# Re-run the full wizard
engram wizard

# Run a specific section
engram wizard --section guard
engram wizard --section profile
engram wizard --section vault

# Or validate and fix specific issues
engram doctor

# Or configure guard rules interactively
engram guard config
```

---

## Plugin SDK Compatibility

### Current SDK Version

The plugin targets OpenClaw >= 0.23.0 and uses a type-only import from the SDK:

```typescript
import type { OpenClawPluginApi } from "openclaw/plugin-sdk";
```

This import is type-only (`import type`), so it works with the current SDK even though the module may not have a runtime export. The installer creates a symlink at `$PLUGIN_PATH/node_modules/openclaw` pointing to the detected SDK location.

### Hook Registration

Hooks are registered via `api.on()` lifecycle listeners in `index.ts`:

```typescript
api.on("session_start", async (event, ctx) => { ... });
api.on("before_tool_call", async (event, ctx) => { ... });
api.on("agent_end", async (event, ctx) => { ... });
api.on("before_message_write", async (event, ctx) => { ... });
```

Each listener shells out to a Python handler via `execFileSync("python3", [scriptPath], { input: eventJson })`. The Python handlers read JSON from stdin and write JSON to stdout.

### Migration Note

The current SDK exposes `openclaw/plugin-sdk`. A future SDK release may move to `openclaw/plugin-sdk/core`. The `index.ts` entry point will need to be updated when that transition happens. Watch the OpenClaw changelog for migration guidance.

---

## Configuration Reference

### Plugin Config

**Location:** `~/.openclaw/extensions/engram/config/.openclaw-lacp.env`

Environment-style config for the plugin. Set during install by the wizard.

### Guard Rules

**Location:** `~/.openclaw/extensions/engram/config/guard-rules.json`

Controls all 16 guard rules, block levels, allowlists, and per-repo overrides. See [Guard System](#guard-system) for the full schema.

### Gateway Registration

**Location:** `~/.openclaw/openclaw.json`

The plugin must be registered here with `"source": "path"`:

```json
{
  "plugins": {
    "installs": {
      "engram": {
        "source": "path",
        "path": "~/.openclaw/extensions/engram"
      }
    }
  }
}
```

### Plugin Manifest

**Location:** `openclaw.plugin.json` (in the plugin directory)

Declares plugin metadata, hooks, profiles, config schema, capabilities, and CLI binaries. The `kind` field must be `"provider"` and the `name` field must be present.

### Profile Definitions

**Location:** `hooks/profiles/<profile-name>.json`

Each profile JSON declares which hooks are enabled, their configuration (sensitivity, block level, TTL), and usage notes. Available profiles:

- `autonomous.json`
- `balanced.json`
- `context-only.json`
- `guard-rail.json`
- `minimal-stop.json`
- `hardened-exec.json`
- `full-audit.json`

### Config Schema Properties

| Property | Type | Default | Description |
|---|---|---|---|
| `enabled` | boolean | true | Enable/disable the plugin |
| `profile` | string | `"balanced"` | Safety profile: minimal-stop, balanced, hardened-exec, etc. |
| `obsidianVault` | string | `~/obsidian/vault` | Path to Obsidian knowledge vault |
| `knowledgeRoot` | string | `~/.openclaw/data/knowledge` | Directory for knowledge graph data |
| `automationRoot` | string | `~/.openclaw/data/automation` | Directory for automation data |
| `localFirst` | boolean | true | All data stays on-device, no external sync |
| `codeGraphEnabled` | boolean | false | Enable AST analysis, call graphs, impact analysis |
| `provenanceEnabled` | boolean | true | Enable hash-chained cryptographic receipts |
| `policyTier` | string | `"review"` | Default risk tier: safe, review, critical |
| `costCeilingSafeUsd` | number | 1.0 | Cost ceiling for safe-tier tasks (USD) |
| `costCeilingReviewUsd` | number | 10.0 | Cost ceiling for review-tier tasks (USD) |
| `costCeilingCriticalUsd` | number | 100.0 | Cost ceiling for critical-tier tasks (USD) |
| `approvalCacheTtlMinutes` | integer | 30 | TTL for cached approvals |
| `contextEngine` | string/null | null | `"lossless-claw"` for LCM integration, null for file-based |
| `lcmQueryBatchSize` | number | 50 | Batch size for LCM queries |
| `promotionThreshold` | number | 70 | Minimum score for auto-promotion (0-100) |
| `autoDiscoveryInterval` | string | `"6h"` | Auto-discovery interval (requires LCM backend) |

---

## Troubleshooting

### "plugin not found"

The gateway cannot discover the plugin. Check that:
- `package.json` exists in the plugin directory with `"openclaw": { "extensions": ["./index.ts"] }`
- The gateway config (`~/.openclaw/openclaw.json`) has the plugin entry under `plugins.installs`

### "missing register/activate export"

The `index.ts` file is either missing or has the wrong export format. It must export a default object with a `register(api)` method:

```typescript
export default {
  name: "Engram",
  register(api: OpenClawPluginApi) { ... }
};
```

### "source: Invalid input"

In the gateway config, the plugin source must be `"path"`, not `"local"`. The gateway only accepts `npm`, `archive`, or `path`.

### SDK not found

The `index.ts` imports `openclaw/plugin-sdk` which must be resolvable. The installer should create a symlink:

```
~/.openclaw/extensions/engram/node_modules/openclaw -> <sdk_path>
```

If the symlink is missing, find the SDK location and create it manually:

```bash
# Check other installed plugins
ls ~/.openclaw/extensions/*/node_modules/openclaw

# Or check global install
ls "$(dirname "$(which openclaw)")/../lib/node_modules/openclaw"

# Create the symlink
ln -s <detected_path> ~/.openclaw/extensions/engram/node_modules/openclaw
```

### Hooks not showing in `openclaw hooks list`

This is expected behavior. Engram registers hooks as lifecycle listeners via `api.on()`, which do not appear in `openclaw hooks list`. The hooks still fire correctly on their respective events. You can verify by checking the logs or running `engram doctor`.

### Run the full validator

```bash
# Check everything with verbose output
engram doctor

# Re-run the wizard to fix configuration
engram wizard
```

---

## Contributing

### Repo Structure

```
engram/
  package.json               # @easylabs/engram, v2.2.0
  openclaw.plugin.json       # Plugin manifest (hooks, profiles, config schema, bins)
  plugin.json                # Plugin metadata
  INSTALL.sh                 # Install script (consumed by wizard output)
  bin/
    engram                   # Main CLI entry point (bash router)
    wizard.mjs               # Node.js interactive wizard (@clack/prompts)
  plugin/
    index.ts                 # Gateway entry point (hook + tool registration)
    bin/                     # 30 CLI tools (engram-*)
    config/                  # Guard rules, example configs
    hooks/
      handlers/              # Python hook scripts
        session-start.py     # Git context + memory injection
        pretool-guard.py     # Dangerous pattern blocking
        stop-quality-gate.py # Incomplete work detection
        write-validate.py    # Schema/format validation
      managed/
        engram-session-capture/  # Auto-capture hook (/new, /reset)
      profiles/              # 7 safety profile JSONs
      tests/                 # Hook unit tests (pytest)
    lib/                     # Python modules
      mycelium.py            # Spreading activation, FSRS memory model, flow scores
      curator.py             # 8-step curator maintenance cycle
      vault_doctor.py        # Orphan scan, frontmatter fix, tag detection, rename
      vault_migrate.py       # Vault structure migration with wikilink preservation
      consolidation.py       # Memory consolidation
      session_writer.py      # Daily session file writer
      wikilink_weaver.py     # Auto-link related notes
      staleness.py           # Stale content detection
      schema_enforcer.py     # Frontmatter schema validation
      conflict_resolver.py   # Contradiction detection
      inbox_processor.py     # Inbox queue routing
      index_generator.py     # Graph index builder
      health_reporter.py     # Vault health reporting
      mode.py                # Operating mode (standalone/connected/curator)
      heartbeat.py           # Connected mode heartbeat
      sync_daemon.py         # Vault sync daemon
      knowledge_gaps.py      # Gap detection
      review_queue.py        # Review queue management
      connectors/            # GitHub, Slack, Email, filesystem, webhook, cron connectors
      tests/                 # Lib unit tests
    memory/
      tests/                 # Memory layer tests
    policy/                  # Risk policy routing
    v2-lcm/                  # LCM bidirectional integration
      tests/                 # LCM integration tests
  docs/                      # Additional documentation
  releases/                  # Distribution ZIPs
```

### Adding a New Profile

1. Create a JSON file in `plugin/hooks/profiles/<name>.json`
2. Follow the schema from an existing profile (e.g., `balanced.json`)
3. Declare `hooks_enabled`, `hooks_disabled`, and per-hook `configuration`
4. If the profile should be selectable in the manifest, add it to `openclaw.plugin.json` under `profiles`

### Adding a New Guard Rule

1. Edit `plugin/config/guard-rules.json`
2. Add a rule object to the `rules` array:
   ```json
   {
     "id": "my-new-rule",
     "pattern": "\\bsome-dangerous-command\\b",
     "flags": "IGNORECASE",
     "label": "Human-readable label",
     "message": "Why this is blocked.",
     "block_level": "block",
     "enabled": true,
     "category": "destructive"
   }
   ```
3. Add tests in `plugin/hooks/tests/test_pretool_guard.py`

### Adding a New CLI Tool

1. Create the script in `plugin/bin/engram-<name>` (bash or python)
2. Make it executable (`chmod +x`)
3. Register it in `openclaw.plugin.json` under the `bin` map
4. Add corresponding tests

### Running Tests

```bash
# All hook tests
cd plugin && python -m pytest hooks/tests/ -v

# All memory tests
cd plugin && python -m pytest memory/tests/ -v

# All LCM tests
cd plugin && python -m pytest v2-lcm/tests/ -v

# Everything
cd plugin && python -m pytest -v

# Specific test file
cd plugin && python -m pytest hooks/tests/test_pretool_guard.py -v
```

---

## Alternative: Using Hooks with Claude Code

While Engram is designed for the OpenClaw gateway, two of the four hooks can also be wired directly into Claude Code via its native hooks system in `~/.claude/settings.json`:

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
- `session-start` (session_initialization) — injects git context and LACP memory
- `stop-quality-gate` (agent_stop) — catches premature stops and rationalization patterns

**Requires OpenClaw (not available in Claude Code):**
- `pretool-guard` (pre_tool_use) — intercepts tool calls before execution
- `write-validate` (file_write) — validates file writes before they happen

---

## Multi-Agent Setup

The setup wizard scans your `openclaw.json` for configured agents and lets you choose which ones get Engram memory tools.

```bash
engram wizard
```

During setup, the wizard will:

1. Detect all agents in your OpenClaw config
2. Let you select which agents should use Engram
3. Append Engram tool documentation to each agent's `TOOLS.md`
4. Initialize the knowledge graph, agent identity, and provenance chain
5. Wire up integrations (lossless-claw, GitNexus, QMD, MCP servers) based on your choices

Each selected agent gets a `TOOLS.md` section that teaches it when and how to use the memory tools — query before investigating, promote facts as they're discovered, ingest external references, save session state.

To add Engram to additional agents later:

```bash
engram wizard --section agents
```

---

## Dependencies

The wizard detects and installs required dependencies based on the features you enable. Core dependencies are installed automatically. Optional integrations are offered during setup:

| Dependency | Installed by wizard | What it enables |
|-----------|-------------------|-----------------|
| poppler (pdftotext) | Yes, if ingestion enabled | PDF text extraction |
| ffmpeg | Yes, if media ingestion enabled | Video/audio processing |
| GitNexus | Optional (offered during setup) | Multi-language AST, call graphs, complexity analysis |
| lossless-claw | Optional (offered during setup) | Native LCM SQLite context engine |
| obsidian-headless (ob) | Optional (offered during setup) | Multi-machine vault sync for connected/curator modes |
| QMD | Optional (offered during setup) | Semantic search indexing on vault |

---

## Current Limitations

**Hooks — waiting on OpenClaw lifecycle methods:**
- The `pretool-guard` and `write-validate` hooks depend on `pre_tool_use` and `file_write` lifecycle events not yet exposed by the OpenClaw gateway. These hooks are fully implemented and tested, but will only activate once OpenClaw introduces these trigger points. Currently only `session_initialization` (session-start) and `agent_stop` (stop-quality-gate) are wired.

**Code intelligence:**
- Built-in AST parsing covers Python only. If GitNexus is not installed, JS/TS/Go/Rust files are counted but not parsed. The wizard offers to install GitNexus during setup. To add additional repos after setup, run `gitnexus analyze <repo-path>` or instruct your agent to initialize the repo with `engram-brain-code analyze <repo-path>`.

**Ingestion:**
- Video/audio ingestion (`engram-brain-ingest video`) is a work in progress — the pipeline is not fully integrated yet.

**Shared vault (connected/curator modes):**
- Requires `obsidian-headless` (`ob`) which is an experimental dependency. The wizard offers to install it if you select connected or curator mode.

**Execution lifecycle:**
- The 12-state lifecycle (SUBMITTED through COMPLETED) is designed but not tracked at runtime. The gated-run system covers the core approval/execution flow but does not emit state transitions.

---

## License

MIT
