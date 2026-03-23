"""
Wikilink weaver for the curator engine.

Scans the vault for related notes using title matching, tag overlap, and
content similarity. Adds [[backlinks]] between related notes. Removes
broken links to deleted or archived notes.
"""

import os
import re
from collections import defaultdict
from pathlib import Path
from typing import Optional

from plugin.lib.consolidation import _parse_frontmatter, _extract_links


# ---------------------------------------------------------------------------
# Similarity scoring
# ---------------------------------------------------------------------------

def _title_similarity(title_a: str, title_b: str) -> float:
    """
    Compute title similarity using word overlap (Jaccard).

    Returns float in [0, 1].
    """
    words_a = set(title_a.lower().split())
    words_b = set(title_b.lower().split())
    # Remove very common words
    stop = {"the", "a", "an", "and", "or", "of", "in", "to", "for", "is", "on", "at", "by"}
    words_a -= stop
    words_b -= stop
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union)


def _tag_overlap(tags_a: list, tags_b: list) -> float:
    """
    Compute tag overlap (Jaccard).

    Returns float in [0, 1].
    """
    set_a = set(t.lower() for t in tags_a)
    set_b = set(t.lower() for t in tags_b)
    if not set_a or not set_b:
        return 0.0
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union)


def _content_keyword_overlap(body_a: str, body_b: str, top_n: int = 30) -> float:
    """
    Compute content similarity using keyword overlap.

    Extracts top_n most frequent non-trivial words from each note body
    and computes Jaccard similarity.

    Returns float in [0, 1].
    """
    stop = {
        "the", "a", "an", "and", "or", "of", "in", "to", "for", "is", "on",
        "at", "by", "it", "be", "as", "that", "this", "was", "are", "with",
        "not", "but", "from", "have", "has", "had", "will", "can", "do",
        "if", "we", "you", "they", "he", "she", "its",
    }

    def extract_keywords(text):
        words = re.findall(r"[a-z]{3,}", text.lower())
        words = [w for w in words if w not in stop]
        freq = defaultdict(int)
        for w in words:
            freq[w] += 1
        sorted_words = sorted(freq, key=freq.get, reverse=True)
        return set(sorted_words[:top_n])

    kw_a = extract_keywords(body_a)
    kw_b = extract_keywords(body_b)
    if not kw_a or not kw_b:
        return 0.0
    intersection = kw_a & kw_b
    union = kw_a | kw_b
    return len(intersection) / len(union)


def compute_relatedness(note_a: dict, note_b: dict) -> float:
    """
    Compute relatedness between two notes.

    Weighted combination:
    - 0.4 * title similarity
    - 0.3 * tag overlap
    - 0.3 * content keyword overlap

    Args:
        note_a, note_b: dicts with keys: title, tags, body.

    Returns:
        float in [0, 1].
    """
    title_sim = _title_similarity(
        note_a.get("title", ""),
        note_b.get("title", ""),
    )
    tag_sim = _tag_overlap(
        note_a.get("tags", []),
        note_b.get("tags", []),
    )
    content_sim = _content_keyword_overlap(
        note_a.get("body", ""),
        note_b.get("body", ""),
    )
    return 0.4 * title_sim + 0.3 * tag_sim + 0.3 * content_sim


# ---------------------------------------------------------------------------
# Vault loading (extended for wikilink weaving)
# ---------------------------------------------------------------------------

def _load_notes_for_weaving(vault_path: Path) -> dict:
    """
    Load all notes with title, tags, body, existing links, and file path.

    Returns:
        {note_stem: {title, tags, body, links, path, content}}
    """
    notes = {}
    for md_file in vault_path.rglob("*.md"):
        # Skip .obsidian and archive
        rel = md_file.relative_to(vault_path).as_posix()
        if rel.startswith(".obsidian/") or rel.startswith("99_Archive/"):
            continue

        try:
            content = md_file.read_text(encoding="utf-8")
        except (IOError, UnicodeDecodeError):
            continue

        fm = _parse_frontmatter(content)
        body = content
        if content.startswith("---"):
            end = content.find("---", 3)
            if end != -1:
                body = content[end + 3:]

        links = _extract_links(content)
        tags = fm.get("tags", [])
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",") if t.strip()]

        title = fm.get("title", md_file.stem)

        notes[md_file.stem] = {
            "title": title,
            "tags": tags,
            "body": body,
            "links": links,
            "path": md_file,
            "content": content,
        }

    return notes


# ---------------------------------------------------------------------------
# Wikilink insertion
# ---------------------------------------------------------------------------

