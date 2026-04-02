"""
Entity profile manager for Engram.

Creates and accumulates person and organization profiles in the vault.
Principle: accumulate, never overwrite. Each interaction adds new entries
to the profile — meetings attended, topics discussed, sentiments, relationships.

People:  people/{sub}/{slug}.md   (sub = team, investors, clients, personal, external)
Orgs:    organizations/{slug}.md
"""

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .consolidation import _parse_frontmatter
from .entity_extractor import _slugify, resolve_entity

logger = logging.getLogger("entity_profiles")


# ---------------------------------------------------------------------------
# Team members (used to classify people into subfolders)
# ---------------------------------------------------------------------------

_TEAM_MEMBERS = {
    "andrew fisher", "niko lemieux", "evan goldberg",
    "ari shaller", "chad green", "danie beukman",
}

_INVESTOR_KEYWORDS = {
    "investor", "venture", "capital", "vc", "fund", "partner",
    "general partner", "managing partner", "limited partner", "lp",
    "a16z", "andreessen", "y combinator", "sequoia", "fundrais",
}

_CLIENT_KEYWORDS = {
    "client", "customer", "merchant", "user", "subscriber",
    "enterprise", "smb", "account",
}


def _classify_person(name: str, org: str = "", role: str = "", context: str = "") -> str:
    """Determine which people/ subfolder this person belongs in."""
    if name.lower() in _TEAM_MEMBERS:
        return "team"

    combined = f"{org} {role} {context}".lower()
    if any(kw in combined for kw in _INVESTOR_KEYWORDS):
        return "investors"
    if any(kw in combined for kw in _CLIENT_KEYWORDS):
        return "clients"
    return "external"


# ---------------------------------------------------------------------------
# Profile templates
# ---------------------------------------------------------------------------

def _person_frontmatter(name: str, subfolder: str, org: str = "", role: str = "") -> str:
    """Generate frontmatter for a new person profile."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    fm = {
        "title": name,
        "category": "people",
        "subcategory": subfolder,
        "tags": ["person"],
        "created": now,
        "updated": now,
        "status": "active",
        "type": "person-profile",
    }
    if org:
        fm["organization"] = org
        fm["tags"].append(org.lower().replace(" ", "-"))
    if role:
        fm["role"] = role

    lines = ["---"]
    for key, val in fm.items():
        if isinstance(val, list):
            lines.append(f"{key}: {json.dumps(val)}")
        else:
            lines.append(f"{key}: \"{val}\"" if isinstance(val, str) else f"{key}: {val}")
    lines.append("---")
    return "\n".join(lines)


def _person_body(name: str, org: str = "", role: str = "") -> str:
    """Generate initial body for a new person profile."""
    parts = [f"# {name}\n"]
    if org:
        parts.append(f"**Organization:** [[{org}]]")
    if role:
        parts.append(f"**Role:** {role}")
    parts.append("")
    parts.append("## Context\n")
    parts.append("## Meetings\n")
    parts.append("## Key Topics\n")
    parts.append("## Relationships\n")
    parts.append("## Sentiment Log\n")
    parts.append("## Notes\n")
    return "\n".join(parts)


def _org_frontmatter(name: str) -> str:
    """Generate frontmatter for a new organization profile."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = [
        "---",
        f'title: "{name}"',
        'category: "organizations"',
        f'tags: ["organization"]',
        f'created: "{now}"',
        f'updated: "{now}"',
        'status: "active"',
        'type: "org-profile"',
        "---",
    ]
    return "\n".join(lines)


def _org_body(name: str) -> str:
    """Generate initial body for a new organization profile."""
    return "\n".join([
        f"# {name}\n",
        "## Overview\n",
        "## People\n",
        "## Meetings\n",
        "## Portfolio Companies\n",
        "## Relationships\n",
        "## Strategic Notes\n",
    ])


# ---------------------------------------------------------------------------
# Profile creation
# ---------------------------------------------------------------------------

