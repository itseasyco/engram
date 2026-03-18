# Provenance — Layer 5: Identity & Hash Chains

Layer 5 provides tamper-proof audit trails through SHA-256 hash-chained session receipts and persistent agent identities.

## Architecture

```
Agent Session Start
    ↓
┌─────────────────────────┐
│ openclaw-provenance      │
│   start                  │ → .sessions/<id>.tmp
│                          │
│ (agent does work...)     │
│                          │
│   end                    │ → chain.jsonl (append)
│   SHA-256 hash chain:    │
│   prev_hash + execution  │
│   → next_hash            │
└─────────────────────────┘
    ↓
Verifiable Audit Trail
```

## Hash Chain

Each session receipt contains:

```json
{
  "session_id": "2026-03-18-a68e0611",
  "agent_id": "wren-abc123",
  "prev_hash": "0000...0000",
  "execution": {
    "start_time": "2026-03-18T10:00:00Z",
    "end_time": "2026-03-18T10:05:00Z",
    "duration_seconds": 300,
    "exit_code": 0,
    "files_modified": 5
  },
  "signature": "sig-abc123...",
  "next_hash": "abc123..."
}
```

The `next_hash` is computed as:
```
SHA-256(prev_hash + execution_json)
```

This creates an immutable chain: if any receipt is tampered with, all subsequent hashes become invalid.

## Commands

### Start Session

```bash
SESSION=$(openclaw-provenance start --project ~/repos/easy-api --agent-id wren-abc)
```

Returns a session ID. Creates a temporary session file with `prev_hash`.

### End Session

```bash
openclaw-provenance end $SESSION --exit-code 0 --files-modified 5 --project ~/repos/easy-api
```

Computes the hash chain, seals the receipt, appends to `chain.jsonl`.

### Verify Chain

```bash
openclaw-provenance verify --project ~/repos/easy-api
```

Walks the chain and verifies each `prev_hash` matches the previous receipt's `next_hash`. Reports any tampering.

### Export Audit Trail

```bash
# JSONL (native format)
openclaw-provenance export --project ~/repos/easy-api --format jsonl --output audit.jsonl

# JSON array
openclaw-provenance export --project ~/repos/easy-api --format json --output audit.json

# CSV (for spreadsheets)
openclaw-provenance export --project ~/repos/easy-api --format csv --output audit.csv
```

### Check Status

```bash
openclaw-provenance status --project ~/repos/easy-api
```

Shows session count, last activity, and integrity status.

## Agent Identity

### Register Agent

```bash
openclaw-agent-id register --project ~/repos/easy-api --agent-name wren
```

Creates a persistent identity per `(hostname, project)` pair.

### Show Identity

```bash
openclaw-agent-id show --project ~/repos/easy-api
```

### List All Identities

```bash
openclaw-agent-id list
```

### Touch (Update Timestamp)

```bash
openclaw-agent-id touch --project ~/repos/easy-api
```

## Storage

```
~/.openclaw/provenance/<project-slug>/
├── chain.jsonl              # Hash-chained receipts
├── .current-session         # Active session ID
└── .sessions/
    └── <session-id>.tmp     # Temp file during active session

~/.openclaw/agent-ids/
└── <slug>.json              # Per-project agent identity

~/.openclaw/projects/<slug>/provenance/
└── agent-identity.json      # Project-scoped identity
```

## Configuration

Set in `.openclaw-lacp.env`:

```bash
PROVENANCE_ROOT=~/.openclaw/provenance
AGENT_ID_STORE=~/.openclaw/agent-ids
AGENT_AUTO_REGISTER=true
PROVENANCE_HASH_ALGORITHM=sha256
PROVENANCE_CHAIN_VERIFICATION=strict
PROVENANCE_RECEIPT_TTL_DAYS=365
```

## Tamper Detection

The verification process checks three things:

1. **Chain continuity**: Each receipt's `prev_hash` matches the previous receipt's `next_hash`
2. **Hash integrity**: The `next_hash` matches `SHA-256(prev_hash + execution_json)`
3. **Genesis receipt**: The first receipt has `prev_hash` of all zeros

```bash
$ openclaw-provenance verify --project ~/repos/easy-api
[✓] Line 1 (2026-03-18-a68e0611): hash verified
[✓] Line 2 (2026-03-18-b72f1122): hash verified
[✓] Line 3 (2026-03-18-c83g2233): hash verified

✓ Chain verified: all 3 receipts intact
```

If tampering is detected:
```bash
[ERROR] Line 2 (2026-03-18-b72f1122): hash mismatch!
  Expected prev: abc123...
  Got prev: fff000...

✗ Chain verification FAILED: 1 errors found
```

## Cross-Platform Compatibility

The provenance system uses `shasum -a 256` on macOS and `sha256sum` on Linux, auto-detected at runtime.

## Integration

### With Layer 1 (Session Memory)
Provenance is automatically initialized with `openclaw-brain-stack init`.

### With Layer 2 (Knowledge Graph)
Audit trails can be exported and indexed into the Obsidian vault.

### With Policy Gates
The `openclaw-gated-run` command integrates with provenance to log gate decisions.

## Doctor Check

```bash
openclaw-brain-doctor --project ~/repos/easy-api --layer 5
```

Checks:
- Agent identity registered
- Provenance chain exists
- Chain integrity verified

## Troubleshooting

**sha256sum not found**: The system auto-detects `shasum -a 256` on macOS. No action needed.

**Chain verification failed**: Investigate which receipt was tampered. Export as JSON and compare hashes manually.

**Session not found on end**: Ensure `start` and `end` use the same `--project` path. The path is converted to a slug for storage.
