"""
Relationship graph for Engram.

Manages typed relationship edges between entities in the vault.

Storage is dual:
  1. Human-readable: ## Relationships sections in entity profiles
  2. Machine-traversal: _metadata/relationship-index.json

Relationship types:
  works-at, founded, advises, invested-in, portfolio-company-of,
  client-of, partner-of, competes-with, met-with, introduced-by,
  discussed, advocates-for, skeptical-of

Traversal: BFS through typed edges.
  "Who do we know at A16Z?" → traverse met-with → works-at → find all paths.
"""

import json
import logging
import os
import re
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .consolidation import _parse_frontmatter
from .entity_extractor import _slugify

logger = logging.getLogger("relationship_graph")


# ---------------------------------------------------------------------------
# Relationship types
# ---------------------------------------------------------------------------

RELATIONSHIP_TYPES = {
    "works-at",
    "founded",
    "advises",
    "invested-in",
    "portfolio-company-of",
    "client-of",
    "partner-of",
    "competes-with",
    "met-with",
    "introduced-by",
    "discussed",
    "advocates-for",
    "skeptical-of",
}

# Inverse relationship mapping for bidirectional edges
_INVERSES = {
    "works-at": "employs",
    "employs": "works-at",
    "founded": "founded-by",
    "founded-by": "founded",
    "advises": "advised-by",
    "advised-by": "advises",
    "invested-in": "funded-by",
    "funded-by": "invested-in",
    "portfolio-company-of": "has-portfolio-company",
    "has-portfolio-company": "portfolio-company-of",
    "client-of": "has-client",
    "has-client": "client-of",
    "partner-of": "partner-of",
    "competes-with": "competes-with",
    "met-with": "met-with",
    "introduced-by": "introduced",
    "introduced": "introduced-by",
    "discussed": "discussed",
    "advocates-for": "advocated-by",
    "advocated-by": "advocates-for",
    "skeptical-of": "skepticism-from",
    "skepticism-from": "skeptical-of",
}


# ---------------------------------------------------------------------------
# Index management
# ---------------------------------------------------------------------------

def _index_path(vault_path: str) -> Path:
    """Return path to relationship-index.json."""
    return Path(vault_path) / "_metadata" / "relationship-index.json"


def load_index(vault_path: str) -> dict:
    """
    Load the relationship index.

    Structure:
    {
        "entities": {
            "kate-levchuk": {
                "name": "Kate Levchuk",
                "type": "person",
                "edges": [
                    {"target": "andreessen-horowitz", "type": "works-at", "since": "2026-03-01", "context": "..."},
                ]
            }
        },
        "updated": "2026-04-01T00:00:00Z"
    }
    """
    path = _index_path(vault_path)
    if not path.exists():
        return {"entities": {}, "updated": ""}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"entities": {}, "updated": ""}


