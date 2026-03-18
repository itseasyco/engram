"""
LCM Backend — Native lossless-claw context engine.

Reads directly from ~/.openclaw/lcm.db (SQLite) to discover summaries,
traverse the DAG, and find relevant context for task injection.
"""

import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from backends import ContextBackend


class LCMBackend(ContextBackend):
    """Context backend that reads from lossless-claw's native SQLite DAG.

The LCM database stores session summaries in a DAG structure where each
summary can have parent references, enabling full conversation history
traversal.
"""

    def __init__(self, config: dict):
        """Initialize with config dict.

Args:
    config: Dict with optional keys:
        - lcmDbPath: path to lcm.db (default: ~/.openclaw/lcm.db)
        - lcmQueryBatchSize: int (default: 50)
        - promotionThreshold: int (default: 70)
"""
        self._db_path = Path(os.path.expanduser(config.get("lcmDbPath", "~/.openclaw/lcm.db")))
        self._batch_size = config.get("lcmQueryBatchSize", 50)
        self._threshold = config.get("promotionThreshold", 70)

    def backend_name(self) -> str:
        """Return backend identifier."""
        return "lossless-claw"

    def is_available(self) -> bool:
        """Check if the LCM database exists and is readable."""
        if not self._db_path.exists():
            return False
        try:
            conn = sqlite3.connect(str(self._db_path))
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='summaries'")
            result = cursor.fetchone()
            conn.close()
            return result is not None
        except (sqlite3.Error, OSError):
            return False

    def _connect(self) -> sqlite3.Connection:
        """Open a connection to the LCM database."""
        if not self._db_path.exists():
            raise FileNotFoundError("LCM database not found: " + str(self._db_path))
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def fetch_summary(self, summary_id: str) -> dict:
        """Fetch a single summary by ID from the LCM database.

Args:
    summary_id: The unique summary identifier.

Returns:
    Summary dict or empty dict if not found.
"""
        try:
            conn = self._connect()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM summaries WHERE summary_id = ?", (summary_id,))
            row = cursor.fetchone()
            conn.close()
            if row:
                return self._row_to_dict(row)
            return {}
        except (sqlite3.Error, FileNotFoundError):
            return {}

    def discover_summaries(self, filters: dict) -> list:
        """Discover summaries matching filters.

Args:
    filters: Dict with optional keys: since, until, conversation_id,
             project, limit.

Returns:
    List of summary dicts sorted by timestamp descending.
"""
        conditions = []
        params = []

        if "since" in filters:
            conditions.append("timestamp >= ?")
            params.append(filters["since"])
        if "until" in filters:
            conditions.append("timestamp <= ?")
            params.append(filters["until"])
        if "conversation_id" in filters:
            conditions.append("conversation_id = ?")
            params.append(filters["conversation_id"])
        if "project" in filters:
            conditions.append("project = ?")
            params.append(filters["project"])

        limit = filters.get("limit", self._batch_size)
        params.append(limit)

        where_clause = " AND ".join(conditions) if conditions else "1=1"
        query = "SELECT * FROM summaries WHERE " + where_clause + " ORDER BY timestamp DESC LIMIT ?"

        try:
            conn = self._connect()
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
            conn.close()
            return [self._row_to_dict(row) for row in rows]
        except (sqlite3.Error, FileNotFoundError):
            return []

    def find_context(self, task: str, project: Optional[str] = None, limit: int = 10) -> list:
        """Find summaries relevant to a task using keyword matching.

Performs a keyword-based search over summary content, scoring by
term frequency overlap with the task description.

Args:
    task: Natural language task description.
    project: Optional project filter.
    limit: Maximum results.

Returns:
    List of scored summary dicts.
"""
        keywords = self._extract_keywords(task)

        try:
            conn = self._connect()
            cursor = conn.cursor()
            if project:
                cursor.execute(
                    "SELECT * FROM summaries WHERE project = ? ORDER BY timestamp DESC LIMIT ?",
                    (project, self._batch_size),
                )
            else:
                cursor.execute(
                    "SELECT * FROM summaries ORDER BY timestamp DESC LIMIT ?",
                    (self._batch_size,),
                )
            rows = cursor.fetchall()
            conn.close()

            scored = []
            for row in rows:
                summary = self._row_to_dict(row)
                content = summary.get("content", "").lower()
                score = sum(1 for kw in keywords if kw in content)
                if score > 0:
                    scored.append({
                        "summary_id": summary.get("summary_id", ""),
                        "content": content,
                        "relevance_score": round(score / len(keywords), 4) if keywords else 0,
                        "source": "lossless-claw",
                        "project": summary.get("project", ""),
                        "timestamp": summary.get("timestamp", ""),
                    })

            scored.sort(key=lambda x: x["relevance_score"], reverse=True)
            return scored[:limit]
        except (sqlite3.Error, FileNotFoundError):
            return []

    def traverse_dag(self, summary_id: str, depth: int = 3) -> dict:
        """Walk the parent chain of a summary.

Args:
    summary_id: Starting summary.
    depth: Max depth to traverse.

Returns:
    Dict with root summary, chain, and depth_reached.
"""
        chain = []
        current_id = summary_id
        depth_reached = -1

        try:
            conn = self._connect()
            cursor = conn.cursor()

            for i in range(depth + 1):
                cursor.execute("SELECT * FROM summaries WHERE summary_id = ?", (current_id,))
                row = cursor.fetchone()
                if not row:
                    break
                summary = self._row_to_dict(row)
                chain.append(summary)
                depth_reached = i
                parent_id = summary.get("parent_id", "")
                if not parent_id or parent_id == current_id:
                    break
                current_id = parent_id

            conn.close()
        except (sqlite3.Error, FileNotFoundError):
            pass

        return {
            "root": chain[-1] if chain else {},
            "chain": chain,
            "depth_reached": depth_reached,
        }

    def _row_to_dict(self, row) -> dict:
        """Convert a sqlite3.Row to a plain dict, parsing JSON fields."""
        d = dict(row)
        for json_field in ("citations", "tags", "metadata"):
            if json_field in d and isinstance(d[json_field], str):
                try:
                    d[json_field] = json.loads(d[json_field])
                except (json.JSONDecodeError, TypeError):
                    pass
        return d

    def _extract_keywords(self, text: str) -> list:
        """Extract meaningful keywords from text for search.

Filters out common stopwords and returns lowercase tokens.
"""
        stopwords = {
            "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
            "have", "has", "had", "do", "does", "did", "will", "would", "could",
            "should", "may", "might", "can", "shall", "to", "of", "in", "for",
            "on", "with", "at", "by", "from", "as", "into", "through", "during",
            "before", "after", "above", "below", "between", "out", "off", "over",
            "under", "again", "further", "then", "once", "here", "there", "when",
            "where", "why", "how", "all", "each", "every", "both", "few", "more",
            "most", "other", "some", "such", "no", "nor", "not", "only", "own",
            "same", "so", "than", "too", "very", "just", "because", "but", "and",
            "or", "if", "while", "about", "up", "it", "its", "this", "that",
            "these", "those", "what", "which", "who", "whom", "i", "me", "my",
            "we", "our", "you", "your", "he", "him", "his", "she", "her", "they",
            "them", "their",
        }
        words = re.findall(r"[a-zA-Z][\w-]*", text)
        return [w.lower() for w in words if w.lower() not in stopwords and len(w) > 2]

    def get_stats(self) -> dict:
        """Return statistics about the LCM database.

Returns:
    Dict with total_summaries, projects, date_range, backend name.
"""
        try:
            conn = self._connect()
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) FROM summaries")
            total = cursor.fetchone()[0]

            cursor.execute("SELECT DISTINCT project FROM summaries WHERE project IS NOT NULL AND project != ''")
            projects = [r[0] for r in cursor.fetchall()]

            cursor.execute("SELECT MIN(timestamp), MAX(timestamp) FROM summaries")
            date_range = cursor.fetchone()

            conn.close()

            return {
                "total_summaries": total,
                "projects": projects,
                "earliest": date_range[0] if date_range else None,
                "latest": date_range[1] if date_range else None,
                "db_path": str(self._db_path),
                "backend": "lossless-claw",
            }
        except (sqlite3.Error, FileNotFoundError):
            return {"error": "Could not read database stats"}
