#!/usr/bin/env python3
"""Tests for config_loader module."""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config_loader import (
    ConfigValidationError,
    load_openclaw_lacp_config,
    get_context_engine_name,
    _load_gateway_config,
    DEFAULTS,
    VALID_CONTEXT_ENGINES,
    VALID_INTERVALS,
    MIN_BATCH_SIZE,
    MAX_BATCH_SIZE,
    MIN_THRESHOLD,
    MAX_THRESHOLD,
)


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

class TestDefaults:
    """Config loading with defaults."""

    def test_returns_defaults_with_missing_file(self, tmp_path):
        config = load_openclaw_lacp_config(config_path=str(tmp_path / "missing.json"))
        assert config["contextEngine"] is None
        assert config["lcmQueryBatchSize"] == 50
        assert config["promotionThreshold"] == 70
        assert config["autoDiscoveryInterval"] == "6h"

    def test_all_default_keys_present(self, tmp_path):
        config = load_openclaw_lacp_config(config_path=str(tmp_path / "x.json"))
        expected_keys = {
            "contextEngine", "lcmDbPath", "lcmQueryBatchSize",
            "promotionThreshold", "autoDiscoveryInterval",
            "vaultPath", "memoryRoot",
        }
        assert expected_keys.issubset(set(config.keys()))

    def test_default_context_engine_is_none(self, tmp_path):
        config = load_openclaw_lacp_config(config_path=str(tmp_path / "x.json"))
        assert config["contextEngine"] is None

    def test_default_batch_size(self, tmp_path):
        config = load_openclaw_lacp_config(config_path=str(tmp_path / "x.json"))
        assert config["lcmQueryBatchSize"] == 50

    def test_default_threshold(self, tmp_path):
        config = load_openclaw_lacp_config(config_path=str(tmp_path / "x.json"))
        assert config["promotionThreshold"] == 70


# ---------------------------------------------------------------------------
# Load from file
# ---------------------------------------------------------------------------

class TestLoadFromFile:
    """Loading config from a real openclaw.json file."""

    def test_reads_from_gateway_config_file(self, tmp_path):
        gw = tmp_path / "openclaw.json"
        gw.write_text(json.dumps({
            "plugins": {
                "entries": {
                    "openclaw-lacp-fusion": {
                        "enabled": True,
                        "config": {
                            "contextEngine": "lossless-claw",
                            "lcmQueryBatchSize": 100,
                        }
                    }
                }
            }
        }))
        config = load_openclaw_lacp_config(config_path=str(gw))
        assert config["contextEngine"] == "lossless-claw"
        assert config["lcmQueryBatchSize"] == 100

    def test_file_values_override_defaults(self, tmp_path):
        gw = tmp_path / "openclaw.json"
        gw.write_text(json.dumps({
            "plugins": {"entries": {"openclaw-lacp-fusion": {
                "enabled": True,
                "config": {"promotionThreshold": 85}
            }}}
        }))
        config = load_openclaw_lacp_config(config_path=str(gw))
        assert config["promotionThreshold"] == 85

    def test_unset_keys_keep_defaults(self, tmp_path):
        gw = tmp_path / "openclaw.json"
        gw.write_text(json.dumps({
            "plugins": {"entries": {"openclaw-lacp-fusion": {
                "enabled": True,
                "config": {"contextEngine": "lossless-claw"}
            }}}
        }))
        config = load_openclaw_lacp_config(config_path=str(gw))
        assert config["lcmQueryBatchSize"] == DEFAULTS["lcmQueryBatchSize"]


# ---------------------------------------------------------------------------
# Disabled plugin
# ---------------------------------------------------------------------------

class TestDisabledPlugin:
    """Disabled plugin returns defaults."""

    def test_disabled_plugin_returns_defaults(self, tmp_path):
        gw = tmp_path / "openclaw.json"
        gw.write_text(json.dumps({
            "plugins": {"entries": {"openclaw-lacp-fusion": {
                "enabled": False,
                "config": {
                    "contextEngine": "lossless-claw",
                    "lcmQueryBatchSize": 999,
                }
            }}}
        }))
        config = load_openclaw_lacp_config(config_path=str(gw))
        assert config["contextEngine"] is None
        assert config["lcmQueryBatchSize"] == 50


