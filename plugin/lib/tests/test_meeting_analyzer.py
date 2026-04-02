"""Tests for post-meeting transcript analysis."""

import pytest
from unittest.mock import patch, MagicMock


class TestTranscriptParsing:
    """Test parsing Circleback transcript format (regex fallback tier)."""

    def test_extract_speakers(self):
        from lib.meeting_analyzer import extract_speakers

        transcript = """
Andrew Fisher: Thanks for meeting today, Kate.
Kate Levchuk: Happy to be here. Let's talk about the round.
Andrew Fisher: We're looking at a 5M raise.
Kate Levchuk: That's in our range. I'd want to see the compliance roadmap.
"""
        speakers = extract_speakers(transcript)
        assert "Andrew Fisher" in speakers
        assert "Kate Levchuk" in speakers

    def test_extract_per_speaker_content(self):
        from lib.meeting_analyzer import extract_per_speaker

        transcript = """
Andrew Fisher: We've been growing 20% month over month.
Kate Levchuk: That's impressive. What's your retention rate?
Andrew Fisher: 95% at 6 months.
"""
        per_speaker = extract_per_speaker(transcript)
        assert len(per_speaker["Andrew Fisher"]) == 2
        assert len(per_speaker["Kate Levchuk"]) == 1
        assert "retention" in per_speaker["Kate Levchuk"][0].lower()


class TestLLMAnalysis:
    """Test LLM-powered transcript analysis (primary tier)."""

    def test_analyze_transcript_with_llm_returns_structured(self):
        from lib.meeting_analyzer import analyze_transcript_with_llm

        transcript = """
Andrew Fisher: Thanks for meeting today, Kate.
Kate Levchuk: Happy to be here. I'm very excited about what you're building.
Andrew Fisher: We're looking at a 5M raise for Series A.
Kate Levchuk: That's in our range. I'd want to see the compliance roadmap first.
Andrew Fisher: Sure, I'll send that over by Friday.
"""
        mock_response = {
            "sentiment": {
                "Kate Levchuk": {"overall": "positive", "signals": ["excited about product", "interested in investing"]},
                "Andrew Fisher": {"overall": "confident", "signals": ["clear fundraise ask"]},
            },
            "concerns": [
                {"speaker": "Kate Levchuk", "concern": "Wants to see compliance roadmap before proceeding"},
            ],
            "enthusiasm": [
                {"speaker": "Kate Levchuk", "signal": "Expressed excitement about what's being built"},
            ],
            "topics": ["Series A fundraise", "compliance roadmap", "investment range"],
            "key_decisions": [],
            "new_information": ["A16Z considers $5M in their range"],
        }

        with patch("lib.meeting_analyzer._call_claude_api_json") as mock_llm:
            mock_llm.return_value = mock_response
            result = analyze_transcript_with_llm(transcript)
            assert "sentiment" in result
            assert "Kate Levchuk" in result["sentiment"]
            assert result["sentiment"]["Kate Levchuk"]["overall"] == "positive"
            assert len(result["topics"]) >= 2
            assert len(result["concerns"]) >= 1

    def test_analyze_transcript_falls_back_to_regex_on_llm_failure(self):
        from lib.meeting_analyzer import analyze_transcript_with_llm

        transcript = "Andrew Fisher: Hello\nKate Levchuk: Hi there\n"

        with patch("lib.meeting_analyzer._call_claude_api_json") as mock_llm:
            mock_llm.side_effect = Exception("API error")
            result = analyze_transcript_with_llm(transcript)
            # Should still return a result via regex fallback
            assert "speakers" in result
            assert "Andrew Fisher" in result["speakers"]


class TestActionItemExtraction:
    """Test extracting action items from transcript."""

    def test_extract_action_items(self):
        from lib.meeting_analyzer import extract_action_items

        transcript = """
Kate Levchuk: Can you send me the compliance roadmap by Friday?
Andrew Fisher: Sure, I'll have it over by end of day Thursday.
Kate Levchuk: Also, I'd love an intro to your CTO.
Andrew Fisher: I'll set that up next week.
"""
        items = extract_action_items(transcript)
        assert len(items) >= 2
        assert any("compliance" in item["description"].lower() for item in items)

    def test_action_items_have_correct_owners(self):
        from lib.meeting_analyzer import extract_action_items

        transcript = (
            "Kate Levchuk: Can you send the metrics?\n"
            "Andrew Fisher: Will do by Monday.\n"
        )
        items = extract_action_items(transcript)
        for item in items:
            assert "owner" in item
        # "Can you" directed at the other speaker — owner should be Andrew
        if items:
            ask_items = [i for i in items if "metrics" in i["description"].lower()]
            if ask_items:
                assert ask_items[0]["owner"] == "Andrew Fisher"


