#!/usr/bin/env python3
"""Tests for the Promotion Scorer module."""

import json
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from promotion_scorer import PromotionScorer, score_summary, CATEGORIES


class TestPromotionScorerInit:
    """Test scorer initialization."""

    def test_default_threshold(self):
        scorer = PromotionScorer()
        assert scorer.threshold == 70

    def test_custom_threshold(self):
        scorer = PromotionScorer(threshold=90)
        assert scorer.threshold == 90

    def test_zero_threshold(self):
        scorer = PromotionScorer(threshold=0)
        assert scorer.threshold == 0


class TestConfidenceScoring:
    """Test confidence dimension scoring."""

    def setup_method(self):
        self.scorer = PromotionScorer()

    def test_base_confidence(self):
        result = self.scorer._score_confidence("Simple fact.", "unknown", [])
        assert result >= 40  # base is 50, no bonuses/penalties expected to be extreme

    def test_trusted_source_boosts(self):
        low = self.scorer._score_confidence("A fact.", "unknown", [])
        high = self.scorer._score_confidence("A fact.", "code", [])
        assert high > low

    def test_citations_boost(self):
        no_cite = self.scorer._score_confidence("A fact.", "unknown", [])
        one_cite = self.scorer._score_confidence("A fact.", "unknown", ["ref1"])
        many_cite = self.scorer._score_confidence("A fact.", "unknown", ["r1", "r2", "r3"])
        assert one_cite > no_cite
        assert many_cite > one_cite

    def test_code_blocks_boost(self):
        without = self.scorer._score_confidence("A fact.", "unknown", [])
        with_code = self.scorer._score_confidence("A fact. ```python\nprint('hi')```", "unknown", [])
        assert with_code > without

    def test_version_numbers_boost(self):
        without = self.scorer._score_confidence("Use the library for tasks.", "unknown", [])
        with_ver = self.scorer._score_confidence("Use the library version 2.1.0 for tasks.", "unknown", [])
        assert with_ver > without

    def test_hedging_reduces(self):
        confident = self.scorer._score_confidence("Finix is the payment provider.", "unknown", [])
        hedging = self.scorer._score_confidence("Maybe Finix is possibly the payment provider.", "unknown", [])
        assert hedging < confident

    def test_score_clamped_0_100(self):
        # Lots of hedging
        score = self.scorer._score_confidence(
            "maybe possibly unclear not sure perhaps maybe", "unknown", []
        )
        assert score >= 0
        assert score <= 100

    def test_file_path_boost(self):
        without = self.scorer._score_confidence("The handler does this.", "unknown", [])
        with_path = self.scorer._score_confidence("The handler at /src/routes/api.ts does this.", "unknown", [])
        assert with_path > without


class TestStrategicImpactScoring:
    """Test strategic impact dimension."""

    def setup_method(self):
        self.scorer = PromotionScorer()

    def test_base_strategic(self):
        result = self.scorer._score_strategic_impact("Hello world.", "test")
        assert result >= 20

    def test_strategic_keywords_boost(self):
        low = self.scorer._score_strategic_impact("A simple change.", "test")
        high = self.scorer._score_strategic_impact(
            "Architecture migration for database schema security.", "test"
        )
        assert high > low

    def test_multi_project_boost(self):
        single = self.scorer._score_strategic_impact("easy-api needs changes.", "test")
        multi = self.scorer._score_strategic_impact(
            "Both easy-api and easy-dashboard need the same update.", "test"
        )
        assert multi > single

    def test_decision_language_boost(self):
        passive = self.scorer._score_strategic_impact("The system uses Finix.", "test")
        active = self.scorer._score_strategic_impact("We decided to use Finix for payments.", "test")
        assert active > passive

    def test_clamped_0_100(self):
        score = self.scorer._score_strategic_impact(
            "architecture migration database schema security infrastructure deployment authentication payment",
            "test"
        )
        assert score <= 100


