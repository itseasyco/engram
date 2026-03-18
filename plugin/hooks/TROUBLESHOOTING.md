# LACP Hooks Plugin — Troubleshooting Guide

**Purpose:** Diagnose and fix common issues with the LACP Hooks plugin.

**Last Updated:** 2026-03-17

---

## Diagnosis Checklist

Before troubleshooting a specific issue, run this health check:

```bash
#!/bin/bash
cd ~/.openclaw-test/plugins/lacp-hooks

echo "=== Health Check ==="
echo "1. Manifest:"
python3 -c "import json; json.load(open('plugin.json'))" && echo "  ✓ plugin.json valid" || echo "  ✗ plugin.json invalid"

echo "2. Handlers:"
for h in handlers/*.py; do
  python3 -m py_compile "$h" && echo "  ✓ $(basename $h)" || echo "  ✗ $(basename $h)"
done

echo "3. Tests:"
python3 -m pytest tests/test_integration.py -q && echo "  ✓ Integration tests pass" || echo "  ✗ Some tests failing"

echo "4. Profile:"
python3 -c "import json; json.load(open('profiles/balanced.json'))" && echo "  ✓ Profiles valid" || echo "  ✗ Profile JSON invalid"

echo "5. Environment:"
echo "  Profile: ${OPENCLAW_HOOKS_PROFILE:-balanced}"
echo "  Debug: ${OPENCLAW_HOOKS_DEBUG:-off}"
echo "  Disabled hooks: ${OPENCLAW_HOOKS_DISABLE:-none}"
```

---

## Plugin Not Loading

### Symptom
Plugin doesn't appear to be active. No hooks fire. No error messages.

### Root Causes & Fixes

**1. Plugin directory not found**
```bash
# Check it exists
ls -la ~/.openclaw-test/plugins/lacp-hooks/

# If not, create structure:
mkdir -p ~/.openclaw-test/plugins/lacp-hooks/{handlers,profiles,rules,tests}
git init
```

**2. plugin.json malformed**
```bash
# Validate JSON
python3 -c "import json; print(json.load(open('plugin.json')))" || echo "INVALID"

# If invalid, check syntax:
cat plugin.json | python3 -m json.tool > /tmp/test.json && mv /tmp/test.json plugin.json
```

**3. OpenClaw config doesn't reference plugin**
```bash
# Check if plugin is mentioned
grep -i "lacp-hooks" ~/.openclaw-test/openclaw.json

# If missing, add to openclaw.json:
{
  "plugins": {
    "lacp-hooks": {
      "enabled": true,
      "profile": "balanced"
    }
  }
}
```

**4. Plugin disabled in config**
```bash
# Check enabled flag
grep -A2 '"enabled"' ~/.openclaw-test/openclaw.json | grep lacp-hooks -A2

# Should say "enabled": true
```

**5. Handlers not executable**
```bash
# Check if handlers are readable
ls -la handlers/

# Make executable if needed
chmod +x handlers/*.py
```

---

## Hooks Not Firing

### Symptom
Plugin loads but hooks never execute. No errors logged.

### Root Causes & Fixes

**1. Hook trigger not recognized**
```bash
# Verify hook triggers in plugin.json match OpenClaw events
grep -A5 '"trigger"' plugin.json

# Common triggers:
# - session_initialization
# - pre_tool_use
# - agent_stop
# - file_write
```

**2. Profile doesn't include the hook**
```bash
# Check which hooks are enabled
python3 -c "import json; p = json.load(open('profiles/balanced.json')); print(p['hooks_enabled'])"

# If hook missing, add it to the profile's hooks_enabled list
```

**3. Debug logging off**
```bash
# Enable debug
export OPENCLAW_HOOKS_DEBUG=1

# Check logs
tail -50 /tmp/openclaw-*.log

# Look for hook execution records
```

**4. Session not starting with hook trigger**
```bash
# Some triggers require specific OpenClaw versions
# Ensure OpenClaw is recent:
openclaw --version

# Restart OpenClaw after config changes:
openclaw gateway restart
```

### Solution Checklist
- [ ] Verify hooks list in plugin.json
- [ ] Check profile has hook in hooks_enabled
- [ ] Enable debug: `export OPENCLAW_HOOKS_DEBUG=1`
- [ ] Check logs: `tail /tmp/openclaw-*.log`
- [ ] Restart OpenClaw: `openclaw gateway restart`
- [ ] Verify trigger in plugin.json matches OpenClaw event

---

## session-start Hook Issues

### Hook Fails to Inject Git Context

