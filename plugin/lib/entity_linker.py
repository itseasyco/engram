"""
Entity linker for Engram.

Injects [[wikilinks]] into notes for extracted entities. Rules:
  - First mention only (subsequent mentions left as plain text)
  - Never inside frontmatter (between --- markers)
  - Never inside code blocks (``` fenced or indented)
  - Bidirectional: if note A links to entity B, B gets a backlink to A
  - Reuses _add_backlink_to_content from wikilink_weaver.py for consistency
"""

import logging
import os
import re
from pathlib import Path
from typing import Optional

from .consolidation import _parse_frontmatter
from .entity_extractor import _slugify, resolve_entity

logger = logging.getLogger("entity_linker")


# ---------------------------------------------------------------------------
# Zones to skip
# ---------------------------------------------------------------------------

def _find_skip_zones(content: str) -> list[tuple[int, int]]:
    """
    Find character ranges that should NOT be modified:
    frontmatter, fenced code blocks, inline code, existing wikilinks.
    """
    zones = []

    # Frontmatter (--- ... ---)
    if content.startswith("---"):
        end = content.find("---", 3)
        if end != -1:
            zones.append((0, end + 3))

    # Fenced code blocks (``` ... ```)
    for match in re.finditer(r"```[\s\S]*?```", content):
        zones.append((match.start(), match.end()))

    # Existing wikilinks [[ ... ]]
    for match in re.finditer(r"\[\[[^\]]+\]\]", content):
        zones.append((match.start(), match.end()))

    # Inline code (` ... `)
    for match in re.finditer(r"`[^`]+`", content):
        zones.append((match.start(), match.end()))

    return sorted(zones)


def _in_skip_zone(pos: int, zones: list[tuple[int, int]]) -> bool:
    """Check if a character position falls inside any skip zone."""
    for start, end in zones:
        if start <= pos < end:
            return True
        if start > pos:
            break
    return False


# ---------------------------------------------------------------------------
# Wikilink injection
# ---------------------------------------------------------------------------

def inject_entity_links(
    content: str,
    entities: list[dict],
) -> tuple[str, list[str]]:
    """
    Inject [[wikilinks]] for entities into content. First mention only.

    Args:
        content: the full note content (including frontmatter).
        entities: list of entity dicts with at least {name, type}.

    Returns:
        (modified_content, list_of_linked_entity_names)
    """
    if not entities:
        return content, []

    skip_zones = _find_skip_zones(content)
    linked = []
    offset = 0  # Track offset as we insert characters

    for entity in entities:
        name = entity["name"]
        slug = _slugify(name)

        # Skip if already wikilinked in the document
        if f"[[{slug}" in content or f"[[{name}" in content:
            continue

        # Find first mention of the name (case-insensitive, word boundary)
        pattern = re.compile(re.escape(name), re.IGNORECASE)
        match = pattern.search(content)

        if not match:
            continue

        # Check if this position is in a skip zone
        # Recalculate skip zones after each insertion
        if _in_skip_zone(match.start(), _find_skip_zones(content)):
            # Try to find next occurrence outside skip zones
            for m in pattern.finditer(content):
                if not _in_skip_zone(m.start(), _find_skip_zones(content)):
                    match = m
                    break
            else:
                continue

        # Replace with wikilink
        original_text = match.group(0)
        # Use the slug for the link target, display original case
        if original_text == name:
            replacement = f"[[{slug}|{name}]]"
        else:
            replacement = f"[[{slug}|{original_text}]]"

        content = content[:match.start()] + replacement + content[match.end():]
        linked.append(name)

    return content, linked


