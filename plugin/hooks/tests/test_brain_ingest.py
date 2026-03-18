"""Tests for openclaw-brain-ingest — Layer 3 ingestion pipeline."""

import os
import subprocess
import tempfile
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent.parent.parent / "bin" / "openclaw-brain-ingest"


class TestIngestHelp:
    """Test help output."""

    def test_help_flag(self):
        result = subprocess.run(
            ["python3", str(SCRIPT), "--help"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "Ingest" in result.stdout or "ingest" in result.stdout.lower()


class TestIngestTranscript:
    """Test transcript ingestion."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.vault = os.path.join(self.temp_dir, "vault")
        os.makedirs(self.vault)

    def test_ingest_transcript_basic(self):
        transcript = os.path.join(self.temp_dir, "call.md")
        Path(transcript).write_text("Speaker A: Hello\nSpeaker B: Hi there\n")

        result = subprocess.run(
            ["python3", str(SCRIPT), "transcript", self.vault, transcript],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "Ingested" in result.stdout

    def test_ingest_transcript_with_speaker(self):
        transcript = os.path.join(self.temp_dir, "call2.md")
        Path(transcript).write_text("Meeting notes here.\n")

        result = subprocess.run(
            ["python3", str(SCRIPT), "transcript", self.vault, transcript,
             "--speaker", "Alice", "--date", "2026-03-18"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0

        # Check output file has speaker info
        inbox = Path(self.vault, "inbox", "queue-generated")
        files = list(inbox.glob("transcript_*.md"))
        assert len(files) == 1
        content = files[0].read_text()
        assert "Alice" in content
        assert "2026-03-18" in content

    def test_ingest_transcript_creates_inbox(self):
        transcript = os.path.join(self.temp_dir, "call3.md")
        Path(transcript).write_text("Test\n")

        subprocess.run(
            ["python3", str(SCRIPT), "transcript", self.vault, transcript],
            capture_output=True, text=True,
        )

        inbox = Path(self.vault, "inbox", "queue-generated")
        assert inbox.exists()

    def test_ingest_nonexistent_transcript(self):
        result = subprocess.run(
            ["python3", str(SCRIPT), "transcript", self.vault, "/nonexistent.md"],
            capture_output=True, text=True,
        )
        # Should still succeed (creates note with empty content)
        assert result.returncode == 0


class TestIngestURL:
    """Test URL ingestion."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.vault = os.path.join(self.temp_dir, "vault")
        os.makedirs(self.vault)

    def test_ingest_url_basic(self):
        result = subprocess.run(
            ["python3", str(SCRIPT), "url", self.vault, "https://example.com"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "Ingested" in result.stdout

    def test_ingest_url_with_title(self):
        result = subprocess.run(
            ["python3", str(SCRIPT), "url", self.vault, "https://example.com",
             "--title", "Example Site"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0

        inbox = Path(self.vault, "inbox", "queue-generated")
        files = list(inbox.glob("url_*.md"))
        assert len(files) == 1
        content = files[0].read_text()
        assert "Example Site" in content

    def test_ingest_url_has_source_link(self):
        subprocess.run(
            ["python3", str(SCRIPT), "url", self.vault, "https://docs.example.com/api"],
            capture_output=True, text=True,
        )
        inbox = Path(self.vault, "inbox", "queue-generated")
        files = list(inbox.glob("url_*.md"))
        content = files[0].read_text()
        assert "https://docs.example.com/api" in content


class TestIngestPDF:
    """Test PDF ingestion."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.vault = os.path.join(self.temp_dir, "vault")
        os.makedirs(self.vault)

    def test_ingest_pdf_basic(self):
        pdf = os.path.join(self.temp_dir, "doc.pdf")
        Path(pdf).write_text("fake pdf content")

        result = subprocess.run(
            ["python3", str(SCRIPT), "pdf", self.vault, pdf],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "Ingested" in result.stdout

    def test_ingest_pdf_with_title(self):
        pdf = os.path.join(self.temp_dir, "report.pdf")
        Path(pdf).write_text("fake content")

        result = subprocess.run(
            ["python3", str(SCRIPT), "pdf", self.vault, pdf, "--title", "Q4 Report"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0

        inbox = Path(self.vault, "inbox", "queue-generated")
        files = list(inbox.glob("pdf_*.md"))
        content = files[0].read_text()
        assert "Q4 Report" in content

    def test_ingest_pdf_has_filename(self):
        pdf = os.path.join(self.temp_dir, "annual-report.pdf")
        Path(pdf).write_text("content")

        subprocess.run(
            ["python3", str(SCRIPT), "pdf", self.vault, pdf],
            capture_output=True, text=True,
        )
        inbox = Path(self.vault, "inbox", "queue-generated")
        files = list(inbox.glob("pdf_*.md"))
        content = files[0].read_text()
        assert "annual-report.pdf" in content


class TestIngestFile:
    """Test generic file ingestion."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.vault = os.path.join(self.temp_dir, "vault")
        os.makedirs(self.vault)

    def test_ingest_file_basic(self):
        source = os.path.join(self.temp_dir, "notes.txt")
        Path(source).write_text("Important notes here.\nLine 2.\n")

        result = subprocess.run(
            ["python3", str(SCRIPT), "file", self.vault, source],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "Ingested" in result.stdout

    def test_ingest_file_content_included(self):
        source = os.path.join(self.temp_dir, "data.md")
        Path(source).write_text("# Data\nThis is the content.\n")

        subprocess.run(
            ["python3", str(SCRIPT), "file", self.vault, source],
            capture_output=True, text=True,
        )
        inbox = Path(self.vault, "inbox", "queue-generated")
        files = list(inbox.glob("file_*.md"))
        content = files[0].read_text()
        assert "This is the content." in content

    def test_ingest_file_truncates_large_content(self):
        source = os.path.join(self.temp_dir, "huge.txt")
        Path(source).write_text("x" * 5000)

        subprocess.run(
            ["python3", str(SCRIPT), "file", self.vault, source],
            capture_output=True, text=True,
        )
        inbox = Path(self.vault, "inbox", "queue-generated")
        files = list(inbox.glob("file_*.md"))
        content = files[0].read_text()
        # Content should be truncated to ~2000 chars
        assert len(content) < 4000

    def test_ingest_nonexistent_file(self):
        result = subprocess.run(
            ["python3", str(SCRIPT), "file", self.vault, "/nonexistent.txt"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0  # Creates empty note

    def test_ingest_file_with_title(self):
        source = os.path.join(self.temp_dir, "raw.txt")
        Path(source).write_text("content")

        subprocess.run(
            ["python3", str(SCRIPT), "file", self.vault, source, "--title", "Custom Title"],
            capture_output=True, text=True,
        )
        inbox = Path(self.vault, "inbox", "queue-generated")
        files = list(inbox.glob("file_*.md"))
        content = files[0].read_text()
        assert "Custom Title" in content


class TestIngestIndex:
    """Test vault index command."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.vault = os.path.join(self.temp_dir, "vault")
        os.makedirs(self.vault)

    def test_index_empty_vault(self):
        inbox = Path(self.vault, "inbox", "queue-generated")
        inbox.mkdir(parents=True)

        result = subprocess.run(
            ["python3", str(SCRIPT), "index", self.vault],
            capture_output=True, text=True,
        )
        assert result.returncode == 0

    def test_index_with_files(self):
        inbox = Path(self.vault, "inbox", "queue-generated")
        inbox.mkdir(parents=True)
        (inbox / "note1.md").write_text("# Note 1\n")
        (inbox / "note2.md").write_text("# Note 2\n")

        subprocess.run(
            ["python3", str(SCRIPT), "index", self.vault],
            capture_output=True, text=True,
        )

        index = inbox / "index.md"
        assert index.exists()
        content = index.read_text()
        assert "note1" in content
        assert "note2" in content

    def test_index_excludes_itself(self):
        inbox = Path(self.vault, "inbox", "queue-generated")
        inbox.mkdir(parents=True)
        (inbox / "note1.md").write_text("# Note\n")

        subprocess.run(
            ["python3", str(SCRIPT), "index", self.vault],
            capture_output=True, text=True,
        )

        index = inbox / "index.md"
        content = index.read_text()
        # Index should not list itself
        lines = [l for l in content.split('\n') if l.startswith('- [')]
        for line in lines:
            assert "index" not in line.lower()

    def test_index_with_qmd_flag(self):
        inbox = Path(self.vault, "inbox", "queue-generated")
        inbox.mkdir(parents=True)

        result = subprocess.run(
            ["python3", str(SCRIPT), "index", self.vault, "--qmd"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0


class TestIngestMetadata:
    """Test metadata in ingested notes."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.vault = os.path.join(self.temp_dir, "vault")
        os.makedirs(self.vault)

    def test_transcript_has_type_metadata(self):
        t = os.path.join(self.temp_dir, "t.md")
        Path(t).write_text("content")

        subprocess.run(
            ["python3", str(SCRIPT), "transcript", self.vault, t],
            capture_output=True, text=True,
        )
        inbox = Path(self.vault, "inbox", "queue-generated")
        files = list(inbox.glob("*.md"))
        content = files[0].read_text()
        assert "Type:** Transcript" in content

    def test_url_has_type_metadata(self):
        subprocess.run(
            ["python3", str(SCRIPT), "url", self.vault, "https://example.com"],
            capture_output=True, text=True,
        )
        inbox = Path(self.vault, "inbox", "queue-generated")
        files = list(inbox.glob("*.md"))
        content = files[0].read_text()
        assert "Type:** URL" in content

    def test_all_notes_have_ingested_timestamp(self):
        t = os.path.join(self.temp_dir, "t.md")
        Path(t).write_text("content")

        subprocess.run(
            ["python3", str(SCRIPT), "transcript", self.vault, t],
            capture_output=True, text=True,
        )
        inbox = Path(self.vault, "inbox", "queue-generated")
        files = list(inbox.glob("*.md"))
        content = files[0].read_text()
        assert "Ingested:" in content

    def test_all_notes_have_footer(self):
        subprocess.run(
            ["python3", str(SCRIPT), "url", self.vault, "https://example.com"],
            capture_output=True, text=True,
        )
        inbox = Path(self.vault, "inbox", "queue-generated")
        files = list(inbox.glob("*.md"))
        content = files[0].read_text()
        assert "openclaw-brain-ingest" in content
