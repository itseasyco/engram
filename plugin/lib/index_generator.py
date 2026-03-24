"""
Index generator for the curator engine.

Regenerates 00_Index.md (master index) and per-folder index.md files
with current note counts, recent changes, and note listings.
"""

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .consolidation import _parse_frontmatter


# ---------------------------------------------------------------------------
# Folder metadata
# ---------------------------------------------------------------------------

FOLDER_DESCRIPTIONS = {
    "01_Projects": "Per-repo and per-project knowledge",
    "02_Concepts": "Cross-project concepts and patterns",
    "03_People": "Team context and roles",
    "04_Systems": "Infrastructure and architecture",
    "05_Inbox": "Incoming notes awaiting classification",
    "06_Planning": "Product planning and roadmaps",
    "07_Research": "Research findings and evaluations",
    "08_Strategy": "Executive-level strategy documents",
    "09_Changelog": "Auto-generated release and deploy logs",
    "10_Templates": "Note templates",
    "99_Archive": "Archived notes",
}

MAIN_FOLDERS = [
    "01_Projects",
    "02_Concepts",
    "03_People",
    "04_Systems",
    "05_Inbox",
    "06_Planning",
    "07_Research",
    "08_Strategy",
    "09_Changelog",
    "10_Templates",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _count_notes(folder: Path) -> int:
    """Count .md files in a folder (recursive, excluding index.md)."""
    if not folder.exists():
        return 0
    return sum(
        1 for f in folder.rglob("*.md")
        if f.name != "index.md" and not f.name.startswith(".")
    )


def _recent_notes(folder: Path, limit: int = 5) -> list:
    """Get the most recently modified notes in a folder."""
    if not folder.exists():
        return []

    notes = []
    for f in folder.rglob("*.md"):
        if f.name == "index.md" or f.name.startswith("."):
            continue
        try:
            mtime = f.stat().st_mtime
            notes.append((f, mtime))
        except OSError:
            continue

    notes.sort(key=lambda x: x[1], reverse=True)
    return [f for f, _ in notes[:limit]]


def _note_title(file_path: Path) -> str:
    """Extract title from note frontmatter or filename."""
    try:
        content = file_path.read_text(encoding="utf-8")
        fm = _parse_frontmatter(content)
        title = fm.get("title", "")
        if title:
            return str(title).strip('"').strip("'")
    except (IOError, UnicodeDecodeError):
        pass
    return file_path.stem.replace("-", " ").replace("_", " ").title()


# ---------------------------------------------------------------------------
# Master index
# ---------------------------------------------------------------------------

def generate_master_index(vault_path: Path) -> str:
    """Generate the content for 00_Index.md."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    total_notes = sum(
        1 for f in vault_path.rglob("*.md")
        if not f.relative_to(vault_path).as_posix().startswith(".obsidian/")
        and f.name != "index.md"
        and f.stem != "00_Index"
    )

    lines = [
        "---",
        "type: index",
        f'generated: "{now}"',
        "---",
        "",
        "# Company Brain",
        "",
        f"Total notes: **{total_notes}** | Last updated: {now}",
        "",
        "## Sections",
        "",
        "| Folder | Notes | Description |",
        "|--------|-------|-------------|",
    ]

    for folder_name in MAIN_FOLDERS:
        folder = vault_path / folder_name
        count = _count_notes(folder)
        desc = FOLDER_DESCRIPTIONS.get(folder_name, "")
        lines.append(f"| [[{folder_name}]] | {count} | {desc} |")

    # Archive
    archive = vault_path / "99_Archive"
    if archive.exists():
        count = _count_notes(archive)
        lines.append(f"| [[99_Archive]] | {count} | {FOLDER_DESCRIPTIONS.get('99_Archive', '')} |")

    lines.append("")
    lines.append("## Recent Changes")
    lines.append("")

    # Gather recent notes across all folders
    all_recent = []
    for folder_name in MAIN_FOLDERS:
        folder = vault_path / folder_name
        for note_path in _recent_notes(folder, limit=3):
            try:
                mtime = note_path.stat().st_mtime
                all_recent.append((note_path, mtime))
            except OSError:
                continue

    all_recent.sort(key=lambda x: x[1], reverse=True)
    for note_path, mtime in all_recent[:10]:
        title = _note_title(note_path)
        rel = note_path.relative_to(vault_path)
        date = datetime.fromtimestamp(mtime, tz=timezone.utc).strftime("%Y-%m-%d")
        lines.append(f"- {date} -- [[{note_path.stem}]] ({rel.parent})")

    if not all_recent:
        lines.append("- No recent changes")

    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Per-folder index
# ---------------------------------------------------------------------------

def generate_folder_index(folder_path: Path, vault_path: Path) -> str:
    """Generate index.md content for a specific folder."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    folder_name = folder_path.name
    desc = FOLDER_DESCRIPTIONS.get(folder_name, "")

    notes = []
    for f in sorted(folder_path.rglob("*.md")):
        if f.name == "index.md" or f.name.startswith("."):
            continue
        title = _note_title(f)
        rel = f.relative_to(folder_path)
        notes.append((str(rel), f.stem, title))

    # Subfolder grouping
    subfolders = {}
    top_level = []
    for rel, stem, title in notes:
        parts = rel.split("/")
        if len(parts) > 1:
            subfolder = parts[0]
            if subfolder not in subfolders:
                subfolders[subfolder] = []
            subfolders[subfolder].append((stem, title))
        else:
            top_level.append((stem, title))

    lines = [
        "---",
        "type: folder-index",
        f'generated: "{now}"',
        "---",
        "",
        f"# {folder_name}",
        "",
        desc,
        "",
        f"**{len(notes)} notes** | Last updated: {now}",
        "",
    ]

    if top_level:
        lines.append("## Notes")
        lines.append("")
        for stem, title in top_level:
            lines.append(f"- [[{stem}]] -- {title}")
        lines.append("")

    for subfolder, sub_notes in sorted(subfolders.items()):
        lines.append(f"## {subfolder}")
        lines.append("")
        for stem, title in sub_notes:
            lines.append(f"- [[{stem}]] -- {title}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main generator
# ---------------------------------------------------------------------------

def regenerate_indexes(
    vault_path: Optional[str] = None,
    dry_run: bool = True,
) -> dict:
    """
    Regenerate 00_Index.md and all per-folder index.md files.

    Args:
        vault_path: root of the Obsidian vault.
        dry_run: if True, report only.

    Returns:
        dict with master_index_updated, folder_indexes_updated, total_notes.
    """
    if vault_path is None:
        vault_path = os.environ.get(
            "LACP_OBSIDIAN_VAULT",
            os.path.expanduser("~/obsidian/vault"),
        )

    vault = Path(vault_path)
    if not vault.exists():
        return {"error": "vault_not_found", "path": str(vault)}

    updated_folders = []

    # Master index
    master_content = generate_master_index(vault)
    master_path = vault / "00_Index.md"
    if not dry_run:
        master_path.write_text(master_content, encoding="utf-8")

    # Per-folder indexes
    for folder_name in MAIN_FOLDERS:
        folder = vault / folder_name
        if not folder.exists():
            continue

        index_content = generate_folder_index(folder, vault)
        index_path = folder / "index.md"
        if not dry_run:
            index_path.write_text(index_content, encoding="utf-8")
        updated_folders.append(folder_name)

        # Subfolder indexes
        for subfolder in sorted(folder.iterdir()):
            if subfolder.is_dir() and not subfolder.name.startswith("."):
                sub_index_content = generate_folder_index(subfolder, vault)
                sub_index_path = subfolder / "index.md"
                if not dry_run:
                    sub_index_path.write_text(sub_index_content, encoding="utf-8")
                updated_folders.append(f"{folder_name}/{subfolder.name}")

    total_notes = sum(
        1 for f in vault.rglob("*.md")
        if not f.relative_to(vault).as_posix().startswith(".obsidian/")
        and f.name != "index.md"
        and f.stem != "00_Index"
    )

    return {
        "master_index_updated": True,
        "folder_indexes_updated": updated_folders,
        "total_notes": total_notes,
        "dry_run": dry_run,
    }
