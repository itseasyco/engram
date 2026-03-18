# OpenClaw Policy System — Configuration Guide

## Overview

The OpenClaw policy system provides three-tier access control for agent execution:
1. **Safe** — Known low-risk operations, no approval needed
2. **Review** — Semi-trusted operations, requires TTL-based approval
3. **Critical** — High-risk operations, requires explicit confirmation

## Policy Configuration

Policies are defined in `~/.openclaw-test/config/policy/risk-policy.json`

### Structure

```json
{
  "tiers": {
    "TIER_NAME": {
      "description": "Human-readable description",
      "cost_ceiling_usd": NUMBER,
      "approval_required": BOOLEAN,
      "approval_ttl_minutes": NUMBER (optional, for review tier),
      "confirmation_required": BOOLEAN (optional, for critical tier)
    }
  },
  "rules": [
    {
      "pattern": "PATTERN_STRING",
      "tier": "TIER_NAME",
      "reason": "HUMAN_DESCRIPTION"
    }
  ],
  "defaults": {
    "tier": "TIER_NAME",
    "reason": "Default policy reason"
  }
}
```

### Tier Definitions

#### Safe Tier
- **Cost ceiling:** $1.00 USD
- **Approval required:** No
- **Use case:** Local operations by control agents
- **Example:** Git commits in local context

#### Review Tier
- **Cost ceiling:** $10.00 USD
- **Approval required:** Yes (TTL: 30 minutes)
- **Use case:** Semi-trusted operations in shared channels
- **Example:** NPM install by engineering agent in #bridge

#### Critical Tier
- **Cost ceiling:** $100.00 USD
- **Approval required:** Yes (explicit confirmation)
- **Confirmation required:** Yes
- **Use case:** High-risk production operations
- **Example:** Database migrations in production

### Pattern Matching

Patterns match agent + channel/context combinations:

```
agent:AGENT_ID,channel:CHANNEL_NAME
agent:AGENT_ID,context:CONTEXT_TYPE
channel:CHANNEL_NAME
context:CONTEXT_TYPE
```

**Example patterns:**
- `agent:zoe,channel:bridge` — Zoe in #bridge channel
- `agent:wren,context:local` — Wren in local context
- `channel:production` — Any agent in production
- `context:external` — Any external context

### Current Rules

The default policy includes:
1. `agent:zoe,channel:bridge` → **review** (engineering agent in shared space)
2. `agent:wren,context:local` → **safe** (control agent in local)
3. `agent:main,context:local` → **safe** (main agent in local)
4. `context:external` → **critical** (external always critical)
5. `channel:production` → **critical** (production always critical)
6. Default → **review** (catch-all, requires approval)

## Adding New Rules

### 1. Edit the Policy Config

```bash
nano ~/.openclaw-test/config/policy/risk-policy.json
```

### 2. Add a New Rule

```json
{
  "pattern": "agent:NEW_AGENT,channel:NEW_CHANNEL",
  "tier": "safe",
  "reason": "Your reason here"
}
```

### 3. Test the Route

```bash
~/.openclaw-test/bin/openclaw-route "NEW_AGENT" "NEW_CHANNEL" "test task"
```

Expected output:
```json
{
  "tier": "safe",
  "cost_ceiling_usd": 1.0,
  "approval_required": false,
  "reason": "Your reason here"
}
```

## Using Gated Execution

### Safe Task (No Approval)

```bash
~/.openclaw-test/bin/openclaw-gated-run \
  --task "my task" \
  --agent "wren" \
  --channel "local" \
  --estimated-cost-usd 0.50 \
  -- git commit -m "test"
```

✅ Executes immediately (no approval needed)

### Review Task (TTL Approval)

```bash
~/.openclaw-test/bin/openclaw-gated-run \
  --task "my task" \
  --agent "zoe" \
  --channel "bridge" \
  --estimated-cost-usd 5.00 \
  -- npm install
```

⚠️ Prompts for approval (30-minute TTL)

### Critical Task (Explicit Confirmation)

```bash
~/.openclaw-test/bin/openclaw-gated-run \
  --task "database migration" \
  --agent "admin" \
  --channel "production" \
  --estimated-cost-usd 50.00 \
  --confirm-budget \
  -- ./migrate.sh
```

🔒 Requires `--confirm-budget` flag + explicit approval

## Cost Ceiling Enforcement

Each tier has a maximum estimated cost. If your task exceeds the ceiling:

1. **Safe tier ($1):** Task will fail unless cost is within limit
2. **Review tier ($10):** Task will fail unless approval is granted
3. **Critical tier ($100):** Task requires `--confirm-budget` flag AND approval

To override:
```bash
~/.openclaw-test/bin/openclaw-gated-run \
  --task "expensive operation" \
  --agent "wren" \
  --channel "local" \
  --estimated-cost-usd 2.00 \
  --confirm-budget \
  -- ./expensive_task.sh
```

## Approval Cache & TTL

When you approve a task, it's cached for 30 minutes (review tier):

```
~/.openclaw-test/data/approval-cache.json
```

Example:
```json
{
  "approvals": [
    {
      "key": "zoe:bridge:npm install",
      "approved_at": 1710000000,
      "expires_at": 1710001800,
      "approver": "user-interactive"
    }
  ]
}
```

The same task within 30 minutes will use the cached approval.

## Monitoring & Logging

All gated executions are logged to:
```
~/.openclaw-test/logs/gated-runs.jsonl
```

Each entry contains:
- Timestamp
- Agent & channel
- Task description
- Tier
- Cost
- Duration
- Gates passed/blocked

View recent executions:
```bash
cat ~/.openclaw-test/logs/gated-runs.jsonl | jq -c '.'
```

## Troubleshooting

### Task blocked by policy?

1. Check the routing decision:
   ```bash
   ~/.openclaw-test/bin/openclaw-route "AGENT" "CHANNEL" "TASK"
   ```

2. If tier is not what you expected, add a matching rule to `risk-policy.json`

3. For review/critical tasks, you'll need approval. Approve at the prompt or provide cached approval.

### Cost ceiling exceeded?

Use the `--confirm-budget` flag:
```bash
~/.openclaw-test/bin/openclaw-gated-run \
  ... \
  --confirm-budget \
  -- <command>
```

### Approval cache expired?

Re-run the gated command and approve again. Cache TTL is 30 minutes.

## Best Practices

1. **Keep safe tier narrow** — Only local, low-risk operations
2. **Use review tier for shared spaces** — Engineering channels, staging
3. **Always use critical tier for production** — Use pattern `channel:production`
4. **Monitor cost ceilings** — Adjust if operations regularly exceed limits
5. **Document reasons** — Explain why each rule exists

## See Also

- [ROUTING-REFERENCE.md](ROUTING-REFERENCE.md) — Technical routing logic
- [Phase 1 Integration Tests](../tests/test_phase1_phase2_integration.sh) — Test suite