class TestReusabilityScoring:
    """Test reusability dimension."""

    def setup_method(self):
        self.scorer = PromotionScorer()

    def test_base_reusability(self):
        result = self.scorer._score_reusability("Something happened.")
        assert result >= 20

    def test_reusability_keywords_boost(self):
        low = self.scorer._score_reusability("A one-off thing happened.")
        high = self.scorer._score_reusability(
            "This pattern is a standard template for the shared pipeline config."
        )
        assert high > low

    def test_code_examples_boost(self):
        without = self.scorer._score_reusability("Use this pattern for routing.")
        with_code = self.scorer._score_reusability(
            "Use this pattern for routing:\n```python\ndef route(): pass\n```\nAnd also:\n```python\ndef handle(): pass\n```"
        )
        assert with_code > without


class TestTeamValueScoring:
    """Test team value dimension."""

    def setup_method(self):
        self.scorer = PromotionScorer()

    def test_base_team_value(self):
        result = self.scorer._score_team_value("Generic fact.", "test")
        assert result >= 30

    def test_team_references_boost(self):
        low = self.scorer._score_team_value("A config change.", "test")
        high = self.scorer._score_team_value("Andrew and the team need this.", "test")
        assert high > low

    def test_documentation_value_boost(self):
        low = self.scorer._score_team_value("It works differently now.", "test")
        high = self.scorer._score_team_value("Here is how to setup and configure the system.", "test")
        assert high > low

    def test_cross_project_boost(self):
        low = self.scorer._score_team_value("A local change.", "test")
        high = self.scorer._score_team_value("Changes needed in easy-api and easy-dashboard.", "test")
        assert high > low


class TestFactExtraction:
    """Test fact extraction from content."""

    def setup_method(self):
        self.scorer = PromotionScorer()

    def test_extract_bullet_points(self):
        content = "Summary:\n- Finix handles payment processing\n- Brale handles stablecoin settlement\n- Auth0 manages authentication"
        facts = self.scorer.extract_facts(content)
        assert len(facts) >= 3

    def test_extract_sentences_with_verbs(self):
        content = "Finix is the payment processor. Brale handles stablecoin conversion. The system uses RLS policies."
        facts = self.scorer.extract_facts(content)
        assert len(facts) >= 1

    def test_skip_short_facts(self):
        content = "- OK\n- Yes\n- This is a longer fact about the system architecture"
        facts = self.scorer.extract_facts(content)
        for fact in facts:
            assert len(fact) > 15

    def test_cap_at_20_facts(self):
        content = "\n".join([f"- This is fact number {i} about the system" for i in range(30)])
        facts = self.scorer.extract_facts(content)
        assert len(facts) <= 20

    def test_empty_content(self):
        facts = self.scorer.extract_facts("")
        assert facts == []

    def test_no_duplicates(self):
        content = "Finix is the payment processor. Finix is the payment processor."
        facts = self.scorer.extract_facts(content)
        # Should not have exact duplicates
        assert len(facts) == len(set(facts))


class TestCategorization:
    """Test content categorization."""

    def setup_method(self):
        self.scorer = PromotionScorer()

    def test_architectural_decision(self):
        content = "We decided on a new architecture design pattern for the database migration."
        category = self.scorer.categorize(content, [])
        assert category == "architectural-decision"

    def test_operational_knowledge(self):
        content = "The deploy pipeline monitors alerts and logs performance metrics for scaling."
        category = self.scorer.categorize(content, [])
        assert category == "operational-knowledge"

    def test_domain_insight(self):
        content = "Business compliance requires the settlement treasury to meet legal requirements."
        category = self.scorer.categorize(content, [])
        assert category == "domain-insight"

    def test_integration_pattern(self):
        content = "The API webhook integration connects to the sync endpoint via protocol."
        category = self.scorer.categorize(content, [])
        assert category == "integration-pattern"

    def test_debugging_insight(self):
        content = "The bug fix for the timeout error crash required a retry workaround."
        category = self.scorer.categorize(content, [])
        assert category == "debugging-insight"

    def test_default_category(self):
        content = "xyzzy foobar baz"
        category = self.scorer.categorize(content, [])
        assert category == "operational-knowledge"

    def test_all_categories_valid(self):
        for cat in CATEGORIES:
            assert isinstance(cat, str)
            assert len(cat) > 0


