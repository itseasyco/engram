"""
Inbox processor for the curator engine.

Classifies notes from queue-* folders in the inbox, determines target folder
based on content analysis (category, tags, trust level), and moves notes to
their destination in the organized graph.
"""

import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .consolidation import _parse_frontmatter


# ---------------------------------------------------------------------------
# Category -> folder mapping
# ---------------------------------------------------------------------------

def _build_category_folder_map() -> dict[str, str]:
    """Build category-to-folder mapping using vault_paths resolver."""
    try:
        from .vault_paths import resolve, root
        vault_root = root()
        _keys = [
            "projects", "concepts", "people", "systems",
            "planning", "research", "strategy", "changelog", "templates",
        ]
        mapping = {}
        for key in _keys:
            resolved = resolve(key)
            mapping[key] = str(resolved.relative_to(vault_root))
        return mapping
    except (ImportError, KeyError):
        return {
            "projects": "projects",
            "concepts": "concepts",
            "people": "people",
            "systems": "systems",
            "planning": "planning",
            "research": "research",
            "strategy": "strategy",
            "changelog": "changelog",
            "templates": "templates",
        }


CATEGORY_FOLDER_MAP = _build_category_folder_map()

# Trust level -> auto-promote threshold
TRUST_AUTO_PROMOTE = {
    "verified": True,
    "high": True,
    "medium": False,
    "low": False,
}

# Keywords used for category inference when frontmatter is missing
CATEGORY_KEYWORDS = {
    "projects": [
        "repo", "repository", "codebase", "pr ", "pull request", "branch",
        "deploy", "feature", "sprint", "backlog",
    ],
    "concepts": [
        "pattern", "architecture", "design", "principle", "convention",
        "best practice", "standard", "approach",
    ],
    "people": [
        "team", "member", "role", "responsibility", "contact", "onboard",
    ],
    "systems": [
        "infrastructure", "server", "database", "deployment", "monitoring",
        "ci/cd", "pipeline", "docker", "kubernetes",
    ],
    "planning": [
        "roadmap", "milestone", "timeline", "priority", "objective",
        "quarter", "okr", "goal",
    ],
    "research": [
        "evaluation", "comparison", "benchmark", "competitor", "market",
        "analysis", "finding",
    ],
    "strategy": [
        "vision", "direction", "fundrais", "investor", "partnership",
        "hiring", "growth",
    ],
    "changelog": [
        "release", "version", "changelog", "deploy", "hotfix", "rollback",
    ],
}


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

def classify_note(file_path: Path, vault_path: Path) -> dict:
    """
    Classify an inbox note to determine its target folder and metadata.

    Args:
        file_path: path to the note file.
        vault_path: root of the Obsidian vault.

    Returns:
        dict with keys: category, target_folder, trust_level, tags,
        title, project, auto_promote, needs_review, reason.
    """
    try:
        content = file_path.read_text(encoding="utf-8")
    except (IOError, UnicodeDecodeError):
        return {
            "category": "inbox",
            "target_folder": "inbox",
            "trust_level": "low",
            "tags": [],
            "title": file_path.stem,
            "project": "",
            "auto_promote": False,
            "needs_review": True,
            "reason": "unreadable_file",
        }

    fm = _parse_frontmatter(content)
    body = content
    # Strip frontmatter from body for keyword analysis
    if content.startswith("---"):
        end = content.find("---", 3)
        if end != -1:
            body = content[end + 3:]

    # Extract from frontmatter if available
    category = fm.get("category", "")
    trust_level = fm.get("trust_level", _infer_trust_from_queue(file_path))
    tags = fm.get("tags", [])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    title = fm.get("title", file_path.stem)
    project = fm.get("project", "")
    source = fm.get("source", "")

    # Infer category from content if not in frontmatter
    if not category:
        category = _infer_category(title, body, tags)

    # Determine target folder
    target_folder = CATEGORY_FOLDER_MAP.get(category, CATEGORY_FOLDER_MAP.get("concepts", "concepts"))
    if category == "projects" and project:
        target_folder = f"{CATEGORY_FOLDER_MAP.get('projects', 'projects')}/{project}"

    # Auto-promote decision
    auto_promote = TRUST_AUTO_PROMOTE.get(trust_level, False)
    needs_review = not auto_promote

    return {
        "category": category or "concepts",
        "target_folder": target_folder,
        "trust_level": trust_level,
        "tags": tags,
        "title": title,
        "project": project,
        "auto_promote": auto_promote,
        "needs_review": needs_review,
        "reason": "classified",
    }


