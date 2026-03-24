"""
Email connector (Tier 2 -- First-party).

Polls email inbox via IMAP or gog (Gmail OAuth). Filters by folder,
sender, and subject. Per-sender routing and trust overrides.

Config keys:
  - provider: "imap" or "gog" (Gmail OAuth via gog utility)
  - imap_host: IMAP server hostname (for imap provider)
  - imap_port: IMAP port (default: 993)
  - username: IMAP username
  - password: IMAP password (use ${ENV_VAR} reference)
  - folders: list of IMAP folders to monitor (default: ["INBOX"])
  - poll_interval_minutes: how often to poll (default: 15)
  - sender_policy: "allowlist" | "domain" | "open"
  - sender_allowlist: list of sender addresses or dicts with trust overrides
  - subject_filters: list of subject patterns to match (optional, regex)
  - max_body_length: max email body characters to include (default: 4000)
"""

from __future__ import annotations

import email
import email.header
import email.utils
import imaplib
import re
import subprocess
import shutil
from datetime import datetime, timezone
from typing import Any, Optional

from .base import Connector, ConnectorStatus, RawData, VaultNote
from .trust import TrustVerifier, TrustDecision


class EmailConnector(Connector):
    """Poll email inbox and transform messages into vault notes."""

    type = "email"

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self._provider: str = self.connector_config.get("provider", "imap")
        self._imap_host: str = self.connector_config.get("imap_host", "")
        self._imap_port: int = self.connector_config.get("imap_port", 993)
        self._username: str = self.connector_config.get("username", "")
        self._password: str = self.connector_config.get("password", "")
        self._folders: list[str] = self.connector_config.get("folders", ["INBOX"])
        self._poll_interval: int = self.connector_config.get("poll_interval_minutes", 15)
        self._subject_filters: list[str] = self.connector_config.get("subject_filters", [])
        self._max_body_length: int = self.connector_config.get("max_body_length", 4000)
        self._trust_verifier = TrustVerifier.from_connector_config(self.connector_config)
        self._seen_message_ids: set[str] = set()
        self._imap: Optional[imaplib.IMAP4_SSL] = None

    def authenticate(self) -> bool:
        """Connect to IMAP server or verify gog is available."""
        if self._provider == "gog":
            return self._authenticate_gog()
        else:
            return self._authenticate_imap()

    def _authenticate_imap(self) -> bool:
        """Connect to IMAP server with credentials."""
        if not self._imap_host or not self._username:
            return False
        try:
            self._imap = imaplib.IMAP4_SSL(self._imap_host, self._imap_port)
            self._imap.login(self._username, self._password)
            return True
        except Exception as exc:
            self.record_error(f"IMAP auth failed: {exc}")
            return False

    def _authenticate_gog(self) -> bool:
        """Verify gog (Gmail OAuth) utility is available."""
        if not shutil.which("gog"):
            self.record_error("gog utility not found in PATH")
            return False
        try:
            result = subprocess.run(
                ["gog", "check"],
                capture_output=True, text=True, timeout=10,
            )
            return result.returncode == 0
        except Exception as exc:
            self.record_error(f"gog check failed: {exc}")
            return False

    def pull(self) -> list[RawData]:
        """Fetch unread messages from configured folders."""
        results: list[RawData] = []

        for folder in self._folders:
            try:
                messages = self._fetch_from_folder(folder)
                results.extend(messages)
            except Exception as exc:
                self.record_error(f"Fetch failed for folder {folder}: {exc}")

        return results

    def _fetch_from_folder(self, folder: str) -> list[RawData]:
        """Fetch messages from a single IMAP folder."""
        results: list[RawData] = []

        if self._provider == "gog":
            return self._fetch_via_gog(folder)

        if self._imap is None:
            return results

        try:
            self._imap.select(folder, readonly=True)
            _, data = self._imap.search(None, "UNSEEN")
            if not data or not data[0]:
                return results

            msg_nums = data[0].split()
            for num in msg_nums[-50:]:  # limit to 50 most recent
                _, msg_data = self._imap.fetch(num, "(RFC822)")
                if not msg_data or not msg_data[0]:
                    continue

                raw_email = msg_data[0][1]
                if isinstance(raw_email, bytes):
                    msg = email.message_from_bytes(raw_email)
                else:
                    msg = email.message_from_string(raw_email)

                raw = self._parse_email(msg, folder)
                if raw is not None:
                    results.append(raw)

        except Exception as exc:
            self.record_error(f"IMAP fetch error in {folder}: {exc}")

        return results

    def _fetch_via_gog(self, folder: str) -> list[RawData]:
        """Fetch messages using gog utility (Gmail OAuth)."""
        results: list[RawData] = []
        try:
            result = subprocess.run(
                ["gog", "fetch", "--folder", folder, "--format", "json", "--limit", "50"],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode != 0:
                self.record_error(f"gog fetch failed: {result.stderr}")
                return results

            import json
            messages = json.loads(result.stdout)
            for msg_data in messages:
                message_id = msg_data.get("message_id", "")
                if message_id in self._seen_message_ids:
                    continue
                self._seen_message_ids.add(message_id)

                sender = msg_data.get("from", "")
                subject = msg_data.get("subject", "")
                body = msg_data.get("body", "")
                date = msg_data.get("date", "")

                # Sender verification
                verdict = self._trust_verifier.check_sender(sender)
                if verdict.decision == TrustDecision.REJECT:
                    continue

                # Subject filter
                if not self._matches_subject(subject):
                    continue

                results.append(RawData(
                    source_id=message_id or f"gog-{folder}-{date}",
                    payload={
                        "from": sender,
                        "subject": subject,
                        "body": body[:self._max_body_length],
                        "date": date,
                        "folder": folder,
                        "message_id": message_id,
                    },
                    sender=sender,
                    metadata={
                        "folder": folder,
                        "trust_override": verdict.trust_override,
                        "landing_zone_override": verdict.landing_zone_override,
                    },
                ))

        except Exception as exc:
            self.record_error(f"gog fetch error: {exc}")

        return results

    def _parse_email(self, msg: email.message.Message, folder: str) -> Optional[RawData]:
        """Parse a single email.message.Message into RawData."""
        message_id = msg.get("Message-ID", "")
        if message_id in self._seen_message_ids:
            return None
        self._seen_message_ids.add(message_id)

        # Decode sender
        from_raw = msg.get("From", "")
        sender_name, sender_addr = email.utils.parseaddr(from_raw)

        # Sender verification
        verdict = self._trust_verifier.check_sender(sender_addr)
        if verdict.decision == TrustDecision.REJECT:
            return None

        # Decode subject
        subject_raw = msg.get("Subject", "")
        decoded_parts = email.header.decode_header(subject_raw)
        subject = ""
        for part, charset in decoded_parts:
            if isinstance(part, bytes):
                subject += part.decode(charset or "utf-8", errors="replace")
            else:
                subject += str(part)

        # Subject filter
        if not self._matches_subject(subject):
            return None

        # Extract body
        body = self._extract_body(msg)

        date = msg.get("Date", "")

        return RawData(
            source_id=message_id or f"email-{folder}-{date}",
            payload={
                "from": sender_addr,
                "from_name": sender_name,
                "subject": subject,
                "body": body[:self._max_body_length],
                "date": date,
                "folder": folder,
                "message_id": message_id,
            },
            sender=sender_addr,
            metadata={
                "folder": folder,
                "trust_override": verdict.trust_override,
                "landing_zone_override": verdict.landing_zone_override,
            },
        )

    def _extract_body(self, msg: email.message.Message) -> str:
        """Extract text body from email message."""
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                if content_type == "text/plain":
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or "utf-8"
                        return payload.decode(charset, errors="replace")
            # Fallback to HTML
            for part in msg.walk():
                if part.get_content_type() == "text/html":
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or "utf-8"
                        html = payload.decode(charset, errors="replace")
                        # Strip HTML tags (basic)
                        return re.sub(r"<[^>]+>", "", html)
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                charset = msg.get_content_charset() or "utf-8"
                return payload.decode(charset, errors="replace")
        return ""

    def _matches_subject(self, subject: str) -> bool:
        """Check if subject matches any configured filter patterns."""
        if not self._subject_filters:
            return True
        for pattern in self._subject_filters:
            if re.search(pattern, subject, re.IGNORECASE):
                return True
        return False

    def transform(self, raw_data: RawData) -> VaultNote:
        """Transform an email into a VaultNote."""
        p = raw_data.payload
        sender = p.get("from", "unknown")
        sender_name = p.get("from_name", sender)
        subject = p.get("subject", "(no subject)")
        body = p.get("body", "")
        date = p.get("date", "")
        folder = p.get("folder", "INBOX")

        # Apply trust/landing zone overrides from sender verification
        trust_override = raw_data.metadata.get("trust_override")
        lz_override = raw_data.metadata.get("landing_zone_override")

        note_body = f"""## Email: {subject}

**From:** {sender_name} <{sender}>
**Date:** {date}
**Folder:** {folder}

### Content

{body}
"""

        trust = trust_override or self.trust_level
        landing = lz_override or self.landing_zone

        return VaultNote(
            title=f"Email: {subject}",
            body=note_body,
            source_connector=self.id,
            source_type=self.type,
            source_id=raw_data.source_id,
            trust_level=trust,
            landing_zone=landing,
            tags=["email", f"folder-{folder.replace('/', '-')}"],
            category="email",
            author=f"{sender_name} <{sender}>",
        )

    def health_check(self) -> ConnectorStatus:
        healthy = True
        if self._provider == "imap":
            healthy = self._imap is not None
        elif self._provider == "gog":
            healthy = bool(shutil.which("gog"))

        status = self.base_status(healthy=healthy)
        status.extra["provider"] = self._provider
        status.extra["folders"] = self._folders
        status.extra["seen_messages"] = len(self._seen_message_ids)
        return status
