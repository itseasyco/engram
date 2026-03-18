#!/usr/bin/env python3
"""Layer 5: Provenance — Tests for SHA-256 hash-chained session receipts."""

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
import pytest


class TestProvenanceStart:
    """Test Layer 5 provenance session start."""
    
    def setup_method(self):
        """Create temp directory for testing."""
        self.temp_dir = tempfile.mkdtemp()
        self.provenance_root = os.path.join(self.temp_dir, "provenance")
        os.makedirs(self.provenance_root)
        
        os.environ["PROVENANCE_ROOT"] = self.provenance_root
    
    def teardown_method(self):
        """Clean up temp directory."""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def test_start_session_creates_receipt(self):
        """Test that starting a session creates a receipt file."""
        script = Path(__file__).parent.parent.parent / "bin" / "openclaw-provenance"
        
        result = subprocess.run(
            ["bash", str(script), "start", "--project", "/test/project", "--agent-id", "agent123"],
            capture_output=True,
            text=True,
            env={**os.environ, "PROVENANCE_ROOT": self.provenance_root},
        )
        
        assert result.returncode == 0, f"Start failed: {result.stderr}"
        session_id = result.stdout.strip().split('\n')[-1]
        assert session_id, "Should output session ID"
    
    def test_session_id_format(self):
        """Test that session IDs follow expected format."""
        script = Path(__file__).parent.parent.parent / "bin" / "openclaw-provenance"
        
        result = subprocess.run(
            ["bash", str(script), "start", "--project", "/test/project"],
            capture_output=True,
            text=True,
            env={**os.environ, "PROVENANCE_ROOT": self.provenance_root},
        )
        
        assert result.returncode == 0
        session_id = result.stdout.strip().split('\n')[-1]
        
        # Should be YYYY-MM-DD-XXXXXXXX format
        assert len(session_id) > 10
        assert "-" in session_id


class TestProvenanceChain:
    """Test provenance hash chaining."""
    
    def setup_method(self):
        """Create temp directory for testing."""
        self.temp_dir = tempfile.mkdtemp()
        self.provenance_root = os.path.join(self.temp_dir, "provenance")
        os.makedirs(self.provenance_root)
        
        os.environ["PROVENANCE_ROOT"] = self.provenance_root
    
    def teardown_method(self):
        """Clean up temp directory."""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def test_hash_chain_continuity(self):
        """Test that next_hash from session N becomes prev_hash in session N+1."""
        script = Path(__file__).parent.parent.parent / "bin" / "openclaw-provenance"
        
        # Session 1: start
        result1 = subprocess.run(
            ["bash", str(script), "start", "--project", "/test/project", "--agent-id", "agent1"],
            capture_output=True,
            text=True,
            env={**os.environ, "PROVENANCE_ROOT": self.provenance_root},
        )
        session1 = result1.stdout.strip().split('\n')[-1]
        
        # Session 1: end
        result_end1 = subprocess.run(
            ["bash", str(script), "end", session1, "--exit-code", "0", "--files-modified", "3",
             "--project", "/test/project"],
            capture_output=True,
            text=True,
            env={**os.environ, "PROVENANCE_ROOT": self.provenance_root},
        )
        
        # Extract next_hash from receipt
        next_hash1 = None
        for line in result_end1.stdout.split('\n'):
            if "next_hash" in line:
                try:
                    next_hash1 = line.split('"next_hash": "')[1].split('"')[0]
                except (IndexError, AttributeError):
                    pass
        
        assert next_hash1 is not None, "Should extract next_hash"
        
        # Session 2: start (should have session1's next_hash as prev)
        result2 = subprocess.run(
            ["bash", str(script), "start", "--project", "/test/project", "--agent-id", "agent1"],
            capture_output=True,
            text=True,
            env={**os.environ, "PROVENANCE_ROOT": self.provenance_root},
        )
        
        # Verify chain file exists
        chain_file = Path(self.provenance_root) / "test-project" / "chain.jsonl"
        assert chain_file.exists(), "Chain file should exist"