class TestFullScoring:
    """Test the complete scoring pipeline."""

    def setup_method(self):
        self.scorer = PromotionScorer()

    def test_score_returns_required_fields(self):
        result = self.scorer.score({"content": "Test fact.", "source": "code"})
        assert "score" in result
        assert "threshold" in result
        assert "promote" in result
        assert "category" in result
        assert "facts" in result
        assert "breakdown" in result
        assert "scored_at" in result

    def test_breakdown_has_all_dimensions(self):
        result = self.scorer.score({"content": "Test."})
        breakdown = result["breakdown"]
        assert "confidence" in breakdown
        assert "strategic_impact" in breakdown
        assert "reusability" in breakdown
        assert "team_value" in breakdown

    def test_high_quality_content_scores_high(self):
        result = self.scorer.score({
            "content": (
                "We decided to use Finix as the payment architecture for easy-api and easy-dashboard. "
                "This pattern is a standard template shared across the team. "
                "Here is how to setup the integration:\n"
                "```python\nclient = finix.Client(api_key=os.environ['FINIX_KEY'])\n```\n"
                "- Finix handles payment processing\n"
                "- Brale handles stablecoin settlement\n"
                "- Auth0 manages authentication"
            ),
            "source": "code",
            "citations": ["architecture.md", "CONTRIBUTING.md", "README.md"],
            "project": "easy-api",
            "summary_id": "sum_test123",
        })
        assert result["score"] >= 60

    def test_low_quality_content_scores_low(self):
        result = self.scorer.score({
            "content": "maybe something unclear happened possibly",
            "source": "unknown",
            "citations": [],
        })
        assert result["score"] < 70

    def test_promote_flag_respects_threshold(self):
        scorer_low = PromotionScorer(threshold=10)
        scorer_high = PromotionScorer(threshold=99)
        summary = {"content": "A moderate fact about the system.", "source": "code"}
        assert scorer_low.score(summary)["promote"] is True
        assert scorer_high.score(summary)["promote"] is False

    def test_score_range_0_100(self):
        result = self.scorer.score({"content": "Test."})
        assert 0 <= result["score"] <= 100

    def test_summary_id_passed_through(self):
        result = self.scorer.score({"content": "Test.", "summary_id": "sum_xyz"})
        assert result["summary_id"] == "sum_xyz"


class TestReceiptHash:
    """Test receipt hash generation."""

    def setup_method(self):
        self.scorer = PromotionScorer()

    def test_hash_is_sha256(self):
        result = self.scorer.score({"content": "Test."})
        hash_val = self.scorer.generate_receipt_hash(result)
        assert len(hash_val) == 64
        assert all(c in "0123456789abcdef" for c in hash_val)

    def test_hash_deterministic(self):
        result = self.scorer.score({"content": "Test."})
        h1 = self.scorer.generate_receipt_hash(result)
        h2 = self.scorer.generate_receipt_hash(result)
        assert h1 == h2

    def test_different_content_different_hash(self):
        r1 = self.scorer.score({"content": "Fact A."})
        r2 = self.scorer.score({"content": "Fact B."})
        assert self.scorer.generate_receipt_hash(r1) != self.scorer.generate_receipt_hash(r2)


class TestConvenienceFunction:
    """Test the score_summary convenience function."""

    def test_score_summary_returns_receipt_hash(self):
        result = score_summary({"content": "Test fact.", "source": "code"})
        assert "receipt_hash" in result
        assert len(result["receipt_hash"]) == 64

    def test_score_summary_custom_threshold(self):
        result = score_summary({"content": "Test."}, threshold=10)
        assert result["threshold"] == 10

    def test_score_summary_with_full_data(self):
        result = score_summary({
            "content": "Finix is the payment processor for easy-api.",
            "source": "documentation",
            "citations": ["arch.md"],
            "project": "easy-api",
            "summary_id": "sum_full_test",
        })
        assert result["summary_id"] == "sum_full_test"
        assert isinstance(result["facts"], list)
