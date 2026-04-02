"""
Calendar watcher for Engram Phase 2.

Parses Google Calendar events, resolves attendees to vault entities,
checks for existing briefings, and watches Gmail for Circleback transcripts.
"""

import logging
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

from .consolidation import _parse_frontmatter
from .entity_extractor import _slugify

logger = logging.getLogger("calendar_watcher")


# ---------------------------------------------------------------------------
# Event parsing
# ---------------------------------------------------------------------------

def parse_calendar_event(event: dict) -> dict:
    """
    Parse a Google Calendar event into a normalized meeting dict.

    Returns:
        {title, date, start_time, end_time, attendees, description, slug}
    """
    title = event.get("summary", "Untitled Meeting")
    start_dt = event.get("start", {}).get("dateTime", "")
    end_dt = event.get("end", {}).get("dateTime", "")
    date = start_dt[:10] if start_dt else ""

    attendees = []
    for att in event.get("attendees", []):
        attendees.append({
            "email": att.get("email", ""),
            "name": att.get("displayName", ""),
            "response": att.get("responseStatus", "needsAction"),
        })

    slug = _slugify(f"{date}-{title}")

    return {
        "title": title,
        "date": date,
        "start_time": start_dt,
        "end_time": end_dt,
        "attendees": attendees,
        "description": event.get("description", ""),
        "slug": slug,
    }


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------

def filter_upcoming(events: list[dict], hours_ahead: int = 48) -> list[dict]:
    """
    Filter events to those starting between now and now + hours_ahead.

    Handles both timezone-aware and naive ISO datetimes.
    """
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(hours=hours_ahead)

    upcoming = []
    for event in events:
        start_str = event.get("start", {}).get("dateTime", "")
        if not start_str:
            continue

        start = _parse_iso(start_str)
        if start is None:
            continue

        if now <= start <= cutoff:
            upcoming.append(event)

    return upcoming


def _parse_iso(dt_str: str) -> Optional[datetime]:
    """Parse an ISO datetime string, returning a timezone-aware datetime."""
    try:
        dt = datetime.fromisoformat(dt_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Attendee resolution
# ---------------------------------------------------------------------------

def resolve_attendee(
    email: str,
    name: str,
    vault_path: str,
    db=None,
) -> dict:
    """
    Resolve a calendar attendee to a vault entity.

    Resolution order:
      1. Graph DB lookup (Person node by name/slug)
      2. Vault filesystem scan (people/ dir, fuzzy match)
      3. Stub with source='calendar'

    Returns:
        {slug, name, source, email}
    """
    slug = _slugify(name) if name else _slugify(email.split("@")[0])

    # --- 1. Graph DB ---
    if db is not None:
        try:
            result = _resolve_from_graph(name, slug, db)
            if result:
                result["email"] = email
                return result
        except Exception:
            logger.debug("Graph DB lookup failed for %s", name, exc_info=True)

    # --- 2. Vault filesystem ---
    vault = Path(vault_path)
    people_dir = vault / "people"
    if people_dir.exists():
        result = _resolve_from_vault(name, slug, people_dir)
        if result:
            result["email"] = email
            return result

    # --- 3. Stub ---
    return {
        "slug": slug,
        "name": name or email,
        "source": "calendar",
        "email": email,
    }


def _resolve_from_graph(name: str, slug: str, db) -> Optional[dict]:
    """Try to find a Person node in the graph DB by name or slug."""
    # Try exact slug match
    query = "MATCH (p:Person) WHERE toLower(p.slug) = $slug RETURN p LIMIT 1"
    rows = db.execute_read_only(query, {"slug": slug})
    if rows:
        node = rows[0]["p"] if isinstance(rows[0], dict) else rows[0]
        return {
            "slug": slug,
            "name": name,
            "source": "graph",
        }

    # Try name pattern
    if name:
        query = "MATCH (p:Person) WHERE toLower(p.name) CONTAINS $pattern RETURN p LIMIT 1"
        rows = db.execute_read_only(query, {"pattern": name.lower()})
        if rows:
            return {
                "slug": slug,
                "name": name,
                "source": "graph",
            }

    return None


def _resolve_from_vault(name: str, slug: str, people_dir: Path) -> Optional[dict]:
    """
    Scan people/ subdirectories for a matching vault note.

    Uses SequenceMatcher for fuzzy matching on slug and frontmatter title.
    Match threshold: 0.6.
    """
    best_match = None
    best_ratio = 0.0

    for md_file in people_dir.rglob("*.md"):
        file_slug = md_file.stem
        # Check slug similarity
        ratio = SequenceMatcher(None, slug, file_slug).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_match = md_file

        # Also check frontmatter title
        if name:
            try:
                content = md_file.read_text(encoding="utf-8")
                fm = _parse_frontmatter(content)
                title = fm.get("title", "")
                if isinstance(title, str) and title:
                    title_slug = _slugify(title)
                    title_ratio = SequenceMatcher(None, slug, title_slug).ratio()
                    if title_ratio > best_ratio:
                        best_ratio = title_ratio
                        best_match = md_file
                    # Also compare raw name to title
                    name_ratio = SequenceMatcher(
                        None, name.lower(), title.lower()
                    ).ratio()
                    if name_ratio > best_ratio:
                        best_ratio = name_ratio
                        best_match = md_file
            except (IOError, UnicodeDecodeError):
                continue

    if best_ratio >= 0.6 and best_match is not None:
        return {
            "slug": best_match.stem,
            "name": name,
            "source": "vault",
        }

    return None


# ---------------------------------------------------------------------------
# Briefing check
# ---------------------------------------------------------------------------

def needs_briefing(meeting_slug: str, vault_path: str) -> bool:
    """Check if a briefing already exists for a meeting."""
    briefing_path = Path(vault_path) / "meetings" / "briefings" / f"{meeting_slug}.md"
    return not briefing_path.exists()


# ---------------------------------------------------------------------------
# Circleback transcript watcher
# ---------------------------------------------------------------------------

def check_for_transcript(
    meeting_slug: str,
    meeting_title: str,
    gmail_client=None,
    search_hours_back: int = 24,
) -> Optional[dict]:
    """
    Search Gmail for a Circleback transcript related to this meeting.

    The gmail_client mock supports:
      - search_messages(query=...) -> {"messages": [{"id": ..., "snippet": ...}]}
      - read_message(message_id=...) -> {"body": ..., "subject": ...}

    Returns:
        {transcript, message_id, subject, received_at, meeting_slug} or None.
    """
    if gmail_client is None:
        return None

    query = f"from:circleback subject:{meeting_title}"
    search_result = gmail_client.search_messages(query=query)
    messages = search_result.get("messages", [])

    if not messages:
        return None

    msg = messages[0]
    message_id = msg.get("id", "")
    full_message = gmail_client.read_message(message_id=message_id)

    return {
        "transcript": full_message.get("body", ""),
        "message_id": message_id,
        "subject": full_message.get("subject", ""),
        "received_at": datetime.now(timezone.utc).isoformat(),
        "meeting_slug": meeting_slug,
    }


# ---------------------------------------------------------------------------
# Stub: upcoming meetings from Calendar MCP
# ---------------------------------------------------------------------------

def get_upcoming_meetings(vault_path: str, hours_ahead: int = 48) -> list[dict]:
    """Stub — returns [] until wired to Calendar MCP."""
    return []
