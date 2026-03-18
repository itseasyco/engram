#!/usr/bin/env python3
"""
Test suite for OpenClaw routing engine.
Tests rule matching, tier decisions, and policy enforcement.
"""

import sys
import os
import json
import subprocess
from pathlib import Path
from typing import Dict, Any


class RoutingEngine:
    """Routing engine for OpenClaw policy system."""
    
    def __init__(self, policy_path: str = None):
        """Initialize routing engine with policy config."""
        if policy_path is None:
            policy_path = os.path.expanduser(
                "~/.openclaw-test/config/policy/risk-policy.json"
            )

        try:
            with open(policy_path, "r") as f:
                self.policy = json.load(f)
        except FileNotFoundError:
            raise FileNotFoundError(f"Policy file not found: {policy_path}")
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in policy file: {e}")

    def match_pattern(self, pattern: str, agent: str, channel: str, context: str) -> bool:
        """
        Match a pattern against agent/channel/context.
        Pattern format: "agent:zoe,channel:bridge" or "context:local" etc.
        ALL specified parts in a pattern must match.
        """
        parts = [p.strip() for p in pattern.split(",")]
        
        for part in parts:
            if ":" not in part:
                continue
                
            key, value = part.split(":", 1)
            key = key.strip()
            value = value.strip()
            
            if key == "agent":
                if value != agent:
                    return False
            elif key == "channel":
                if value != channel:
                    return False
            elif key == "context":
                if value != context:
                    return False
        
        # All specified parts matched
        return True

    def decide(self, agent: str, channel: str, context: str) -> Dict[str, Any]:
        """
        Match rules against input and return tier decision.
        Returns: {tier, reason, approval_required, cost_ceiling_usd}
        """
        # Try each rule in order
        for rule in self.policy.get("rules", []):
            if self.match_pattern(rule["pattern"], agent, channel, context):
                tier_name = rule["tier"]
                tier_info = self.policy["tiers"].get(tier_name, {})
                return {
                    "tier": tier_name,
                    "reason": rule.get("reason", "Rule matched"),
                    "approval_required": tier_info.get("approval_required", False),
                    "cost_ceiling_usd": tier_info.get("cost_ceiling_usd", 1.00),
                    "confirmation_required": tier_info.get("confirmation_required", False),
                    "approval_ttl_minutes": tier_info.get("approval_ttl_minutes", None)
                }
        
        # Fallback to default
        default = self.policy.get("defaults", {})
        default_tier = default.get("tier", "review")
        tier_info = self.policy["tiers"].get(default_tier, {})
        
        return {
            "tier": default_tier,
            "reason": default.get("reason", "Default policy applied"),
            "approval_required": tier_info.get("approval_required", True),
            "cost_ceiling_usd": tier_info.get("cost_ceiling_usd", 10.00),
            "confirmation_required": tier_info.get("confirmation_required", False),
            "approval_ttl_minutes": tier_info.get("approval_ttl_minutes", None)
        }


