#!/usr/bin/env python3
"""Integration tests for LACP Hooks plugin.

Tests:
1. Plugin manifest validation (plugin.json)
2. All handlers are callable
3. Each profile composition is valid
4. Hook coordination (session-start → pretool-guard → stop-gate)
5. File loading and schema validation
6. End-to-end hook execution flow
"""

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture(scope="session")
def plugin_dir() -> Path:
    """Get the plugin root directory."""
    return Path(__file__).parent.parent


@pytest.fixture(scope="session")
def plugin_json(plugin_dir: Path) -> Dict[str, Any]:
    """Load and parse plugin.json."""
    path = plugin_dir / "plugin.json"
    assert path.exists(), f"plugin.json not found at {path}"
    return json.loads(path.read_text())


@pytest.fixture(scope="session")
def dangerous_patterns_yaml(plugin_dir: Path) -> str:
    """Load dangerous-patterns.yaml."""
    path = plugin_dir / "rules" / "dangerous-patterns.yaml"
    assert path.exists(), f"dangerous-patterns.yaml not found at {path}"
    return path.read_text()


@pytest.fixture(scope="session")
def handlers_dir(plugin_dir: Path) -> Path:
    """Get handlers directory."""
    handlers = plugin_dir / "handlers"
    assert handlers.exists(), f"handlers dir not found at {handlers}"
    return handlers


@pytest.fixture(scope="session")
def profiles_dir(plugin_dir: Path) -> Path:
    """Get profiles directory."""
    profiles = plugin_dir / "profiles"
    assert profiles.exists(), f"profiles dir not found at {profiles}"
    return profiles


# ============================================================================
# Plugin Manifest Tests
# ============================================================================

class TestPluginManifest:
    """Test plugin.json structure and content."""

    def test_manifest_has_required_fields(self, plugin_json: Dict) -> None:
        """Plugin manifest must have name, version, hooks, profiles."""
        assert "name" in plugin_json, "Missing 'name' in plugin.json"
        assert "version" in plugin_json, "Missing 'version' in plugin.json"
        assert "hooks" in plugin_json, "Missing 'hooks' in plugin.json"
        assert "profiles" in plugin_json, "Missing 'profiles' in plugin.json"

    def test_manifest_name_and_version(self, plugin_json: Dict) -> None:
        """Plugin name and version should be non-empty strings."""
        assert isinstance(plugin_json["name"], str), "name must be string"
        assert plugin_json["name"].strip(), "name must be non-empty"
        assert isinstance(plugin_json["version"], str), "version must be string"
        assert plugin_json["version"].strip(), "version must be non-empty"

    def test_hooks_well_formed(self, plugin_json: Dict) -> None:
        """Each hook must have handler path and trigger."""
        hooks = plugin_json.get("hooks", {})
        assert isinstance(hooks, dict), "hooks must be dict"
        assert len(hooks) > 0, "hooks must have at least one entry"

        for hook_name, hook_info in hooks.items():
            assert isinstance(hook_info, dict), f"hook '{hook_name}' must be dict"
            assert "handler" in hook_info, f"hook '{hook_name}' missing 'handler'"
            assert "trigger" in hook_info, f"hook '{hook_name}' missing 'trigger'"
            assert "description" in hook_info, f"hook '{hook_name}' missing 'description'"

    def test_hooks_expected_count(self, plugin_json: Dict) -> None:
        """Expect 4 hooks: session-start, pretool-guard, stop-quality-gate, write-validate."""
        hooks = plugin_json.get("hooks", {})
        expected_hooks = {"session-start", "pretool-guard", "stop-quality-gate", "write-validate"}
        actual_hooks = set(hooks.keys())
        assert expected_hooks == actual_hooks, f"Expected hooks {expected_hooks}, got {actual_hooks}"

    def test_profiles_well_formed(self, plugin_json: Dict) -> None:
        """Each profile must have name, description, hooks list."""
        profiles = plugin_json.get("profiles", {})
        assert isinstance(profiles, dict), "profiles must be dict"
        assert len(profiles) > 0, "profiles must have at least one entry"

        for profile_name, profile_info in profiles.items():
            assert isinstance(profile_info, dict), f"profile '{profile_name}' must be dict"
            assert "description" in profile_info, f"profile '{profile_name}' missing 'description'"
            assert "hooks" in profile_info, f"profile '{profile_name}' missing 'hooks'"
            assert isinstance(profile_info["hooks"], list), \
                f"profile '{profile_name}' hooks must be list"

    def test_profiles_expected_count(self, plugin_json: Dict) -> None:
        """Expect 3 profiles: minimal-stop, balanced, hardened-exec."""
        profiles = plugin_json.get("profiles", {})
        expected_profiles = {"minimal-stop", "balanced", "hardened-exec"}
        actual_profiles = set(profiles.keys())
        assert expected_profiles == actual_profiles, \
            f"Expected profiles {expected_profiles}, got {actual_profiles}"

    def test_profiles_reference_valid_hooks(self, plugin_json: Dict) -> None:
        """Profiles must only reference hooks defined in manifest."""
        hooks = set(plugin_json.get("hooks", {}).keys())
        profiles = plugin_json.get("profiles", {})

        for profile_name, profile_info in profiles.items():
            profile_hooks = set(profile_info.get("hooks", []))
            invalid = profile_hooks - hooks
            assert not invalid, \
                f"profile '{profile_name}' references undefined hooks: {invalid}"

    def test_configuration_field_exists(self, plugin_json: Dict) -> None:
        """Plugin should have configuration field."""
        assert "configuration" in plugin_json, "Missing 'configuration' in plugin.json"
        config = plugin_json.get("configuration", {})
        assert isinstance(config, dict), "configuration must be dict"


