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

# Meeting sub-classification folders
MEETING_FOLDERS = {
    "meetings/team": "meetings/team",
    "meetings/investors": "meetings/investors",
    "meetings/clients": "meetings/clients",
    "meetings/conference": "meetings/conference",
    "meetings/personal": "meetings/personal",
    "meetings/external": "meetings/external",
}

# Session folder
SESSION_FOLDER = "sessions"

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
# Structural detection (meetings, sessions, PRDs)
# ---------------------------------------------------------------------------

# Known internal team members (lowercase)
_TEAM_MEMBERS = {
    "niko lemieux", "andrew fisher", "evan goldberg", "ari shaller",
    "chad green", "danie beukman",
}

_NOTETAKER_PATTERNS = [
    "notetaker", "fireflies", "read.ai", "circleback", "otter.ai",
    "participant ",
]

_INVESTOR_KEYWORDS = [
    "investor", "fundrais", "pitch", "valuation", "safe", "term sheet",
    "cap table", "round", "pre-seed", "seed", "series a", "vc ", "venture",
    "deck", "due diligence",
]

_CLIENT_KEYWORDS = [
    "merchant", "onboard", "settlement", "payment", "processing", "volume",
    "transaction", "integration", "demo", "walkthrough", "pricing",
    "contract", "sow", "pilot",
]

_MEETING_MARKERS = [
    ("**Attendees:**", "**Duration:**"),
    ("Attendees:", "Duration:"),
    ("**Participants:**", "**Duration:**"),
]

_DAILY_NOTE_RE = re.compile(r'^# \d{4}-\d{2}-\d{2}')
_SESSION_MARKERS = ["## Session", "## First Session", "came online", "woke up"]


def _is_internal(name: str) -> bool:
    """Check if a participant is internal team or a bot."""
    n = name.lower().strip()
    if n in _TEAM_MEMBERS:
        return True
    for pat in _NOTETAKER_PATTERNS:
        if pat in n:
            return True
    return False


def _classify_meeting(title: str, body: str, attendees_raw: str) -> str:
    """Sub-classify a meeting by participant context."""
    attendees = [a.strip() for a in attendees_raw.split(",") if a.strip()]
    external = [a for a in attendees if not _is_internal(a)]

    title_lower = title.lower()
    content_lower = body[:3000].lower()

    if len(attendees) > 15:
        return "meetings/conference"
    if "family" in title_lower or "personal" in title_lower:
        return "meetings/personal"
    if len(external) == 0:
        return "meetings/team"
    if any(kw in content_lower for kw in _INVESTOR_KEYWORDS):
        return "meetings/investors"
    if any(kw in content_lower for kw in _CLIENT_KEYWORDS):
        return "meetings/clients"
    return "meetings/external"


def _extract_meeting_attendees(content: str) -> str | None:
    """Extract raw attendees string from meeting content."""
    for attendee_marker, duration_marker in _MEETING_MARKERS:
        if attendee_marker in content and duration_marker in content:
            m = re.search(re.escape(attendee_marker) + r'\s*(.+?)(?:\n|$)', content)
            if m:
                return m.group(1)
    return None


def _detect_structural_type(title: str, body: str) -> tuple[str | None, str | None]:
    """
    Detect note type by content structure.

    Returns (category, attendees_raw) — category is a folder path like
    "meetings/investors" or "sessions", attendees_raw is set for meetings.
    """
    content = body[:3000]

    # ── Meetings ──────────────────────────────────────────────────────
    attendees_raw = _extract_meeting_attendees(content)
    if not attendees_raw and re.match(r'^\d{4}[\s-]\d{2}[\s-]\d{2}[\s-]', title):
        m = re.search(r'Attendees:\s*(.+?)(?:\n|$)', content)
        if m:
            attendees_raw = m.group(1)

    if attendees_raw is not None:
        cat = _classify_meeting(title, content, attendees_raw)
        return cat, attendees_raw

    # ── Agent session/daily notes ─────────────────────────────────────
    if _DAILY_NOTE_RE.match(body.strip()):
        for marker in _SESSION_MARKERS:
            if marker in content:
                return "sessions", None

    return None, None


# ---------------------------------------------------------------------------
# People profile extraction from meetings
# ---------------------------------------------------------------------------

def _slugify(name: str) -> str:
    """Convert a person's name to a filename-safe slug."""
    return re.sub(r'[^\w\s-]', '', name.strip().lower()).replace(' ', '-')