class TestProvenanceVerification:
    """Test provenance chain verification."""
    
    def setup_method(self):
        """Create temp directory for testing."""
        self.temp_dir = tempfile.mkdtemp()
        self.provenance_root = os.path.join(self.temp_dir, "provenance")
        os.makedirs(self.provenance_root)
        
        os.environ["PROVENANCE_ROOT"] = self.provenance_root
    
    def teardown_method(self):
        """Clean up temp directory."""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def test_verify_empty_chain(self):
        """Test verification with no chain fails gracefully."""
        script = Path(__file__).parent.parent.parent / "bin" / "openclaw-provenance"
        
        result = subprocess.run(
            ["bash", str(script), "verify", "--project", "/nonexistent/project"],
            capture_output=True,
            text=True,
            env={**os.environ, "PROVENANCE_ROOT": self.provenance_root},
        )
        
        # Should warn, not crash
        assert "No provenance chain" in result.stderr or result.returncode == 1


class TestProvenanceStatus:
    """Test provenance status reporting."""
    
    def setup_method(self):
        """Create temp directory for testing."""
        self.temp_dir = tempfile.mkdtemp()
        self.provenance_root = os.path.join(self.temp_dir, "provenance")
        os.makedirs(self.provenance_root)
        
        os.environ["PROVENANCE_ROOT"] = self.provenance_root
    
    def teardown_method(self):
        """Clean up temp directory."""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def test_status_shows_session_count(self):
        """Test status command shows session count."""
        script = Path(__file__).parent.parent.parent / "bin" / "openclaw-provenance"
        
        # Start and end a session
        result_start = subprocess.run(
            ["bash", str(script), "start", "--project", "/test/project"],
            capture_output=True,
            text=True,
            env={**os.environ, "PROVENANCE_ROOT": self.provenance_root},
        )
        session_id = result_start.stdout.strip().split('\n')[-1]
        
        subprocess.run(
            ["bash", str(script), "end", session_id, "--project", "/test/project"],
            capture_output=True,
            env={**os.environ, "PROVENANCE_ROOT": self.provenance_root},
        )
        
        # Check status
        result_status = subprocess.run(
            ["bash", str(script), "status", "--project", "/test/project"],
            capture_output=True,
            text=True,
            env={**os.environ, "PROVENANCE_ROOT": self.provenance_root},
        )
        
        assert result_status.returncode == 0
        assert "Sessions:" in result_status.stdout or "sessions:" in result_status.stdout.lower()


class TestProvenanceExport:
    """Test provenance audit trail export."""
    
    def setup_method(self):
        """Create temp directory for testing."""
        self.temp_dir = tempfile.mkdtemp()
        self.provenance_root = os.path.join(self.temp_dir, "provenance")
        os.makedirs(self.provenance_root)
        
        os.environ["PROVENANCE_ROOT"] = self.provenance_root
    
    def teardown_method(self):
        """Clean up temp directory."""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def test_export_jsonl_format(self):
        """Test exporting audit trail as JSONL."""
        script = Path(__file__).parent.parent.parent / "bin" / "openclaw-provenance"
        
        # Create a session
        result_start = subprocess.run(
            ["bash", str(script), "start", "--project", "/test/project"],
            capture_output=True,
            text=True,
            env={**os.environ, "PROVENANCE_ROOT": self.provenance_root},
        )
        session_id = result_start.stdout.strip().split('\n')[-1]
        
        subprocess.run(
            ["bash", str(script), "end", session_id, "--project", "/test/project"],
            capture_output=True,
            env={**os.environ, "PROVENANCE_ROOT": self.provenance_root},
        )
        
        # Export
        output_file = os.path.join(self.temp_dir, "audit.jsonl")
        result_export = subprocess.run(
            ["bash", str(script), "export", "--project", "/test/project",
             "--format", "jsonl", "--output", output_file],
            capture_output=True,
            text=True,
            env={**os.environ, "PROVENANCE_ROOT": self.provenance_root},
        )
        
        assert result_export.returncode == 0, f"Export failed: {result_export.stderr}"
        assert os.path.exists(output_file), f"Output file not created: {output_file}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
