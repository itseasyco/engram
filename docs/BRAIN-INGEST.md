# Brain Ingest — Layer 3: Ingestion Pipeline

The Ingestion Pipeline converts external content (transcripts, URLs, PDFs, files) into structured, indexed notes in the knowledge graph.

## Architecture

```
Input Sources                    Processing              Output
─────────────                    ──────────              ──────
Transcripts  ─┐
URLs         ─┤                  ┌──────────┐           inbox/queue-generated/
PDFs         ─┼── brain-ingest ──┤ Metadata  ├──────►  ├── transcript_abc123.md
Files        ─┤                  │ Chunking  │          ├── url_def456.md
Audio*       ─┘                  │ Indexing   │          ├── pdf_ghi789.md
                                 └──────────┘           └── index.md
```

## Commands

### Ingest Transcript

```bash
openclaw-brain-ingest transcript ~/obsidian/vault meeting.md \
  --speaker "Alice" --date "2026-03-18"
```

Creates a structured note with speaker attribution and date metadata.

### Ingest URL

```bash
openclaw-brain-ingest url ~/obsidian/vault https://docs.example.com/api \
  --title "API Documentation"
```

Fetches URL content and creates a note with source link.

### Ingest PDF

```bash
openclaw-brain-ingest pdf ~/obsidian/vault report.pdf \
  --title "Q4 Financial Report"
```

Extracts text from PDF and creates a structured note.

### Ingest File

```bash
openclaw-brain-ingest file ~/obsidian/vault notes.txt \
  --title "Meeting Notes"
```

Reads file content (truncated to 2000 chars) and creates a note.

### Rebuild Index

```bash
openclaw-brain-ingest index ~/obsidian/vault --qmd
```

Rebuilds the `inbox/queue-generated/index.md` file. With `--qmd`, triggers QMD re-indexing.

## Note Format

All ingested notes follow this structure:

```markdown
# <Title>

## Metadata
- **Type:** Transcript | URL | PDF | File
- **Source:** <origin info>
- **Ingested:** 2026-03-18T10:30:00

## Content

<extracted content>

---
Ingested by openclaw-brain-ingest
```

## Configuration

Set in `.openclaw-lacp.env`:

```bash
INGEST_WATCH_DIR=/Volumes/Cortex/06-inbox
INGEST_POLL_INTERVAL=6h
INGEST_AUTO_LINK=true
INGEST_CHUNK_SIZE=2000
INGEST_KEEP_PROCESSED=true
INGEST_URL_FETCH_TIMEOUT=30
INGEST_PDF_EXTRACT_IMAGES=false
```

## Storage Layout

```
~/.openclaw/projects/<slug>/memory/
└── inbox/
    ├── queue-generated/
    │   ├── index.md
    │   ├── transcript_abc123.md
    │   ├── url_def456.md
    │   └── pdf_ghi789.md
    └── processed/
        └── <archived files>
```

## Initialization

The ingestion pipeline is automatically initialized when using:

```bash
openclaw-brain-stack init --project . --with-obsidian
# or
openclaw-brain-stack init --project . --auto-ingest
```

This creates the `inbox/queue-generated/` and `inbox/processed/` directories.

## Content Processing

### Transcript Processing
- Preserves speaker attribution
- Adds date metadata
- Full content included

### URL Processing
- Records source URL as clickable link
- Placeholder for fetched content (use MCP `web_fetch` for live fetching)

### PDF Processing
- Records original filename
- Placeholder for extracted text (use MCP PDF tools for extraction)

### File Processing
- Reads text content directly
- Truncates to `INGEST_CHUNK_SIZE` (default: 2000 chars)
- Handles encoding errors gracefully

## Integration

### With Layer 2 (Knowledge Graph)
Ingested notes land in the vault's `05_Inbox/queue-generated/` directory, making them searchable via QMD and Smart-Connections.

### With Layer 1 (Session Memory)
Ingested notes are stored under the project's memory directory for per-project isolation.

### With openclaw-brain-expand
Running `openclaw-brain-expand --layer 3` rebuilds the ingestion index.

## Troubleshooting

**No inbox directory**: Run `openclaw-brain-stack init --auto-ingest` to create it.

**Index out of date**: Run `openclaw-brain-ingest index <vault-path>` to rebuild.

**Large files**: Content is truncated to `INGEST_CHUNK_SIZE`. Adjust in config if needed.
