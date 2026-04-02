"""Tests for Neo4j connection manager."""

import pytest


# Tests that don't require a live Neo4j instance


class TestGraphDBConfig:
    def test_load_config_from_file(self, neo4j_config, monkeypatch):
        from lib.graph_db import GraphDB

        # Clear env vars so they don't override the file config
        monkeypatch.delenv("ENGRAM_NEO4J_BOLT_URL", raising=False)
        monkeypatch.delenv("ENGRAM_NEO4J_USERNAME", raising=False)
        monkeypatch.delenv("ENGRAM_NEO4J_PASSWORD", raising=False)
        db = GraphDB(config_path=str(neo4j_config))
        # neo4j_config fixture writes bolt_url from env or defaults to bolt://localhost:7687
        import json

        config_data = json.loads(neo4j_config.read_text())
        assert db.bolt_url == config_data["bolt_url"]

    def test_load_config_from_env(self, monkeypatch):
        from lib.graph_db import GraphDB

        monkeypatch.setenv("ENGRAM_NEO4J_BOLT_URL", "bolt://custom:7687")
        monkeypatch.setenv("ENGRAM_NEO4J_USERNAME", "custom_user")
        monkeypatch.setenv("ENGRAM_NEO4J_PASSWORD", "custom_pass")
        db = GraphDB()
        assert db.bolt_url == "bolt://custom:7687"

    def test_default_config_when_nothing_set(self, monkeypatch):
        from lib.graph_db import GraphDB

        monkeypatch.delenv("ENGRAM_NEO4J_BOLT_URL", raising=False)
        monkeypatch.delenv("ENGRAM_NEO4J_USERNAME", raising=False)
        monkeypatch.delenv("ENGRAM_NEO4J_PASSWORD", raising=False)
        monkeypatch.delenv("ENGRAM_NEO4J_DATABASE", raising=False)
        monkeypatch.delenv("OPENCLAW_PLUGIN_DIR", raising=False)
        db = GraphDB()
        assert db.bolt_url == "bolt://localhost:7687"


class TestGraphDBHealth:
    def test_is_available_returns_false_when_no_connection(self):
        from lib.graph_db import GraphDB

        db = GraphDB(config={"bolt_url": "bolt://nonexistent:9999"})
        assert db.is_available() is False

    def test_execute_returns_fallback_when_unavailable(self):
        from lib.graph_db import GraphDB

        db = GraphDB(config={"bolt_url": "bolt://nonexistent:9999"})
        result = db.execute("RETURN 1", fallback=[])
        assert result == []


class TestGraphDBQueries:
    def test_execute_with_params(self):
        from lib.graph_db import GraphDB

        db = GraphDB()
        if not db.is_available():
            pytest.skip("Neo4j not available")
        result = db.execute("RETURN $value AS v", params={"value": 42})
        assert result[0]["v"] == 42

    def test_execute_read_only(self):
        from lib.graph_db import GraphDB

        db = GraphDB()
        if not db.is_available():
            pytest.skip("Neo4j not available")
        # Write queries should fail in read-only mode
        with pytest.raises(Exception):
            db.execute_read_only("CREATE (n:Test) RETURN n")
