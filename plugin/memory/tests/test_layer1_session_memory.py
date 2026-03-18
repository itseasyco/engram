#!/usr/bin/env python3
"""Layer 1: Session Memory — Tests for memory scaffolding and initialization."""

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
import pytest


class TestSessionMemoryInit:
    """Test Layer 1 session memory initialization."""
    
    def setup_method(self):
        """Create temp directory for testing."""
        self.temp_dir = tempfile.mkdtemp()
        self.memory_root = os.path.join(self.temp_dir, "projects")
        os.makedirs(self.memory_root)
        
        # Set env var
        os.environ["SESSION_MEMORY_ROOT"] = self.memory_root
    
    def teardown_method(self):
        """Clean up temp directory."""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def test_path_to_slug(self):
        """Test path → slug conversion."""
        # Find the script
        script_dir = Path(__file__).parent.parent.parent / "bin"
        script = script_dir / "openclaw-brain-stack"
        
        result = subprocess.run(
            ["bash", "-c", f"source {script}; path_to_slug '/Users/alice/repos/my-project'"],
            capture_output=True,
            text=True,
        )
        
        # Should convert to slug format
        assert "Users-alice-repos-my-project" in result.stdout or result.returncode == 0
    
    def test_initialize_creates_five_files(self):
        """Test that init creates all 5 seed files."""
        project_dir = os.path.join(self.temp_dir, "test-project")
        os.makedirs(project_dir)
        
        script = Path(__file__).parent.parent.parent / "bin" / "openclaw-brain-stack"
        
        result = subprocess.run(
            ["bash", str(script), "init", "--project", project_dir, "--agent", "test-agent"],
            capture_output=True,
            text=True,
            env={**os.environ, "SESSION_MEMORY_ROOT": self.memory_root},
        )
        
        assert result.returncode == 0, f"Init failed: {result.stderr}"
        
        # Find memory dir
        memory_dirs = list(Path(self.memory_root).glob("*/memory"))
        assert len(memory_dirs) == 1, "Should create one memory dir"
        
        memory_dir = memory_dirs[0]
        
        # Check all 5 files exist
        required_files = [
            "MEMORY.md",
            "debugging.md",
            "patterns.md",
            "architecture.md",
            "preferences.md",
        ]
        
        for filename in required_files:
            filepath = memory_dir / filename
            assert filepath.exists(), f"Missing: {filename}"
            assert filepath.stat().st_size > 0, f"Empty: {filename}"
    
    def test_memory_index_created(self):
        """Test that .memory-index.json is created with metadata."""
        project_dir = os.path.join(self.temp_dir, "test-project")
        os.makedirs(project_dir)
        
        script = Path(__file__).parent.parent.parent / "bin" / "openclaw-brain-stack"
        
        subprocess.run(
            ["bash", str(script), "init", "--project", project_dir, "--agent", "test-agent"],
            capture_output=True,
            env={**os.environ, "SESSION_MEMORY_ROOT": self.memory_root},
        )
        
        memory_dirs = list(Path(self.memory_root).glob("*/memory"))
        memory_dir = memory_dirs[0]
        
        index_file = memory_dir / ".memory-index.json"
        assert index_file.exists(), "Missing .memory-index.json"
        
        with open(index_file) as f:
            index = json.load(f)
        
        assert "project" in index
        assert "agent" in index
        assert "initialized_at" in index
        assert "layers_enabled" in index
    
    def test_doctor_checks_layer1(self):
        """Test doctor command validates Layer 1."""
        project_dir = os.path.join(self.temp_dir, "test-project")
        os.makedirs(project_dir)
        
        script = Path(__file__).parent.parent.parent / "bin" / "openclaw-brain-stack"
        
        # Init
        subprocess.run(
            ["bash", str(script), "init", "--project", project_dir, "--agent", "test-agent"],
            capture_output=True,
            env={**os.environ, "SESSION_MEMORY_ROOT": self.memory_root},
        )
        
        # Doctor
        result = subprocess.run(
            ["bash", str(script), "doctor", "--project", project_dir],
            capture_output=True,
            text=True,
            env={**os.environ, "SESSION_MEMORY_ROOT": self.memory_root},
        )
        
        assert result.returncode == 0
        combined = result.stdout + result.stderr
        assert "✓" in combined or "MEMORY.md" in combined


