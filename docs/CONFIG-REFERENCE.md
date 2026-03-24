# Config Reference

Complete reference for all configuration keys in OpenClaw LACP Fusion v2.2.0.

---

## Config File Location

The plugin reads its config from `~/.openclaw/openclaw.json` in one of two formats:

**Nested format (gateway config):**

```json
{
  "plugins": {
    "entries": {
      "openclaw-lacp-fusion": {
        "config": { ... }
      }
    }
  }
}
```

**Flat format (standalone):**

```json
{
  "openclaw-lacp-fusion": {
    "enabled": true,
    "config": { ... }
  }
}
```

---

## All Config Keys

### enabled

- **Type:** `boolean`
- **Default:** (none -- must be set)
- **Description:** Master switch to enable or disable the plugin.

### profile

- **Type:** `string`
- **Enum:** `"minimal-stop"`, `"balanced"`, `"hardened-exec"`
- **Default:** `"balanced"`
- **Description:** Hook profile controlling which execution hooks are active.
  - `minimal-stop` -- quality gate only (`stop-quality-gate`).
  - `balanced` -- session context injection + quality gate (`session-start`, `stop-quality-gate`).
  - `hardened-exec` -- all hooks enabled (`session-start`, `pretool-guard`, `stop-quality-gate`, `write-validate`).

### obsidianVault

- **Type:** `string`
- **Default:** `"~/obsidian/vault"`
- **Description:** Path to the Obsidian knowledge vault used by Layer 2 (knowledge graph).

### knowledgeRoot

- **Type:** `string`
- **Default:** `"~/.openclaw/data/knowledge"`
- **Description:** Directory for LACP knowledge graph data storage.

### automationRoot

- **Type:** `string`
- **Default:** `"~/.openclaw/data/automation"`
- **Description:** Directory for automation data storage.

### localFirst

- **Type:** `boolean`
- **Default:** `true`
- **Description:** When true, all data stays on-device with no external sync. Disabling this is not currently supported but reserved for future remote sync features.

### codeGraphEnabled

- **Type:** `boolean`
- **Default:** `false`
- **Description:** Enable Layer 4 code intelligence (AST analysis, call graphs, impact analysis). Requires additional setup.

### provenanceEnabled

- **Type:** `boolean`
- **Default:** `true`
- **Description:** Enable Layer 5 provenance tracking with hash-chained cryptographic receipts for audit trails.

### policyTier

- **Type:** `string`
- **Enum:** `"safe"`, `"review"`, `"critical"`
- **Default:** `"review"`
- **Description:** Default risk tier for tasks that don't match any policy rule.

### costCeilingSafeUsd

- **Type:** `number`
- **Minimum:** `0`
- **Default:** `1.0`
- **Description:** Maximum cost (USD) for tasks in the `safe` tier before requiring approval.

### costCeilingReviewUsd

- **Type:** `number`
- **Minimum:** `0`
- **Default:** `10.0`
- **Description:** Maximum cost (USD) for tasks in the `review` tier before requiring approval.

### costCeilingCriticalUsd

- **Type:** `number`
- **Minimum:** `0`
- **Default:** `100.0`
- **Description:** Maximum cost (USD) for tasks in the `critical` tier before requiring approval.

### approvalCacheTtlMinutes

- **Type:** `integer`
- **Minimum:** `0`
- **Default:** `30`
- **Description:** How long (in minutes) an approval decision is cached before re-prompting.

### contextEngine

- **Type:** `string | null`
- **Enum:** `"lossless-claw"`, `null`
- **Default:** `null`
- **Description:** Selects the context backend for summary discovery and retrieval.
  - `"lossless-claw"` -- uses the native LCM SQLite database (`lcm.db`) for structured queries and DAG traversal.
  - `null` -- uses the file-based backend, reading from vault markdown files and memory directories.

### lcmQueryBatchSize

- **Type:** `number`
- **Minimum:** `1`
- **Maximum:** `1000`
- **Default:** `50`
- **Description:** Number of rows fetched per query when using the LCM backend. Higher values improve throughput for bulk operations but use more memory.

### promotionThreshold

