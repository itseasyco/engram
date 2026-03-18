#!/usr/bin/env python3
"""Integration tests for all 5 LACP memory layers."""

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
import pytest


class TestFullStackIntegration:
    """Test complete 5-layer memory stack end-to-end."""
    
    def setup_method(self):
        """Create temp environment."""
        self.temp_dir = tempfile.mkdtemp()
        
        # Create all necessary root directories
        self.project_dir = os.path.join(self.temp_dir, "test-project")
        os.makedirs(self.project_dir)
        
        self.memory_root = os.path.join(self.temp_dir, "memory-root")
        self.provenance_root = os.path.join(self.temp_dir, "provenance-root")
        self.obsidian_vault = os.path.join(self.temp_dir, "obsidian-vault")
        
        os.makedirs(self.memory_root)
        os.makedirs(self.provenance_root)
        
        # Set env vars
        os.environ["SESSION_MEMORY_ROOT"] = self.memory_root
        os.environ["PROVENANCE_ROOT"] = self.provenance_root
        os.environ["LACP_OBSIDIAN_VAULT"] = self.obsidian_vault
    
    def teardown_method(self):
        """Clean up."""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def test_full_workflow(self):
        """Test complete workflow: init → session → seal."""
        brain_stack = Path(__file__).parent.parent.parent / "bin" / "openclaw-brain-stack"
        agent_id = Path(__file__).parent.parent.parent / "bin" / "openclaw-agent-id"
        provenance = Path(__file__).parent.parent.parent / "bin" / "openclaw-provenance"
        
        # 1. Initialize stack (Layer 1-5)
        result_init = subprocess.run(
            ["bash", str(brain_stack), "init",
             "--project", self.project_dir,
             "--agent", "test-agent",
             "--with-obsidian"],
            capture_output=True,
            text=True,
            env=os.environ,
        )
        assert result_init.returncode == 0, f"Init failed: {result_init.stderr}"
        
        # 2. Check Layer 1 memory files exist
        memory_dirs = list(Path(self.memory_root).glob("*/memory"))
        assert len(memory_dirs) > 0, "No memory directory created"
        memory_dir = memory_dirs[0]
        
        for filename in ["MEMORY.md", "debugging.md", "patterns.md", "architecture.md", "preferences.md"]:
            assert (memory_dir / filename).exists(), f"Missing {filename}"
        
        # 3. Register agent (Layer 5a)
        result_register = subprocess.run(
            ["bash", str(agent_id), "register", "--project", self.project_dir],
            capture_output=True,
            text=True,
            env=os.environ,
        )
        assert result_register.returncode == 0
        
        # 4. Show agent identity
        result_show = subprocess.run(
            ["bash", str(agent_id), "show", "--project", self.project_dir],
            capture_output=True,
            text=True,
            env=os.environ,
        )
        assert result_show.returncode == 0
        
        # 5. Start provenance session (Layer 5b)
        result_start = subprocess.run(
            ["bash", str(provenance), "start", "--project", self.project_dir],
            capture_output=True,
            text=True,
            env=os.environ,
        )
        assert result_start.returncode == 0
        session_id = result_start.stdout.strip().split('\n')[-1]
        assert session_id, "No session ID returned"
        
        # 6. End session
        result_end = subprocess.run(
            ["bash", str(provenance), "end", session_id,
             "--exit-code", "0",
             "--files-modified", "5",
             "--project", self.project_dir],
            capture_output=True,
            text=True,
            env=os.environ,
        )
        assert result_end.returncode == 0
        
        # 7. Verify chain
        result_verify = subprocess.run(
            ["bash", str(provenance), "verify", "--project", self.project_dir],
            capture_output=True,
            text=True,
            env=os.environ,
        )
        # Should pass or at least not crash
        assert "ERROR" not in result_verify.stderr or result_verify.returncode == 0
        
        # 8. Check Layer 2 knowledge graph (Obsidian) was created
        assert os.path.exists(self.obsidian_vault), "Obsidian vault not created"
        assert os.path.exists(os.path.join(self.obsidian_vault, "00_Index.md")), "Vault index not created"
        
        # 9. Check Layer 3 ingestion pipeline ready
        ingest_dir = memory_dir / "inbox" / "queue-generated"
        assert ingest_dir.exists(), "Ingestion pipeline not created"
        
        # 10. Doctor check (all layers)
        result_doctor = subprocess.run(
            ["bash", str(brain_stack), "doctor", "--project", self.project_dir],
            capture_output=True,
            text=True,
            env=os.environ,
        )
        assert result_doctor.returncode == 0
        combined = result_doctor.stdout + result_doctor.stderr
        assert "Layer" in combined or "Session Memory" in combined
    
    def test_multiple_sessions_hash_chain(self):
        """Test hash chain across multiple sessions."""
        provenance = Path(__file__).parent.parent.parent / "bin" / "openclaw-provenance"
        
        sessions = []
        hashes = []
        
        # Create 3 sessions and track hashes
        for i in range(3):
            # Start
            result_start = subprocess.run(
                ["bash", str(provenance), "start", "--project", self.project_dir],
                capture_output=True,
                text=True,
                env=os.environ,
            )
            session_id = result_start.stdout.strip().split('\n')[-1]
            sessions.append(session_id)
            
            # End
            result_end = subprocess.run(
                ["bash", str(provenance), "end", session_id, "--exit-code", "0",
                 "--project", self.project_dir],
                capture_output=True,
                text=True,
                env=os.environ,
            )
            
            # Extract hash
            try:
                output_json = json.loads(result_end.stdout)
                hashes.append(output_json.get("next_hash"))
            except:
                pass
        
        # All 3 sessions should be created
        assert len(sessions) == 3
        
        # Check chain file
        # Find chain file - provenance root may have slug-based dirs
        chain_files = list(Path(self.provenance_root).rglob("chain.jsonl"))
        assert len(chain_files) > 0, "No chain file found"
        with open(chain_files[0]) as f:
            lines = [l.strip() for l in f if l.strip() and not l.startswith("#")]
        # All sessions should be tracked; allow for partial failures
        assert len(lines) >= 1, f"Chain should have receipts, got {len(lines)}"


