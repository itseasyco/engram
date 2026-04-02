"""
Schema enforcer for the curator engine.

Validates that all notes have required frontmatter fields and adds
missing fields with sensible defaults. Flags malformed notes for review.

Required fields (from spec Section 6):
    title, category, tags, created, updated, author, source, status
"""

import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .consolidation import _parse_frontmatter


# ---------------------------------------------------------------------------
# Schema definition
# ---------------------------------------------------------------------------

REQUIRED_FIELDS = {
    "title": None,        # Derived from filename if missing
    "category": None,     # Derived from folder if missing
    "tags": "[]",         # Empty list
    "created": None,      # Derived from file mtime if missing
    "updated": None,      # Derived from file mtime if missing
    "author": "curator",  # Default author
    "source": "curator",  # Default source
    "status": "active",   # Default status
}

VALID_STATUSES = {"active", "review", "stale", "unverified", "archived"}

def _build_folder_to_category() -> dict[str, str]:
    """Build folder-to-category mapping using vault_paths resolver."""
    try:
        from .vault_paths import resolve
        _key_to_category = {
            "projects": "projects",
            "concepts": "concepts",
            "people": "people",
            "organizations": "organizations",
            "systems": "systems",
            "inbox": "inbox",
            "planning": "planning",
            "research": "research",
            "strategy": "strategy",
            "changelog": "changelog",
            "templates": "templates",
        }
        mapping = {}
        for key, category in _key_to_category.items():
            folder_name = resolve(key).name
            mapping[folder_name] = category
        return mapping
    except (ImportError, KeyError):
        # Fallback to schema-free defaults
        return {
            "projects": "projects",
            "concepts": "concepts",
            "people": "people",
            "systems": "systems",
            "inbox": "inbox",
            "planning": "planning",
            "research": "research",
            "strategy": "strategy",
            "changelog": "changelog",
            "templates": "templates",
        }


FOLDER_TO_CATEGORY = _build_folder_to_category()


# ---------------------------------------------------------------------------
# Frontmatter manipulation
# ---------------------------------------------------------------------------

def _infer_category_from_path(rel_path: str) -> str:
    """Infer category from the note's folder."""
    parts = rel_path.split("/")
    if parts:
        folder = parts[0]
        return FOLDER_TO_CATEGORY.get(folder, "concepts")
    return "concepts"


def _add_missing_frontmatter(content: str, file_path: Path, vault_path: Path) -> tuple:
    """
    Add missing required frontmatter fields to note content.

    Returns:
        (modified_content, list_of_added_fields, list_of_issues)
    """
    added_fields = []
    issues = []

    rel_path = str(file_path.relative_to(vault_path))

    # Check if frontmatter exists
    has_fm = content.startswith("---")

    if not has_fm:
        # No frontmatter at all -- create it
        try:
            mtime = file_path.stat().st_mtime
            created_date = datetime.fromtimestamp(mtime, tz=timezone.utc).strftime("%Y-%m-%d")
        except (OSError, ValueError):
            created_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        title = file_path.stem.replace("-", " ").replace("_", " ").title()
        category = _infer_category_from_path(rel_path)

        fm_lines = [
            f'title: "{title}"',
            f"category: {category}",
            "tags: []",
            f"created: {created_date}",
            f"updated: {created_date}",
            "author: curator",
            "source: curator",
            "status: active",
        ]
        new_fm = "---\n" + "\n".join(fm_lines) + "\n---\n\n"
        added_fields = list(REQUIRED_FIELDS.keys())
        return new_fm + content, added_fields, issues

    # Frontmatter exists -- check for missing fields
    end = content.find("---", 3)
    if end == -1:
        issues.append("malformed_frontmatter")
        return content, added_fields, issues

    fm_text = content[3:end]
    body = content[end + 3:]

    fm = _parse_frontmatter(content)

    # Determine defaults for missing fields
    try:
        mtime = file_path.stat().st_mtime
        file_date = datetime.fromtimestamp(mtime, tz=timezone.utc).strftime("%Y-%m-%d")
    except (OSError, ValueError):
        file_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    defaults = {
        "title": f'"{file_path.stem.replace("-", " ").replace("_", " ").title()}"',
        "category": _infer_category_from_path(rel_path),
        "tags": "[]",
        "created": file_date,
        "updated": file_date,
        "author": "curator",
        "source": "curator",
        "status": "active",
    }

    new_lines = []
    for field, default in defaults.items():
        if field not in fm or fm[field] == "" or fm[field] is None:
            new_lines.append(f"{field}: {default}")
            added_fields.append(field)

    # Validate status field
    status = fm.get("status", "")
    if isinstance(status, str) and status and status not in VALID_STATUSES:
        issues.append(f"invalid_status:{status}")

    if not new_lines:
        return content, added_fields, issues

    # Append missing fields to frontmatter
    fm_text = fm_text.rstrip() + "\n" + "\n".join(new_lines) + "\n"
    return "---" + fm_text + "---" + body, added_fields, issues


# ---------------------------------------------------------------------------
# Main enforcer
# ---------------------------------------------------------------------------

def enforce_schema(
    vault_path: Optional[str] = None,
    dry_run: bool = True,
) -> dict:
    """
    Validate and enforce frontmatter schema on all vault notes.

    Args:
        vault_path: root of the Obsidian vault.
        dry_run: if True, report only.

    Returns:
        dict with total, compliant, fixed, malformed, details.
    """
    if vault_path is None:
        vault_path = os.environ.get(
            "LACP_OBSIDIAN_VAULT",
            os.path.expanduser("~/obsidian/vault"),
        )

    vault = Path(vault_path)
    if not vault.exists():
        return {"error": "vault_not_found", "path": str(vault)}

    total = 0
    compliant = 0
    fixed = 0
    malformed = 0
    details = []

    for md_file in vault.rglob("*.md"):
        rel = md_file.relative_to(vault).as_posix()
        # Skip .obsidian, templates, index files
        if rel.startswith(".obsidian/"):
            continue
        if md_file.name == "index.md" or md_file.stem == "index":
            continue

        try:
            content = md_file.read_text(encoding="utf-8")
        except (IOError, UnicodeDecodeError):
            continue

        total += 1

        modified, added, issues = _add_missing_frontmatter(content, md_file, vault)

        if issues:
            malformed += 1
            details.append({
                "path": rel,
                "action": "malformed",
                "issues": issues,
            })
        elif not added:
            compliant += 1
        else:
            fixed += 1
            if not dry_run:
                md_file.write_text(modified, encoding="utf-8")
            details.append({
                "path": rel,
                "action": "fixed",
                "added_fields": added,
            })

    return {
        "total": total,
        "compliant": compliant,
        "fixed": fixed,
        "malformed": malformed,
        "details": details,
        "dry_run": dry_run,
    }
