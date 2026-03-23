"""
Conflict resolver for the curator engine.

Detects Obsidian Sync conflict files (pattern: "note (conflict YYYY-MM-DD).md"),
attempts auto-merge for non-overlapping changes, and escalates contradicting
changes to human review.
"""

import os
import re
import shutil
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

from .consolidation import _parse_frontmatter


# ---------------------------------------------------------------------------
# Conflict detection
# ---------------------------------------------------------------------------

CONFLICT_PATTERN = re.compile(
    r"^(.+?)\s*\(conflict\s+(\d{4}-\d{2}-\d{2})\)\.md$"
)


def find_conflict_files(vault_path: Path) -> list:
    """
    Find all Obsidian Sync conflict files in the vault.

    Returns:
        list of dicts with: conflict_path, original_stem, conflict_date, original_path.
    """
    conflicts = []

    for md_file in vault_path.rglob("*.md"):
        rel = md_file.relative_to(vault_path).as_posix()
        if rel.startswith(".obsidian/"):
            continue

        match = CONFLICT_PATTERN.match(md_file.name)
        if match:
            original_stem = match.group(1).strip()
            conflict_date = match.group(2)

            # Find the original file in the same directory
            original_path = md_file.parent / f"{original_stem}.md"

            conflicts.append({
                "conflict_path": md_file,
                "original_stem": original_stem,
                "conflict_date": conflict_date,
                "original_path": original_path,
                "original_exists": original_path.exists(),
            })

    return conflicts


# ---------------------------------------------------------------------------
# Auto-merge logic
# ---------------------------------------------------------------------------

def _split_sections(content: str) -> list:
    """
    Split markdown content into sections (by ## headers).

    Returns list of (header_or_empty, body_text) tuples.
    """
    # Split frontmatter from body
    body = content
    frontmatter = ""
    if content.startswith("---"):
        end = content.find("---", 3)
        if end != -1:
            frontmatter = content[:end + 3]
            body = content[end + 3:]

    sections = []
    if frontmatter:
        sections.append(("__frontmatter__", frontmatter))

    # Split body by ## headers
    parts = re.split(r"(?m)^(##\s+.+)$", body)

    # First part (before any header)
    if parts and parts[0].strip():
        sections.append(("__preamble__", parts[0]))

    # Remaining parts come in (header, body) pairs
    i = 1
    while i < len(parts) - 1:
        header = parts[i].strip()
        body_part = parts[i + 1] if i + 1 < len(parts) else ""
        sections.append((header, body_part))
        i += 2

    return sections


def _sections_to_dict(sections: list) -> dict:
    """Convert sections list to dict keyed by header."""
    result = {}
    for header, body in sections:
        result[header] = body
    return result


def attempt_auto_merge(original_content: str, conflict_content: str) -> tuple:
    """
    Attempt to auto-merge two versions of a note.

    Strategy: split both into sections by ## headers. If changes are in
    different sections (non-overlapping), merge by taking the newer version
    of each changed section. If changes overlap in the same section,
    escalate.

    Args:
        original_content: content of the original note.
        conflict_content: content of the conflict copy.

    Returns:
        (success: bool, merged_content_or_None: str|None, conflict_sections: list)
    """
    orig_sections = _split_sections(original_content)
    conf_sections = _split_sections(conflict_content)

    orig_dict = _sections_to_dict(orig_sections)
    conf_dict = _sections_to_dict(conf_sections)

    all_keys = list(dict.fromkeys(
        [k for k, _ in orig_sections] + [k for k, _ in conf_sections]
    ))

    merged_sections = []
    conflict_keys = []
    changed_keys = []

    for key in all_keys:
        orig_val = orig_dict.get(key, "")
        conf_val = conf_dict.get(key, "")

        if orig_val == conf_val:
            # No change in this section
            merged_sections.append((key, orig_val))
        elif key not in orig_dict:
            # New section in conflict copy
            merged_sections.append((key, conf_val))
        elif key not in conf_dict:
            # Section removed in conflict copy -- keep original
            merged_sections.append((key, orig_val))
        else:
            # Section differs -- check severity
            ratio = SequenceMatcher(None, orig_val, conf_val).ratio()
            changed_keys.append((key, ratio))
            if ratio < 0.5:
                # Drastic rewrite -- escalate regardless
                conflict_keys.append(key)
                merged_sections.append((key, orig_val))
            else:
                # Moderate change -- take conflict version (auto-merge)
                merged_sections.append((key, conf_val))

    if conflict_keys:
        return False, None, conflict_keys

    # Reconstruct merged content
    merged_parts = []
    for key, body in merged_sections:
        if key == "__frontmatter__":
            merged_parts.append(body)
        elif key == "__preamble__":
            merged_parts.append(body)
        else:
            merged_parts.append(f"\n{key}{body}")

    merged = "".join(merged_parts)
    return True, merged, []


# ---------------------------------------------------------------------------
# Main resolver
# ---------------------------------------------------------------------------

def resolve_conflicts(
    vault_path: Optional[str] = None,
    dry_run: bool = True,
) -> dict:
    """
    Detect and resolve Obsidian Sync conflict files.

    Args:
        vault_path: root of the Obsidian vault.
        dry_run: if True, report only.

    Returns:
        dict with found, auto_merged, escalated, orphaned, details.
    """
    if vault_path is None:
        vault_path = os.environ.get(
            "LACP_OBSIDIAN_VAULT",
            os.path.expanduser("~/obsidian/vault"),
        )

    vault = Path(vault_path)
    conflicts = find_conflict_files(vault)

    auto_merged = 0
    escalated = 0
    orphaned = 0
    details = []

    review_dir = vault / "05_Inbox" / "review-conflicts"

    for conflict in conflicts:
        conflict_path = conflict["conflict_path"]
        original_path = conflict["original_path"]

        if not conflict["original_exists"]:
            # Original was deleted -- rename conflict to original
            orphaned += 1
            if not dry_run:
                shutil.move(str(conflict_path), str(original_path))
            details.append({
                "conflict": str(conflict_path.relative_to(vault)),
                "action": "renamed_to_original",
                "original": str(original_path.relative_to(vault)),
            })
            continue

        try:
            original_content = original_path.read_text(encoding="utf-8")
            conflict_content = conflict_path.read_text(encoding="utf-8")
        except (IOError, UnicodeDecodeError):
            escalated += 1
            details.append({
                "conflict": str(conflict_path.relative_to(vault)),
                "action": "escalated",
                "reason": "unreadable",
            })
            continue

        success, merged, conflict_sections = attempt_auto_merge(
            original_content, conflict_content,
        )

        if success and merged is not None:
            auto_merged += 1
            if not dry_run:
                original_path.write_text(merged, encoding="utf-8")
                conflict_path.unlink()
            details.append({
                "conflict": str(conflict_path.relative_to(vault)),
                "action": "auto_merged",
                "original": str(original_path.relative_to(vault)),
            })
        else:
            escalated += 1
            if not dry_run:
                review_dir.mkdir(parents=True, exist_ok=True)
                # Move conflict file to review
                dest = review_dir / conflict_path.name
                shutil.move(str(conflict_path), str(dest))
            details.append({
                "conflict": str(conflict_path.relative_to(vault)),
                "action": "escalated",
                "conflict_sections": conflict_sections,
                "original": str(original_path.relative_to(vault)),
            })

    return {
        "found": len(conflicts),
        "auto_merged": auto_merged,
        "escalated": escalated,
        "orphaned": orphaned,
        "details": details,
        "dry_run": dry_run,
    }
