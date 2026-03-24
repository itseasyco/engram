"""Tests for trust and sender verification."""

import hashlib
import hmac as hmac_mod

import pytest

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from lib.connectors.trust import (
    SenderEntry,
    SenderPolicy,
    SenderVerdict,
    TrustDecision,
    TrustVerifier,
    verify_hmac_signature,
)


class TestSenderEntry:
    def test_exact_match(self):
        e = SenderEntry(address="andrew@easylabs.io")
        assert e.matches("andrew@easylabs.io") is True
        assert e.matches("niko@easylabs.io") is False

    def test_case_insensitive(self):
        e = SenderEntry(address="Andrew@EasyLabs.io")
        assert e.matches("andrew@easylabs.io") is True

    def test_wildcard_domain(self):
        e = SenderEntry(address="*@easylabs.io")
        assert e.matches("andrew@easylabs.io") is True
        assert e.matches("niko@easylabs.io") is True
        assert e.matches("hacker@evil.com") is False

    def test_from_config_string(self):
        e = SenderEntry.from_config("test@example.com")
        assert e.address == "test@example.com"
        assert e.trust_override is None

    def test_from_config_dict(self):
        e = SenderEntry.from_config({
            "address": "boss@co.com",
            "trust_override": "high",
            "landing_zone_override": "queue-agent",
        })
        assert e.address == "boss@co.com"
        assert e.trust_override == "high"
        assert e.landing_zone_override == "queue-agent"


class TestTrustVerifierAllowlist:
    def test_accept_listed_sender(self):
        v = TrustVerifier.from_connector_config({
            "sender_policy": "allowlist",
            "sender_allowlist": ["andrew@easylabs.io", "niko@easylabs.io"],
        })
        verdict = v.check_sender("andrew@easylabs.io")
        assert verdict.decision == TrustDecision.ACCEPT

    def test_reject_unlisted_sender(self):
        v = TrustVerifier.from_connector_config({
            "sender_policy": "allowlist",
            "sender_allowlist": ["andrew@easylabs.io"],
        })
        verdict = v.check_sender("hacker@evil.com")
        assert verdict.decision == TrustDecision.REJECT

    def test_trust_override_propagated(self):
        v = TrustVerifier.from_connector_config({
            "sender_policy": "allowlist",
            "sender_allowlist": [
                {"address": "andrew@easylabs.io", "trust_override": "high"},
            ],
        })
        verdict = v.check_sender("andrew@easylabs.io")
        assert verdict.trust_override == "high"

    def test_empty_sender_rejected(self):
        v = TrustVerifier.from_connector_config({
            "sender_policy": "allowlist",
            "sender_allowlist": ["andrew@easylabs.io"],
        })
        verdict = v.check_sender("")
        assert verdict.decision == TrustDecision.REJECT


class TestTrustVerifierDomain:
    def test_accept_matching_domain(self):
        v = TrustVerifier.from_connector_config({
            "sender_policy": "domain",
            "sender_domains": ["easylabs.io"],
        })
        verdict = v.check_sender("anyone@easylabs.io")
        assert verdict.decision == TrustDecision.ACCEPT

    def test_reject_non_matching_domain(self):
        v = TrustVerifier.from_connector_config({
            "sender_policy": "domain",
            "sender_domains": ["easylabs.io"],
        })
        verdict = v.check_sender("someone@other.com")
        assert verdict.decision == TrustDecision.REJECT


class TestTrustVerifierOpen:
    def test_accept_anyone(self):
        v = TrustVerifier.from_connector_config({
            "sender_policy": "open",
        })
        verdict = v.check_sender("random@anywhere.net")
        assert verdict.decision == TrustDecision.ACCEPT

    def test_accept_empty_sender(self):
        v = TrustVerifier.from_connector_config({
            "sender_policy": "open",
        })
        verdict = v.check_sender("")
        assert verdict.decision == TrustDecision.ACCEPT

    def test_default_is_open(self):
        v = TrustVerifier.from_connector_config({})
        verdict = v.check_sender("anyone@anywhere.com")
        assert verdict.decision == TrustDecision.ACCEPT


class TestIPAllowlist:
    def test_no_restriction_allows_all(self):
        v = TrustVerifier(
            policy=SenderPolicy.OPEN,
            entries=[],
            ip_allowlist=[],
        )
        assert v.check_ip("1.2.3.4") is True

    def test_exact_ip_match(self):
        v = TrustVerifier(
            policy=SenderPolicy.OPEN,
            entries=[],
            ip_allowlist=["10.0.0.1", "10.0.0.2"],
        )
        assert v.check_ip("10.0.0.1") is True
        assert v.check_ip("10.0.0.3") is False

    def test_cidr_match(self):
        v = TrustVerifier(
            policy=SenderPolicy.OPEN,
            entries=[],
            ip_allowlist=["192.168.1.0/24"],
        )
        assert v.check_ip("192.168.1.100") is True
        assert v.check_ip("192.168.2.1") is False

    def test_invalid_ip_rejected(self):
        v = TrustVerifier(
            policy=SenderPolicy.OPEN,
            entries=[],
            ip_allowlist=["10.0.0.0/8"],
        )
        assert v.check_ip("not-an-ip") is False


class TestHMACVerification:
    def test_valid_sha256(self):
        secret = "webhook-secret-123"
        body = b'{"event": "push"}'
        sig = hmac_mod.new(secret.encode(), body, hashlib.sha256).hexdigest()
        assert verify_hmac_signature(body, sig, secret, algorithm="sha256") is True

    def test_invalid_signature(self):
        assert verify_hmac_signature(b"body", "badsig", "secret") is False

    def test_prefix_stripping(self):
        secret = "s3cret"
        body = b"data"
        sig = hmac_mod.new(secret.encode(), body, hashlib.sha256).hexdigest()
        header = f"sha256={sig}"
        assert verify_hmac_signature(body, header, secret, prefix="sha256=") is True

    def test_empty_signature_rejected(self):
        assert verify_hmac_signature(b"x", "", "secret") is False

    def test_empty_secret_rejected(self):
        assert verify_hmac_signature(b"x", "sig", "") is False
