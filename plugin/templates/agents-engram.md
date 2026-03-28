
## Engram — Memory-First Workflow

You are connected to a persistent memory system. Other agents have worked in this codebase before you and may have already documented what you're about to investigate.

### Before starting any task

1. **Query memory first.** Use `engram_memory_query` with your task topic before reading code or exploring. Previous sessions may have the answer, a relevant pattern, or a known gotcha.
2. **Check for related vault notes.** If memory returns results, follow up with related topics — the knowledge graph links related concepts.

### During your work

3. **Promote facts immediately.** When you discover something non-obvious — an architectural decision, a debugging insight, an integration pattern, a gotcha — use `engram_promote_fact` right away. Don't wait until the end.
4. **Ingest external references.** If you consult a URL, doc, or file outside the codebase, use `engram_ingest` so future sessions have that content indexed.
5. **Resolve contradictions.** If you find information in memory that conflicts with what you observe, use `engram_brain_resolve` to mark the old fact as superseded or stale.

### When finishing

6. **Save your session.** Use `engram_save_session` with a summary of what you did, key decisions made, tasks completed, and tasks still pending. This is how the next agent picks up where you left off.

### What NOT to do

- Don't re-investigate topics that are already in memory — read first, verify if needed, then build on it.
- Don't wait until the end of a session to promote facts — promote as you discover them.
- Don't ignore memory query results — even if they seem tangential, they may contain context that prevents you from repeating mistakes.
