# OpenClaw Infrastructure Integration

How `openclaw-lacp-fusion` integrates with the OpenClaw gateway, plugin system, and agent lifecycle.

---

## Plugin Registration

OpenClaw uses a declarative plugin system. LACP Fusion registers via three mechanisms:

### 1. Plugin Manifest (`openclaw.plugin.json`)

Located at the plugin root. Declares:
- **id** — unique plugin identifier
- **configSchema** — JSON Schema for validating plugin config
- **uiHints** — labels and help text for config fields
- **hooks** — handler definitions with triggers
- **profiles** — named hook presets
- **capabilities** — what the plugin provides
- **bin** — executable scripts

### 2. Gateway Config (`~/.openclaw/openclaw.json`)

The installer adds three entries:

```json
{
  "plugins": {
    "allow": ["openclaw-lacp-fusion"],
    "entries": {
      "openclaw-lacp-fusion": {
        "enabled": true,
        "config": {
          "profile": "balanced",
          "obsidianVault": "~/obsidian/vault",
          "knowledgeRoot": "~/.openclaw/data/knowledge",
          "localFirst": true,
          "provenanceEnabled": true,
          "codeGraphEnabled": false,
          "policyTier": "review"
        }
      }
    },
    "installs": {
      "openclaw-lacp-fusion": {
        "source": "local",
        "installPath": "~/.openclaw/extensions/openclaw-lacp-fusion",
        "version": "2.0.0"
      }
    }
  }
}
```

### 3. Install Path

```
~/.openclaw/extensions/openclaw-lacp-fusion/
├── openclaw.plugin.json    # Plugin manifest
├── hooks/
│   ├── handlers/           # 4 Python hook handlers
│   ├── profiles/           # 3 safety profiles (JSON)
│   └── rules/              # Dangerous pattern rules (YAML)
├── policy/
│   └── risk-policy.json    # 3-tier routing config
├── bin/                    # 15 executable scripts
├── config/
│   ├── .openclaw-lacp.env  # Active config
│   └── .openclaw-lacp.env.template
├── v2-lcm/                 # Lifecycle manager
├── docs/                   # Documentation
└── logs/                   # Runtime logs
```

---

## Hook Lifecycle

LACP Fusion hooks into 4 OpenClaw lifecycle events:

| Hook | Trigger | When | Purpose |
|------|---------|------|---------|
| `session-start` | `session_initialization` | Agent session begins | Inject git context, load LACP memory |
| `pretool-guard` | `pre_tool_use` | Before any tool execution | Block dangerous patterns |
| `stop-quality-gate` | `agent_stop` | Agent reports "done" | Detect incomplete work |
| `write-validate` | `file_write` | Before file write | Validate schema/format |

### Hook Protocol

Each handler receives JSON on stdin and writes JSON to stdout:

```
stdin  → { "event": "...", "context": {...}, "session_id": "..." }
stdout ← { "action": "allow|block|warn", "message": "...", "injected": {...} }
```

Exit codes: `0` = allow, `1` = block, `2` = warn.

### Safety Profiles

Profiles control which hooks are active:

| Profile | Hooks Enabled | Use Case |
|---------|--------------|----------|
| `minimal-stop` | stop-quality-gate | Quick dev, low-risk work |
| `balanced` | session-start, stop-quality-gate | General development (default) |
| `hardened-exec` | All 4 hooks | Production, high-stakes |

Change profile in gateway config:
```bash
jq '.plugins.entries["openclaw-lacp-fusion"].config.profile = "hardened-exec"' \
  ~/.openclaw/openclaw.json > /tmp/oc.json && mv /tmp/oc.json ~/.openclaw/openclaw.json
```

---

## Session Context Injection

When a session starts (with `balanced` or `hardened-exec` profile):

1. `session-start.py` fires on `session_initialization`
2. Collects git context: branch, recent commits, modified files
3. Auto-detects test command (npm test, pytest, cargo test, etc.)
4. Returns injected context for the agent's prompt window

This means agents automatically know:
- What branch they're on
- What changed recently
- How to run tests

---

## Policy Routing

The risk-policy engine routes tasks through 3 tiers:

```
Task arrives → openclaw-route evaluates → Tier assigned
                                           │
                    ┌──────────────────────┤
                    ▼                      ▼                    ▼
                 safe                   review               critical
              (auto-approve)      (cache + approve)     (require confirm)
              $1.00 ceiling       $10.00 ceiling        $100.00 ceiling
```

Rules in `policy/risk-policy.json` match patterns like:
```json
{ "pattern": "agent:wren,channel:webchat", "tier": "safe" }
{ "pattern": "agent:zoe,channel:bridge",   "tier": "review" }
```

