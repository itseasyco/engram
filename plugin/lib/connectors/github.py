"""
GitHub connector (Tier 2 -- First-party).

Handles GitHub webhook events: pull_request, push, deployment, release.
Verifies webhook secret, filters by repo allowlist, and transforms
events into structured vault notes.

Config keys:
  - webhook_secret: GitHub webhook secret for HMAC-SHA256 verification
  - repos: list of "owner/repo" strings to accept (empty = accept all)
  - events: list of event types to process (default: all supported)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from .base import Connector, ConnectorStatus, RawData, VaultNote
from .trust import verify_hmac_signature


SUPPORTED_EVENTS = {"pull_request", "push", "deployment", "release", "issues"}


class GithubConnector(Connector):
    """Receive and process GitHub webhook events."""

    type = "github"

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self._webhook_secret: str = self.connector_config.get("webhook_secret", "")
        self._repos: list[str] = self.connector_config.get("repos", [])
        self._events: set[str] = set(
            self.connector_config.get("events", list(SUPPORTED_EVENTS))
        )
        self._processed_deliveries: set[str] = set()

    def authenticate(self) -> bool:
        """GitHub connector requires a webhook secret."""
        return bool(self._webhook_secret)

    def verify_webhook(self, body: bytes, signature: str) -> bool:
        """Verify GitHub webhook HMAC-SHA256 signature."""
        return verify_hmac_signature(
            payload_body=body,
            signature_header=signature,
            secret=self._webhook_secret,
            algorithm="sha256",
            prefix="sha256=",
        )

    def receive(self, payload: dict[str, Any]) -> RawData:
        """Accept a GitHub webhook payload."""
        event_type = payload.get("_event_type", "unknown")
        delivery_id = payload.get("_delivery_id", "")

        # Extract repo info
        repo = payload.get("repository", {})
        repo_full_name = repo.get("full_name", "unknown/unknown")

        # Filter by repo allowlist
        if self._repos and repo_full_name not in self._repos:
            raise ValueError(f"Repo {repo_full_name} not in allowlist")

        # Filter by event type
        if event_type not in self._events:
            raise ValueError(f"Event type {event_type} not in accepted events")

        # Deduplicate by delivery ID
        if delivery_id and delivery_id in self._processed_deliveries:
            raise ValueError(f"Duplicate delivery: {delivery_id}")
        if delivery_id:
            self._processed_deliveries.add(delivery_id)
            # Keep set bounded
            if len(self._processed_deliveries) > 10000:
                self._processed_deliveries = set(
                    list(self._processed_deliveries)[-5000:]
                )

        sender = payload.get("sender", {}).get("login", "unknown")

        return RawData(
            source_id=f"{event_type}-{delivery_id or repo_full_name}",
            payload=payload,
            sender=sender,
            metadata={"event_type": event_type, "repo": repo_full_name},
        )

    def transform(self, raw_data: RawData) -> VaultNote:
        """Transform a GitHub event into a VaultNote."""
        event_type = raw_data.metadata.get("event_type", "unknown")
        repo = raw_data.metadata.get("repo", "")
        payload = raw_data.payload

        if event_type == "pull_request":
            return self._transform_pr(raw_data, payload, repo)
        elif event_type == "push":
            return self._transform_push(raw_data, payload, repo)
        elif event_type == "deployment":
            return self._transform_deployment(raw_data, payload, repo)
        elif event_type == "release":
            return self._transform_release(raw_data, payload, repo)
        elif event_type == "issues":
            return self._transform_issue(raw_data, payload, repo)
        else:
            return self._transform_generic(raw_data, payload, repo, event_type)

    def _transform_pr(
        self, raw: RawData, payload: dict, repo: str
    ) -> VaultNote:
        pr = payload.get("pull_request", {})
        action = payload.get("action", "unknown")
        number = pr.get("number", "?")
        title = pr.get("title", "Untitled PR")
        author = pr.get("user", {}).get("login", "unknown")
        body_text = pr.get("body", "") or ""
        state = pr.get("state", "unknown")
        merged = pr.get("merged", False)
        base = pr.get("base", {}).get("ref", "?")
        head = pr.get("head", {}).get("ref", "?")
        url = pr.get("html_url", "")
        additions = pr.get("additions", 0)
        deletions = pr.get("deletions", 0)
        changed_files = pr.get("changed_files", 0)

        status_label = "merged" if merged else state

        note_body = f"""## PR #{number}: {title}

**Repository:** {repo}
**Author:** @{author}
**Action:** {action}
**Status:** {status_label}
**Branch:** `{head}` -> `{base}`
**Changes:** +{additions} -{deletions} across {changed_files} files

{f"**URL:** [{url}]({url})" if url else ""}

### Description