**Symptom:** Session starts but no git context appears.

**Fixes:**

1. **Not in a git repository**
   ```bash
   # Check if in git repo
   git rev-parse --is-inside-work-tree
   
   # If not, hook will skip (expected behavior)
   ```

2. **Git command fails**
   ```bash
   # Test git commands manually
   git branch --show-current
   git log --oneline -3
   git diff --name-only
   
   # If they fail, fix git repo or env
   ```

3. **Session ID not detected**
   ```bash
   # Check if environment variable set
   echo $OPENCLAW_SESSION_ID
   echo $TMUX_PANE
   
   # If empty, hook uses fallback (CWD hash)
   ```

4. **Test command detection failing**
   ```bash
   # Check if test command found
   ls package.json Makefile Cargo.toml pyproject.toml 2>/dev/null
   
   # If none exist, hook skips test detection (expected)
   ```

5. **Output not injected into system message**
   ```bash
   # Test handler directly
   echo '{}' | python3 handlers/session-start.py | python3 -m json.tool
   
   # Should have "systemMessage" key
   ```

### Debug Steps

```bash
# Enable debug and check output
export OPENCLAW_HOOKS_DEBUG=1
echo '{"matcher": "startup"}' | python3 handlers/session-start.py | jq .

# Should output:
# {
#   "systemMessage": "=== Git Context ===\n..."
# }
```

---

## pretool-guard Hook Issues

### Command Blocked Incorrectly

**Symptom:** Safe command blocked. Pattern matches too broadly.

**Fixes:**

1. **Pattern is overly broad**
   ```bash
   # Check pattern regex
   grep "npm_publish" rules/dangerous-patterns.yaml
   
   # If too broad, make more specific:
   # Bad:  \bnpm\b
   # Good: \bnpm\s+publish\b
   ```

2. **Safe pattern exception missing**
   ```bash
   # Add to safe_patterns section in dangerous-patterns.yaml:
   safe_patterns:
     - regex: '\bnpm\s+install\b'
       description: "Safe npm install"
   ```

3. **Command is actually dangerous**
   - Review the remediation hint provided
   - If it's truly safe, whitelist it (see above)
   - Or use a different approach that's safer

### Command Not Blocked When It Should Be

**Symptom:** Dangerous command was allowed through.

**Fixes:**

1. **Pattern not matching**
   ```bash
   # Test pattern directly
   python3 << 'EOF'
   import re
   cmd = "npm publish --tag v1.2.3"
   pattern = re.compile(r"\b(?:npm|yarn|pnpm|cargo)\s+publish\b", re.IGNORECASE)
   print(pattern.search(cmd))  # Should match, not None
   EOF
   ```

2. **Command was approved previously**
   ```bash
   # Check approval cache
   ls ~/.openclaw/approval-cache/
   cat ~/.openclaw/approval-cache/*.json
   
   # Clear cache if needed:
   rm ~/.openclaw/approval-cache/*.json
   ```

3. **Hook disabled**
   ```bash
   # Check if hook is in profile
   python3 -c "import json; p = json.load(open('profiles/balanced.json')); print('pretool-guard' in p['hooks_enabled'])"
   
   # Or check if disabled:
   echo $OPENCLAW_HOOKS_DISABLE
   ```

4. **Pattern removed or renamed**
   ```bash
   # Verify pattern still exists
   grep "npm_publish" rules/dangerous-patterns.yaml
   ```

### Approval Cache Issues

**Command not cached when expected:**
```bash
# Check cache TTL
grep "ttl" plugin.json

# Cache expires after 12 hours by default
# To extend: export OPENCLAW_PRETOOL_TTL=1440

# To immediately cache, approve manually:
# Run dangerous command → approve when prompted → cached
```

**Cache persists too long:**
```bash
# Clear approval cache
rm ~/.openclaw/approval-cache/*.json

# Or reduce TTL
export OPENCLAW_PRETOOL_TTL=60  # 1 hour instead of 12
```

### Debug Steps

```bash
# Test guard directly
echo '{"tool_input": {"command": "npm publish"}}' | \
  python3 handlers/pretool-guard.py command

# Should return error message if blocked
# Exit code 1 = blocked, 0 = allowed

# Test with approval
# Add cache entry manually or approve when prompted
```

---

## stop-quality-gate Hook Issues

### False Positive: Blocked Valid Completion

**Symptom:** Agent claims work is done, but hook blocks it incorrectly.

**Root Causes & Fixes:**