def save_index(vault_path: str, index: dict):
    """Write the relationship index to disk."""
    path = _index_path(vault_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    index["updated"] = datetime.now(timezone.utc).isoformat()
    path.write_text(
        json.dumps(index, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Edge operations
# ---------------------------------------------------------------------------

def add_relationship(
    source_name: str,
    target_name: str,
    rel_type: str,
    vault_path: str,
    context: str = "",
    source_type: str = "person",
    target_type: str = "organization",
    dry_run: bool = True,
) -> bool:
    """
    Add a typed relationship edge between two entities.

    Updates both the index and the profile ## Relationships sections.

    Returns:
        True if relationship was added (new), False if already existed.
    """
    source_slug = _slugify(source_name)
    target_slug = _slugify(target_name)

    index = load_index(vault_path)
    entities = index.setdefault("entities", {})

    # Ensure source entity in index
    if source_slug not in entities:
        entities[source_slug] = {
            "name": source_name,
            "type": source_type,
            "edges": [],
        }

    # Ensure target entity in index
    if target_slug not in entities:
        entities[target_slug] = {
            "name": target_name,
            "type": target_type,
            "edges": [],
        }

    # Check if edge already exists
    source_edges = entities[source_slug]["edges"]
    for edge in source_edges:
        if edge["target"] == target_slug and edge["type"] == rel_type:
            return False  # Already exists

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Add forward edge
    source_edges.append({
        "target": target_slug,
        "type": rel_type,
        "since": now,
        "context": context,
    })

    # Add inverse edge
    inverse_type = _INVERSES.get(rel_type, rel_type)
    target_edges = entities[target_slug]["edges"]
    already_has_inverse = any(
        e["target"] == source_slug and e["type"] == inverse_type
        for e in target_edges
    )
    if not already_has_inverse:
        target_edges.append({
            "target": source_slug,
            "type": inverse_type,
            "since": now,
            "context": context,
        })

    if not dry_run:
        save_index(vault_path, index)

        # Update profile ## Relationships sections
        _update_profile_relationships(source_name, target_name, rel_type, context, vault_path)
        _update_profile_relationships(target_name, source_name, inverse_type, context, vault_path)

    logger.info("Relationship: %s -[%s]-> %s", source_name, rel_type, target_name)
    return True


def _update_profile_relationships(
    entity_name: str,
    related_name: str,
    rel_type: str,
    context: str,
    vault_path: str,
):
    """Update the ## Relationships section in an entity's profile."""
    vault = Path(vault_path)
    slug = _slugify(entity_name)
    related_slug = _slugify(related_name)

    # Find profile
    profile_path = None
    for search_dir in [vault / "people", vault / "organizations"]:
        if search_dir.exists():
            for candidate in search_dir.rglob(f"{slug}.md"):
                profile_path = candidate
                break
        if profile_path:
            break

    if not profile_path or not profile_path.exists():
        return

    content = profile_path.read_text(encoding="utf-8")

    # Check if relationship already recorded
    if f"[[{related_slug}" in content and rel_type in content:
        return

    entry = f"- **{rel_type}**: [[{related_slug}|{related_name}]]"
    if context:
        entry += f" — {context}"

    # Append under ## Relationships
    pattern = re.compile(r"^(## Relationships\s*\n)", re.MULTILINE)
    match = pattern.search(content)

    if match:
        section_start = match.end()
        next_section = re.search(r"^## ", content[section_start:], re.MULTILINE)
        if next_section:
            insert_pos = section_start + next_section.start()
        else:
            insert_pos = len(content)
        content = content[:insert_pos].rstrip() + "\n" + entry + "\n\n" + content[insert_pos:].lstrip("\n")
    else:
        content = content.rstrip() + f"\n\n## Relationships\n\n{entry}\n"

    profile_path.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Traversal
# ---------------------------------------------------------------------------

def query_relationships(
    entity_name: str,
    vault_path: str,
    rel_type: Optional[str] = None,
) -> list[dict]:
    """
    Query all relationships for an entity.

    Args:
        entity_name: canonical name or slug.
        vault_path: vault root.
        rel_type: optional filter by relationship type.

    Returns:
        list of {target, target_name, type, since, context}
    """
    index = load_index(vault_path)
    slug = _slugify(entity_name)
    entity = index.get("entities", {}).get(slug)

    if not entity:
        return []

    edges = entity.get("edges", [])
    if rel_type:
        edges = [e for e in edges if e["type"] == rel_type]

    # Enrich with target names
    results = []
    for edge in edges:
        target_entity = index["entities"].get(edge["target"], {})
        results.append({
            "target": edge["target"],
            "target_name": target_entity.get("name", edge["target"]),
            "type": edge["type"],
            "since": edge.get("since", ""),
            "context": edge.get("context", ""),
        })

    return results


def traverse(
    start_name: str,
    vault_path: str,
    max_hops: int = 3,
    rel_types: Optional[set[str]] = None,
) -> list[dict]:
    """
    BFS traversal through the relationship graph.

    Args:
        start_name: starting entity.
        vault_path: vault root.
        max_hops: maximum traversal depth.
        rel_types: optional set of relationship types to follow.

    Returns:
        list of {entity, entity_name, depth, path, via_type}
    """
    index = load_index(vault_path)
    start_slug = _slugify(start_name)

    if start_slug not in index.get("entities", {}):
        return []

    visited = {start_slug}
    queue = deque([(start_slug, 0, [start_name], "")])
    results = []

    while queue:
        current_slug, depth, path, via_type = queue.popleft()

        if depth > 0:
            entity_data = index["entities"].get(current_slug, {})
            results.append({
                "entity": current_slug,
                "entity_name": entity_data.get("name", current_slug),
                "entity_type": entity_data.get("type", "unknown"),
                "depth": depth,
                "path": path,
                "via_type": via_type,
            })

        if depth >= max_hops:
            continue

        entity = index["entities"].get(current_slug, {})
        for edge in entity.get("edges", []):
            target = edge["target"]
            edge_type = edge["type"]

            if target in visited:
                continue
            if rel_types and edge_type not in rel_types:
                continue

            visited.add(target)
            target_name = index["entities"].get(target, {}).get("name", target)
            queue.append((target, depth + 1, path + [target_name], edge_type))

    return results


def find_paths(
    start_name: str,
    end_name: str,
    vault_path: str,
    max_hops: int = 4,
) -> list[list[dict]]:
    """
    Find all paths between two entities (up to max_hops).

    Returns:
        list of paths, where each path is a list of
        {entity, entity_name, via_type} steps.
    """
    index = load_index(vault_path)
    start_slug = _slugify(start_name)
    end_slug = _slugify(end_name)

    if start_slug not in index.get("entities", {}) or end_slug not in index.get("entities", {}):
        return []

    paths = []
    queue = deque([(start_slug, [{"entity": start_slug, "entity_name": start_name, "via_type": ""}])])

    while queue:
        current_slug, path = queue.popleft()

        if len(path) > max_hops + 1:
            continue

        if current_slug == end_slug and len(path) > 1:
            paths.append(path)
            continue

        entity = index["entities"].get(current_slug, {})
        visited_in_path = {step["entity"] for step in path}

        for edge in entity.get("edges", []):
            target = edge["target"]
            if target in visited_in_path:
                continue

            target_name = index["entities"].get(target, {}).get("name", target)
            new_path = path + [{
                "entity": target,
                "entity_name": target_name,
                "via_type": edge["type"],
            }]
            queue.append((target, new_path))

    return paths


# ---------------------------------------------------------------------------
# Index rebuild from vault profiles
# ---------------------------------------------------------------------------

def rebuild_index(vault_path: str, dry_run: bool = True) -> dict:
    """
    Rebuild relationship-index.json by scanning all entity profiles.

    Parses ## Relationships sections from people/ and organizations/ profiles.

    Returns:
        dict with entities_found, edges_found.
    """
    vault = Path(vault_path)
    index = {"entities": {}, "updated": ""}
    stats = {"entities_found": 0, "edges_found": 0, "dry_run": dry_run}

    # Relationship line pattern: "- **type**: [[slug|Name]] — context"
    rel_pattern = re.compile(
        r"^\s*-\s+\*\*([^*]+)\*\*:\s+\[\[([^\]|]+)(?:\|([^\]]+))?\]\](?:\s*[—–-]\s*(.+))?",
        re.MULTILINE,
    )

    for search_dir_name in ["people", "organizations"]:
        search_dir = vault / search_dir_name
        if not search_dir.exists():
            continue

        entity_type = "person" if search_dir_name == "people" else "organization"

        for md_file in search_dir.rglob("*.md"):
            if md_file.name == "index.md":
                continue

            try:
                content = md_file.read_text(encoding="utf-8")
            except (IOError, UnicodeDecodeError):
                continue

            fm = _parse_frontmatter(content)
            entity_name = fm.get("title", md_file.stem.replace("-", " ").title())
            slug = md_file.stem

            entity_data = {
                "name": entity_name,
                "type": entity_type,
                "edges": [],
            }

            # Parse ## Relationships section
            for match in rel_pattern.finditer(content):
                rel_type = match.group(1).strip()
                target_slug = match.group(2).strip()
                target_name = match.group(3) or target_slug.replace("-", " ").title()
                context = (match.group(4) or "").strip()

                entity_data["edges"].append({
                    "target": target_slug,
                    "type": rel_type,
                    "since": "",
                    "context": context,
                })
                stats["edges_found"] += 1

            index["entities"][slug] = entity_data
            stats["entities_found"] += 1

    if not dry_run:
        save_index(vault_path, index)
        logger.info(
            "Index rebuilt: %d entities, %d edges",
            stats["entities_found"],
            stats["edges_found"],
        )

    return stats


# ---------------------------------------------------------------------------
# Relationship inference from meetings
# ---------------------------------------------------------------------------

def infer_relationships_from_meeting(
    entities: list[dict],
    meeting_title: str,
    vault_path: str,
    dry_run: bool = True,
) -> dict:
    """
    Infer relationships from a meeting's extracted entities.

    Logic:
    - All people at a meeting → met-with each other
    - Person with org → works-at org
    - Org mentioned in investor context → potential invested-in relationships

    Returns:
        dict with relationships_added, details.
    """
    results = {"relationships_added": 0, "details": []}
    people = [e for e in entities if e["type"] == "person"]
    orgs = [e for e in entities if e["type"] == "organization"]

    # People met-with each other
    for i, person_a in enumerate(people):
        for person_b in people[i + 1:]:
            added = add_relationship(
                person_a["name"],
                person_b["name"],
                "met-with",
                vault_path,
                context=meeting_title,
                source_type="person",
                target_type="person",
                dry_run=dry_run,
            )
            if added:
                results["relationships_added"] += 1
                results["details"].append({
                    "source": person_a["name"],
                    "target": person_b["name"],
                    "type": "met-with",
                })

    # Person works-at org (if org field is set)
    for person in people:
        org_name = person.get("org", "")
        if org_name:
            added = add_relationship(
                person["name"],
                org_name,
                "works-at",
                vault_path,
                source_type="person",
                target_type="organization",
                dry_run=dry_run,
            )
            if added:
                results["relationships_added"] += 1
                results["details"].append({
                    "source": person["name"],
                    "target": org_name,
                    "type": "works-at",
                })

    return results
