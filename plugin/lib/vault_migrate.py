#!/usr/bin/env python3
"""
Vault structure migration for Engram.

Scans an existing vault, proposes a clean Engram-compatible structure,
and migrates files with wikilink preservation.

The Engram vault structure:
  home/           — master index, vault overview
  memory/         — session memories (daily folders, per-agent files)
  projects/       — per-repo/per-project knowledge
  engineering/    — architecture, decisions, active work
  knowledge/      — concepts, learnings, agent knowledge
  inbox/          — incoming notes awaiting curator processing
    queue-agent/    — agent-submitted facts
    queue-cicd/     — CI/CD events
    queue-human/    — human-submitted (email, voice notes, research)
    queue-session/  — auto-captured session memories (connected mode)
    review-stale/   — curator-flagged for review
  reference/      — external docs, API references
  health/         — personal/team health tracking
  people/         — team members, contacts
  strategy/       — business strategy, planning
  archive/        — archived/deprecated content
  _metadata/      — vault config, taxonomy

No numbered prefixes. Clean names. Obsidian sort settings handle display order.
"""
from __future__ import annotations

import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# The target Engram structure
ENGRAM_STRUCTURE = {
    "home": {
        "description": "Master index, vault overview",
        "migrate_from": ["00-home"],
    },
    "memory": {
        "description": "Session memories (daily folders, per-agent files)",
        "migrate_from": ["01_memory"],
    },
    "projects": {
        "description": "Per-repo/per-project knowledge",
        "migrate_from": ["02-projects"],
    },
    "engineering": {
        "description": "Architecture, decisions, active work",
        "migrate_from": ["03-engineering"],
    },
    "knowledge": {
        "description": "Concepts, learnings, agent knowledge",
        "migrate_from": ["04-knowledge", "01-atlas"],
    },
    "inbox": {
        "description": "Incoming notes awaiting curator processing",
        "migrate_from": ["05_Inbox", "06-inbox", "inbox"],
        "subfolders": {
            "queue-agent": "Agent-submitted facts",
            "queue-cicd": "CI/CD events",
            "queue-human": "Human-submitted (email, voice notes, research)",
            "queue-session": "Auto-captured session memories",
            "review-stale": "Curator-flagged for review",
        },
    },
    "sessions": {
        "description": "Meeting notes, transcripts",
        "migrate_from": ["05-sessions"],
    },
    "reference": {
        "description": "External docs, API references",
        "migrate_from": ["07-reference"],
    },
    "health": {
        "description": "Health tracking",
        "migrate_from": ["08-health"],
    },
    "people": {
        "description": "Team members, contacts",
        "migrate_from": [],
    },
    "strategy": {
        "description": "Business strategy, planning, investors",
        "migrate_from": ["09-twitter"],
    },
    "archive": {
        "description": "Archived/deprecated content",
        "migrate_from": ["99_Archive"],
    },
    "_metadata": {
        "description": "Vault config, taxonomy",
        "migrate_from": ["_metadata"],
    },
}


def scan_vault(vault_path: str) -> dict:
    """Scan an existing vault and return its structure."""
    vault = Path(vault_path)
    if not vault.exists():
        return {"error": f"Vault not found: {vault_path}"}

    folders = {}
    for item in sorted(vault.iterdir()):
        if item.name.startswith(".") or not item.is_dir():
            continue

        file_count = sum(1 for _ in item.rglob("*.md"))
        total_files = sum(1 for _ in item.rglob("*") if _.is_file())
        subfolders = [
            sf.name for sf in item.iterdir()
            if sf.is_dir() and not sf.name.startswith(".")
        ]

        folders[item.name] = {
            "path": str(item),
            "md_files": file_count,
            "total_files": total_files,
            "subfolders": subfolders,
            "empty": file_count == 0 and total_files == 0,
        }

    return {
        "vault_path": str(vault),
        "folders": folders,
        "total_folders": len(folders),
        "total_md_files": sum(f["md_files"] for f in folders.values()),
    }


