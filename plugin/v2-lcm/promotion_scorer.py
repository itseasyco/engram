#!/usr/bin/env python3
"""
Promotion Scorer — Score LCM summaries for promotion to LACP.

Evaluates LCM session summaries against four dimensions:
  - confidence: How well-sourced and certain is this fact?
  - strategic_impact: Does it affect multiple projects/decisions?
  - reusability: Can other agents leverage this?
  - team_value: Would other team members benefit?

Score = (confidence × 0.4) + (strategic_impact × 0.3) +
        (reusability × 0.2) + (team_value × 0.1)
"""

import json
import re
import hashlib
from datetime import datetime, timezone
from typing import Optional


# Keywords that signal high strategic impact
STRATEGIC_KEYWORDS = [
    "architecture", "migration", "settlement", "treasury", "compliance",
    "security", "infrastructure", "deployment", "database", "schema",
    "authentication", "authorization", "payment", "integration", "api",
    "breaking-change", "deprecation", "incident", "outage", "rollback",
]

# Keywords that signal high reusability
REUSABILITY_KEYWORDS = [
    "pattern", "convention", "standard", "template", "utility",
    "shared", "common", "reusable", "library", "framework",
    "config", "setup", "workflow", "pipeline", "process",
]

# Categories for promoted facts
CATEGORIES = [
    "architectural-decision",
    "operational-knowledge",
    "domain-insight",
    "integration-pattern",
    "debugging-insight",
    "team-context",
    "process-improvement",
]

# Default promotion threshold
DEFAULT_THRESHOLD = 70


