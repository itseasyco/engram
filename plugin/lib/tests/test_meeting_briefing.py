"""Tests for meeting_briefing module."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# TestAttendeeContext — require live Neo4j
# ---------------------------------------------------------------------------


class TestAttendeeContext:
    """Tests that gather attendee context from the graph database."""

    def _get_db(self):
        from lib.graph_db import GraphDB

        db = GraphDB()
        if not db.is_available():
            pytest.skip("Neo4j not available")
        return db

    def _cleanup(self, db, slugs):
        """Remove test nodes created during the test."""
        for slug in slugs:
            db.execute(
                "MATCH (n {slug: $slug}) DETACH DELETE n",
                params={"slug": slug},
            )

    def test_gather_person_context_from_graph(self):
        """Create Person→Organization→Goal chain, verify context has orgs + goals."""
        from lib.meeting_briefing import gather_attendee_context

        db = self._get_db()
        slugs = ["test-person-brief", "test-org-brief", "test-goal-brief"]
        try:
            # Setup: create Person → WORKS_AT → Org, Org → RELATED_TO → Goal
            db.execute(
                "MERGE (p:Person {slug: 'test-person-brief', name: 'Test Person Brief'}) "
                "MERGE (o:Organization {slug: 'test-org-brief', name: 'Test Org Brief'}) "
                "MERGE (g:Goal {slug: 'test-goal-brief', title: 'Test Goal Brief', status: 'active'}) "
                "MERGE (p)-[:WORKS_AT]->(o) "
                "MERGE (o)-[:RELATED_TO]->(g)"
            )

            ctx = gather_attendee_context(db, "test-person-brief")

            assert ctx["is_new"] is False
            assert ctx["person"] is not None
            assert ctx["person"]["name"] == "Test Person Brief"
            assert len(ctx["organizations"]) >= 1
            assert any(o["name"] == "Test Org Brief" for o in ctx["organizations"])
            # Goal is within 3 hops: Person -> WORKS_AT -> Org -> RELATED_TO -> Goal
            assert len(ctx["relevant_goals"]) >= 1
            assert any(g["title"] == "Test Goal Brief" for g in ctx["relevant_goals"])
        finally:
            self._cleanup(db, slugs)

    def test_gather_context_includes_past_meetings(self):
        """Create Person→Meeting via MET_WITH, verify past_meetings populated."""
        from lib.meeting_briefing import gather_attendee_context

        db = self._get_db()
        slugs = ["test-person-mtg", "test-meeting-mtg"]
        try:
            db.execute(
                "MERGE (p:Person {slug: 'test-person-mtg', name: 'Test Meeting Person'}) "
                "MERGE (m:Meeting {slug: 'test-meeting-mtg', title: 'Past Sync', date: '2026-03-20'}) "
                "MERGE (p)-[:MET_WITH]->(m)"
            )

            ctx = gather_attendee_context(db, "test-person-mtg")

            assert ctx["is_new"] is False
            assert len(ctx["past_meetings"]) >= 1
            assert any(m["title"] == "Past Sync" for m in ctx["past_meetings"])
        finally:
            self._cleanup(db, slugs)

    def test_gather_context_for_unknown_person(self):
        """Query nonexistent slug, verify is_new=True, person=None."""
        from lib.meeting_briefing import gather_attendee_context

        db = self._get_db()
        ctx = gather_attendee_context(db, "nonexistent-person-xyz-999")

        assert ctx["is_new"] is True
        assert ctx["person"] is None


# ---------------------------------------------------------------------------
# TestWebSearch — use mock
# ---------------------------------------------------------------------------


class TestWebSearch:
    """Tests for web search context enrichment."""

    @patch("lib.meeting_briefing._call_web_search")
    def test_search_web_context_returns_results(self, mock_search):
        """Patch _call_web_search, verify results returned and deduplicated."""
        from lib.meeting_briefing import search_web_context

        mock_search.side_effect = [
            [
                {"title": "Article 1", "url": "https://example.com/1", "snippet": "..."},
                {"title": "Article 2", "url": "https://example.com/2", "snippet": "..."},
            ],
            [
                {"title": "Article 1 dup", "url": "https://example.com/1", "snippet": "..."},
                {"title": "Article 3", "url": "https://example.com/3", "snippet": "..."},
            ],
        ]

        results = search_web_context("Kate Levchuk", org_name="Andreessen Horowitz")

        assert len(results) == 3  # deduplicated
        urls = [r["url"] for r in results]
        assert "https://example.com/1" in urls
        assert "https://example.com/2" in urls
        assert "https://example.com/3" in urls

    @patch("lib.meeting_briefing._call_web_search")
    def test_search_web_context_handles_failure_gracefully(self, mock_search):
        """Patch with Exception, verify returns []."""
        from lib.meeting_briefing import search_web_context

        mock_search.side_effect = Exception("API error")

        results = search_web_context("Kate Levchuk")
        assert results == []


# ---------------------------------------------------------------------------
# TestTalkingPoints — use mock
# ---------------------------------------------------------------------------


class TestTalkingPoints:
    """Tests for AI-generated talking points."""

    @patch("lib.meeting_briefing._call_claude_api")
    def test_generate_talking_points_returns_list(self, mock_claude):
        """Patch _call_claude_api, verify parsed points."""
        from lib.meeting_briefing import generate_talking_points

        mock_claude.return_value = (
            "1. Discuss Series A timeline and milestones\n"
            "2. Review compliance roadmap for Q3\n"
            "3. Ask about portfolio company introductions\n"
        )

        contexts = [
            {
                "person": {"name": "Kate Levchuk"},
                "organizations": [{"name": "Andreessen Horowitz"}],
                "relevant_goals": [{"title": "Series A Fundraise"}],
                "past_meetings": [{"title": "Intro call", "date": "2026-03-01"}],
            }
        ]

        points = generate_talking_points(contexts, "Investor Call")

        assert len(points) == 3
        assert "Series A" in points[0]
        assert "compliance" in points[1].lower()

    @patch("lib.meeting_briefing._call_claude_api")
    def test_generate_talking_points_handles_llm_failure(self, mock_claude):
        """Patch with Exception, verify returns []."""
        from lib.meeting_briefing import generate_talking_points

        mock_claude.side_effect = Exception("API unavailable")

        points = generate_talking_points([], "Meeting")
        assert points == []


# ---------------------------------------------------------------------------
# TestBriefingGeneration — pure logic
# ---------------------------------------------------------------------------


class TestBriefingGeneration:
    """Tests for briefing formatting (pure logic, no mocks needed)."""

    def test_format_briefing_markdown(self):
        """Full attendee context, verify markdown contains name, org, goals, dates, starts with ---."""
        from lib.meeting_briefing import format_briefing

        contexts = [
            {
                "person": {"name": "Kate Levchuk"},
                "organizations": [{"name": "Andreessen Horowitz"}],
                "past_meetings": [
                    {"title": "Intro Call", "date": "2026-03-01"},
                    {"title": "Follow-up", "date": "2026-03-15"},
                ],
                "relevant_goals": [{"title": "Series A Fundraise", "status": "active"}],
                "network": [{"name": "Marc Andreessen"}],
                "web_context": [],
                "is_new": False,
            }
        ]

        md = format_briefing("Investor Sync", "2026-04-02", contexts)

        assert md.startswith("---")
        assert "Investor Sync" in md
        assert "Kate Levchuk" in md
        assert "Andreessen Horowitz" in md
        assert "Series A Fundraise" in md
        assert "2026-03-01" in md
        assert "2026-04-02" in md

    def test_format_briefing_handles_new_attendee(self):
        """is_new=True, verify 'First meeting' or 'No prior' appears."""
        from lib.meeting_briefing import format_briefing

        contexts = [
            {
                "person": {"name": "New Person"},
                "organizations": [],
                "past_meetings": [],
                "relevant_goals": [],
                "network": [],
                "web_context": [],
                "is_new": True,
            }
        ]

        md = format_briefing("Intro Call", "2026-04-02", contexts)

        assert "First meeting" in md or "No prior" in md

    def test_format_briefing_includes_talking_points(self):
        """Pass talking_points list, verify in output."""
        from lib.meeting_briefing import format_briefing

        contexts = [
            {
                "person": {"name": "Kate Levchuk"},
                "organizations": [],
                "past_meetings": [],
                "relevant_goals": [],
                "network": [],
                "web_context": [],
                "is_new": False,
            }
        ]

        points = [
            "Discuss Series A timeline",
            "Review compliance milestones",
            "Ask about portfolio introductions",
        ]

        md = format_briefing("Investor Call", "2026-04-02", contexts, talking_points=points)

        assert "Talking Points" in md
        assert "Discuss Series A timeline" in md
        assert "Review compliance milestones" in md
        assert "Ask about portfolio introductions" in md


# ---------------------------------------------------------------------------
# TestBriefingWriter
# ---------------------------------------------------------------------------


class TestBriefingWriter:
    """Tests for writing briefings to the vault."""

    def test_write_briefing_to_vault(self, temp_vault):
        """Write briefing, verify file exists."""
        from lib.meeting_briefing import write_briefing

        content = "---\ntitle: Test Briefing\n---\n\n# Test\n"
        result_path = write_briefing(str(temp_vault), "2026-04-02-test-meeting", content)

        expected = temp_vault / "meetings" / "briefings" / "2026-04-02-test-meeting.md"
        assert expected.exists()
        assert expected.read_text() == content
        assert result_path == expected
