"""
Opportunity scorer for Engram.

Scores relationships/deals by strategic value using graph-native operations.

Scoring dimensions (separate from the general intelligence rubric in Section 4.3):
  - Goal alignment (40%) — path proximity to active goals
  - Connection strength (25%) — recency, frequency, sentiment
  - Network value (20%) — graph centrality (who else they connect us to)
  - Timing signals (15%) — proximity to deadlines, meetings, events
"""

import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger("opportunity_scorer")


def score_goal_alignment(db, person_slug: str) -> float:
    """
    Score how directly this person connects to active goals.

    40% weight. Range: 0.0 - 1.0.
    Direct connection = 1.0, 2-hop = 0.6, 3-hop = 0.3, none = 0.0.
    Priority multiplier: critical = 1.0, high = 0.8, medium = 0.5.
    """
    results = db.execute_read_only("""
        MATCH path = (p:Person {slug: $slug})-[*1..3]-(g:Goal {status: 'active'})
        RETURN g.name AS goal, g.priority AS priority, length(path) AS hops
        ORDER BY hops ASC
    """, {"slug": person_slug})

    if not results:
        return 0.0

    best_score = 0.0
    for r in results:
        hops = r["hops"]
        priority = r.get("priority", "medium")

        # Distance score
        if hops == 1:
            distance_score = 1.0
        elif hops == 2:
            distance_score = 0.6
        else:
            distance_score = 0.3

        # Priority multiplier
        priority_mult = {"critical": 1.0, "high": 0.8, "medium": 0.5, "low": 0.2}.get(priority, 0.5)

        score = distance_score * priority_mult
        best_score = max(best_score, score)

    return best_score


def _sentiment_to_numeric(sentiment: str) -> float:
    """Convert sentiment label to numeric value for trend calculation."""
    return {
        "very positive": 1.0, "positive": 0.75, "neutral": 0.5,
        "negative": 0.25, "very negative": 0.0,
    }.get(sentiment, 0.5)


def _compute_sentiment_trajectory(sentiments: list[str]) -> str:
    """
    Compute sentiment direction from last 2-3 meetings.

    Returns: "improving", "declining", or "stable".
    """
    if len(sentiments) < 2:
        return "stable"

    values = [_sentiment_to_numeric(s) for s in sentiments[-3:]]  # last 3 max
    delta = values[-1] - values[0]
    if delta > 0.15:
        return "improving"
    elif delta < -0.15:
        return "declining"
    return "stable"


def score_connection_strength(db, person_slug: str) -> float:
    """
    Score relationship strength based on recency, frequency, sentiment,
    and sentiment trajectory (improving/declining/stable).

    25% weight. Range: 0.0 - 1.0.
    """
    results = db.execute_read_only("""
        MATCH (p:Person {slug: $slug})
        OPTIONAL MATCH (p)-[:MET_WITH]-(m:Meeting)
        WITH p, count(DISTINCT m) AS meeting_count,
             p.last_contact AS last_contact,
             p.last_sentiment AS sentiment
        RETURN meeting_count, last_contact, sentiment
    """, {"slug": person_slug})

    if not results:
        return 0.0

    r = results[0]
    meeting_count = r.get("meeting_count", 0)
    last_contact = r.get("last_contact", "")
    sentiment = r.get("sentiment", "neutral")

    # Query recent meeting sentiments for trajectory detection
    trajectory_results = db.execute_read_only("""
        MATCH (p:Person {slug: $slug})-[:MET_WITH]-(m:Meeting)
        WHERE m.sentiment IS NOT NULL
        RETURN m.sentiment AS sentiment, m.date AS date
        ORDER BY m.date ASC
    """, {"slug": person_slug})

    recent_sentiments = [tr["sentiment"] for tr in (trajectory_results or [])]
    trajectory = _compute_sentiment_trajectory(recent_sentiments)

    # Frequency score (0-5 meetings = 0-0.35, 5+ = 0.35)
    freq_score = min(0.35, meeting_count * 0.07)

    # Recency score
    recency_score = 0.0
    if last_contact:
        try:
            last = datetime.fromisoformat(str(last_contact).replace("Z", "+00:00"))
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            days_ago = (datetime.now(timezone.utc) - last).days
            recency_score = max(0, 0.35 - (days_ago * 0.009))  # Decays over ~39 days
        except (ValueError, TypeError):
            pass

    # Sentiment snapshot score
    sentiment_scores = {
        "very positive": 0.15, "positive": 0.1, "neutral": 0.05,
        "negative": 0.0, "very negative": 0.0,
    }
    sent_score = sentiment_scores.get(sentiment, 0.05)

    # Sentiment trajectory bonus/penalty
    trajectory_adj = {"improving": 0.15, "stable": 0.0, "declining": -0.1}.get(trajectory, 0.0)

    return max(0.0, min(1.0, freq_score + recency_score + sent_score + trajectory_adj))


