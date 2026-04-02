"""
Natural language relationship graph queries for Engram.

Translates natural language queries about relationships into Neo4j Cypher
queries and returns formatted results.

Supports:
- "Who do we know at {org}?"  -> find all people connected to an organization
- "How are {A} and {B} connected?" -> shortest path between two entities
- "Find paths between {A} and {B} within N hops" -> variable-length path query
- General relationship exploration queries
"""

import logging
import re
from typing import Optional

from .entity_extractor import _slugify

logger = logging.getLogger("relationship_query")


def parse_query(query: str) -> dict:
    """
    Parse a natural language relationship query into a structured query dict.

    Returns dict with 'type' key and type-specific fields:
    - who_at_org: {type, org}
    - connection: {type, entities: [str, str]}
    - path: {type, entities: [str, str], max_hops: int}
    - general: {type, query: str}
    """
    q = query.strip()

    # Pattern: "Who do we know at {org}?"
    who_match = re.search(r"(?i)who\s+(?:do\s+we\s+)?know\s+at\s+(.+?)[\?\.]?\s*$", q)
    if who_match:
        return {"type": "who_at_org", "org": who_match.group(1).strip()}

    # Pattern: "How are {A} and {B} connected?"
    conn_match = re.search(
        r"(?i)how\s+(?:are|is)\s+(.+?)\s+and\s+(.+?)\s+connected[\?\.]?\s*$", q
    )
    if conn_match:
        return {
            "type": "connection",
            "entities": [conn_match.group(1).strip(), conn_match.group(2).strip()],
        }

    # Pattern: "Find paths between {A} and {B} within N hops"
    path_match = re.search(
        r"(?i)(?:find\s+)?paths?\s+between\s+(.+?)\s+and\s+(.+?)"
        r"(?:\s+within\s+(\d+)\s+hops?)?\s*[\?\.]?\s*$",
        q,
    )
    if path_match:
        max_hops = int(path_match.group(3)) if path_match.group(3) else 3
        return {
            "type": "path",
            "entities": [path_match.group(1).strip(), path_match.group(2).strip()],
            "max_hops": max_hops,
        }

    # General/unrecognized
    return {"type": "general", "query": q}


def execute_query(db, parsed: dict, max_results: int = 20) -> dict:
    """
    Execute a parsed relationship query against the graph DB.

    Args:
        db: GraphDB instance.
        parsed: Parsed query dict from parse_query().
        max_results: Maximum number of results to return.

    Returns:
        dict with 'results' list and 'query_type' string.
    """
    if not db or not db.is_available():
        return {"results": [], "query_type": parsed["type"], "error": "Graph DB not available"}

    query_type = parsed["type"]

    if query_type == "who_at_org":
        org_slug = _slugify(parsed["org"])
        results = db.execute_read_only(
            "MATCH (p:Person)-[r]->(o:Organization) "
            "WHERE o.slug = $org_slug OR toLower(o.name) CONTAINS toLower($org_name) "
            "RETURN p.name AS name, p.slug AS slug, type(r) AS relationship, "
            "       o.name AS org_name "
            "LIMIT $limit",
            {"org_slug": org_slug, "org_name": parsed["org"], "limit": max_results},
        )
        return {
            "results": [dict(r) for r in results],
            "query_type": query_type,
            "org": parsed["org"],
        }

    elif query_type == "connection":
        slug_a = _slugify(parsed["entities"][0])
        slug_b = _slugify(parsed["entities"][1])
        results = db.execute_read_only(
            "MATCH path = shortestPath("
            "  (a {slug: $slug_a})-[*..5]-(b {slug: $slug_b})"
            ") "
            "RETURN [n IN nodes(path) | n.name] AS node_names, "
            "       [r IN relationships(path) | type(r)] AS rel_types, "
            "       length(path) AS hops",
            {"slug_a": slug_a, "slug_b": slug_b},
        )
        return {
            "results": [dict(r) for r in results],
            "query_type": query_type,
            "entities": parsed["entities"],
        }

    elif query_type == "path":
        slug_a = _slugify(parsed["entities"][0])
        slug_b = _slugify(parsed["entities"][1])
        max_hops = parsed.get("max_hops", 3)
        results = db.execute_read_only(
            f"MATCH path = (a {{slug: $slug_a}})-[*1..{max_hops}]-(b {{slug: $slug_b}}) "
            "RETURN [n IN nodes(path) | n.name] AS node_names, "
            "       [r IN relationships(path) | type(r)] AS rel_types, "
            "       length(path) AS hops "
            "ORDER BY length(path) "
            "LIMIT $limit",
            {"slug_a": slug_a, "slug_b": slug_b, "limit": max_results},
        )
        return {
            "results": [dict(r) for r in results],
            "query_type": query_type,
            "entities": parsed["entities"],
            "max_hops": max_hops,
        }

    else:
        # General query — do a broad text search across the graph
        results = db.execute_read_only(
            "MATCH (n) WHERE toLower(n.name) CONTAINS toLower($query) "
            "OPTIONAL MATCH (n)-[r]-(connected) "
            "RETURN n.name AS name, n.slug AS slug, labels(n)[0] AS label, "
            "       collect(DISTINCT {name: connected.name, rel: type(r)}) AS connections "
            "LIMIT $limit",
            {"query": parsed["query"], "limit": max_results},
        )
        return {
            "results": [dict(r) for r in results],
            "query_type": query_type,
            "query": parsed["query"],
        }


