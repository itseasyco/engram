"""Tests for Neo4j schema setup."""

import pytest


class TestGraphSchema:
    def test_create_constraints(self):
        from lib.graph_db import GraphDB
        from lib.graph_schema import ensure_schema

        db = GraphDB()
        if not db.is_available():
            pytest.skip("Neo4j not available")

        result = ensure_schema(db)
        assert result["constraints_created"] >= 0
        assert result["indexes_created"] >= 0

    def test_node_types_registered(self):
        from lib.graph_schema import NODE_TYPES
        assert "Person" in NODE_TYPES
        assert "Organization" in NODE_TYPES
        assert "Goal" in NODE_TYPES
        assert "Meeting" in NODE_TYPES
        assert "Note" in NODE_TYPES

    def test_edge_types_registered(self):
        from lib.graph_schema import EDGE_TYPES
        assert "WORKS_AT" in EDGE_TYPES
        assert "PORTFOLIO_COMPANY_OF" in EDGE_TYPES
        assert "MET_WITH" in EDGE_TYPES
        assert "RELEVANT_TO" in EDGE_TYPES
        assert "LINKS_TO" in EDGE_TYPES

    def test_relationship_type_mapping(self):
        """Vault relationship types map to Cypher edge types."""
        from lib.graph_schema import vault_rel_to_cypher
        assert vault_rel_to_cypher("works-at") == "WORKS_AT"
        assert vault_rel_to_cypher("portfolio-company-of") == "PORTFOLIO_COMPANY_OF"
        assert vault_rel_to_cypher("met-with") == "MET_WITH"

    def test_schema_is_idempotent(self):
        from lib.graph_db import GraphDB
        from lib.graph_schema import ensure_schema

        db = GraphDB()
        if not db.is_available():
            pytest.skip("Neo4j not available")

        result1 = ensure_schema(db)
        result2 = ensure_schema(db)
        # Second run should not fail
        assert result2 is not None
