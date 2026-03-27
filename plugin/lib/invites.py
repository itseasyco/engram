#!/usr/bin/env python3
"""
Invite token system for openclaw-lacp-fusion.

Tokens gate membership in a shared vault cluster. The curator generates tokens,
connected nodes redeem them during the join flow.

Token format: inv_<32 hex chars>
Storage: ~/.openclaw/config/invites.json
"""
from __future__ import annotations

import json
import os
import secrets
from dataclasses import asdict, dataclass, field
from datetime import datetime, UTC, timedelta
from pathlib import Path
from typing import Optional


TOKEN_PREFIX = "inv_"
TOKEN_HEX_LENGTH = 32  # 16 bytes = 128 bits


@dataclass
class InviteToken:
    token: str
    email: str
    role: str  # developer, pm, executive, readonly
    created_at: str
    expires_at: str
    single_use: bool = True
    redeemed: bool = False
    redeemed_at: Optional[str] = None
    redeemed_by: Optional[str] = None
    revoked: bool = False


def _invites_path() -> Path:
    openclaw_home = os.environ.get("OPENCLAW_HOME", os.path.expanduser("~/.openclaw"))
    return Path(openclaw_home) / "config" / "invites.json"


def _load_invites() -> list[dict]:
    path = _invites_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("invites", [])
    except (json.JSONDecodeError, OSError):
        return []


def _save_invites(invites: list[dict]) -> Path:
    path = _invites_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"invites": invites}, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def generate_token(
    email: str,
    role: str = "developer",
    expires_hours: int = 72,
    single_use: bool = True,
) -> InviteToken:
    """Generate a new invite token and persist it."""
    valid_roles = ("developer", "pm", "executive", "readonly")
    if role not in valid_roles:
        raise ValueError(f"Invalid role: {role!r}. Must be one of {valid_roles}")

    now = datetime.now(UTC)
    token_str = TOKEN_PREFIX + secrets.token_hex(TOKEN_HEX_LENGTH // 2)

    invite = InviteToken(
        token=token_str,
        email=email,
        role=role,
        created_at=now.isoformat(),
        expires_at=(now + timedelta(hours=expires_hours)).isoformat(),
        single_use=single_use,
    )

    invites = _load_invites()
    invites.append(asdict(invite))
    _save_invites(invites)

    return invite


def validate_token(token: str) -> tuple[bool, Optional[InviteToken], str]:
    """
    Validate an invite token.

    Returns (valid, invite_or_none, reason).
    """
    if not token.startswith(TOKEN_PREFIX):
        return False, None, "invalid_format"

    invites = _load_invites()
    for inv_dict in invites:
        if inv_dict["token"] != token:
            continue

        invite = InviteToken(**{k: v for k, v in inv_dict.items() if k in InviteToken.__dataclass_fields__})

        if invite.revoked:
            return False, invite, "revoked"

        if invite.single_use and invite.redeemed:
            return False, invite, "already_redeemed"

        now = datetime.now(UTC)
        expires = datetime.fromisoformat(invite.expires_at)
        if now > expires:
            return False, invite, "expired"

        return True, invite, "valid"

    return False, None, "not_found"


def redeem_token(token: str, redeemed_by: str = "") -> tuple[bool, str]:
    """
    Mark a token as redeemed.

    Returns (success, reason).
    """
    valid, invite, reason = validate_token(token)
    if not valid:
        return False, reason

    invites = _load_invites()
    now = datetime.now(UTC).isoformat()
    for inv_dict in invites:
        if inv_dict["token"] == token:
            inv_dict["redeemed"] = True
            inv_dict["redeemed_at"] = now
            inv_dict["redeemed_by"] = redeemed_by
            break

    _save_invites(invites)
    return True, "redeemed"


def revoke_token(token: str) -> tuple[bool, str]:
    """Revoke an invite token. Returns (success, reason)."""
    invites = _load_invites()
    for inv_dict in invites:
        if inv_dict["token"] == token:
            inv_dict["revoked"] = True
            _save_invites(invites)
            return True, "revoked"
    return False, "not_found"


def list_tokens(*, include_expired: bool = False) -> list[InviteToken]:
    """List all invite tokens, optionally including expired ones."""
    invites = _load_invites()
    now = datetime.now(UTC)
    result = []
    for inv_dict in invites:
        invite = InviteToken(**{k: v for k, v in inv_dict.items() if k in InviteToken.__dataclass_fields__})
        if not include_expired:
            expires = datetime.fromisoformat(invite.expires_at)
            if now > expires and not invite.redeemed:
                continue
        result.append(invite)
    return result