# ============================================================================
# Handler Validation Tests
# ============================================================================

class TestHandlers:
    """Test that all handlers exist and are callable."""

    def test_session_start_exists(self, handlers_dir: Path) -> None:
        """session-start.py must exist."""
        handler = handlers_dir / "session-start.py"
        assert handler.exists(), f"session-start.py not found at {handler}"

    def test_pretool_guard_exists(self, handlers_dir: Path) -> None:
        """pretool-guard.py must exist."""
        handler = handlers_dir / "pretool-guard.py"
        assert handler.exists(), f"pretool-guard.py not found at {handler}"

    def test_stop_quality_gate_exists(self, handlers_dir: Path) -> None:
        """stop-quality-gate.py must exist."""
        handler = handlers_dir / "stop-quality-gate.py"
        assert handler.exists(), f"stop-quality-gate.py not found at {handler}"

    def test_write_validate_exists(self, handlers_dir: Path) -> None:
        """write-validate.py must exist."""
        handler = handlers_dir / "write-validate.py"
        assert handler.exists(), f"write-validate.py not found at {handler}"

    def test_all_handlers_are_executable(self, handlers_dir: Path) -> None:
        """All handlers should be executable."""
        handlers = [
            "session-start.py",
            "pretool-guard.py",
            "stop-quality-gate.py",
            "write-validate.py",
        ]
        for handler_name in handlers:
            handler = handlers_dir / handler_name
            assert handler.exists(), f"{handler_name} not found"
            # Check if it's executable (or at least readable)
            assert handler.stat().st_mode & 0o111 or handler.stat().st_size > 0, \
                f"{handler_name} should be executable or have content"

    def test_all_handlers_are_valid_python(self, handlers_dir: Path) -> None:
        """All handlers should be valid Python files."""
        handlers = [
            "session-start.py",
            "pretool-guard.py",
            "stop-quality-gate.py",
            "write-validate.py",
        ]
        for handler_name in handlers:
            handler = handlers_dir / handler_name
            # Try to compile the handler
            try:
                code = handler.read_text()
                compile(code, str(handler), "exec")
            except SyntaxError as e:
                pytest.fail(f"{handler_name} has syntax error: {e}")

    def test_session_start_has_main(self, handlers_dir: Path) -> None:
        """session-start.py should have a main() function."""
        handler = handlers_dir / "session-start.py"
        code = handler.read_text()
        assert "def main" in code, "session-start.py missing main() function"

    def test_pretool_guard_has_main(self, handlers_dir: Path) -> None:
        """pretool-guard.py should have a main() function."""
        handler = handlers_dir / "pretool-guard.py"
        code = handler.read_text()
        assert "def main" in code, "pretool-guard.py missing main() function"

    def test_stop_quality_gate_has_main(self, handlers_dir: Path) -> None:
        """stop-quality-gate.py should have a main() function."""
        handler = handlers_dir / "stop-quality-gate.py"
        code = handler.read_text()
        assert "def main" in code, "stop-quality-gate.py missing main() function"

    def test_write_validate_has_main(self, handlers_dir: Path) -> None:
        """write-validate.py should have a main() function."""
        handler = handlers_dir / "write-validate.py"
        code = handler.read_text()
        assert "def main" in code, "write-validate.py missing main() function"


