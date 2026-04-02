"""Tests for natural language relationship queries."""

import pytest
from unittest.mock import MagicMock


class TestRelationshipQuery:
    """Test natural language relationship graph queries."""

    def test_parse_who_query(self):
        from lib.relationship_query import parse_query
        parsed = parse_query("Who do we know at A16Z?")
        assert parsed["type"] == "who_at_org"
        assert "a16z" in parsed["org"].lower()

    def test_parse_connection_query(self):
        from lib.relationship_query import parse_query
        parsed = parse_query("How are Kate and Andrew connected?")
        assert parsed["type"] == "connection"
        assert len(parsed["entities"]) == 2

    def test_parse_path_query(self):
        from lib.relationship_query import parse_query
        parsed = parse_query("Find paths between Kate Levchuk and Series A Fundraise within 3 hops")
        assert parsed["type"] == "path"
        assert parsed["max_hops"] == 3

    def test_execute_who_at_org(self):
        from lib.relationship_query import execute_query

        mock_db = MagicMock()
        mock_db.is_available.return_value = True
        mock_db.execute_read_only.return_value = [
            {"name": "Kate Levchuk", "slug": "kate-levchuk", "relationship": "WORKS_AT"},
            {"name": "Marc Andreessen", "slug": "marc-andreessen", "relationship": "FOUNDED"},
        ]

        result = execute_query(mock_db, {"type": "who_at_org", "org": "A16Z"})
        assert len(result["results"]) >= 1
        assert any("Kate" in r["name"] for r in result["results"])

    def test_execute_returns_empty_for_no_results(self):
        from lib.relationship_query import execute_query

        mock_db = MagicMock()
        mock_db.is_available.return_value = True
        mock_db.execute_read_only.return_value = []

        result = execute_query(mock_db, {"type": "who_at_org", "org": "NonexistentCorp"})
        assert result["results"] == []

    def test_query_end_to_end(self):
        from lib.relationship_query import relationship_query

        mock_db = MagicMock()
        mock_db.is_available.return_value = True
        mock_db.execute_read_only.return_value = [
            {"name": "Kate Levchuk", "slug": "kate-levchuk", "relationship": "WORKS_AT"},
        ]

        result = relationship_query(mock_db, "Who do we know at A16Z?")
        assert "results" in result