# ---------------------------------------------------------------------------
# Missing file
# ---------------------------------------------------------------------------

class TestMissingFile:
    """Missing openclaw.json returns defaults."""

    def test_missing_file_returns_defaults(self):
        config = load_openclaw_lacp_config(config_path="/nonexistent/openclaw.json")
        assert config["contextEngine"] is None
        assert config["lcmQueryBatchSize"] == 50


# ---------------------------------------------------------------------------
# Invalid JSON
# ---------------------------------------------------------------------------

class TestInvalidJSON:
    """Corrupted config file returns defaults."""

    def test_corrupted_file_returns_defaults(self, tmp_path):
        f = tmp_path / "openclaw.json"
        f.write_text("not json {{!!")
        config = load_openclaw_lacp_config(config_path=str(f))
        assert config["contextEngine"] is None
        assert config["lcmQueryBatchSize"] == 50


# ---------------------------------------------------------------------------
# Overrides
# ---------------------------------------------------------------------------

class TestOverrides:
    """Explicit overrides applied correctly."""

    def test_overrides_applied_over_defaults(self, tmp_path):
        config = load_openclaw_lacp_config(
            config_path=str(tmp_path / "missing.json"),
            overrides={"promotionThreshold": 90},
        )
        assert config["promotionThreshold"] == 90

    def test_overrides_applied_over_file_config(self, tmp_path):
        gw = tmp_path / "openclaw.json"
        gw.write_text(json.dumps({
            "plugins": {"entries": {"openclaw-lacp-fusion": {
                "enabled": True,
                "config": {"promotionThreshold": 60}
            }}}
        }))
        config = load_openclaw_lacp_config(
            config_path=str(gw),
            overrides={"promotionThreshold": 95},
        )
        assert config["promotionThreshold"] == 95


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class TestValidation:
    """Validation raises ConfigValidationError on bad values."""

    def test_invalid_context_engine(self, tmp_path):
        with pytest.raises(ConfigValidationError, match="contextEngine"):
            load_openclaw_lacp_config(
                config_path=str(tmp_path / "x.json"),
                overrides={"contextEngine": "invalid-engine"},
            )

    def test_batch_size_too_low(self, tmp_path):
        with pytest.raises(ConfigValidationError, match="lcmQueryBatchSize"):
            load_openclaw_lacp_config(
                config_path=str(tmp_path / "x.json"),
                overrides={"lcmQueryBatchSize": 0},
            )

    def test_batch_size_too_high(self, tmp_path):
        with pytest.raises(ConfigValidationError, match="lcmQueryBatchSize"):
            load_openclaw_lacp_config(
                config_path=str(tmp_path / "x.json"),
                overrides={"lcmQueryBatchSize": 1001},
            )

    def test_batch_size_wrong_type(self, tmp_path):
        with pytest.raises(ConfigValidationError, match="lcmQueryBatchSize"):
            load_openclaw_lacp_config(
                config_path=str(tmp_path / "x.json"),
                overrides={"lcmQueryBatchSize": "fifty"},
            )

    def test_threshold_negative(self, tmp_path):
        with pytest.raises(ConfigValidationError, match="promotionThreshold"):
            load_openclaw_lacp_config(
                config_path=str(tmp_path / "x.json"),
                overrides={"promotionThreshold": -1},
            )

    def test_threshold_above_100(self, tmp_path):
        with pytest.raises(ConfigValidationError, match="promotionThreshold"):
            load_openclaw_lacp_config(
                config_path=str(tmp_path / "x.json"),
                overrides={"promotionThreshold": 101},
            )

    def test_threshold_wrong_type(self, tmp_path):
        with pytest.raises(ConfigValidationError, match="promotionThreshold"):
            load_openclaw_lacp_config(
                config_path=str(tmp_path / "x.json"),
                overrides={"promotionThreshold": "high"},
            )

    def test_invalid_interval(self, tmp_path):
        with pytest.raises(ConfigValidationError, match="autoDiscoveryInterval"):
            load_openclaw_lacp_config(
                config_path=str(tmp_path / "x.json"),
                overrides={"autoDiscoveryInterval": "30m"},
            )

    def test_valid_config_passes(self, tmp_path):
        config = load_openclaw_lacp_config(
            config_path=str(tmp_path / "x.json"),
            overrides={
                "contextEngine": "lossless-claw",
                "lcmQueryBatchSize": 100,
                "promotionThreshold": 80,
                "autoDiscoveryInterval": "4h",
            },
        )
        assert config["contextEngine"] == "lossless-claw"

    def test_boundary_threshold_zero(self, tmp_path):
        config = load_openclaw_lacp_config(
            config_path=str(tmp_path / "x.json"),
            overrides={"promotionThreshold": 0},
        )
        assert config["promotionThreshold"] == 0

    def test_boundary_threshold_100(self, tmp_path):
        config = load_openclaw_lacp_config(
            config_path=str(tmp_path / "x.json"),
            overrides={"promotionThreshold": 100},
        )
        assert config["promotionThreshold"] == 100

    def test_boundary_batch_size_min(self, tmp_path):
        config = load_openclaw_lacp_config(
            config_path=str(tmp_path / "x.json"),
            overrides={"lcmQueryBatchSize": MIN_BATCH_SIZE},
        )
        assert config["lcmQueryBatchSize"] == MIN_BATCH_SIZE

    def test_boundary_batch_size_max(self, tmp_path):
        config = load_openclaw_lacp_config(
            config_path=str(tmp_path / "x.json"),
            overrides={"lcmQueryBatchSize": MAX_BATCH_SIZE},
        )
        assert config["lcmQueryBatchSize"] == MAX_BATCH_SIZE

    def test_context_engine_none_is_valid(self, tmp_path):
        config = load_openclaw_lacp_config(
            config_path=str(tmp_path / "x.json"),
            overrides={"contextEngine": None},
        )
        assert config["contextEngine"] is None

    def test_all_valid_intervals_accepted(self, tmp_path):
        for interval in VALID_INTERVALS:
            config = load_openclaw_lacp_config(
                config_path=str(tmp_path / "x.json"),
                overrides={"autoDiscoveryInterval": interval},
            )
            assert config["autoDiscoveryInterval"] == interval


