# Engram Config

Engram's configuration lives at `~/.engram/config.json`. This is the single
source of truth for the vault path, mode, curator endpoint, and feature
flags. It is host-agnostic — the same file is used whether you launched
Engram via Claude Code, Codex, or OpenClaw.

## Environment overrides

| Var            | Default       | Purpose                                  |
|----------------|---------------|------------------------------------------|
| `ENGRAM_HOME`  | `~/.engram`   | Where Engram stores config + extensions  |

Setting `ENGRAM_HOME=/tmp/lme-engram` lets you run Engram against an
isolated config without touching the real one — useful for benchmarks
(LongMemEval) and tests.

## Migrating from `~/.openclaw/openclaw.json`

```bash
./bin/engram-migrate-config --dry-run    # preview
./bin/engram-migrate-config              # write ~/.engram/config.json
./bin/engram-migrate-config --move-lcm   # also move lcm.db (with backup)
```

The migration:
- Reads `plugins.entries.engram.config` from `~/.openclaw/openclaw.json`
- Reads `~/.openclaw/config/mode.json` if present
- Writes `~/.engram/config.json` matching the schema in
  `plugin/lib/engram_config.py:DEFAULTS`
- Backs up both source and target before writing
- Is idempotent (re-running produces the same result)

## Schema

See `plugin/lib/engram_config.py` for the canonical defaults and
`plugin/openclaw.plugin.json` `configSchema` for field descriptions.

## Pointing hosts at it

OpenClaw learns about Engram via a tiny pointer in `~/.openclaw/openclaw.json`:

```json
{
  "plugins": {
    "entries": {
      "engram": { "enabled": true, "configRef": "~/.engram/config.json" }
    }
  }
}
```

Claude Code and Codex don't need any host-side config today — they pick up
Engram via its MCP server entry, which reads `~/.engram/config.json`
directly.