{body_text[:2000] if body_text else "(no description)"}
"""

        tags = ["github", "pull-request", action]
        if merged:
            tags.append("merged")

        return VaultNote(
            title=f"PR #{number}: {title} ({repo})",
            body=note_body,
            source_connector=self.id,
            source_type=self.type,
            source_id=f"pr-{repo}-{number}-{action}",
            trust_level=self.trust_level,
            landing_zone=self.landing_zone,
            tags=tags,
            category="pull-request",
            author=author,
            source_url=url,
        )

    def _transform_push(
        self, raw: RawData, payload: dict, repo: str
    ) -> VaultNote:
        ref = payload.get("ref", "unknown")
        branch = ref.replace("refs/heads/", "")
        commits = payload.get("commits", [])
        pusher = payload.get("pusher", {}).get("name", "unknown")
        compare = payload.get("compare", "")

        commit_lines = []
        for c in commits[:20]:
            sha = c.get("id", "")[:7]
            msg = c.get("message", "").split("\n")[0][:80]
            commit_lines.append(f"- `{sha}` {msg}")

        note_body = f"""## Push to {repo}

**Branch:** `{branch}`
**Pusher:** @{pusher}
**Commits:** {len(commits)}
{f"**Compare:** [{compare}]({compare})" if compare else ""}

### Commits

{chr(10).join(commit_lines) if commit_lines else "(no commits)"}
"""

        return VaultNote(
            title=f"Push: {branch} ({repo}) - {len(commits)} commits",
            body=note_body,
            source_connector=self.id,
            source_type=self.type,
            source_id=f"push-{repo}-{branch}-{len(commits)}",
            trust_level=self.trust_level,
            landing_zone=self.landing_zone,
            tags=["github", "push", branch],
            category="push",
            author=pusher,
            source_url=compare,
        )

    def _transform_deployment(
        self, raw: RawData, payload: dict, repo: str
    ) -> VaultNote:
        deployment = payload.get("deployment", {})
        env = deployment.get("environment", "unknown")
        ref = deployment.get("ref", "unknown")
        creator = deployment.get("creator", {}).get("login", "unknown")
        desc = deployment.get("description", "") or ""

        note_body = f"""## Deployment: {repo}

**Environment:** {env}
**Ref:** `{ref}`
**Creator:** @{creator}
**Description:** {desc or "(none)"}
"""

        return VaultNote(
            title=f"Deploy: {repo} -> {env}",
            body=note_body,
            source_connector=self.id,
            source_type=self.type,
            source_id=f"deploy-{repo}-{env}-{ref}",
            trust_level=self.trust_level,
            landing_zone=self.landing_zone,
            tags=["github", "deployment", env],
            category="deployment",
            author=creator,
        )

    def _transform_release(
        self, raw: RawData, payload: dict, repo: str
    ) -> VaultNote:
        release = payload.get("release", {})
        tag = release.get("tag_name", "unknown")
        name = release.get("name", tag)
        author = release.get("author", {}).get("login", "unknown")
        body_text = release.get("body", "") or ""
        url = release.get("html_url", "")
        prerelease = release.get("prerelease", False)

        note_body = f"""## Release: {name}

**Repository:** {repo}
**Tag:** `{tag}`
**Author:** @{author}
**Pre-release:** {"yes" if prerelease else "no"}
{f"**URL:** [{url}]({url})" if url else ""}

### Release Notes

{body_text[:3000] if body_text else "(no release notes)"}
"""

        return VaultNote(
            title=f"Release: {name} ({repo})",
            body=note_body,
            source_connector=self.id,
            source_type=self.type,
            source_id=f"release-{repo}-{tag}",
            trust_level=self.trust_level,
            landing_zone=self.landing_zone,
            tags=["github", "release", tag],
            category="release",
            author=author,
            source_url=url,
        )

    def _transform_issue(
        self, raw: RawData, payload: dict, repo: str
    ) -> VaultNote:
        issue = payload.get("issue", {})
        action = payload.get("action", "unknown")
        number = issue.get("number", "?")
        title = issue.get("title", "Untitled")
        author = issue.get("user", {}).get("login", "unknown")
        body_text = issue.get("body", "") or ""
        labels = [lb.get("name", "") for lb in issue.get("labels", [])]
        url = issue.get("html_url", "")

        note_body = f"""## Issue #{number}: {title}

**Repository:** {repo}
**Author:** @{author}
**Action:** {action}
**Labels:** {", ".join(labels) if labels else "(none)"}
{f"**URL:** [{url}]({url})" if url else ""}

### Description

{body_text[:2000] if body_text else "(no description)"}
"""

        return VaultNote(
            title=f"Issue #{number}: {title} ({repo})",
            body=note_body,
            source_connector=self.id,
            source_type=self.type,
            source_id=f"issue-{repo}-{number}-{action}",
            trust_level=self.trust_level,
            landing_zone=self.landing_zone,
            tags=["github", "issue", action] + labels,
            category="issue",
            author=author,
            source_url=url,
        )

    def _transform_generic(
        self, raw: RawData, payload: dict, repo: str, event_type: str
    ) -> VaultNote:
        return VaultNote(
            title=f"GitHub: {event_type} ({repo})",
            body=f"## {event_type}\n\n```json\n{json.dumps(payload, indent=2, default=str)[:3000]}\n```",
            source_connector=self.id,
            source_type=self.type,
            source_id=raw.source_id,
            trust_level=self.trust_level,
            landing_zone=self.landing_zone,
            tags=["github", event_type],
            category=event_type,
        )

    def health_check(self) -> ConnectorStatus:
        status = self.base_status(healthy=bool(self._webhook_secret))
        status.extra["repos"] = self._repos
        status.extra["events"] = list(self._events)
        status.extra["processed_deliveries"] = len(self._processed_deliveries)
        return status