def _infer_trust_from_queue(file_path: Path) -> str:
    """Infer trust level from the queue folder name."""
    parts = file_path.parts
    for part in parts:
        if part == "queue-agent":
            return "high"
        elif part == "queue-cicd":
            return "verified"
        elif part == "queue-human":
            return "medium"
        elif part == "queue-external":
            return "low"
    return "medium"


def _infer_category(title: str, body: str, tags: list) -> str:
    """Infer category from title, body text, and tags using keyword matching."""
    text = f"{title} {body}".lower()
    tag_text = " ".join(t.lower() for t in tags)
    combined = f"{text} {tag_text}"

    scores = {}
    for category, keywords in CATEGORY_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in combined)
        if score > 0:
            scores[category] = score

    if not scores:
        return "concepts"  # default

    return max(scores, key=scores.get)


# ---------------------------------------------------------------------------
# Processing
# ---------------------------------------------------------------------------

def process_inbox(vault_path: Optional[str] = None, dry_run: bool = True) -> dict:
    """
    Process all notes in queue-* folders under the inbox.

    Args:
        vault_path: root of the Obsidian vault.
        dry_run: if True, report what would be done without moving files.

    Returns:
        dict with processed, promoted, held, errors, and details list.
    """
    if vault_path is None:
        vault_path = os.environ.get(
            "LACP_OBSIDIAN_VAULT",
            os.path.expanduser("~/obsidian/vault"),
        )

    vault = Path(vault_path)
    try:
        from .vault_paths import resolve
        inbox = resolve("inbox")
    except (ImportError, KeyError):
        inbox = vault / "inbox"

    if not inbox.exists():
        return {
            "processed": 0,
            "promoted": 0,
            "held": 0,
            "errors": 0,
            "details": [],
        }

    results = {
        "processed": 0,
        "promoted": 0,
        "held": 0,
        "errors": 0,
        "details": [],
    }

    # Find all queue-* directories
    queue_dirs = sorted(
        d for d in inbox.iterdir()
        if d.is_dir() and d.name.startswith("queue-")
    )

    for queue_dir in queue_dirs:
        for md_file in sorted(queue_dir.glob("*.md")):
            if md_file.name == "index.md":
                continue

            results["processed"] += 1

            try:
                classification = classify_note(md_file, vault)
            except Exception as exc:
                results["errors"] += 1
                results["details"].append({
                    "file": str(md_file.relative_to(vault)),
                    "action": "error",
                    "reason": str(exc),
                })
                continue

            if classification["auto_promote"]:
                target_dir = vault / classification["target_folder"]
                if not dry_run:
                    target_dir.mkdir(parents=True, exist_ok=True)
                    dest = target_dir / md_file.name
                    # Avoid overwriting
                    if dest.exists():
                        stem = md_file.stem
                        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
                        dest = target_dir / f"{stem}-{ts}.md"
                    shutil.move(str(md_file), str(dest))
                results["promoted"] += 1
                results["details"].append({
                    "file": str(md_file.relative_to(vault)),
                    "action": "promoted",
                    "target": classification["target_folder"],
                    "category": classification["category"],
                    "trust": classification["trust_level"],
                })
            else:
                results["held"] += 1
                results["details"].append({
                    "file": str(md_file.relative_to(vault)),
                    "action": "held",
                    "target": classification["target_folder"],
                    "category": classification["category"],
                    "trust": classification["trust_level"],
                    "reason": "needs_review",
                })

    return results