def _add_backlink_to_content(content: str, target_stem: str) -> str:
    """
    Add a [[backlink]] to the "Related Notes" section of a note.

    If no "Related Notes" section exists, append one at the end.
    Returns the modified content.
    """
    link = f"[[{target_stem}]]"

    # Already linked?
    if link in content:
        return content

    # Find or create "Related Notes" section
    related_header_pat = re.compile(r"(?m)^##\s+Related\s+Notes?\s*$")
    match = related_header_pat.search(content)

    if match:
        # Insert after the header line
        insert_pos = match.end()
        # Find next section header or end of content
        next_header = re.search(r"(?m)^##\s+", content[insert_pos + 1:])
        if next_header:
            insert_pos = insert_pos + 1 + next_header.start()
        else:
            insert_pos = len(content)
        # Insert the link as a list item
        link_line = f"\n- {link}"
        content = content[:insert_pos].rstrip() + link_line + "\n" + content[insert_pos:].lstrip("\n")
    else:
        # Append Related Notes section
        content = content.rstrip() + f"\n\n## Related Notes\n\n- {link}\n"

    return content


# ---------------------------------------------------------------------------
# Broken link removal
# ---------------------------------------------------------------------------

def _remove_broken_links(content: str, valid_stems: set) -> tuple:
    """
    Remove [[wikilinks]] that point to non-existent notes.

    Returns:
        (modified_content, list_of_removed_links)
    """
    removed = []

    def replace_link(match):
        link_target = match.group(1)
        # Handle aliased links: [[target|alias]]
        stem = link_target.split("|")[0].strip()
        if stem not in valid_stems:
            removed.append(stem)
            # Replace with just the display text
            if "|" in link_target:
                return link_target.split("|")[1].strip()
            return stem
        return match.group(0)

    modified = re.sub(r"\[\[([^\]]+)\]\]", replace_link, content)
    return modified, removed


# ---------------------------------------------------------------------------
# Main weaving function
# ---------------------------------------------------------------------------

def weave_wikilinks(
    vault_path: Optional[str] = None,
    relatedness_threshold: float = 0.25,
    max_links_per_note: int = 10,
    dry_run: bool = True,
    remove_broken: bool = True,
) -> dict:
    """
    Scan vault for related notes and add wikilinks between them.

    Args:
        vault_path: root of the Obsidian vault.
        relatedness_threshold: minimum relatedness score to add a link.
        max_links_per_note: max new links to add per note per run.
        dry_run: if True, report what would be done without modifying files.
        remove_broken: if True, also remove links to non-existent notes.

    Returns:
        dict with links_added, links_removed, pairs_evaluated, notes_modified.
    """
    if vault_path is None:
        vault_path = os.environ.get(
            "LACP_OBSIDIAN_VAULT",
            os.path.expanduser("~/obsidian/vault"),
        )

    vault = Path(vault_path)
    notes = _load_notes_for_weaving(vault)
    stems = list(notes.keys())
    valid_stems = set(stems)

    links_added = 0
    links_removed_total = 0
    notes_modified = set()
    pairs_evaluated = 0
    added_details = []

    # Phase 1: Find related pairs and add links
    for i, stem_a in enumerate(stems):
        note_a = notes[stem_a]
        new_links_for_a = 0

        for stem_b in stems[i + 1:]:
            if new_links_for_a >= max_links_per_note:
                break

            note_b = notes[stem_b]
            pairs_evaluated += 1

            # Skip if already linked in either direction
            if stem_b in note_a["links"] or stem_a in note_b["links"]:
                continue

            score = compute_relatedness(note_a, note_b)
            if score >= relatedness_threshold:
                if not dry_run:
                    # Add link A -> B
                    new_content_a = _add_backlink_to_content(note_a["content"], stem_b)
                    if new_content_a != note_a["content"]:
                        note_a["path"].write_text(new_content_a, encoding="utf-8")
                        note_a["content"] = new_content_a
                        notes_modified.add(stem_a)

                    # Add link B -> A
                    new_content_b = _add_backlink_to_content(note_b["content"], stem_a)
                    if new_content_b != note_b["content"]:
                        note_b["path"].write_text(new_content_b, encoding="utf-8")
                        note_b["content"] = new_content_b
                        notes_modified.add(stem_b)

                links_added += 1
                new_links_for_a += 1
                added_details.append({
                    "a": stem_a,
                    "b": stem_b,
                    "score": round(score, 4),
                })

    # Phase 2: Remove broken links
    broken_details = []
    if remove_broken:
        for stem, note in notes.items():
            modified_content, removed = _remove_broken_links(
                note["content"], valid_stems,
            )
            if removed:
                links_removed_total += len(removed)
                if not dry_run:
                    note["path"].write_text(modified_content, encoding="utf-8")
                notes_modified.add(stem)
                broken_details.append({
                    "note": stem,
                    "removed_links": removed,
                })

    return {
        "links_added": links_added,
        "links_removed": links_removed_total,
        "pairs_evaluated": pairs_evaluated,
        "notes_modified": len(notes_modified),
        "added_details": added_details,
        "broken_details": broken_details,
        "dry_run": dry_run,
    }
