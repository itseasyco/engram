#!/usr/bin/env python3
"""Stop Quality Gate - OpenClaw adaptation of LACP's stop_quality_gate.py

Detects incomplete work via heuristics + test verification (no Ollama, too heavy).
Uses fast pattern matching on transcript format.

Hook protocol (Stop event):
  - exit 0 with no stdout -> allow stop
  - exit 0 with {"decision": "block", "reason": "..."} -> block stop
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Configuration
DEBUG = os.getenv("QUALITY_GATE_DEBUG", "0") == "1"
DEBUG_LOG = Path("/tmp/openclaw-quality-gate.log")
MAX_BLOCKS = int(os.getenv("QUALITY_GATE_MAX_BLOCKS", "3"))


def _debug(msg: str) -> None:
    if DEBUG:
        with open(DEBUG_LOG, "a") as f:
            f.write(f"{msg}\n")


@dataclass
class CheckResult:
    decision: str
    reason: str = ""
    system_message: str = ""


@dataclass
class Context:
    hook_input: dict
    session_id: str
    last_message: str
    transcript_path: str


def _build_context(hook_input: dict) -> Context:
    session_id = hook_input.get("session_id") or ""
    last_message = hook_input.get("last_assistant_message") or ""
    transcript_path = hook_input.get("transcript_path") or ""

    if not last_message and transcript_path and os.path.isfile(transcript_path):
        last_message = _extract_last_assistant_from_transcript(transcript_path)

    return Context(
        hook_input=hook_input,
        session_id=session_id,
        last_message=last_message,
        transcript_path=transcript_path,
    )


def _extract_last_assistant_from_transcript(path: str) -> str:
    """Extract the most recent assistant message from OpenClaw transcript format."""
    last_line = ""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if '"role":"assistant"' in line or '"role": "assistant"' in line:
                    last_line = line.strip()
    except OSError:
        return ""

    if not last_line:
        return ""

    try:
        obj = json.loads(last_line)
        content = obj.get("message", {}).get("content", [])
        if isinstance(content, list):
            return "\n".join(
                b.get("text", "") for b in content
                if isinstance(b, dict) and b.get("type") == "text"
            )
    except (json.JSONDecodeError, AttributeError):
        pass

    return ""


# Heuristic patterns from LACP
HEURISTIC_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"pre-existing|out of scope", re.IGNORECASE), "pre-existing/out-of-scope"),
    (re.compile(r"too many.*(issues|failures|problems|errors)", re.IGNORECASE), "too-many-issues"),
    (re.compile(r"follow[- ]up|next session|next pr|defer(?:ring)?", re.IGNORECASE), "deferral"),
    (re.compile(r"will need to.*(address|fix|handle|resolve).*later", re.IGNORECASE), "postponement"),
    (re.compile(r"beyond the scope|outside the scope|outside of scope", re.IGNORECASE), "scope-deflection"),
    (re.compile(r"would (?:require|need).*(significant|extensive|major|substantial)", re.IGNORECASE), "effort-inflation"),
    (re.compile(r"at this point.*(recommend|suggest)|i would (?:recommend|suggest).*instead", re.IGNORECASE), "advisory-pivot"),
    (re.compile(r"left as.*(exercise|future)|leave.*(as is|for now|for later)", re.IGNORECASE), "abandonment"),
    (re.compile(r"done|complete|finished|all set|ready", re.IGNORECASE), "completion-claim"),
]


def check_heuristic_rationalization(message: str) -> tuple[int, list[str]]:
    """Return (hit_count, matched_names)."""
    hits = 0
    matched = []
    lower = message.lower()
    for rx, name in HEURISTIC_PATTERNS:
        if rx.search(lower):
            hits += 1
            matched.append(name)
    return hits, matched


# Failure pattern detection
FAILURE_PATTERNS = [
    (re.compile(r"error|failed|exception|traceback", re.IGNORECASE), "error-msg"),
    (re.compile(r"FAILED|FAIL |failed test", re.IGNORECASE), "test-failure"),
    (re.compile(r"TODO|FIXME|XXX|HACK", re.IGNORECASE), "unresolved-todo"),
    (re.compile(r"(?:still\s+)?(?:need to|have to|must)\s+(?:fix|implement|add|handle)", re.IGNORECASE), "unfinished-work"),
    (re.compile(r"not (?:yet\s+)?(?:implemented|done|complete|working|finished)", re.IGNORECASE), "incomplete"),
]


def check_for_failures(message: str) -> tuple[int, list[str]]:
    """Check if message contains indicators of incomplete work."""
    hits = 0
    matched = []
    lower = message.lower()
    for rx, name in FAILURE_PATTERNS:
        if rx.search(lower):
            hits += 1
            matched.append(name)
    return hits, matched


def check_loop_guard(ctx: Context) -> Optional[CheckResult]:
    """Prevent infinite loops when stop hook itself triggers stop."""
    if ctx.hook_input.get("stop_hook_active", False):
        _debug("SKIP: stop_hook_active=true (loop prevention)")
        return CheckResult("allow")
    return None


def check_message_trivial(ctx: Context) -> Optional[CheckResult]:
    """Empty or very short messages - not enough to evaluate."""
    stripped = ctx.last_message.strip()
    if not stripped:
        _debug("SKIP: empty message")
        return CheckResult("allow")
    if len(stripped) < 50:
        _debug(f"SKIP: message too short ({len(stripped)} < 50 chars)")
        return CheckResult("allow")
    return None


def check_circuit_breaker(ctx: Context) -> Optional[CheckResult]:
    """After MAX_BLOCKS blocks in same session, always allow."""
    if not ctx.session_id:
        return None

    circuit_file = Path(f"/tmp/openclaw-quality-gate-count-{ctx.session_id}")
    if not circuit_file.exists():
        return None

    try:
        count = int(circuit_file.read_text().strip())
    except (ValueError, OSError):
        return None

    if count >= MAX_BLOCKS:
        _debug(f"CIRCUIT_BREAKER: {count} blocks >= {MAX_BLOCKS} max, allowing stop")
        try:
            circuit_file.unlink()
        except OSError:
            pass
        return CheckResult("allow")

    return None


def _increment_circuit_breaker(session_id: str) -> int:
    """Increment and return block count for this session."""
    if not session_id:
        return 1
    circuit_file = Path(f"/tmp/openclaw-quality-gate-count-{session_id}")
    try:
        count = int(circuit_file.read_text().strip()) if circuit_file.exists() else 0
    except (ValueError, OSError):
        count = 0
    new_count = count + 1
    try:
        circuit_file.write_text(str(new_count))
    except OSError:
        pass
    _debug(f"CIRCUIT_BREAKER: block count now {new_count}/{MAX_BLOCKS} for session {session_id}")
    return new_count


# Test detection
TEST_CLAIM_PATTERNS = [
    re.compile(r"all\s+\d+\s+tests?\s+pass", re.IGNORECASE),
    re.compile(r"tests?\s+(?:are\s+)?pass(?:ing|ed)", re.IGNORECASE),
    re.compile(r"(?:ci|build)\s+(?:is\s+)?green", re.IGNORECASE),
    re.compile(r"test suite\s+pass", re.IGNORECASE),
]


def _detect_test_command(cwd: Optional[str] = None) -> Optional[str]:
    """Find test command from project files."""
    if not cwd:
        cwd = os.getcwd()

    pkg_json = Path(cwd) / "package.json"
    if pkg_json.exists():
        try:
            pkg = json.loads(pkg_json.read_text())
            scripts = pkg.get("scripts", {})
            if "test" in scripts:
                for runner in ("bun", "pnpm", "yarn", "npm"):
                    try:
                        subprocess.run(["which", runner], capture_output=True, timeout=2)
                        return f"{runner} test"
                    except Exception:
                        pass
        except (json.JSONDecodeError, OSError):
            pass

    makefile = Path(cwd) / "Makefile"
    if makefile.exists():
        try:
            content = makefile.read_text()
            if re.search(r"^test\s*:", content, re.MULTILINE):
                return "make test"
        except OSError:
            pass

    cargo_toml = Path(cwd) / "Cargo.toml"
    if cargo_toml.exists():
        return "cargo test"

    pyproject = Path(cwd) / "pyproject.toml"
    if pyproject.exists():
        return "python3 -m pytest"

    return None


def check_test_verification(ctx: Context) -> Optional[CheckResult]:
    """If message claims tests pass, verify they actually do."""
    has_claim = any(rx.search(ctx.last_message) for rx in TEST_CLAIM_PATTERNS)
    if not has_claim:
        return None

    _debug("TEST_VERIFY: test-success claim detected")

    cwd = ctx.hook_input.get("cwd") or os.getcwd()
    test_cmd = _detect_test_command(cwd)
    if not test_cmd:
        _debug("TEST_VERIFY: no test command found, skipping")
        return None

    _debug(f"TEST_VERIFY: running '{test_cmd}'")
    try:
        result = subprocess.run(
            test_cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=cwd,
        )
    except subprocess.TimeoutExpired:
        _debug("TEST_VERIFY: timeout, skipping")
        return None
    except OSError:
        _debug("TEST_VERIFY: command failed, skipping")
        return None

    if result.returncode == 0:
        _debug("TEST_VERIFY: tests PASSED, claim verified")
        return None

    # Tests failed - block
    output = (result.stdout or "") + (result.stderr or "")
    last_lines = "\n".join(output.strip().splitlines()[-5:])
    reason = f"Tests FAILED (exit {result.returncode}). Fix and re-run before stopping:\n{last_lines}"
    _debug(f"TEST_VERIFY: BLOCK - {reason}")
    return CheckResult("block", reason=reason)


def main() -> None:
    raw = sys.stdin.read()
    try:
        hook_input = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        hook_input = {}

    ctx = _build_context(hook_input)
    stripped = ctx.last_message.strip()

    _debug(f"INPUT: session_id={ctx.session_id or 'none'} message_len={len(stripped)}")

    # 1. Loop guard
    result = check_loop_guard(ctx)
    if result:
        return

    # 2. Circuit breaker
    result = check_circuit_breaker(ctx)
    if result:
        return

    # 3. Message trivial check
    result = check_message_trivial(ctx)
    if result:
        return

    # 4. Test verification
    result = check_test_verification(ctx)
    if result and result.decision == "block":
        _increment_circuit_breaker(ctx.session_id)
        _emit(result)
        return

    # 5. Check for explicit failures
    failure_hits, failure_matched = check_for_failures(stripped)
    if failure_hits > 0:
        _debug(f"FAILURES: {failure_hits} indicators: {failure_matched}")
        reason = f"Found indicators of incomplete work: {', '.join(failure_matched)}"
        _increment_circuit_breaker(ctx.session_id)
        _emit(CheckResult("block", reason=reason))
        return

    # 6. Heuristic rationalization check
    heuristic_hits, heuristic_matched = check_heuristic_rationalization(stripped)
    if heuristic_hits > 0:
        _debug(f"HEURISTIC: {heuristic_hits} rationalization patterns: {heuristic_matched}")

        # Fast path: if only completion claim (no failures), allow
        if heuristic_matched == ["completion-claim"] and failure_hits == 0:
            _debug("DECISION: allow (completion-claim only, no failures)")
            return

        # Multiple rationalization patterns + claim = suspicious
        if heuristic_hits >= 2:
            reason = f"Detected rationalization patterns: {', '.join(heuristic_matched)}"
            _increment_circuit_breaker(ctx.session_id)
            _emit(CheckResult("block", reason=reason))
            return

    _debug("DECISION: allow (no blockers)")


def _emit(result: CheckResult) -> None:
    """Output hook protocol JSON."""
    if result.decision == "block":
        print(json.dumps({"decision": "block", "reason": result.reason}))
    elif result.system_message:
        print(json.dumps({"decision": "allow", "systemMessage": result.system_message}))


if __name__ == "__main__":
    main()
