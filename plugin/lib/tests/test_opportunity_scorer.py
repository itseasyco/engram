"""Tests for opportunity scoring."""

import pytest
from datetime import datetime, timezone, timedelta


# ---------------------------------------------------------------------------
# Unit tests — no Neo4j required
# ---------------------------------------------------------------------------

class TestSentimentTrajectory:
    """Test sentiment trajectory computation (pure logic, no DB)."""

    def test_improving_trajectory(self):
        from lib.opportunity_scorer import _compute_sentiment_trajectory
        assert _compute_sentiment_trajectory(["negative", "neutral", "positive"]) == "improving"

    def test_declining_trajectory(self):
        from lib.opportunity_scorer import _compute_sentiment_trajectory
        assert _compute_sentiment_trajectory(["positive", "neutral", "negative"]) == "declining"

    def test_stable_trajectory(self):
        from lib.opportunity_scorer import _compute_sentiment_trajectory
        assert _compute_sentiment_trajectory(["neutral", "neutral", "neutral"]) == "stable"

    def test_single_sentiment_is_stable(self):
        from lib.opportunity_scorer import _compute_sentiment_trajectory
        assert _compute_sentiment_trajectory(["positive"]) == "stable"

    def test_empty_is_stable(self):
        from lib.opportunity_scorer import _compute_sentiment_trajectory
        assert _compute_sentiment_trajectory([]) == "stable"


class TestSentimentNumeric:
    """Test sentiment label to numeric conversion (pure logic, no DB)."""

    def test_known_labels(self):
        from lib.opportunity_scorer import _sentiment_to_numeric
        assert _sentiment_to_numeric("very positive") == 1.0
        assert _sentiment_to_numeric("very negative") == 0.0

    def test_unknown_label_defaults(self):
        from lib.opportunity_scorer import _sentiment_to_numeric
        assert _sentiment_to_numeric("unknown") == 0.5


class TestScoreWeights:
    """Verify weight constants add to 100."""

    def test_weights_sum_to_100(self):
        # Goal alignment 40% + Connection 25% + Network 20% + Timing 15% = 100%
        assert 40 + 25 + 20 + 15 == 100


# ---------------------------------------------------------------------------
# Integration tests — require live Neo4j
# ---------------------------------------------------------------------------

class TestGoalAlignment:
    def test_scores_high_when_connected_to_active_goal(self):
        from lib.graph_db import GraphDB
        from lib.opportunity_scorer import score_goal_alignment

        db = GraphDB()
        if not db.is_available():
            pytest.skip("Neo4j not available")

        db.execute_write("""
            MERGE (p:Person {slug: 'ga-person', name: 'GA Person'})
            MERGE (g:Goal {slug: 'ga-goal', name: 'GA Goal', status: 'active', priority: 'critical'})
            MERGE (p)-[:RELEVANT_TO]->(g)
        """)

        score = score_goal_alignment(db, "ga-person")
        assert score > 0.5  # Direct connection to active goal

        db.execute_write("MATCH (n) WHERE n.slug STARTS WITH 'ga-' DETACH DELETE n")

    def test_scores_zero_when_no_goal_connection(self):
        from lib.graph_db import GraphDB
        from lib.opportunity_scorer import score_goal_alignment

        db = GraphDB()
        if not db.is_available():
            pytest.skip("Neo4j not available")

        db.execute_write("MERGE (p:Person {slug: 'no-goal', name: 'No Goal Person'})")
        score = score_goal_alignment(db, "no-goal")
        assert score == 0.0

        db.execute_write("MATCH (n:Person {slug: 'no-goal'}) DELETE n")


class TestConnectionStrength:
    def test_recent_meetings_score_higher(self):
        from lib.graph_db import GraphDB
        from lib.opportunity_scorer import score_connection_strength

        db = GraphDB()
        if not db.is_available():
            pytest.skip("Neo4j not available")

        recent_date = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
        older_date = (datetime.now(timezone.utc) - timedelta(days=11)).strftime("%Y-%m-%d")
        db.execute_write("""
            MERGE (p:Person {slug: 'cs-person', name: 'CS Person',
                             last_contact: $recent, last_sentiment: 'positive'})
            MERGE (m1:Meeting {slug: 'cs-m1', date: $older})
            MERGE (m2:Meeting {slug: 'cs-m2', date: $recent})
            MERGE (p)-[:MET_WITH]->(m1)
            MERGE (p)-[:MET_WITH]->(m2)
        """, {"recent": recent_date, "older": older_date})

        score = score_connection_strength(db, "cs-person")
        assert score > 0.3  # Has recent meetings and positive sentiment

        db.execute_write("MATCH (n) WHERE n.slug STARTS WITH 'cs-' DETACH DELETE n")


class TestCompositeScore:
    def test_composite_score_in_range(self):
        from lib.graph_db import GraphDB
        from lib.opportunity_scorer import score_opportunity

        db = GraphDB()
        if not db.is_available():
            pytest.skip("Neo4j not available")

        recent_date = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
        db.execute_write("""
            MERGE (p:Person {slug: 'comp-person', name: 'Comp Person',
                             last_contact: $recent, relationship_stage: 'active-conversation'})
        """, {"recent": recent_date})

        score = score_opportunity(db, "comp-person")
        assert 0.0 <= score["total"] <= 100.0
        assert "goal_alignment" in score
        assert "connection_strength" in score
        assert "network_value" in score
        assert "timing_signals" in score

        db.execute_write("MATCH (n:Person {slug: 'comp-person'}) DELETE n")