def score_network_value(db, person_slug: str) -> float:
    """
    Score network value — who else does this person connect us to?

    20% weight. Range: 0.0 - 1.0.

    Uses a 2-hop weighted centrality approximation: counts direct connections
    weighted by THEIR connection count. This approximates betweenness centrality
    without requiring Neo4j GDS (Graph Data Science) library.

    NOTE: When Neo4j GDS is available, upgrade this to use true PageRank or
    betweenness centrality via:
        CALL gds.pageRank.stream('person-graph') YIELD nodeId, score
    """
    results = db.execute_read_only("""
        MATCH (p:Person {slug: $slug})-[r]-(neighbor)
        OPTIONAL MATCH (neighbor)-[r2]-(second_hop)
        WHERE second_hop <> p
        WITH p,
             count(DISTINCT neighbor) AS direct_connections,
             count(DISTINCT second_hop) AS second_hop_reach
        RETURN direct_connections, second_hop_reach
    """, {"slug": person_slug})

    if not results:
        return 0.0

    direct = results[0].get("direct_connections", 0)
    reach = results[0].get("second_hop_reach", 0)

    # Weighted score: direct connections + discounted 2nd-hop reach
    weighted_score = direct + (reach * 0.3)

    # Normalize against the best-connected person in the graph
    max_results = db.execute_read_only("""
        MATCH (p:Person)-[r]-(neighbor)
        OPTIONAL MATCH (neighbor)-[r2]-(second_hop)
        WHERE second_hop <> p
        WITH p,
             count(DISTINCT neighbor) AS d,
             count(DISTINCT second_hop) AS s
        WITH d + (s * 0.3) AS weighted
        RETURN max(weighted) AS max_weighted
    """)

    max_weighted = max_results[0].get("max_weighted", 1) if max_results else 1
    if not max_weighted or max_weighted == 0:
        max_weighted = 1

    return min(1.0, weighted_score / max_weighted)


def score_timing_signals(db, person_slug: str) -> float:
    """
    Score timing urgency — upcoming meetings, approaching deadlines.

    15% weight. Range: 0.0 - 1.0.
    """
    # Check for upcoming meetings
    meeting_results = db.execute_read_only("""
        MATCH (p:Person {slug: $slug})-[:MET_WITH]-(m:Meeting)
        WHERE m.date >= date()
        RETURN count(m) AS upcoming
    """, {"slug": person_slug})

    upcoming = meeting_results[0].get("upcoming", 0) if meeting_results else 0

    # Check for approaching goal deadlines
    deadline_results = db.execute_read_only("""
        MATCH (p:Person {slug: $slug})-[*1..2]-(g:Goal {status: 'active'})
        WHERE g.target_close IS NOT NULL
        RETURN g.target_close AS deadline
    """, {"slug": person_slug})

    timing_score = 0.0

    # Upcoming meeting boost
    if upcoming > 0:
        timing_score += 0.5

    # Deadline proximity boost
    now = datetime.now(timezone.utc)
    for r in (deadline_results or []):
        deadline_raw = r.get("deadline", "")
        if not deadline_raw:
            continue
        try:
            deadline_dt = datetime.fromisoformat(str(deadline_raw).replace("Z", "+00:00"))
            if deadline_dt.tzinfo is None:
                deadline_dt = deadline_dt.replace(tzinfo=timezone.utc)
            days_until = (deadline_dt - now).days
            if days_until < 0:
                timing_score += 0.5
            elif days_until <= 14:
                timing_score += 0.4
            elif days_until <= 30:
                timing_score += 0.25
            elif days_until <= 90:
                timing_score += 0.1
            break  # Use the nearest deadline only
        except (ValueError, TypeError):
            continue

    return min(1.0, timing_score)


def score_opportunity(db, person_slug: str) -> dict:
    """
    Compute composite opportunity score.

    Weights: Goal alignment 40%, Connection strength 25%,
    Network value 20%, Timing signals 15%.
    """
    ga = score_goal_alignment(db, person_slug)
    cs = score_connection_strength(db, person_slug)
    nv = score_network_value(db, person_slug)
    ts = score_timing_signals(db, person_slug)

    total = (ga * 40) + (cs * 25) + (nv * 20) + (ts * 15)

    return {
        "slug": person_slug,
        "goal_alignment": round(ga * 40, 1),
        "connection_strength": round(cs * 25, 1),
        "network_value": round(nv * 20, 1),
        "timing_signals": round(ts * 15, 1),
        "total": round(total, 1),
    }


def score_all_active_relationships(db) -> list[dict]:
    """Score all non-cold, non-closed relationships and rank them."""
    results = db.execute_read_only("""
        MATCH (p:Person)
        WHERE p.relationship_stage IS NOT NULL
          AND p.relationship_stage <> 'cold'
          AND p.relationship_stage <> 'closed'
        RETURN p.slug AS slug
    """)

    scores = []
    for r in results:
        score = score_opportunity(db, r["slug"])
        scores.append(score)

    return sorted(scores, key=lambda s: s["total"], reverse=True)
