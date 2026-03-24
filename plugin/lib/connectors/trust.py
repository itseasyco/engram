"""
Two-layer trust and sender verification for connectors.

Layer 1: Connector trust level (verified, high, medium, low)
         Determines how the curator handles ingested notes.

Layer 2: Sender allowlist per connector
         Determines whether incoming data is accepted at all.

Policies:
  - allowlist: Only messages from listed senders accepted. Others dropped.
  - domain:    Accept from any sender matching the domain (e.g. @easylabs.io).
  - open:      Accept from anyone. Lowest trust, always tagged unverified.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class SenderPolicy(str, Enum):
    ALLOWLIST = "allowlist"
    DOMAIN = "domain"
    OPEN = "open"


class TrustDecision(str, Enum):
    ACCEPT = "accept"
    REJECT = "reject"


@dataclass
class SenderVerdict:
    """Result of sender verification."""

    decision: TrustDecision
    sender: str
    policy: str
    trust_override: Optional[str] = None
    landing_zone_override: Optional[str] = None
    reason: str = ""


@dataclass
class SenderEntry:
    """
    A single entry in a sender allowlist.

    Supports exact match, wildcard prefix (*@domain.com), and optional
    trust/landing_zone overrides per sender.
    """

    address: str
    trust_override: Optional[str] = None
    landing_zone_override: Optional[str] = None

    @classmethod
    def from_config(cls, entry: str | dict[str, Any]) -> "SenderEntry":
        """Parse from config -- supports both string and dict formats."""
        if isinstance(entry, str):
            return cls(address=entry)
        return cls(
            address=entry.get("address", ""),
            trust_override=entry.get("trust_override"),
            landing_zone_override=entry.get("landing_zone_override"),
        )

    def matches(self, sender: str) -> bool:
        """Check if sender matches this entry. Supports * wildcard."""
        sender_lower = sender.lower().strip()
        pattern_lower = self.address.lower().strip()

        if pattern_lower == sender_lower:
            return True

        # Wildcard: *@domain.com matches any user at that domain
        if pattern_lower.startswith("*@"):
            domain = pattern_lower[1:]  # "@domain.com"
            return sender_lower.endswith(domain)

        return False


class TrustVerifier:
    """
    Verifies senders against connector-specific policies.

    Usage:
        verifier = TrustVerifier.from_connector_config(connector_config)
        verdict = verifier.check_sender("user@example.com")
        if verdict.decision == TrustDecision.REJECT:
            # drop the message
    """

    def __init__(
        self,
        policy: SenderPolicy,
        entries: list[SenderEntry],
        domains: list[str] | None = None,
        ip_allowlist: list[str] | None = None,
    ):
        self.policy = policy
        self.entries = entries
        self.domains = [d.lower().strip() for d in (domains or [])]
        self.ip_allowlist = ip_allowlist or []

    @classmethod
    def from_connector_config(cls, config: dict[str, Any]) -> "TrustVerifier":
        """
        Build a TrustVerifier from a connector's config dict.

        Expects optional keys:
          - sender_policy: "allowlist" | "domain" | "open"
          - sender_allowlist: list of strings or dicts
          - sender_domains: list of domain strings
          - ip_allowlist: list of IP/CIDR strings
        """
        policy_str = config.get("sender_policy", "open")
        try:
            policy = SenderPolicy(policy_str)
        except ValueError:
            policy = SenderPolicy.OPEN

        raw_entries = config.get("sender_allowlist", [])
        entries = [SenderEntry.from_config(e) for e in raw_entries]

        domains = config.get("sender_domains", [])
        ip_allowlist = config.get("ip_allowlist", [])

        return cls(
            policy=policy,
            entries=entries,
            domains=domains,
            ip_allowlist=ip_allowlist,
        )

    def check_sender(self, sender: str) -> SenderVerdict:
        """
        Verify a sender against the configured policy.

        Returns a SenderVerdict with accept/reject decision and any overrides.
        """
        if not sender:
            if self.policy == SenderPolicy.OPEN:
                return SenderVerdict(
                    decision=TrustDecision.ACCEPT,
                    sender="",
                    policy=self.policy.value,
                    reason="open policy accepts all",
                )
            return SenderVerdict(
                decision=TrustDecision.REJECT,
                sender="",
                policy=self.policy.value,
                reason="empty sender rejected by non-open policy",
            )

        if self.policy == SenderPolicy.ALLOWLIST:
            return self._check_allowlist(sender)
        elif self.policy == SenderPolicy.DOMAIN:
            return self._check_domain(sender)
        else:  # OPEN
            return SenderVerdict(
                decision=TrustDecision.ACCEPT,
                sender=sender,
                policy=self.policy.value,
                reason="open policy accepts all",
            )

    def _check_allowlist(self, sender: str) -> SenderVerdict:
        """Check sender against explicit allowlist."""
        for entry in self.entries:
            if entry.matches(sender):
                return SenderVerdict(
                    decision=TrustDecision.ACCEPT,
                    sender=sender,
                    policy=self.policy.value,
                    trust_override=entry.trust_override,
                    landing_zone_override=entry.landing_zone_override,
                    reason=f"matched allowlist entry: {entry.address}",
                )
        return SenderVerdict(
            decision=TrustDecision.REJECT,
            sender=sender,
            policy=self.policy.value,
            reason="sender not in allowlist",
        )

    def _check_domain(self, sender: str) -> SenderVerdict:
        """Check sender against allowed domains."""
        sender_lower = sender.lower().strip()
        for domain in self.domains:
            normalized = domain if domain.startswith("@") else f"@{domain}"
            if sender_lower.endswith(normalized):
                return SenderVerdict(
                    decision=TrustDecision.ACCEPT,
                    sender=sender,
                    policy=self.policy.value,
                    reason=f"matched domain: {domain}",
                )
        # Also check entries (allowlist entries work as fallback in domain mode)
        for entry in self.entries:
            if entry.matches(sender):
                return SenderVerdict(
                    decision=TrustDecision.ACCEPT,
                    sender=sender,
                    policy=self.policy.value,
                    trust_override=entry.trust_override,
                    landing_zone_override=entry.landing_zone_override,
                    reason=f"matched allowlist entry: {entry.address}",
                )
        return SenderVerdict(
            decision=TrustDecision.REJECT,
            sender=sender,
            policy=self.policy.value,
            reason=f"sender domain not in allowed list: {self.domains}",
        )

    def check_ip(self, ip_str: str) -> bool:
        """
        Verify an IP address against the IP allowlist.

        Returns True if allowed (or if no IP allowlist is configured).
        Supports individual IPs and CIDR ranges.
        """
        if not self.ip_allowlist:
            return True  # no restriction
        try:
            addr = ipaddress.ip_address(ip_str)
        except ValueError:
            return False
        for entry in self.ip_allowlist:
            try:
                if "/" in entry:
                    network = ipaddress.ip_network(entry, strict=False)
                    if addr in network:
                        return True
                else:
                    if addr == ipaddress.ip_address(entry):
                        return True
            except ValueError:
                continue
        return False


def verify_hmac_signature(
    payload_body: bytes,
    signature_header: str,
    secret: str,
    algorithm: str = "sha256",
    prefix: str = "",
) -> bool:
    """
    Verify an HMAC signature from a webhook payload.

    Args:
        payload_body: Raw request body bytes.
        signature_header: Value of the signature header from the request.
        secret: The shared HMAC secret.
        algorithm: Hash algorithm (sha256, sha1).
        prefix: Optional prefix to strip from signature (e.g. "sha256=").

    Returns:
        True if signature is valid.
    """
    if not signature_header or not secret:
        return False

    sig = signature_header
    if prefix and sig.startswith(prefix):
        sig = sig[len(prefix):]

    hash_func = getattr(hashlib, algorithm, None)
    if hash_func is None:
        return False

    expected = hmac.new(
        secret.encode("utf-8"),
        payload_body,
        hash_func,
    ).hexdigest()

    return hmac.compare_digest(sig.lower(), expected.lower())
