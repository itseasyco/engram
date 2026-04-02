"""
Pre-meeting briefing generator for Engram.

Gathers attendee context from the knowledge graph, optionally enriches
with web search results, generates AI-powered talking points, and writes
a formatted briefing document to the vault.

Usage:
    from lib.meeting_briefing import generate_briefing
    from lib.graph_db import get_graph_db

    db = get_graph_db()
    result = generate_briefing(db, "/path/to/vault", meeting_dict)
"""

import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger("meeting_briefing")


# ---------------------------------------------------------------------------
# Web search (stub)
# ---------------------------------------------------------------------------

def _call_web_search(query: str, max_results: int = 5) -> list[dict]:
    """Call external web search API. Returns [] if not configured.

    Each result is a dict with keys: title, url, snippet.
    """
    api_key = os.environ.get("ENGRAM_WEB_SEARCH_API_KEY")
    if not api_key:
        logger.debug("ENGRAM_WEB_SEARCH_API_KEY not set, skipping web search")
        return []

    # Stub — actual implementation would call a search API (e.g., Brave, SerpAPI)
    logger.info("Web search stub called for: %s", query)
    return []


def search_web_context(person_name: str, org_name: str = "") -> list[dict]:
    """Search the web for recent context about a person/org.

    Deduplicates results by URL. Returns [] on any failure.
    """
    try:
        results = []
        seen_urls = set()

        # Search for the person
        person_results = _call_web_search(f"{person_name} latest news")
        for r in person_results:
            url = r.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                results.append(r)

        # Search person + org if org is provided
        if org_name:
            org_results = _call_web_search(f"{person_name} {org_name}")
            for r in org_results:
                url = r.get("url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    results.append(r)

        return results
    except Exception as exc:
        logger.warning("Web search failed for %s: %s", person_name, exc)
        return []


# ---------------------------------------------------------------------------
# Claude API (talking points)
# ---------------------------------------------------------------------------

def _call_claude_api(prompt: str, max_tokens: int = 1024) -> str:
    """Call Claude API to generate text. Raises on failure."""
    import anthropic

    client = anthropic.Anthropic()
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


def generate_talking_points(
    attendee_contexts: list[dict],
    meeting_title: str,
) -> list[str]:
    """Generate talking points from attendee contexts using Claude.

    Builds a context summary, sends to Claude, and parses numbered response
    lines. Returns [] on failure.
    """
    try:
        # Build context summary
        parts = [f"Meeting: {meeting_title}\n"]
        for ctx in attendee_contexts:
            person = ctx.get("person") or {}
            name = person.get("name", "Unknown")
            parts.append(f"## {name}")
            orgs = ctx.get("organizations", [])
            if orgs:
                org_names = [o.get("name", "") for o in orgs]
                parts.append(f"Organizations: {', '.join(org_names)}")
            goals = ctx.get("relevant_goals", [])
            if goals:
                goal_titles = [g.get("title", "") for g in goals]
                parts.append(f"Active goals: {', '.join(goal_titles)}")
            meetings = ctx.get("past_meetings", [])
            if meetings:
                parts.append(f"Past meetings: {len(meetings)}")
            parts.append("")

        context_summary = "\n".join(parts)

        prompt = (
            f"Based on the following meeting context, generate 5-7 concise "
            f"talking points as a numbered list. Each point should be actionable "
            f"and specific.\n\n{context_summary}"
        )

        raw = _call_claude_api(prompt)

        # Parse numbered lines: "1. ...", "2. ...", etc.
        points = []
        for line in raw.strip().split("\n"):
            line = line.strip()
            match = re.match(r"^\d+[\.\)]\s*(.+)$", line)
            if match:
                points.append(match.group(1).strip())

        return points
    except Exception as exc:
        logger.warning("Failed to generate talking points: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Graph context gathering
# ---------------------------------------------------------------------------

def gather_attendee_context(db, person_slug: str) -> dict:
    """Gather full context for a meeting attendee from Neo4j.

    Queries for:
    - Person node by slug
    - Organizations via WORKS_AT/ADVISES/FOUNDED edges
    - Past meetings via MET_WITH or ATTENDED edges (both directions)
    - Goals within 3 hops with status='active'
    - Network: 2-hop person connections
    - Web search results

    Returns dict with: person, organizations, past_meetings, relevant_goals,
    network, web_context, is_new.
    """
    context = {
        "person": None,
        "organizations": [],
        "past_meetings": [],
        "relevant_goals": [],
        "network": [],
        "web_context": [],
        "is_new": True,
    }

    if not db or not db.is_available():
        return context

    # Person node
    person_results = db.execute(
        "MATCH (p:Person {slug: $slug}) RETURN p",
        params={"slug": person_slug},
        fallback=[],
    )
    if not person_results:
        return context

    person_record = person_results[0]
    person_node = person_record.get("p")
    if person_node is None:
        return context

    # Extract person properties
    if hasattr(person_node, "items"):
        person_data = dict(person_node.items())
    elif isinstance(person_node, dict):
        person_data = person_node
    else:
        person_data = {"slug": person_slug}

    context["person"] = person_data
    context["is_new"] = False

    person_name = person_data.get("name", "")

    # Organizations
    org_results = db.execute(
        "MATCH (p:Person {slug: $slug})-[:WORKS_AT|ADVISES|FOUNDED]->(o:Organization) "
        "RETURN o",
        params={"slug": person_slug},
        fallback=[],
    )
    for rec in (org_results or []):
        o = rec.get("o")
        if o is not None:
            if hasattr(o, "items"):
                context["organizations"].append(dict(o.items()))
            elif isinstance(o, dict):
                context["organizations"].append(o)

    # Past meetings — match both MET_WITH and ATTENDED in any direction
    meeting_results = db.execute(
        "MATCH (p:Person {slug: $slug})-[:MET_WITH|ATTENDED]-(m:Meeting) "
        "RETURN m ORDER BY m.date DESC LIMIT 10",
        params={"slug": person_slug},
        fallback=[],
    )
    for rec in (meeting_results or []):
        m = rec.get("m")
        if m is not None:
            if hasattr(m, "items"):
                context["past_meetings"].append(dict(m.items()))
            elif isinstance(m, dict):
                context["past_meetings"].append(m)

    # Active goals within 3 hops
    goal_results = db.execute(
        "MATCH (p:Person {slug: $slug})-[*1..3]-(g:Goal {status: 'active'}) "
        "RETURN DISTINCT g",
        params={"slug": person_slug},
        fallback=[],
    )
    for rec in (goal_results or []):
        g = rec.get("g")
        if g is not None:
            if hasattr(g, "items"):
                context["relevant_goals"].append(dict(g.items()))
            elif isinstance(g, dict):
                context["relevant_goals"].append(g)

    # 2-hop network
    network_results = db.execute(
        "MATCH (p:Person {slug: $slug})-[*1..2]-(other:Person) "
        "WHERE other.slug <> $slug "
        "RETURN DISTINCT other LIMIT 20",
        params={"slug": person_slug},
        fallback=[],
    )
    for rec in (network_results or []):
        other = rec.get("other")
        if other is not None:
            if hasattr(other, "items"):
                context["network"].append(dict(other.items()))
            elif isinstance(other, dict):
                context["network"].append(other)

    # Web search enrichment
    org_name = ""
    if context["organizations"]:
        org_name = context["organizations"][0].get("name", "")
    context["web_context"] = search_web_context(person_name, org_name)

    return context


# ---------------------------------------------------------------------------
# Briefing formatting
# ---------------------------------------------------------------------------

def format_briefing(
    title: str,
    date: str,
    attendee_contexts: list[dict],
    talking_points: Optional[list[str]] = None,
) -> str:
    """Format a complete meeting briefing as markdown with YAML frontmatter.

    Args:
        title: Meeting title
        date: Meeting date string
        attendee_contexts: List of context dicts from gather_attendee_context
        talking_points: Optional list of talking point strings
    """
    lines = [
        "---",
        f"title: \"{title}\"",
        "type: meeting-briefing",
        f"date: \"{date}\"",
        f"generated: \"{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}\"",
        "---",
        "",
        f"# {title}",
        "",
        f"**Date:** {date}",
        "",
    ]

    # Per-attendee sections
    for ctx in attendee_contexts:
        person = ctx.get("person") or {}
        is_new = ctx.get("is_new", True)
        name = person.get("name", "Unknown attendee")

        lines.append(f"## {name}")
        lines.append("")

        # Organization
        orgs = ctx.get("organizations", [])
        if orgs:
            org_names = [o.get("name", "Unknown") for o in orgs]
            lines.append(f"**Organization:** {', '.join(org_names)}")
            lines.append("")

        # Meeting history
        past_meetings = ctx.get("past_meetings", [])
        if is_new or not past_meetings:
            lines.append("*First meeting — No prior interactions on record.*")
            lines.append("")
        else:
            lines.append(f"**Past meetings:** {len(past_meetings)}")
            for m in past_meetings[:5]:
                m_title = m.get("title", "Untitled")
                m_date = m.get("date", "Unknown date")
                lines.append(f"- {m_date}: {m_title}")
            lines.append("")

        # Goals
        goals = ctx.get("relevant_goals", [])
        if goals:
            lines.append("**Active goals:**")
            for g in goals:
                g_title = g.get("title", "Untitled")
                g_status = g.get("status", "")
                lines.append(f"- {g_title} ({g_status})")
            lines.append("")

        # Network
        network = ctx.get("network", [])
        if network:
            lines.append("**Network connections:**")
            for n in network[:5]:
                n_name = n.get("name", "Unknown")
                lines.append(f"- {n_name}")
            lines.append("")

        # Web context
        web = ctx.get("web_context", [])
        if web:
            lines.append("**Recent news:**")
            for w in web:
                w_title = w.get("title", "")
                w_url = w.get("url", "")
                lines.append(f"- [{w_title}]({w_url})")
            lines.append("")

    # Talking points section
    if talking_points:
        lines.append("## Talking Points")
        lines.append("")
        for i, point in enumerate(talking_points, 1):
            lines.append(f"{i}. {point}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# File writer
# ---------------------------------------------------------------------------

def write_briefing(vault_path: str, slug: str, content: str) -> Path:
    """Write briefing markdown to meetings/briefings/{slug}.md.

    Creates the directory if needed. Returns the written file path.
    """
    vault = Path(vault_path)
    briefing_dir = vault / "meetings" / "briefings"
    briefing_dir.mkdir(parents=True, exist_ok=True)

    filepath = briefing_dir / f"{slug}.md"
    filepath.write_text(content, encoding="utf-8")
    logger.info("Wrote briefing to %s", filepath)
    return filepath


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def generate_briefing(
    db,
    vault_path: str,
    meeting: dict,
    dry_run: bool = False,
) -> dict:
    """Full briefing pipeline: gather context -> web search -> talking points -> format -> write.

    Args:
        db: GraphDB instance
        vault_path: Path to the vault root
        meeting: Dict with keys: title, date, slug, attendees (list of dicts with 'slug')
        dry_run: If True, generate content but don't write to disk

    Returns:
        Dict with: content, path (if written), attendee_count, talking_points_count
    """
    title = meeting.get("title", "Untitled Meeting")
    date = meeting.get("date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    slug = meeting.get("slug", "untitled-meeting")
    attendees = meeting.get("attendees", [])

    # Gather context for each attendee
    attendee_contexts = []
    for att in attendees:
        att_slug = att.get("slug", "")
        if att_slug:
            ctx = gather_attendee_context(db, att_slug)
            attendee_contexts.append(ctx)

    # Generate talking points
    points = generate_talking_points(attendee_contexts, title)

    # Format the briefing
    content = format_briefing(title, date, attendee_contexts, points)

    result = {
        "content": content,
        "path": None,
        "attendee_count": len(attendee_contexts),
        "talking_points_count": len(points),
    }

    # Write to vault
    if not dry_run:
        filepath = write_briefing(vault_path, slug, content)
        result["path"] = str(filepath)

    return result