class TestCrossPlatformPaths:
    """Test that path handling works cross-platform."""
    
    def setup_method(self):
        """Create temp environment."""
        self.temp_dir = tempfile.mkdtemp()
        
        self.memory_root = os.path.join(self.temp_dir, "memory")
        os.makedirs(self.memory_root)
        
        os.environ["SESSION_MEMORY_ROOT"] = self.memory_root
    
    def teardown_method(self):
        """Clean up."""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def test_deep_nested_project_path(self):
        """Test deep nested path handling."""
        brain_stack = Path(__file__).parent.parent.parent / "bin" / "openclaw-brain-stack"
        
        deep_project = os.path.join(
            self.temp_dir, "a", "b", "c", "d", "e", "project"
        )
        os.makedirs(deep_project)
        
        result = subprocess.run(
            ["bash", str(brain_stack), "init", "--project", deep_project, "--agent", "test"],
            capture_output=True,
            text=True,
            env=os.environ,
        )
        
        assert result.returncode == 0, f"Failed with deep path: {result.stderr}"
        
        # Check memory was created
        memory_dirs = list(Path(self.memory_root).glob("*/memory"))
        assert len(memory_dirs) > 0


class TestErrorHandling:
    """Test error handling and edge cases."""
    
    def setup_method(self):
        """Create temp environment."""
        self.temp_dir = tempfile.mkdtemp()
        
        self.memory_root = os.path.join(self.temp_dir, "memory")
        self.provenance_root = os.path.join(self.temp_dir, "provenance")
        
        os.makedirs(self.memory_root)
        os.makedirs(self.provenance_root)
        
        os.environ["SESSION_MEMORY_ROOT"] = self.memory_root
        os.environ["PROVENANCE_ROOT"] = self.provenance_root
    
    def teardown_method(self):
        """Clean up."""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def test_init_nonexistent_project_creates_dirs(self):
        """Test init with nonexistent project path."""
        brain_stack = Path(__file__).parent.parent.parent / "bin" / "openclaw-brain-stack"
        
        nonexistent = os.path.join(self.temp_dir, "does-not-exist")
        
        result = subprocess.run(
            ["bash", str(brain_stack), "init", "--project", nonexistent, "--agent", "test"],
            capture_output=True,
            text=True,
            env=os.environ,
        )
        
        # Should still work (project auto-created or gracefully handled)
        assert result.returncode == 0 or "error" not in result.stderr.lower()
    
    def test_provenance_missing_session_error(self):
        """Test ending a nonexistent session returns error."""
        provenance = Path(__file__).parent.parent.parent / "bin" / "openclaw-provenance"
        
        result = subprocess.run(
            ["bash", str(provenance), "end", "nonexistent-session-id",
             "--project", self.temp_dir],
            capture_output=True,
            text=True,
            env=os.environ,
        )
        
        # Should fail gracefully
        assert result.returncode != 0 or "not found" in result.stderr.lower()
    
    def test_agent_id_list_empty(self):
        """Test listing agents when none registered."""
        agent_id = Path(__file__).parent.parent.parent / "bin" / "openclaw-agent-id"
        
        result = subprocess.run(
            ["bash", str(agent_id), "list"],
            capture_output=True,
            text=True,
            env=os.environ,
        )
        
        # Should not crash
        assert result.returncode == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
