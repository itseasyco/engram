"""
Cross-reference intelligence engine for Engram.

Detects hidden connections and patterns across the relationship graph:

  SHARED_PORTFOLIO  — "2 of our clients are A16Z portfolio companies"
  WARM_INTRO_PATH   — "Person A → Person B → Target VC"
  RESONATING_TOPIC  — "5 investors asked about compliance this quarter"
  STALE_RELATIONSHIP — "Haven't met Person X in 90d, connected to active goal"
  CONVERGING_SIGNAL  — "3 meetings this month mentioned stablecoin settlement"

Output: _metadata/intelligence-report.md
"""

import json
import logging
import os
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from .consolidation import _parse_frontmatter
from .entity_extractor import _slugify
from .relationship_graph import load_index, traverse, find_paths

logger = logging.getLogger("cross_reference")


# ---------------------------------------------------------------------------
# Pattern detectors
# ---------------------------------------------------------------------------

def detect_shared_portfolio(index: dict) -> list[dict]:
    """
    Find entities that share a portfolio/investor relationship.

    Example: "Finix and Alloy are both A16Z portfolio companies, and both are our clients."
    """
    findings = []
    entities = index.get("entities", {})

    # Build org -> portfolio companies mapping
    portfolio_map = defaultdict(set)  # org_slug -> set of portfolio company slugs
    for slug, entity in entities.items():
        for edge in entity.get("edges", []):
            if edge["type"] == "portfolio-company-of":
                portfolio_map[edge["target"]].add(slug)
            elif edge["type"] == "has-portfolio-company":
                portfolio_map[slug].add(edge["target"])

    # Find orgs where we have multiple connections
    for org_slug, companies in portfolio_map.items():
        if len(companies) < 2:
            continue

        org_name = entities.get(org_slug, {}).get("name", org_slug)

        # Check which of these companies we have relationships with
        our_relationships = []
        for company_slug in companies:
            company_data = entities.get(company_slug, {})
            company_name = company_data.get("name", company_slug)
            for edge in company_data.get("edges", []):
                if edge["type"] in ("client-of", "partner-of"):
                    our_relationships.append({
                        "company": company_name,
                        "relationship": edge["type"],
                    })

        if len(our_relationships) >= 2:
            findings.append({
                "pattern": "SHARED_PORTFOLIO",
                "org": org_name,
                "connections": our_relationships,
                "insight": (
                    f"{len(our_relationships)} of our relationships "
                    f"({', '.join(r['company'] for r in our_relationships)}) "
                    f"are {org_name} portfolio companies. "
                    f"This is leverage for investor conversations with {org_name}."
                ),
                "priority": "high",
            })

    return findings


def detect_warm_intro_paths(
    index: dict,
    target_entities: Optional[list[str]] = None,
    vault_path: str = "",
) -> list[dict]:
    """
    Find warm introduction paths to target entities.

    If target_entities is None, finds paths to all entities we haven't met directly.
    """
    findings = []
    entities = index.get("entities", {})

    # Find entities we've met (direct met-with edges from our team)
    from .entity_profiles import _TEAM_MEMBERS
    team_slugs = {_slugify(name) for name in _TEAM_MEMBERS}

    directly_met = set()
    for slug in team_slugs:
        entity = entities.get(slug, {})
        for edge in entity.get("edges", []):
            if edge["type"] == "met-with":
                directly_met.add(edge["target"])

    # Determine targets
    if target_entities:
        targets = [_slugify(t) for t in target_entities]
    else:
        # Find entities 2-3 hops away that we haven't directly met
        targets = []
        for slug in entities:
            if slug not in team_slugs and slug not in directly_met:
                targets.append(slug)

    for target_slug in targets[:20]:  # Limit to avoid explosion
        target_name = entities.get(target_slug, {}).get("name", target_slug)

        # Find paths from any team member to target
        for team_slug in team_slugs:
            team_name = entities.get(team_slug, {}).get("name", team_slug)
            paths = find_paths(team_name, target_name, vault_path, max_hops=3)

            for path in paths[:3]:  # Top 3 paths per target
                if len(path) <= 2:
                    continue  # Direct connection, not an intro

                intermediaries = [step["entity_name"] for step in path[1:-1]]
                findings.append({
                    "pattern": "WARM_INTRO_PATH",
                    "from": team_name,
                    "to": target_name,
                    "via": intermediaries,
                    "hops": len(path) - 1,
                    "path_detail": [
                        {"name": step["entity_name"], "via": step["via_type"]}
                        for step in path
                    ],
                    "insight": (
                        f"Warm intro to {target_name} via "
                        f"{' → '.join(intermediaries)} "
                        f"({len(path) - 1} hops from {team_name})"
                    ),
                    "priority": "medium" if len(path) <= 3 else "low",
                })

    return findings


