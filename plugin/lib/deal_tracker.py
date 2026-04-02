"""
Deal & relationship lifecycle tracker for Engram.

Tracks every relationship through stages:
  cold -> warm-intro -> first-meeting -> active-conversation ->
  due-diligence -> committed -> closed

Auto-advances stages based on meeting frequency and content signals.
Detects stale deals and overdue follow-ups.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger("deal_tracker")


# ---------------------------------------------------------------------------
# Lifecycle stages
# ---------------------------------------------------------------------------

LIFECYCLE_STAGES = [
    "cold",
    "warm-intro",
    "first-meeting",
    "active-conversation",
    "due-diligence",
    "committed",
    "closed",
]

# Days before a relationship is considered stale, per stage
STALENESS_THRESHOLDS = {
    "warm-intro": 21,
    "first-meeting": 30,
    "active-conversation": 30,
    "due-diligence": 14,
    "committed": 30,
}

# Minimum meetings to advance to the next stage
ADVANCE_CRITERIA = {
    "warm-intro": {"min_meetings": 1, "next": "first-meeting"},
    "first-meeting": {"min_meetings": 2, "next": "active-conversation"},
    "active-conversation": {"min_meetings": 4, "next": "due-diligence"},
}


def stage_index(stage: str) -> int:
    """Return the ordinal index of a lifecycle stage."""
    try:
        return LIFECYCLE_STAGES.index(stage)
    except ValueError:
        return -1


def can_advance(current: str, target: str) -> bool:
    """Check if advancing from current to target is a valid single-step transition."""
    ci = stage_index(current)
    ti = stage_index(target)
    return ti == ci + 1


# ---------------------------------------------------------------------------
# Stage evaluation
# ---------------------------------------------------------------------------

def evaluate_stage_transitions(db) -> list[dict]:
    """
    Evaluate all relationships for potential stage advancement.

    Queries the graph for meeting counts and determines which relationships
    should advance to the next stage. Uses can_advance() as a guard to ensure
    only valid single-step transitions are proposed.
    """
    transitions = []

    for current_stage, criteria in ADVANCE_CRITERIA.items():
        min_meetings = criteria["min_meetings"]
        next_stage = criteria["next"]

        # Guard: skip if the transition is not a valid single-step advance
        if not can_advance(current_stage, next_stage):
            logger.warning("Invalid advance criteria: %s -> %s", current_stage, next_stage)
            continue

        results = db.execute_read_only("""
            MATCH (p:Person {relationship_stage: $stage})
            OPTIONAL MATCH (p)-[:MET_WITH]-(m:Meeting)
            WITH p, count(DISTINCT m) AS meeting_count
            WHERE meeting_count >= $min_meetings
            RETURN p.slug AS slug, p.name AS name,
                   p.relationship_stage AS current_stage,
                   meeting_count
        """, {"stage": current_stage, "min_meetings": min_meetings})

        for record in results:
            transitions.append({
                "slug": record["slug"],
                "name": record["name"],
                "current_stage": current_stage,
                "new_stage": next_stage,
                "meeting_count": record["meeting_count"],
                "reason": f"{record['meeting_count']} meetings (threshold: {min_meetings})",
            })

    return transitions


def apply_stage_transitions(db, transitions: list[dict], dry_run: bool = False) -> dict:
    """Apply stage transitions to the graph."""
    if dry_run:
        return {"transitions": len(transitions), "dry_run": True}

    applied = 0
    for t in transitions:
        try:
            db.execute_write("""
                MATCH (p:Person {slug: $slug})
                SET p.relationship_stage = $new_stage,
                    p.stage_changed = datetime()
            """, {"slug": t["slug"], "new_stage": t["new_stage"]})
            applied += 1
            logger.info("Stage advance: %s %s -> %s", t["name"], t["current_stage"], t["new_stage"])
        except Exception as exc:
            logger.warning("Failed to advance %s: %s", t["slug"], exc)

    return {"transitions": applied, "dry_run": False}


# ---------------------------------------------------------------------------
# Staleness detection
# ---------------------------------------------------------------------------

def detect_stale_deals(db) -> list[dict]:
    """Find relationships that have gone stale (no contact beyond threshold)."""
    stale = []

    for stage, threshold_days in STALENESS_THRESHOLDS.items():
        results = db.execute_read_only("""
            MATCH (p:Person {relationship_stage: $stage})
            WHERE p.last_contact IS NOT NULL
              AND date(p.last_contact) < date() - duration({days: $days})
            RETURN p.slug AS slug, p.name AS name,
                   p.last_contact AS last_contact,
                   p.relationship_stage AS stage
        """, {"stage": stage, "days": threshold_days})

        for record in results:
            stale.append({
                "slug": record["slug"],
                "name": record["name"],
                "stage": record["stage"],
                "last_contact": record["last_contact"],
                "days_threshold": threshold_days,
                "reason": f"No contact in {threshold_days}+ days at {stage} stage",
            })

    return stale


# ---------------------------------------------------------------------------
# Commitment tracking
# ---------------------------------------------------------------------------

def find_overdue_actions(db) -> list[dict]:
    """Find people with overdue next_action dates."""
    results = db.execute_read_only("""
        MATCH (p:Person)
        WHERE p.next_action IS NOT NULL
          AND p.next_action_date IS NOT NULL
          AND date(p.next_action_date) < date()
        RETURN p.slug AS slug, p.name AS name,
               p.next_action AS action, p.next_action_date AS due_date
        ORDER BY p.next_action_date
    """)
    return [dict(r) for r in results]


# ---------------------------------------------------------------------------
# Pipeline view
# ---------------------------------------------------------------------------

def get_pipeline(db) -> dict:
    """Get the full deal pipeline grouped by stage."""
    pipeline = {}

    for stage in LIFECYCLE_STAGES:
        results = db.execute_read_only("""
            MATCH (p:Person {relationship_stage: $stage})
            OPTIONAL MATCH (p)-[:MET_WITH]-(m:Meeting)
            WITH p, count(DISTINCT m) AS meetings
            RETURN p.slug AS slug, p.name AS name, p.org AS org,
                   p.last_contact AS last_contact, meetings
            ORDER BY p.last_contact DESC
        """, {"stage": stage})

        pipeline[stage] = [dict(r) for r in results]

    return pipeline


# ---------------------------------------------------------------------------
# Full deal tracking cycle
# ---------------------------------------------------------------------------

def run_deal_tracking(db, dry_run: bool = False) -> dict:
    """Run the full deal tracking cycle."""
    transitions = evaluate_stage_transitions(db)
    apply_result = apply_stage_transitions(db, transitions, dry_run=dry_run)

    stale = detect_stale_deals(db)
    overdue = find_overdue_actions(db)

    logger.info(
        "Deal tracking: %d transitions, %d stale, %d overdue",
        len(transitions), len(stale), len(overdue),
    )

    return {
        "transitions": transitions,
        "applied": apply_result,
        "stale_deals": stale,
        "overdue_actions": overdue,
    }