---

## Memory Architecture

### Per-Project Sessions

```
~/.openclaw/data/project-sessions/
  └── {PROJECT_SLUG}/
      └── {AGENT_ID}/
          └── {SESSION_ID}/
              ├── MEMORY.md          # Decisions & learnings
              ├── debugging.md       # Issues & solutions
              ├── patterns.md        # Code conventions
              ├── architecture.md    # System design notes
              └── preferences.md     # Team preferences
```

### Knowledge Graph (Layer 2)

Integrates with Obsidian vault for persistent knowledge:
- `openclaw-brain-graph` — vault indexing, QMD search, MCP config
- `openclaw-brain-ingest` — ingest URLs, PDFs, transcripts
- `openclaw-brain-expand` — expand knowledge connections

### Provenance (Layer 5)

SHA-256 hash-chained receipts in `~/.openclaw/provenance/`:
- Every gated execution produces a receipt
- Receipts chain to previous (tamper detection)
- Read-only files (chmod 0o444)
- Verifiable: `openclaw-provenance verify --chain`

---

## Agent Spinup Integration

When spawning agents that need LACP context:

```bash
# Agent session with LACP project context
openclaw-memory-init ~/projects/easy-api agent-wren webchat

# This creates:
# ~/.openclaw/data/project-sessions/easy-api/agent-wren/{session-id}/
# with 5 seed files pre-loaded with project context
```

The `session-start` hook automatically injects this context when the agent session begins.

### Explicit Context Injection

For agents that need LACP knowledge mid-session:

```bash
# Query knowledge graph
openclaw-brain-graph query "payment processing flow"

# Load project memory
openclaw-brain-stack status --project easy-api
```

---

## Environment Configuration

### Config Resolution Order

1. Gateway config (`~/.openclaw/openclaw.json` → `plugins.entries.openclaw-lacp-fusion.config`)
2. Env file (`~/.openclaw/extensions/openclaw-lacp-fusion/config/.openclaw-lacp.env`)
3. Shell environment variables
4. Defaults from `openclaw.plugin.json` configSchema

### Key Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `OPENCLAW_HOME` | `~/.openclaw` | OpenClaw root directory |
| `OPENCLAW_HOOKS_PROFILE` | `balanced` | Active safety profile |
| `LACP_OBSIDIAN_VAULT` | `~/obsidian/vault` | Obsidian vault path |
| `LACP_KNOWLEDGE_ROOT` | `~/.openclaw/data/knowledge` | Knowledge graph data |
| `LACP_LOCAL_FIRST` | `true` | All data stays on-device |

### Cross-Machine Portability

The installer auto-detects paths per machine:
- Uses `~` (not hardcoded paths) everywhere
- Detects OS (macOS/Linux/WSL)
- Finds Obsidian vault location
- Generates `.openclaw-lacp.env` with detected values
- Override mechanism: edit the env file or set shell variables

---

## Validation

Run after install or any config change:

```bash
openclaw-lacp-validate
```

Checks:
- Plugin registered in gateway config
- All hook handlers present and syntactically valid
- Safety profiles present
- Bin scripts present and executable
- Data directories exist with correct permissions
- Obsidian vault accessible
- Optional tools (QMD, GitNexus) detected

Options:
- `--fix` — auto-resolve fixable issues
- `--verbose` — detailed output per check
- `--json` — machine-readable output

---

## Troubleshooting

### Plugin not loading after install
```bash
# Check registration
jq '.plugins.allow' ~/.openclaw/openclaw.json
jq '.plugins.entries["openclaw-lacp-fusion"]' ~/.openclaw/openclaw.json

# Restart gateway
openclaw gateway restart
```

### Hooks not firing
```bash
# Check profile
jq '.plugins.entries["openclaw-lacp-fusion"].config.profile' ~/.openclaw/openclaw.json

# Test hook handler directly
echo '{"event":"session_initialization"}' | python3 ~/.openclaw/extensions/openclaw-lacp-fusion/hooks/handlers/session-start.py
```

### Context not injecting
```bash
# Verify session-start hook is in active profile
# balanced and hardened-exec include it; minimal-stop does not

# Check handler syntax
python3 -c "import py_compile; py_compile.compile('$HOME/.openclaw/extensions/openclaw-lacp-fusion/hooks/handlers/session-start.py', doraise=True)"
```

### Gateway config corrupted
```bash
# Backups are created during install with timestamp suffix
ls ~/.openclaw/openclaw.json.bak.*

# Restore most recent
cp ~/.openclaw/openclaw.json.bak.TIMESTAMP ~/.openclaw/openclaw.json
```
