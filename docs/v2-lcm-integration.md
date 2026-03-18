# v2.0.0 — LCM Bidirectional Integration

## Architecture

v2.0.0 introduces a bidirectional bridge between LACP (persistent memory) and LCM (session-bound context). This enables a knowledge flywheel: each session enriches the persistent memory, and each new session starts with the accumulated knowledge.

### Flow

```
Session Starts
    ↓
[openclaw-lacp-context inject] → Facts injected into LCM window
    ↓
Agent reasons (informed by LACP)
    ↓
Session ends → LCM creates summary (sum_xxx)
    ↓
[openclaw-lacp-promote] → Score summary, auto-promote high-value facts to LACP
    ↓
[openclaw-brain-graph sync --from-lcm] → Enrich Obsidian knowledge graph
    ↓
Next session → Cycle repeats with enriched memory
```

### Components

| Component | Type | Purpose |
|-----------|------|---------|
| `promotion_scorer.py` | Python module | Score LCM summaries for promotion |
| `lcm_lacp_linker.py` | Python module | Create cross-references between LCM and LACP |
| `openclaw-lacp-context` | Bash CLI | Inject LACP facts into LCM sessions |
| `openclaw-lacp-promote` | Bash CLI | Promote facts from LCM to LACP |
| `openclaw-lacp-share` | Bash CLI | Multi-agent sharing (Phase B stubs) |
| `openclaw-brain-graph sync` | Bash CLI | Sync promoted facts to Obsidian graph |

## Roadmap

### Phase A (v2.0.0) — Foundation
- Promotion scoring system
- Context injection CLI
- Promotion pipeline CLI
- LCM ↔ LACP cross-references
- Knowledge graph auto-enrichment

### Phase B (v2.1.0) — Multi-Agent Sharing
- Cross-agent memory queries
- Granular access control
- Shared fact deduplication
- Agent trust scoring

## Backward Compatibility

- All v1.0.0 CLI commands work unchanged
- All v1.0.0 tests pass (512/512)
- v2.0.0 features are opt-in (new commands only)
- LACP Layer 1-5 compatibility maintained
- Config is backward compatible
