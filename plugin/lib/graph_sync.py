"""
Vault-to-graph synchronization for Engram.

Parses Obsidian vault markdown notes (frontmatter + wikilinks + relationship sections)
and upserts them as nodes and edges in Neo4j.

This is the CQRS sync layer: vault is the write side, graph DB is the query side.
"""

import logging
import os
import re
from pathlib import Path
from typing import Optional

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


def parse_vault_note(note_path: Path) -> tuple[dict, list[dict]]:
    """
    Parse a vault note into a graph node + edges.

    Returns:
        (node_dict, list_of_edge_dicts)
    """
    content = note_path.read_text(encoding="utf-8")
    fm = _parse_frontmatter(content)

    # Determine label from frontmatter type
    note_type = fm.get("type", "")
    label = _TYPE_TO_LABEL.get(str(note_type).lower(), "Note")

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

    # Add source info to all edges
    for edge in edges:
        edge["source_slug"] = slug
        edge["source_label"] = label

    return node, edges


# ---------------------------------------------------------------------------
# Vault scanner
# ---------------------------------------------------------------------------

def scan_vault(vault_path: str) -> tuple[list[dict], list[dict]]:
    """Scan the full vault and return all nodes and edges."""
    vault = Path(vault_path)
    all_nodes = []
    all_edges = []

    for md_file in vault.rglob("*.md"):
        # Skip non-content directories
        rel = md_file.relative_to(vault)
        if any(part in _SKIP_DIRS for part in rel.parts):
            continue
        # Skip index files
        if md_file.name == "index.md":
            continue

        try:
            node, edges = parse_vault_note(md_file)
            all_nodes.append(node)
            all_edges.extend(edges)
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
