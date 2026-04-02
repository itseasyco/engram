"""
Neo4j connection manager for Engram.

Provides connection pooling, health checks, query execution with fallback,
and graceful degradation when Neo4j is unavailable.

Usage:
    from lib.graph_db import get_graph_db

    db = get_graph_db()
    if db.is_available():
        results = db.execute("MATCH (p:Person) RETURN p.name")
    else:
        # Fall back to JSON index
        ...
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("graph_db")

# Lazy import — neo4j driver may not be installed
_neo4j = None


def _ensure_driver():
    """Lazy-load the neo4j driver."""
    global _neo4j
    if _neo4j is None:
        try:
            import neo4j as _neo4j_module

            _neo4j = _neo4j_module
        except ImportError:
            logger.warning("neo4j driver not installed. Run: pip install neo4j")
            raise
    return _neo4j


class GraphDB:
    """Neo4j connection manager with graceful fallback."""

    def __init__(
        self,
        config: Optional[dict] = None,
        config_path: Optional[str] = None,
    ):
        self._driver = None
        self._config = self._load_config(config, config_path)
        self.bolt_url = self._config.get("bolt_url", "bolt://localhost:7687")
        self._username = self._config.get("username", "neo4j")
        self._password = self._config.get("password", "neo4j")
        self._database = self._config.get("database", "neo4j")
        self._pool_size = self._config.get("max_connection_pool_size", 10)
        self._timeout = self._config.get("connection_timeout", 5)

    def _load_config(self, config: Optional[dict], config_path: Optional[str]) -> dict:
        """Load config from: explicit dict > explicit path > env vars > default file > defaults."""
        if config:
            return config

        # Explicit config_path takes priority over env vars
        if config_path:
            path = Path(config_path)
            if path.exists():
                try:
                    return json.loads(path.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, IOError) as exc:
                    logger.warning("Failed to read Neo4j config at %s: %s", path, exc)

        # Env vars
        env_url = os.environ.get("ENGRAM_NEO4J_BOLT_URL")
        if env_url:
            return {
                "bolt_url": env_url,
                "username": os.environ.get("ENGRAM_NEO4J_USERNAME", "neo4j"),
                "password": os.environ.get("ENGRAM_NEO4J_PASSWORD", "neo4j"),
                "database": os.environ.get("ENGRAM_NEO4J_DATABASE", "neo4j"),
            }

        # Default config file location
        plugin_dir = os.environ.get(
            "OPENCLAW_PLUGIN_DIR",
            os.path.expanduser("~/.openclaw/extensions/engram"),
        )
        path = Path(plugin_dir) / "config" / "neo4j-config.json"

        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, IOError) as exc:
                logger.warning("Failed to read Neo4j config at %s: %s", path, exc)

        return {}

    def _connect(self):
        """Establish connection to Neo4j."""
        if self._driver is not None:
            return

        neo4j = _ensure_driver()
        self._driver = neo4j.GraphDatabase.driver(
            self.bolt_url,
            auth=(self._username, self._password),
            max_connection_pool_size=self._pool_size,
            connection_timeout=self._timeout,
        )

    def close(self):
        """Close the driver connection."""
        if self._driver:
            self._driver.close()
            self._driver = None

    def is_available(self) -> bool:
        """Check if Neo4j is reachable."""
        try:
            self._connect()
            self._driver.verify_connectivity()
            return True
        except Exception:
            return False

    def execute(
        self,
        query: str,
        params: Optional[dict] = None,
        fallback: Any = None,
    ) -> Any:
        """Execute a Cypher query. Returns fallback if Neo4j is unavailable."""
        try:
            self._connect()
            with self._driver.session(database=self._database) as session:
                result = session.run(query, params or {})
                return [dict(record) for record in result]
        except Exception as exc:
            logger.warning("Neo4j query failed: %s", exc)
            if fallback is not None:
                return fallback
            raise

    def execute_read_only(self, query: str, params: Optional[dict] = None) -> list[dict]:
        """Execute a read-only query. Raises on write attempts."""
        try:
            self._connect()
            with self._driver.session(database=self._database) as session:
                result = session.execute_read(
                    lambda tx: [dict(r) for r in tx.run(query, params or {})]
                )
                return result
        except Exception as exc:
            logger.warning("Neo4j read query failed: %s", exc)
            raise

    def execute_write(self, query: str, params: Optional[dict] = None) -> list[dict]:
        """Execute a write query within a transaction."""
        try:
            self._connect()
            with self._driver.session(database=self._database) as session:
                result = session.execute_write(
                    lambda tx: [dict(r) for r in tx.run(query, params or {})]
                )
                return result
        except Exception as exc:
            logger.warning("Neo4j write query failed: %s", exc)
            raise


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------

_instance: Optional[GraphDB] = None


def get_graph_db(config_path: Optional[str] = None) -> GraphDB:
    """Get or create the singleton GraphDB instance."""
    global _instance
    if _instance is None:
        _instance = GraphDB(config_path=config_path)
    return _instance


def reset_graph_db():
    """Close and reset the singleton (for testing)."""
    global _instance
    if _instance:
        _instance.close()
    _instance = None
