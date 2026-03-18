# LACP Hooks Plugin — Operations Guide

**Purpose:** Run, configure, debug, and maintain the LACP Hooks plugin for OpenClaw.

**Status:** Production-ready (Phase 1 complete)  
**Last Updated:** 2026-03-17

---

## Quick Reference

| Task | Command |
|------|---------|
| Run tests | `pytest tests/ -v` |
| Run integration tests | `pytest tests/test_integration.py -v` |
| Enable plugin | Set `OPENCLAW_HOOKS_PROFILE=balanced` |
| Debug hooks | Set `OPENCLAW_HOOKS_DEBUG=1` and check `/tmp/openclaw-*.log` |
| Disable specific hook | `export OPENCLAW_HOOKS_DISABLE=pretool-guard` |
| Check handler syntax | `python3 -m py_compile handlers/*.py` |

---

## Plugin Architecture

```
lacp-hooks/
├── plugin.json                 # Manifest: hooks, profiles, config
├── handlers/                   # Hook implementations
│   ├── session-start.py        # Git context injection
│   ├── pretool-guard.py        # Dangerous pattern blocking
│   ├── stop-quality-gate.py    # Incomplete work detection
│   └── write-validate.py       # Schema validation
├── rules/                      # Shared pattern libraries
│   └── dangerous-patterns.yaml # Centralized threat definitions
├── profiles/                   # Composable hook profiles
│   ├── minimal-stop.json
│   ├── balanced.json
│   └── hardened-exec.json
├── tests/                      # Unit + integration tests
│   ├── test_*.py               # Individual handler tests
│   └── test_integration.py     # End-to-end plugin validation
└── README.md                   # User guide
```

---

## Profiles

### minimal-stop
**Enabled hooks:** stop-quality-gate  
**Best for:** Quick dev cycles, low-risk work  
**Overhead:** Minimal (single heuristic check)  

```bash
export OPENCLAW_HOOKS_PROFILE=minimal-stop
```

**Configuration:**
```json
{
  "stop_quality_gate": {
    "enable_test_detection": true,
    "enable_todo_detection": true,
    "enable_rationalization_detection": true,
    "sensitivity": "medium"
  }
}
```

---

### balanced (Recommended Default)
**Enabled hooks:** session-start, stop-quality-gate  
**Best for:** General development, feature work, moderate risk  
**Overhead:** Low (git context + quality check)  

```bash
export OPENCLAW_HOOKS_PROFILE=balanced
```

**Configuration:**
```json
{
  "session_start": {
    "inject_git_context": true,
    "inject_file_list": true,
    "max_commits_to_show": 5
  },
  "stop_quality_gate": {
    "enable_test_detection": true,
    "enable_todo_detection": true,
    "enable_rationalization_detection": true,
    "sensitivity": "medium"
  }
}
```

---

### hardened-exec
**Enabled hooks:** All (session-start, pretool-guard, stop-quality-gate, write-validate)  
**Best for:** Production deploys, dangerous commands, security-critical work  
**Overhead:** Moderate (all safety checks enabled)  

```bash
export OPENCLAW_HOOKS_PROFILE=hardened-exec
```

**Configuration:**
```json
{
  "session_start": {
    "inject_git_context": true,
    "max_commits_to_show": 10
  },
  "pretool_guard": {
    "ttl_minutes": 720,
    "approval_cache_enabled": true,
    "block_level": "error",
    "strict_mode": true
  },
  "stop_quality_gate": {
    "sensitivity": "high"
  },
  "write_validate": {
    "require_explicit_approval": true
  }
}
```

---

## Configuration

### Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `OPENCLAW_HOOKS_PROFILE` | `balanced` | Which profile to use |
| `OPENCLAW_HOOKS_DEBUG` | `0` | Enable verbose logging |
| `OPENCLAW_HOOKS_DISABLE` | (none) | Comma-separated hooks to disable |
| `OPENCLAW_PRETOOL_TTL` | `720` (min) | Approval cache TTL |
| `QUALITY_GATE_DEBUG` | `0` | Enable stop-gate debug logging |
| `OPENCLAW_VAULT_ROOT` | `/Volumes/Cortex` | Knowledge base path |

### Config File

Edit `~/.openclaw-test/openclaw.json`:

```json
{
  "plugins": {
    "lacp-hooks": {
      "enabled": true,
      "profile": "balanced",
      "configuration": {
        "pretool_guard": {
          "ttl_minutes": 720,
          "approval_cache_enabled": true
        },
        "stop_quality_gate": {
          "enable_test_detection": true
        }
      }
    }
  }
}
```

---

## Running Tests

### All Tests
```bash
cd ~/.openclaw-test/plugins/lacp-hooks
python3 -m pytest tests/ -v
```