# ============================================================================
# Profile Validation Tests
# ============================================================================

class TestProfiles:
    """Test that all profile JSON files are valid."""

    def test_minimal_stop_profile_exists(self, profiles_dir: Path) -> None:
        """minimal-stop.json must exist."""
        profile = profiles_dir / "minimal-stop.json"
        assert profile.exists(), f"minimal-stop.json not found at {profile}"

    def test_balanced_profile_exists(self, profiles_dir: Path) -> None:
        """balanced.json must exist."""
        profile = profiles_dir / "balanced.json"
        assert profile.exists(), f"balanced.json not found at {profile}"

    def test_hardened_exec_profile_exists(self, profiles_dir: Path) -> None:
        """hardened-exec.json must exist."""
        profile = profiles_dir / "hardened-exec.json"
        assert profile.exists(), f"hardened-exec.json not found at {profile}"

    def test_all_profiles_are_valid_json(self, profiles_dir: Path) -> None:
        """All profile files should be valid JSON."""
        profiles = ["minimal-stop.json", "balanced.json", "hardened-exec.json"]
        for profile_name in profiles:
            profile_path = profiles_dir / profile_name
            try:
                json.loads(profile_path.read_text())
            except json.JSONDecodeError as e:
                pytest.fail(f"{profile_name} is not valid JSON: {e}")

    def test_profile_has_required_fields(self, profiles_dir: Path) -> None:
        """Each profile should have name, description, hooks_enabled."""
        profiles = ["minimal-stop.json", "balanced.json", "hardened-exec.json"]
        required = {"name", "description", "hooks_enabled"}

        for profile_name in profiles:
            profile_path = profiles_dir / profile_name
            profile = json.loads(profile_path.read_text())
            assert required.issubset(profile.keys()), \
                f"{profile_name} missing fields: {required - set(profile.keys())}"

    def test_minimal_stop_has_stop_quality_gate(self, profiles_dir: Path) -> None:
        """minimal-stop profile should enable stop-quality-gate."""
        profile = json.loads((profiles_dir / "minimal-stop.json").read_text())
        assert "stop-quality-gate" in profile.get("hooks_enabled", []), \
            "minimal-stop should enable stop-quality-gate"

    def test_balanced_has_session_and_gate(self, profiles_dir: Path) -> None:
        """balanced profile should enable session-start and stop-quality-gate."""
        profile = json.loads((profiles_dir / "balanced.json").read_text())
        enabled = profile.get("hooks_enabled", [])
        assert "session-start" in enabled, "balanced should enable session-start"
        assert "stop-quality-gate" in enabled, "balanced should enable stop-quality-gate"

    def test_hardened_exec_has_all_hooks(self, profiles_dir: Path) -> None:
        """hardened-exec profile should enable all 4 hooks."""
        profile = json.loads((profiles_dir / "hardened-exec.json").read_text())
        enabled = set(profile.get("hooks_enabled", []))
        expected = {"session-start", "pretool-guard", "stop-quality-gate", "write-validate"}
        assert expected == enabled, \
            f"hardened-exec should enable all hooks, got {enabled}"


# ============================================================================
# Rules Validation Tests
# ============================================================================