def format_results(result: dict) -> str:
    """
    Format query results as human-readable text.

    Returns a formatted string suitable for MCP tool output.
    """
    query_type = result.get("query_type", "unknown")
    results = result.get("results", [])

    if not results:
        return f"No results found for {query_type} query."

    lines = []

    if query_type == "who_at_org":
        org = result.get("org", "")
        lines.append(f"People connected to {org}:")
        for r in results:
            rel = r.get("relationship", "connected to")
            lines.append(f"  - {r.get('name', 'Unknown')} ({rel})")

    elif query_type == "connection":
        entities = result.get("entities", [])
        lines.append(f"Connection between {' and '.join(entities)}:")
        for r in results:
            nodes = r.get("node_names", [])
            rels = r.get("rel_types", [])
            path_str = ""
            for i, node in enumerate(nodes):
                path_str += node
                if i < len(rels):
                    path_str += f" --[{rels[i]}]--> "
            lines.append(f"  Path ({r.get('hops', '?')} hops): {path_str}")

    elif query_type == "path":
        entities = result.get("entities", [])
        lines.append(f"Paths between {' and '.join(entities)} (max {result.get('max_hops', 3)} hops):")
        for r in results:
            nodes = r.get("node_names", [])
            rels = r.get("rel_types", [])
            path_str = " -> ".join(nodes)
            lines.append(f"  [{r.get('hops', '?')} hops] {path_str}")

    else:
        lines.append("Results:")
        for r in results:
            name = r.get("name", "Unknown")
            label = r.get("label", "")
            connections = r.get("connections", [])
            conn_str = ", ".join(
                f"{c.get('name', '?')} ({c.get('rel', '?')})"
                for c in connections if c.get("name")
            )
            lines.append(f"  - {name} [{label}] — {conn_str or 'no connections'}")

    return "\n".join(lines)


def relationship_query(db, query: str, max_hops: int = 3) -> dict:
    """
    End-to-end relationship query: parse, execute, return results.

    This is the main entry point called by the CLI and MCP tool.

    Args:
        db: GraphDB instance.
        query: Natural language query string.
        max_hops: Maximum traversal depth for path queries.

    Returns:
        dict with 'results', 'query_type', and 'formatted' text.
    """
    parsed = parse_query(query)
    if parsed["type"] == "path" and "max_hops" not in parsed:
        parsed["max_hops"] = max_hops

    result = execute_query(db, parsed)
    result["formatted"] = format_results(result)
    return result