class TestRoutingEngine:
    """Test suite for routing engine decisions."""
    
    def __init__(self):
        self.policy_path = os.path.expanduser("~/.openclaw-test/config/policy/risk-policy.json")
        self.engine = RoutingEngine(self.policy_path)
        self.tests_passed = 0
        self.tests_failed = 0
        self.failures = []
    
    def assert_equal(self, actual: Any, expected: Any, test_name: str) -> bool:
        """Assert equality and track results."""
        if actual == expected:
            self.tests_passed += 1
            print(f"✓ {test_name}")
            return True
        else:
            self.tests_failed += 1
            msg = f"✗ {test_name}: expected {expected}, got {actual}"
            print(msg)
            self.failures.append(msg)
            return False
    
    def test_rule_safe_wren_local(self):
        """Test: wren agent, local context → safe tier"""
        result = self.engine.decide("wren", "general", "local")
        self.assert_equal(result["tier"], "safe", "Rule: wren + local → safe")
        self.assert_equal(result["approval_required"], False, "Safe tier: no approval needed")
        self.assert_equal(result["cost_ceiling_usd"], 1.00, "Safe tier: $1.00 ceiling")
    
    def test_rule_safe_main_local(self):
        """Test: main agent, local context → safe tier"""
        result = self.engine.decide("main", "general", "local")
        self.assert_equal(result["tier"], "safe", "Rule: main + local → safe")
        self.assert_equal(result["approval_required"], False, "Safe tier: no approval needed")
    
    def test_rule_review_zoe_bridge(self):
        """Test: zoe agent, bridge channel → review tier"""
        result = self.engine.decide("zoe", "bridge", "external")
        self.assert_equal(result["tier"], "review", "Rule: zoe + bridge → review")
        self.assert_equal(result["approval_required"], True, "Review tier: approval needed")
        self.assert_equal(result["approval_ttl_minutes"], 30, "Review tier: 30min TTL")
        self.assert_equal(result["cost_ceiling_usd"], 10.00, "Review tier: $10.00 ceiling")
    
    def test_rule_critical_external_context(self):
        """Test: external context → critical tier"""
        result = self.engine.decide("any_agent", "any_channel", "external")
        self.assert_equal(result["tier"], "critical", "Rule: external context → critical")
        self.assert_equal(result["approval_required"], True, "Critical tier: approval required")
        self.assert_equal(result["confirmation_required"], True, "Critical tier: confirmation required")
        self.assert_equal(result["cost_ceiling_usd"], 100.00, "Critical tier: $100.00 ceiling")
    
    def test_rule_critical_production_channel(self):
        """Test: production channel → critical tier"""
        result = self.engine.decide("any_agent", "production", "internal")
        self.assert_equal(result["tier"], "critical", "Rule: production channel → critical")
        self.assert_equal(result["confirmation_required"], True, "Critical: confirmation required")
    
    def test_fallback_to_default(self):
        """Test: unknown agent/channel → default review tier"""
        result = self.engine.decide("unknown_agent", "unknown_channel", "local")
        self.assert_equal(result["tier"], "review", "Fallback: unknown combo → review tier")
        self.assert_equal(result["approval_required"], True, "Default: approval required")
        self.assert_equal(result["cost_ceiling_usd"], 10.00, "Default: $10.00 ceiling")
    
    def test_cost_ceiling_safe(self):
        """Test: safe tier has $1.00 ceiling"""
        result = self.engine.decide("wren", "general", "local")
        self.assert_equal(result["cost_ceiling_usd"], 1.00, "Safe tier ceiling: $1.00")
    
    def test_cost_ceiling_review(self):
        """Test: review tier has $10.00 ceiling"""
        result = self.engine.decide("zoe", "bridge", "local")
        self.assert_equal(result["cost_ceiling_usd"], 10.00, "Review tier ceiling: $10.00")
    
    def test_cost_ceiling_critical(self):
        """Test: critical tier has $100.00 ceiling"""
        result = self.engine.decide("any", "production", "any")
        self.assert_equal(result["cost_ceiling_usd"], 100.00, "Critical tier ceiling: $100.00")
    
    def test_approval_flags_safe(self):
        """Test: safe tier has no approval flags"""
        result = self.engine.decide("wren", "general", "local")
        self.assert_equal(result["approval_required"], False, "Safe: no approval_required")
        self.assert_equal(result.get("confirmation_required", False), False, "Safe: no confirmation_required")
    
    def test_approval_flags_review(self):
        """Test: review tier requires approval (not confirmation)"""
        result = self.engine.decide("zoe", "bridge", "local")
        self.assert_equal(result["approval_required"], True, "Review: approval_required=True")
        self.assert_equal(result.get("confirmation_required", False), False, "Review: confirmation_required=False")
        self.assert_equal(result["approval_ttl_minutes"], 30, "Review: TTL is 30 minutes")
    
    def test_approval_flags_critical(self):
        """Test: critical tier requires both approval and confirmation"""
        result = self.engine.decide("any", "production", "any")
        self.assert_equal(result["approval_required"], True, "Critical: approval_required=True")
        self.assert_equal(result["confirmation_required"], True, "Critical: confirmation_required=True")
    
    def test_reason_field_populated(self):
        """Test: all decisions include a reason"""
        for agent, channel, context in [
            ("wren", "general", "local"),
            ("zoe", "bridge", "external"),
            ("any", "production", "any"),
            ("unknown", "unknown", "unknown")
        ]:
            result = self.engine.decide(agent, channel, context)
            self.assert_equal(
                bool(result.get("reason")),
                True,
                f"Reason field present: {agent}/{channel}/{context}"
            )
    
    def test_partial_pattern_match_context_only(self):
        """Test: pattern 'context:external' matches any agent/channel"""
        results = [
            self.engine.decide("agent_a", "channel_x", "external"),
            self.engine.decide("agent_b", "channel_y", "external"),
            self.engine.decide("wren", "production", "external"),
        ]
        for result in results:
            self.assert_equal(result["tier"], "critical", "All external → critical")
    
    def test_pattern_specificity_order(self):
        """Test: more specific patterns should match before general ones"""
        # zoe + bridge should match "agent:zoe,channel:bridge" (review)
        # NOT fall through to "context:external" (critical)
        result = self.engine.decide("zoe", "bridge", "external")
        self.assert_equal(result["tier"], "review", "Specific pattern (zoe+bridge) takes precedence")
        self.assert_equal(
            "Engineering agent" in result["reason"],
            True,
            "Matched first (zoe+bridge) rule, not fallback"
        )
    
    def run_all_tests(self):
        """Run all tests and report results."""
        print("\n" + "=" * 60)
        print("OpenClaw Routing Engine Test Suite")
        print("=" * 60 + "\n")
        
        # Run all test methods
        test_methods = [m for m in dir(self) if m.startswith("test_")]
        for method_name in test_methods:
            method = getattr(self, method_name)
            try:
                method()
            except Exception as e:
                self.tests_failed += 1
                msg = f"✗ {method_name}: Exception - {e}"
                print(msg)
                self.failures.append(msg)
        
        # Print summary
        print("\n" + "=" * 60)
        print(f"Results: {self.tests_passed} passed, {self.tests_failed} failed")
        print("=" * 60)
        
        if self.failures:
            print("\nFailures:")
            for failure in self.failures:
                print(f"  {failure}")
        
        return self.tests_failed == 0


