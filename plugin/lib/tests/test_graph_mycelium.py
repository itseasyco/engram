"""Tests for mycelium algorithms on Neo4j."""

import pytest


class TestSpreadingActivation:
    def test_activation_propagates_from_seed(self):
        from lib.graph_db import GraphDB
        from lib.graph_mycelium import spreading_activation

        db = GraphDB()
        if not db.is_available():
            pytest.skip("Neo4j not available")

        # Setup: A -> B -> C chain
        db.execute_write("""
            MERGE (a:Note {slug: 'sa-a', name: 'A'})
            MERGE (b:Note {slug: 'sa-b', name: 'B'})
            MERGE (c:Note {slug: 'sa-c', name: 'C'})
            MERGE (a)-[:LINKS_TO {confidence: 0.8}]->(b)
            MERGE (b)-[:LINKS_TO {confidence: 0.7}]->(c)
        """)

        result = spreading_activation(db, seeds={"sa-a": 1.0}, alpha=0.7, max_hops=2)

        assert result.get("sa-a", 0) == 1.0
        assert result.get("sa-b", 0) > 0
        assert result.get("sa-c", 0) > 0
        assert result["sa-b"] > result["sa-c"]  # Decays with distance

        # Cleanup
        db.execute_write("MATCH (n) WHERE n.slug STARTS WITH 'sa-' DETACH DELETE n")

    def test_activation_respects_max_hops(self):
        from lib.graph_db import GraphDB
        from lib.graph_mycelium import spreading_activation

        db = GraphDB()
        if not db.is_available():
            pytest.skip("Neo4j not available")

        db.execute_write("""
            MERGE (a:Note {slug: 'hop-a'}) MERGE (b:Note {slug: 'hop-b'})
            MERGE (c:Note {slug: 'hop-c'}) MERGE (d:Note {slug: 'hop-d'})
            MERGE (a)-[:LINKS_TO]->(b) MERGE (b)-[:LINKS_TO]->(c) MERGE (c)-[:LINKS_TO]->(d)
        """)

        result = spreading_activation(db, seeds={"hop-a": 1.0}, alpha=0.7, max_hops=1)
        assert "hop-b" in result
        assert "hop-c" not in result or result["hop-c"] == 0

        db.execute_write("MATCH (n) WHERE n.slug STARTS WITH 'hop-' DETACH DELETE n")


class TestStrengthComputation:
    def test_update_storage_strength(self):
        from lib.graph_db import GraphDB
        from lib.graph_mycelium import update_storage_strengths

        db = GraphDB()
        if not db.is_available():
            pytest.skip("Neo4j not available")

        db.execute_write("MERGE (n:Note {slug: 'ss-test', access_count: 10})")
        update_storage_strengths(db)
        result = db.execute("MATCH (n:Note {slug: 'ss-test'}) RETURN n.storage_strength AS s")
        assert result[0]["s"] > 0

        db.execute_write("MATCH (n:Note {slug: 'ss-test'}) DELETE n")

    def test_update_retrieval_strength_decays(self):
        from lib.graph_db import GraphDB
        from lib.graph_mycelium import update_retrieval_strengths

        db = GraphDB()
        if not db.is_available():
            pytest.skip("Neo4j not available")

        # Note accessed long ago should have low retrieval strength
        db.execute_write(
            "MERGE (n:Note {slug: 'rs-test', last_seen: '2025-01-01T00:00:00Z', access_count: 5})"
        )
        update_retrieval_strengths(db)
        result = db.execute("MATCH (n:Note {slug: 'rs-test'}) RETURN n.retrieval_strength AS r")
        assert result[0]["r"] < 0.5  # Old note should have decayed

        db.execute_write("MATCH (n:Note {slug: 'rs-test'}) DELETE n")


class TestFlowScore:
    def test_compute_flow_scores(self):
        from lib.graph_db import GraphDB
        from lib.graph_mycelium import compute_flow_scores

        db = GraphDB()
        if not db.is_available():
            pytest.skip("Neo4j not available")

        # Hub node B connects A to C (B should have higher flow score)
        db.execute_write("""
            MERGE (a:Note {slug: 'flow-a'}) MERGE (b:Note {slug: 'flow-b'}) MERGE (c:Note {slug: 'flow-c'})
            MERGE (a)-[:LINKS_TO]->(b) MERGE (b)-[:LINKS_TO]->(c)
        """)

        compute_flow_scores(db)
        result = db.execute(
            "MATCH (n:Note) WHERE n.slug STARTS WITH 'flow-' RETURN n.slug AS slug, n.flow_score AS f ORDER BY n.slug"
        )
        scores = {r["slug"]: r["f"] or 0 for r in result}
        assert scores.get("flow-b", 0) >= scores.get("flow-a", 0)

        db.execute_write("MATCH (n) WHERE n.slug STARTS WITH 'flow-' DETACH DELETE n")
