"""
Config Loader — Load and validate openclaw-lacp plugin configuration.

Reads from openclaw.json plugins.entries.openclaw-lacp-fusion.config
and validates against the expected schema for backend selection.
"""

import json
import os
from pathlib import Path
from typing import Optional

DEFAULTS = {
    "contextEngine": None,
    "lcmDbPath": "~/.openclaw/lcm.db",
    "lcmQueryBatchSize": 50,
    "promotionThreshold": 70,
    "autoDiscoveryInterval": "6h",
    "vaultPath": "~/.openclaw/vault",
    "memoryRoot": "~/.openclaw/memory",
}

VALID_CONTEXT_ENGINES = {None, "lossless-claw"}
MIN_BATCH_SIZE = 1
MAX_BATCH_SIZE = 1000
MIN_THRESHOLD = 0
MAX_THRESHOLD = 100
VALID_INTERVALS = frozenset({"1h", "2h", "4h", "6h", "8h", "12h", "24h"})


class ConfigValidationError(Exception):
    """Raised when plugin configuration is invalid."""
    pass


def load_openclaw_lacp_config(config_path: Optional[str] = None, overrides: Optional[dict] = None) -> dict:
    """Load and validate the openclaw-lacp plugin config.

Resolution order:
    1. Defaults (DEFAULTS dict)
    2. openclaw.json gateway config
    3. Explicit overrides

Args:
    config_path: Path to openclaw.json. If None, uses
                 ~/.openclaw/openclaw.json.
    overrides: Dict of config overrides (e.g., from CLI flags).

Returns:
    Validated config dict with all required keys.

Raises:
    ConfigValidationError: If config values are invalid.
"""
    config = dict(DEFAULTS)
    gateway_config = _load_gateway_config(config_path)
    config.update(gateway_config)
    if overrides:
        config.update(overrides)
    _validate_config(config)
    return config


def _load_gateway_config(config_path: Optional[str] = None) -> dict:
    """Load the plugin config section from openclaw.json.

Args:
    config_path: Path to openclaw.json.

Returns:
    Config dict from the plugin entry, or empty dict.
"""
    if config_path is None:
        path = os.path.expanduser("~/.openclaw/openclaw.json")
    else:
        path = config_path

    try:
        if not Path(path).exists():
            return {}
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        plugin_entry = data.get("plugins", {}).get("entries", {}).get("openclaw-lacp-fusion", {})
        if plugin_entry.get("enabled", False) is False:
            return {}
        return plugin_entry.get("config", {})
    except (json.JSONDecodeError, OSError, TypeError):
        return {}


def _validate_config(config: dict) -> None:
    """Validate config values. Raises ConfigValidationError on invalid values.

Args:
    config: Config dict to validate.

Raises:
    ConfigValidationError: If any value is invalid.
"""
    errors = []

    engine = config.get("contextEngine")
    if engine not in VALID_CONTEXT_ENGINES:
        errors.append("contextEngine must be 'lossless-claw' or null, got: " + str(engine))

    batch_size = config.get("lcmQueryBatchSize")
    if batch_size is not None:
        if not isinstance(batch_size, (int, float)) or isinstance(batch_size, bool):
            errors.append("lcmQueryBatchSize must be a number, got: " + type(batch_size).__name__)
        elif batch_size < MIN_BATCH_SIZE or batch_size > MAX_BATCH_SIZE:
            errors.append(
                "lcmQueryBatchSize must be between " + str(MIN_BATCH_SIZE) +
                " and " + str(MAX_BATCH_SIZE) + ", got: " + str(batch_size)
            )

    threshold = config.get("promotionThreshold")
    if threshold is not None:
        if not isinstance(threshold, (int, float)) or isinstance(threshold, bool):
            errors.append("promotionThreshold must be a number, got: " + type(threshold).__name__)
        elif threshold < MIN_THRESHOLD or threshold > MAX_THRESHOLD:
            errors.append(
                "promotionThreshold must be between " + str(MIN_THRESHOLD) +
                " and " + str(MAX_THRESHOLD) + ", got: " + str(threshold)
            )

    interval = config.get("autoDiscoveryInterval")
    if interval is not None and isinstance(interval, str) and interval not in VALID_INTERVALS:
        errors.append("autoDiscoveryInterval must be one of " + str(sorted(VALID_INTERVALS)))

    if errors:
        raise ConfigValidationError("Invalid openclaw-lacp config:\n  " + "\n  ".join(errors))


def get_context_engine_name(config: dict) -> str:
    """Return human-readable name for the active context engine.

Args:
    config: Validated config dict.

Returns:
    'lossless-claw' or 'file-based'.
"""
    engine = config.get("contextEngine")
    if engine == "lossless-claw":
        return "lossless-claw"
    return "file-based"
