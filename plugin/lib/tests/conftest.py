"""Shared fixtures for engram lib tests."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def temp_vault():
    """Create a temporary vault with basic structure."""
    with tempfile.TemporaryDirectory() as tmpdir:
        vault = Path(tmpdir)
        # Create minimal vault structure
        (vault / "people" / "investors").mkdir(parents=True)
        (vault / "people" / "team").mkdir(parents=True)
        (vault / "organizations").mkdir(parents=True)
        (vault / "strategy" / "goals").mkdir(parents=True)
        (vault / "meetings" / "investors").mkdir(parents=True)
        (vault / "_metadata").mkdir(parents=True)
        yield vault


@pytest.fixture
def neo4j_config(tmp_path):
    """Create a temporary Neo4j config pointing to test database."""
    config = {
        "bolt_url": os.environ.get("NEO4J_BOLT_URL", "bolt://localhost:7687"),
        "username": os.environ.get("NEO4J_USERNAME", "neo4j"),
        "password": os.environ.get("NEO4J_PASSWORD", "engram-dev"),
        "database": "neo4j",
        "max_connection_pool_size": 5,
        "connection_timeout": 5,
    }
    config_path = tmp_path / "neo4j-config.json"
    config_path.write_text(json.dumps(config))
    return config_path


@pytest.fixture
def sample_person_note(temp_vault):
    """Create a sample person note in the vault."""
    content = """---
title: "Kate Levchuk"
type: person
role: Partner
org: "Andreessen Horowitz"
category: investors
relationship_stage: active-conversation
last_contact: "2026-03-25"
---

# Kate Levchuk

Partner at [[Andreessen Horowitz]].

## Relationships
- works-at: [[Andreessen Horowitz]]
- met-with: [[Andrew Fisher]] (2026-03-25)
- discussed: compliance, stablecoin settlement
"""
    note_path = temp_vault / "people" / "investors" / "kate-levchuk.md"
    note_path.write_text(content)
    return note_path


@pytest.fixture
def sample_org_note(temp_vault):
    """Create a sample organization note in the vault."""
    content = """---
title: "Andreessen Horowitz"
type: organization
sector: venture-capital
aliases: ["A16Z", "a16z"]
---

# Andreessen Horowitz

## Portfolio Companies
- [[Finix]]
- [[Alloy]]

## Relationships
- has-portfolio-company: [[Finix]]
- has-portfolio-company: [[Alloy]]
"""
    note_path = temp_vault / "organizations" / "andreessen-horowitz.md"
    note_path.write_text(content)
    return note_path


@pytest.fixture
def sample_goal_note(temp_vault):
    """Create a sample goal note in the vault."""
    content = """---
title: "Series A Fundraise"
type: goal
status: active
priority: critical
target_close: "2026-Q3"
scoring_signals:
  positive: ["investor enthusiasm", "warm intro", "portfolio overlap"]
  negative: ["ghosting", "concern about market"]
related_entities:
  - "[[Kate Levchuk]]"
  - "[[Andreessen Horowitz]]"
---

# Series A Fundraise
"""
    note_path = temp_vault / "strategy" / "goals" / "series-a-fundraise.md"
    note_path.write_text(content)
    return note_path


@pytest.fixture
def sample_meeting_note(temp_vault):
    """Create a sample meeting note in the vault."""
    content = """---
title: "2026-03-25 Investor Call — Kate Levchuk"
category: inbox
---

# Investor Call — Kate Levchuk

**Date:** 2026-03-25
**Duration:** 1800 seconds
**Attendees:** Andrew Fisher, Kate Levchuk, Niko Lemieux

## Notes
- Discussed Series A timeline and compliance roadmap
- Kate interested in stablecoin settlement layer
- Follow-up: send pitch deck v3

## Action Items
- [ ] Send updated pitch deck to Kate by Friday
- [ ] Schedule follow-up call for next week
"""
    (temp_vault / "meetings" / "investors").mkdir(parents=True, exist_ok=True)
    note_path = temp_vault / "meetings" / "investors" / "2026-03-25-investor-call-kate.md"
    note_path.write_text(content)
    return note_path


@pytest.fixture
def mock_graph_db():
    """Mock GraphDB that returns canned results for common queries."""
    db = MagicMock()
    db.is_available.return_value = True
    db.execute_read_only.return_value = []
    db.execute_write.return_value = None
    db.execute.return_value = []
    return db