1. **Test detection too aggressive**
   ```bash
   # Check what patterns trigger
   grep "test\|fail\|error" rules/dangerous-patterns.yaml
   
   # If pattern too broad, make specific:
   # Edit handlers/stop-quality-gate.py FAILURE_PATTERNS
   ```

2. **TODO detection finding comments not actual work**
   ```bash
   # Check what was flagged
   tail -20 /tmp/openclaw-quality-gate.log | grep TODO
   
   # If legitimate TODOs (e.g., in comments), ignore or lower sensitivity
   ```

3. **Rationalization detection triggering on innocent language**
   ```bash
   # Example: "I recommend we leave this as-is for now"
   # Matches "leave.*for now" pattern
   
   # Edit HEURISTIC_PATTERNS in stop-quality-gate.py to be less strict
   ```

### False Negative: Should Block But Doesn't

**Symptom:** Incomplete work passes quality gate when it shouldn't.

**Fixes:**

1. **Test verification not running**
   ```bash
   # Check if tests exist
   ls tests/ | head
   
   # Check if test command detected
   ls package.json Makefile Cargo.toml pyproject.toml 2>/dev/null
   
   # If not, hook skips test verification (expected)
   ```

2. **Circuit breaker preventing further blocks**
   ```bash
   # Check circuit breaker file
   ls /tmp/openclaw-quality-gate-count-*
   
   # Clear it
   rm /tmp/openclaw-quality-gate-count-*
   ```

3. **Sensitivity set too low**
   ```bash
   # Check sensitivity in profile
   python3 -c "import json; p = json.load(open('profiles/balanced.json')); print(p['configuration']['stop_quality_gate']['sensitivity'])"
   
   # Change to 'high' for stricter checks
   ```

### Debug Steps

```bash
# Enable debug logging
export QUALITY_GATE_DEBUG=1

# Test with message
echo '{"last_assistant_message": "I have unresolved TODOs"}' | \
  python3 handlers/stop-quality-gate.py | jq .

# Check debug log
tail -50 /tmp/openclaw-quality-gate.log
```

---

## write-validate Hook Issues

### File Write Blocked Incorrectly

**Symptom:** Legitimate file cannot be written. Schema validation too strict.

**Fixes:**

1. **File not in knowledge path**
   ```bash
   # Check knowledge paths
   grep "OPENCLAW_VAULT" handlers/write-validate.py
   echo $OPENCLAW_VAULT_ROOT
   
   # File must be under /Volumes/Cortex or ~/.openclaw/knowledge
   # To add custom path:
   export OPENCLAW_WRITE_VALIDATE_PATHS=/my/path:/another/path
   ```

2. **Markdown missing required frontmatter**
   ```bash
   # File should start with:
   # ---
   # title: My Title
   # category: documentation
   # ---
   
   # Add frontmatter to fix
   ```

3. **Category not in taxonomy**
   ```bash
   # Check taxonomy
   cat /Volumes/Cortex/_metadata/taxonomy.json | jq '.classification.category_rules'
   
   # Use valid category or update taxonomy
   ```

### Debug Steps

```bash
# Test validator directly
python3 handlers/write-validate.py /path/to/file.md

# Should output JSON with status: PASS, WARN, or FAIL
# Check exit code:
echo $?  # 0 = pass/warn, 2 = fail
```

---

## Performance Issues

### Hooks Running Slowly

**Symptom:** Agent sessions slower than expected when hooks enabled.

**Root Causes & Fixes:**

1. **session-start running expensive git commands**
   ```bash
   # In large repos, git operations slow
   # Solution: Use faster profile
   export OPENCLAW_HOOKS_PROFILE=minimal-stop
   
   # Or disable session-start:
   export OPENCLAW_HOOKS_DISABLE=session-start
   ```

2. **stop-quality-gate running tests**
   ```bash
   # Test verification can take seconds
   # Solution: Only runs if agent claims tests pass
   # Or disable test verification:
   export QUALITY_GATE_MAX_BLOCKS=999  # Skip all checks after 999 blocks
   ```

3. **pretool-guard regex matching slow**
   ```bash
   # Unlikely unless command very long
   # Check profile has pretool-guard enabled
   # If slow, disable it:
   export OPENCLAW_HOOKS_DISABLE=pretool-guard
   ```

### Solution Checklist
- [ ] Switch to `minimal-stop` profile
- [ ] Disable slow hooks: `export OPENCLAW_HOOKS_DISABLE=session-start,write-validate`
- [ ] Check git repo size: `du -sh .git/`
- [ ] Run tests outside of hook: manually before stopping

---

