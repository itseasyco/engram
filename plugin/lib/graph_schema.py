"""
Neo4j schema definitions for Engram.

Defines node types, edge types, constraints, and indexes.
Maps vault relationship types (kebab-case) to Cypher edge types (UPPER_SNAKE).

Usage:
    from lib.graph_schema import ensure_schema
    ensure_schema(db)  # Creates constraints + indexes if they don't exist
"""

import logging

logger = logging.getLogger("graph_schema")

# ---------------------------------------------------------------------------
# Node types and their unique key properties
# ---------------------------------------------------------------------------

NODE_TYPES = {
    "Person":              {"unique_key": "slug"},
    "Organization":        {"unique_key": "slug"},
    "Meeting":             {"unique_key": "slug"},
    "Goal":                {"unique_key": "slug"},
    "Feature":             {"unique_key": "name"},
    "Decision":            {"unique_key": "slug"},
    "IntelligenceReport":  {"unique_key": "slug"},
    "Session":             {"unique_key": "id"},
    "Note":                {"unique_key": "path"},
}

# ---------------------------------------------------------------------------
# Edge types
# ---------------------------------------------------------------------------

EDGE_TYPES = {
    # Relationship edges
    "WORKS_AT", "FOUNDED", "ADVISES", "INVESTED_IN",
    "PORTFOLIO_COMPANY_OF", "CLIENT_OF", "PARTNER_OF",
    "COMPETES_WITH", "MET_WITH", "INTRODUCED_BY",
    "DISCUSSED", "FRIENDS_WITH", "ADVOCATES_FOR", "SKEPTICAL_OF",
    # Intelligence edges
    "RELEVANT_TO", "IMPLEMENTS", "REQUESTED_BY",
    "BLOCKS", "TRIGGERED_BY", "DERIVED_FROM",
    # Mycelium edges
    "LINKS_TO",
    # Temporal edges
    "NEXT_STAGE", "FOLLOWED_BY",
}

# ---------------------------------------------------------------------------
# Vault relationship type -> Cypher edge type mapping
# ---------------------------------------------------------------------------

_VAULT_TO_CYPHER = {
    "works-at": "WORKS_AT",
    "founded": "FOUNDED",
    "advises": "ADVISES",
    "invested-in": "INVESTED_IN",
    "portfolio-company-of": "PORTFOLIO_COMPANY_OF",
    "has-portfolio-company": "PORTFOLIO_COMPANY_OF",
    "client-of": "CLIENT_OF",
    "partner-of": "PARTNER_OF",
    "competes-with": "COMPETES_WITH",
    "met-with": "MET_WITH",
    "introduced-by": "INTRODUCED_BY",
    "discussed": "DISCUSSED",
    "friends-with": "FRIENDS_WITH",
    "advocates-for": "ADVOCATES_FOR",
    "skeptical-of": "SKEPTICAL_OF",
    "relevant-to": "RELEVANT_TO",
    "implements": "IMPLEMENTS",
    "requested-by": "REQUESTED_BY",
    "blocks": "BLOCKS",
    "links-to": "LINKS_TO",
}


def vault_rel_to_cypher(vault_type: str) -> str:
    """Convert vault relationship type (kebab-case) to Cypher edge type (UPPER_SNAKE)."""
    mapped = _VAULT_TO_CYPHER.get(vault_type)
    if mapped:
        return mapped
    # Fallback: convert kebab to UPPER_SNAKE
    return vault_type.upper().replace("-", "_")


# ---------------------------------------------------------------------------
# Schema enforcement
# ---------------------------------------------------------------------------

def ensure_schema(db) -> dict:
    """Create uniqueness constraints and indexes in Neo4j. Idempotent."""
    constraints_created = 0
    indexes_created = 0

    for label, props in NODE_TYPES.items():
        key = props["unique_key"]
        constraint_name = f"unique_{label.lower()}_{key}"
        try:
            db.execute_write(
                f"CREATE CONSTRAINT {constraint_name} IF NOT EXISTS "
                f"FOR (n:{label}) REQUIRE n.{key} IS UNIQUE"
            )
            constraints_created += 1
        except Exception as exc:
            logger.debug("Constraint %s already exists or failed: %s", constraint_name, exc)

    # Full-text search index on name/title fields
    try:
        db.execute_write(
            "CREATE FULLTEXT INDEX entity_names IF NOT EXISTS "
            "FOR (n:Person|Organization|Goal|Meeting) ON EACH [n.name, n.title]"
        )
        indexes_created += 1
    except Exception as exc:
        logger.debug("Full-text index creation: %s", exc)

    # Index on Note.path for fast sync lookups
    try:
        db.execute_write(
            "CREATE INDEX note_path IF NOT EXISTS FOR (n:Note) ON (n.path)"
        )
        indexes_created += 1
    except Exception as exc:
        logger.debug("Note path index: %s", exc)

    logger.info(
        "Schema ensured: %d constraints, %d indexes",
        constraints_created, indexes_created,
    )
    return {
        "constraints_created": constraints_created,
        "indexes_created": indexes_created,
    }