### Specific Test Class
```bash
pytest tests/test_pretool_guard.py::TestDangerousPatterns -v
```

### Single Test
```bash
pytest tests/test_session_start.py::TestGitDetection::test_is_git_repo_true -v
```

### With Coverage
```bash
pytest tests/ --cov=handlers --cov-report=html
```

### Integration Tests Only
```bash
pytest tests/test_integration.py -v
```

---

## Debugging

### Enable Debug Logging

```bash
export OPENCLAW_HOOKS_DEBUG=1
export QUALITY_GATE_DEBUG=1
```

Logs are written to:
- `/tmp/openclaw-quality-gate.log` (stop-quality-gate)
- stderr for other hooks

### Check Handler Syntax

```bash
python3 -c "import handlers.session_start"
python3 -c "import handlers.pretool_guard"
python3 -c "import handlers.stop_quality_gate"
python3 -c "import handlers.write_validate"
```

Or use the compile check:
```bash
python3 -m py_compile handlers/*.py
```

### Test Handler Directly

```bash
# Test session-start with empty payload
echo '{}' | python3 handlers/session-start.py

# Test pretool-guard with dangerous command
echo '{"tool_input": {"command": "npm publish"}}' | \
  python3 handlers/pretool-guard.py command

# Test stop-quality-gate with failure message
echo '{"last_assistant_message": "I got an error TODO"}' | \
  python3 handlers/stop-quality-gate.py
```

### Check Approval Cache

```bash
ls -la ~/.openclaw/approval-cache/
cat ~/.openclaw/approval-cache/session_*.json
```

### Clear Approval Cache

```bash
rm ~/.openclaw/approval-cache/*.json
rm /tmp/openclaw-session-test-cmd-*
```

---

## Common Issues

### Hooks Not Firing?

1. **Verify plugin is enabled:**
   ```bash
   grep -A5 lacp-hooks ~/.openclaw-test/openclaw.json
   ```

2. **Check handlers exist:**
   ```bash
   ls -la ~/.openclaw-test/plugins/lacp-hooks/handlers/
   ```

3. **Verify handler is executable:**
   ```bash
   python3 -m py_compile handlers/*.py
   ```

4. **Enable debug logging:**
   ```bash
   export OPENCLAW_HOOKS_DEBUG=1
   tail -f /tmp/openclaw-*.log
   ```

### Command Blocked But It's Safe?

1. **Whitelist the pattern:**
   - Edit `rules/dangerous-patterns.yaml`
   - Add to `safe_patterns:` section
   - Restart OpenClaw

2. **Approve once (12h TTL):**
   ```bash
   # Run the command, approve when prompted
   # It's cached for 12 hours
   ```

3. **Disable the hook temporarily:**
   ```bash
   export OPENCLAW_HOOKS_DISABLE=pretool-guard
   ```

### Quality Gate False Positives?

1. **Lower sensitivity:**
   - Edit `profiles/balanced.json`
   - Change `"sensitivity": "low"`

2. **Disable specific detection:**
   ```bash
   export QUALITY_GATE_MAX_BLOCKS=999  # Disable circuit breaker
   ```

3. **File an issue:**
   - Check TROUBLESHOOTING.md
   - Include the message that was incorrectly blocked

### Write Validation Failing?

1. **Check file format:**
   ```bash
   python3 handlers/write-validate.py /path/to/file.md
   ```

2. **Verify frontmatter:**
   ```bash
   head -10 /path/to/file.md
   ```
   Should look like:
   ```yaml
   ---
   title: My Title
   category: documentation
   ---
   ```

3. **Whitelist path:**
   - Edit `handlers/write-validate.py`
   - Add to `KNOWLEDGE_PATHS_ENV` or
   - Set `OPENCLAW_WRITE_VALIDATE_PATHS=/custom/path`

---

## Maintenance

### Adding New Patterns

1. **Edit `rules/dangerous-patterns.yaml`:**
   ```yaml
   - name: "new_pattern"
     regex: '\bmy_pattern\b'
     description: "What this blocks"
     severity: "high"
     remediation: "How to work around it"
   ```

2. **Update handler to load new patterns** (if needed)

3. **Add test:**
   ```bash
   # In tests/test_pretool_guard.py
   def test_new_pattern_blocked(self):
       assert main_guard("some new_pattern command") == 1
   ```

4. **Run tests:**
   ```bash
   pytest tests/ -v
   ```

5. **Commit:**
   ```bash
   git add rules/dangerous-patterns.yaml tests/
   git commit -m "feat: add pattern for X"
   ```

### Updating Profiles

1. **Edit profile JSON:**
   ```bash
   vim profiles/balanced.json
   ```

