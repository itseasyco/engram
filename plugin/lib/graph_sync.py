"""
Vault-to-graph synchronization for Engram.

Parses Obsidian vault markdown notes (frontmatter + wikilinks + relationship sections)
and upserts them as nodes and edges in Neo4j.

Label inference uses three sources (first match wins):
  1. Frontmatter ``type`` field (e.g. ``type: person``)
  2. Folder path (e.g. ``meetings/investors/`` → Meeting)
  3. Default: ``Note``

Meeting notes also auto-extract attendees from ``**Attendees:**`` lines,
creating Person nodes and ATTENDED edges automatically.

This is the CQRS sync layer: vault is the write side, graph DB is the query side.
"""

import logging
import re
from pathlib import Path

from .consolidation import _parse_frontmatter
from .graph_schema import vault_rel_to_cypher


def slugify(name: str) -> str:
    """Convert a display name to a URL-safe slug (e.g. 'Kate Levchuk' -> 'kate-levchuk')."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")

logger = logging.getLogger("graph_sync")

# ---------------------------------------------------------------------------
# Frontmatter type -> Neo4j label mapping
# ---------------------------------------------------------------------------

_TYPE_TO_LABEL = {
    "person": "Person",
    "organization": "Organization",
    "goal": "Goal",
    "meeting": "Meeting",
    "decision": "Decision",
    "feature": "Feature",
}

# ---------------------------------------------------------------------------
# Folder path -> Neo4j label mapping
# Matched against the relative path from vault root. First prefix match wins.
# ---------------------------------------------------------------------------

_FOLDER_TO_LABEL = {
    "people/investors/": "Person",
    "people/team/": "Person",
    "people/clients/": "Person",
    "people/personal/": "Person",
    "organizations/": "Organization",
    "meetings/": "Meeting",
    "strategy/goals/": "Goal",
    "strategy/decisions/": "Decision",
    "strategy/synthesis/": "IntelligenceReport",
    "sessions/": "Session",
    "engineering/decisions/": "Decision",
}

# ---------------------------------------------------------------------------
# Attendee extraction for meeting notes
# ---------------------------------------------------------------------------

# Names to skip when extracting attendees
_SKIP_ATTENDEES = {
    "niko's notetaker", "notetaker",
}

# Patterns that indicate a bot/notetaker, not a real person
_NOTETAKER_PATTERNS = re.compile(
    r"(?i)"
    r"notetaker|note[\s-]?taker|"
    r"fireflies\.ai|read\.ai|"
    r"ai notetaker|ai note taker|"
    r"^participant\s+\d+$"
)


def _extract_attendees(content: str) -> list[str]:
    """Extract attendee names from **Attendees:** line in meeting notes."""
    match = re.search(r'\*\*Attendees:\*\*\s*(.+)', content)
    if not match:
        return []
    raw = match.group(1).strip().rstrip("\\").strip()
    names = []
    for name in raw.split(","):
        name = name.strip().rstrip("  ")  # trailing double space
        if not name or name.lower() in _SKIP_ATTENDEES:
            continue
        if _NOTETAKER_PATTERNS.search(name):
            continue
        names.append(name)
    return names


def _extract_meeting_date(content: str) -> str:
    """Extract date from **Date:** line in meeting notes."""
    match = re.search(r'\*\*Date:\*\*\s*(\d{4}-\d{2}-\d{2})', content)
    return match.group(1) if match else ""


def _infer_label_from_path(rel_path: str) -> str:
    """Infer Neo4j label from the note's relative path within the vault."""
    for prefix, label in _FOLDER_TO_LABEL.items():
        if rel_path.startswith(prefix):
            return label
    return ""


# ---------------------------------------------------------------------------
# Skip patterns
# ---------------------------------------------------------------------------

_SKIP_DIRS = {"_metadata", ".obsidian", ".trash", "templates", "archive"}


# ---------------------------------------------------------------------------
# Note parser
# ---------------------------------------------------------------------------

def _extract_wikilinks(content: str) -> list[str]:
    """Extract [[wikilink]] targets from markdown content."""
    return re.findall(r'\[\[([^\]|]+)(?:\|[^\]]+)?\]\]', content)


