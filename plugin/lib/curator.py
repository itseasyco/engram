"""
Curator engine orchestrator.

Runs the 8-step scheduled maintenance cycle:
1. Process inbox
2. Run mycelium consolidation
3. Weave wikilinks
4. Staleness scan
5. Conflict resolution
6. Schema enforcement
7. Index update
8. Health report
"""

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from plugin.lib.consolidation import run_consolidation
from plugin.lib.conflict_resolver import resolve_conflicts
from plugin.lib.health_reporter import generate_health_report
from plugin.lib.inbox_processor import process_inbox
from plugin.lib.index_generator import regenerate_indexes
from plugin.lib.knowledge_gaps import detect_knowledge_gaps
from plugin.lib.review_queue import write_review_queue
from plugin.lib.schema_enforcer import enforce_schema
from plugin.lib.staleness import scan_staleness
from plugin.lib.wikilink_weaver import weave_wikilinks

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
            Valid: inbox, consolidation, wikilinks, staleness, conflicts,
                   schema, indexes, health

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
        "inbox", "consolidation", "wikilinks", "staleness",
        "conflicts", "schema", "indexes", "health",
    ]
    if steps is None:
        steps = all_steps

    results = {}
    cycle_start = time.monotonic()
    total_processed = 0

    # Step 1: Process inbox
    if "inbox" in steps:
        logger.info("Step 1/8: Processing inbox...")
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
        logger.info("Step 2/8: Running mycelium consolidation...")
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
        except Exception as exc:
            logger.error("Consolidation failed: %s", exc)
            results["consolidation"] = {"error": str(exc)}

    # Step 3: Weave wikilinks
    if "wikilinks" in steps:
        logger.info("Step 3/8: Weaving wikilinks...")
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

    # Step 4: Staleness scan
    if "staleness" in steps:
        logger.info("Step 4/8: Scanning staleness...")
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

    # Step 5: Conflict resolution
    if "conflicts" in steps:
        logger.info("Step 5/8: Resolving conflicts...")
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

    # Step 6: Schema enforcement
    if "schema" in steps:
        logger.info("Step 6/8: Enforcing schema...")
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

    # Step 7: Index update
    if "indexes" in steps:
        logger.info("Step 7/8: Regenerating indexes...")
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

    # Step 8: Health report
    cycle_duration = time.monotonic() - cycle_start

    if "health" in steps:
        logger.info("Step 8/8: Generating health report...")
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
            from plugin.lib.knowledge_gaps import write_gap_report
            write_gap_report(vault_path=str(vault))
        except Exception:
            pass

    return {
        "cycle_duration_seconds": round(cycle_duration, 2),
        "dry_run": dry_run,
        "steps_run": steps,
        "results": results,
    }
