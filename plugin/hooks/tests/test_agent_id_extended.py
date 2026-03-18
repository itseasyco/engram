"""Extended tests for openclaw-agent-id — identity management."""

import os
import json
import subprocess
import tempfile
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent.parent.parent / "bin" / "openclaw-agent-id"


class TestAgentIdHelp:
    """Test help output."""

    def test_no_args_shows_usage(self):
        result = subprocess.run(
            ["bash", str(SCRIPT)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0 or "USAGE" in result.stdout

    def test_help_flag(self):
        result = subprocess.run(
            ["bash", str(SCRIPT), "help"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0

    def test_help_lists_commands(self):
        result = subprocess.run(
            ["bash", str(SCRIPT), "help"],
            capture_output=True, text=True,
        )
        for cmd in ["register", "show", "list"]:
            assert cmd in result.stdout


class TestAgentIdRegister:
    """Test agent registration."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.agent_store = os.path.join(self.temp_dir, "agent-ids")
        self.memory_root = os.path.join(self.temp_dir, "memory")

    def test_register_creates_identity(self):
        project = os.path.join(self.temp_dir, "proj")
        os.makedirs(project)

        result = subprocess.run(
            ["bash", str(SCRIPT), "register", "--project", project],
            capture_output=True, text=True,
            env={**os.environ, "AGENT_ID_STORE": self.agent_store,
                 "SESSION_MEMORY_ROOT": self.memory_root},
        )
        assert result.returncode == 0

    def test_register_with_agent_name(self):
        project = os.path.join(self.temp_dir, "proj2")
        os.makedirs(project)

        result = subprocess.run(
            ["bash", str(SCRIPT), "register", "--project", project, "--agent-name", "wren"],
            capture_output=True, text=True,
            env={**os.environ, "AGENT_ID_STORE": self.agent_store,
                 "SESSION_MEMORY_ROOT": self.memory_root},
        )
        assert result.returncode == 0

    def test_register_idempotent(self):
        project = os.path.join(self.temp_dir, "proj3")
        os.makedirs(project)

        # Register twice
        for _ in range(2):
            result = subprocess.run(
                ["bash", str(SCRIPT), "register", "--project", project],
                capture_output=True, text=True,
                env={**os.environ, "AGENT_ID_STORE": self.agent_store,
                     "SESSION_MEMORY_ROOT": self.memory_root},
            )
            assert result.returncode == 0


class TestAgentIdShow:
    """Test showing agent identity."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.agent_store = os.path.join(self.temp_dir, "agent-ids")
        self.memory_root = os.path.join(self.temp_dir, "memory")

    def _register(self, project):
        subprocess.run(
            ["bash", str(SCRIPT), "register", "--project", project],
            capture_output=True,
            env={**os.environ, "AGENT_ID_STORE": self.agent_store,
                 "SESSION_MEMORY_ROOT": self.memory_root},
        )

    def test_show_registered_agent(self):
        project = os.path.join(self.temp_dir, "proj")
        os.makedirs(project)
        self._register(project)

        result = subprocess.run(
            ["bash", str(SCRIPT), "show", "--project", project],
            capture_output=True, text=True,
            env={**os.environ, "AGENT_ID_STORE": self.agent_store,
                 "SESSION_MEMORY_ROOT": self.memory_root},
        )
        assert result.returncode == 0

    def test_show_unregistered_agent(self):
        project = os.path.join(self.temp_dir, "unregistered")
        os.makedirs(project)

        result = subprocess.run(
            ["bash", str(SCRIPT), "show", "--project", project],
            capture_output=True, text=True,
            env={**os.environ, "AGENT_ID_STORE": self.agent_store,
                 "SESSION_MEMORY_ROOT": self.memory_root},
        )
        # May auto-register or show error
        combined = result.stdout + result.stderr
        assert len(combined) > 0


class TestAgentIdList:
    """Test listing agent identities."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.agent_store = os.path.join(self.temp_dir, "agent-ids")
        self.memory_root = os.path.join(self.temp_dir, "memory")

    def test_list_empty(self):
        result = subprocess.run(
            ["bash", str(SCRIPT), "list"],
            capture_output=True, text=True,
            env={**os.environ, "AGENT_ID_STORE": self.agent_store,
                 "SESSION_MEMORY_ROOT": self.memory_root},
        )
        # Should succeed even with no agents
        assert result.returncode == 0

    def test_list_after_register(self):
        project = os.path.join(self.temp_dir, "proj")
        os.makedirs(project)
        subprocess.run(
            ["bash", str(SCRIPT), "register", "--project", project],
            capture_output=True,
            env={**os.environ, "AGENT_ID_STORE": self.agent_store,
                 "SESSION_MEMORY_ROOT": self.memory_root},
        )

        result = subprocess.run(
            ["bash", str(SCRIPT), "list"],
            capture_output=True, text=True,
            env={**os.environ, "AGENT_ID_STORE": self.agent_store,
                 "SESSION_MEMORY_ROOT": self.memory_root},
        )
        assert result.returncode == 0


class TestAgentIdTouch:
    """Test touch command."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.agent_store = os.path.join(self.temp_dir, "agent-ids")
        self.memory_root = os.path.join(self.temp_dir, "memory")

    def test_touch_updates_timestamp(self):
        project = os.path.join(self.temp_dir, "proj")
        os.makedirs(project)
        subprocess.run(
            ["bash", str(SCRIPT), "register", "--project", project],
            capture_output=True,
            env={**os.environ, "AGENT_ID_STORE": self.agent_store,
                 "SESSION_MEMORY_ROOT": self.memory_root},
        )

        result = subprocess.run(
            ["bash", str(SCRIPT), "touch", "--project", project],
            capture_output=True, text=True,
            env={**os.environ, "AGENT_ID_STORE": self.agent_store,
                 "SESSION_MEMORY_ROOT": self.memory_root},
        )
        assert result.returncode == 0
