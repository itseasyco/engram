# Complete 5-Layer Workflow Example

This document shows a realistic workflow using all 5 memory layers together.

## Scenario: Agent improving a payment processing system

### Setup (One-time)

```bash
# 1. Initialize knowledge graph for project
openclaw-brain-graph init ~/easy-api --vault /Volumes/Cortex/easy-api-vault

# 2. Verify vault structure
openclaw-brain-graph status /Volumes/Cortex/easy-api-vault --details
# Output:
# Vault: easy-api-vault
# Total Files: 6
# Git History: ✓
# Directories: inbox, projects, agents, patterns, decisions, references
```

### Session Start

```bash
# 1. Create new session with all 5 seed files (Layer 1)
SESSION_DIR=$(openclaw-memory-init ~/easy-api agent-a discord)
echo $SESSION_DIR
# Output: /Users/andrew/.openclaw-test/data/project-sessions/easy-api/agent-a/1710787800

# 2. Verify session created with all 5 files
ls -la $SESSION_DIR/
# Output:
# -rw-r--r--  MEMORY.md
# -rw-r--r--  debugging.md
# -rw-r--r--  patterns.md
# -rw-r--r--  architecture.md
# -rw-r--r--  preferences.md
# -rw-r--r--  context.json
# drwxr-xr-x  .git
```

### Session Work

```bash
# 1. Agent edits MEMORY.md to document context
cat >> $SESSION_DIR/MEMORY.md << 'EOF'

## Current Session — 2026-03-18

### Problem
Payment processing occasionally fails with timeout errors in high-load scenarios.

### Investigation Goal
- Understand current payment flow architecture
- Identify bottlenecks
- Design timeout mitigation strategy

### Related Issues
- #523: Payment timeouts under load
- #506: Rate limiting not properly enforced

EOF

# 2. Agent documents patterns found
cat >> $SESSION_DIR/patterns.md << 'EOF'

### Payment Processing Pattern

The codebase uses a request/response pattern:

1. **Validation** — Input validation in `PaymentValidator.py`
2. **Processing** — Core processing in `PaymentProcessor.py`
3. **Settlement** — Settlement via Stripe in `StripeGateway.py`
4. **Audit** — Logging in `AuditLogger.py`

**Key insight:** Settlement (Step 3) is not async, causing blocking.

EOF

# 3. Ingest decision-making transcript (Layer 3)
cat > /tmp/design-review.txt << 'EOF'
Speaker: Engineering Lead
Date: 2026-03-18

We discussed making settlement async using Celery tasks. Key points:

1. Current: Settlement is synchronous, blocks payment response
2. Proposed: Queue settlement task, return success immediately
3. Concern: Double-charging if task retries after timeout
4. Solution: Idempotency key in settlement request
5. Action: Implement async settlement with idempotency

EOF

openclaw-brain-ingest transcript /Volumes/Cortex/easy-api-vault /tmp/design-review.txt \
  --speaker "Engineering Lead" \
  --date "2026-03-18"
# Output: Ingested: /Volumes/Cortex/easy-api-vault/inbox/queue-generated/transcript_a1b2c3d4.md

# 4. Ingest relevant research paper (Layer 3)
openclaw-brain-ingest url /Volumes/Cortex/easy-api-vault \
  "https://stripe.com/docs/api/idempotent_requests" \
  --title "Stripe Idempotency Documentation" \
  --tags "stripe,idempotency,safety"
# Output: Ingested: /Volumes/Cortex/easy-api-vault/inbox/queue-generated/url_c3d4e5f6.md

# 5. Analyze codebase to understand impact (Layer 4)
openclaw-brain-code analyze ~/easy-api --output analysis.json

# 6. Check impact of changes to payment processor
openclaw-brain-code impact ~/easy-api "src/payments/processor.py" --scope
# Output:
# {
#   "file": "src/payments/processor.py",
#   "symbols_in_file": ["PaymentProcessor", "validate", "process", "settle"],
#   "dependent_files": ["src/webhooks/stripe.py", "src/api/v1/payments.py"],
#   "affected_symbols": ["PaymentProcessor", "handle_webhook", "POST /payments"],
#   "impact_radius": {
#     "files": 2,
#     "symbols": 3
#   }
# }

# 7. Get call chain for affected functions
openclaw-brain-code calls ~/easy-api "PaymentProcessor.settle" --depth 2
# Output:
# {
#   "symbol": "PaymentProcessor.settle",
#   "callers": ["PaymentProcessor.process", "SettlementTask.execute"],
#   "callees": ["StripeGateway.create_charge", "AuditLogger.log"]
# }
```