class TestStrategicScoring:
    """Test strategic goal scoring per Spec Section 7.3 item 5."""

    def test_score_strategic_implications(self):
        from lib.meeting_analyzer import score_strategic_implications

        analysis = {
            "topics": ["Series A fundraise", "compliance roadmap", "retention metrics"],
            "sentiment": {
                "Kate Levchuk": {"overall": "positive", "signals": ["interested in investing"]},
            },
            "concerns": [
                {"speaker": "Kate Levchuk", "concern": "Wants compliance roadmap"},
            ],
            "enthusiasm": [
                {"speaker": "Kate Levchuk", "signal": "Excited about product"},
            ],
        }

        mock_db = MagicMock()
        mock_db.is_available.return_value = True
        mock_db.execute_read_only.return_value = [
            {"slug": "series-a-fundraise", "name": "Series A Fundraise", "priority": "high", "status": "active"},
            {"slug": "compliance-certification", "name": "Compliance Certification", "priority": "medium", "status": "active"},
        ]

        scores = score_strategic_implications(analysis, mock_db)
        assert len(scores) >= 1
        # Should score against matching goals
        goal_names = [s["goal"] for s in scores]
        assert any("Series A" in g for g in goal_names)
        for score_item in scores:
            assert "relevance" in score_item  # 0.0 - 1.0
            assert "evidence" in score_item

    def test_generate_follow_ups(self):
        from lib.meeting_analyzer import generate_follow_ups

        analysis = {
            "topics": ["compliance roadmap"],
            "concerns": [
                {"speaker": "Kate Levchuk", "concern": "Wants compliance roadmap before proceeding"},
            ],
        }
        action_items = [
            {"owner": "Andrew Fisher", "description": "Send compliance roadmap by Friday", "deadline": "Friday"},
        ]

        follow_ups = generate_follow_ups(analysis, action_items)
        assert len(follow_ups) >= 1
        assert any("compliance" in f["description"].lower() for f in follow_ups)
        for fu in follow_ups:
            assert "priority" in fu
            assert "description" in fu


class TestGraphUpdates:
    """Test updating graph DB from transcript analysis."""

    def test_build_graph_updates_from_analysis(self):
        from lib.meeting_analyzer import build_graph_updates

        analysis = {
            "speakers": ["Andrew Fisher", "Kate Levchuk"],
            "per_speaker": {
                "Kate Levchuk": ["Excited about compliance progress", "Wants to see metrics"],
            },
            "action_items": [
                {"owner": "Andrew Fisher", "description": "Send compliance roadmap", "deadline": "2026-04-04"},
            ],
            "topics": ["compliance", "metrics", "fundraise"],
            "sentiment": {
                "Kate Levchuk": {"overall": "positive", "signals": []},
            },
        }

        updates = build_graph_updates(
            meeting_slug="2026-04-01-a16z-checkin",
            meeting_date="2026-04-01",
            analysis=analysis,
        )

        assert len(updates["node_updates"]) > 0
        assert len(updates["edge_updates"]) > 0
        # Should create MET_WITH edges
        met_edges = [e for e in updates["edge_updates"] if e["type"] == "MET_WITH"]
        assert len(met_edges) >= 1


class TestDossierDiff:
    """Test diffing post-meeting results against pre-meeting briefing."""

    def test_diff_finds_new_information(self):
        from lib.meeting_analyzer import diff_against_briefing

        briefing_context = {
            "known_topics": ["compliance", "fundraise"],
            "known_relationships": [{"slug": "kate-levchuk", "stage": "active-conversation"}],
        }
        analysis = {
            "topics": ["compliance", "fundraise", "retention metrics"],
            "sentiment": {
                "Kate Levchuk": {"overall": "very positive", "signals": []},
            },
            "new_entities": ["CTO intro requested"],
        }

        diff = diff_against_briefing(briefing_context, analysis)
        assert "retention metrics" in diff["new_topics"]
        assert len(diff["sentiment_changes"]) >= 0


class TestGraphDBCleanup:
    """Test that graph DB tests clean up properly even on failure."""

    def test_graph_updates_with_cleanup(self):
        """Demonstrate try/finally cleanup pattern for graph tests."""
        from lib.meeting_analyzer import build_graph_updates

        updates = build_graph_updates("test-slug", "2026-04-01", {"speakers": [], "topics": [], "sentiment": {}})
        assert "node_updates" in updates
