"""
Post-meeting transcript analyzer for Engram.

Processes Circleback transcripts using a two-tier approach:
  - Primary: LLM analysis via Claude API for sentiment, concerns, enthusiasm, topics
  - Fallback: Regex-based extraction when LLM is unavailable

Extracts:
- Per-speaker contributions and sentiment (LLM-primary)
- Action items with owners and deadlines
- Topics discussed
- New entities and relationships
- Strategic implications scored against active goals (Spec 7.3 item 5)
- Follow-up recommendations

Updates the knowledge graph with new information.
"""

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .entity_extractor import _slugify

logger = logging.getLogger("meeting_analyzer")


# ---------------------------------------------------------------------------
# LLM integration
# ---------------------------------------------------------------------------

def _call_claude_api_json(prompt: str, max_tokens: int = 2048) -> dict:
    """
    Call Claude API and parse JSON response.

    Args:
        prompt: The prompt to send (should request JSON output).
        max_tokens: Maximum tokens in response.

    Returns:
        Parsed JSON dict from Claude's response.

    Raises:
        Exception if API call fails or response isn't valid JSON.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")

    try:
        import anthropic
    except ImportError:
        raise RuntimeError("anthropic package not installed (pip install anthropic)")

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    text = message.content[0].text.strip()

    # Extract JSON from response (handle markdown code fences)
    if text.startswith("```"):
        lines = text.split("\n")
        json_lines = []
        in_fence = False
        for line in lines:
            if line.strip().startswith("```"):
                in_fence = not in_fence
                continue
            if in_fence or not line.strip().startswith("```"):
                json_lines.append(line)
        text = "\n".join(json_lines).strip()

    return json.loads(text)


def analyze_transcript_with_llm(transcript: str) -> dict:
    """
    Send transcript to Claude with a structured prompt for analysis.

    Per Spec Section 7.3: LLM-powered analysis is the primary tier.
    Regex extraction (extract_speakers, extract_per_speaker) is the fallback.

    Analyzes: sentiment per speaker, concerns raised, enthusiasm signals,
    topics discussed, key decisions, new information.

    Args:
        transcript: Full meeting transcript text.

    Returns:
        Structured analysis dict with keys:
        - sentiment: {speaker: {overall: str, signals: [str]}}
        - concerns: [{speaker: str, concern: str}]
        - enthusiasm: [{speaker: str, signal: str}]
        - topics: [str]
        - key_decisions: [str]
        - new_information: [str]
        - speakers: [str]

        On LLM failure, falls back to regex-based extraction.
    """
    prompt = (
        "Analyze this meeting transcript and return a JSON object with the following structure:\n\n"
        "{\n"
        '  "sentiment": {"Speaker Name": {"overall": "positive|negative|neutral|mixed", '
        '"signals": ["specific signal from transcript"]}},\n'
        '  "concerns": [{"speaker": "Name", "concern": "What they expressed concern about"}],\n'
        '  "enthusiasm": [{"speaker": "Name", "signal": "What they were enthusiastic about"}],\n'
        '  "topics": ["topic1", "topic2"],\n'
        '  "key_decisions": ["Decision that was made"],\n'
        '  "new_information": ["New fact or insight revealed"]\n'
        "}\n\n"
        "Be specific and cite evidence from the transcript for sentiment signals.\n\n"
        f"Transcript:\n{transcript}\n\n"
        "Return ONLY valid JSON, no markdown fences or preamble."
    )

    try:
        result = _call_claude_api_json(prompt)
        # Ensure required keys exist
        result.setdefault("sentiment", {})
        result.setdefault("concerns", [])
        result.setdefault("enthusiasm", [])
        result.setdefault("topics", [])
        result.setdefault("key_decisions", [])
        result.setdefault("new_information", [])
        # Add speakers list from sentiment keys + regex extraction
        result["speakers"] = list(result["sentiment"].keys()) or extract_speakers(transcript)
        return result
    except Exception as exc:
        logger.warning("LLM transcript analysis failed, falling back to regex: %s", exc)
        # Fallback to regex-based extraction
        return _regex_fallback_analysis(transcript)


def _regex_fallback_analysis(transcript: str) -> dict:
    """
    Regex-based transcript analysis (fallback tier).

    Provides basic extraction when LLM is unavailable.
    """
    speakers = extract_speakers(transcript)
    per_speaker = extract_per_speaker(transcript)

    # Basic topic extraction from all statements
    all_text = " ".join(
        stmt for stmts in per_speaker.values() for stmt in stmts
    ).lower()

    # Simple keyword-based topic detection
    topic_keywords = {
        "fundraise": ["fundraise", "raise", "round", "series", "investment", "valuation"],
        "compliance": ["compliance", "regulation", "audit", "certification"],
        "metrics": ["metrics", "retention", "growth", "revenue", "mrr", "arr"],
        "product": ["product", "feature", "roadmap", "launch", "release"],
        "hiring": ["hiring", "team", "recruit", "headcount"],
        "partnership": ["partnership", "integration", "collaboration"],
    }
    topics = []
    for topic, keywords in topic_keywords.items():
        if any(kw in all_text for kw in keywords):
            topics.append(topic)

    return {
        "speakers": speakers,
        "per_speaker": per_speaker,
        "sentiment": {s: {"overall": "unknown", "signals": []} for s in speakers},
        "concerns": [],
        "enthusiasm": [],
        "topics": topics,
        "key_decisions": [],
        "new_information": [],
        "_analysis_method": "regex_fallback",
    }


# ---------------------------------------------------------------------------
# Transcript parsing (regex tier — used as fallback and for action items)
# ---------------------------------------------------------------------------

def extract_speakers(transcript: str) -> list[str]:
    """Extract unique speaker names from transcript."""
    pattern = r'^([A-Z][a-zA-Z]+ [A-Z][a-zA-Z]+):'
    speakers = set()
    for line in transcript.strip().split("\n"):
        match = re.match(pattern, line.strip())
        if match:
            speakers.add(match.group(1))
    return sorted(speakers)


def extract_per_speaker(transcript: str) -> dict[str, list[str]]:
    """Extract what each speaker said, grouped by speaker."""
    per_speaker = {}
    pattern = r'^([A-Z][a-zA-Z]+ [A-Z][a-zA-Z]+):\s*(.+)'

    for line in transcript.strip().split("\n"):
        match = re.match(pattern, line.strip())
        if match:
            speaker, content = match.groups()
            per_speaker.setdefault(speaker, []).append(content.strip())

    return per_speaker


def extract_action_items(transcript: str) -> list[dict]:
    """
    Extract action items from transcript.

    Looks for patterns like:
    - "Can you send...", "I'll...", "Will do by...", "Let's schedule..."
    - Deadline indicators: "by Friday", "next week", "end of day"

    Owner attribution logic:
    - "Can you / Could you / Please" -> owner is the OTHER speaker (the
      person being asked), identified as the next speaker in the transcript
    - "I'll / I will / Will do / Let me" -> owner is the speaker themselves
    """
    items = []
    action_patterns = [
        r"(?:can you|could you|please|I'll|I will|will do|let me|let's)\s+(.+)",
        r"(?:send|share|prepare|set up|schedule|follow up|get back)\s+(.+)",
    ]

    per_speaker = extract_per_speaker(transcript)
    speakers = extract_speakers(transcript)

    # Build an ordered list of (speaker, statement) for context
    ordered_turns = []
    turn_pattern = r'^([A-Z][a-zA-Z]+ [A-Z][a-zA-Z]+):\s*(.+)'
    for line in transcript.strip().split("\n"):
        match = re.match(turn_pattern, line.strip())
        if match:
            ordered_turns.append((match.group(1), match.group(2).strip()))

    for idx, (speaker, stmt) in enumerate(ordered_turns):
        for pattern in action_patterns:
            match = re.search(pattern, stmt, re.IGNORECASE)
            if match:
                # Determine owner based on phrasing
                is_request_to_other = any(
                    w in stmt.lower() for w in ["can you", "could you", "please send"]
                )
                if is_request_to_other:
                    # Owner is the person being asked — look for next speaker
                    # or find the other participant
                    owner = None
                    for future_idx in range(idx + 1, len(ordered_turns)):
                        future_speaker = ordered_turns[future_idx][0]
                        if future_speaker != speaker:
                            owner = future_speaker
                            break
                    if owner is None:
                        # Fall back to any other speaker
                        other_speakers = [s for s in speakers if s != speaker]
                        owner = other_speakers[0] if other_speakers else speaker
                else:
                    # Self-assigned: "I'll do X", "Will do by Y"
                    owner = speaker

                # Look for deadline
                deadline = None
                deadline_patterns = [
                    r"by\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)",
                    r"by\s+(end of (?:day|week|month))",
                    r"(next week|this week|tomorrow)",
                ]
                for dp in deadline_patterns:
                    dm = re.search(dp, stmt, re.IGNORECASE)
                    if dm:
                        deadline = dm.group(1)
                        break

                items.append({
                    "owner": owner,
                    "description": stmt.strip(),
                    "deadline": deadline,
                    "source_speaker": speaker,
                })
                break  # One match per statement

    return items


# ---------------------------------------------------------------------------
# Strategic goal scoring (Spec Section 7.3 item 5)
# ---------------------------------------------------------------------------

def score_strategic_implications(analysis: dict, db) -> list[dict]:
    """
    Score strategic implications of meeting against active goals.

    Per Spec Section 7.3 item 5: "Score strategic implications against active goals."

    Queries the graph DB for all active goals, then scores each goal's relevance
    to the meeting based on topic overlap, sentiment signals, and concerns.

    Args:
        analysis: Structured analysis dict from analyze_transcript_with_llm.
        db: GraphDB instance.

    Returns:
        List of dicts with keys: goal, goal_slug, relevance (0.0-1.0),
        evidence (list of strings), impact (positive/negative/neutral).
    """
    if not db or not db.is_available():
        logger.warning("Graph DB not available for strategic scoring")
        return []

    # Fetch active goals
    goals = db.execute_read_only(
        "MATCH (g:Goal {status: 'active'}) "
        "RETURN g.slug AS slug, g.name AS name, g.priority AS priority, "
        "       g.description AS description",
    )

    if not goals:
        return []

    topics = set(t.lower() for t in analysis.get("topics", []))
    concerns = analysis.get("concerns", [])
    enthusiasm = analysis.get("enthusiasm", [])
    sentiment = analysis.get("sentiment", {})

    scores = []
    for goal in goals:
        goal_name = goal.get("name", "").lower()
        goal_slug = goal.get("slug", "")
        goal_desc = (goal.get("description", "") or "").lower()
        goal_words = set(goal_name.split()) | set(goal_desc.split())

        # Score topic overlap
        evidence = []
        topic_overlap = 0
        for topic in topics:
            topic_words = set(topic.lower().split())
            if topic_words & goal_words:
                topic_overlap += 1
                evidence.append(f"Topic '{topic}' relates to goal")

        if topic_overlap == 0:
            continue  # No relevance to this goal

        # Score sentiment alignment
        positive_signals = sum(
            1 for e in enthusiasm
            if any(w in e.get("signal", "").lower() for w in goal_words)
        )
        negative_signals = sum(
            1 for c in concerns
            if any(w in c.get("concern", "").lower() for w in goal_words)
        )

        if positive_signals > 0:
            evidence.append(f"{positive_signals} enthusiasm signal(s) aligned with goal")
        if negative_signals > 0:
            evidence.append(f"{negative_signals} concern(s) related to goal")

        # Calculate relevance score (0.0 - 1.0)
        relevance = min(1.0, (topic_overlap * 0.4 + positive_signals * 0.3 + negative_signals * 0.2) / 1.0)

        # Determine impact direction
        if positive_signals > negative_signals:
            impact = "positive"
        elif negative_signals > positive_signals:
            impact = "negative"
        else:
            impact = "neutral"

        # Boost relevance for high-priority goals
        priority = goal.get("priority", "").lower()
        if priority == "high":
            relevance = min(1.0, relevance * 1.2)

        scores.append({
            "goal": goal.get("name", goal_slug),
            "goal_slug": goal_slug,
            "relevance": round(relevance, 2),
            "evidence": evidence,
            "impact": impact,
            "priority": priority,
        })

    # Sort by relevance descending
    scores.sort(key=lambda s: s["relevance"], reverse=True)
    return scores


def generate_follow_ups(analysis: dict, action_items: list[dict]) -> list[dict]:
    """
    Generate follow-up recommendations from analysis and action items.

    Per Spec Section 7.3: Generate follow-up items beyond explicit action items,
    including strategic follow-ups based on concerns and enthusiasm signals.

    Args:
        analysis: Structured analysis dict.
        action_items: Extracted action items from transcript.

    Returns:
        List of follow-up dicts with keys: description, priority (high/medium/low),
        source (action_item/concern/enthusiasm/strategic), deadline_hint.
    """
    follow_ups = []

    # Convert explicit action items to follow-ups
    for item in action_items:
        follow_ups.append({
            "description": item["description"],
            "priority": "high" if item.get("deadline") else "medium",
            "source": "action_item",
            "owner": item.get("owner", ""),
            "deadline_hint": item.get("deadline", ""),
        })

    # Generate follow-ups from concerns (Spec 7.3)
    for concern in analysis.get("concerns", []):
        concern_text = concern.get("concern", "")
        speaker = concern.get("speaker", "")
        # Check if concern is already covered by an action item
        already_covered = any(
            concern_text.lower() in item["description"].lower() or
            item["description"].lower() in concern_text.lower()
            for item in action_items
        )
        if not already_covered and concern_text:
            follow_ups.append({
                "description": f"Address {speaker}'s concern: {concern_text}",
                "priority": "high",
                "source": "concern",
                "owner": "",
                "deadline_hint": "soon",
            })

    # Generate follow-ups from enthusiasm signals
    for signal in analysis.get("enthusiasm", []):
        signal_text = signal.get("signal", "")
        speaker = signal.get("speaker", "")
        if signal_text:
            follow_ups.append({
                "description": f"Leverage {speaker}'s enthusiasm about: {signal_text}",
                "priority": "medium",
                "source": "enthusiasm",
                "owner": "",
                "deadline_hint": "",
            })

    return follow_ups


# ---------------------------------------------------------------------------
# Graph updates
# ---------------------------------------------------------------------------

def build_graph_updates(
    meeting_slug: str,
    meeting_date: str,
    analysis: dict,
) -> dict:
    """
    Build graph node/edge updates from transcript analysis.

    Returns dict with node_updates and edge_updates lists.
    """
    node_updates = []
    edge_updates = []

    # Create/update Meeting node
    node_updates.append({
        "label": "Meeting",
        "properties": {
            "slug": meeting_slug,
            "date": meeting_date,
            "topics": ", ".join(analysis.get("topics", [])),
        },
    })

    # Create MET_WITH edges for each speaker
    for speaker in analysis.get("speakers", []):
        speaker_slug = _slugify(speaker)
        speaker_sentiment = analysis.get("sentiment", {}).get(speaker, {})
        # Handle both LLM format (dict) and regex fallback format (dict with 'overall')
        if isinstance(speaker_sentiment, dict):
            sentiment_value = speaker_sentiment.get("overall", "neutral")
        else:
            sentiment_value = str(speaker_sentiment) if speaker_sentiment else "neutral"

        edge_updates.append({
            "source_slug": speaker_slug,
            "source_label": "Person",
            "target_slug": meeting_slug,
            "target_label": "Meeting",
            "type": "MET_WITH",
            "properties": {
                "date": meeting_date,
                "sentiment": sentiment_value,
            },
        })

    # Create DISCUSSED edges for topics
    for topic in analysis.get("topics", []):
        topic_slug = _slugify(topic)
        edge_updates.append({
            "source_slug": meeting_slug,
            "source_label": "Meeting",
            "target_slug": topic_slug,
            "target_label": "Note",
            "type": "DISCUSSED",
            "properties": {"topic": topic},
        })

    # Update person sentiment
    for speaker, sentiment_data in analysis.get("sentiment", {}).items():
        if isinstance(sentiment_data, dict):
            sentiment_value = sentiment_data.get("overall", "neutral")
        else:
            sentiment_value = str(sentiment_data) if sentiment_data else "neutral"

        node_updates.append({
            "label": "Person",
            "properties": {
                "slug": _slugify(speaker),
                "last_contact": meeting_date,
                "last_sentiment": sentiment_value,
            },
        })

    return {
        "node_updates": node_updates,
        "edge_updates": edge_updates,
    }


def diff_against_briefing(briefing_context: dict, analysis: dict) -> dict:
    """
    Diff post-meeting analysis against pre-meeting briefing.

    Identifies: new topics, sentiment changes, new entities, surprises.
    """
    known_topics = set(briefing_context.get("known_topics", []))
    discussed_topics = set(analysis.get("topics", []))
    new_topics = discussed_topics - known_topics

    sentiment_changes = []
    for person_name, sentiment_data in analysis.get("sentiment", {}).items():
        if isinstance(sentiment_data, dict):
            new_sentiment = sentiment_data.get("overall", "unknown")
        else:
            new_sentiment = str(sentiment_data)

        for known in briefing_context.get("known_relationships", []):
            if known.get("slug") == _slugify(person_name):
                old_sentiment = known.get("sentiment", "unknown")
                if old_sentiment != new_sentiment:
                    sentiment_changes.append({
                        "person": person_name,
                        "old": old_sentiment,
                        "new": new_sentiment,
                    })

    return {
        "new_topics": list(new_topics),
        "sentiment_changes": sentiment_changes,
        "new_entities": analysis.get("new_entities", []),
    }


def apply_graph_updates(db, updates: dict, dry_run: bool = False) -> dict:
    """Apply node/edge updates to Neo4j."""
    if dry_run:
        return {
            "nodes_updated": len(updates["node_updates"]),
            "edges_updated": len(updates["edge_updates"]),
            "dry_run": True,
        }

    from .graph_sync import upsert_node, upsert_edge

    nodes_updated = 0
    edges_updated = 0

    for node in updates["node_updates"]:
        try:
            upsert_node(db, node)
            nodes_updated += 1
        except Exception as exc:
            logger.warning("Failed to update node: %s", exc)

    for edge in updates["edge_updates"]:
        try:
            upsert_edge(db, edge)
            edges_updated += 1
        except Exception as exc:
            logger.debug("Failed to update edge: %s", exc)

    return {
        "nodes_updated": nodes_updated,
        "edges_updated": edges_updated,
        "dry_run": False,
    }


# ---------------------------------------------------------------------------
# Full analysis pipeline
# ---------------------------------------------------------------------------

def analyze_meeting(
    db,
    vault_path: str,
    meeting_slug: str,
    transcript: str,
    dry_run: bool = False,
) -> dict:
    """
    Full post-meeting analysis pipeline.

    1. Analyze transcript with LLM (regex fallback)
    2. Extract action items
    3. Score strategic implications against active goals
    4. Generate follow-up recommendations
    5. Build and apply graph updates
    6. Diff against pre-meeting briefing if available

    Args:
        db: GraphDB instance.
        vault_path: Path to the vault.
        meeting_slug: Meeting identifier slug.
        transcript: Full transcript text.
        dry_run: If True, don't write to DB.

    Returns:
        Comprehensive analysis result dict.
    """
    meeting_date = meeting_slug[:10] if len(meeting_slug) >= 10 else datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Step 1: LLM analysis (with regex fallback)
    analysis = analyze_transcript_with_llm(transcript)

    # Step 2: Action item extraction (always regex — reliable for structured items)
    action_items = extract_action_items(transcript)
    analysis["action_items"] = action_items

    # Step 3: Strategic goal scoring (Spec 7.3 item 5)
    strategic_scores = score_strategic_implications(analysis, db)

    # Step 4: Follow-up generation
    follow_ups = generate_follow_ups(analysis, action_items)

    # Step 5: Graph updates
    updates = build_graph_updates(meeting_slug, meeting_date, analysis)
    update_result = apply_graph_updates(db, updates, dry_run=dry_run)

    return {
        "meeting_slug": meeting_slug,
        "analysis": analysis,
        "action_items": action_items,
        "strategic_scores": strategic_scores,
        "follow_ups": follow_ups,
        "graph_updates": update_result,
        "dry_run": dry_run,
    }