### Index Knowledge Graph

```bash
# 1. Index session seed files into graph (Layer 2)
openclaw-brain-graph index $SESSION_DIR --update-qmd
# Output:
# ✓ Created Obsidian vault structure
# ✓ Indexed: agent-a-MEMORY.md
# ✓ Indexed: agent-a-debugging.md
# ✓ Indexed: agent-a-patterns.md
# ✓ Indexed: agent-a-architecture.md
# ✓ Indexed: agent-a-preferences.md
# ✓ Committed to vault git history
# ✓ QMD indices updated

# 2. Verify index
openclaw-brain-ingest index /Volumes/Cortex/easy-api-vault --qmd
# Output: Indexed: /Volumes/Cortex/easy-api-vault/inbox/queue-generated/index.md

# 3. Search the graph for related work
openclaw-brain-graph query $SESSION_DIR "payment timeout async" --limit 5
# Output: (From previous similar sessions/issues)
# - Async Payment Processing (session from 2 weeks ago)
# - Celery Task Queue Setup (previous agent's notes)
# - Idempotency Implementation (reference)
```

### Implementation (with code intelligence)

```bash
# 1. Get call chain for the function being modified
openclaw-brain-code calls ~/easy-api "PaymentProcessor.settle" --depth 3
# Output: Shows all functions that might be affected

# 2. Use impact analysis to understand test scope
openclaw-brain-code impact ~/easy-api "src/payments/processor.py"
# Output: Shows 2 dependent files need testing

# 3. Document findings in architecture.md
cat >> $SESSION_DIR/architecture.md << 'EOF'

## Payment Processing Architecture

### Current Flow (Synchronous)
```
POST /payments
  → PaymentValidator.validate()
  → PaymentProcessor.process()
    → StripeGateway.create_charge()  [BLOCKING]
  ← Return response
```

### Proposed Flow (Async)
```
POST /payments
  → PaymentValidator.validate()
  → PaymentProcessor.queue_settlement()
  ← Return immediate success
  
[Background Task]
  → SettlementTask.execute()
  → StripeGateway.create_charge()
  → AuditLogger.log()
```

### Impact
- Files affected: src/webhooks/stripe.py, src/api/v1/payments.py
- Symbols affected: PaymentProcessor, handle_webhook, POST /payments endpoint
- Tests needed: 12+ in payment processing, 4+ in webhook handling

EOF
```

### Completion & Audit Trail

```bash
# 1. Create provenance receipt (Layer 5)
AGENT_ID=$(openclaw-agent-id get easy-api --create)
echo $AGENT_ID
# Output: easy-api-mac-mini-a1b2c3d4-260318

# 2. Get previous receipt hash for chaining
PREV_HASH=$(openclaw-provenance chain easy-api | jq -r '.[-1].receipt_hash' 2>/dev/null || echo "genesis")

# 3. Create new receipt linking to previous
openclaw-provenance receipt $SESSION_DIR $AGENT_ID --prev-hash $PREV_HASH --output receipt.json

# 4. Store receipt (immutable)
mkdir -p ~/.openclaw-test/provenance/easy-api
RECEIPT_ID=$(jq -r '.receipt_hash | .[0:16]' receipt.json)
cp receipt.json ~/.openclaw-test/provenance/easy-api/$RECEIPT_ID.json
chmod 0o444 ~/.openclaw-test/provenance/easy-api/$RECEIPT_ID.json

# 5. Record execution results (Layer 1)
openclaw-memory-append $SESSION_DIR \
  --cost 2.50 \
  --exit-code 0 \
  --learning "Identified async settlement as solution for timeouts" \
  --learning "Idempotency keys required to prevent double-charging" \
  --learning "Impact affects 2 files and 3 core symbols" \
  --gate "Code review: approved" \
  --gate "Architecture review: approved"
# Output:
# ✓ Updated context.json
# ✓ Appended to MEMORY.md
# ✓ Committed to git

# 6. Verify audit trail integrity
openclaw-provenance chain easy-api --verify
# Output:
# Chain status: valid
# Receipts: 5
# (All hashes match, no tampering detected)

# 7. Export audit trail for compliance
openclaw-provenance export easy-api audit-trail.json
```

