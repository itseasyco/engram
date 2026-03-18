"""Extended tests for openclaw-provenance — comprehensive coverage."""

import os
import json
import subprocess
import tempfile
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent.parent.parent / "bin" / "openclaw-provenance"


class TestProvenanceHelp:
    """Test help and usage."""

    def test_no_args_shows_usage(self):
        result = subprocess.run(
            ["bash", str(SCRIPT)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "USAGE" in result.stdout

    def test_help_command(self):
        result = subprocess.run(
            ["bash", str(SCRIPT), "help"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0

    def test_help_flag(self):
        result = subprocess.run(
            ["bash", str(SCRIPT), "--help"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0

    def test_unknown_command_fails(self):
        result = subprocess.run(
            ["bash", str(SCRIPT), "bogus"],
            capture_output=True, text=True,
        )
        assert result.returncode != 0

    def test_help_shows_examples(self):
        result = subprocess.run(
            ["bash", str(SCRIPT), "help"],
            capture_output=True, text=True,
        )
        assert "EXAMPLES" in result.stdout

    def test_help_mentions_all_commands(self):
        result = subprocess.run(
            ["bash", str(SCRIPT), "help"],
            capture_output=True, text=True,
        )
        for cmd in ["start", "end", "verify", "export", "status"]:
            assert cmd in result.stdout


class TestProvenanceStart:
    """Test session start."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.provenance_root = os.path.join(self.temp_dir, "provenance")

    def test_start_returns_session_id(self):
        result = subprocess.run(
            ["bash", str(SCRIPT), "start", "--project", "/test/project"],
            capture_output=True, text=True,
            env={**os.environ, "PROVENANCE_ROOT": self.provenance_root},
        )
        assert result.returncode == 0
        session_id = result.stdout.strip().split('\n')[-1]
        assert len(session_id) > 0

    def test_start_session_id_format(self):
        result = subprocess.run(
            ["bash", str(SCRIPT), "start", "--project", "/test/project"],
            capture_output=True, text=True,
            env={**os.environ, "PROVENANCE_ROOT": self.provenance_root},
        )
        session_id = result.stdout.strip().split('\n')[-1]
        # Format: YYYY-MM-DD-<hex>
        assert "2026" in session_id
        assert "-" in session_id

    def test_start_with_agent_id(self):
        result = subprocess.run(
            ["bash", str(SCRIPT), "start", "--project", "/test/project", "--agent-id", "agent-abc"],
            capture_output=True, text=True,
            env={**os.environ, "PROVENANCE_ROOT": self.provenance_root},
        )
        assert result.returncode == 0

    def test_start_creates_session_file(self):
        result = subprocess.run(
            ["bash", str(SCRIPT), "start", "--project", "/test/project"],
            capture_output=True, text=True,
            env={**os.environ, "PROVENANCE_ROOT": self.provenance_root},
        )
        session_id = result.stdout.strip().split('\n')[-1]

        slug = "test-project"
        session_file = Path(self.provenance_root, slug, ".sessions", f"{session_id}.tmp")
        assert session_file.exists()

    def test_start_session_file_has_prev_hash(self):
        result = subprocess.run(
            ["bash", str(SCRIPT), "start", "--project", "/test/project"],
            capture_output=True, text=True,
            env={**os.environ, "PROVENANCE_ROOT": self.provenance_root},
        )
        session_id = result.stdout.strip().split('\n')[-1]

        slug = "test-project"
        session_file = Path(self.provenance_root, slug, ".sessions", f"{session_id}.tmp")
        content = session_file.read_text()
        assert "prev_hash" in content

    def test_start_logs_to_stderr(self):
        result = subprocess.run(
            ["bash", str(SCRIPT), "start", "--project", "/test/project"],
            capture_output=True, text=True,
            env={**os.environ, "PROVENANCE_ROOT": self.provenance_root},
        )
        assert "[INFO]" in result.stderr or "Starting" in result.stderr

    def test_multiple_starts_create_separate_sessions(self):
        ids = []
        for _ in range(3):
            result = subprocess.run(
                ["bash", str(SCRIPT), "start", "--project", "/test/project"],
                capture_output=True, text=True,
                env={**os.environ, "PROVENANCE_ROOT": self.provenance_root},
            )
            ids.append(result.stdout.strip().split('\n')[-1])

        assert len(set(ids)) == 3  # All unique


class TestProvenanceEnd:
    """Test session end."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.provenance_root = os.path.join(self.temp_dir, "provenance")

    def _start_session(self, project="/test/project"):
        result = subprocess.run(
            ["bash", str(SCRIPT), "start", "--project", project],
            capture_output=True, text=True,
            env={**os.environ, "PROVENANCE_ROOT": self.provenance_root},
        )
        return result.stdout.strip().split('\n')[-1]

    def test_end_session_succeeds(self):
        session_id = self._start_session()

        result = subprocess.run(
            ["bash", str(SCRIPT), "end", session_id, "--project", "/test/project"],
            capture_output=True, text=True,
            env={**os.environ, "PROVENANCE_ROOT": self.provenance_root},
        )
        assert result.returncode == 0

    def test_end_produces_receipt(self):
        session_id = self._start_session()

        result = subprocess.run(
            ["bash", str(SCRIPT), "end", session_id, "--project", "/test/project"],
            capture_output=True, text=True,
            env={**os.environ, "PROVENANCE_ROOT": self.provenance_root},
        )
        receipt = json.loads(result.stdout.strip())
        assert "session_id" in receipt
        assert "next_hash" in receipt
        assert "prev_hash" in receipt

    def test_end_with_exit_code(self):
        session_id = self._start_session()

        result = subprocess.run(
            ["bash", str(SCRIPT), "end", session_id, "--exit-code", "1", "--project", "/test/project"],
            capture_output=True, text=True,
            env={**os.environ, "PROVENANCE_ROOT": self.provenance_root},
        )
        receipt = json.loads(result.stdout.strip())
        assert receipt["execution"]["exit_code"] == 1

    def test_end_with_files_modified(self):
        session_id = self._start_session()

        result = subprocess.run(
            ["bash", str(SCRIPT), "end", session_id,
             "--files-modified", "7", "--project", "/test/project"],
            capture_output=True, text=True,
            env={**os.environ, "PROVENANCE_ROOT": self.provenance_root},
        )
        receipt = json.loads(result.stdout.strip())
        assert receipt["execution"]["files_modified"] == 7

    def test_end_nonexistent_session_fails(self):
        result = subprocess.run(
            ["bash", str(SCRIPT), "end", "nonexistent-session", "--project", "/test/project"],
            capture_output=True, text=True,
            env={**os.environ, "PROVENANCE_ROOT": self.provenance_root},
        )
        assert result.returncode != 0

    def test_end_no_session_id_fails(self):
        result = subprocess.run(
            ["bash", str(SCRIPT), "end"],
            capture_output=True, text=True,
            env={**os.environ, "PROVENANCE_ROOT": self.provenance_root},
        )
        assert result.returncode != 0

    def test_end_appends_to_chain(self):
        session_id = self._start_session()

        subprocess.run(
            ["bash", str(SCRIPT), "end", session_id, "--project", "/test/project"],
            capture_output=True, text=True,
            env={**os.environ, "PROVENANCE_ROOT": self.provenance_root},
        )

        chain_file = Path(self.provenance_root, "test-project", "chain.jsonl")
        assert chain_file.exists()
        lines = [l for l in chain_file.read_text().strip().split('\n') if l.strip()]
        assert len(lines) == 1

    def test_end_cleans_up_session_file(self):
        session_id = self._start_session()
        slug = "test-project"
        session_file = Path(self.provenance_root, slug, ".sessions", f"{session_id}.tmp")
        assert session_file.exists()

        subprocess.run(
            ["bash", str(SCRIPT), "end", session_id, "--project", "/test/project"],
            capture_output=True, text=True,
            env={**os.environ, "PROVENANCE_ROOT": self.provenance_root},
        )
        assert not session_file.exists()

    def test_end_receipt_has_duration(self):
        session_id = self._start_session()

        result = subprocess.run(
            ["bash", str(SCRIPT), "end", session_id, "--project", "/test/project"],
            capture_output=True, text=True,
            env={**os.environ, "PROVENANCE_ROOT": self.provenance_root},
        )
        receipt = json.loads(result.stdout.strip())
        assert "duration_seconds" in receipt["execution"]

    def test_end_receipt_has_timestamps(self):
        session_id = self._start_session()

        result = subprocess.run(
            ["bash", str(SCRIPT), "end", session_id, "--project", "/test/project"],
            capture_output=True, text=True,
            env={**os.environ, "PROVENANCE_ROOT": self.provenance_root},
        )
        receipt = json.loads(result.stdout.strip())
        assert "start_time" in receipt["execution"]
        assert "end_time" in receipt["execution"]


class TestProvenanceVerify:
    """Test chain verification."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.provenance_root = os.path.join(self.temp_dir, "provenance")

    def _create_session(self, project="/test/project"):
        result = subprocess.run(
            ["bash", str(SCRIPT), "start", "--project", project],
            capture_output=True, text=True,
            env={**os.environ, "PROVENANCE_ROOT": self.provenance_root},
        )
        session_id = result.stdout.strip().split('\n')[-1]
        subprocess.run(
            ["bash", str(SCRIPT), "end", session_id, "--project", project],
            capture_output=True, text=True,
            env={**os.environ, "PROVENANCE_ROOT": self.provenance_root},
        )
        return session_id

    def test_verify_single_receipt(self):
        self._create_session()

        result = subprocess.run(
            ["bash", str(SCRIPT), "verify", "--project", "/test/project"],
            capture_output=True, text=True,
            env={**os.environ, "PROVENANCE_ROOT": self.provenance_root},
        )
        assert result.returncode == 0
        combined = result.stdout + result.stderr
        assert "verified" in combined.lower() or "✓" in combined

    def test_verify_multi_receipt_chain(self):
        for _ in range(3):
            self._create_session()

        result = subprocess.run(
            ["bash", str(SCRIPT), "verify", "--project", "/test/project"],
            capture_output=True, text=True,
            env={**os.environ, "PROVENANCE_ROOT": self.provenance_root},
        )
        assert result.returncode == 0

    def test_verify_empty_project_fails(self):
        result = subprocess.run(
            ["bash", str(SCRIPT), "verify", "--project", "/empty/project"],
            capture_output=True, text=True,
            env={**os.environ, "PROVENANCE_ROOT": self.provenance_root},
        )
        assert result.returncode != 0

    def test_verify_tampered_chain_fails(self):
        self._create_session()

        chain_file = Path(self.provenance_root, "test-project", "chain.jsonl")
        content = chain_file.read_text()
        # Tamper with the hash
        tampered = content.replace('"prev_hash":"0000', '"prev_hash":"ffff')
        chain_file.write_text(tampered)

        result = subprocess.run(
            ["bash", str(SCRIPT), "verify", "--project", "/test/project"],
            capture_output=True, text=True,
            env={**os.environ, "PROVENANCE_ROOT": self.provenance_root},
        )
        assert result.returncode != 0


class TestProvenanceExport:
    """Test audit trail export."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.provenance_root = os.path.join(self.temp_dir, "provenance")

    def _create_session(self, project="/test/project"):
        result = subprocess.run(
            ["bash", str(SCRIPT), "start", "--project", project],
            capture_output=True, text=True,
            env={**os.environ, "PROVENANCE_ROOT": self.provenance_root},
        )
        session_id = result.stdout.strip().split('\n')[-1]
        subprocess.run(
            ["bash", str(SCRIPT), "end", session_id, "--project", project],
            capture_output=True, text=True,
            env={**os.environ, "PROVENANCE_ROOT": self.provenance_root},
        )

    def test_export_jsonl(self):
        self._create_session()
        output = os.path.join(self.temp_dir, "audit.jsonl")

        result = subprocess.run(
            ["bash", str(SCRIPT), "export", "--project", "/test/project",
             "--format", "jsonl", "--output", output],
            capture_output=True, text=True,
            env={**os.environ, "PROVENANCE_ROOT": self.provenance_root},
        )
        assert result.returncode == 0
        assert os.path.exists(output)

    def test_export_json(self):
        self._create_session()
        output = os.path.join(self.temp_dir, "audit.json")

        result = subprocess.run(
            ["bash", str(SCRIPT), "export", "--project", "/test/project",
             "--format", "json", "--output", output],
            capture_output=True, text=True,
            env={**os.environ, "PROVENANCE_ROOT": self.provenance_root},
        )
        assert result.returncode == 0
        assert os.path.exists(output)
        content = Path(output).read_text()
        assert content.startswith("[")

    def test_export_csv(self):
        self._create_session()
        output = os.path.join(self.temp_dir, "audit.csv")

        result = subprocess.run(
            ["bash", str(SCRIPT), "export", "--project", "/test/project",
             "--format", "csv", "--output", output],
            capture_output=True, text=True,
            env={**os.environ, "PROVENANCE_ROOT": self.provenance_root},
        )
        assert result.returncode == 0
        assert os.path.exists(output)
        content = Path(output).read_text()
        assert "session_id" in content

    def test_export_empty_chain_fails(self):
        output = os.path.join(self.temp_dir, "audit.jsonl")
        result = subprocess.run(
            ["bash", str(SCRIPT), "export", "--project", "/empty/project",
             "--format", "jsonl", "--output", output],
            capture_output=True, text=True,
            env={**os.environ, "PROVENANCE_ROOT": self.provenance_root},
        )
        assert result.returncode != 0

    def test_export_unknown_format_fails(self):
        self._create_session()
        output = os.path.join(self.temp_dir, "audit.xml")
        result = subprocess.run(
            ["bash", str(SCRIPT), "export", "--project", "/test/project",
             "--format", "xml", "--output", output],
            capture_output=True, text=True,
            env={**os.environ, "PROVENANCE_ROOT": self.provenance_root},
        )
        assert result.returncode != 0


class TestProvenanceStatus:
    """Test status command."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.provenance_root = os.path.join(self.temp_dir, "provenance")

    def test_status_no_data(self):
        result = subprocess.run(
            ["bash", str(SCRIPT), "status", "--project", "/test/project"],
            capture_output=True, text=True,
            env={**os.environ, "PROVENANCE_ROOT": self.provenance_root},
        )
        assert "No provenance data" in result.stdout

    def test_status_with_sessions(self):
        # Create a session
        r = subprocess.run(
            ["bash", str(SCRIPT), "start", "--project", "/test/project"],
            capture_output=True, text=True,
            env={**os.environ, "PROVENANCE_ROOT": self.provenance_root},
        )
        session_id = r.stdout.strip().split('\n')[-1]
        subprocess.run(
            ["bash", str(SCRIPT), "end", session_id, "--project", "/test/project"],
            capture_output=True, text=True,
            env={**os.environ, "PROVENANCE_ROOT": self.provenance_root},
        )

        result = subprocess.run(
            ["bash", str(SCRIPT), "status", "--project", "/test/project"],
            capture_output=True, text=True,
            env={**os.environ, "PROVENANCE_ROOT": self.provenance_root},
        )
        assert "Sessions:" in result.stdout
        assert "1" in result.stdout
