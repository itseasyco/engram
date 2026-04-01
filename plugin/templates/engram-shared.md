# Engram — Memory-First Workflow

You are connected to a persistent memory system. Other agents have worked in this codebase before you and left knowledge you should use.

## Before Starting Any Task
1. **Query memory first.** `engram_memory_query` with your task topic before reading code. Previous sessions may have the answer or a known gotcha.
2. **Check related vault notes.** Follow up on related topics — the knowledge graph links concepts.

## During Your Work
3. **Promote facts immediately.** Non-obvious discoveries (architectural decisions, debugging insights, gotchas) → `engram_promote_fact` right away. Don't wait.
4. **Ingest external references.** Consulted a URL, doc, or file outside the codebase? → `engram_ingest` so future sessions have it indexed.
5. **Resolve contradictions.** Memory conflicts with what you observe? → `engram_brain_resolve` to mark the old fact as stale.

## When Finishing
6. **Save your session.** `engram_save_session` with: what you did, key decisions, tasks completed, tasks pending. This is how the next agent picks up where you left off.

## Rules
- Don't re-investigate topics already in memory — read first, verify if needed, build on it.
- Promote facts as you discover them, not at the end.
- Don't ignore memory results — they may prevent you from repeating mistakes.

## Repository Workflow

Agents share a repository registry at `~/.openclaw/shared/repositories.json`. This file tracks every repo's path, stack, deploy target, conventions, and gotchas.

### When starting work on a repo
- Update `last_agent` to your name and `last_worked` to today's date (YYYY-MM-DD).

### When finishing work on a repo
- Add to `conventions` if you learned a pattern others should follow.
- Add to `gotchas` if you hit something non-obvious that would waste time for the next agent.

### If the repo isn't in the file
- Add a new entry with what you can determine (path, stack, default_branch).

### If `gitnexus_indexed` is >14 days old
- Re-run `npx gitnexus analyze` in the repo and update the date.