def _extract_people_from_meeting(
    title: str,
    body: str,
    attendees_raw: str,
    meeting_file: Path,
    vault_path: Path,
    dry_run: bool = True,
) -> list[str]:
    """
    Extract external participants from a meeting and create/update people profiles.

    Returns list of people profile paths created or updated.
    """
    attendees = [a.strip() for a in attendees_raw.split(",") if a.strip()]
    external = [a for a in attendees if not _is_internal(a)]
    if not external:
        return []

    people_dir = vault_path / "people"
    updated = []

    for person in external:
        slug = _slugify(person)
        if not slug or len(slug) < 2:
            continue

        profile_path = people_dir / f"{slug}.md"
        meeting_link = f"[[{meeting_file.stem}]]"

        # Extract any action items or notes mentioning this person
        person_mentions = []
        for line in body.split("\n"):
            if person.lower() in line.lower() and len(line.strip()) > 10:
                clean = line.strip().lstrip("*-• ").strip()
                if clean:
                    person_mentions.append(clean)

        if dry_run:
            updated.append(str(profile_path.relative_to(vault_path)))
            continue

        people_dir.mkdir(parents=True, exist_ok=True)

        if profile_path.exists():
            # Append meeting reference if not already there
            try:
                existing = profile_path.read_text(encoding="utf-8")
                if meeting_link not in existing:
                    # Add to meetings section
                    meeting_entry = f"\n- {meeting_link} — {title}"
                    if person_mentions:
                        meeting_entry += f"\n  - {person_mentions[0][:120]}"
                    existing += meeting_entry + "\n"
                    profile_path.write_text(existing, encoding="utf-8")
                    updated.append(str(profile_path.relative_to(vault_path)))
            except (IOError, UnicodeDecodeError):
                pass
        else:
            # Create new profile
            date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            content_lines = [
                "---",
                f'title: "{person}"',
                "category: people",
                "tags: []",
                f"created: {date_str}",
                f"updated: {date_str}",
                "author: curator",
                "source: meeting-extraction",
                "status: active",
                "---",
                "",
                f"# {person}",
                "",
                "## Context",
                "",
                f"First encountered in: {meeting_link}",
                "",
                "## Meetings",
                "",
                f"- {meeting_link} — {title}",
            ]
            if person_mentions:
                content_lines.append(f"  - {person_mentions[0][:120]}")

            content_lines.append("")
            profile_path.write_text("\n".join(content_lines), encoding="utf-8")
            updated.append(str(profile_path.relative_to(vault_path)))

    return updated


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

    # Structural detection first (meetings, sessions)
    attendees_raw = None
    if not category:
        structural_cat, attendees_raw = _detect_structural_type(title, body)
        if structural_cat:
            category = structural_cat

    # Keyword-based fallback
    if not category:
        category = _infer_category(title, body, tags)

    # Determine target folder
    if category in MEETING_FOLDERS:
        target_folder = MEETING_FOLDERS[category]
    elif category == "sessions":
        target_folder = SESSION_FOLDER
    else:
        target_folder = CATEGORY_FOLDER_MAP.get(category, CATEGORY_FOLDER_MAP.get("concepts", "concepts"))
    if category == "projects" and project:
        target_folder = f"{CATEGORY_FOLDER_MAP.get('projects', 'projects')}/{project}"

    # Meetings with attendees are auto-promoted (structured data = high trust)
    auto_promote = TRUST_AUTO_PROMOTE.get(trust_level, False)
    if category.startswith("meetings/"):
        auto_promote = True
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
        "attendees_raw": attendees_raw,
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
                dest = target_dir / md_file.name
                if not dry_run:
                    target_dir.mkdir(parents=True, exist_ok=True)
                    # Avoid overwriting
                    if dest.exists():
                        stem = md_file.stem
                        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
                        dest = target_dir / f"{stem}-{ts}.md"
                    shutil.move(str(md_file), str(dest))

                # Extract people profiles from meetings
                attendees_raw = classification.get("attendees_raw")
                people_updated = []
                if attendees_raw and classification["category"].startswith("meetings/"):
                    try:
                        content = dest.read_text(encoding="utf-8") if not dry_run else md_file.read_text(encoding="utf-8")
                        body = content
                        if content.startswith("---"):
                            end = content.find("---", 3)
                            if end != -1:
                                body = content[end + 3:]
                        people_updated = _extract_people_from_meeting(
                            title=classification["title"],
                            body=body,
                            attendees_raw=attendees_raw,
                            meeting_file=dest if not dry_run else md_file,
                            vault_path=vault,
                            dry_run=dry_run,
                        )
                    except (IOError, UnicodeDecodeError):
                        pass

                results["promoted"] += 1
                detail = {
                    "file": str(md_file.relative_to(vault)),
                    "action": "promoted",
                    "target": classification["target_folder"],
                    "category": classification["category"],
                    "trust": classification["trust_level"],
                }
                if people_updated:
                    detail["people_profiles"] = people_updated
                results["details"].append(detail)
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