def propose_migration(vault_path: str) -> dict:
    """Propose a migration plan from current structure to Engram structure."""
    scan = scan_vault(vault_path)
    if "error" in scan:
        return scan

    vault = Path(vault_path)
    existing = scan["folders"]
    plan = {
        "vault_path": str(vault),
        "moves": [],
        "creates": [],
        "merges": [],
        "deletes_empty": [],
        "skipped": [],
        "unmapped": [],
    }

    mapped_sources = set()

    for target_name, spec in ENGRAM_STRUCTURE.items():
        target_path = vault / target_name
        sources = spec.get("migrate_from", [])

        if not sources:
            if not target_path.exists():
                plan["creates"].append({
                    "path": target_name,
                    "description": spec["description"],
                })
            continue

        existing_sources = [s for s in sources if s in existing]

        if not existing_sources:
            if not target_path.exists():
                plan["creates"].append({
                    "path": target_name,
                    "description": spec["description"],
                })
            continue

        if len(existing_sources) == 1 and existing_sources[0] == target_name:
            # Already in the right place
            plan["skipped"].append({
                "source": existing_sources[0],
                "target": target_name,
                "reason": "already correctly named",
            })
            mapped_sources.add(existing_sources[0])
            continue

        if len(existing_sources) == 1:
            source = existing_sources[0]
            source_info = existing[source]

            if source_info["empty"]:
                plan["deletes_empty"].append(source)
                if not target_path.exists():
                    plan["creates"].append({
                        "path": target_name,
                        "description": spec["description"],
                    })
            else:
                plan["moves"].append({
                    "source": source,
                    "target": target_name,
                    "files": source_info["md_files"],
                    "total_files": source_info["total_files"],
                })
            mapped_sources.add(source)
        else:
            # Multiple sources merge into one target
            merge_sources = []
            for source in existing_sources:
                source_info = existing[source]
                if source_info["empty"]:
                    plan["deletes_empty"].append(source)
                else:
                    merge_sources.append({
                        "source": source,
                        "files": source_info["md_files"],
                        "total_files": source_info["total_files"],
                    })
                mapped_sources.add(source)

            if merge_sources:
                plan["merges"].append({
                    "target": target_name,
                    "sources": merge_sources,
                    "total_files": sum(s["total_files"] for s in merge_sources),
                })

        # Handle subfolders
        if "subfolders" in spec:
            for subfolder, desc in spec["subfolders"].items():
                sub_path = target_path / subfolder
                if not sub_path.exists():
                    plan["creates"].append({
                        "path": f"{target_name}/{subfolder}",
                        "description": desc,
                    })

    # Find unmapped folders
    for folder_name in existing:
        if folder_name not in mapped_sources:
            plan["unmapped"].append({
                "folder": folder_name,
                "files": existing[folder_name]["md_files"],
                "total_files": existing[folder_name]["total_files"],
            })

    return plan


def _update_wikilinks(vault: Path, old_name: str, new_name: str) -> int:
    """Update wikilinks across the vault when a folder is renamed."""
    count = 0
    for md_file in vault.rglob("*.md"):
        if ".obsidian" in str(md_file):
            continue
        try:
            content = md_file.read_text(encoding="utf-8")
            # Replace folder references in wikilinks
            updated = content.replace(f"[[{old_name}/", f"[[{new_name}/")
            updated = updated.replace(f"[[{old_name}]]", f"[[{new_name}]]")
            if updated != content:
                md_file.write_text(updated, encoding="utf-8")
                count += 1
        except (OSError, UnicodeDecodeError):
            continue
    return count


def execute_migration(vault_path: str, plan: dict, dry_run: bool = True) -> dict:
    """Execute a migration plan."""
    vault = Path(vault_path)
    results = {
        "dry_run": dry_run,
        "moved": [],
        "merged": [],
        "created": [],
        "deleted": [],
        "links_updated": 0,
        "errors": [],
    }

    if dry_run:
        results["moved"] = plan.get("moves", [])
        results["merged"] = plan.get("merges", [])
        results["created"] = plan.get("creates", [])
        results["deleted"] = plan.get("deletes_empty", [])
        return results

    # Backup timestamp
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")

    # 1. Create new folders
    for item in plan.get("creates", []):
        target = vault / item["path"]
        target.mkdir(parents=True, exist_ok=True)
        results["created"].append(item["path"])

    # 2. Execute moves (rename)
    for move in plan.get("moves", []):
        source = vault / move["source"]
        target = vault / move["target"]

        if not source.exists():
            results["errors"].append(f"Source not found: {move['source']}")
            continue

        if target.exists():
            # Merge into existing target
            for item in source.rglob("*"):
                if item.is_file():
                    rel = item.relative_to(source)
                    dest = target / rel
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(item), str(dest))
            # Clean up empty source
            shutil.rmtree(str(source), ignore_errors=True)
        else:
            shutil.move(str(source), str(target))

        # Update wikilinks
        links = _update_wikilinks(vault, move["source"], move["target"])
        results["links_updated"] += links
        results["moved"].append({
            "source": move["source"],
            "target": move["target"],
            "links_updated": links,
        })

    # 3. Execute merges
    for merge in plan.get("merges", []):
        target = vault / merge["target"]
        target.mkdir(parents=True, exist_ok=True)

        for source_info in merge["sources"]:
            source = vault / source_info["source"]
            if not source.exists():
                continue

            # Move all files, preserving subfolders
            for item in source.rglob("*"):
                if item.is_file():
                    rel = item.relative_to(source)
                    dest = target / rel
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    if dest.exists():
                        # Collision — append source name
                        stem = dest.stem
                        suffix = dest.suffix
                        dest = dest.parent / f"{stem}-from-{source_info['source']}{suffix}"
                    shutil.move(str(item), str(dest))

            links = _update_wikilinks(vault, source_info["source"], merge["target"])
            results["links_updated"] += links

            # Clean up empty source
            shutil.rmtree(str(source), ignore_errors=True)

        results["merged"].append({
            "target": merge["target"],
            "sources": [s["source"] for s in merge["sources"]],
        })

    # 4. Delete empty folders
    for folder_name in plan.get("deletes_empty", []):
        folder = vault / folder_name
        if folder.exists():
            try:
                shutil.rmtree(str(folder))
                results["deleted"].append(folder_name)
            except OSError as e:
                results["errors"].append(f"Failed to delete {folder_name}: {e}")

    # 5. Generate updated vault-schema.json
    schema = generate_schema(vault_path)
    plugin_dir = os.environ.get(
        "OPENCLAW_PLUGIN_DIR",
        os.path.expanduser("~/.openclaw/extensions/engram"),
    )
    schema_path = Path(plugin_dir) / "config" / "vault-schema.json"
    schema_path.parent.mkdir(parents=True, exist_ok=True)
    schema_path.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
    results["schema_updated"] = str(schema_path)

    return results


