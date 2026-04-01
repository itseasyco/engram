#!/usr/bin/env python3
"""Write Validation Hook - OpenClaw adaptation of LACP's write_validate.py

Validates YAML frontmatter schema on files written to knowledge/vault paths.
Only activates for markdown files under configurable knowledge directories.

Exit codes:
  0 - PASS or WARN (non-blocking)
  2 - FAIL (blocking, missing required frontmatter)
"""

import json
import os
import re
import sys
from pathlib import Path

# Configurable knowledge paths (colon-separated)
def _default_vault_root():
    """Resolve vault root from env-source.sh config or fallback."""
    env_file = os.path.expanduser("~/.openclaw/extensions/engram/config/.engram.env")
    if os.path.isfile(env_file):
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line.startswith("LACP_OBSIDIAN_VAULT="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    return os.path.expanduser("~/.openclaw/data/knowledge")

_vault_root = os.environ.get("OPENCLAW_VAULT_ROOT") or _default_vault_root()

KNOWLEDGE_PATHS_ENV = os.environ.get(
    "OPENCLAW_WRITE_VALIDATE_PATHS",
    _vault_root
    + ":"
    + os.environ.get("OPENCLAW_KNOWLEDGE_ROOT", os.path.expanduser("~/.openclaw/knowledge"))
)

TAXONOMY_PATH = os.environ.get(
    "OPENCLAW_TAXONOMY_PATH",
    os.path.join(_vault_root, "_metadata", "taxonomy.json"),
)

REQUIRED_FIELDS = ["title", "category"]
RECOMMENDED_FIELDS = ["created", "tags"]

FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def load_taxonomy_categories() -> set[str]:
    """Load valid category names from taxonomy.json."""
    try:
        data = json.loads(Path(TAXONOMY_PATH).read_text(encoding="utf-8"))
        rules = data.get("classification", {}).get("category_rules", [])
        return {r["name"] for r in rules if isinstance(r, dict) and "name" in r}
    except Exception:
        return set()


def parse_frontmatter(content: str) -> dict | None:
    """Extract YAML frontmatter as a dict (simple key: value parsing)."""
    match = FRONTMATTER_RE.match(content)
    if not match:
        return None

    raw = match.group(1)
    result = {}

    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()
            # Strip quotes
            if value and value[0] in ('"', "'") and value[-1] == value[0]:
                value = value[1:-1]
            result[key] = value

    return result


def is_knowledge_path(file_path: str) -> bool:
    """Check if file is under a knowledge directory."""
    resolved = str(Path(file_path).resolve())
    for kpath in KNOWLEDGE_PATHS_ENV.split(":"):
        kpath = kpath.strip()
        if not kpath:
            continue
        kpath_resolved = str(Path(kpath).resolve())
        if resolved.startswith(kpath_resolved):
            return True
    return False


def validate(file_path: str) -> dict:
    """Validate a file's frontmatter schema."""
    issues = []
    status = "PASS"

    if not file_path.endswith(".md"):
        return {
            "status": "SKIP",
            "file": file_path,
            "issues": [],
            "reason": "not markdown",
        }

    if not is_knowledge_path(file_path):
        return {
            "status": "SKIP",
            "file": file_path,
            "issues": [],
            "reason": "not in knowledge path",
        }

    try:
        content = Path(file_path).read_text(encoding="utf-8")
    except Exception as e:
        return {
            "status": "SKIP",
            "file": file_path,
            "issues": [],
            "reason": str(e),
        }

    fm = parse_frontmatter(content)
    if fm is None:
        return {
            "status": "FAIL",
            "file": file_path,
            "issues": ["No YAML frontmatter found. Expected:\n---\ntitle: ...\ncategory: ...\n---"],
        }

    # Required fields
    for field in REQUIRED_FIELDS:
        if field not in fm or not fm[field]:
            issues.append(f"Missing required field '{field}'")
            status = "FAIL"

    # Recommended fields (WARN only)
    for field in RECOMMENDED_FIELDS:
        if field not in fm or not fm[field]:
            issues.append(f"Missing recommended field '{field}'")
            if status == "PASS":
                status = "WARN"

    # Category validation
    if "category" in fm and fm["category"]:
        categories = load_taxonomy_categories()
        if categories and fm["category"] not in categories:
            issues.append(f"Category '{fm['category']}' not in taxonomy")
            if status == "PASS":
                status = "WARN"

    return {"status": status, "file": file_path, "issues": issues}


def main():
    # When invoked as a hook, read JSON from stdin
    raw = sys.stdin.read() if not sys.stdin.isatty() else ""

    if raw.strip():
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = {}
        # PostToolUse(Write) hook provides tool_input.file_path
        tool_input = data.get("tool_input", {})
        if isinstance(tool_input, dict):
            file_path = tool_input.get("file_path", "")
        else:
            file_path = ""
    elif len(sys.argv) > 1:
        # Direct invocation with file path argument
        file_path = sys.argv[1]
    else:
        print(json.dumps({"status": "SKIP", "reason": "no file path provided"}))
        sys.exit(0)

    if not file_path:
        sys.exit(0)

    result = validate(file_path)
    print(json.dumps(result))

    # Exit code protocol (standardized across all hooks):
    #   0 = allow (PASS or SKIP)
    #   1 = block (FAIL — validation errors that should prevent write)
    #   2 = warn (WARN — non-fatal issues, write proceeds)
    if result["status"] == "FAIL":
        sys.exit(1)
    elif result["status"] == "WARN":
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
