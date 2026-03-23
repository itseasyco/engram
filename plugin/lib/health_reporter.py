"""
Health reporter for the curator engine.

Computes graph health metrics (note count, orphan rate, staleness distribution,
link density, inbox size) and generates a health report written to
05_Inbox/curator-health-report.md.
"""

import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from plugin.lib.consolidation import _load_vault_notes, _parse_frontmatter, _extract_links
from plugin.lib.staleness import compute_staleness_score, classify_staleness


# ---------------------------------------------------------------------------
# Metrics computation
# ---------------------------------------------------------------------------

def compute_graph_metrics(vault_path: Path) -> dict:
    """
    Compute comprehensive graph health metrics.

    Returns:
        dict with note_count, link_count, avg_links_per_note, orphan_count,
        orphan_rate, staleness_distribution, inbox_pending, category_counts,
        broken_link_count.
    """
    notes = {}  # stem -> {links, tags, path, rel_path, fm}
    all_links = []
    broken_links = 0
    category_counts = defaultdict(int)

    for md_file in vault_path.rglob("*.md"):
        rel = md_file.relative_to(vault_path).as_posix()
        if rel.startswith(".obsidian/") or md_file.name == "index.md" or md_file.stem == "00_Index":
            continue

        try:
            content = md_file.read_text(encoding="utf-8")
        except (IOError, UnicodeDecodeError):
            continue

        fm = _parse_frontmatter(content)
        links = _extract_links(content)
        all_links.extend(links)

        category = fm.get("category", "uncategorized")
        if isinstance(category, str):
            category_counts[category] += 1

        notes[md_file.stem] = {
            "links": links,
            "fm": fm,
            "path": md_file,
            "rel_path": rel,
        }

    valid_stems = set(notes.keys())
    note_count = len(notes)

    # Link density
    link_count = len(all_links)
    avg_links = link_count / note_count if note_count > 0 else 0.0

    # Broken links
    for link in all_links:
        if link not in valid_stems:
            broken_links += 1

    # Orphan detection (notes with no incoming links)
    incoming = defaultdict(int)
    for stem, data in notes.items():
        for link in data["links"]:
            incoming[link] += 1

    orphan_count = sum(
        1 for stem in notes
        if incoming.get(stem, 0) == 0
        and not notes[stem]["rel_path"].startswith("05_Inbox/")
        and not notes[stem]["rel_path"].startswith("99_Archive/")
    )
    orphan_rate = orphan_count / note_count if note_count > 0 else 0.0

    # Staleness distribution
    now = datetime.now(timezone.utc)
    staleness_dist = defaultdict(int)
    for stem, data in notes.items():
        fm = data["fm"]
        if data["rel_path"].startswith("05_Inbox/") or data["rel_path"].startswith("99_Archive/"):
            continue
        last_traversed = fm.get("last_traversed", fm.get("updated", ""))
        traversal_count = fm.get("traversal_count", fm.get("count", 0))
        if not isinstance(traversal_count, int):
            try:
                traversal_count = int(traversal_count)
            except (ValueError, TypeError):
                traversal_count = 0
        score = compute_staleness_score(str(last_traversed), traversal_count, now=now)
        classification = classify_staleness(score)
        staleness_dist[classification] += 1

    # Inbox pending
    inbox_pending = 0
    inbox_dir = vault_path / "05_Inbox"
    if inbox_dir.exists():
        for queue_dir in inbox_dir.iterdir():
            if queue_dir.is_dir() and queue_dir.name.startswith("queue-"):
                inbox_pending += sum(
                    1 for f in queue_dir.glob("*.md") if f.name != "index.md"
                )

    return {
        "note_count": note_count,
        "link_count": link_count,
        "avg_links_per_note": round(avg_links, 2),
        "orphan_count": orphan_count,
        "orphan_rate": round(orphan_rate, 4),
        "staleness_distribution": dict(staleness_dist),
        "inbox_pending": inbox_pending,
        "category_counts": dict(category_counts),
        "broken_link_count": broken_links,
    }


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def generate_health_report(
    vault_path: Optional[str] = None,
    dry_run: bool = True,
    cycle_duration_seconds: float = 0.0,
    cycle_results: Optional[dict] = None,
) -> dict:
    """
    Generate and write the curator health report.

    Args:
        vault_path: root of the Obsidian vault.
        dry_run: if True, do not write the report file.
        cycle_duration_seconds: how long the curator cycle took.
        cycle_results: optional dict of results from each step.

    Returns:
        dict with metrics, report_path.
    """
    if vault_path is None:
        vault_path = os.environ.get(
            "LACP_OBSIDIAN_VAULT",
            os.path.expanduser("~/obsidian/vault"),
        )

    vault = Path(vault_path)
    if not vault.exists():
        return {"error": "vault_not_found", "path": str(vault)}

    metrics = compute_graph_metrics(vault)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Health score: composite
    # Target: orphan_rate < 0.03, avg_links >= 3, stale ratio < 0.05
    graph_notes = sum(metrics["staleness_distribution"].values()) or 1
    stale_count = (
        metrics["staleness_distribution"].get("stale", 0)
        + metrics["staleness_distribution"].get("review_needed", 0)
    )
    stale_ratio = stale_count / graph_notes

    health_score = 100
    if metrics["orphan_rate"] > 0.10:
        health_score -= 20
    elif metrics["orphan_rate"] > 0.03:
        health_score -= 10
    if metrics["avg_links_per_note"] < 1.0:
        health_score -= 20
    elif metrics["avg_links_per_note"] < 3.0:
        health_score -= 10
    if stale_ratio > 0.10:
        health_score -= 20
    elif stale_ratio > 0.05:
        health_score -= 10
    if metrics["broken_link_count"] > 10:
        health_score -= 10

    health_status = "healthy" if health_score >= 80 else "degraded" if health_score >= 60 else "unhealthy"

    lines = [
        "---",
        "type: health-report",
        f'generated: "{now}"',
        f"health_score: {health_score}",
        f"health_status: {health_status}",
        "---",
        "",
        "# Curator Health Report",
        "",
        f"Generated: {now}",
        f"Cycle duration: {cycle_duration_seconds:.1f}s",
        f"Health score: **{health_score}/100** ({health_status})",
        "",
        "## Graph Metrics",
        "",
        f"- Total notes: {metrics['note_count']}",
        f"- Total links: {metrics['link_count']}",
        f"- Avg links per note: {metrics['avg_links_per_note']}",
        f"- Orphan notes: {metrics['orphan_count']} ({metrics['orphan_rate']:.1%})",
        f"- Broken links: {metrics['broken_link_count']}",
        f"- Inbox pending: {metrics['inbox_pending']}",
        "",
        "## Staleness Distribution",
        "",
        "| Classification | Count |",
        "|---------------|-------|",
    ]

    for classification in ["active", "aging", "stale", "review_needed"]:
        count = metrics["staleness_distribution"].get(classification, 0)
        lines.append(f"| {classification} | {count} |")

    lines.append("")
    lines.append("## Category Breakdown")
    lines.append("")
    lines.append("| Category | Notes |")
    lines.append("|----------|-------|")

    for cat, count in sorted(metrics["category_counts"].items(), key=lambda x: x[1], reverse=True):
        lines.append(f"| {cat} | {count} |")

    # Cycle results summary
    if cycle_results:
        lines.append("")
        lines.append("## Cycle Summary")
        lines.append("")
        for step_name, step_result in cycle_results.items():
            if isinstance(step_result, dict):
                summary_parts = []
                for k, v in step_result.items():
                    if isinstance(v, (int, float, str, bool)):
                        summary_parts.append(f"{k}={v}")
                lines.append(f"- **{step_name}:** {', '.join(summary_parts[:5])}")
            else:
                lines.append(f"- **{step_name}:** {step_result}")

    lines.append("")

    report_content = "\n".join(lines)
    report_path = vault / "05_Inbox" / "curator-health-report.md"

    if not dry_run:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report_content, encoding="utf-8")

    return {
        "metrics": metrics,
        "health_score": health_score,
        "health_status": health_status,
        "report_path": str(report_path),
        "dry_run": dry_run,
    }
