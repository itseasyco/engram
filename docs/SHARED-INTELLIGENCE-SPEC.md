# Shared Intelligence Graph — Architecture Spec

**Status:** Draft / Brainstorm
**Author:** Andrew + Claude
**Date:** 2026-03-21

---

## Vision

Turn the LACP knowledge vault from a single-machine local store into a **shared company intelligence graph** — a hivemind where every agent across the organization contributes knowledge, and every agent benefits from the collective intelligence.

An engineer's agent discovers a bug pattern → it's available to every other engineer's agent. A PM documents a feature plan → the dev agents already know about it when they start building. C-suite sets strategic direction → every agent in the org has context on why decisions are being made.

The backing infrastructure is **Obsidian Sync** (E2EE) with **obsidian-headless** (`ob`) providing server-side/CLI vault access on every node. No desktop app required.

---

## Core Concepts

### The Shared Vault

A single Obsidian vault (the "Company Brain") synced across all participating machines via Obsidian Sync. Every team member's OpenClaw agent reads from and writes to a local copy of this vault. obsidian-headless keeps all copies in sync continuously.

**Key properties:**
- **End-to-end encrypted** — Obsidian can't read your company data
- **Real-time sync** — `ob sync --continuous` watches for changes
- **Conflict-aware** — Obsidian Sync handles merge conflicts natively
- **Offline-capable** — agents work locally, sync catches up when online
- **No central server required** — Obsidian's cloud is the relay, but every node has a full local copy

### Agent Roles

Not all agents contribute the same way. The system recognizes different roles:

| Role | Writes to | Reads from | Examples |
|---|---|---|---|
| **Developer Agent** | `01_Projects/`, `02_Concepts/`, `05_Inbox/` | Everything | Wren, dev team agents |
| **PM Agent** | `06_Planning/`, `07_Research/`, `05_Inbox/` | Everything | Project manager's agent |
| **Executive Agent** | `08_Strategy/`, `05_Inbox/` | Everything | C-suite agents |
| **CI/CD Bot** | `09_Changelog/`, `05_Inbox/` | Nothing (write-only) | GitHub Actions |
| **Curator Agent** | Everything (organize/relink) | Everything | Dedicated maintenance agent |
| **Read-Only Observer** | Nothing | Everything | Dashboards, reporting tools |

### The Curator Agent

A dedicated agent (or cron job) whose sole purpose is maintaining the knowledge graph:

**Responsibilities:**
1. **Inbox processing** — classify new notes from `05_Inbox/` and move to correct folder
2. **Wikilink weaving** — find related notes and add `[[backlinks]]` between them
3. **Deduplication** — detect notes covering the same topic, merge or cross-reference
4. **Staleness detection** — identify notes not traversed in 90+ days, flag for review
5. **Orphan cleanup** — find notes with zero backlinks, connect them or archive
6. **Index maintenance** — keep `00_Index.md` and folder-level index files up to date
7. **Conflict resolution** — handle sync conflict files, merge or escalate
8. **Schema enforcement** — ensure all notes have required frontmatter (title, category, tags)
9. **Reporting** — weekly summary of graph health to the team (via Slack/email)

**How it runs:**
```bash
openclaw cron add \
  --every 2h \
  --agent curator \
  --description "Curate the shared knowledge graph" \
  --prompt "<curator-prompt-here>"
```

The curator prompt would be a detailed system prompt stored as a LACP skill or BOOT.md file, not an inline string.

---

## Vault Structure

