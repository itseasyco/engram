#!/usr/bin/env python3
"""
Vault Doctor — heal orphans, fix frontmatter, add tags, rename hash files, connect notes.

Scans every note in the vault and fixes what it can:
1. Find orphans (notes with zero backlinks)
2. Add/fix YAML frontmatter (title, category, tags, dates, status)
3. Auto-detect tags from content (#PRD, #research, #architecture, #meeting, etc.)
4. Rename hash-named files to prose-style titles
5. Detect category and suggest/execute moves to correct folders
6. Run wikilink weaver to connect orphans
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# Tag detection keywords — maps tag name to content keywords
TAG_KEYWORDS = {
    "prd": ["prd", "product requirement", "product requirements document", "feature spec", "user stories"],
    "research": ["research", "analysis", "evaluation", "comparison", "literature", "findings", "study"],
    "architecture": ["architecture", "system design", "infrastructure", "deployment", "service"],
    "meeting": ["meeting", "discussed", "agenda", "action items", "attendees", "minutes", "standup"],
    "transcript": ["speaker:", "q:", "a:", "[00:", "timestamp"],
    "decision": ["decision", "decided", "adr", "we chose", "going with", "settled on"],
    "bug": ["bug", "issue", "regression", "fix", "hotfix", "patch"],
    "payment": ["payment", "finix", "brale", "settlement", "payout", "checkout", "transaction"],
    "api": ["api", "endpoint", "route", "rest", "graphql", "webhook"],
    "auth": ["auth", "login", "session", "token", "oauth", "passkey", "2fa"],
    "database": ["database", "migration", "rls", "supabase", "postgres", "schema", "sql"],
    "security": ["security", "vulnerability", "audit", "encryption", "cve"],
    "testing": ["test", "jest", "pytest", "coverage", "e2e", "maestro", "qa"],
    "deployment": ["deploy", "ci/cd", "vercel", "render", "github actions", "pipeline"],
    "frontend": ["react", "next.js", "tailwind", "component", "dashboard", "css"],
    "mobile": ["mobile", "ios", "android", "react native", "expo", "app store"],
    "sdk": ["sdk", "client library", "integration", "embed"],
    "onboarding": ["onboarding", "getting started", "setup", "install", "tutorial"],
    "investor": ["investor", "fundrais", "pitch", "seed", "series", "valuation"],
    "strategy": ["strategy", "roadmap", "vision", "okr", "kpi", "quarterly"],
    "health": ["health", "peptide", "supplement", "workout", "nutrition", "protocol"],
    "personal": ["personal", "family", "schedule", "preference"],
}

# Category detection — maps category to keywords
CATEGORY_KEYWORDS = {
    "sessions": ["meeting", "transcript", "discussed", "agenda", "speaker:", "call notes"],
    "engineering": ["architecture", "system design", "infrastructure", "api", "database", "migration", "code"],
    "projects": ["project", "feature", "prd", "milestone", "sprint", "backlog", "easy-api", "easy-dashboard"],
    "reference": ["documentation", "reference", "guide", "tutorial", "how-to", "api docs"],
    "strategy": ["strategy", "investor", "fundrais", "partnership", "revenue", "roadmap", "pitch"],
    "knowledge": ["concept", "pattern", "principle", "convention", "learning", "insight"],
    "health": ["health", "peptide", "supplement", "workout", "nutrition"],
    "people": ["person", "contact", "team member", "scheduling preferences"],
    "memory": ["session memory", "daily log", "session —", "session started"],
}

# Patterns for hash-named files
HASH_NAME_PATTERN = re.compile(r'^(file|url|pdf|transcript|video)_[a-f0-9]{6,8}$')


def _parse_frontmatter(text):
    """Extract frontmatter dict and body from a note."""
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text
    fm_raw = text[4:end]
    body = text[end + 5:]

    fm = {}
    for line in fm_raw.splitlines():
        line = line.strip()
        if ":" in line and not line.startswith("#"):
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if val.startswith("[") and val.endswith("]"):
                val = [v.strip().strip('"').strip("'") for v in val[1:-1].split(",") if v.strip()]
            fm[key] = val
    return fm, body


def _build_frontmatter_str(fm):
    """Convert frontmatter dict to YAML string."""
    lines = ["---"]
    for key, val in fm.items():
        if isinstance(val, list):
            lines.append(f"{key}: [{', '.join(val)}]")
        elif isinstance(val, bool):
            lines.append(f"{key}: {'true' if val else 'false'}")
        else:
            if isinstance(val, str) and (" " in val or ":" in val or '"' in val):
                lines.append(f'{key}: "{val}"')
            else:
                lines.append(f"{key}: {val}")
    lines.append("---")
    return "\n".join(lines)


def _extract_tags(content, title=""):
    """Extract tags from content using keyword detection."""
    tags = set()
    combined = (title + " " + content[:3000]).lower()
    for tag, keywords in TAG_KEYWORDS.items():
        if any(kw in combined for kw in keywords):
            tags.add(tag)
    return sorted(tags) if tags else ["general"]


def _detect_category(content, title="", current_path=""):
    """Detect the best category for a note."""
    combined = (title + " " + content[:2000]).lower()
    path_lower = current_path.lower()

    # If already in a category folder, keep it
    for cat in CATEGORY_KEYWORDS:
        if f"/{cat}/" in path_lower:
            return cat

    # Detect from content
    scores = {}
    for cat, keywords in CATEGORY_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in combined)
        if score > 0:
            scores[cat] = score

    if scores:
        return max(scores, key=scores.get)
    return "inbox"


def _prose_title(filename):
    """Generate prose title from filename."""
    stem = Path(filename).stem
    date_match = re.match(r'^(\d{4}-\d{2}-\d{2})[_-]?(.*)', stem)
    if date_match:
        date_str = date_match.group(1)
        rest = date_match.group(2).replace("-", " ").replace("_", " ").strip()
        title = rest.title() if rest else "Notes"
        return f"{title} ({date_str})"
    title = stem.replace("-", " ").replace("_", " ").strip().title()
    return title or "Untitled"


def _is_hash_name(filename):
    """Check if a filename is a hash-based auto-generated name."""
    stem = Path(filename).stem
    return bool(HASH_NAME_PATTERN.match(stem))


def _extract_title_from_content(content):
    """Try to extract a meaningful title from the note content."""
    # Look for # heading
    match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
    if match:
        title = match.group(1).strip()
        # Skip generic headings
        if title.lower() not in ("content", "metadata", "notes", "untitled"):
            return title

    # Look for title: in frontmatter-like content
    match = re.search(r'^title:\s*["\']?(.+?)["\']?\s*$', content, re.MULTILINE)
    if match:
        return match.group(1).strip()

    # First non-empty, non-heading line
    for line in content.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and not line.startswith("---") and len(line) > 10:
            return line[:60].strip()

    return None


def _find_all_links(vault_path):
    """Build a map of what links to what."""
    vault = Path(vault_path)
    links_to = {}  # note -> set of notes it links to
    linked_from = {}  # note -> set of notes that link to it

    for md in vault.rglob("*.md"):
        if ".obsidian" in str(md):
            continue
        rel = str(md.relative_to(vault))
        stem = md.stem

        try:
            content = md.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        # Find [[wikilinks]]
        found_links = re.findall(r'\[\[([^\]|]+?)(?:\|[^\]]+?)?\]\]', content)
        links_to[rel] = set(found_links)

        for link in found_links:
            linked_from.setdefault(link, set()).add(rel)
            # Also try with stem match
            linked_from.setdefault(link.split("/")[-1], set()).add(rel)

    return links_to, linked_from


def scan_vault(vault_path, dry_run=True):
    """Scan the vault and identify issues."""
    vault = Path(vault_path)
    if not vault.exists():
        return {"error": f"Vault not found: {vault_path}"}

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    links_to, linked_from = _find_all_links(vault_path)

    results = {
        "total_notes": 0,
        "orphans": [],
        "missing_frontmatter": [],
        "hash_names": [],
        "missing_tags": [],
        "missing_category": [],
        "suggested_moves": [],
        "fixes_applied": {
            "frontmatter_added": 0,
            "tags_added": 0,
            "titles_fixed": 0,
            "files_renamed": 0,
            "notes_moved": 0,
        },
        "dry_run": dry_run,
    }

    for md in sorted(vault.rglob("*.md")):
        if ".obsidian" in str(md):
            continue

        rel = str(md.relative_to(vault))
        stem = md.stem
        results["total_notes"] += 1

        try:
            content = md.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        fm, body = _parse_frontmatter(content)

        # Check orphan status
        is_orphan = stem not in linked_from and rel not in linked_from
        if is_orphan and "index" not in stem.lower():
            results["orphans"].append(rel)

        # Check frontmatter
        has_fm = bool(fm)
        if not has_fm:
            results["missing_frontmatter"].append(rel)

        # Check hash name
        if _is_hash_name(md.name):
            results["hash_names"].append(rel)

        # Check tags
        if not fm.get("tags"):
            results["missing_tags"].append(rel)

        # Check category
        if not fm.get("category"):
            results["missing_category"].append(rel)

        # === Apply fixes ===
        changed = False
        new_content = content

        # Fix 1: Add/update frontmatter
        if not has_fm or not fm.get("tags") or not fm.get("category") or not fm.get("title"):
            detected_tags = _extract_tags(body or content, fm.get("title", stem))
            detected_category = _detect_category(body or content, fm.get("title", stem), rel)

            if not has_fm:
                # Generate full frontmatter
                title = fm.get("title") or _extract_title_from_content(content) or _prose_title(md.name)
                new_fm = {
                    "title": title,
                    "category": detected_category,
                    "tags": detected_tags,
                    "created": now,
                    "updated": now,
                    "author": "engram-doctor",
                    "source": "vault-scan",
                    "status": "active",
                }
                new_content = _build_frontmatter_str(new_fm) + "\n\n" + content
                changed = True
                results["fixes_applied"]["frontmatter_added"] += 1
            else:
                # Update existing frontmatter
                updated = False
                if not fm.get("tags"):
                    fm["tags"] = detected_tags
                    updated = True
                    results["fixes_applied"]["tags_added"] += 1
                if not fm.get("category"):
                    fm["category"] = detected_category
                    updated = True
                if not fm.get("title"):
                    fm["title"] = _extract_title_from_content(body or content) or _prose_title(md.name)
                    updated = True
                    results["fixes_applied"]["titles_fixed"] += 1
                if not fm.get("status"):
                    fm["status"] = "active"
                    updated = True

                if updated:
                    new_content = _build_frontmatter_str(fm) + "\n\n" + (body or content)
                    changed = True

        # Fix 2: Rename hash-named files
        new_path = None
        if _is_hash_name(md.name):
            title = fm.get("title") or _extract_title_from_content(body or content)
            if title:
                slug = re.sub(r'[^\w\s-]', '', title.lower().strip())
                slug = re.sub(r'[\s_]+', '-', slug).strip('-')[:80]
                if slug and slug != stem:
                    new_path = md.parent / f"{slug}.md"
                    if new_path.exists():
                        new_path = md.parent / f"{slug}-{hashlib.md5(str(md).encode()).hexdigest()[:4]}.md"
                    results["fixes_applied"]["files_renamed"] += 1

        # Fix 3: Suggest moves based on category
        detected_cat = _detect_category(body or content, fm.get("title", stem), rel)
        current_folder = rel.split("/")[0] if "/" in rel else ""
        if detected_cat != "inbox" and current_folder in ("inbox", ""):
            results["suggested_moves"].append({
                "file": rel,
                "from": current_folder or "(root)",
                "to": detected_cat,
                "reason": f"Content matches {detected_cat}",
            })

        # Write changes
        if not dry_run and changed:
            target = new_path or md
            if new_path and new_path != md:
                md.rename(new_path)
            target.write_text(new_content, encoding="utf-8")
        elif not dry_run and new_path and not changed:
            md.rename(new_path)

    return results


def print_report(results):
    """Print a human-readable report."""
    print(f"\n{'='*60}")
    print(f"  Engram Vault Doctor Report")
    print(f"{'='*60}\n")

    if results.get("dry_run"):
        print("  MODE: DRY RUN (no changes made)\n")

    print(f"  Total notes scanned: {results['total_notes']}")
    print(f"  Orphans (no backlinks): {len(results['orphans'])}")
    print(f"  Missing frontmatter: {len(results['missing_frontmatter'])}")
    print(f"  Hash-named files: {len(results['hash_names'])}")
    print(f"  Missing tags: {len(results['missing_tags'])}")
    print(f"  Missing category: {len(results['missing_category'])}")
    print(f"  Suggested moves: {len(results['suggested_moves'])}")

    fixes = results["fixes_applied"]
    if any(fixes.values()):
        print(f"\n  Fixes {'proposed' if results.get('dry_run') else 'applied'}:")
        if fixes["frontmatter_added"]:
            print(f"    Frontmatter added: {fixes['frontmatter_added']}")
        if fixes["tags_added"]:
            print(f"    Tags added: {fixes['tags_added']}")
        if fixes["titles_fixed"]:
            print(f"    Titles fixed: {fixes['titles_fixed']}")
        if fixes["files_renamed"]:
            print(f"    Files to rename: {fixes['files_renamed']}")

    if results["hash_names"][:10]:
        print(f"\n  Hash-named files (sample):")
        for f in results["hash_names"][:10]:
            print(f"    {f}")

    if results["suggested_moves"][:10]:
        print(f"\n  Suggested moves (sample):")
        for m in results["suggested_moves"][:10]:
            print(f"    {m['file']}")
            print(f"      {m['from']} -> {m['to']} ({m['reason']})")

    print(f"\n{'='*60}\n")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Engram Vault Doctor — heal orphans, fix frontmatter, add tags")
    parser.add_argument("vault_path", help="Path to the Obsidian vault")
    parser.add_argument("--apply", action="store_true", help="Apply fixes (default: dry run)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--move", action="store_true", help="Execute suggested moves (requires --apply)")
    args = parser.parse_args()

    dry_run = not args.apply

    results = scan_vault(args.vault_path, dry_run=dry_run)

    if args.json:
        print(json.dumps(results, indent=2, default=str))
    else:
        print_report(results)

    if not dry_run:
        print("Fixes applied. Run the curator cycle to weave wikilinks:")
        print(f"  engram brain expand --curator-cycle")


if __name__ == "__main__":
    main()