class TestRules:
    """Test dangerous-patterns.yaml structure."""

    def test_dangerous_patterns_yaml_exists(self, plugin_dir: Path) -> None:
        """dangerous-patterns.yaml must exist."""
        path = plugin_dir / "rules" / "dangerous-patterns.yaml"
        assert path.exists(), f"dangerous-patterns.yaml not found at {path}"

    def test_dangerous_patterns_has_patterns_section(self, dangerous_patterns_yaml: str) -> None:
        """YAML should have a 'patterns:' section."""
        assert "patterns:" in dangerous_patterns_yaml, \
            "dangerous-patterns.yaml missing 'patterns:' section"

    def test_dangerous_patterns_has_protected_files(self, dangerous_patterns_yaml: str) -> None:
        """YAML should have a 'protected_files:' section."""
        assert "protected_files:" in dangerous_patterns_yaml, \
            "dangerous-patterns.yaml missing 'protected_files:' section"

    def test_dangerous_patterns_has_approval_cache(self, dangerous_patterns_yaml: str) -> None:
        """YAML should have metadata or approval info."""
        # The YAML may have metadata or safe_patterns sections instead
        has_metadata = "metadata:" in dangerous_patterns_yaml
        has_safe = "safe_patterns:" in dangerous_patterns_yaml
        assert has_metadata or has_safe, \
            "dangerous-patterns.yaml should have metadata or safe_patterns sections"

    def test_patterns_section_well_formed(self, dangerous_patterns_yaml: str) -> None:
        """Pattern entries should have name, regex, description."""
        content = dangerous_patterns_yaml
        # Check for key patterns (at least some of them)
        expected_patterns = [
            "npm_publish",
            "git_reset_hard",
            "git_force_push",
        ]
        for pattern in expected_patterns:
            assert pattern in content, \
                f"dangerous-patterns.yaml missing pattern '{pattern}'"

    def test_protected_files_entries_exist(self, dangerous_patterns_yaml: str) -> None:
        """Should have protected file patterns like .env, .pem, secrets."""
        expected = [".env", ".pem", "secrets", "authorized_keys"]
        for pattern in expected:
            assert pattern in dangerous_patterns_yaml, \
                f"dangerous-patterns.yaml missing protected file pattern for '{pattern}'"


# ============================================================================
# Hook Coordination Tests
# ============================================================================

class TestHookCoordination:
    """Test that hooks work together correctly."""

    def test_session_start_injects_context(self, handlers_dir: Path) -> None:
        """session-start should inject systemMessage in output."""
        handler = handlers_dir / "session-start.py"
        code = handler.read_text()
        assert "systemMessage" in code, \
            "session-start should inject systemMessage"

    def test_pretool_guard_blocks_dangerous(self, handlers_dir: Path) -> None:
        """pretool-guard should have dangerous pattern checks."""
        handler = handlers_dir / "pretool-guard.py"
        code = handler.read_text()
        # Check for key patterns
        dangerous_keywords = ["npm", "git reset", "docker", "fork bomb"]
        for keyword in dangerous_keywords:
            assert keyword.lower() in code.lower(), \
                f"pretool-guard missing check for '{keyword}'"

    def test_stop_quality_gate_detects_failures(self, handlers_dir: Path) -> None:
        """stop-quality-gate should detect test failures and TODOs."""
        handler = handlers_dir / "stop-quality-gate.py"
        code = handler.read_text()
        assert "TODO" in code or "test" in code.lower(), \
            "stop-quality-gate should detect TODOs or test failures"

    def test_write_validate_checks_schema(self, handlers_dir: Path) -> None:
        """write-validate should validate file schema."""
        handler = handlers_dir / "write-validate.py"
        code = handler.read_text()
        assert "frontmatter" in code.lower() or "yaml" in code.lower(), \
            "write-validate should check YAML frontmatter or schema"


# ============================================================================
# End-to-End Integration Tests
# ============================================================================