def detect_resonating_topics(vault_path: str, lookback_days: int = 60) -> list[dict]:
    """
    Find topics that multiple people have mentioned across meetings.

    Example: "5 investors asked about compliance in the last 60 days."
    """
    findings = []
    vault = Path(vault_path)
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)

    # Scan meetings for topic mentions
    topic_mentions = defaultdict(list)  # topic -> [{meeting, date, person}]
    meetings_dir = vault / "meetings"

    if not meetings_dir.exists():
        return findings

    for md_file in meetings_dir.rglob("*.md"):
        if md_file.name == "index.md":
            continue

        try:
            content = md_file.read_text(encoding="utf-8")
        except (IOError, UnicodeDecodeError):
            continue

        fm = _parse_frontmatter(content)
        created = fm.get("created", "")
        if created:
            try:
                note_date = datetime.fromisoformat(created.replace("Z", "+00:00"))
                if note_date.tzinfo is None:
                    note_date = note_date.replace(tzinfo=timezone.utc)
                if note_date < cutoff:
                    continue
            except (ValueError, TypeError):
                pass

        # Extract wikilinked topics
        wikilinks = re.findall(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", content)
        attendees = fm.get("attendees", "")
        meeting_title = fm.get("title", md_file.stem)

        for topic in wikilinks:
            topic_mentions[topic].append({
                "meeting": meeting_title,
                "date": created,
                "file": str(md_file.relative_to(vault)),
            })

    # Find topics mentioned in 3+ meetings
    for topic, mentions in topic_mentions.items():
        if len(mentions) >= 3:
            findings.append({
                "pattern": "RESONATING_TOPIC",
                "topic": topic,
                "mention_count": len(mentions),
                "meetings": mentions[:10],
                "insight": (
                    f"[[{topic}]] mentioned in {len(mentions)} meetings "
                    f"over the last {lookback_days} days. "
                    f"This may warrant strategic attention."
                ),
                "priority": "high" if len(mentions) >= 5 else "medium",
            })

    # Sort by mention count descending
    findings.sort(key=lambda f: f["mention_count"], reverse=True)
    return findings


def detect_stale_relationships(
    index: dict,
    vault_path: str,
    stale_days: int = 90,
) -> list[dict]:
    """
    Find relationships that have gone cold but are connected to active goals.
    """
    findings = []
    entities = index.get("entities", {})
    vault = Path(vault_path)
    cutoff = datetime.now(timezone.utc) - timedelta(days=stale_days)

    # Load active goals
    goals = _load_active_goals(vault)
    goal_keywords = set()
    for goal in goals:
        goal_keywords.update(goal.get("keywords", []))

    for slug, entity in entities.items():
        if entity.get("type") != "person":
            continue

        # Check last meeting date
        profile_path = _find_entity_profile(slug, vault)
        if not profile_path:
            continue

        try:
            content = profile_path.read_text(encoding="utf-8")
        except (IOError, UnicodeDecodeError):
            continue

        fm = _parse_frontmatter(content)
        last_contact = fm.get("last_contact", fm.get("updated", ""))

        if not last_contact:
            continue

        try:
            contact_date = datetime.fromisoformat(last_contact.replace("Z", "+00:00"))
            if contact_date.tzinfo is None:
                contact_date = contact_date.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue

        if contact_date >= cutoff:
            continue  # Not stale

        # Check if connected to active goals
        entity_topics = set()
        for edge in entity.get("edges", []):
            entity_topics.add(edge["target"])
            entity_topics.add(edge.get("context", "").lower())

        relevant_goals = [
            g for g in goals
            if any(kw in str(entity_topics).lower() for kw in g.get("keywords", []))
        ]

        if relevant_goals:
            days_since = (datetime.now(timezone.utc) - contact_date).days
            entity_name = entity.get("name", slug)
            findings.append({
                "pattern": "STALE_RELATIONSHIP",
                "entity": entity_name,
                "days_since_contact": days_since,
                "related_goals": [g["title"] for g in relevant_goals],
                "insight": (
                    f"Haven't contacted [[{slug}|{entity_name}]] in {days_since} days, "
                    f"but they're connected to goals: "
                    f"{', '.join(g['title'] for g in relevant_goals[:3])}. "
                    f"Consider re-engagement."
                ),
                "priority": "high" if days_since > 120 else "medium",
            })

    return findings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_active_goals(vault: Path) -> list[dict]:
    """Load active goals from strategy/goals/."""
    goals = []
    goals_dir = vault / "strategy" / "goals"
    if not goals_dir.exists():
        return goals

    for md_file in goals_dir.glob("*.md"):
        try:
            content = md_file.read_text(encoding="utf-8")
            fm = _parse_frontmatter(content)
            if fm.get("status", "active") == "active":
                # Extract keywords from title and tags
                title = fm.get("title", md_file.stem)
                tags = fm.get("tags", [])
                if isinstance(tags, str):
                    tags = [t.strip() for t in tags.split(",")]
                keywords = [w.lower() for w in title.split()] + [t.lower() for t in tags]
                goals.append({
                    "title": title,
                    "keywords": keywords,
                    "file": str(md_file.name),
                })
        except (IOError, UnicodeDecodeError):
            continue

    return goals


def _find_entity_profile(slug: str, vault: Path) -> Optional[Path]:
    """Find an entity's profile by slug."""
    for search_dir in [vault / "people", vault / "organizations"]:
        if search_dir.exists():
            for candidate in search_dir.rglob(f"{slug}.md"):
                return candidate
    return None


# ---------------------------------------------------------------------------
# Intelligence report generation
# ---------------------------------------------------------------------------

def generate_intelligence_report(
    vault_path: str,
    dry_run: bool = True,
) -> dict:
    """
    Run all cross-reference detectors and generate intelligence report.

    Output: _metadata/intelligence-report.md

    Returns:
        dict with findings counts and report path.
    """
    index = load_index(vault_path)
    vault = Path(vault_path)

    all_findings = []

    # Run detectors
    portfolio = detect_shared_portfolio(index)
    all_findings.extend(portfolio)

    intros = detect_warm_intro_paths(index, vault_path=vault_path)
    all_findings.extend(intros)

    topics = detect_resonating_topics(vault_path)
    all_findings.extend(topics)

    stale = detect_stale_relationships(index, vault_path)
    all_findings.extend(stale)

    # Sort by priority
    priority_order = {"high": 0, "medium": 1, "low": 2}
    all_findings.sort(key=lambda f: priority_order.get(f.get("priority", "low"), 3))

    results = {
        "total_findings": len(all_findings),
        "by_pattern": {
            "SHARED_PORTFOLIO": len(portfolio),
            "WARM_INTRO_PATH": len(intros),
            "RESONATING_TOPIC": len(topics),
            "STALE_RELATIONSHIP": len(stale),
        },
        "high_priority": sum(1 for f in all_findings if f.get("priority") == "high"),
        "dry_run": dry_run,
    }

    if not dry_run:
        report_path = _write_report(vault, all_findings)
        results["report_path"] = str(report_path)

    return results


def _write_report(vault: Path, findings: list[dict]) -> Path:
    """Write the intelligence report to _metadata/."""
    report_dir = vault / "_metadata"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "intelligence-report.md"

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    high_count = sum(1 for f in findings if f.get("priority") == "high")

    lines = [
        "---",
        f'title: "Intelligence Report"',
        f'generated: "{now}"',
        f'total_findings: {len(findings)}',
        f'high_priority: {high_count}',
        'type: "intelligence-report"',
        "---",
        "",
        "# Intelligence Report",
        "",
        f"Generated: {now}",
        f"Total findings: {len(findings)} ({high_count} high priority)",
        "",
    ]

    # Group by pattern
    by_pattern = defaultdict(list)
    for finding in findings:
        by_pattern[finding["pattern"]].append(finding)

    pattern_labels = {
        "SHARED_PORTFOLIO": "Shared Portfolio Leverage",
        "WARM_INTRO_PATH": "Warm Introduction Paths",
        "RESONATING_TOPIC": "Resonating Topics",
        "STALE_RELATIONSHIP": "Stale Relationships",
    }

    for pattern, label in pattern_labels.items():
        group = by_pattern.get(pattern, [])
        if not group:
            continue

        lines.append(f"## {label} ({len(group)})")
        lines.append("")

        for finding in group:
            priority_marker = ""
            if finding.get("priority") == "high":
                priority_marker = " [HIGH]"

            lines.append(f"### {finding.get('insight', 'Finding')}{priority_marker}")
            lines.append("")

            # Add details based on pattern type
            if pattern == "WARM_INTRO_PATH" and "path_detail" in finding:
                path_str = " → ".join(
                    f"[[{step['name']}]]" if step["via_type"] else step["name"]
                    for step in finding["path_detail"]
                )
                lines.append(f"Path: {path_str}")
                lines.append("")
            elif pattern == "RESONATING_TOPIC" and "meetings" in finding:
                for m in finding["meetings"][:5]:
                    lines.append(f"- {m.get('date', '?')}: {m.get('meeting', '?')}")
                lines.append("")
            elif pattern == "SHARED_PORTFOLIO" and "connections" in finding:
                for conn in finding["connections"]:
                    lines.append(f"- [[{_slugify(conn['company'])}|{conn['company']}]] ({conn['relationship']})")
                lines.append("")

        lines.append("---")
        lines.append("")

    report_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Intelligence report written: %d findings", len(findings))
    return report_path