```
Company Brain/
├── 00_Index.md                          ← Master index (curator-maintained)
│
├── 01_Projects/                         ← Per-repo/per-project knowledge
│   ├── easy-api/
│   │   ├── index.md                     ← Project overview, links to all notes
│   │   ├── architecture.md              ← Architecture decisions
│   │   ├── api-patterns.md              ← Discovered API patterns
│   │   ├── bug-patterns.md              ← Recurring bugs and fixes
│   │   └── onboarding.md                ← What a new dev needs to know
│   ├── easy-dashboard/
│   ├── easy-checkout/
│   └── easy-sdk/
│
├── 02_Concepts/                         ← Cross-project knowledge
│   ├── authentication-patterns.md
│   ├── database-migration-strategy.md
│   ├── error-handling-conventions.md
│   └── testing-philosophy.md
│
├── 03_People/                           ← Team context (opt-in)
│   ├── andrew.md                        ← Role, expertise, preferences
│   ├── niko.md
│   └── team-structure.md
│
├── 04_Systems/                          ← Infrastructure and architecture
│   ├── deployment-architecture.md
│   ├── payment-flow.md                  ← Finix → Brale → settlement
│   ├── auth-system.md                   ← Auth0 + Supabase Auth
│   └── monitoring.md                    ← Sentry, PostHog, Grafana
│
├── 05_Inbox/                            ← Unsorted incoming notes
│   ├── queue-agent/                     ← Agent-submitted (auto-classified by curator)
│   ├── queue-cicd/                      ← CI/CD-submitted PR summaries, deploy notes
│   ├── queue-human/                     ← Human-submitted (drag-and-drop, email)
│   └── review-stale/                    ← Curator-flagged notes needing human review
│
├── 06_Planning/                         ← Product planning
│   ├── roadmap-q2-2026.md
│   ├── feature-treasury-v2.md
│   ├── feature-mobile-app.md
│   └── user-research/
│       ├── interview-2026-03-15.md
│       └── survey-results-q1.md
│
├── 07_Research/                         ← Research findings
│   ├── competitor-analysis/
│   ├── technology-evaluations/
│   └── market-research/
│
├── 08_Strategy/                         ← Executive-level docs
│   ├── company-direction-2026.md
│   ├── hiring-plan.md
│   ├── fundraising-notes.md             ← (access-controlled)
│   └── partnerships/
│
├── 09_Changelog/                        ← Auto-generated from git/CI
│   ├── branches/                        ← Active feature branches
│   │   └── feat-treasury-send/
│   │       ├── PR-142.md
│   │       └── PR-145.md
│   ├── merged/                          ← Archived merged branches
│   │   └── feat-checkout-v2-20260315/
│   ├── releases/                        ← Release notes
│   │   ├── v2.1.0.md
│   │   └── v2.2.0.md
│   └── deploys/                         ← Deploy logs
│       ├── staging-20260321.md
│       └── production-20260320.md
│
├── 10_Templates/                        ← Note templates
│   ├── project-note.md
│   ├── meeting-note.md
│   ├── decision-record.md
│   ├── bug-report.md
│   └── pr-summary.md
│
└── .obsidian/                           ← Synced Obsidian config
    ├── plugins/                         ← Shared community plugins
    └── templates/
```

### Frontmatter Schema

Every note in the shared vault should have standardized frontmatter:

```yaml
---
title: "API Authentication Architecture"
category: systems              # maps to folder: 01-09
tags: [auth, auth0, supabase, security]
created: 2026-03-15
updated: 2026-03-21
author: wren                   # agent or human who created it
source: agent-promoted         # how it got here: agent-promoted, ci-cd, human, curator
project: easy-api              # associated project (optional)
status: active                 # active, review, stale, archived
last_traversed: 2026-03-21    # last time an agent injected this as context
traversal_count: 12            # how many times agents have used this
confidence: 0.85               # curator's confidence this is still accurate
---
```

---

## Node Architecture

### What runs on each machine

```
┌──────────────────────────────────────────────────┐
│                  Team Member's Machine             │
│                                                    │
│  ┌─────────────┐   ┌──────────────────────────┐  │
│  │  OpenClaw    │   │  obsidian-headless       │  │
│  │  Gateway     │   │  (ob sync --continuous)  │  │
│  │             │   │                          │  │
│  │  ┌─────────┐│   │  Watches local vault     │  │
│  │  │  LACP   ││   │  for changes, syncs      │  │
│  │  │  Plugin  ││   │  bidirectionally with    │  │
│  │  │         ││   │  Obsidian cloud           │  │
│  │  │ Reads/  ││   │                          │  │
│  │  │ writes  │├───┤  ~/.openclaw/vault/       │  │
│  │  │ vault   ││   │  (local copy of shared    │  │
│  │  └─────────┘│   │   Company Brain)          │  │
│  └─────────────┘   └──────────────────────────┘  │
│                                                    │
└──────────────────────────────────────────────────┘
          │                        │
          │                        │
          ▼                        ▼
   OpenClaw Cloud           Obsidian Sync Cloud
   (agent routing)          (vault sync, E2EE)
```