def ensure_person_profile(
    name: str,
    vault_path: Optional[str] = None,
    org: str = "",
    role: str = "",
    context: str = "",
) -> Path:
    """
    Ensure a person profile exists; create if not.

    Args:
        name: canonical person name.
        vault_path: vault root.
        org: organization name.
        role: person's role/title.
        context: additional context for classification.

    Returns:
        Path to the person's profile.
    """
    if vault_path is None:
        try:
            from .vault_paths import root
            vault_path = str(root())
        except (ImportError, KeyError):
            vault_path = os.environ.get("LACP_OBSIDIAN_VAULT", os.path.expanduser("~/obsidian/vault"))

    vault = Path(vault_path)
    slug = _slugify(name)
    subfolder = _classify_person(name, org, role, context)

    # Check if profile already exists anywhere in people/
    people_dir = vault / "people"
    for sub in people_dir.iterdir() if people_dir.exists() else []:
        if sub.is_dir():
            candidate = sub / f"{slug}.md"
            if candidate.exists():
                return candidate

    # Create new profile
    target_dir = vault / "people" / subfolder
    target_dir.mkdir(parents=True, exist_ok=True)
    profile_path = target_dir / f"{slug}.md"

    fm = _person_frontmatter(name, subfolder, org, role)
    body = _person_body(name, org, role)
    profile_path.write_text(f"{fm}\n\n{body}", encoding="utf-8")
    logger.info("Created person profile: %s", profile_path)

    return profile_path


def ensure_org_profile(
    name: str,
    vault_path: Optional[str] = None,
    context: str = "",
) -> Path:
    """
    Ensure an organization profile exists; create if not.

    Args:
        name: canonical organization name.
        vault_path: vault root.
        context: additional context.

    Returns:
        Path to the organization's profile.
    """
    if vault_path is None:
        try:
            from .vault_paths import root
            vault_path = str(root())
        except (ImportError, KeyError):
            vault_path = os.environ.get("LACP_OBSIDIAN_VAULT", os.path.expanduser("~/obsidian/vault"))

    vault = Path(vault_path)
    slug = _slugify(name)

    orgs_dir = vault / "organizations"
    profile_path = orgs_dir / f"{slug}.md"
    if profile_path.exists():
        return profile_path

    # Create new profile
    orgs_dir.mkdir(parents=True, exist_ok=True)
    fm = _org_frontmatter(name)
    body = _org_body(name)
    profile_path.write_text(f"{fm}\n\n{body}", encoding="utf-8")
    logger.info("Created org profile: %s", profile_path)

    return profile_path


# ---------------------------------------------------------------------------
# Profile accumulation
# ---------------------------------------------------------------------------

def accumulate_meeting(
    profile_path: Path,
    meeting_date: str,
    meeting_title: str,
    meeting_slug: str,
    topics: Optional[list[str]] = None,
    sentiment: str = "",
    notes: str = "",
):
    """
    Add a meeting entry to a person or org profile.

    Accumulates under ## Meetings. Never overwrites existing entries.
    """
    if not profile_path.exists():
        logger.warning("Profile not found: %s", profile_path)
        return

    content = profile_path.read_text(encoding="utf-8")

    # Check if this meeting is already recorded
    if meeting_slug in content:
        return  # Already accumulated

    # Build meeting entry
    entry_lines = [f"- **{meeting_date}** — [[{meeting_slug}|{meeting_title}]]"]
    if topics:
        linked_topics = ", ".join(f"[[{t}]]" if not t.startswith("[[") else t for t in topics[:5])
        entry_lines.append(f"  - Topics: {linked_topics}")
    if sentiment:
        entry_lines.append(f"  - Sentiment: {sentiment}")
    if notes:
        entry_lines.append(f"  - {notes}")
    entry = "\n".join(entry_lines)

    # Insert under ## Meetings
    content = _append_to_section(content, "Meetings", entry)

    # Update frontmatter 'updated' field
    content = _update_frontmatter_field(content, "updated", meeting_date)

    profile_path.write_text(content, encoding="utf-8")


def accumulate_topic(profile_path: Path, topic: str):
    """Add a topic under ## Key Topics if not already present."""
    if not profile_path.exists():
        return

    content = profile_path.read_text(encoding="utf-8")
    if f"[[{topic}]]" in content:
        return

    entry = f"- [[{topic}]]"
    content = _append_to_section(content, "Key Topics", entry)
    profile_path.write_text(content, encoding="utf-8")


def accumulate_sentiment(
    profile_path: Path,
    date: str,
    sentiment: str,
    context: str = "",
):
    """Add a sentiment log entry under ## Sentiment Log."""
    if not profile_path.exists():
        return

    content = profile_path.read_text(encoding="utf-8")

    entry = f"- **{date}**: {sentiment}"
    if context:
        entry += f" — {context}"

    content = _append_to_section(content, "Sentiment Log", entry)
    profile_path.write_text(content, encoding="utf-8")


