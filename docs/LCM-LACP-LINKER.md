# LCM ↔ LACP Cross-Reference Linker

## Overview

The linker creates bidirectional connections between LCM session summaries and LACP vault notes. This enables traceability: you can follow a fact from its session origin to its persistent storage, and vice versa.

## How Cross-References Work

```
LCM Summary (sum_xxx)
    ↓ extract topics
    ↓ find related notes
    ↓ create wikilinks
LACP Vault Note (*.md)
    ↓ append LCM reference
    ↓ verify with hash
Bidirectional Link (verified)
```

### Topic Extraction

The linker extracts topics from LCM summaries by detecting:
- Explicit tags (`#architecture`, `#deployment`)
- Wikilinks (`[[Finix Integration]]`)
- Technical terms (snake_case, kebab-case)
- Proper nouns (capitalized terms, excluding stopwords)

### Note Matching

Related vault notes are found by:
1. Filename matching (highest weight)
2. Content matching (lower weight)
3. Results scored and ranked by relevance

### Link Verification

Each cross-reference includes a SHA-256 hash computed from:
- `summary_id`
- `note_path`
- `timestamp`

This hash can be verified later to detect tampering.

## Usage

### Python API

```python
from lcm_lacp_linker import link_summary_to_vault

result = link_summary_to_vault(
    summary={
        "summary_id": "sum_abc123",
        "content": "Finix handles payment processing for merchants.",
        "project": "easy-api",
    },
    vault_path="/path/to/vault",
)

print(result["link_count"])        # 2
print(result["topics"])            # ["Finix", "payment-processing", ...]
print(result["related_notes"])     # [{path: "projects/finix.md", ...}]
print(result["cross_references"])  # [{link_hash: "abc...", ...}]
```

### Verification

```python
from lcm_lacp_linker import LCMLACPLinker

linker = LCMLACPLinker(vault_path="/path/to/vault")
ref = result["cross_references"][0]
assert linker.verify_link(ref)  # True if untampered
```

### CLI Integration

Cross-references are automatically created when using `openclaw-lacp-promote`:

```bash
# Auto-promote creates cross-references
openclaw-lacp-promote auto --summary sum_abc123 --project easy-api

# Graph sync enriches the Obsidian graph
openclaw-brain-graph sync --from-lcm --summary sum_abc123 --auto-link
```

## Logging

All cross-references are logged to `~/.openclaw/logs/linker.jsonl` in JSONL format for audit.
