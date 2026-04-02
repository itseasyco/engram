"""Tests for vault-to-graph sync."""

import pytest
from pathlib import Path


class TestNoteParser:
    """Test parsing vault notes into graph nodes/edges."""

    def test_parse_person_note(self, sample_person_note):
        from lib.graph_sync import parse_vault_note
        node, edges, extra = parse_vault_note(sample_person_note)
        assert node["label"] == "Person"
        assert node["properties"]["name"] == "Kate Levchuk"
        assert node["properties"]["slug"] == "kate-levchuk"
        assert node["properties"]["org"] == "Andreessen Horowitz"
        assert any(e["type"] == "WORKS_AT" for e in edges)

    def test_parse_org_note(self, sample_org_note):
        from lib.graph_sync import parse_vault_note
        node, edges, extra = parse_vault_note(sample_org_note)
        assert node["label"] == "Organization"
        assert node["properties"]["name"] == "Andreessen Horowitz"
        assert any(e["type"] == "PORTFOLIO_COMPANY_OF" for e in edges)

    def test_parse_goal_note(self, sample_goal_note):
        from lib.graph_sync import parse_vault_note
        node, edges, extra = parse_vault_note(sample_goal_note)
        assert node["label"] == "Goal"
        assert node["properties"]["status"] == "active"
        assert node["properties"]["priority"] == "critical"

    def test_parse_extracts_wikilinks_as_edges(self, sample_person_note):
        from lib.graph_sync import parse_vault_note
        node, edges, extra = parse_vault_note(sample_person_note)
        targets = {e["target_name"] for e in edges}
        assert "Andreessen Horowitz" in targets

    def test_parse_note_without_frontmatter(self, temp_vault):
        from lib.graph_sync import parse_vault_note
        note = temp_vault / "random-note.md"
        note.write_text("# Just a note\n\nSome content about [[Something]].\n")
        node, edges, extra = parse_vault_note(note)
        assert node["label"] == "Note"
        assert any(e["target_name"] == "Something" for e in edges)

    def test_label_inferred_from_folder_path(self, temp_vault):
        """Notes in meetings/ should be labeled Meeting even without type frontmatter."""
        from lib.graph_sync import parse_vault_note
        (temp_vault / "meetings" / "investors").mkdir(parents=True, exist_ok=True)
        note = temp_vault / "meetings" / "investors" / "2026-01-15-meeting.md"
        note.write_text("---\ntitle: Test Meeting\ncategory: inbox\n---\n\n# Test Meeting\n")
        node, edges, extra = parse_vault_note(note, vault_root=temp_vault)
        assert node["label"] == "Meeting"

    def test_frontmatter_type_takes_priority_over_folder(self, temp_vault):
        """Frontmatter type should override folder-based label inference."""
        from lib.graph_sync import parse_vault_note
        note = temp_vault / "meetings" / "investors" / "special-person.md"
        (temp_vault / "meetings" / "investors").mkdir(parents=True, exist_ok=True)
        note.write_text("---\ntitle: Special Person\ntype: person\n---\n\n# Special\n")
        node, edges, extra = parse_vault_note(note, vault_root=temp_vault)
        assert node["label"] == "Person"

    def test_meeting_extracts_attendees(self, temp_vault):
        """Meeting notes should extract attendees as Person nodes."""
        from lib.graph_sync import parse_vault_note
        (temp_vault / "meetings" / "investors").mkdir(parents=True, exist_ok=True)
        note = temp_vault / "meetings" / "investors" / "2026-01-15-test.md"
        note.write_text(
            "---\ntitle: Test Meeting\ncategory: inbox\n---\n\n"
            "# Test Meeting\n\n"
            "**Date:** 2026-01-15  \n"
            "**Attendees:** Alice Smith, Bob Jones, Niko's Notetaker  \n\n"
            "## Notes\nSome discussion.\n"
        )
        node, edges, extra = parse_vault_note(note, vault_root=temp_vault)
        assert node["label"] == "Meeting"
        assert node["properties"]["date"] == "2026-01-15"
        # Should have 2 attendees (Notetaker filtered out)
        assert len(extra) == 2
        assert extra[0]["label"] == "Person"
        assert extra[0]["properties"]["name"] == "Alice Smith"
        # Should have ATTENDED edges
        attended = [e for e in edges if e["type"] == "ATTENDED"]
        assert len(attended) == 2