- **Type:** `number`
- **Minimum:** `0`
- **Maximum:** `100`
- **Default:** `70`
- **Description:** Minimum promotion score (0-100) required for auto-promotion. Facts scoring below this threshold are skipped unless manually promoted. The confidence calibration system (`openclaw-lacp-calibrate`) can adjust this dynamically.

### autoDiscoveryInterval

- **Type:** `string`
- **Enum:** `"1h"`, `"2h"`, `"4h"`, `"6h"`, `"8h"`, `"12h"`, `"24h"`
- **Default:** `"6h"`
- **Description:** How often the auto-discovery process scans for new summaries. Only effective when `contextEngine` is set to `"lossless-claw"`.

---

## Full Example: openclaw.json

```json
{
  "openclaw-lacp-fusion": {
    "enabled": true,
    "config": {
      "profile": "balanced",
      "obsidianVault": "~/obsidian/vault",
      "knowledgeRoot": "~/.openclaw/data/knowledge",
      "automationRoot": "~/.openclaw/data/automation",
      "localFirst": true,
      "codeGraphEnabled": false,
      "provenanceEnabled": true,
      "policyTier": "review",
      "costCeilingSafeUsd": 1.0,
      "costCeilingReviewUsd": 10.0,
      "costCeilingCriticalUsd": 100.0,
      "approvalCacheTtlMinutes": 30,
      "contextEngine": "lossless-claw",
      "lcmQueryBatchSize": 50,
      "promotionThreshold": 70,
      "autoDiscoveryInterval": "6h"
    }
  }
}
```

---

## Environment Variables

Environment variables override config file values. They are read by CLI scripts at runtime.

### Core paths

| Variable | Description | Default |
|----------|-------------|---------|
| `SESSION_MEMORY_ROOT` | Session memory storage root | `~/.openclaw/projects` |
| `OPENCLAW_VAULT_ROOT` | LACP vault root (promoted facts, vault notes) | `~/.openclaw/vault` |
| `OPENCLAW_MEMORY_ROOT` | Memory directory for promoted facts | `~/.openclaw/memory` |
| `LACP_OBSIDIAN_VAULT` | Obsidian vault path | `~/obsidian/vault` |
| `LACP_KNOWLEDGE_ROOT` | Knowledge graph storage | `~/.openclaw/data/knowledge` |

### Logging

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENCLAW_PROMOTIONS_LOG` | Promotions JSONL log | `~/.openclaw/logs/promotions.jsonl` |
| `OPENCLAW_INJECTION_LOG` | Context injection JSONL log | `~/.openclaw/logs/injections.jsonl` |
| `OPENCLAW_GATED_RUNS_LOG` | Gated execution audit log | `~/.openclaw/logs/gated-runs.jsonl` |
| `GATED_RUNS_LOG` | Alias for gated runs log | `~/.openclaw/logs/gated-runs.jsonl` |

### Identity and provenance

| Variable | Description | Default |
|----------|-------------|---------|
| `PROVENANCE_ROOT` | Provenance chain storage | `~/.openclaw/provenance` |
| `OPENCLAW_PROVENANCE_DIR` | Alias for provenance directory | `~/.openclaw/provenance` |
| `AGENT_ID_STORE` | Agent identity storage | `~/.openclaw/agent-ids` |

### Session

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENCLAW_SESSION_ID` | Current session ID (set by session-start hook) | (auto-generated) |

### Feature flags

| Variable | Description | Default |
|----------|-------------|---------|
| `LACP_LOCAL_FIRST` | Keep all data on-device | `true` |
| `LACP_WITH_GITNEXUS` | Enable GitNexus code intelligence | `false` |

---

## Config File vs. Environment Variables

Environment variables take precedence for path-related settings (vault root, memory root, log paths). The JSON config file is authoritative for behavioral settings (profile, thresholds, engine selection).

For the `contextEngine` setting specifically, the JSON config is the primary source. The `--backend` CLI flag overrides both config and environment.

Precedence order (highest to lowest):
1. CLI flags (`--backend`, `--threshold`, etc.)
2. Environment variables (for paths and feature flags)
3. JSON config file (`~/.openclaw/openclaw.json`)
4. Built-in defaults
