# Engram Tools Reference

## Memory Tools

| Tool | Purpose | When to Use |
|------|---------|-------------|
| `engram_memory_query` | Search persistent memory | Before starting work, when you need context |
| `engram_promote_fact` | Save important discovery | Immediately when you learn something valuable |
| `engram_save_session` | Record session summary | At end of every session |
| `engram_ingest` | Store content permanently | When given docs, URLs, PDFs, video |

## Knowledge Graph Tools

| Tool | Purpose | When to Use |
|------|---------|-------------|
| `engram_graph_index` | Index session into graph | After productive sessions |
| `engram_brain_resolve` | Fix conflicting info | When you find contradictions |
| `engram_vault_status` | Check vault health | Periodically or when issues arise |
| `engram_vault_optimize` | Tune graph display | When vault visualization needs adjustment |
| `engram_memory_kpi` | Memory quality metrics | To assess vault coverage and quality |

## Safety Tools

| Tool | Purpose | When to Use |
|------|---------|-------------|
| `engram_guard_status` | View guard rules/blocks | When a command is blocked |

## Automation

These tools are called automatically by hooks — you don't need to invoke them manually:
- **Session start**: Git context, test commands, and memory facts are injected
- **Pre-tool**: Dangerous commands are blocked or flagged for approval
- **Post-write**: YAML frontmatter on vault files is validated
- **Session end**: Quality gate checks for incomplete work
