"""Tests for overall plugin structure and integrity."""

import json
import os
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).parent.parent.parent


class TestPluginFiles:
    """Test all required files exist."""

    def test_plugin_json_exists(self):
        # plugin.json may be at root or in hooks/
        assert (PLUGIN_ROOT / "hooks" / "plugin.json").exists() or (PLUGIN_ROOT.parent / "plugin.json").exists()

    def test_readme_exists(self):
        assert (PLUGIN_ROOT.parent / "README.md").exists()

    def test_changelog_exists(self):
        assert (PLUGIN_ROOT.parent / "CHANGELOG.md").exists()

    def test_setup_exists(self):
        assert (PLUGIN_ROOT.parent / "SETUP.md").exists()

    def test_install_script_exists(self):
        assert (PLUGIN_ROOT.parent / "INSTALL.sh").exists()

    def test_license_exists(self):
        assert (PLUGIN_ROOT.parent / "LICENSE").exists()


class TestBinScripts:
    """Test all bin scripts exist and are executable."""

    EXPECTED_SCRIPTS = [
        "openclaw-gated-run",
        "openclaw-memory-init",
        "openclaw-memory-append",
        "openclaw-route",
        "openclaw-verify",
        "openclaw-brain-stack",
        "openclaw-brain-code",
        "openclaw-brain-graph",
        "openclaw-brain-ingest",
        "openclaw-agent-id",
        "openclaw-provenance",
        "openclaw-brain-doctor",
        "openclaw-brain-expand",
        "openclaw-obsidian",
        "openclaw-repo-research-sync",
    ]

    def test_all_scripts_exist(self):
        bin_dir = PLUGIN_ROOT / "bin"
        for script in self.EXPECTED_SCRIPTS:
            assert (bin_dir / script).exists(), f"Missing: {script}"

    def test_all_scripts_executable(self):
        bin_dir = PLUGIN_ROOT / "bin"
        for script in self.EXPECTED_SCRIPTS:
            path = bin_dir / script
            assert os.access(path, os.X_OK), f"Not executable: {script}"

    def test_script_count(self):
        bin_dir = PLUGIN_ROOT / "bin"
        scripts = [f for f in bin_dir.iterdir() if f.is_file() and not f.name.startswith('.') and f.name != 'test_gated_run.sh']
        assert len(scripts) >= 15, f"Expected 15+ scripts, found {len(scripts)}"

    def test_bash_scripts_have_shebang(self):
        bin_dir = PLUGIN_ROOT / "bin"
        for script in self.EXPECTED_SCRIPTS:
            path = bin_dir / script
            first_line = path.read_text().split('\n')[0]
            assert first_line.startswith('#!'), f"Missing shebang: {script}"

    def test_no_windows_line_endings(self):
        bin_dir = PLUGIN_ROOT / "bin"
        for script in self.EXPECTED_SCRIPTS:
            path = bin_dir / script
            content = path.read_bytes()
            assert b'\r\n' not in content, f"Windows line endings in: {script}"


class TestHookHandlers:
    """Test hook handler files."""

    EXPECTED_HANDLERS = [
        "session-start.py",
        "pretool-guard.py",
        "stop-quality-gate.py",
        "write-validate.py",
    ]

    def test_all_handlers_exist(self):
        handlers_dir = PLUGIN_ROOT / "hooks" / "handlers"
        for handler in self.EXPECTED_HANDLERS:
            assert (handlers_dir / handler).exists(), f"Missing: {handler}"

    def test_handlers_are_python(self):
        handlers_dir = PLUGIN_ROOT / "hooks" / "handlers"
        for handler in self.EXPECTED_HANDLERS:
            content = (handlers_dir / handler).read_text()
            assert "def " in content or "class " in content


class TestProfiles:
    """Test execution profiles."""

    EXPECTED_PROFILES = [
        "minimal-stop.json",
        "balanced.json",
        "hardened-exec.json",
    ]

    def test_all_profiles_exist(self):
        profiles_dir = PLUGIN_ROOT / "hooks" / "profiles"
        for profile in self.EXPECTED_PROFILES:
            assert (profiles_dir / profile).exists(), f"Missing: {profile}"

    def test_profiles_are_valid_json(self):
        profiles_dir = PLUGIN_ROOT / "hooks" / "profiles"
        for profile in self.EXPECTED_PROFILES:
            content = (profiles_dir / profile).read_text()
            data = json.loads(content)
            assert isinstance(data, dict)

    def test_profiles_have_hooks(self):
        profiles_dir = PLUGIN_ROOT / "hooks" / "profiles"
        for profile in self.EXPECTED_PROFILES:
            data = json.loads((profiles_dir / profile).read_text())
            assert "hooks" in data or "enabled_hooks" in data or any(
                "hook" in str(k).lower() for k in data.keys()
            )


class TestPolicyConfig:
    """Test policy configuration."""

    def test_risk_policy_exists(self):
        assert (PLUGIN_ROOT / "policy" / "risk-policy.json").exists()

    def test_risk_policy_valid_json(self):
        content = (PLUGIN_ROOT / "policy" / "risk-policy.json").read_text()
        data = json.loads(content)
        assert isinstance(data, dict)

    def test_risk_policy_has_tiers(self):
        data = json.loads((PLUGIN_ROOT / "policy" / "risk-policy.json").read_text())
        assert "tiers" in data

    def test_risk_policy_has_rules(self):
        data = json.loads((PLUGIN_ROOT / "policy" / "risk-policy.json").read_text())
        assert "rules" in data


class TestConfigFile:
    """Test configuration file."""

    def test_config_file_exists(self):
        assert (PLUGIN_ROOT / "config" / ".engram.env").exists()

    def test_config_has_layer_sections(self):
        content = (PLUGIN_ROOT / "config" / ".engram.env").read_text()
        for layer_num in range(1, 6):
            assert f"Layer {layer_num}" in content


class TestDangerousPatterns:
    """Test dangerous patterns YAML."""

    def test_patterns_file_exists(self):
        assert (PLUGIN_ROOT / "hooks" / "rules" / "dangerous-patterns.yaml").exists()

    def test_patterns_file_not_empty(self):
        path = PLUGIN_ROOT / "hooks" / "rules" / "dangerous-patterns.yaml"
        assert path.stat().st_size > 100


class TestDirectoryStructure:
    """Test overall directory structure."""

    def test_bin_dir_exists(self):
        assert (PLUGIN_ROOT / "bin").is_dir()

    def test_hooks_dir_exists(self):
        assert (PLUGIN_ROOT / "hooks").is_dir()

    def test_policy_dir_exists(self):
        assert (PLUGIN_ROOT / "policy").is_dir()

    def test_memory_dir_exists(self):
        assert (PLUGIN_ROOT / "memory").is_dir()

    def test_config_dir_exists(self):
        assert (PLUGIN_ROOT / "config").is_dir()

    def test_hooks_handlers_dir_exists(self):
        assert (PLUGIN_ROOT / "hooks" / "handlers").is_dir()

    def test_hooks_profiles_dir_exists(self):
        assert (PLUGIN_ROOT / "hooks" / "profiles").is_dir()

    def test_hooks_rules_dir_exists(self):
        assert (PLUGIN_ROOT / "hooks" / "rules").is_dir()

    def test_hooks_tests_dir_exists(self):
        assert (PLUGIN_ROOT / "hooks" / "tests").is_dir()