# ---------------------------------------------------------------------------
# get_context_engine_name
# ---------------------------------------------------------------------------

class TestGetContextEngineName:
    """get_context_engine_name returns human-readable names."""

    def test_returns_lossless_claw(self):
        assert get_context_engine_name({"contextEngine": "lossless-claw"}) == "lossless-claw"

    def test_returns_file_based_for_none(self):
        assert get_context_engine_name({"contextEngine": None}) == "file-based"

    def test_returns_file_based_for_missing_key(self):
        assert get_context_engine_name({}) == "file-based"


# ---------------------------------------------------------------------------
# Private _load_gateway_config
# ---------------------------------------------------------------------------

class TestLoadGatewayConfig:
    """Private _load_gateway_config helper."""

    def test_handles_missing_file(self, tmp_path):
        assert _load_gateway_config(str(tmp_path / "nope.json")) == {}

    def test_handles_invalid_json(self, tmp_path):
        f = tmp_path / "bad.json"
        f.write_text("not json {{!!")
        assert _load_gateway_config(str(f)) == {}

    def test_handles_disabled_plugin(self, tmp_path):
        f = tmp_path / "disabled.json"
        f.write_text(json.dumps({
            "plugins": {"entries": {"openclaw-lacp-fusion": {
                "enabled": False,
                "config": {"contextEngine": "lossless-claw"},
            }}}
        }))
        assert _load_gateway_config(str(f)) == {}

    def test_handles_missing_plugin_entry(self, tmp_path):
        f = tmp_path / "empty.json"
        f.write_text(json.dumps({"plugins": {"entries": {}}}))
        assert _load_gateway_config(str(f)) == {}

    def test_returns_config_for_enabled_plugin(self, tmp_path):
        f = tmp_path / "good.json"
        f.write_text(json.dumps({
            "plugins": {"entries": {"openclaw-lacp-fusion": {
                "enabled": True,
                "config": {"lcmQueryBatchSize": 100},
            }}}
        }))
        assert _load_gateway_config(str(f)) == {"lcmQueryBatchSize": 100}
