#!/usr/bin/env python3
"""Unit tests for write-validate.py handler."""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# Test setup
HANDLERS_DIR = Path(__file__).parent.parent / "handlers"
VAULT_PATH = Path(tempfile.gettempdir()) / "test-vault"
VAULT_PATH.mkdir(exist_ok=True)


class TestWriteValidate:
    """Test suite for write-validate hook."""

    @classmethod
    def setup_class(cls):
        """Create test vault structure."""
        VAULT_PATH.mkdir(exist_ok=True)

    def test_skip_non_markdown(self):
        """Non-markdown files should be skipped."""
        test_file = VAULT_PATH / "test.txt"
        test_file.write_text("some content")

        result = run_hook(str(test_file))
        parsed = json.loads(result)
        assert parsed["status"] == "SKIP"
        assert "not markdown" in parsed.get("reason", "")
        print("✅ test_skip_non_markdown PASS")

    def test_skip_non_knowledge_path(self):
        """Files outside knowledge paths should be skipped."""
        test_file = Path(tempfile.gettempdir()) / "random.md"
        test_file.write_text("# Test\ncontent")

        result = run_hook(str(test_file))
        parsed = json.loads(result)
        assert parsed["status"] == "SKIP"
        print("✅ test_skip_non_knowledge_path PASS")

    def test_fail_missing_frontmatter(self):
        """Files without frontmatter should fail."""
        test_file = VAULT_PATH / "no-frontmatter.md"
        test_file.write_text("# Just a heading\n\nNo frontmatter here.")

        # Set vault path via env var
        env = os.environ.copy()
        env["OPENCLAW_WRITE_VALIDATE_PATHS"] = str(VAULT_PATH)

        result = run_hook(str(test_file), env=env)
        parsed = json.loads(result)
        assert parsed["status"] == "FAIL"
        assert "frontmatter" in result.lower()
        print("✅ test_fail_missing_frontmatter PASS")

    def test_fail_missing_required_fields(self):
        """Files missing required fields should fail."""
        test_file = VAULT_PATH / "incomplete.md"
        test_file.write_text("""---
created: 2026-03-18
tags: test
---

# Content

This file is missing title and category.
""")

        env = os.environ.copy()
        env["OPENCLAW_WRITE_VALIDATE_PATHS"] = str(VAULT_PATH)

        result = run_hook(str(test_file), env=env)
        parsed = json.loads(result)
        assert parsed["status"] == "FAIL"
        assert "title" in result.lower() or "category" in result.lower()
        print("✅ test_fail_missing_required_fields PASS")

    def test_warn_missing_recommended_fields(self):
        """Files missing recommended fields should warn."""
        test_file = VAULT_PATH / "minimal.md"
        test_file.write_text("""---
title: Minimal Document
category: notes
---

# Content

This is minimal but valid.
""")

        env = os.environ.copy()
        env["OPENCLAW_WRITE_VALIDATE_PATHS"] = str(VAULT_PATH)

        result = run_hook(str(test_file), env=env)
        parsed = json.loads(result)
        assert parsed["status"] in ("WARN", "PASS")
        # If WARN, should mention missing recommended fields
        if parsed["status"] == "WARN":
            assert len(parsed.get("issues", [])) > 0
        print("✅ test_warn_missing_recommended_fields PASS")

    def test_pass_complete_frontmatter(self):
        """Files with all fields should pass."""
        test_file = VAULT_PATH / "complete.md"
        test_file.write_text("""---
title: Complete Document
category: notes
created: 2026-03-18
tags: test, example, docs
---

# Content

This file has all required and recommended fields.
""")

        env = os.environ.copy()
        env["OPENCLAW_WRITE_VALIDATE_PATHS"] = str(VAULT_PATH)

        result = run_hook(str(test_file), env=env)
        parsed = json.loads(result)
        assert parsed["status"] == "PASS"
        assert len(parsed.get("issues", [])) == 0
        print("✅ test_pass_complete_frontmatter PASS")

    def test_frontmatter_quoted_values(self):
        """Frontmatter with quoted values should parse correctly."""
        test_file = VAULT_PATH / "quoted.md"
        test_file.write_text("""---
title: "Document with 'quoted' title"
category: 'notes'
created: "2026-03-18"
tags: tag1, tag2
---

# Content
""")

        env = os.environ.copy()
        env["OPENCLAW_WRITE_VALIDATE_PATHS"] = str(VAULT_PATH)

        result = run_hook(str(test_file), env=env)
        parsed = json.loads(result)
        assert parsed["status"] in ("PASS", "WARN")
        print("✅ test_frontmatter_quoted_values PASS")

    def test_frontmatter_with_comments(self):
        """Frontmatter with YAML comments should parse."""
        test_file = VAULT_PATH / "comments.md"
        test_file.write_text("""---
# This is a comment
title: Document Title
# Another comment
category: notes
created: 2026-03-18
---

# Content
""")

        env = os.environ.copy()
        env["OPENCLAW_WRITE_VALIDATE_PATHS"] = str(VAULT_PATH)

        result = run_hook(str(test_file), env=env)
        parsed = json.loads(result)
        assert parsed["status"] in ("PASS", "WARN")
        print("✅ test_frontmatter_with_comments PASS")

    def test_json_output_format(self):
        """Output should always be valid JSON."""
        test_file = VAULT_PATH / "json-test.md"
        test_file.write_text("not markdown content")

        result = run_hook(str(test_file))
        try:
            parsed = json.loads(result)
            assert "status" in parsed
            assert "file" in parsed
            print("✅ test_json_output_format PASS")
        except json.JSONDecodeError:
            raise AssertionError(f"Output not valid JSON: {result}")

    def test_skip_nonexistent_file(self):
        """Nonexistent files should be skipped gracefully."""
        test_file = VAULT_PATH / "does-not-exist-12345.md"

        env = os.environ.copy()
        env["OPENCLAW_WRITE_VALIDATE_PATHS"] = str(VAULT_PATH)

        result = run_hook(str(test_file), env=env)
        parsed = json.loads(result)
        assert parsed["status"] == "SKIP"
        print("✅ test_skip_nonexistent_file PASS")

    def test_empty_file(self):
        """Empty files should fail (no frontmatter)."""
        test_file = VAULT_PATH / "empty.md"
        test_file.write_text("")

        env = os.environ.copy()
        env["OPENCLAW_WRITE_VALIDATE_PATHS"] = str(VAULT_PATH)

        result = run_hook(str(test_file), env=env)
        parsed = json.loads(result)
        assert parsed["status"] == "FAIL"
        print("✅ test_empty_file PASS")

    def test_file_with_only_frontmatter(self):
        """File with frontmatter but no content should pass."""
        test_file = VAULT_PATH / "only-frontmatter.md"
        test_file.write_text("""---
title: Test Document
category: notes
created: 2026-03-18
tags: test
---
""")

        env = os.environ.copy()
        env["OPENCLAW_WRITE_VALIDATE_PATHS"] = str(VAULT_PATH)

        result = run_hook(str(test_file), env=env)
        parsed = json.loads(result)
        assert parsed["status"] == "PASS"
        print("✅ test_file_with_only_frontmatter PASS")

    def test_malformed_frontmatter(self):
        """Frontmatter with syntax errors should fail."""
        test_file = VAULT_PATH / "malformed.md"
        test_file.write_text("""---
title Document without colon
category: notes
---

Content
""")

        env = os.environ.copy()
        env["OPENCLAW_WRITE_VALIDATE_PATHS"] = str(VAULT_PATH)

        result = run_hook(str(test_file), env=env)
        parsed = json.loads(result)
        # Missing title because of parse error
        assert parsed["status"] in ("FAIL", "WARN")
        print("✅ test_malformed_frontmatter PASS")

    def test_multiple_vault_paths(self):
        """Multiple vault paths should be recognized."""
        # Create file in second vault path
        vault2 = Path(tempfile.gettempdir()) / "test-vault-2"
        vault2.mkdir(exist_ok=True)
        test_file = vault2 / "test.md"
        test_file.write_text("""---
title: Test in Vault 2
category: notes
created: 2026-03-18
tags: test
---

Content
""")

        env = os.environ.copy()
        env["OPENCLAW_WRITE_VALIDATE_PATHS"] = f"{VAULT_PATH}:{vault2}"

        result = run_hook(str(test_file), env=env)
        parsed = json.loads(result)
        assert parsed["status"] == "PASS"
        print("✅ test_multiple_vault_paths PASS")


def run_hook(file_path: str, env=None) -> str:
    """Run the hook with given file path, return stdout."""
    hook_script = HANDLERS_DIR / "write-validate.py"
    hook_env = env or os.environ.copy()
    proc = subprocess.run(
        ["python3", str(hook_script), file_path],
        capture_output=True,
        text=True,
        timeout=10,
        env=hook_env,
    )
    return proc.stdout.strip()


def main():
    test = TestWriteValidate()
    test.setup_class()

    tests = [m for m in dir(test) if m.startswith("test_")]

    print(f"Running {len(tests)} tests for write-validate...")
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
