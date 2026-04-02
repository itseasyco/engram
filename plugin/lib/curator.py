"""
Curator engine orchestrator.

Runs the 12-step scheduled maintenance cycle:
 1. Process inbox           (ENHANCED: entity extraction on ingest)
 2. Mycelium consolidation  (unchanged)
 3. Entity extraction       (NEW: batch process unlinked notes)
 4. Graph DB sync           (NEW: vault-to-Neo4j CQRS sync)
 5. Wikilink weaving        (ENHANCED: entity-aware linking)
 6. Relationship inference  (NEW: typed edges + index rebuild)
 7. Staleness scan          (unchanged)
 8. Conflict resolution     (unchanged)
 9. Schema enforcement      (ENHANCED: person/org schemas)
10. Cross-ref intelligence  (NEW: pattern detection + reports)
11. Index regeneration      (ENHANCED: orgs + goals)
12. Health report           (ENHANCED: entity + relationship metrics)
"""

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .consolidation import run_consolidation
from .conflict_resolver import resolve_conflicts
from .cross_reference import generate_intelligence_report
from .entity_extractor import extract_entities_batch
from .entity_linker import link_entities_batch
from .health_reporter import generate_health_report
from .inbox_processor import process_inbox
from .index_generator import regenerate_indexes
from .knowledge_gaps import detect_knowledge_gaps
from .relationship_graph import rebuild_index as rebuild_relationship_index
from .review_queue import write_review_queue
from .schema_enforcer import enforce_schema
from .staleness import scan_staleness
from .wikilink_weaver import weave_wikilinks
from .graph_db import get_graph_db
from .graph_sync import sync_vault_to_graph
from .deal_tracker import run_deal_tracking
from .opportunity_scorer import score_all_active_relationships
from .graph_mycelium import run_full_mycelium_cycle

logger = logging.getLogger("curator")


# ---------------------------------------------------------------------------
# Heartbeat
# ---------------------------------------------------------------------------