class PromotionScorer:
    """Score LCM summaries for promotion to LACP persistent memory."""

    def __init__(self, threshold: int = DEFAULT_THRESHOLD):
        self.threshold = threshold

    def score(self, lcm_summary: dict) -> dict:
        """
        Score an LCM summary for promotion to LACP.

        Args:
            lcm_summary: Dict with keys like 'content', 'source', 'citations',
                         'project', 'agent', 'timestamp', 'summary_id'.

        Returns:
            Dict with score (0-100), category, facts, and metadata.
        """
        content = lcm_summary.get("content", "")
        source = lcm_summary.get("source", "unknown")
        citations = lcm_summary.get("citations", [])
        project = lcm_summary.get("project", "")
        summary_id = lcm_summary.get("summary_id", "")

        confidence = self._score_confidence(content, source, citations)
        strategic_impact = self._score_strategic_impact(content, project)
        reusability = self._score_reusability(content)
        team_value = self._score_team_value(content, project)

        total = round(
            (confidence * 0.4)
            + (strategic_impact * 0.3)
            + (reusability * 0.2)
            + (team_value * 0.1),
            2,
        )

        facts = self.extract_facts(content)
        category = self.categorize(content, facts)

        return {
            "score": total,
            "threshold": self.threshold,
            "promote": total >= self.threshold,
            "category": category,
            "facts": facts,
            "breakdown": {
                "confidence": round(confidence, 2),
                "strategic_impact": round(strategic_impact, 2),
                "reusability": round(reusability, 2),
                "team_value": round(team_value, 2),
            },
            "summary_id": summary_id,
            "scored_at": datetime.now(timezone.utc).isoformat(),
        }

    def _score_confidence(
        self, content: str, source: str, citations: list
    ) -> float:
        """Score confidence based on source quality and citations."""
        score = 50.0  # base

        # Source quality
        trusted_sources = ["code", "git", "documentation", "api", "test"]
        if any(s in source.lower() for s in trusted_sources):
            score += 20.0

        # Citation count
        if len(citations) >= 3:
            score += 20.0
        elif len(citations) >= 1:
            score += 10.0

        # Content has specifics (code blocks, file paths, numbers)
        if re.search(r"```[\s\S]+```", content):
            score += 5.0
        if re.search(r"[/\\][\w./-]+\.\w+", content):
            score += 5.0
        if re.search(r"\b\d+\.\d+\.\d+\b", content):  # version numbers
            score += 5.0

        # Hedging language reduces confidence
        hedging = ["maybe", "might", "possibly", "unclear", "not sure", "perhaps"]
        hedging_count = sum(1 for h in hedging if h in content.lower())
        score -= hedging_count * 5.0

        return max(0.0, min(100.0, score))

    def _score_strategic_impact(self, content: str, project: str) -> float:
        """Score strategic impact based on keyword matches and scope."""
        score = 30.0  # base

        content_lower = content.lower()
        matches = sum(1 for kw in STRATEGIC_KEYWORDS if kw in content_lower)
        score += min(matches * 8.0, 50.0)

        # Multi-project references boost impact
        project_refs = re.findall(r"easy-\w+", content_lower)
        unique_projects = set(project_refs)
        if len(unique_projects) > 1:
            score += 15.0

        # Decision language boosts impact
        decision_words = ["decided", "chose", "selected", "adopted", "switched to"]
        if any(w in content_lower for w in decision_words):
            score += 10.0

        return max(0.0, min(100.0, score))

    def _score_reusability(self, content: str) -> float:
        """Score reusability based on pattern/convention language."""
        score = 30.0  # base

        content_lower = content.lower()
        matches = sum(1 for kw in REUSABILITY_KEYWORDS if kw in content_lower)
        score += min(matches * 7.0, 50.0)

        # Code examples increase reusability
        code_blocks = re.findall(r"```[\s\S]*?```", content)
        if len(code_blocks) >= 2:
            score += 15.0
        elif len(code_blocks) >= 1:
            score += 8.0

        return max(0.0, min(100.0, score))

    def _score_team_value(self, content: str, project: str) -> float:
        """Score team value based on cross-cutting concerns."""
        score = 40.0  # base

        content_lower = content.lower()

        # References to team roles/agents
        team_refs = ["andrew", "niko", "wren", "zoe", "agent", "team"]
        if any(ref in content_lower for ref in team_refs):
            score += 15.0

        # Onboarding/documentation value
        doc_words = ["how to", "steps to", "guide", "setup", "configure", "install"]
        if any(w in content_lower for w in doc_words):
            score += 15.0

        # Cross-project relevance
        if re.findall(r"easy-\w+", content_lower):
            score += 10.0

        return max(0.0, min(100.0, score))

    def extract_facts(self, content: str) -> list:
        """
        Extract atomic facts from content.

        Looks for:
        - Sentences with decision/fact indicators
        - Bullet points
        - Key-value declarations
        """
        facts = []

        # Extract bullet points as facts
        bullets = re.findall(r"^[\s]*[-*]\s+(.+)$", content, re.MULTILINE)
        for bullet in bullets:
            cleaned = bullet.strip()
            if len(cleaned) > 15 and len(cleaned) < 500:
                facts.append(cleaned)

        # Extract sentences with fact indicators
        fact_indicators = [
            r"(?:^|\.\s+)([A-Z][^.]*(?:is|are|was|were|uses?|requires?|handles?|runs?|stores?|processes?)[^.]*\.)",
            r"(?:^|\.\s+)([A-Z][^.]*(?:decided|chose|selected|adopted|switched)[^.]*\.)",
        ]
        for pattern in fact_indicators:
            matches = re.findall(pattern, content)
            for m in matches:
                cleaned = m.strip()
                if len(cleaned) > 15 and len(cleaned) < 500 and cleaned not in facts:
                    facts.append(cleaned)

        return facts[:20]  # cap at 20 facts

    def categorize(self, content: str, facts: list) -> str:
        """Categorize the content based on keywords and structure."""
        content_lower = content.lower()

        category_signals = {
            "architectural-decision": [
                "architecture", "decided", "chose", "design", "pattern",
                "schema", "migration", "infrastructure",
            ],
            "operational-knowledge": [
                "deploy", "monitor", "alert", "incident", "debug",
                "log", "performance", "scaling",
            ],
            "domain-insight": [
                "business", "user", "customer", "market", "compliance",
                "legal", "settlement", "treasury",
            ],
            "integration-pattern": [
                "api", "webhook", "integration", "connect", "sync",
                "endpoint", "protocol",
            ],
            "debugging-insight": [
                "bug", "fix", "error", "crash", "timeout", "retry",
                "workaround", "root cause",
            ],
            "team-context": [
                "team", "role", "responsibility", "workflow", "process",
                "meeting", "decision",
            ],
            "process-improvement": [
                "improve", "optimize", "automate", "streamline",
                "efficiency", "reduce", "eliminate",
            ],
        }

        scores = {}
        for category, signals in category_signals.items():
            scores[category] = sum(1 for s in signals if s in content_lower)

        if not scores or max(scores.values()) == 0:
            return "operational-knowledge"

        return max(scores, key=scores.get)

    def generate_receipt_hash(self, score_result: dict) -> str:
        """Generate a SHA-256 hash for the scoring result."""
        payload = json.dumps(score_result, sort_keys=True, default=str)
        return hashlib.sha256(payload.encode()).hexdigest()


def score_summary(summary_data: dict, threshold: int = DEFAULT_THRESHOLD) -> dict:
    """Convenience function to score a summary."""
    scorer = PromotionScorer(threshold=threshold)
    result = scorer.score(summary_data)
    result["receipt_hash"] = scorer.generate_receipt_hash(result)
    return result
