"""Tests for deal & relationship lifecycle tracker."""

import pytest
from datetime import datetime, timezone, timedelta


STAGES = ["cold", "warm-intro", "first-meeting", "active-conversation",
          "due-diligence", "committed", "closed"]


# ---------------------------------------------------------------------------
# Unit tests — no Neo4j required
# ---------------------------------------------------------------------------

class TestLifecycleStages:
    """Test stage definitions and transitions (pure logic, no DB)."""

    def test_stages_are_ordered(self):
        from lib.deal_tracker import LIFECYCLE_STAGES, stage_index
        assert stage_index("cold") < stage_index("warm-intro")
        assert stage_index("warm-intro") < stage_index("first-meeting")
        assert stage_index("due-diligence") < stage_index("committed")

    def test_can_advance_forward(self):
        from lib.deal_tracker import can_advance
        assert can_advance("cold", "warm-intro") is True
        assert can_advance("first-meeting", "active-conversation") is True

    def test_cannot_skip_stages(self):
        from lib.deal_tracker import can_advance
        assert can_advance("cold", "due-diligence") is False

    def test_cannot_go_backward(self):
        from lib.deal_tracker import can_advance
        assert can_advance("active-conversation", "cold") is False

    def test_unknown_stage_returns_negative_index(self):
        from lib.deal_tracker import stage_index
        assert stage_index("nonexistent") == -1

    def test_advance_criteria_match_stage_order(self):
        """Every ADVANCE_CRITERIA 'next' must be exactly one stage ahead."""
        from lib.deal_tracker import ADVANCE_CRITERIA, can_advance
        for current, criteria in ADVANCE_CRITERIA.items():
            assert can_advance(current, criteria["next"]) is True


class TestStalenessThresholds:
    """Test staleness threshold configuration (pure logic, no DB)."""

    def test_due_diligence_has_shortest_threshold(self):
        from lib.deal_tracker import STALENESS_THRESHOLDS
        assert STALENESS_THRESHOLDS["due-diligence"] < STALENESS_THRESHOLDS["active-conversation"]

    def test_cold_and_closed_have_no_threshold(self):
        from lib.deal_tracker import STALENESS_THRESHOLDS
        assert "cold" not in STALENESS_THRESHOLDS
        assert "closed" not in STALENESS_THRESHOLDS


# ---------------------------------------------------------------------------
# Integration tests — require live Neo4j
# ---------------------------------------------------------------------------

class TestStageAdvancement:
    """Test auto-advancing stages based on signals."""

    def test_advance_on_first_meeting(self):
        from lib.graph_db import GraphDB
        from lib.deal_tracker import evaluate_stage_transitions

        db = GraphDB()
        if not db.is_available():
            pytest.skip("Neo4j not available")

        meeting_date = (datetime.now(timezone.utc) - timedelta(days=3)).strftime("%Y-%m-%d")
        db.execute_write("""
            MERGE (p:Person {slug: 'deal-test-1', name: 'Deal Test 1',
                             relationship_stage: 'warm-intro'})
            MERGE (m:Meeting {slug: 'deal-meeting-1', date: $mdate})
            MERGE (p)-[:MET_WITH {date: $mdate}]->(m)
        """, {"mdate": meeting_date})

        transitions = evaluate_stage_transitions(db)
        advanced = [t for t in transitions if t["slug"] == "deal-test-1"]
        assert len(advanced) == 1
        assert advanced[0]["new_stage"] == "first-meeting"

        db.execute_write("MATCH (n) WHERE n.slug IN ['deal-test-1', 'deal-meeting-1'] DETACH DELETE n")

    def test_advance_to_active_on_repeat_meetings(self):
        from lib.graph_db import GraphDB
        from lib.deal_tracker import evaluate_stage_transitions

        db = GraphDB()
        if not db.is_available():
            pytest.skip("Neo4j not available")

        date_a = (datetime.now(timezone.utc) - timedelta(days=16)).strftime("%Y-%m-%d")
        date_b = (datetime.now(timezone.utc) - timedelta(days=6)).strftime("%Y-%m-%d")
        db.execute_write("""
            MERGE (p:Person {slug: 'deal-test-2', name: 'Deal Test 2',
                             relationship_stage: 'first-meeting'})
            MERGE (m1:Meeting {slug: 'deal-m2a', date: $da})
            MERGE (m2:Meeting {slug: 'deal-m2b', date: $db})
            MERGE (p)-[:MET_WITH]->(m1)
            MERGE (p)-[:MET_WITH]->(m2)
        """, {"da": date_a, "db": date_b})

        transitions = evaluate_stage_transitions(db)
        advanced = [t for t in transitions if t["slug"] == "deal-test-2"]
        assert len(advanced) == 1
        assert advanced[0]["new_stage"] == "active-conversation"

        db.execute_write("""
            MATCH (n) WHERE n.slug IN ['deal-test-2', 'deal-m2a', 'deal-m2b'] DETACH DELETE n
        """)


class TestStalenessDetection:
    """Test detecting stale relationships."""

    def test_detect_stale_active_conversation(self):
        from lib.graph_db import GraphDB
        from lib.deal_tracker import detect_stale_deals

        db = GraphDB()
        if not db.is_available():
            pytest.skip("Neo4j not available")

        # Person at active-conversation with last contact 45 days ago
        old_date = (datetime.now(timezone.utc) - timedelta(days=45)).strftime("%Y-%m-%d")
        db.execute_write("""
            MERGE (p:Person {slug: 'stale-test', name: 'Stale Test',
                             relationship_stage: 'active-conversation',
                             last_contact: $old_date})
        """, {"old_date": old_date})

        stale = detect_stale_deals(db)
        stale_slugs = [s["slug"] for s in stale]
        assert "stale-test" in stale_slugs

        db.execute_write("MATCH (n:Person {slug: 'stale-test'}) DELETE n")

    def test_not_stale_if_recent_contact(self):
        from lib.graph_db import GraphDB
        from lib.deal_tracker import detect_stale_deals

        db = GraphDB()
        if not db.is_available():
            pytest.skip("Neo4j not available")

        recent = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        db.execute_write("""
            MERGE (p:Person {slug: 'fresh-test', name: 'Fresh Test',
                             relationship_stage: 'active-conversation',
                             last_contact: $recent})
        """, {"recent": recent})

        stale = detect_stale_deals(db)
        stale_slugs = [s["slug"] for s in stale]
        assert "fresh-test" not in stale_slugs

        db.execute_write("MATCH (n:Person {slug: 'fresh-test'}) DELETE n")


class TestCommitmentTracking:
    """Test tracking what they asked for and whether we delivered."""

    def test_find_overdue_actions(self):
        from lib.graph_db import GraphDB
        from lib.deal_tracker import find_overdue_actions

        db = GraphDB()
        if not db.is_available():
            pytest.skip("Neo4j not available")

        old_date = (datetime.now(timezone.utc) - timedelta(days=5)).strftime("%Y-%m-%d")
        db.execute_write("""
            MERGE (p:Person {slug: 'action-test', name: 'Action Test',
                             next_action: 'Send compliance roadmap',
                             next_action_date: $old_date})
        """, {"old_date": old_date})

        overdue = find_overdue_actions(db)
        overdue_slugs = [o["slug"] for o in overdue]
        assert "action-test" in overdue_slugs

        db.execute_write("MATCH (n:Person {slug: 'action-test'}) DELETE n")