def _write_heartbeat(vault_path: Path, status: str, cycle_duration: float, notes_processed: int):
    """Write the .curator-heartbeat.json file."""
    heartbeat_path = vault_path / ".curator-heartbeat.json"
    now = datetime.now(timezone.utc)

    heartbeat = {
        "last_seen": now.isoformat(),
        "status": status,
        "cycle_duration_seconds": round(cycle_duration, 1),
        "notes_processed": notes_processed,
        "next_cycle": "",  # Populated by cron scheduler
        "missed_heartbeats": 0,
    }

    # Preserve outage_log from previous heartbeat
    if heartbeat_path.exists():
        try:
            prev = json.loads(heartbeat_path.read_text(encoding="utf-8"))
            heartbeat["outage_log"] = prev.get("outage_log", [])
        except (json.JSONDecodeError, IOError):
            heartbeat["outage_log"] = []
    else:
        heartbeat["outage_log"] = []

    heartbeat_path.write_text(
        json.dumps(heartbeat, indent=2),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Main cycle
# ---------------------------------------------------------------------------

def run_curator_cycle(
    vault_path: Optional[str] = None,
    dry_run: bool = True,
    steps: Optional[list] = None,
) -> dict:
    """
    Run the full curator maintenance cycle.

    Args:
        vault_path: root of the Obsidian vault.
        dry_run: if True, no mutations.
        steps: optional list of step names to run (default: all).
            Valid: inbox, consolidation, entities, graph_sync, wikilinks,
                   relationships, staleness, conflicts, schema, intelligence,
                   indexes, health

    Returns:
        dict with per-step results and overall timing.
    """
    if vault_path is None:
        vault_path = os.environ.get(
            "LACP_OBSIDIAN_VAULT",
            os.path.expanduser("~/obsidian/vault"),
        )

    vault = Path(vault_path)
    if not vault.exists():
        return {"error": "vault_not_found", "path": str(vault)}

    all_steps = [
        "inbox", "consolidation", "entities", "graph_sync", "wikilinks",
        "relationships", "staleness", "conflicts", "schema",
        "intelligence", "deals", "indexes", "health",
    ]
    if steps is None:
        steps = all_steps

    results = {}
    cycle_start = time.monotonic()
    total_processed = 0

    # Step 1: Process inbox
    if "inbox" in steps:
        logger.info("Step 1/13: Processing inbox...")
        try:
            inbox_result = process_inbox(str(vault), dry_run=dry_run)
            results["inbox"] = inbox_result
            total_processed += inbox_result.get("processed", 0)
            logger.info(
                "Inbox: processed=%d promoted=%d held=%d",
                inbox_result["processed"],
                inbox_result["promoted"],
                inbox_result["held"],
            )
        except Exception as exc:
            logger.error("Inbox processing failed: %s", exc)
            results["inbox"] = {"error": str(exc)}

    # Step 2: Mycelium consolidation
    if "consolidation" in steps:
        logger.info("Step 2/13: Running mycelium consolidation...")
        try:
            consolidation_result = run_consolidation(
                vault_path=str(vault),
                apply=not dry_run,
                dry_run=dry_run,
            )
            results["consolidation"] = consolidation_result
            logger.info(
                "Consolidation: pruned=%s healed=%s reinforced=%s",
                consolidation_result.get("pruned", 0),
                consolidation_result.get("healed_count", 0),
                consolidation_result.get("reinforced_count", 0),
            )
            # Run graph-native mycelium if available
            try:
                db = get_graph_db()
                if db.is_available() and not dry_run:
                    mycelium_result = run_full_mycelium_cycle(db)
                    results["graph_mycelium"] = mycelium_result
            except Exception as exc:
                logger.debug("Graph mycelium skipped: %s", exc)
        except Exception as exc:
            logger.error("Consolidation failed: %s", exc)
            results["consolidation"] = {"error": str(exc)}

    # Step 3: Entity extraction (NEW)
    if "entities" in steps:
        logger.info("Step 3/13: Extracting entities...")
        try:
            entity_result = extract_entities_batch(
                vault_path=str(vault),
                dry_run=dry_run,
                use_agent=False,  # Heuristic for cron; agent extraction on ingest
            )
            results["entities"] = entity_result
            logger.info(
                "Entities: processed=%d found=%d",
                entity_result.get("processed", 0),
                entity_result.get("entities_found", 0),
            )
        except Exception as exc:
            logger.error("Entity extraction failed: %s", exc)
            results["entities"] = {"error": str(exc)}

    # Step 4: Graph DB sync (NEW)
    if "graph_sync" in steps:
        logger.info("Step 4/13: Syncing vault to graph DB...")
        try:
            db = get_graph_db()
            if db.is_available():
                sync_result = sync_vault_to_graph(db, str(vault), dry_run=dry_run)
                results["graph_sync"] = sync_result
                logger.info(
                    "Graph sync: nodes=%d edges=%d",
                    sync_result.get("nodes_upserted", 0),
                    sync_result.get("edges_upserted", 0),
                )
            else:
                logger.warning("Graph DB unavailable — skipping sync")
                results["graph_sync"] = {"skipped": True, "reason": "graph_db_unavailable"}
        except Exception as exc:
            logger.error("Graph DB sync failed: %s", exc)
            results["graph_sync"] = {"error": str(exc)}

    # Step 5: Weave wikilinks (includes entity links)
    if "wikilinks" in steps:
        logger.info("Step 5/13: Weaving wikilinks...")
        try:
            wikilink_result = weave_wikilinks(
                vault_path=str(vault),
                dry_run=dry_run,
            )
            results["wikilinks"] = wikilink_result
            logger.info(
                "Wikilinks: added=%d removed=%d",
                wikilink_result["links_added"],
                wikilink_result["links_removed"],
            )
        except Exception as exc:
            logger.error("Wikilink weaving failed: %s", exc)
            results["wikilinks"] = {"error": str(exc)}

    # Step 6: Relationship inference (NEW)
    if "relationships" in steps:
        logger.info("Step 6/13: Rebuilding relationship index...")
        try:
            rel_result = rebuild_relationship_index(
                vault_path=str(vault),
                dry_run=dry_run,
            )
            results["relationships"] = rel_result
            logger.info(
                "Relationships: entities=%d edges=%d",
                rel_result.get("entities_found", 0),
                rel_result.get("edges_found", 0),
            )
        except Exception as exc:
            logger.error("Relationship index rebuild failed: %s", exc)
            results["relationships"] = {"error": str(exc)}

        # Also run entity linking batch
        try:
            link_result = link_entities_batch(
                vault_path=str(vault),
                dry_run=dry_run,
            )
            results["entity_links"] = link_result
            logger.info(
                "Entity links: processed=%d added=%d",
                link_result.get("processed", 0),
                link_result.get("links_added", 0),
            )
        except Exception as exc:
            logger.error("Entity linking failed: %s", exc)
            results["entity_links"] = {"error": str(exc)}

    # Step 7: Staleness scan
    if "staleness" in steps:
        logger.info("Step 7/13: Scanning staleness...")
        try:
            staleness_result = scan_staleness(
                vault_path=str(vault),
                dry_run=dry_run,
            )
            results["staleness"] = staleness_result
            logger.info(
                "Staleness: scanned=%d stale=%d review=%d",
                staleness_result.get("total_scanned", 0),
                len(staleness_result.get("flagged_stale", [])),
                len(staleness_result.get("moved_to_review", [])),
            )
        except Exception as exc:
            logger.error("Staleness scan failed: %s", exc)
            results["staleness"] = {"error": str(exc)}

    # Step 8: Conflict resolution
    if "conflicts" in steps:
        logger.info("Step 8/13: Resolving conflicts...")
        try:
            conflict_result = resolve_conflicts(
                vault_path=str(vault),
                dry_run=dry_run,
            )
            results["conflicts"] = conflict_result
            logger.info(
                "Conflicts: found=%d merged=%d escalated=%d",
                conflict_result["found"],
                conflict_result["auto_merged"],
                conflict_result["escalated"],
            )
        except Exception as exc:
            logger.error("Conflict resolution failed: %s", exc)
            results["conflicts"] = {"error": str(exc)}

    # Step 9: Schema enforcement
    if "schema" in steps:
        logger.info("Step 9/13: Enforcing schema...")
        try:
            schema_result = enforce_schema(
                vault_path=str(vault),
                dry_run=dry_run,
            )
            results["schema"] = schema_result
            logger.info(
                "Schema: total=%d compliant=%d fixed=%d malformed=%d",
                schema_result.get("total", 0),
                schema_result.get("compliant", 0),
                schema_result.get("fixed", 0),
                schema_result.get("malformed", 0),
            )
        except Exception as exc:
            logger.error("Schema enforcement failed: %s", exc)
            results["schema"] = {"error": str(exc)}

    # Step 10: Cross-reference intelligence (NEW)
    if "intelligence" in steps:
        logger.info("Step 10/13: Running cross-reference intelligence...")
        try:
            intel_result = generate_intelligence_report(
                vault_path=str(vault),
                dry_run=dry_run,
            )
            results["intelligence"] = intel_result
            logger.info(
                "Intelligence: findings=%d high_priority=%d",
                intel_result.get("total_findings", 0),
                intel_result.get("high_priority", 0),
            )
        except Exception as exc:
            logger.error("Intelligence report failed: %s", exc)
            results["intelligence"] = {"error": str(exc)}

    # Step 11: Deal tracking + opportunity scoring (Phase 3)
    if "deals" in steps:
        logger.info("Step 11/13: Running deal tracking...")
        try:
            db = get_graph_db()
            if db and db.is_available():
                deal_result = run_deal_tracking(db, dry_run=dry_run)
                results["deals"] = deal_result

                scores = score_all_active_relationships(db)
                results["opportunity_scores"] = {
                    "relationships_scored": len(scores),
                    "top_5": scores[:5],
                }
                logger.info(
                    "Deals: %d transitions, %d stale, %d overdue. %d relationships scored.",
                    len(deal_result.get("transitions", [])),
                    len(deal_result.get("stale_deals", [])),
                    len(deal_result.get("overdue_actions", [])),
                    len(scores),
                )
            else:
                results["deals"] = {"skipped": True, "reason": "graph_db_unavailable"}
        except Exception as exc:
            logger.error("Deal tracking failed: %s", exc)
            results["deals"] = {"error": str(exc)}

    # Step 12: Index update
    if "indexes" in steps:
        logger.info("Step 12/13: Regenerating indexes...")
        try:
            index_result = regenerate_indexes(
                vault_path=str(vault),
                dry_run=dry_run,
            )
            results["indexes"] = index_result
            logger.info(
                "Indexes: folders=%d total_notes=%d",
                len(index_result.get("folder_indexes_updated", [])),
                index_result.get("total_notes", 0),
            )
        except Exception as exc:
            logger.error("Index regeneration failed: %s", exc)
            results["indexes"] = {"error": str(exc)}

    # Step 12: Health report
    cycle_duration = time.monotonic() - cycle_start

    if "health" in steps:
        logger.info("Step 13/13: Generating health report...")
        try:
            health_result = generate_health_report(
                vault_path=str(vault),
                dry_run=dry_run,
                cycle_duration_seconds=cycle_duration,
                cycle_results=results,
            )
            results["health"] = health_result
            logger.info(
                "Health: score=%d status=%s",
                health_result.get("health_score", 0),
                health_result.get("health_status", "unknown"),
            )
        except Exception as exc:
            logger.error("Health report failed: %s", exc)
            results["health"] = {"error": str(exc)}

    # Write heartbeat (even in dry_run, heartbeat is always written)
    if not dry_run:
        health_status = results.get("health", {}).get("health_status", "unknown")
        _write_heartbeat(vault, health_status, cycle_duration, total_processed)

    # Also generate review queue and gap report (bonus steps from consolidation)
    if "consolidation" in steps:
        try:
            write_review_queue(vault_path=str(vault))
        except Exception:
            pass
        try:
            from .knowledge_gaps import write_gap_report
            write_gap_report(vault_path=str(vault))
        except Exception:
            pass

    return {
        "cycle_duration_seconds": round(cycle_duration, 2),
        "dry_run": dry_run,
        "steps_run": steps,
        "results": results,
    }