def generate_schema(vault_path: str) -> dict:
    """Generate vault-schema.json from current vault structure."""
    vault = Path(vault_path)
    schema = {
        "version": "1.0.0",
        "description": "Auto-generated by Engram vault migration. Edit to customize.",
        "paths": {},
    }

    # Map existing folders to logical names
    for target_name, spec in ENGRAM_STRUCTURE.items():
        target = vault / target_name
        if target.exists():
            schema["paths"][target_name] = target_name

        # Check subfolders
        if "subfolders" in spec:
            for subfolder in spec["subfolders"]:
                sub_path = target / subfolder
                if sub_path.exists() or target.exists():
                    schema["paths"][f"inbox_{subfolder.replace('-', '_').replace('queue_', '')}"] = f"{target_name}/{subfolder}"

    return schema


def print_plan(plan: dict) -> None:
    """Print a migration plan in human-readable format."""
    print("\n=== Engram Vault Migration Plan ===\n")
    print(f"Vault: {plan['vault_path']}\n")

    if plan.get("moves"):
        print("RENAME:")
        for m in plan["moves"]:
            print(f"  {m['source']}  →  {m['target']}  ({m['files']} md files)")

    if plan.get("merges"):
        print("\nMERGE:")
        for m in plan["merges"]:
            sources = ", ".join(s["source"] for s in m["sources"])
            print(f"  [{sources}]  →  {m['target']}  ({m['total_files']} files)")

    if plan.get("creates"):
        print("\nCREATE:")
        for c in plan["creates"]:
            print(f"  {c['path']}/  ({c['description']})")

    if plan.get("deletes_empty"):
        print("\nDELETE (empty):")
        for d in plan["deletes_empty"]:
            print(f"  {d}/")

    if plan.get("skipped"):
        print("\nSKIP (already correct):")
        for s in plan["skipped"]:
            print(f"  {s['source']}  ({s['reason']})")

    if plan.get("unmapped"):
        print("\nUNMAPPED (not in Engram schema, left as-is):")
        for u in plan["unmapped"]:
            print(f"  {u['folder']}/  ({u['files']} md files)")

    print()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Migrate vault to Engram structure")
    parser.add_argument("vault_path", help="Path to the Obsidian vault")
    parser.add_argument("--apply", action="store_true", help="Execute the migration (default: dry run)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    plan = propose_migration(args.vault_path)

    if args.json:
        print(json.dumps(plan, indent=2))
    else:
        print_plan(plan)

    if args.apply:
        print("Executing migration...")
        results = execute_migration(args.vault_path, plan, dry_run=False)
        if args.json:
            print(json.dumps(results, indent=2))
        else:
            print(f"\nResults:")
            print(f"  Moved: {len(results['moved'])}")
            print(f"  Merged: {len(results['merged'])}")
            print(f"  Created: {len(results['created'])}")
            print(f"  Deleted: {len(results['deleted'])}")
            print(f"  Wikilinks updated: {results['links_updated']}")
            if results.get("errors"):
                print(f"  Errors: {len(results['errors'])}")
                for e in results["errors"]:
                    print(f"    - {e}")
            if results.get("schema_updated"):
                print(f"  Schema: {results['schema_updated']}")
    else:
        if not args.json:
            print("This is a DRY RUN. Add --apply to execute.\n")


if __name__ == "__main__":
    main()
