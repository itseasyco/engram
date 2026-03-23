"""
Slack connector (Tier 2 -- First-party).

Handles Slack events: messages, reaction_added. Filters by channel and
user allowlists. Supports reaction-based bookmarking (min_reactions
threshold) and thread extraction.

Config keys:
  - bot_token: Slack bot OAuth token
  - channels: list of channel names or IDs to monitor
  - user_allowlist: list of Slack user IDs to accept (empty = accept all users)
  - events: list of event types (default: ["message", "reaction_added"])
  - min_reactions: minimum reactions on a message to auto-ingest (default: 2)
  - bookmark_reactions: list of reaction names that trigger ingestion (e.g. ["brain", "bookmark"])
"""

from __future__ import annotations

import json
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Any, Optional

from .base import Connector, ConnectorStatus, RawData, VaultNote
from .trust import TrustVerifier, TrustDecision


class SlackConnector(Connector):
    """Receive and process Slack events."""

    type = "slack"

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self._bot_token: str = self.connector_config.get("bot_token", "")
        self._channels: list[str] = self.connector_config.get("channels", [])
        self._user_allowlist: list[str] = self.connector_config.get("user_allowlist", [])
        self._events: set[str] = set(
            self.connector_config.get("events", ["message", "reaction_added"])
        )
        self._min_reactions: int = self.connector_config.get("min_reactions", 2)
        self._bookmark_reactions: list[str] = self.connector_config.get(
            "bookmark_reactions", ["brain", "bookmark", "star"]
        )
        self._channel_name_cache: dict[str, str] = {}  # id -> name
        self._user_name_cache: dict[str, str] = {}  # id -> display_name
        self._trust_verifier = TrustVerifier.from_connector_config(self.connector_config)

    def authenticate(self) -> bool:
        """Verify bot token by calling auth.test."""
        if not self._bot_token:
            return False
        try:
            result = self._slack_api("auth.test")
            return result.get("ok", False)
        except Exception:
            return False

    def _slack_api(self, method: str, data: Optional[dict] = None) -> dict:
        """Call a Slack API method."""
        url = f"https://slack.com/api/{method}"
        headers = {
            "Authorization": f"Bearer {self._bot_token}",
            "Content-Type": "application/json; charset=utf-8",
        }
        body = json.dumps(data).encode() if data else None
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())

    def _resolve_channel_name(self, channel_id: str) -> str:
        """Get channel name from ID, with caching."""
        if channel_id in self._channel_name_cache:
            return self._channel_name_cache[channel_id]
        try:
            result = self._slack_api("conversations.info", {"channel": channel_id})
            name = result.get("channel", {}).get("name", channel_id)
            self._channel_name_cache[channel_id] = name
            return name
        except Exception:
            return channel_id

    def _resolve_user_name(self, user_id: str) -> str:
        """Get user display name from ID, with caching."""
        if user_id in self._user_name_cache:
            return self._user_name_cache[user_id]
        try:
            result = self._slack_api("users.info", {"user": user_id})
            profile = result.get("user", {}).get("profile", {})
            name = profile.get("display_name") or profile.get("real_name") or user_id
            self._user_name_cache[user_id] = name
            return name
        except Exception:
            return user_id

    def receive(self, payload: dict[str, Any]) -> RawData:
        """Accept a Slack event payload."""
        event = payload.get("event", payload)
        event_type = event.get("type", "unknown")

        if event_type not in self._events:
            raise ValueError(f"Event type {event_type} not accepted")

        # Channel filter
        channel = event.get("channel", "")
        if self._channels:
            channel_name = self._resolve_channel_name(channel) if channel else ""
            if channel not in self._channels and channel_name not in self._channels:
                raise ValueError(f"Channel {channel} ({channel_name}) not in allowlist")

        # User filter
        user = event.get("user", "")
        if self._user_allowlist and user not in self._user_allowlist:
            raise ValueError(f"User {user} not in allowlist")

        # For reaction events, check the reaction name and count
        if event_type == "reaction_added":
            reaction = event.get("reaction", "")
            if reaction not in self._bookmark_reactions:
                raise ValueError(f"Reaction {reaction} not a bookmark reaction")

        ts = event.get("ts", event.get("event_ts", ""))
        source_id = f"slack-{channel}-{ts}"

        return RawData(
            source_id=source_id,
            payload=event,
            sender=user,
            metadata={
                "event_type": event_type,
                "channel": channel,
                "ts": ts,
            },
        )

    def pull(self) -> list[RawData]:
        """
        Pull recent messages from configured channels.

        Fetches messages with >= min_reactions and messages with bookmark reactions.
        """
        results: list[RawData] = []

        for channel in self._channels:
            try:
                resp = self._slack_api("conversations.history", {
                    "channel": channel,
                    "limit": 50,
                })
                if not resp.get("ok"):
                    continue

                for msg in resp.get("messages", []):
                    # Check reaction threshold
                    reactions = msg.get("reactions", [])
                    total_reactions = sum(r.get("count", 0) for r in reactions)
                    has_bookmark = any(
                        r.get("name", "") in self._bookmark_reactions
                        for r in reactions
                    )

                    if total_reactions >= self._min_reactions or has_bookmark:
                        user = msg.get("user", "")
                        if self._user_allowlist and user not in self._user_allowlist:
                            continue

                        ts = msg.get("ts", "")
                        results.append(RawData(
                            source_id=f"slack-{channel}-{ts}",
                            payload=msg,
                            sender=user,
                            metadata={
                                "event_type": "message",
                                "channel": channel,
                                "ts": ts,
                            },
                        ))
            except Exception as exc:
                self.record_error(f"Pull failed for channel {channel}: {exc}")

        return results

    def transform(self, raw_data: RawData) -> VaultNote:
        """Transform a Slack event into a VaultNote."""
        event = raw_data.payload
        event_type = raw_data.metadata.get("event_type", "message")
        channel = raw_data.metadata.get("channel", "")
        channel_name = self._resolve_channel_name(channel) if channel else "unknown"
        user = raw_data.sender
        user_name = self._resolve_user_name(user) if user else "unknown"

        if event_type == "reaction_added":
            return self._transform_reaction(raw_data, event, channel_name, user_name)
        else:
            return self._transform_message(raw_data, event, channel_name, user_name)

    def _transform_message(
        self, raw: RawData, event: dict, channel_name: str, user_name: str
    ) -> VaultNote:
        text = event.get("text", "")
        ts = event.get("ts", "")
        thread_ts = event.get("thread_ts", "")

        # Build title from first line of message
        first_line = text.split("\n")[0][:60] if text else "(empty message)"

        note_body = f"""## Slack Message

**Channel:** #{channel_name}
**Author:** {user_name}
**Timestamp:** {ts}
{f"**Thread:** {thread_ts}" if thread_ts else ""}

### Content

{text}
"""

        reactions = event.get("reactions", [])
        if reactions:
            reaction_lines = [
                f"- :{r.get('name', '?')}: x{r.get('count', 0)}"
                for r in reactions
            ]
            note_body += f"\n### Reactions\n\n" + "\n".join(reaction_lines)

        tags = ["slack", f"channel-{channel_name}"]

        return VaultNote(
            title=f"Slack: {first_line} (#{channel_name})",
            body=note_body,
            source_connector=self.id,
            source_type=self.type,
            source_id=raw.source_id,
            trust_level=self.trust_level,
            landing_zone=self.landing_zone,
            tags=tags,
            category="slack-message",
            author=user_name,
        )

    def _transform_reaction(
        self, raw: RawData, event: dict, channel_name: str, user_name: str
    ) -> VaultNote:
        reaction = event.get("reaction", "?")
        item = event.get("item", {})
        item_ts = item.get("ts", "")
        item_channel = item.get("channel", "")

        note_body = f"""## Slack Bookmark

**Reaction:** :{reaction}:
**By:** {user_name}
**Channel:** #{channel_name}
**Message timestamp:** {item_ts}

(Original message content would be fetched via conversations.history)
"""

        return VaultNote(
            title=f"Slack Bookmark: :{reaction}: in #{channel_name}",
            body=note_body,
            source_connector=self.id,
            source_type=self.type,
            source_id=raw.source_id,
            trust_level=self.trust_level,
            landing_zone=self.landing_zone,
            tags=["slack", "bookmark", reaction],
            category="slack-bookmark",
            author=user_name,
        )

    def health_check(self) -> ConnectorStatus:
        healthy = bool(self._bot_token)
        status = self.base_status(healthy=healthy)
        status.extra["channels"] = self._channels
        status.extra["user_allowlist_count"] = len(self._user_allowlist)
        status.extra["events"] = list(self._events)
        return status