## Configuration Issues

### Profile Not Applied

**Symptom:** Set `OPENCLAW_HOOKS_PROFILE=hardened-exec` but still getting `balanced` behavior.

**Fixes:**

1. **Environment variable not exported**
   ```bash
   # Must export, not just set
   export OPENCLAW_HOOKS_PROFILE=hardened-exec
   
   # Verify
   echo $OPENCLAW_HOOKS_PROFILE
   ```

2. **Config file overrides env**
   ```bash
   # openclaw.json takes precedence
   grep "profile" ~/.openclaw-test/openclaw.json
   
   # Remove from config or change there
   ```

3. **New session didn't pick up change**
   ```bash
   # Env vars only apply to new sessions
   # Start a fresh OpenClaw session
   # Or restart daemon:
   openclaw gateway restart
   ```

### Custom Configuration Not Working

**Symptom:** Modified `plugin.json` but changes not reflected.

**Fixes:**

1. **JSON syntax error**
   ```bash
   python3 -m json.tool plugin.json > /tmp/test.json && echo "VALID" || echo "INVALID"
   ```

2. **Daemon caching old config**
   ```bash
   # Restart gateway to reload
   openclaw gateway restart
   ```

3. **Hook still using old code**
   ```bash
   # Python bytecode cached
   find . -name "*.pyc" -delete
   find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null
   ```

---

## Test Failures

### Integration Tests Failing

**Run tests and check output:**
```bash
cd ~/.openclaw-test/plugins/lacp-hooks
python3 -m pytest tests/test_integration.py -v
```

**Common failures:**

1. **Handler not found**
   ```bash
   # Check handler exists and is readable
   ls -la handlers/*.py
   ```

2. **Profile JSON invalid**
   ```bash
   # Validate all profiles
   for f in profiles/*.json; do
     python3 -c "import json; json.load(open('$f'))"  && echo "$f: OK" || echo "$f: ERROR"
   done
   ```

3. **plugin.json malformed**
   ```bash
   python3 -c "import json; json.load(open('plugin.json'))" || python3 -m json.tool plugin.json
   ```

### Unit Tests Failing

**Example: test_session_start.py failures**

```bash
# Run with verbose output
pytest tests/test_session_start.py::TestGitDetection -v

# Common issues:
# 1. Not in git repo: Initialize or run in git repo
# 2. Git not installed: Check `which git`
# 3. Permissions: Check `ls -la .git/`
```

---

## Getting Help

### When to Check What

| Problem | Check First | Then Check |
|---------|-------------|-----------|
| Plugin not loading | plugin.json syntax | openclaw.json config |
| Hook not firing | Handler exists | Profile includes hook |
| Command blocked wrongly | Pattern regex | Approval cache |
| Tests failing | Handler syntax | Test dependencies |
| Slow performance | Profile setting | Git repo size |

### Required Information for Bug Reports

When reporting an issue:

1. **Environment:**
   ```bash
   openclaw --version
   python3 --version
   uname -a
   ```

2. **Configuration:**
   ```bash
   echo $OPENCLAW_HOOKS_PROFILE
   echo $OPENCLAW_HOOKS_DEBUG
   echo $OPENCLAW_HOOKS_DISABLE
   ```

3. **Logs:**
   ```bash
   tail -100 /tmp/openclaw-quality-gate.log
   cat ~/.openclaw/approval-cache/*.json 2>/dev/null | head -20
   ```

4. **Test output:**
   ```bash
   pytest tests/ -v 2>&1 | head -50
   ```

5. **Exact steps to reproduce**

---

## Quick Fixes Reference

```bash
# Clear all caches
rm ~/.openclaw/approval-cache/*.json
rm /tmp/openclaw-*.log
rm /tmp/openclaw-session-test-cmd-*

# Restart hooks system
openclaw gateway restart

# Run health check
pytest tests/test_integration.py -v

# Enable all debugging
export OPENCLAW_HOOKS_DEBUG=1
export QUALITY_GATE_DEBUG=1
export OPENCLAW_HOOKS_PROFILE=balanced

# Disable everything temporarily
export OPENCLAW_HOOKS_DISABLE=session-start,pretool-guard,stop-quality-gate,write-validate

# Reset to defaults
unset OPENCLAW_HOOKS_PROFILE
unset OPENCLAW_HOOKS_DEBUG
unset OPENCLAW_HOOKS_DISABLE
unset QUALITY_GATE_DEBUG
```

---

**Need more help?** Check README.md for user guide or OPERATIONS.md for detailed configuration.