2. **Validate JSON:**
   ```bash
   python3 -c "import json; json.load(open('profiles/balanced.json'))" && echo "OK"
   ```

3. **Test with profile:**
   ```bash
   export OPENCLAW_HOOKS_PROFILE=balanced
   pytest tests/test_integration.py::TestProfiles -v
   ```

4. **Commit:**
   ```bash
   git add profiles/balanced.json
   git commit -m "feat: update balanced profile configuration"
   ```

---

## Performance

### Hook Overhead

| Hook | Overhead | Notes |
|------|----------|-------|
| session-start | ~100ms | Git commands, file detection |
| pretool-guard | ~50ms | Regex matching on command |
| stop-quality-gate | ~200ms | May run tests |
| write-validate | ~10ms | File path + schema check |

**Total overhead:** 300-400ms per hook invocation (profile-dependent).

### Optimization Tips

1. **Use minimal-stop profile for fast iteration**
   ```bash
   export OPENCLAW_HOOKS_PROFILE=minimal-stop
   ```

2. **Disable test verification when not needed**
   ```bash
   export QUALITY_GATE_MAX_BLOCKS=0  # Disable all quality gate blocks
   ```

3. **Increase approval cache TTL**
   ```bash
   export OPENCLAW_PRETOOL_TTL=1440  # 24 hours
   ```

---

## Monitoring

### Check Hook Execution

```bash
# Session-start
grep "session-start" ~/.openclaw-test/openclaw.json

# PreTool Guard
ls -ltr ~/.openclaw/approval-cache/ | tail -5

# Stop Quality Gate
tail -100 /tmp/openclaw-quality-gate.log

# Write Validate
echo '{"tool_input": {"file_path": "test.md"}}' | \
  python3 handlers/write-validate.py | jq .
```

### Log Locations

- **Hook debug logs:** `/tmp/openclaw-*.log`
- **Approval cache:** `~/.openclaw/approval-cache/`
- **Test cache:** `/tmp/openclaw-session-test-cmd-*`
- **Quality gate circuit breaker:** `/tmp/openclaw-quality-gate-count-*`

### Health Check

```bash
#!/bin/bash
echo "Checking LACP Hooks health..."

# 1. Plugin manifest
python3 -c "import json; json.load(open('plugin.json'))" && \
  echo "✓ plugin.json valid" || echo "✗ plugin.json invalid"

# 2. Handlers
for h in handlers/*.py; do
  python3 -m py_compile "$h" && echo "✓ $(basename $h)" || echo "✗ $(basename $h)"
done

# 3. Tests
pytest tests/test_integration.py -q && echo "✓ Integration tests pass"

# 4. Profiles
for p in profiles/*.json; do
  python3 -c "import json; json.load(open('$p'))" && \
    echo "✓ $(basename $p)" || echo "✗ $(basename $p)"
done

echo "Health check complete"
```

---

## Git Workflow

### Before Committing

```bash
# 1. Run all tests
pytest tests/ -v

# 2. Check coverage
pytest tests/ --cov=handlers

# 3. Validate syntax
python3 -m py_compile handlers/*.py

# 4. Validate JSON
for f in plugin.json profiles/*.json; do
  python3 -c "import json; json.load(open('$f'))" || exit 1
done

# 5. Commit
git add -A
git commit -m "feat|fix: clear description"
```

### Branching Strategy

- **main** — Stable, tested, production-ready
- **dev** — Integration branch for active development
- **feat/*** — Feature branches (e.g., feat/pretool-guard-improvements)
- **fix/*** — Bug fixes

### Commit Messages

```
feat: <short description>    # New feature
fix: <short description>     # Bug fix
docs: <short description>    # Documentation
test: <short description>    # Test improvements
refactor: <short description># Code refactoring
```

---

## Support & Issues

### Getting Help

1. **Check README.md** — User-facing guide
2. **Check TROUBLESHOOTING.md** — Common problems
3. **Check test failures** — Run `pytest tests/ -v`
4. **Enable debug logging** — `export OPENCLAW_HOOKS_DEBUG=1`
5. **Review handler code** — Source is well-commented

### Reporting Issues

When reporting a problem, include:
- Profile being used
- Handler that's failing (if known)
- Complete error message
- Steps to reproduce
- Debug log output (with `OPENCLAW_HOOKS_DEBUG=1`)

---

## Upgrade Path

### From Phase 1 → Phase 2

Phase 2 will add:
- Policy gates (risk tiers, budgets, context contracts)
- Approval workflows
- Multi-agent coordination

Current handlers will remain compatible. Breaking changes will be in separate major version.

---

**Questions?** See README.md for user guide or review handler source code for implementation details.