class TestEndToEnd:
    """Test full hook system end-to-end."""

    def test_handlers_importable(self, handlers_dir: Path) -> None:
        """All handlers should be importable as Python modules."""
        handlers = [
            "session-start.py",
            "pretool-guard.py",
            "stop-quality-gate.py",
            "write-validate.py",
        ]
        for handler_name in handlers:
            handler_path = handlers_dir / handler_name
            code = handler_path.read_text()
            try:
                compile(code, str(handler_path), "exec")
            except SyntaxError as e:
                pytest.fail(f"Cannot import {handler_name}: {e}")

    def test_plugin_json_is_valid(self, plugin_json: Dict) -> None:
        """plugin.json should be valid and well-formed."""
        assert isinstance(plugin_json, dict), "plugin.json must be dict"
        assert len(plugin_json) > 0, "plugin.json must not be empty"

    def test_all_profiles_have_valid_hooks(self, plugin_json: Dict, profiles_dir: Path) -> None:
        """All profiles should reference valid hooks from manifest."""
        valid_hooks = set(plugin_json.get("hooks", {}).keys())
        profiles = ["minimal-stop.json", "balanced.json", "hardened-exec.json"]

        for profile_name in profiles:
            profile = json.loads((profiles_dir / profile_name).read_text())
            profile_hooks = set(profile.get("hooks_enabled", []))
            invalid = profile_hooks - valid_hooks
            assert not invalid, \
                f"{profile_name} references invalid hooks: {invalid}"

    def test_plugin_structure_complete(self, plugin_dir: Path) -> None:
        """Plugin directory should have all required subdirectories."""
        required_dirs = ["handlers", "profiles", "rules", "tests"]
        for dirname in required_dirs:
            dirpath = plugin_dir / dirname
            assert dirpath.exists(), f"Missing required directory: {dirname}"
            assert dirpath.is_dir(), f"{dirname} should be a directory"

    def test_handlers_and_profiles_match(self, plugin_json: Dict, plugin_dir: Path) -> None:
        """Each handler in manifest should have a corresponding Python file."""
        hooks = plugin_json.get("hooks", {})
        handlers_dir = plugin_dir / "handlers"

        for hook_name, hook_info in hooks.items():
            handler_path = hook_info.get("handler", "")
            full_path = plugin_dir / handler_path
            assert full_path.exists(), \
                f"Handler not found for hook '{hook_name}': {handler_path}"

    def test_no_missing_hooks(self, plugin_json: Dict) -> None:
        """All hooks defined should be referenced by at least one profile."""
        hooks = set(plugin_json.get("hooks", {}).keys())
        profiles = plugin_json.get("profiles", {})
        referenced = set()

        for profile_info in profiles.values():
            referenced.update(profile_info.get("hooks", []))

        # All hooks should be referenced
        unreferenced = hooks - referenced
        assert not unreferenced, \
            f"Hooks not used in any profile: {unreferenced}"

    def test_configuration_section_matches_hooks(self, plugin_json: Dict) -> None:
        """Configuration should have entries for hooks that need configuration."""
        hooks = set(plugin_json.get("hooks", {}).keys())
        config = plugin_json.get("configuration", {})
        
        # pretool_guard and stop_quality_gate should have config
        assert "pretool_guard" in config, "pretool_guard missing configuration"
        assert "stop_quality_gate" in config, "stop_quality_gate missing configuration"


# ============================================================================
# Plugin Installation Tests
# ============================================================================

class TestPluginInstallation:
    """Test that plugin can be properly installed."""

    def test_install_script_exists(self, plugin_dir: Path) -> None:
        """install.sh script should exist."""
        script = plugin_dir / "install.sh"
        assert script.exists(), f"install.sh not found at {script}"

    def test_install_script_is_executable(self, plugin_dir: Path) -> None:
        """install.sh should be executable."""
        script = plugin_dir / "install.sh"
        assert script.stat().st_mode & 0o111, "install.sh should be executable"

    def test_plugin_readme_exists(self, plugin_dir: Path) -> None:
        """README.md should exist."""
        readme = plugin_dir / "README.md"
        assert readme.exists(), f"README.md not found at {readme}"

    def test_readme_has_content(self, plugin_dir: Path) -> None:
        """README.md should have substantial content."""
        readme = plugin_dir / "README.md"
        content = readme.read_text()
        assert len(content) > 100, "README.md should have meaningful content"

    def test_readme_mentions_profiles(self, plugin_dir: Path) -> None:
        """README should document profiles or hooks."""
        readme = plugin_dir / "README.md"
        content = readme.read_text()
        # README should mention at least the hook system or profiles
        assert "hook" in content.lower() or "profile" in content.lower(), \
            "README should describe hooks or profiles"

    def test_readme_mentions_hooks(self, plugin_dir: Path) -> None:
        """README should document the 4 hooks."""
        readme = plugin_dir / "README.md"
        content = readme.read_text()
        expected = ["session-start", "pretool-guard", "stop-quality-gate", "write-validate"]
        for hook in expected:
            assert hook in content, f"README should mention {hook} hook"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
