# Phase C Integration

Phase C introduced config-driven backend selection, completing the transition from a single-backend architecture to a pluggable context engine system. This document covers the changes from v2.0.0 to v2.2.0.

---

## What Phase C Adds

Phase C is the third major integration phase of the OpenClaw LACP Fusion plugin:

- **Phase A** (v1.0.0) -- hooks, policy gates, memory scaffolding, provenance tracking.
- **Phase B** (v2.0.0) -- LCM bidirectional integration: promotion scorer, context injection, semantic dedup, confidence calibration, multi-agent sharing.
- **Phase C** (v2.2.0) -- config-driven backend selection, the `discover` command, `--backend` CLI flag, and the ContextBackend abstraction.

Phase C makes the plugin's context engine swappable at runtime. Instead of hardcoding the file-based approach, the plugin reads `contextEngine` from config and delegates to the appropriate backend.

---

## v2.0.0 to v2.2.0 Changes

### New config keys

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `contextEngine` | `string \| null` | `null` | Backend selector: `"lossless-claw"` or `null` (file-based) |
| `lcmQueryBatchSize` | `number` | `50` | Batch size for LCM database queries (1-1000) |
| `autoDiscoveryInterval` | `string` | `"6h"` | How often to auto-discover summaries (requires LCM backend) |

### New CLI flags

| Flag | Commands | Description |
|------|----------|-------------|
| `--backend <name>` | `promote`, `context` | Override the configured backend (`lossless-claw` or `file`) |
| `--discover` | `promote`, `context` | Auto-discover summaries/context from LCM backend |

### New subcommand

Both `openclaw-lacp-promote` and `openclaw-lacp-context` gained a `discover` subcommand:

```bash
openclaw-lacp-promote discover [--project <name>] [--since <date>] [--limit <n>] [--backend <name>]
openclaw-lacp-context discover --topic <topic> [--project <name>] [--limit <n>] [--backend <name>]
```

### Version bump

- `plugin/v2-lcm/__init__.py` -- `__version__` changed from `"2.0.0"` to `"2.2.0"`
- `openclaw.plugin.json` -- `version` changed from `"2.0.0"` to `"2.2.0"`
- CLI scripts -- `VERSION` variable updated to `"2.2.0"`

---

## Backend Abstraction Architecture

```
openclaw.plugin.json
    |
    +-- configSchema.contextEngine  -->  "lossless-claw" | null
    |
    v
get_backend(config)
    |
    +-- LCMBackend (SQLite)    <-- contextEngine = "lossless-claw"
    |       |
    |       +-- discover_summaries()
    |       +-- find_context()
    |       +-- get_ancestors() (DAG traversal)
    |
    +-- FileBackend (Files)    <-- contextEngine = null
            |
            +-- load_layer1_facts()   (MEMORY.md, patterns.md, context.json)
            +-- load_layer2_links()   (Obsidian wikilinks)
            +-- score_fact()          (relevance scoring)
```

The abstraction allows all downstream components (promotion scorer, semantic dedup, confidence calibration, sharing policy) to work identically regardless of the active backend. The backend only controls **how summaries are discovered and retrieved**; scoring, dedup, and promotion logic remain the same.

---

## Config Loader and Validation

### Config sources

The plugin config is loaded from `~/.openclaw/openclaw.json` using the following path:

```
.plugins.entries["openclaw-lacp-fusion"].config
```

Or in the flat format:

```
.["openclaw-lacp-fusion"].config
```

### Validation

The config schema is defined in `openclaw.plugin.json` under `configSchema`. Key validations:

- `contextEngine` must be `"lossless-claw"` or `null`. Any other string is rejected.
- `lcmQueryBatchSize` must be between 1 and 1000.
- `promotionThreshold` must be between 0 and 100.
- `autoDiscoveryInterval` must be one of: `"1h"`, `"2h"`, `"4h"`, `"6h"`, `"8h"`, `"12h"`, `"24h"`.

### Environment variable fallbacks

CLI scripts also read from environment variables as fallbacks:

| Variable | Config Key Equivalent | Default |
|----------|----------------------|---------|
| `OPENCLAW_VAULT_ROOT` | `obsidianVault` | `~/.openclaw/vault` |
| `OPENCLAW_MEMORY_ROOT` | (internal) | `~/.openclaw/memory` |
| `OPENCLAW_PROMOTIONS_LOG` | (internal) | `~/.openclaw/logs/promotions.jsonl` |
| `OPENCLAW_PROVENANCE_DIR` | (internal) | `~/.openclaw/provenance` |

---

## New CLI Flags

### --discover

The `--discover` flag (or `discover` subcommand) triggers auto-discovery of summaries from the LCM database. It requires the lossless-claw backend.

**On `openclaw-lacp-promote`:**

```bash
# Discover recent summaries for a project
openclaw-lacp-promote discover --project easy-api --since 2026-03-01 --limit 20
```

Output: JSON lines, one per discovered summary.

**On `openclaw-lacp-context`:**

```bash
# Discover context relevant to a topic
openclaw-lacp-context discover --topic "settlement" --project easy-api --limit 10
```

Output: JSON lines, one per relevant context entry.

### --backend

The `--backend` flag overrides the configured `contextEngine` for a single invocation.

```bash
# Force LCM backend
openclaw-lacp-promote discover --backend lossless-claw --project easy-api

# Force file backend
openclaw-lacp-context inject --backend file --project easy-api --topic "checkout"
```

Valid values: `lossless-claw`, `file`.

---

## Example Configs

### Lossless-claw backend (recommended for LCM users)

```json
{
  "openclaw-lacp-fusion": {
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

See: `plugin/config/example-openclaw-lacp.lossless-claw.json`

### File-based backend (default)

```json
{
  "openclaw-lacp-fusion": {
    "enabled": true,
    "config": {
      "contextEngine": null,
      "promotionThreshold": 70
    }
  }
}
```

See: `plugin/config/example-openclaw-lacp.file-based.json`

### Full config with all options

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

## Testing Strategy

### Unit tests

Phase C tests are in `plugin/hooks/tests/test_phase_c_d_integration.py`. They cover:

- **Promotion to dedup pipeline** -- score a summary, check dedup, verify novel facts pass.
- **Promotion to calibration pipeline** -- promote a fact, track it, mark as used, verify metrics.
- **Promotion with policy** -- verify role-based access (writers can promote, readers cannot).
- **End-to-end pipeline** -- full cycle: score, dedup, policy check, calibrate.
- **CLI integration** -- verify all scripts exist, are executable, and respond to `--help`.

### Running tests

```bash
cd plugin
python -m pytest hooks/tests/test_phase_c_d_integration.py -v
```

### Test coverage areas

| Area | Test File |
|------|-----------|
| Phase C/D integration | `hooks/tests/test_phase_c_d_integration.py` |
| Promotion scorer | `v2-lcm/tests/test_promotion_scorer.py` |
| Semantic dedup | `v2-lcm/tests/test_semantic_dedup.py` |
| Confidence calibration | `v2-lcm/tests/test_confidence_calibration.py` |
| Sharing policy | `v2-lcm/tests/test_sharing_policy.py` |
| Context injection | `v2-lcm/tests/test_cli_context.py` |
| Promote CLI | `v2-lcm/tests/test_cli_promote.py` |
| Config handling | `hooks/tests/test_config.py` |