### Sync Modes

Different nodes may need different sync configurations:

| Node Type | Sync Mode | Rationale |
|---|---|---|
| Developer workstation | `bidirectional` | Reads and writes freely |
| CI/CD runner | `bidirectional` | Writes changelogs, reads templates |
| Curator server | `bidirectional` | Needs full read/write for reorganization |
| Read-only dashboard | `pull-only` | Only consumes, never modifies |
| Staging environment | `bidirectional` | Writes deploy status, reads configs |

Configure via: `ob sync-config --mode <mode>`

---

## Onboarding Flow: `openclaw-lacp-connect`

### How a new team member joins the hivemind

**Step 1: Admin (main agent) sends invite**
```bash
openclaw-lacp-connect invite \
  --email teammate@company.com \
  --role developer \
  --vault "Company Brain"
```

This:
- Generates a one-time invite token
- Emails the invite (via the agent's email) with setup instructions
- Optionally adds the user to the Obsidian vault's shared access list

**Step 2: Team member receives invite and connects**
```bash
openclaw-lacp-connect join --token <invite-token>
```

The `join` command:
1. Validates the invite token
2. Runs `ob login` (interactive — they enter their Obsidian credentials)
3. Runs `ob sync-setup --vault "Company Brain" --path ~/.openclaw/vault`
4. Starts `ob sync --continuous` as a background daemon (launchd on macOS, systemd on Linux)
5. Updates their LACP config to point `LACP_OBSIDIAN_VAULT` at `~/.openclaw/vault`
6. Sets their agent's role (developer/pm/executive) for write-path routing
7. Runs initial sync — pulls down the full vault
8. Confirms connection: "Connected to Company Brain (4,231 notes, last sync: 2s ago)"

**Step 3: Verify**
```bash
openclaw-lacp-connect status
```
Shows:
- Connection status (syncing/paused/disconnected)
- Vault name, note count, last sync time
- Agent role and write permissions
- Sync daemon status (pid, uptime)

### Other `openclaw-lacp-connect` commands

```bash
# List all connected members (admin only)
openclaw-lacp-connect members

# Disconnect from shared vault
openclaw-lacp-connect disconnect

# Pause sync (keep local copy)
openclaw-lacp-connect pause

# Resume sync
openclaw-lacp-connect resume

# Change role
openclaw-lacp-connect set-role --role pm

# Check sync health
openclaw-lacp-connect health
```

---

## CI/CD Integration

### GitHub Action: PR → Vault

When a PR is opened, updated, or merged, a GitHub Action generates a vault note and syncs it.

**What gets generated per PR:**
```markdown
---
title: "PR #142: feat: add treasury send flow"
category: changelog
tags: [easy-api, treasury, finix, brale]
created: 2026-03-21
author: ci-cd
source: ci-cd
project: easy-api
branch: feat/treasury-send
pr_number: 142
pr_status: open
---

# PR #142: feat: add treasury send flow

## Summary
Added the treasury send flow for processing outbound payments
via Finix → Brale → stablecoin conversion.

## Files Changed (12)
- `src/routes/treasury/send.ts` (new)
- `src/services/brale/payout.ts` (modified)
- `src/models/transfer.ts` (modified)
...

## Key Decisions
- Used RTP for same-day settlement instead of ACH
- Added retry logic with exponential backoff for Brale API

## Test Coverage
- 8 new tests added
- All existing tests pass

## Links
- [[easy-api]] | [[treasury]] | [[payment-flow]]
```

### Branch Lifecycle in the Vault

```
Branch created (push)
  → 09_Changelog/branches/feat-treasury-send/ created
  → index.md generated with branch metadata

PR opened
  → PR-142.md created in branch folder

PR updated (new commits)
  → PR-142.md updated with latest diff summary

PR merged
  → Branch folder moved to 09_Changelog/merged/feat-treasury-send-20260321/
  → PR note updated with merge metadata
  → Curator agent cross-links to project notes

Branch deleted
  → (handled by merge step above, or archived if deleted without merge)

Deploy to staging
  → 09_Changelog/deploys/staging-20260321.md created
  → Links to all PRs included in this deploy

Deploy to production
  → 09_Changelog/releases/v2.2.0.md created
  → Full release notes aggregated from merged PRs
```

### Environment-Aware Documentation

Each environment gets its own view of what's current:

```
09_Changelog/
├── environments/
│   ├── staging.md              ← "What's on staging right now"
│   │                              Auto-updated on each deploy
│   ├── production.md           ← "What's in production"
│   └── feature-branches.md    ← "Active feature work"
```

These files are auto-generated and always current — any team member's agent can read them to understand the current state of any environment.

---

## Staleness Detection & Invalidation

### How it works

Every time a note's fact is injected into an agent's context (via `session-start` hook), the `last_traversed` timestamp and `traversal_count` in the frontmatter are updated. This happens in `_store_injection_metadata()` in `session-start.py`.

The curator agent runs staleness checks on a schedule:

**Staleness scoring:**
```
staleness_score = days_since_traversed / (traversal_count + 1)
```

- Score < 10: **Active** — recently and frequently used
- Score 10-30: **Aging** — used but not recently
- Score 30-90: **Stale** — may be outdated
- Score > 90: **Review needed** — curator flags for human review

**What the curator does with stale notes:**

1. **Score 30-90 (stale):** Adds a `⚠️ This note may be outdated` banner to the note. Checks if the note's content contradicts anything in more recent notes. If contradictions found, creates a merge/review task.

2. **Score > 90 (review needed):** Moves to `05_Inbox/review-stale/`. Sends a message to the original author's agent: "Is this still accurate?" If no response in 14 days, archives to `99_Archive/`.

3. **Code-related notes:** Cross-references with git history. If the files mentioned in a note have been significantly modified since the note was written, the curator flags it as potentially outdated and includes the relevant diff summary.

### Proactive invalidation triggers

Beyond time-based staleness, certain events should trigger immediate review:

- **Major refactor merged** → curator scans `02_Concepts/` for affected patterns
- **Dependency upgraded** → curator checks `04_Systems/` for affected architecture docs
- **Team member leaves** → curator reviews their authored notes for handoff
- **Strategic pivot** → executive updates `08_Strategy/`, curator propagates to affected planning docs

---

## Access Control

### Current approach: Convention-based

Since Obsidian Sync doesn't have per-folder ACLs, access control is enforced by convention + the agent's role configuration:

- Each agent's role determines which folders it writes to (enforced by the LACP plugin, not by Obsidian)
- The pretool-guard could be extended with vault-write rules: "agents with role=developer cannot write to 08_Strategy/"
- The curator agent reviews all writes and can revert unauthorized changes

### Future approach: Obsidian Publish for read-only

For truly sensitive docs (fundraising, legal), you could:
- Keep them in a separate vault
- Use Obsidian Publish for read-only access
- Or use a separate "executive" shared vault with restricted membership

### Conflict Resolution

When two agents edit the same note simultaneously:

1. **Obsidian Sync detects conflict** → creates a conflict file (e.g., `note (conflict 2026-03-21).md`)
2. **Curator agent detects conflict files** on next run
3. **Curator merges or escalates:**
   - If changes are to different sections → auto-merge
   - If changes contradict → create a review task with both versions
   - If one is clearly newer context → prefer the newer version, archive the older

---

## Multi-Vault Topology (Advanced)

For larger organizations, a single vault may not scale. Consider:

```
                    ┌──────────────┐
                    │ Company Brain │ ← Master vault (curator-managed)
                    │ (read-heavy)  │
                    └───────┬──────┘
                            │
              ┌─────────────┼─────────────┐
              │             │             │
     ┌────────▼──────┐ ┌───▼────────┐ ┌──▼──────────┐
     │ Engineering   │ │ Product    │ │ Executive   │
     │ Vault         │ │ Vault      │ │ Vault       │
     │ (read-write)  │ │ (r/w)      │ │ (restricted)│
     └───────────────┘ └────────────┘ └─────────────┘
```

The curator agent syncs summaries from child vaults into the master vault. Each team has full read-write in their vault, and read access to the master. This avoids conflict storms from too many writers.

---

## Performance Considerations

- **Vault size:** Obsidian handles vaults with 10,000+ notes well. At 100 team members × 10 notes/day, that's ~365,000 notes/year. May need archival strategy after year 1.
- **Sync latency:** obsidian-headless `--continuous` mode detects changes within seconds. For most use cases, this is fast enough. For real-time collaboration (two agents editing simultaneously), conflicts are possible.
- **Agent context injection:** `session-start` hook queries the vault for relevant facts. With a large vault, this needs efficient indexing — QMD vector embeddings or a local SQLite index.
- **ob sync bandwidth:** E2EE means full file contents are synced (no diffing at the server). Large vaults with frequent changes could use meaningful bandwidth. Consider `--excluded-folders` for heavy media content.

---

## Implementation Phases

### Phase 1: Foundation (build first)
- `openclaw-lacp-connect` CLI tool (invite, join, status, disconnect)
- `ob sync --continuous` daemon management (start/stop/status)
- Shared vault folder structure + frontmatter schema
- Role-based write routing in the LACP plugin
- Update `session-start.py` to update traversal metadata

### Phase 2: CI/CD Integration
- GitHub Action template for PR/branch/deploy → vault notes
- Branch lifecycle management (create/merge/delete → vault ops)
- Environment status notes (staging.md, production.md)
- PR summary note generation from diff + commit messages

### Phase 3: Curator Agent
- Curator agent prompt/skill design
- Inbox processing automation
- Wikilink weaving algorithm
- Staleness detection + scoring
- Orphan/broken link detection
- Conflict file resolution
- Weekly health report generation

### Phase 4: Advanced Features
- Multi-vault topology for larger orgs
- Real-time presence (which agents are active)
- Knowledge graph visualization (Obsidian graph view via Publish)
- Smart routing: curator auto-classifies which vault/folder based on content
- Proactive invalidation triggers (refactor detection, dependency changes)
- Cross-vault search via QMD embeddings

---

## Open Questions

1. **Obsidian Sync pricing for teams** — does the current plan support enough shared vault members? What's the per-seat cost?

2. **obsidian-headless stability** — it's in open beta. How reliable is `--continuous` mode for always-on daemon use? Do we need a watchdog/restart mechanism?

3. **Plugin compatibility** — obsidian-headless syncs `.obsidian/` config including community plugins. If one team member installs a plugin that modifies vault structure, does it affect everyone?

4. **Vault encryption password management** — E2EE requires a shared password. How do we distribute this securely to new team members during the invite flow?

5. **Git vs Obsidian Sync** — for the CI/CD integration, should the GitHub Action use `ob sync` (requires Obsidian credentials on the runner) or a git-based vault (simpler but no real-time sync)? Could do both: git for CI/CD writes, ob sync for agent reads.

6. **Offline behavior** — if a team member is offline for days and their agent makes many vault changes, will the sync catch up cleanly? What about very large batch syncs?

7. **GDPR/compliance** — if the vault contains employee data (`03_People/`), what are the data handling requirements? Obsidian Sync is E2EE so Obsidian can't access it, but local copies exist on every synced machine.

8. **Vault backup strategy** — Obsidian Sync has version history, but should we also run periodic git backups of the vault as a safety net?

---

## Success Metrics

- **Knowledge graph density:** Average backlinks per note (target: 3+)
- **Staleness ratio:** % of notes with staleness_score > 90 (target: < 5%)
- **Agent utilization:** % of sessions where facts from shared vault were injected (target: > 70%)
- **Time to knowledge:** How quickly a new fact (e.g., PR merged) is available in all agents' context (target: < 5 minutes)
- **Curator efficiency:** % of inbox notes auto-classified correctly (target: > 85%)
- **Zero-context starts:** % of new sessions where the agent had useful pre-loaded context (target: > 90%)
