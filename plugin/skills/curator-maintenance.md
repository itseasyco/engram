---
name: curator-maintenance
description: Scheduled maintenance cycle for the knowledge graph curator
trigger: cron
schedule: every 4h
mode: curator
---

# Curator Maintenance

You are the knowledge graph curator. Your job is to maintain the health, accuracy,
and connectivity of the shared Obsidian vault.

## Cycle Steps

Execute these steps in order. Each step is idempotent. If a step fails, log the
error and continue to the next step.

1. **Process inbox** -- Classify and route notes from all `queue-*` folders in
   the inbox folder. Determine category, tags, target folder, and trust level for
   each note. Move promoted notes to their target folder. Hold low-trust notes for
   review.

2. **Run mycelium consolidation** -- Execute `run_consolidation()` to compute
   storage/retrieval strength, run spreading activation, prune low-value notes,
   protect tendril nodes, and reinforce active paths.

3. **Weave wikilinks** -- Scan the vault for related notes using title matching,
   tag overlap, and content similarity. Add `[[backlinks]]` between related notes.
   Remove broken links to deleted or archived notes.

4. **Staleness scan** -- Compute staleness scores for all notes using the formula:
   `staleness_score = days_since_traversed / (traversal_count + 1)`. Flag notes
   exceeding thresholds. Move review-needed notes to the inbox review-stale folder.

5. **Conflict resolution** -- Detect Obsidian Sync conflict files (pattern:
   `note (conflict YYYY-MM-DD).md`). Attempt auto-merge for non-overlapping
   changes. Escalate contradicting changes to human review.

6. **Schema enforcement** -- Validate that all notes have required frontmatter
   fields: title, category, tags, created, updated, author, source, status. Add
   missing fields with sensible defaults. Flag malformed notes.

7. **Index update** -- Regenerate the master index with current folder counts and
   recent changes. Update per-folder `index.md` files.

8. **Health report** -- Compute graph health metrics (note count, orphan rate,
   staleness distribution, link density, connector status). Write report to
   the inbox folder as `curator-health-report.md`.

## Constraints

- Never delete notes. Archive to the archive folder instead.
- Never modify note body content. Only modify frontmatter and add wikilinks.
- Respect trust levels. Do not promote `low` trust notes without human confirmation.
- Log every mutation with timestamp and reason.
- If vault has > 10,000 notes, batch operations to avoid filesystem pressure.