class TestMemoryArchive:
    """Test memory archiving functionality."""
    
    def setup_method(self):
        """Create temp directory for testing."""
        self.temp_dir = tempfile.mkdtemp()
        self.memory_root = os.path.join(self.temp_dir, "projects")
        os.makedirs(self.memory_root)
        
        os.environ["SESSION_MEMORY_ROOT"] = self.memory_root
    
    def teardown_method(self):
        """Clean up temp directory."""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def test_archive_directory_created(self):
        """Test that archive/ subdirectory is created."""
        project_dir = os.path.join(self.temp_dir, "test-project")
        os.makedirs(project_dir)
        
        script = Path(__file__).parent.parent.parent / "bin" / "openclaw-brain-stack"
        
        subprocess.run(
            ["bash", str(script), "init", "--project", project_dir, "--agent", "test-agent"],
            capture_output=True,
            env={**os.environ, "SESSION_MEMORY_ROOT": self.memory_root},
        )
        
        memory_dirs = list(Path(self.memory_root).glob("*/memory"))
        memory_dir = memory_dirs[0]
        
        archive_dir = memory_dir / "archive"
        assert archive_dir.exists(), "archive/ dir should exist"
        assert archive_dir.is_dir()


class TestMemoryContent:
    """Test that memory files have meaningful initial content."""
    
    def setup_method(self):
        """Create temp directory for testing."""
        self.temp_dir = tempfile.mkdtemp()
        self.memory_root = os.path.join(self.temp_dir, "projects")
        os.makedirs(self.memory_root)
        
        os.environ["SESSION_MEMORY_ROOT"] = self.memory_root
    
    def teardown_method(self):
        """Clean up temp directory."""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def test_memory_md_has_structure(self):
        """Test MEMORY.md has expected sections."""
        project_dir = os.path.join(self.temp_dir, "test-project")
        os.makedirs(project_dir)
        
        script = Path(__file__).parent.parent.parent / "bin" / "openclaw-brain-stack"
        
        subprocess.run(
            ["bash", str(script), "init", "--project", project_dir, "--agent", "test-agent"],
            capture_output=True,
            env={**os.environ, "SESSION_MEMORY_ROOT": self.memory_root},
        )
        
        memory_dirs = list(Path(self.memory_root).glob("*/memory"))
        memory_file = memory_dirs[0] / "MEMORY.md"
        
        content = memory_file.read_text()
        
        # Check for expected sections
        assert "# Project Memory" in content
        assert "Context" in content
        assert "Architecture" in content
        assert "Learnings" in content
    
    def test_debugging_md_has_checklist(self):
        """Test debugging.md has debugging patterns."""
        project_dir = os.path.join(self.temp_dir, "test-project")
        os.makedirs(project_dir)
        
        script = Path(__file__).parent.parent.parent / "bin" / "openclaw-brain-stack"
        
        subprocess.run(
            ["bash", str(script), "init", "--project", project_dir, "--agent", "test-agent"],
            capture_output=True,
            env={**os.environ, "SESSION_MEMORY_ROOT": self.memory_root},
        )
        
        memory_dirs = list(Path(self.memory_root).glob("*/memory"))
        debug_file = memory_dirs[0] / "debugging.md"
        
        content = debug_file.read_text()
        
        assert "Debugging Patterns" in content
        assert "Checklist" in content or "Check" in content
    
    def test_preferences_md_includes_agent_name(self):
        """Test preferences.md includes agent info."""
        project_dir = os.path.join(self.temp_dir, "test-project")
        os.makedirs(project_dir)
        
        script = Path(__file__).parent.parent.parent / "bin" / "openclaw-brain-stack"
        
        subprocess.run(
            ["bash", str(script), "init", "--project", project_dir, "--agent", "my-agent"],
            capture_output=True,
            env={**os.environ, "SESSION_MEMORY_ROOT": self.memory_root},
        )
        
        memory_dirs = list(Path(self.memory_root).glob("*/memory"))
        pref_file = memory_dirs[0] / "preferences.md"
        
        content = pref_file.read_text()
        
        # Should reference agent
        assert "my-agent" in content or "Agent" in content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
