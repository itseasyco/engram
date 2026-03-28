"""Tests for configuration file and environment variable handling."""

import os
from pathlib import Path

import pytest

CONFIG_FILE = Path(__file__).parent.parent.parent / "config" / ".engram.env"


class TestConfigFileExists:
    """Test config file presence and structure."""

    def test_config_file_exists(self):
        assert CONFIG_FILE.exists()

    def test_config_file_not_empty(self):
        assert CONFIG_FILE.stat().st_size > 0

    def test_config_file_is_valid_env(self):
        content = CONFIG_FILE.read_text()
        for line in content.split('\n'):
            line = line.strip()
            if line and not line.startswith('#'):
                # Must be KEY=VALUE
                assert '=' in line, f"Invalid env line: {line}"


class TestConfigSections:
    """Test all config sections present."""

    def setup_method(self):
        self.content = CONFIG_FILE.read_text()

    def test_layer1_section(self):
        assert "Layer 1: Session Memory" in self.content

    def test_layer2_section(self):
        assert "Layer 2: Knowledge Graph" in self.content

    def test_layer3_section(self):
        assert "Layer 3: Ingestion Pipeline" in self.content

    def test_layer4_section(self):
        assert "Layer 4: Code Intelligence" in self.content

    def test_layer5_section(self):
        assert "Layer 5: Agent Identity" in self.content

    def test_policy_section(self):
        assert "Policy & Routing" in self.content

    def test_hooks_section(self):
        assert "Hooks System" in self.content

    def test_logging_section(self):
        assert "Logging" in self.content

    def test_mcp_section(self):
        assert "MCP Integration" in self.content

    def test_performance_section(self):
        assert "Performance" in self.content

    def test_feature_flags_section(self):
        assert "Feature Flags" in self.content


class TestConfigKeys:
    """Test important config keys are present."""

    def setup_method(self):
        self.content = CONFIG_FILE.read_text()

    def test_session_memory_root(self):
        assert "SESSION_MEMORY_ROOT" in self.content

    def test_obsidian_vault(self):
        assert "LACP_OBSIDIAN_VAULT" in self.content

    def test_provenance_root(self):
        assert "PROVENANCE_ROOT" in self.content

    def test_agent_id_store(self):
        assert "AGENT_ID_STORE" in self.content

    def test_cost_ceiling_keys(self):
        assert "COST_CEILING_SAFE_USD" in self.content
        assert "COST_CEILING_REVIEW_USD" in self.content
        assert "COST_CEILING_CRITICAL_USD" in self.content

    def test_hook_keys(self):
        assert "HOOK_SESSION_START_ENABLED" in self.content
        assert "HOOK_PRETOOL_GUARD_ENABLED" in self.content

    def test_feature_flags(self):
        assert "LACP_LOCAL_FIRST" in self.content
        assert "LACP_WITH_GITNEXUS" in self.content

    def test_local_first_enabled(self):
        # LACP_LOCAL_FIRST should be uncommented and true
        for line in self.content.split('\n'):
            if line.strip().startswith('LACP_LOCAL_FIRST'):
                assert 'true' in line.lower()
                break
        else:
            pytest.fail("LACP_LOCAL_FIRST not found as active config")

    def test_gitnexus_disabled(self):
        for line in self.content.split('\n'):
            if line.strip().startswith('LACP_WITH_GITNEXUS'):
                assert 'false' in line.lower()
                break
        else:
            pytest.fail("LACP_WITH_GITNEXUS not found as active config")


class TestConfigDefaults:
    """Test that commented defaults have valid values."""

    def setup_method(self):
        self.content = CONFIG_FILE.read_text()

    def test_all_commented_lines_have_values(self):
        for line in self.content.split('\n'):
            line = line.strip()
            if line.startswith('# ') and '=' in line and not line.startswith('# =='):
                # Commented config line
                key_val = line.lstrip('# ')
                parts = key_val.split('=', 1)
                assert len(parts) == 2, f"No value for: {line}"
                assert len(parts[1].strip()) > 0, f"Empty value for: {line}"

    def test_no_secrets_in_config(self):
        # Check that no actual secret values are present (not key names)
        for line in self.content.split('\n'):
            stripped = line.strip()
            if stripped.startswith('#') or not stripped:
                continue
            if '=' in stripped:
                value = stripped.split('=', 1)[1].strip()
                assert not value.startswith('sk-'), f"Possible API key: {stripped}"
                assert "password" not in value.lower(), f"Possible password: {stripped}"