def link_entities_in_note(
    file_path: Path,
    entities: list[dict],
    vault_path: Optional[str] = None,
    dry_run: bool = True,
) -> dict:
    """
    Inject entity wikilinks into a single note and add backlinks.

    Args:
        file_path: path to the note.
        entities: extracted entities for this note.
        vault_path: vault root.
        dry_run: if True, don't write changes.

    Returns:
        dict with links_added, backlinks_added, details.
    """
    if vault_path is None:
        try:
            from .vault_paths import root
            vault_path = str(root())
        except (ImportError, KeyError):
            vault_path = os.environ.get("LACP_OBSIDIAN_VAULT", "")

    try:
        content = file_path.read_text(encoding="utf-8")
    except (IOError, UnicodeDecodeError):
        return {"links_added": 0, "backlinks_added": 0, "details": []}

    modified_content, linked = inject_entity_links(content, entities)

    results = {
        "links_added": len(linked),
        "backlinks_added": 0,
        "details": [],
    }

    if not dry_run and linked:
        file_path.write_text(modified_content, encoding="utf-8")
        logger.info("Linked %d entities in %s", len(linked), file_path.name)

        # Add backlinks: for each linked entity, add a backlink from their profile to this note
        note_stem = file_path.stem
        for entity_name in linked:
            backlinks = _add_entity_backlink(
                entity_name,
                note_stem,
                vault_path,
            )
            results["backlinks_added"] += backlinks

    for name in linked:
        results["details"].append({"entity": name, "action": "linked"})

    return results


def _add_entity_backlink(entity_name: str, source_stem: str, vault_path: str) -> int:
    """
    Add a backlink from an entity's profile to the source note.

    Returns 1 if backlink was added, 0 otherwise.
    """
    vault = Path(vault_path)
    slug = _slugify(entity_name)

    # Find the entity's profile
    profile_path = None
    for search_dir in [vault / "people", vault / "organizations"]:
        if search_dir.exists():
            for candidate in search_dir.rglob(f"{slug}.md"):
                profile_path = candidate
                break
        if profile_path:
            break

    if not profile_path or not profile_path.exists():
        return 0

    content = profile_path.read_text(encoding="utf-8")

    # Check if backlink already exists
    if f"[[{source_stem}" in content:
        return 0

    # Use wikilink_weaver's backlink function if available
    try:
        from .wikilink_weaver import _add_backlink_to_content
        new_content = _add_backlink_to_content(content, source_stem)
        if new_content != content:
            profile_path.write_text(new_content, encoding="utf-8")
            return 1
    except ImportError:
        # Manual fallback: append under ## Related Notes
        entry = f"- [[{source_stem}]]"
        if "## Related Notes" in content:
            content = content.replace(
                "## Related Notes\n",
                f"## Related Notes\n{entry}\n",
            )
        else:
            content = content.rstrip() + f"\n\n## Related Notes\n\n{entry}\n"
        profile_path.write_text(content, encoding="utf-8")
        return 1

    return 0


def link_entities_batch(
    vault_path: Optional[str] = None,
    dry_run: bool = True,
) -> dict:
    """
    Batch process: inject entity wikilinks for all notes with extracted entities.

    Reads the entities field from frontmatter and injects wikilinks.
    Designed for curator cycle integration.

    Returns:
        dict with processed, links_added, backlinks_added.
    """
    if vault_path is None:
        vault_path = os.environ.get(
            "LACP_OBSIDIAN_VAULT",
            os.path.expanduser("~/obsidian/vault"),
        )

    vault = Path(vault_path)
    skip_dirs = {".obsidian", "archive", "_metadata", ".trash"}
    results = {
        "processed": 0,
        "links_added": 0,
        "backlinks_added": 0,
        "dry_run": dry_run,
        "details": [],
    }

    for md_file in sorted(vault.rglob("*.md")):
        rel = md_file.relative_to(vault)
        if any(part in skip_dirs for part in rel.parts):
            continue
        if md_file.name == "index.md":
            continue

        try:
            content = md_file.read_text(encoding="utf-8")
        except (IOError, UnicodeDecodeError):
            continue

        fm = _parse_frontmatter(content)
        entity_names = fm.get("entities", [])
        if not entity_names or not isinstance(entity_names, list):
            continue

        # Build entity dicts from names
        entities = [{"name": n, "type": "person"} for n in entity_names]

        result = link_entities_in_note(md_file, entities, str(vault), dry_run)
        if result["links_added"] > 0:
            results["processed"] += 1
            results["links_added"] += result["links_added"]
            results["backlinks_added"] += result["backlinks_added"]
            results["details"].extend(result["details"])

    return results