### Next Session (Agent B)

```bash
# Agent B can now retrieve all learnings:

# 1. Get Agent A's session
SESSION_A=~/.openclaw-test/data/project-sessions/easy-api/agent-a/1710787800

# 2. Search the knowledge graph for related work
openclaw-brain-graph query $SESSION_A "payment timeout async idempotency"
# Output: (Rich context from Agent A's work)

# 3. Read Agent A's documented decisions
cat $SESSION_A/MEMORY.md
# Output:
# # Project Memory — easy-api
# 
# ## Current Session — 2026-03-18
# 
# ### Problem
# Payment processing occasionally fails with timeout errors...
# 
# ### Solution Identified
# Async settlement with idempotency keys
# ...

# 4. Check impact analysis from Layer 4
openclaw-brain-code impact ~/easy-api "src/payments/processor.py"
# Output: (Same analysis as Agent A computed)

# 5. Verify audit trail
openclaw-provenance chain easy-api --verify
# Output: Chain is valid, all 5 receipts intact, no tampering
```

---

## Complete Workflow Summary

### Layer 1: Session Memory
```
Agent A creates session → Fills 5 seed files → Documents findings
                                             → Git tracks changes
```

### Layer 2: Knowledge Graph
```
Seed files → Indexed into Obsidian vault → Searchable via QMD
                                         → Accessible to future agents
```

### Layer 3: Ingestion
```
Transcripts → Structured notes → Indexed in vault
URLs        → with metadata   → Searchable
PDFs
Files
```

### Layer 4: Code Intelligence
```
Codebase → AST analysis → Symbol extraction
        → Call graphs → Impact analysis
        → Help inform decisions
```

### Layer 5: Provenance
```
Session start → Create receipt → Chain to previous
Session end → Verify chain → Export audit trail
             → Tamper detection → Compliance ready
```

---

## Key Insights from This Workflow

1. **Knowledge Accumulation**: Agent B benefits from Agent A's analysis without repeating work
2. **Impact Analysis**: Code intelligence helps estimate risk and scope
3. **Tamper Detection**: Hash chain catches any modifications to session records
4. **Cross-Layer Synergy**: All 5 layers work together naturally
5. **Decision Continuity**: Future agents understand the "why" behind decisions

---

## Performance Metrics

| Layer | Time | Size | Items |
|-------|------|------|-------|
| 1 | 0.1s | 45KB | 5 files |
| 2 | 0.5s | 125KB | 50+ notes |
| 3 | 0.3s | 85KB | 3 ingested |
| 4 | 2.1s | 250KB | 47 symbols |
| 5 | 0.2s | 12KB | 1 receipt |
| **Total** | **3.2s** | **517KB** | **100+** |

---

## Troubleshooting This Workflow

### "QMD search returns no results"
```bash
# Re-index the vault
openclaw-brain-ingest index /Volumes/Cortex/easy-api-vault --qmd
```

### "Provenance chain broken"
```bash
# Verify integrity
openclaw-provenance chain easy-api --verify
# Check receipt file permissions
ls -la ~/.openclaw-test/provenance/easy-api/*.json
```

### "Code analysis shows wrong impact"
```bash
# Re-analyze with fresh results
rm analysis.json
openclaw-brain-code analyze ~/easy-api --output analysis.json
```

---

## Next Steps for Production Use

1. **Automate Session Creation**: Create wrapper script for `openclaw-memory-init`
2. **Scheduled Indexing**: Cron job for `openclaw-brain-graph index --update-qmd`
3. **Monitoring**: Track provenance chain integrity daily
4. **Governance**: Document which teams own which projects
5. **Training**: Onboard teams on 5-layer workflow

---

**Total Session Cost: $2.50**
**Knowledge Value: Priceless**
**Audit Trail: Tamper-Proof**