def _extract_relationships(content: str) -> list[dict]:
    """Extract typed relationships from ## Relationships section."""
    edges = []
    in_rel_section = False

    for line in content.split("\n"):
        if line.strip().startswith("## Relationships"):
            in_rel_section = True
            continue
        if in_rel_section and line.strip().startswith("## "):
            break
        if in_rel_section and line.strip().startswith("- "):
            # Parse: "- works-at: [[Target Name]]"
            match = re.match(r'-\s+([\w-]+):\s+\[\[([^\]]+)\]\]', line.strip())
            if match:
                rel_type, target = match.groups()
                edges.append({
                    "type": vault_rel_to_cypher(rel_type),
                    "target_name": target.split("|")[0].strip(),
                    "vault_type": rel_type,
                })

    return edges


def parse_vault_note(note_path: Path, vault_root: Path | None = None) -> tuple[dict, list[dict], list[dict]]:
    """
    Parse a vault note into a graph node + edges + extra nodes (e.g. attendees).

    Label inference order:
      1. Frontmatter ``type`` field
      2. Folder path relative to vault root
      3. Default: ``Note``

    Returns:
        (node_dict, list_of_edge_dicts, list_of_extra_node_dicts)
    """
    content = note_path.read_text(encoding="utf-8")
    fm = _parse_frontmatter(content)

    # Determine label: frontmatter type first, then folder path
    note_type = fm.get("type", "")
    label = _TYPE_TO_LABEL.get(str(note_type).lower(), "")

    if not label and vault_root:
        rel_path = note_path.relative_to(vault_root).as_posix()
        label = _infer_label_from_path(rel_path)

    if not label:
        label = "Note"

    # Build slug from filename
    slug = note_path.stem

    # Core properties
    properties = {
        "slug": slug,
        "path": str(note_path),
        "name": fm.get("title", slug.replace("-", " ").title()),
        "title": fm.get("title", ""),
    }

    # Copy relevant frontmatter fields
    for key in ("role", "org", "sector", "status", "priority", "category",
                "relationship_stage", "last_contact", "target_close", "type"):
        if key in fm:
            properties[key] = str(fm[key]) if not isinstance(fm[key], str) else fm[key]

    # Scoring signals (for goals)
    if "scoring_signals" in fm:
        properties["scoring_signals_json"] = str(fm["scoring_signals"])

    node = {"label": label, "properties": properties}

    # Extract edges from relationships section
    edges = _extract_relationships(content)

    # Extract wikilinks as LINKS_TO edges (for non-relationship wikilinks)
    wikilinks = _extract_wikilinks(content)
    existing_targets = {e["target_name"] for e in edges}
    for link in wikilinks:
        if link not in existing_targets:
            edges.append({
                "type": "LINKS_TO",
                "target_name": link,
                "vault_type": "links-to",
            })

    # Meeting-specific: extract attendees as Person nodes + ATTENDED edges
    extra_nodes = []
    if label == "Meeting":
        attendees = _extract_attendees(content)
        meeting_date = _extract_meeting_date(content)
        if meeting_date:
            properties["date"] = meeting_date

        for name in attendees:
            person_slug = slugify(name)
            extra_nodes.append({
                "label": "Person",
                "properties": {
                    "slug": person_slug,
                    "name": name,
                },
            })
            edges.append({
                "type": "ATTENDED",
                "target_name": name,
                "target_slug": person_slug,
                "target_label": "Person",
                "vault_type": "attended",
                "properties": {"date": meeting_date} if meeting_date else {},
            })

    # Add source info to all edges
    for edge in edges:
        edge["source_slug"] = slug
        edge["source_label"] = label

    return node, edges, extra_nodes


# ---------------------------------------------------------------------------
# Vault scanner
# ---------------------------------------------------------------------------

def scan_vault(vault_path: str) -> tuple[list[dict], list[dict]]:
    """Scan the full vault and return all nodes and edges.

    Extra nodes (e.g. Person nodes from meeting attendees) are deduplicated
    by slug — if a note already exists with that slug, the extra node is
    skipped to avoid overwriting richer data.
    """
    vault = Path(vault_path)
    all_nodes = []
    all_edges = []
    seen_slugs: set[str] = set()

    for md_file in vault.rglob("*.md"):
        # Skip non-content directories
        rel = md_file.relative_to(vault)
        if any(part in _SKIP_DIRS for part in rel.parts):
            continue
        # Skip index files
        if md_file.name == "index.md":
            continue

        try:
            node, edges, extra_nodes = parse_vault_note(md_file, vault_root=vault)
            slug = node["properties"]["slug"]
            all_nodes.append(node)
            seen_slugs.add(slug)
            all_edges.extend(edges)

            # Add extra nodes (attendees etc.) if not already seen
            for extra in extra_nodes:
                extra_slug = extra["properties"]["slug"]
                if extra_slug not in seen_slugs:
                    all_nodes.append(extra)
                    seen_slugs.add(extra_slug)
        except Exception as exc:
            logger.warning("Failed to parse %s: %s", md_file, exc)

    return all_nodes, all_edges


