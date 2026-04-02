"""Tests for calendar_watcher module."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# TestAttendeeResolution
# ---------------------------------------------------------------------------

class TestAttendeeResolution:
    """Test resolving calendar attendees to vault entities."""

    def test_resolve_email_to_person(self, temp_vault, sample_person_note):
        """Kate's email resolves to her vault profile via name match, source='vault'."""
        from lib.calendar_watcher import resolve_attendee

        result = resolve_attendee(
            email="kate@a16z.com",
            name="Kate Levchuk",
            vault_path=str(temp_vault),
            db=None,
        )
        assert result["slug"] == "kate-levchuk"
        assert result["source"] == "vault"
        assert "Kate" in result["name"]

    def test_resolve_unknown_attendee_returns_stub(self):
        """Unknown email returns stub with source='calendar'."""
        from lib.calendar_watcher import resolve_attendee

        result = resolve_attendee(
            email="nobody@example.com",
            name="Nobody Special",
            vault_path="/nonexistent/vault",
            db=None,
        )
        assert result["source"] == "calendar"
        assert result["slug"] == "nobody-special"
        assert result["name"] == "Nobody Special"

    def test_resolve_attendee_by_name_fuzzy(self, temp_vault, sample_person_note):
        """'Kate L.' fuzzy matches to 'kate-levchuk'."""
        from lib.calendar_watcher import resolve_attendee

        result = resolve_attendee(
            email="unknown@example.com",
            name="Kate L.",
            vault_path=str(temp_vault),
            db=None,
        )
        assert result["slug"] == "kate-levchuk"
        assert result["source"] == "vault"


# ---------------------------------------------------------------------------
# TestMeetingExtraction
# ---------------------------------------------------------------------------

class TestMeetingExtraction:
    """Test parsing and filtering calendar events."""

    def test_parse_calendar_event(self):
        """Parses event dict with summary, start.dateTime, attendees into normalized meeting."""
        from lib.calendar_watcher import parse_calendar_event

        event = {
            "summary": "Investor Call with Kate",
            "start": {"dateTime": "2026-04-02T14:00:00-07:00"},
            "end": {"dateTime": "2026-04-02T15:00:00-07:00"},
            "attendees": [
                {"email": "kate@a16z.com", "displayName": "Kate Levchuk", "responseStatus": "accepted"},
                {"email": "andrew@easylabs.io", "displayName": "Andrew Fisher", "responseStatus": "accepted"},
            ],
            "description": "Discuss Series A timeline",
        }

        meeting = parse_calendar_event(event)

        assert meeting["title"] == "Investor Call with Kate"
        assert meeting["date"] == "2026-04-02"
        assert meeting["start_time"] == "2026-04-02T14:00:00-07:00"
        assert meeting["end_time"] == "2026-04-02T15:00:00-07:00"
        assert len(meeting["attendees"]) == 2
        assert meeting["attendees"][0]["email"] == "kate@a16z.com"
        assert meeting["attendees"][0]["name"] == "Kate Levchuk"
        assert meeting["attendees"][0]["response"] == "accepted"
        assert meeting["description"] == "Discuss Series A timeline"
        assert meeting["slug"] == "2026-04-02-investor-call-with-kate"

    def test_filter_upcoming_meetings(self):
        """Only returns events in next 48 hours, filters past events."""
        from lib.calendar_watcher import filter_upcoming

        now = datetime.now(timezone.utc)
        future_time = (now + timedelta(hours=12)).isoformat()
        past_time = (now - timedelta(hours=12)).isoformat()
        far_future_time = (now + timedelta(hours=72)).isoformat()

        events = [
            {"summary": "Future meeting", "start": {"dateTime": future_time}},
            {"summary": "Past meeting", "start": {"dateTime": past_time}},
            {"summary": "Far future meeting", "start": {"dateTime": far_future_time}},
        ]

        result = filter_upcoming(events, hours_ahead=48)

        assert len(result) == 1
        assert result[0]["summary"] == "Future meeting"


# ---------------------------------------------------------------------------
# TestBriefingTrigger
# ---------------------------------------------------------------------------

class TestBriefingTrigger:
    """Test whether a meeting needs a briefing."""

    def test_needs_briefing_returns_true_for_new_meeting(self, temp_vault):
        """No existing briefing -> True."""
        from lib.calendar_watcher import needs_briefing

        # Ensure briefings dir exists but no file for this meeting
        (temp_vault / "meetings" / "briefings").mkdir(parents=True, exist_ok=True)
        assert needs_briefing("2026-04-02-investor-call", str(temp_vault)) is True

    def test_needs_briefing_returns_false_if_exists(self, temp_vault):
        """Existing briefing file -> False."""
        from lib.calendar_watcher import needs_briefing

        briefing_dir = temp_vault / "meetings" / "briefings"
        briefing_dir.mkdir(parents=True, exist_ok=True)
        (briefing_dir / "2026-04-02-investor-call.md").write_text("# Briefing\n")

        assert needs_briefing("2026-04-02-investor-call", str(temp_vault)) is False


# ---------------------------------------------------------------------------
# TestCirclebackWatcher
# ---------------------------------------------------------------------------

class TestCirclebackWatcher:
    """Test checking Gmail for Circleback transcripts."""

    def test_check_for_transcript_returns_none_when_not_found(self):
        """Mock gmail with empty results -> None."""
        from lib.calendar_watcher import check_for_transcript

        gmail = MagicMock()
        gmail.search_messages.return_value = {"messages": []}

        result = check_for_transcript(
            meeting_slug="2026-04-02-investor-call",
            meeting_title="Investor Call",
            gmail_client=gmail,
        )
        assert result is None

    def test_check_for_transcript_returns_body_when_found(self):
        """Mock gmail with message -> returns transcript + message_id."""
        from lib.calendar_watcher import check_for_transcript

        gmail = MagicMock()
        gmail.search_messages.return_value = {
            "messages": [{"id": "msg-123", "snippet": "Transcript from meeting"}],
        }
        gmail.read_message.return_value = {
            "body": "Full transcript text here...",
            "subject": "Circleback: Investor Call",
        }

        result = check_for_transcript(
            meeting_slug="2026-04-02-investor-call",
            meeting_title="Investor Call",
            gmail_client=gmail,
        )

        assert result is not None
        assert result["transcript"] == "Full transcript text here..."
        assert result["message_id"] == "msg-123"
        assert result["subject"] == "Circleback: Investor Call"
        assert result["meeting_slug"] == "2026-04-02-investor-call"
        assert "received_at" in result
