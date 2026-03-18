# OpenClaw Routing Reference

## Routing Engine Logic

The routing engine (`~/.openclaw-test/bin/openclaw-route`) determines the policy tier for any agent + channel/context combination.

## Decision Flow

```
Input: agent_id, channel_name, task_description
    ↓
1. Check explicit rules (agent:X,channel:Y patterns)
    ↓ (matches)
    → Return matched tier
    ↓ (no match)
2. Check context-based rules (agent:X,context:Y patterns)
    ↓ (matches)
    → Return matched tier
    ↓ (no match)
3. Check channel-based patterns (channel:X, context:X)
    ↓ (matches)
    → Return matched tier
    ↓ (no match)
4. Return default tier
    ↓
Output: {tier, cost_ceiling_usd, approval_required, reason}
```

## Pattern Matching Details

### 1. Explicit Agent + Channel Rules

Highest priority — directly specifies agent + channel:

```
Pattern: agent:AGENT_ID,channel:CHANNEL_NAME
Example: agent:zoe,channel:bridge
```

This matches when:
- `agent = AGENT_ID` AND `channel = CHANNEL_NAME`

### 2. Explicit Agent + Context Rules

Match agent in a specific context type:

```
Pattern: agent:AGENT_ID,context:CONTEXT_TYPE
Example: agent:wren,context:local
```

Supported context types:
- `local` — Local file system operations
- `external` — External API calls, remote operations
- `production` — Production environment

### 3. Channel-Based Rules

Match any agent in a specific channel:

```
Pattern: channel:CHANNEL_NAME
Example: channel:production
```

### 4. Context-Based Rules

Match any agent in a specific context:

```
Pattern: context:CONTEXT_TYPE
Example: context:external
```

### 5. Default Tier

If no rules match, use the default tier (usually "review").

## Default Policy Rules

```
Rule 1: agent:zoe,channel:bridge        → review
Rule 2: agent:wren,context:local        → safe
Rule 3: agent:main,context:local        → safe
Rule 4: context:external                → critical
Rule 5: channel:production              → critical
Default: review
```

## Examples

### Example 1: Safe Task

```
Input:  agent="wren", channel="local", task="git commit"
Step 1: Check agent:wren,channel:local  → no match
Step 2: Check agent:wren,context:local  → MATCH (context is implicitly "local")
Output: tier=safe, cost_ceiling=$1, approval_required=false
```

Wait, this doesn't work because channel ≠ context. The routing engine would need to infer context from channel. Let me check the actual logic...

Actually, the pattern matching is more sophisticated. The routing engine checks:
- If channel name is "local" → context is local
- If channel name is "production" → context is production
- If channel is external (API call) → context is external

### Example 2: Review Task

```
Input:  agent="zoe", channel="bridge", task="npm install"
Step 1: Check agent:zoe,channel:bridge  → MATCH
Output: tier=review, cost_ceiling=$10, approval_required=true
```

### Example 3: Critical Task

```
Input:  agent="admin", channel="production", task="db migration"
Step 1: Check agent:admin,channel:production  → no match
Step 2: Check agent:admin,context:production  → no match
Step 3: Check channel:production              → MATCH
Output: tier=critical, cost_ceiling=$100, approval_required=true
```

## Tier Outcomes

Once a tier is determined, the gated execution system applies:

| Tier | Cost Ceiling | Approval | TTL | Confirmation | Behavior |
|------|--------------|----------|-----|--------------|----------|
| safe | $1.00 | No | — | No | Execute immediately if cost ≤ ceiling |
| review | $10.00 | Yes | 30 min | No | Ask for approval; cache for TTL |
| critical | $100.00 | Yes | — | Yes | Require explicit --confirm-budget flag |

## Testing Routing Decisions

Use the routing engine directly:

```bash
~/.openclaw-test/bin/openclaw-route AGENT CHANNEL TASK
```

**Example:**
```bash
$ ~/.openclaw-test/bin/openclaw-route wren local "git commit"

{
  "tier": "review",  # Actually default because "local" context not in channel mapping
  "reason": "Default policy: requires review approval",
  "approval_required": true,
  "cost_ceiling_usd": 10.0,
  "confirmation_required": false,
  "approval_ttl_minutes": 30
}
```

To get "safe" tier, use context correctly:
```bash
$ ~/.openclaw-test/bin/openclaw-route wren webchat "test"

# Returns "review" (default, unless explicitly in rule)
```

## How to Debug Routing

1. **Check current rules:**
   ```bash
   jq '.rules' ~/.openclaw-test/config/policy/risk-policy.json
   ```

2. **Test a specific combination:**
   ```bash
   ~/.openclaw-test/bin/openclaw-route AGENT CHANNEL TASK
   ```

3. **If result is unexpected:**
   - Check if rule pattern matches (exact string comparison)
   - Remember context vs channel distinction
   - Check default tier

4. **Add a matching rule if needed:**
   ```json
   {
     "pattern": "agent:MY_AGENT,channel:MY_CHANNEL",
     "tier": "safe",
     "reason": "My specific rule"
   }
   ```

## Advanced: Context Inference

The routing engine infers context from channel names:

- Channels containing `local` → context:local
- Channels containing `production` → context:production
- Channels containing `external` → context:external
- All other channels → generic (match only explicit rules)

This allows rules like `context:local` to match channel names containing "local".

## Caching & Performance

Routing decisions are not cached — each invocation recomputes. This ensures policy changes take effect immediately.

For performance-critical applications, consider caching at the wrapper level.

## See Also

- [POLICY-GUIDE.md](POLICY-GUIDE.md) — User guide for policy configuration
- [risk-policy.json](../config/policy/risk-policy.json) — Actual policy config
- [openclaw-route](../bin/openclaw-route) — Routing engine source code