class TestCLIInterface:
    """Test the CLI interface of the routing engine."""
    
    def __init__(self):
        self.route_bin = os.path.expanduser("~/.openclaw-test/bin/openclaw-route")
        self.tests_passed = 0
        self.tests_failed = 0
        self.failures = []
    
    def run_route(self, agent: str, channel: str, context: str) -> Dict[str, Any]:
        """Call the routing engine CLI and parse output."""
        try:
            result = subprocess.run(
                [self.route_bin, agent, channel, context],
                capture_output=True,
                text=True,
                check=True
            )
            return json.loads(result.stdout)
        except subprocess.CalledProcessError as e:
            print(f"Error running routing engine: {e.stderr}")
            return None
        except json.JSONDecodeError as e:
            print(f"Error parsing JSON output: {e}")
            return None
    
    def assert_equal(self, actual: Any, expected: Any, test_name: str) -> bool:
        """Assert equality and track results."""
        if actual == expected:
            self.tests_passed += 1
            print(f"✓ {test_name}")
            return True
        else:
            self.tests_failed += 1
            msg = f"✗ {test_name}: expected {expected}, got {actual}"
            print(msg)
            self.failures.append(msg)
            return False
    
    def test_cli_valid_json_output(self):
        """Test: CLI produces valid JSON output"""
        result = self.run_route("wren", "general", "local")
        self.assert_equal(result is not None, True, "CLI output is valid JSON")
    
    def test_cli_required_fields(self):
        """Test: CLI output includes all required fields"""
        result = self.run_route("zoe", "bridge", "external")
        required_fields = ["tier", "reason", "approval_required", "cost_ceiling_usd"]
        for field in required_fields:
            self.assert_equal(
                field in result,
                True,
                f"Output includes '{field}' field"
            )
    
    def test_cli_tier_values(self):
        """Test: CLI returns valid tier values"""
        valid_tiers = ["safe", "review", "critical"]
        test_cases = [
            ("wren", "general", "local"),
            ("zoe", "bridge", "external"),
            ("any", "production", "any"),
        ]
        for agent, channel, context in test_cases:
            result = self.run_route(agent, channel, context)
            self.assert_equal(
                result["tier"] in valid_tiers,
                True,
                f"Tier is valid: {result['tier']}"
            )
    
    def run_all_tests(self):
        """Run all CLI tests."""
        print("\n" + "=" * 60)
        print("OpenClaw Routing Engine CLI Test Suite")
        print("=" * 60 + "\n")
        
        test_methods = [m for m in dir(self) if m.startswith("test_")]
        for method_name in test_methods:
            method = getattr(self, method_name)
            try:
                method()
            except Exception as e:
                self.tests_failed += 1
                msg = f"✗ {method_name}: Exception - {e}"
                print(msg)
                self.failures.append(msg)
        
        print("\n" + "=" * 60)
        print(f"Results: {self.tests_passed} passed, {self.tests_failed} failed")
        print("=" * 60)
        
        if self.failures:
            print("\nFailures:")
            for failure in self.failures:
                print(f"  {failure}")
        
        return self.tests_failed == 0


def main():
    """Run all test suites."""
    # Test the engine directly
    engine_suite = TestRoutingEngine()
    engine_ok = engine_suite.run_all_tests()
    
    # Test the CLI interface
    cli_suite = TestCLIInterface()
    cli_ok = cli_suite.run_all_tests()
    
    # Final summary
    total_passed = engine_suite.tests_passed + cli_suite.tests_passed
    total_failed = engine_suite.tests_failed + cli_suite.tests_failed
    
    print("\n" + "=" * 60)
    print("OVERALL RESULTS")
    print("=" * 60)
    print(f"Total: {total_passed} passed, {total_failed} failed")
    
    if engine_ok and cli_ok:
        print("\n✓ All tests passed!")
        return 0
    else:
        print("\n✗ Some tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
