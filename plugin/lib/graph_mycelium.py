"""
Mycelium algorithms implemented as Neo4j graph operations.

Replaces the in-memory Python implementations in mycelium.py with Cypher queries
that run natively in the graph database.

The original mycelium.py is preserved — these functions are used when Neo4j is
available; the originals serve as fallback.
"""

import logging
import math
from datetime import datetime, timezone

logger = logging.getLogger("graph_mycelium")


def spreading_activation(
    db,
    seeds: dict[str, float],
    alpha: float = 0.7,
    max_hops: int = 3,
) -> dict[str, float]:
    """
    Spreading activation over the graph using variable-length path queries.

    Args:
        db: GraphDB instance.
        seeds: {slug: initial_activation}.
        alpha: Decay factor per hop.
        max_hops: Maximum traversal depth (1-10).

    Returns:
        {slug: activation_score} for all reachable nodes.
    """
    # Validate max_hops — Neo4j does not support parameterized path bounds,
    # so we interpolate directly into the query. Clamp to [1, 10] for safety.
    max_hops = int(max_hops)
    if max_hops < 1:
        max_hops = 1
    elif max_hops > 10:
        max_hops = 10

    activations = dict(seeds)

    for seed_slug, initial_activation in seeds.items():
        # Neo4j doesn't allow $params in variable-length path bounds,
        # so we use f-string interpolation with the validated int.
        results = db.execute_read_only(
            f"""
            MATCH path = (seed {{slug: $seed_slug}})-[:LINKS_TO*1..{max_hops}]-(target)
            WHERE target.slug <> $seed_slug
            RETURN target.slug AS slug, length(path) AS hops
            ORDER BY hops
            """,
            {"seed_slug": seed_slug},
        )

        for record in results:
            slug = record["slug"]
            hops = record["hops"]
            propagated = initial_activation * (alpha ** hops)
            existing = activations.get(slug, 0.0)
            if propagated > existing:
                activations[slug] = propagated

    return activations


def update_storage_strengths(db):
    """
    Update storage strength for all nodes.

    Formula: S = min(1.0, 0.1 + 0.05 * access_count)
    Preserves existing value if higher (monotonically increasing).
    """
    db.execute_write("""
        MATCH (n)
        WHERE n.access_count IS NOT NULL
        WITH n, CASE
            WHEN 0.1 + 0.05 * n.access_count > 1.0 THEN 1.0
            ELSE 0.1 + 0.05 * n.access_count
        END AS computed
        SET n.storage_strength = CASE
            WHEN n.storage_strength IS NOT NULL AND n.storage_strength > computed
            THEN n.storage_strength
            ELSE computed
        END
    """)


def update_retrieval_strengths(db):
    """
    Update retrieval strength with temporal decay for all nodes.

    Formula: R = exp(-days_since_last_seen / stability)
    Where stability = max(1.0, access_count * (1.0 + 0.2 * edge_count))

    Note: n.last_seen is stored as an ISO 8601 string (e.g. '2025-01-01T00:00:00Z').
    We convert it to a date via date(datetime(n.last_seen)) and compute days elapsed
    using duration.inDays().
    """
    db.execute_write("""
        MATCH (n)
        WHERE n.last_seen IS NOT NULL
        WITH n,
             duration.inDays(date(datetime(n.last_seen)), date()).days AS days_ago,
             COALESCE(n.access_count, 0) AS count,
             size([(n)-[]-() | 1]) AS edge_count
        WITH n, days_ago,
             CASE
                 WHEN count * (1.0 + 0.2 * edge_count) > 1.0
                 THEN count * (1.0 + 0.2 * edge_count)
                 ELSE 1.0
             END AS stability
        SET n.retrieval_strength = exp(toFloat(-days_ago) / stability)
    """)


def compute_flow_scores(db):
    """
    Compute betweenness centrality proxy as flow score.

    Uses normalized degree centrality (degree / max_degree across all nodes).

    Note: Neo4j GDS (Graph Data Science) is NOT included in Community Edition.
    The degree-based approximation below is the production path for Community Edition.
    """
    db.execute_write("""
        MATCH (n)
        WITH n, size([(n)-[]-() | 1]) AS degree
        WITH collect({node: n, degree: degree}) AS rows, max(degree) AS max_deg
        UNWIND rows AS row
        WITH row.node AS n, row.degree AS degree, max_deg
        SET n.flow_score = CASE
            WHEN max_deg > 0 THEN toFloat(degree) / max_deg
            ELSE 0.0
        END
    """)


def reinforce_path(db, slug: str, boost: float = 0.1):
    """
    Reinforce edges connected to an accessed node.

    When a node is accessed, boost confidence on all its edges.
    """
    db.execute_write("""
        MATCH (n {slug: $slug})-[r]-()
        SET r.confidence = CASE
            WHEN r.confidence IS NOT NULL THEN CASE
                WHEN r.confidence + $boost > 1.0 THEN 1.0
                ELSE r.confidence + $boost
            END
            ELSE 0.5 + $boost
        END,
        r.last_reinforced = datetime()
    """, {"slug": slug, "boost": boost})


def heal_orphans(db):
    """
    Find disconnected nodes and reconnect them to the nearest hub.

    A hub is any node with degree >= 5.
    """
    db.execute_write("""
        MATCH (orphan)
        WHERE NOT (orphan)-[]-() AND orphan.slug IS NOT NULL
        WITH orphan
        MATCH (hub)
        WHERE size([(hub)-[]-() | 1]) >= 5
        WITH orphan, hub, rand() AS r
        ORDER BY r
        LIMIT 1
        MERGE (orphan)-[:LINKS_TO {confidence: 0.3, healed: true}]->(hub)
    """)


def run_full_mycelium_cycle(db) -> dict:
    """Run all mycelium operations in sequence."""
    update_storage_strengths(db)
    update_retrieval_strengths(db)
    compute_flow_scores(db)
    heal_orphans(db)

    # Get summary stats
    stats = db.execute_read_only("""
        MATCH (n)
        WHERE n.storage_strength IS NOT NULL
        RETURN count(n) AS nodes_with_strength,
               avg(n.storage_strength) AS avg_storage,
               avg(n.retrieval_strength) AS avg_retrieval,
               avg(n.flow_score) AS avg_flow
    """)

    result = stats[0] if stats else {}
    logger.info(
        "Mycelium cycle: %d nodes, avg S=%.2f R=%.2f F=%.2f",
        result.get("nodes_with_strength", 0),
        result.get("avg_storage", 0),
        result.get("avg_retrieval", 0),
        result.get("avg_flow", 0),
    )
    return dict(result) if result else {}