class TestVaultScan:
    """Test scanning the full vault."""

    def test_scan_vault_finds_all_notes(self, temp_vault, sample_person_note, sample_org_note, sample_goal_note):
        from lib.graph_sync import scan_vault
        nodes, edges = scan_vault(str(temp_vault))
        assert len(nodes) >= 3  # person + org + goal

    def test_scan_vault_skips_metadata(self, temp_vault):
        from lib.graph_sync import scan_vault
        (temp_vault / "_metadata" / "something.md").write_text("---\ntitle: meta\n---\n")
        nodes, edges = scan_vault(str(temp_vault))
        meta_nodes = [n for n in nodes if "_metadata" in n.get("properties", {}).get("path", "")]
        assert len(meta_nodes) == 0


class TestGraphUpsert:
    """Test upserting parsed nodes/edges to Neo4j."""

    def test_upsert_person_node(self):
        from lib.graph_db import GraphDB
        from lib.graph_sync import upsert_node

        db = GraphDB()
        if not db.is_available():
            pytest.skip("Neo4j not available")

        node = {
            "label": "Person",
            "properties": {
                "slug": "test-person",
                "name": "Test Person",
                "org": "Test Org",
            },
        }
        upsert_node(db, node)
        result = db.execute(
            "MATCH (p:Person {slug: 'test-person'}) RETURN p.name AS name"
        )
        assert result[0]["name"] == "Test Person"

        # Cleanup
        db.execute_write("MATCH (p:Person {slug: 'test-person'}) DELETE p")

    def test_upsert_is_idempotent(self):
        from lib.graph_db import GraphDB
        from lib.graph_sync import upsert_node

        db = GraphDB()
        if not db.is_available():
            pytest.skip("Neo4j not available")

        node = {
            "label": "Person",
            "properties": {"slug": "idempotent-test", "name": "Same Person"},
        }
        upsert_node(db, node)
        upsert_node(db, node)
        result = db.execute(
            "MATCH (p:Person {slug: 'idempotent-test'}) RETURN count(p) AS c"
        )
        assert result[0]["c"] == 1

        # Cleanup
        db.execute_write("MATCH (p:Person {slug: 'idempotent-test'}) DELETE p")

    def test_upsert_edge(self):
        from lib.graph_db import GraphDB
        from lib.graph_sync import upsert_node, upsert_edge

        db = GraphDB()
        if not db.is_available():
            pytest.skip("Neo4j not available")

        # Create two nodes
        upsert_node(db, {"label": "Person", "properties": {"slug": "edge-test-person", "name": "EP"}})
        upsert_node(db, {"label": "Organization", "properties": {"slug": "edge-test-org", "name": "EO"}})

        # Create edge
        upsert_edge(db, {
            "source_slug": "edge-test-person",
            "source_label": "Person",
            "target_slug": "edge-test-org",
            "target_label": "Organization",
            "type": "WORKS_AT",
            "properties": {"role": "Engineer"},
        })

        result = db.execute(
            "MATCH (p:Person {slug: 'edge-test-person'})-[r:WORKS_AT]->(o:Organization) RETURN o.name AS org"
        )
        assert result[0]["org"] == "EO"

        # Cleanup
        db.execute_write("MATCH (n) WHERE n.slug IN ['edge-test-person', 'edge-test-org'] DETACH DELETE n")


class TestFullSync:
    """Test end-to-end vault-to-graph sync."""

    def test_sync_vault_to_graph(self, temp_vault, sample_person_note, sample_org_note, sample_goal_note):
        from lib.graph_db import GraphDB
        from lib.graph_sync import sync_vault_to_graph

        db = GraphDB()
        if not db.is_available():
            pytest.skip("Neo4j not available")

        result = sync_vault_to_graph(db, str(temp_vault))
        assert result["nodes_upserted"] >= 3
        assert result["edges_upserted"] >= 1

        # Cleanup
        db.execute_write("MATCH (n) WHERE n.slug IS NOT NULL DETACH DELETE n")
