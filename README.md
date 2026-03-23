# Engram

**By [Easy Labs](https://itseasy.co)**

**v2.2.0** -- Persistent agent memory, knowledge graph, safety hooks, code intelligence, provenance tracking, and video/audio ingestion. 10 MCP tools for Claude Code and compatible agents.

![MIT License](https://img.shields.io/badge/license-MIT-blue.svg)
![OpenClaw >= 0.23.0](https://img.shields.io/badge/openclaw-%3E%3D0.23.0-green.svg)
![Python >= 3.9](https://img.shields.io/badge/python-%3E%3D3.9-yellow.svg)
![Tests](https://img.shields.io/badge/tests-122%2F122-brightgreen.svg)

---

## Overview

Engram brings persistent agent memory into your development workflow. It gives your agents session memory that survives across conversations, a knowledge graph backed by Obsidian, safety hooks that block dangerous operations before they execute, and a hash-chained provenance trail for every session.

The plugin implements a 5-layer memory system: per-project session memory with daily structure, an Obsidian-backed knowledge graph, an ingestion pipeline for external content (including video and audio), AST-level code intelligence, and cryptographic provenance receipts. These layers work together so that every agent session starts with institutional context and ends with auditable evidence of what happened.

Engram is for teams and individuals who run agents on real codebases and need guardrails (blocking `npm publish`, `git reset --hard`, secrets access), persistent memory (facts that carry between sessions), and a clear audit trail. It is local-first by default -- all data stays on your machine.

**Key capabilities:**

- Execution hooks (session context injection, pretool guard, quality gate, write validation)
- Risk-based policy routing with three tiers (safe / review / critical) and cost ceilings
- Per-project session memory with daily folder structure and per-agent session files
- Obsidian-backed knowledge graph with semantic search (QMD)
- Video and audio ingestion via ffmpeg + Whisper transcription
- Code intelligence via AST analysis, call graphs, and impact analysis
- Cryptographic provenance tracking (SHA-256 hash-chained receipts)
- Multi-agent memory sharing with role-based access
- Configurable safety profiles from autonomous to full-audit
- **10 MCP tools** for memory query, fact promotion, ingestion, guard status, vault management, graph indexing, brain resolution, memory KPIs, vault optimization, and session saving
- 25+ CLI tools for managing memory, guard rules, ingestion, and more

---

## Quick Start

### Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| OpenClaw | >= 0.23.0 | Core runtime |
| Python | >= 3.9 | Hook handlers are Python scripts |
| Bash | >= 5.0 | CLI tools are bash/python scripts |
| gum | (optional) | Interactive wizard with arrow-key selection; falls back to `read` prompts |
| Obsidian | (optional) | Knowledge graph vault (Layer 2) |
| qmd | (optional) | Semantic search indexing |
| ffmpeg | (optional) | Video/audio ingestion (Layer 3) |
| whisper | (optional) | Audio transcription for media ingestion |

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
git clone https://github.com/easylabs/engram
cd engram
bash INSTALL.sh
```

### First-time Setup

Run the setup wizard:

```bash
engram wizard
```

The wizard walks you through configuration interactively:

1. **Context engine** -- choose `lossless-claw` (native LCM integration) or file-based (default)
2. **Safety profile** -- pick from 7 profiles (see [Safety Profiles](#safety-profiles))
3. **Policy tier** -- default risk tier for unmatched tasks: `safe`, `review`, or `critical`
4. **Obsidian vault** -- auto-detects vaults on your system, or type/browse to a path
5. **Code intelligence** -- enable AST analysis and call graphs (optional)
6. **Provenance tracking** -- hash-chained cryptographic receipts (enabled by default)

After install, verify:

```bash
engram doctor
```

---

## MCP Tools (10 tools)

Engram exposes 10 tools via the Model Context Protocol that agents can call directly during sessions.

| Tool | Description |
|---|---|
| `engram_memory_query` | Query session memory and LACP facts with semantic search |
| `engram_promote_fact` | Promote a session observation to persistent scored fact |
| `engram_ingest` | Ingest transcripts, URLs, PDFs, files, video, and audio into the knowledge graph |
| `engram_guard_status` | Check guard rule status, recent blocks, and allowlist entries |
| `engram_vault_status` | Report on Obsidian vault health, note counts, and index freshness |
| `engram_graph_index` | Trigger knowledge graph re-indexing with optional QMD semantic search |
| `engram_brain_resolve` | Resolve a query against all 5 memory layers and return unified context |
| `engram_memory_kpi` | Return memory system KPIs: fact count, promotion rate, staleness, coverage |
| `engram_vault_optimize` | Run vault optimization: dedup notes, compress stale entries, rebuild index |
| `engram_save_session` | Save session memory to daily folder structure with per-agent session files |

---

## How the Memory System Works

Engram implements a continuous memory lifecycle across agent sessions. Understanding this cycle is key to getting the most out of the plugin.

### The Five Layers

```
Layer 1: Session Memory     ~/.openclaw/projects/<slug>/memory/
Layer 2: Knowledge Graph    ~/obsidian/vault/ (Obsidian + QMD)
Layer 3: Ingestion Pipeline engram ingest (transcripts, URLs, PDFs, video, audio)
Layer 4: Code Intelligence  engram brain (AST, call graphs, impact)
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
  Organized into Projects / Concepts / People / Systems / Inbox
       |
       v
  Session saved to daily structure (engram_save_session)
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

### 2. Daily Session Memory Structure

Session memory is organized into a daily folder structure for easy browsing and automatic indexing:

```
vault/memory/
  2026-03-23/
    agent-a1b2c3-session-001.md
    agent-a1b2c3-session-002.md
    agent-d4e5f6-session-001.md
    _daily-index.md              # Auto-generated summary of all sessions that day
  2026-03-22/
    agent-a1b2c3-session-001.md
    _daily-index.md
```

Each session file contains the agent ID, project slug, start/end timestamps, key facts discovered, commands run, and a session summary. The `_daily-index.md` is auto-generated and links to all session files for that day, providing a chronological view of agent activity.

The `engram_save_session` tool writes session data to this structure at session end. Daily indexes are rebuilt automatically when new sessions are saved.

### 3. Persistent Facts

Persistent facts are extracted from session data and stored via `engram memory context`. Facts have scores, categories, and timestamps. The `engram_promote_fact` tool handles promotion from raw session summaries to scored, persistent facts. Deduplication prevents redundant facts from accumulating. Confidence calibration tunes promotion thresholds over time.

### 4. Knowledge Graph

The Obsidian vault is organized into a taxonomy:

```
vault/
  Projects/       # Per-project knowledge
  Concepts/       # Technical concepts, patterns
  People/         # Team members, contacts
  Systems/        # Infrastructure, services
  Inbox/          # Unsorted incoming notes
    queue-generated/  # Ingested content landing zone
  memory/         # Daily session memory (see above)
    YYYY-MM-DD/   # Per-day folders with agent session files
```

`engram brain graph` initializes and indexes the vault. `engram vault` manages vault status, backups, and optimization. QMD provides semantic search across the vault.

### 5. Lossless Context Integration

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

Set the profile during install or change it later in `~/.openclaw/extensions/engram/config/.engram.env`.

---

## Guard System

The pretool-guard hook intercepts every tool call before execution and checks it against a configurable set of rules.

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

### Built-in Rules

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

# Interactive configuration (gum-powered)
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

# Customize Whisper model for better accuracy
engram ingest video ~/obsidian/vault ./presentation.mov \
  --whisper-model large --language en
```

The pipeline: ffmpeg extracts audio -> Whisper transcribes to text -> transcript is structured into an Obsidian note with timestamps, speaker labels, and metadata.

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

### 5. OpenClaw Cron Integration

If OpenClaw supports recurring jobs, configure them in your project config:

```bash
# Example: auto-ingest and re-index every 6 hours
openclaw cron add "engram ingest index ~/obsidian/vault --qmd" --interval 6h

# Example: promote high-confidence facts daily
openclaw cron add "engram memory promote auto --score 80" --interval 24h
```

### 6. Repo Research Sync

Mirror repository documentation into the knowledge graph:

```bash
# Sync README, docs/, wiki, and code comments into the vault
engram connector repo-sync /path/to/my-repo
```

---

## CLI Reference

The `engram` command is the main entry point with the following subcommands:

| Subcommand | Description |
|---|---|
| `engram wizard` | Interactive first-time setup and reconfiguration |
| `engram status` | Memory and context health dashboard |
| `engram doctor` | Health check across all 5 memory layers with optional auto-fix |
| `engram guard` | Manage guard rules, allowlists, block logs, and repo overrides |
| `engram memory` | Session memory operations: query, append, promote, dedup, calibrate, context |
| `engram brain` | Knowledge graph: ingest, index, resolve, code analysis, expand |
| `engram vault` | Obsidian vault: status, audit, apply, backup, restore, optimize |
| `engram connector` | External integrations: repo-sync, webhook handlers |
| `engram watch` | File watcher for auto-ingestion of new content |
| `engram connect` | Register and activate Engram with an agent runtime |
| `engram disconnect` | Deregister Engram from an agent runtime |

### Additional CLI Tools

| Tool | Description |
|---|---|
| `engram brain ingest` | Ingest transcripts, URLs, PDFs, video, audio, and files into structured vault notes |
| `engram brain graph` | Initialize, index, and query the Obsidian knowledge graph |
| `engram brain code` | AST analysis, symbol lookup, call graphs, and impact analysis |
| `engram brain expand` | Re-summarize, deduplicate, and compress memory layers |
| `engram memory context` | Inject facts into context windows; query and list facts |
| `engram memory promote` | Promote session facts to persistent memory |
| `engram memory calibrate` | Confidence calibration for promotion thresholds |
| `engram memory dedup` | Semantic deduplication for promoted facts |
| `engram memory policies` | View and manage multi-agent sharing policies |
| `engram memory share` | Multi-agent memory sharing with role-based access |
| `engram memory init` | Scaffold per-project session memory structure |
| `engram memory append` | Append execution results to session memory |
| `engram agent-id` | Persistent agent identity per (hostname, project) pair |
| `engram gated-run` | Policy enforcement wrapper for commands (cost ceilings, approval) |
| `engram provenance` | SHA-256 hash-chained session receipts and audit trail |
| `engram route` | Risk-based policy routing for tasks |
| `engram verify` | Task verification with heuristic, test, LLM, and hybrid modes |

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

# Or validate and fix specific issues
engram doctor --fix

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

**Location:** `~/.openclaw/extensions/engram/config/.engram.env`

Environment-style config for the plugin. Set during install by the wizard.

### Guard Rules

**Location:** `~/.openclaw/extensions/engram/config/guard-rules.json`

Controls all guard rules, block levels, allowlists, and per-repo overrides. See [Guard System](#guard-system) for the full schema.

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

### Context Engine Config Examples

**File-based (default):**

```json
{
  "engram": {
    "enabled": true,
    "config": {
      "contextEngine": null,
      "promotionThreshold": 70
    }
  }
}
```

**Lossless-claw backend:**

```json
{
  "engram": {
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

### Config Schema Properties

| Property | Type | Default | Description |
|---|---|---|---|
| `enabled` | boolean | true | Enable/disable the plugin |
| `profile` | string | `"balanced"` | Safety profile: minimal-stop, balanced, hardened-exec |
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
engram doctor --verbose

# Auto-fix common issues
engram doctor --fix

# Output as JSON for scripting
engram doctor --json
```

---

## Contributing

### Repo Structure

```
engram/
  openclaw.plugin.json       # Plugin manifest (hooks, profiles, config schema, bins)
  plugin.json                # Plugin metadata
  INSTALL.sh                 # Interactive install wizard
  plugin/
    index.ts                 # Gateway entry point (hook registration shim)
    bin/                     # 25+ CLI tools
    config/                  # Guard rules, example configs
    hooks/
      handlers/              # Python hook scripts
        session-start.py     # Git context + memory injection
        pretool-guard.py     # Dangerous pattern blocking
        stop-quality-gate.py # Incomplete work detection
        write-validate.py    # Schema/format validation
      profiles/              # 7 safety profile JSONs
      tests/                 # Hook unit tests (pytest)
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

## License

MIT