def accumulate_context(profile_path: Path, context_line: str):
    """Add a context line under ## Context if not already present."""
    if not profile_path.exists():
        return

    content = profile_path.read_text(encoding="utf-8")
    if context_line in content:
        return

    entry = f"- {context_line}"
    content = _append_to_section(content, "Context", entry)
    profile_path.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _append_to_section(content: str, section_name: str, entry: str) -> str:
    """Append entry under a ## section. Creates section if missing."""
    pattern = re.compile(rf"^(## {re.escape(section_name)}\s*\n)", re.MULTILINE)
    match = pattern.search(content)

    if match:
        # Find the end of this section (next ## or end of file)
        section_start = match.end()
        next_section = re.search(r"^## ", content[section_start:], re.MULTILINE)
        if next_section:
            insert_pos = section_start + next_section.start()
        else:
            insert_pos = len(content)

        # Insert before next section (with blank line)
        content = content[:insert_pos].rstrip() + "\n" + entry + "\n\n" + content[insert_pos:].lstrip("\n")
    else:
        # Section doesn't exist — append at end
        content = content.rstrip() + f"\n\n## {section_name}\n\n{entry}\n"

    return content


def _update_frontmatter_field(content: str, field: str, value: str) -> str:
    """Update a field in existing frontmatter."""
    if not content.startswith("---"):
        return content

    end = content.find("---", 3)
    if end == -1:
        return content

    fm_section = content[3:end]
    body = content[end:]

    pattern = re.compile(rf"^{re.escape(field)}:.*$", re.MULTILINE)
    if pattern.search(fm_section):
        fm_section = pattern.sub(f'{field}: "{value}"', fm_section)
    else:
        fm_section = fm_section.rstrip() + f'\n{field}: "{value}"\n'

    return f"---{fm_section}{body}"


def process_entities_for_profiles(
    entities: list[dict],
    vault_path: str,
    meeting_date: str = "",
    meeting_title: str = "",
    meeting_slug: str = "",
    dry_run: bool = True,
) -> dict:
    """
    Process extracted entities: create profiles and accumulate meeting data.

    Called after entity extraction on a note. Creates missing profiles and
    adds meeting context to existing ones.

    Returns:
        dict with profiles_created, profiles_updated, details.
    """
    results = {
        "profiles_created": 0,
        "profiles_updated": 0,
        "details": [],
    }

    if not meeting_date:
        meeting_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    for entity in entities:
        name = entity["name"]
        etype = entity["type"]
        org = entity.get("org", "")
        role = entity.get("role", "")

        if dry_run:
            results["details"].append({
                "name": name,
                "type": etype,
                "action": "would_create_or_update",
            })
            continue

        if etype == "person":
            profile = _find_existing_profile(name, "person", vault_path)
            if profile:
                results["profiles_updated"] += 1
                action = "updated"
            else:
                profile = ensure_person_profile(name, vault_path, org=org, role=role)
                results["profiles_created"] += 1
                action = "created"

            # Accumulate meeting data if this came from a meeting
            if meeting_slug and profile:
                accumulate_meeting(
                    profile,
                    meeting_date,
                    meeting_title,
                    meeting_slug,
                )

            results["details"].append({"name": name, "type": etype, "action": action})

        elif etype == "organization":
            profile = _find_existing_profile(name, "organization", vault_path)
            if profile:
                results["profiles_updated"] += 1
                action = "updated"
            else:
                profile = ensure_org_profile(name, vault_path)
                results["profiles_created"] += 1
                action = "created"

            if meeting_slug and profile:
                accumulate_meeting(
                    profile,
                    meeting_date,
                    meeting_title,
                    meeting_slug,
                )

            results["details"].append({"name": name, "type": etype, "action": action})

    return results


def _find_existing_profile(name: str, entity_type: str, vault_path: str) -> Optional[Path]:
    """Check if a profile exists for this entity."""
    vault = Path(vault_path)
    slug = _slugify(name)

    if entity_type == "person":
        people_dir = vault / "people"
        if people_dir.exists():
            for sub in people_dir.iterdir():
                if sub.is_dir():
                    candidate = sub / f"{slug}.md"
                    if candidate.exists():
                        return candidate
    else:
        orgs_dir = vault / "organizations"
        candidate = orgs_dir / f"{slug}.md"
        if candidate.exists():
            return candidate

    return None
