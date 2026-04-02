"""
Entity extraction engine for Engram.

Two-tier extraction:
  Tier 1 — Agent-powered (primary): Uses Claude via subprocess to analyze
           content with a structured prompt. Handles nuance and context.
  Tier 2 — Heuristic fallback (cron/offline): Structural extraction from
           Attendees lines, frontmatter, capitalized name patterns, and
           alias resolution.

The alias dictionary at plugin/config/entity-aliases.json is self-improving:
when fuzzy matching resolves a new alias, it is written back for next time.
"""

import json
import logging
import os
import re
import subprocess
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

from .consolidation import _parse_frontmatter

logger = logging.getLogger("entity_extractor")


# ---------------------------------------------------------------------------
# Alias dictionary
# ---------------------------------------------------------------------------

def _alias_path() -> Path:
    """Return path to entity-aliases.json."""
    plugin_dir = os.environ.get(
        "OPENCLAW_PLUGIN_DIR",
        os.path.expanduser("~/.openclaw/extensions/engram"),
    )
    return Path(plugin_dir) / "config" / "entity-aliases.json"


def _load_aliases() -> dict:
    """Load alias dictionary. Returns {people: {}, organizations: {}}."""
    path = _alias_path()
    if not path.exists():
        return {"people": {}, "organizations": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {
            "people": data.get("people", {}),
            "organizations": data.get("organizations", {}),
        }
    except (json.JSONDecodeError, OSError):
        return {"people": {}, "organizations": {}}


def _save_alias(name_lower: str, canonical: str, entity_type: str):
    """Write a new alias back to the dictionary (self-improving)."""
    path = _alias_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {
            "_version": "1.0.0",
            "_description": "Self-improving entity alias dictionary.",
            "people": {},
            "organizations": {},
        }
    except (json.JSONDecodeError, OSError):
        data = {"_version": "1.0.0", "people": {}, "organizations": {}}

    bucket = "people" if entity_type == "person" else "organizations"
    if name_lower not in data.get(bucket, {}):
        data.setdefault(bucket, {})[name_lower] = canonical
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info("Alias learned: %r -> %r (%s)", name_lower, canonical, entity_type)


# ---------------------------------------------------------------------------
# Alias resolution + fuzzy matching
# ---------------------------------------------------------------------------

def resolve_entity(
    name: str,
    entity_type: str = "person",
    vault_path: Optional[str] = None,
) -> tuple[str, Optional[Path]]:
    """
    Resolve a raw name to its canonical form and vault profile path.

    Returns:
        (canonical_name, profile_path_or_None)
    """
    aliases = _load_aliases()
    bucket = "people" if entity_type == "person" else "organizations"
    alias_map = aliases.get(bucket, {})
    name_lower = name.strip().lower()

    # Exact alias match
    if name_lower in alias_map:
        canonical = alias_map[name_lower]
        profile = _find_profile(canonical, entity_type, vault_path)
        return canonical, profile

    # Fuzzy match against known aliases
    best_match = None
    best_ratio = 0.0
    for alias_key, canonical in alias_map.items():
        ratio = SequenceMatcher(None, name_lower, alias_key).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_match = canonical

    if best_ratio >= 0.85 and best_match:
        # Self-improve: write back this alias
        _save_alias(name_lower, best_match, entity_type)
        profile = _find_profile(best_match, entity_type, vault_path)
        return best_match, profile

    # No match — return cleaned-up version of input as canonical
    canonical = _clean_name(name)
    return canonical, _find_profile(canonical, entity_type, vault_path)


def _clean_name(name: str) -> str:
    """Clean a raw name into title case canonical form."""
    # Remove common noise
    name = re.sub(r"\(.*?\)", "", name).strip()
    name = re.sub(r"<[^>]+>", "", name).strip()  # email addresses
    name = re.sub(r"\s+", " ", name).strip()
    return name.title() if name else name


def _find_profile(canonical: str, entity_type: str, vault_path: Optional[str]) -> Optional[Path]:
    """Check if a profile file already exists for this entity."""
    if not vault_path:
        try:
            from .vault_paths import root
            vault_path = str(root())
        except (ImportError, KeyError):
            return None

    vault = Path(vault_path)
    slug = _slugify(canonical)

    if entity_type == "person":
        # Search all people/ subdirectories
        people_dir = vault / "people"
        if people_dir.exists():
            for sub in people_dir.iterdir():
                if sub.is_dir():
                    candidate = sub / f"{slug}.md"
                    if candidate.exists():
                        return candidate
            # Also check direct children
            candidate = people_dir / f"{slug}.md"
            if candidate.exists():
                return candidate
    else:
        orgs_dir = vault / "organizations"
        if orgs_dir.exists():
            candidate = orgs_dir / f"{slug}.md"
            if candidate.exists():
                return candidate

    return None


def _slugify(name: str) -> str:
    """Convert a name to a filename slug: 'Kate Levchuk' -> 'kate-levchuk'."""
    slug = name.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug


# ---------------------------------------------------------------------------
# Tier 2: Heuristic extraction (cron/offline)
# ---------------------------------------------------------------------------

# Patterns for meeting attendees lines
_ATTENDEES_RE = re.compile(
    r"(?:attendees?|participants?|present|who)\s*[:—–-]\s*(.+)",
    re.IGNORECASE,
)

# Notetaker/bot names to exclude
_NOTETAKER_PATTERNS = {
    "circleback", "otter", "fireflies", "notetaker", "bot", "recorder",
    "fathom", "grain", "read.ai", "avoma", "gong",
}

# Organization context words that hint the next token is an org
_ORG_CONTEXT = re.compile(
    r"\b(?:at|from|with|of|joining from|representing|on behalf of)\s+([A-Z][A-Za-z0-9&\s]{1,40}?)(?:\s*[,.\n;)]|$)",
)

# Capitalized name pattern: "First Last" or "First Middle Last"
_NAME_RE = re.compile(
    r"\b([A-Z][a-z]{1,20}(?:\s+[A-Z]\.?)?\s+[A-Z][a-z]{1,20}(?:-[A-Z][a-z]+)?)\b"
)


def _is_notetaker(name: str) -> bool:
    """Check if a name looks like a notetaker/bot."""
    lower = name.lower()
    return any(pat in lower for pat in _NOTETAKER_PATTERNS)


def _extract_heuristic(content: str, title: str = "", frontmatter: Optional[dict] = None) -> list[dict]:
    """
    Heuristic entity extraction (Tier 2).

    Returns list of dicts: {name, type, org, role, source, confidence}
    """
    entities = []
    seen_names = set()
    fm = frontmatter or {}

    # 1. Frontmatter people fields
    for field in ("attendees", "participants", "author", "speaker", "guest"):
        val = fm.get(field, "")
        if val:
            names = val if isinstance(val, list) else [n.strip() for n in str(val).split(",")]
            for raw in names:
                raw = raw.strip()
                if raw and not _is_notetaker(raw):
                    canonical, _ = resolve_entity(raw, "person")
                    if canonical.lower() not in seen_names:
                        seen_names.add(canonical.lower())
                        entities.append({
                            "name": canonical,
                            "type": "person",
                            "org": "",
                            "role": "",
                            "source": "frontmatter",
                            "confidence": 0.9,
                        })

    # 2. Attendees lines in body
    for match in _ATTENDEES_RE.finditer(content):
        line = match.group(1)
        # Split by commas, semicolons, or " and "
        parts = re.split(r"[,;]|\band\b", line)
        for part in parts:
            part = part.strip()
            if not part or _is_notetaker(part):
                continue
            # Check for "Name (Role at Org)" pattern
            role_match = re.match(r"(.+?)\s*\((.+)\)", part)
            org = ""
            role = ""
            if role_match:
                part = role_match.group(1).strip()
                context = role_match.group(2).strip()
                if " at " in context.lower():
                    role, org = context.rsplit(" at ", 1)
                else:
                    role = context

            canonical, _ = resolve_entity(part, "person")
            if canonical.lower() not in seen_names and len(canonical) > 2:
                seen_names.add(canonical.lower())
                entities.append({
                    "name": canonical,
                    "type": "person",
                    "org": org.strip(),
                    "role": role.strip(),
                    "source": "attendees_line",
                    "confidence": 0.85,
                })

    # 3. Organization context extraction
    for match in _ORG_CONTEXT.finditer(content):
        org_name = match.group(1).strip()
        if len(org_name) > 2 and org_name.lower() not in seen_names:
            canonical, _ = resolve_entity(org_name, "organization")
            seen_names.add(canonical.lower())
            entities.append({
                "name": canonical,
                "type": "organization",
                "org": "",
                "role": "",
                "source": "context_pattern",
                "confidence": 0.6,
            })

    # 4. Capitalized name patterns in body (lowest confidence)
    for match in _NAME_RE.finditer(content):
        name = match.group(1).strip()
        if name.lower() not in seen_names and not _is_notetaker(name) and len(name) > 4:
            # Skip common false positives
            if name.lower() in _COMMON_PHRASES:
                continue
            canonical, _ = resolve_entity(name, "person")
            if canonical.lower() not in seen_names:
                seen_names.add(canonical.lower())
                entities.append({
                    "name": canonical,
                    "type": "person",
                    "org": "",
                    "role": "",
                    "source": "name_pattern",
                    "confidence": 0.4,
                })

    return entities


# Common phrases that look like names but aren't
_COMMON_PHRASES = {
    "next steps", "action items", "follow up", "key takeaways",
    "meeting notes", "open questions", "main topics", "dear team",
    "quick update", "status update", "project update", "weekly sync",
    "daily standup", "sprint review", "sprint planning", "due diligence",
    "term sheet", "pitch deck", "product market", "general partner",
    "managing director", "vice president", "chief executive",
    "united states", "new york", "san francisco", "los angeles",
}


# ---------------------------------------------------------------------------
# Tier 1: Agent-powered extraction (primary)
# ---------------------------------------------------------------------------

_EXTRACTION_PROMPT = """\
Analyze the following document and extract all named entities (people and organizations).

For each entity, provide:
- name: full canonical name
- type: "person" or "organization"
- org: organization they belong to (if mentioned, for people)
- role: their role/title (if mentioned, for people)
- context: a brief note on why this entity is relevant

Return ONLY valid JSON — an array of objects. No markdown, no commentary.

Example output:
[
  {{"name": "Kate Levchuk", "type": "person", "org": "Andreessen Horowitz", "role": "Partner", "context": "Attending pitch meeting"}},
  {{"name": "Andreessen Horowitz", "type": "organization", "org": "", "role": "", "context": "VC firm, potential investor"}}
]

If no entities are found, return an empty array: []

---

Title: {title}

Content:
{content}
"""


def _extract_agent(content: str, title: str = "") -> list[dict]:
    """
    Agent-powered entity extraction (Tier 1).

    Uses Claude via subprocess (claude CLI) to analyze content.
    Falls back to heuristic if agent is unavailable.
    """
    prompt = _EXTRACTION_PROMPT.format(
        title=title,
        content=content[:8000],  # Limit to avoid token overflow
    )

    try:
        result = subprocess.run(
            ["claude", "--print", "-m", prompt],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            logger.warning("Agent extraction failed (rc=%d), falling back to heuristic", result.returncode)
            return []

        # Parse JSON from output
        output = result.stdout.strip()
        # Try to find JSON array in the output
        start = output.find("[")
        end = output.rfind("]")
        if start >= 0 and end > start:
            raw_entities = json.loads(output[start:end + 1])
        else:
            logger.warning("No JSON array found in agent output")
            return []

        # Normalize and resolve each entity
        entities = []
        for raw in raw_entities:
            name = raw.get("name", "").strip()
            etype = raw.get("type", "person")
            if not name:
                continue
            canonical, _ = resolve_entity(name, etype)
            entities.append({
                "name": canonical,
                "type": etype,
                "org": raw.get("org", ""),
                "role": raw.get("role", ""),
                "context": raw.get("context", ""),
                "source": "agent",
                "confidence": 0.95,
            })
        return entities

    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
        logger.warning("Agent extraction unavailable (%s), falling back to heuristic", exc)
        return []
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("Agent output parse error (%s), falling back to heuristic", exc)
        return []


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_entities(
    content: str,
    title: str = "",
    frontmatter: Optional[dict] = None,
    use_agent: bool = True,
) -> list[dict]:
    """
    Extract named entities from content.

    Uses agent-powered extraction when available, with heuristic fallback.
    Deduplicates and merges results from both tiers.

    Args:
        content: the note body text.
        title: the note title (helps with context).
        frontmatter: parsed frontmatter dict (optional).
        use_agent: if True, attempt agent-powered extraction first.

    Returns:
        list of dicts: {name, type, org, role, source, confidence}
    """
    entities = []

    # Tier 1: Agent extraction
    if use_agent:
        agent_results = _extract_agent(content, title)
        if agent_results:
            entities.extend(agent_results)

    # Tier 2: Heuristic extraction (always runs — catches what agent misses)
    heuristic_results = _extract_heuristic(content, title, frontmatter)

    # Merge: agent results take priority, add heuristic-only entities
    seen = {e["name"].lower() for e in entities}
    for entity in heuristic_results:
        if entity["name"].lower() not in seen:
            entities.append(entity)
            seen.add(entity["name"].lower())

    return entities


def extract_entities_batch(
    vault_path: Optional[str] = None,
    dry_run: bool = True,
    use_agent: bool = False,
) -> dict:
    """
    Batch extract entities from all notes that haven't been processed yet.

    Designed for curator cycle step 3 (entity extraction).

    Args:
        vault_path: root of the Obsidian vault.
        dry_run: if True, report without writing.
        use_agent: if True, use agent extraction (slower but better).

    Returns:
        dict with processed, entities_found, profiles_created, etc.
    """
    if vault_path is None:
        vault_path = os.environ.get(
            "LACP_OBSIDIAN_VAULT",
            os.path.expanduser("~/obsidian/vault"),
        )

    vault = Path(vault_path)
    if not vault.exists():
        return {"error": "vault_not_found", "path": str(vault_path)}

    skip_dirs = {".obsidian", "archive", "_metadata", ".trash"}
    results = {
        "processed": 0,
        "skipped": 0,
        "entities_found": 0,
        "new_entities": 0,
        "dry_run": dry_run,
        "details": [],
    }

    for md_file in sorted(vault.rglob("*.md")):
        # Skip system directories and index files
        rel = md_file.relative_to(vault)
        if any(part in skip_dirs for part in rel.parts):
            continue
        if md_file.name == "index.md":
            continue

        try:
            content = md_file.read_text(encoding="utf-8")
        except (IOError, UnicodeDecodeError):
            continue

        fm = _parse_frontmatter(content)

        # Skip if already processed for entities
        if fm.get("entities_extracted"):
            results["skipped"] += 1
            continue

        results["processed"] += 1

        # Strip frontmatter from body
        body = content
        if content.startswith("---"):
            end = content.find("---", 3)
            if end != -1:
                body = content[end + 3:]

        entities = extract_entities(
            body,
            title=fm.get("title", md_file.stem),
            frontmatter=fm,
            use_agent=use_agent,
        )

        if entities:
            results["entities_found"] += len(entities)
            results["details"].append({
                "file": str(rel),
                "entities": [{"name": e["name"], "type": e["type"]} for e in entities],
            })

        # Mark as processed (add frontmatter flag)
        if not dry_run and entities:
            _mark_entities_extracted(md_file, content, entities)

    return results


def _mark_entities_extracted(file_path: Path, content: str, entities: list[dict]):
    """Add entities_extracted flag and entity list to frontmatter."""
    from datetime import datetime, timezone

    fm = _parse_frontmatter(content)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    entity_names = [e["name"] for e in entities]

    if content.startswith("---"):
        end = content.find("---", 3)
        if end != -1:
            # Insert before closing ---
            fm_section = content[3:end].rstrip()
            body = content[end + 3:]
            fm_section += f"\nentities_extracted: {now}\n"
            fm_section += f"entities: {json.dumps(entity_names)}\n"
            new_content = f"---{fm_section}---{body}"
            file_path.write_text(new_content, encoding="utf-8")
    else:
        # No frontmatter — prepend one
        header = (
            f"---\n"
            f"entities_extracted: {now}\n"
            f"entities: {json.dumps(entity_names)}\n"
            f"---\n\n"
        )
        file_path.write_text(header + content, encoding="utf-8")