# ---------------------------------------------------------------------------
# Graph upsert operations
# ---------------------------------------------------------------------------

def upsert_node(db, node: dict):
    """Upsert a single node into Neo4j. MERGE on slug/path."""
    label = node["label"]
    props = node["properties"]
    key = "slug" if "slug" in props else "path"

    # Build SET clause for all properties
    set_parts = []
    params = {"key_value": props[key]}
    for k, v in props.items():
        if k != key:
            param_name = f"p_{k}"
            set_parts.append(f"n.{k} = ${param_name}")
            params[param_name] = v

    set_clause = ", ".join(set_parts) if set_parts else "n.updated = true"

    query = f"MERGE (n:{label} {{{key}: $key_value}}) SET {set_clause}"
    db.execute_write(query, params)


def upsert_edge(db, edge: dict):
    """Upsert a single edge into Neo4j."""
    edge_type = edge["type"]
    source_slug = edge["source_slug"]
    source_label = edge.get("source_label", "Note")

    # Resolve target — we may not know the label, so match any node by slug or name
    target_name = edge.get("target_name", "")
    target_slug = slugify(target_name) if target_name else edge.get("target_slug", "")
    target_label = edge.get("target_label")

    if not target_slug:
        return

    # Build edge properties
    edge_props = {k: v for k, v in edge.get("properties", {}).items()}
    props_clause = ""
    params = {"source_slug": source_slug, "target_slug": target_slug}

    if edge_props:
        prop_parts = []
        for k, v in edge_props.items():
            param_name = f"ep_{k}"
            prop_parts.append(f"r.{k} = ${param_name}")
            params[param_name] = v
        props_clause = "SET " + ", ".join(prop_parts)

    # Try to match target by slug across any label
    if target_label:
        query = (
            f"MATCH (s:{source_label} {{slug: $source_slug}}) "
            f"MATCH (t:{target_label} {{slug: $target_slug}}) "
            f"MERGE (s)-[r:{edge_type}]->(t) {props_clause}"
        )
    else:
        # Target label unknown — match any node with this slug
        query = (
            f"MATCH (s:{source_label} {{slug: $source_slug}}) "
            f"MATCH (t {{slug: $target_slug}}) "
            f"MERGE (s)-[r:{edge_type}]->(t) {props_clause}"
        )

    try:
        db.execute_write(query, params)
    except Exception as exc:
        # Target node may not exist yet — log and skip
        logger.debug("Edge upsert skipped (target not found?): %s -> %s: %s", source_slug, target_slug, exc)


# ---------------------------------------------------------------------------
# Full sync
# ---------------------------------------------------------------------------

def sync_vault_to_graph(
    db,
    vault_path: str,
    dry_run: bool = False,
) -> dict:
    """
    Full vault-to-graph synchronization.

    Scans all vault notes, parses into nodes/edges, upserts into Neo4j.
    """
    nodes, edges = scan_vault(vault_path)

    if dry_run:
        return {
            "nodes_found": len(nodes),
            "edges_found": len(edges),
            "nodes_upserted": 0,
            "edges_upserted": 0,
            "dry_run": True,
        }

    nodes_upserted = 0
    edges_upserted = 0

    # Upsert all nodes first
    for node in nodes:
        try:
            upsert_node(db, node)
            nodes_upserted += 1
        except Exception as exc:
            logger.warning("Failed to upsert node %s: %s", node.get("properties", {}).get("slug"), exc)

    # Then upsert edges (targets should exist now)
    for edge in edges:
        try:
            upsert_edge(db, edge)
            edges_upserted += 1
        except Exception as exc:
            logger.debug("Failed to upsert edge: %s", exc)

    logger.info("Vault sync: %d nodes, %d edges upserted", nodes_upserted, edges_upserted)
    return {
        "nodes_found": len(nodes),
        "edges_found": len(edges),
        "nodes_upserted": nodes_upserted,
        "edges_upserted": edges_upserted,
        "dry_run": False,
    }
