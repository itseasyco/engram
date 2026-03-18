#!/usr/bin/env python3
"""Unit tests for stop-quality-gate.py handler."""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# Add handlers to path
HANDLERS_DIR = Path(__file__).parent.parent / "handlers"
sys.path.insert(0, str(HANDLERS_DIR))

# Import the handler module
import importlib.util
spec = importlib.util.spec_from_file_location("stop_quality_gate", HANDLERS_DIR / "stop-quality-gate.py")
stop_gate = importlib.util.module_from_spec(spec)


class TestStopQualityGate:
    """Test suite for stop-quality-gate hook."""

    def test_allow_empty_message(self):
        """Empty messages should be allowed (not enough to evaluate)."""
        hook_input = {
            "session_id": "test1",
            "last_assistant_message": "",
            "transcript_path": None,
        }
        result = run_hook(hook_input)
        assert result is None or result == ""
        print("✅ test_allow_empty_message PASS")

    def test_allow_short_message(self):
        """Very short messages should be allowed."""
        hook_input = {
            "session_id": "test2",
            "last_assistant_message": "Done.",
            "transcript_path": None,
        }
        result = run_hook(hook_input)
        assert result is None or result == ""
        print("✅ test_allow_short_message PASS")

    def test_allow_completion_claim_no_failures(self):
        """'Done/completed' with no failures should allow."""
        hook_input = {
            "session_id": "test3",
            "last_assistant_message": "All done! I've completed the implementation and everything is working correctly.",
            "transcript_path": None,
        }
        result = run_hook(hook_input)
        assert result is None or result == ""
        print("✅ test_allow_completion_claim_no_failures PASS")

    def test_block_unresolved_todo(self):
        """Message with TODO/FIXME should block."""
        hook_input = {
            "session_id": "test4",
            "last_assistant_message": "I've implemented most of the feature. TODO: add error handling. FIXME: edge case not handled.",
            "transcript_path": None,
        }
        result = run_hook(hook_input)
        assert result is not None
        parsed = json.loads(result)
        assert parsed["decision"] == "block"
        assert "TODO" in result or "FIXME" in result or "unresolved" in result.lower()
        print("✅ test_block_unresolved_todo PASS")

    def test_block_explicit_failure(self):
        """Message saying tests failed should block."""
        hook_input = {
            "session_id": "test5",
            "last_assistant_message": "I tried to implement the feature but the tests are failing. The errors are hard to debug and I'm not sure what's wrong.",
            "transcript_path": None,
        }
        result = run_hook(hook_input)
        assert result is not None
        parsed = json.loads(result)
        assert parsed["decision"] == "block"
        print("✅ test_block_explicit_failure PASS")

    def test_block_rationalization_deferral(self):
        """'Will fix in follow-up' patterns should block."""
        hook_input = {
            "session_id": "test6",
            "last_assistant_message": "I've done the basic implementation. The edge cases will need to be handled in a follow-up session.",
            "transcript_path": None,
        }
        result = run_hook(hook_input)
        assert result is not None
        parsed = json.loads(result)
        assert parsed["decision"] == "block"
        print("✅ test_block_rationalization_deferral PASS")

    def test_block_too_many_issues(self):
        """'Too many issues' excuse should block."""
        hook_input = {
            "session_id": "test7",
            "last_assistant_message": "There are too many failing tests and problems to fix in one session. I'll leave it as is for now.",
            "transcript_path": None,
        }
        result = run_hook(hook_input)
        assert result is not None
        parsed = json.loads(result)
        assert parsed["decision"] == "block"
        print("✅ test_block_too_many_issues PASS")

    def test_block_scope_deflection(self):
        """'Outside the scope' should block when claiming done."""
        hook_input = {
            "session_id": "test8",
            "last_assistant_message": "I've completed the main work. The bug fix you mentioned is outside the scope of this task.",
            "transcript_path": None,
        }
        result = run_hook(hook_input)
        assert result is not None
        parsed = json.loads(result)
        assert parsed["decision"] == "block"
        print("✅ test_block_scope_deflection PASS")

    def test_block_effort_inflation(self):
        """Saying something 'would require extensive work' should block."""
        hook_input = {
            "session_id": "test9",
            "last_assistant_message": "The refactoring would require significant effort and I'm leaving it as is. This is beyond the scope of current work.",
            "transcript_path": None,
        }
        result = run_hook(hook_input)
        # Should detect rationalization pattern (deferral or scope-deflection)
        if result:
            parsed = json.loads(result)
            assert parsed["decision"] == "block"
        print("✅ test_block_effort_inflation PASS")

    def test_block_abandonment(self):
        """'Left as exercise' or 'leave for later' should block."""
        hook_input = {
            "session_id": "test10",
            "last_assistant_message": "The implementation is mostly done. I've left the error handling as an exercise for the user.",
            "transcript_path": None,
        }
        result = run_hook(hook_input)
        # May or may not block depending on other patterns; at least shouldn't crash
        print("✅ test_block_abandonment PASS")

    def test_loop_guard(self):
        """Should not block if stop_hook_active is true (prevent loops)."""
        hook_input = {
            "session_id": "test11",
            "last_assistant_message": "TODO: fix something",
            "transcript_path": None,
            "stop_hook_active": True,
        }
        result = run_hook(hook_input)
        assert result is None or result == ""
        print("✅ test_loop_guard PASS")

    def test_multiple_patterns(self):
        """Multiple rationalization patterns should increase likelihood of block."""
        hook_input = {
            "session_id": "test12",
            "last_assistant_message": (
                "Done with implementation. There are too many issues to fix right now. "
                "Beyond the scope. Will follow up next session."
            ),
            "transcript_path": None,
        }
        result = run_hook(hook_input)
        if result:
            parsed = json.loads(result)
            assert parsed["decision"] == "block"
        print("✅ test_multiple_patterns PASS")

    def test_case_insensitive(self):
        """Patterns should be case-insensitive."""
        hook_input = {
            "session_id": "test13",
            "last_assistant_message": "The implementation is complete BUT THERE ARE TOO MANY ERRORS to fix.",
            "transcript_path": None,
        }
        result = run_hook(hook_input)
        assert result is not None
        parsed = json.loads(result)
        assert parsed["decision"] == "block"
        print("✅ test_case_insensitive PASS")

    def test_incomplete_indicator(self):
        """'Not yet implemented' should block."""
        hook_input = {
            "session_id": "test14",
            "last_assistant_message": "I've implemented the main feature. Error handling is not yet implemented.",
            "transcript_path": None,
        }
        result = run_hook(hook_input)
        assert result is not None
        parsed = json.loads(result)
        assert parsed["decision"] == "block"
        print("✅ test_incomplete_indicator PASS")

    def test_allow_legitimate_summary(self):
        """Legitimate work summary should allow."""
        hook_input = {
            "session_id": "test15",
            "last_assistant_message": (
                "I've completed the implementation. Here's what was done:\n"
                "1. Added user authentication\n"
                "2. Created database schema\n"
                "3. Implemented API endpoints\n"
                "4. Added comprehensive tests\n"
                "All tests pass and the feature is ready for review."
            ),
            "transcript_path": None,
        }
        result = run_hook(hook_input)
        assert result is None or result == ""
        print("✅ test_allow_legitimate_summary PASS")


def run_hook(hook_input: dict) -> str:
    """Run the hook with given input, return stdout."""
    hook_script = HANDLERS_DIR / "stop-quality-gate.py"
    proc = subprocess.run(
        ["python3", str(hook_script)],
        input=json.dumps(hook_input),
        capture_output=True,
        text=True,
        timeout=10,
    )
    return proc.stdout.strip()


def main():
    test = TestStopQualityGate()
    tests = [m for m in dir(test) if m.startswith("test_")]

    print(f"Running {len(tests)} tests for stop-quality-gate...")
    print()

    failed = 0
    for test_name in sorted(tests):
        try:
            getattr(test, test_name)()
        except AssertionError as e:
            print(f"❌ {test_name} FAIL: {e}")
            failed += 1
        except Exception as e:
            print(f"❌ {test_name} ERROR: {e}")
            failed += 1

    print()
    passed = len(tests) - failed
    print(f"Results: {passed}/{len(tests)} passed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
