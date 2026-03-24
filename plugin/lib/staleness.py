"""
Staleness scanner for the curator engine.

Computes staleness scores for all notes using the formula:
    staleness_score = days_since_traversed / (traversal_count + 1)

Applies threshold-based actions:
    < 10:   active (no action)
    10-30:  aging (monitor)
    30-90:  stale (flag, check contradictions)
    > 90:   review needed (move to review-stale/)
"""

import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .consolidation import _parse_frontmatter


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

STALENESS_ACTIVE = "active"         # < 10
STALENESS_AGING = "aging"           # 10-30
STALENESS_STALE = "stale"           # 30-90
STALENESS_REVIEW = "review_needed"  # > 90


def classify_staleness(score: float) -> str:
    """Classify a staleness score into a category."""
    if score < 10:
        return STALENESS_ACTIVE
    elif score < 30:
        return STALENESS_AGING
    elif score < 90:
        return STALENESS_STALE
    else:
        return STALENESS_REVIEW


# ---------------------------------------------------------------------------
# Score computation
# ---------------------------------------------------------------------------

def compute_staleness_score(
    last_traversed: str,
    traversal_count: int,
    now: Optional[datetime] = None,
) -> float:
    """
    Compute staleness score for a note.

    Formula: days_since_traversed / (traversal_count + 1)

    Args:
        last_traversed: ISO date string (e.g., "2026-03-15").
        traversal_count: number of times this note has been traversed.
        now: current datetime (defaults to utcnow).

    Returns:
        float >= 0. Lower is fresher.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    if not last_traversed:
        # Never traversed: treat as maximally stale
        return 999.0

    try:
        # Handle date-only and datetime formats
        if "T" in last_traversed:
            clean = last_traversed.replace("Z", "+00:00")
            if "+" not in clean and "-" not in clean[10:]:
                clean += "+00:00"
            dt = datetime.fromisoformat(clean)
        else:
            dt = datetime.strptime(last_traversed[:10], "%Y-%m-%d")
            dt = dt.replace(tzinfo=timezone.utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return 999.0

    days_since = max(0.0, (now - dt).total_seconds() / 86400.0)
    return days_since / (traversal_count + 1)


# ---------------------------------------------------------------------------
# Frontmatter update
# ---------------------------------------------------------------------------

def _update_status_in_content(content: str, new_status: str) -> str:
    """Update the status field in frontmatter."""
    if not content.startswith("---"):
        return content

    end = content.find("---", 3)
    if end == -1:
        return content

    fm_section = content[3:end]
    body = content[end:]

    # Update or add status field
    status_pat = re.compile(r"(?m)^status:\s*.*$")
    if status_pat.search(fm_section):
        fm_section = status_pat.sub(f"status: {new_status}", fm_section)
    else:
        fm_section = fm_section.rstrip() + f"\nstatus: {new_status}\n"

    return "---" + fm_section + body


# ---------------------------------------------------------------------------
# Main scan
# ---------------------------------------------------------------------------

def scan_staleness(
    vault_path: Optional[str] = None,
    dry_run: bool = True,
    now: Optional[datetime] = None,
) -> dict:
    """
    Scan all vault notes for staleness and apply threshold actions.

    Actions:
    - stale (30-90): set status to 'stale' in frontmatter.
    - review_needed (>90): move to 05_Inbox/review-stale/.

    Args:
        vault_path: root of the Obsidian vault.
        dry_run: if True, report only.
        now: current datetime for testing.

    Returns:
        dict with distribution counts, flagged notes, moved notes.
    """
    if vault_path is None:
        vault_path = os.environ.get(
            "LACP_OBSIDIAN_VAULT",
            os.path.expanduser("~/obsidian/vault"),
        )

    vault = Path(vault_path)
    if not vault.exists():
        return {"error": "vault_not_found", "path": str(vault)}

    distribution = {
        STALENESS_ACTIVE: 0,
        STALENESS_AGING: 0,
        STALENESS_STALE: 0,
        STALENESS_REVIEW: 0,
    }
    flagged = []
    moved = []
    total = 0

    review_dir = vault / "05_Inbox" / "review-stale"

    for md_file in vault.rglob("*.md"):
        rel = md_file.relative_to(vault).as_posix()
        # Skip system dirs, inbox, archive, and .obsidian
        if any(rel.startswith(p) for p in (
            ".obsidian/", "99_Archive/", "05_Inbox/", "10_Templates/",
            "00_Index",
        )):
            continue

        try:
            content = md_file.read_text(encoding="utf-8")
        except (IOError, UnicodeDecodeError):
            continue

        fm = _parse_frontmatter(content)
        total += 1

        last_traversed = fm.get("last_traversed", fm.get("updated", ""))
        if isinstance(last_traversed, (int, float)):
            last_traversed = str(last_traversed)
        traversal_count = fm.get("traversal_count", fm.get("count", 0))
        if not isinstance(traversal_count, int):
            try:
                traversal_count = int(traversal_count)
            except (ValueError, TypeError):
                traversal_count = 0

        score = compute_staleness_score(str(last_traversed), traversal_count, now=now)
        classification = classify_staleness(score)
        distribution[classification] += 1

        if classification == STALENESS_STALE:
            flagged.append({
                "note": md_file.stem,
                "path": rel,
                "score": round(score, 2),
                "classification": classification,
            })
            if not dry_run:
                updated = _update_status_in_content(content, "stale")
                if updated != content:
                    md_file.write_text(updated, encoding="utf-8")

        elif classification == STALENESS_REVIEW:
            moved.append({
                "note": md_file.stem,
                "path": rel,
                "score": round(score, 2),
                "classification": classification,
            })
            if not dry_run:
                # Update status first
                updated = _update_status_in_content(content, "review")
                md_file.write_text(updated, encoding="utf-8")
                # Move to review-stale
                review_dir.mkdir(parents=True, exist_ok=True)
                dest = review_dir / md_file.name
                if dest.exists():
                    dest = review_dir / f"{md_file.stem}-{int(datetime.now(timezone.utc).timestamp())}.md"
                shutil.move(str(md_file), str(dest))

    return {
        "total_scanned": total,
        "distribution": distribution,
        "flagged_stale": flagged,
        "moved_to_review": moved,
        "dry_run": dry_run,
    }
