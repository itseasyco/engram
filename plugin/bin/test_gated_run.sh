#!/usr/bin/env bash

# test_gated_run.sh — Comprehensive test suite for openclaw-gated-run wrapper
# Non-interactive version for CI/automated testing

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEST_ROOT="$(dirname "$SCRIPT_DIR")"
GATED_RUN="$SCRIPT_DIR/openclaw-gated-run"
DATA_DIR="$TEST_ROOT/data"
LOGS_DIR="$TEST_ROOT/logs"

# Test counters
TESTS_PASSED=0
TESTS_FAILED=0

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# ============================================================================
# Test Helpers
# ============================================================================

# Extract JSON from output (find first { and take to end)
extract_json() {
  local output="$1"
  # Find the line with { and take from there to the end
  echo "$output" | sed -n '/^{/,$p' | head -20
}

assert_exit_code() {
  local expected=$1
  local actual=$2
  local test_name=$3

  if [ "$expected" -eq "$actual" ]; then
    echo -e "${GREEN}✓${NC} $test_name (exit: $actual)"
    ((TESTS_PASSED++))
    return 0
  else
    echo -e "${RED}✗${NC} $test_name (expected: $expected, got: $actual)"
    ((TESTS_FAILED++))
    return 1
  fi
}

assert_json_field() {
  local json=$1
  local field=$2
  local expected=$3
  local test_name=$4

  local actual=$(echo "$json" | jq -r "$field" 2>/dev/null || echo "null")

  if [ "$actual" = "$expected" ]; then
    echo -e "${GREEN}✓${NC} $test_name"
    ((TESTS_PASSED++))
    return 0
  else
    echo -e "${RED}✗${NC} $test_name (expected '$expected', got '$actual')"
    ((TESTS_FAILED++))
    return 1
  fi
}

# ============================================================================
# Test 1: Safe Tier (No Approval Needed)
# ============================================================================

echo ""
echo -e "${YELLOW}TEST:${NC} Safe tier: low cost, no approval required"
FULL_OUTPUT=$($GATED_RUN --task "safe task" --agent "wren" --channel "webchat" --estimated-cost-usd 0.50 -- echo "test" 2>&1)
EXIT_CODE=$?
OUTPUT=$(extract_json "$FULL_OUTPUT")

assert_exit_code 0 $EXIT_CODE "Safe tier execution succeeded"
assert_json_field "$OUTPUT" ".exit_code" "0" "Exit code is 0"

# Cost field could be 0.5 or 0.50, so just check it's there
COST=$(echo "$OUTPUT" | jq -r ".cost // null")
if [ "$COST" != "null" ] && (( $(echo "$COST == 0.5" | bc -l) )); then
  echo -e "${GREEN}✓${NC} Cost field present"
  ((TESTS_PASSED++))
else
  echo -e "${RED}✗${NC} Cost field (expected 0.5, got $COST)"
  ((TESTS_FAILED++))
fi

# ============================================================================
# Test 2: Safe Tier with Cost Limit
# ============================================================================

echo ""
echo -e "${YELLOW}TEST:${NC} Safe tier: cost at ceiling (1.00)"
FULL_OUTPUT=$($GATED_RUN --task "safe cost limit" --agent "wren" --channel "webchat" --estimated-cost-usd 1.00 -- echo "at limit" 2>&1)
EXIT_CODE=$?
OUTPUT=$(extract_json "$FULL_OUTPUT")

assert_exit_code 0 $EXIT_CODE "Safe tier at ceiling allowed"

# ============================================================================
# Test 3: Safe Tier Exceeding Cost (Should Block)
# ============================================================================

echo ""
echo -e "${YELLOW}TEST:${NC} Safe tier: cost exceeds ceiling (blocked)"
$GATED_RUN --task "over budget" --agent "wren" --channel "webchat" --estimated-cost-usd 2.00 --non-interactive -- echo "too much" > /tmp/test_over_budget.json 2>&1
EXIT_CODE=$?
OUTPUT=$(cat /tmp/test_over_budget.json)

assert_exit_code 2 $EXIT_CODE "Cost ceiling blocking works"

if echo "$OUTPUT" | jq -e ".gate_decisions.blocked[]" 2>/dev/null | grep -q "cost_ceiling"; then
  echo -e "${GREEN}✓${NC} Cost ceiling gate blocked"
  ((TESTS_PASSED++))
else
  echo -e "${RED}✗${NC} Cost ceiling gate not in blocked list"
  ((TESTS_FAILED++))
fi

# ============================================================================
# Test 4: Cost Override with --confirm-budget
# ============================================================================

echo ""
echo -e "${YELLOW}TEST:${NC} Safe tier: cost override with --confirm-budget flag"
FULL_OUTPUT=$($GATED_RUN --task "approved override" --agent "wren" --channel "webchat" --estimated-cost-usd 2.00 --confirm-budget -- echo "override works" 2>&1)
EXIT_CODE=$?
OUTPUT=$(extract_json "$FULL_OUTPUT")

assert_exit_code 0 $EXIT_CODE "Cost override with --confirm-budget succeeds"

# ============================================================================
# Test 5: Review Tier (Approval Required - will fail)
# ============================================================================

echo ""
echo -e "${YELLOW}TEST:${NC} Review tier: approval required (blocks without cache)"

# Clear approval cache
echo '{"approvals": []}' > $DATA_DIR/approval-cache.json

$GATED_RUN --task "review task" --agent "zoe" --channel "bridge" --estimated-cost-usd 5.00 --non-interactive -- echo "should fail" > /tmp/test_review.json 2>&1
EXIT_CODE=$?
OUTPUT=$(cat /tmp/test_review.json)

assert_exit_code 3 $EXIT_CODE "Review tier blocks without approval"

if echo "$OUTPUT" | jq -e ".gate_decisions.blocked[]" 2>/dev/null | grep -q "approval_cache"; then
  echo -e "${GREEN}✓${NC} Approval cache gate blocked"
  ((TESTS_PASSED++))
else
  echo -e "${RED}✗${NC} Approval cache gate not in blocked list"
  ((TESTS_FAILED++))
fi

# ============================================================================
# Test 6: Approval Cache with Valid TTL
# ============================================================================

echo ""
echo -e "${YELLOW}TEST:${NC} Review tier: valid approval in cache allows execution"

CURRENT_TIME=$(date +%s)
FUTURE_TIME=$((CURRENT_TIME + 1800))

APPROVAL_KEY="zoe:bridge:review task with cache"
CACHE_ENTRY="{\"key\":\"$APPROVAL_KEY\",\"approved_at\":$CURRENT_TIME,\"expires_at\":$FUTURE_TIME,\"approver\":\"test-approver\"}"

NEW_CACHE=$(echo "{\"approvals\": [$CACHE_ENTRY]}" | jq .)
echo "$NEW_CACHE" > $DATA_DIR/approval-cache.json

FULL_OUTPUT=$($GATED_RUN --task "review task with cache" --agent "zoe" --channel "bridge" --estimated-cost-usd 5.00 -- echo "cache approved" 2>&1)
EXIT_CODE=$?
OUTPUT=$(extract_json "$FULL_OUTPUT")

assert_exit_code 0 $EXIT_CODE "Valid approval in cache allows execution"

if echo "$OUTPUT" | jq -e ".gate_decisions.passed[]" 2>/dev/null | grep -q "approval_cache"; then
  echo -e "${GREEN}✓${NC} Valid approval shown in gates_passed"
  ((TESTS_PASSED++))
else
  echo -e "${RED}✗${NC} Valid approval not in gates_passed"
  ((TESTS_FAILED++))
fi

# ============================================================================
# Test 7: Approval Cache TTL Expiration
# ============================================================================

echo ""
echo -e "${YELLOW}TEST:${NC} Review tier: expired approval rejected (TTL)"

CURRENT_TIME=$(date +%s)
PAST_TIME=$((CURRENT_TIME - 60))

APPROVAL_KEY="zoe:bridge:expired approval test"
CACHE_ENTRY="{\"key\":\"$APPROVAL_KEY\",\"approved_at\":$((CURRENT_TIME - 1800)),\"expires_at\":$PAST_TIME,\"approver\":\"test-approver\"}"

NEW_CACHE=$(echo "{\"approvals\": [$CACHE_ENTRY]}" | jq .)
echo "$NEW_CACHE" > $DATA_DIR/approval-cache.json

$GATED_RUN --task "expired approval test" --agent "zoe" --channel "bridge" --estimated-cost-usd 5.00 --non-interactive -- echo "should fail" > /tmp/test_expired.json 2>&1
EXIT_CODE=$?
OUTPUT=$(cat /tmp/test_expired.json)

assert_exit_code 3 $EXIT_CODE "Expired approval rejected"

# ============================================================================
# Test 8: Execution Logging (JSONL)
# ============================================================================

echo ""
echo -e "${YELLOW}TEST:${NC} Execution logging: logs to gated-runs.jsonl"

# Clear logs
echo -n > $LOGS_DIR/gated-runs.jsonl

$GATED_RUN --task "test logging" --agent "wren" --channel "webchat" --estimated-cost-usd 0.25 -- echo "logged" >/dev/null 2>&1

if [ -f $LOGS_DIR/gated-runs.jsonl ] && [ -s $LOGS_DIR/gated-runs.jsonl ]; then
  echo -e "${GREEN}✓${NC} gated-runs.jsonl created and populated"
  ((TESTS_PASSED++))

  if jq . $LOGS_DIR/gated-runs.jsonl >/dev/null 2>&1; then
    echo -e "${GREEN}✓${NC} Log entry is valid JSON"
    ((TESTS_PASSED++))
  else
    echo -e "${RED}✗${NC} Log entry is not valid JSON"
    ((TESTS_FAILED++))
  fi

  # Find and verify the logging entry
  if [ -f $LOGS_DIR/gated-runs.jsonl ]; then
    TASK_ENTRY=$(grep '"task":"test logging"' $LOGS_DIR/gated-runs.jsonl | head -1)
    if [ -n "$TASK_ENTRY" ]; then
      assert_json_field "$TASK_ENTRY" ".agent" "wren" "Log agent field"
      assert_json_field "$TASK_ENTRY" ".channel" "webchat" "Log channel field"
    else
      echo -e "${RED}✗${NC} Could not find test logging entry in log"
      ((TESTS_FAILED += 2))
    fi
  fi
else
  echo -e "${RED}✗${NC} gated-runs.jsonl not created"
  ((TESTS_FAILED++))
fi

# ============================================================================
# Test 9: Command Exit Code Propagation
# ============================================================================

echo ""
echo -e "${YELLOW}TEST:${NC} Command exit code: propagates from wrapped command"

$GATED_RUN --task "exit code test" --agent "wren" --channel "webchat" --estimated-cost-usd 0.10 --non-interactive -- sh -c "exit 42" > /tmp/exit_test.json 2>&1
EXIT_CODE=$?
OUTPUT=$(cat /tmp/exit_test.json)

assert_exit_code 42 $EXIT_CODE "Command exit code propagated"
assert_json_field "$OUTPUT" ".exit_code" "42" "JSON exit_code matches command"

# ============================================================================
# Test 10: JSON Output Format
# ============================================================================

echo ""
echo -e "${YELLOW}TEST:${NC} JSON output: valid structure with required fields"

FULL_OUTPUT=$($GATED_RUN --task "json output test" --agent "wren" --channel "webchat" --estimated-cost-usd 0.15 -- echo "test" 2>&1)
OUTPUT=$(extract_json "$FULL_OUTPUT")

if echo "$OUTPUT" | jq . >/dev/null 2>&1; then
  echo -e "${GREEN}✓${NC} Output is valid JSON"
  ((TESTS_PASSED++))
else
  echo -e "${RED}✗${NC} Output is not valid JSON"
  ((TESTS_FAILED++))
fi

assert_json_field "$OUTPUT" ".exit_code" "0" "exit_code present"
assert_json_field "$OUTPUT" ".cost" "0.15" "cost present"

if echo "$OUTPUT" | jq -e ".gate_decisions.passed" >/dev/null 2>&1; then
  echo -e "${GREEN}✓${NC} gate_decisions.passed present"
  ((TESTS_PASSED++))
else
  echo -e "${RED}✗${NC} gate_decisions.passed missing"
  ((TESTS_FAILED++))
fi

if echo "$OUTPUT" | jq -e ".gate_decisions.blocked" >/dev/null 2>&1; then
  echo -e "${GREEN}✓${NC} gate_decisions.blocked present"
  ((TESTS_PASSED++))
else
  echo -e "${RED}✗${NC} gate_decisions.blocked missing"
  ((TESTS_FAILED++))
fi

# ============================================================================
# Test 11: Execution Time Tracking
# ============================================================================

echo ""
echo -e "${YELLOW}TEST:${NC} Execution time: tracked and reported in milliseconds"

FULL_OUTPUT=$($GATED_RUN --task "timing test" --agent "wren" --channel "webchat" --estimated-cost-usd 0.05 -- sleep 0.1 2>&1)
OUTPUT=$(extract_json "$FULL_OUTPUT")

EXEC_TIME=$(echo "$OUTPUT" | jq -r ".execution_time // 0")

if [ "$EXEC_TIME" -ge 100 ]; then
  echo -e "${GREEN}✓${NC} Execution time tracked: ${EXEC_TIME}ms"
  ((TESTS_PASSED++))
else
  echo -e "${RED}✗${NC} Execution time too short: ${EXEC_TIME}ms (expected >= 100)"
  ((TESTS_FAILED++))
fi

# ============================================================================
# Test 12: Default Tier When No Rule Matches
# ============================================================================

echo ""
echo -e "${YELLOW}TEST:${NC} Default tier: unknown agent/channel falls back to review"

# Clear approval cache to force gate failure
echo '{"approvals": []}' > $DATA_DIR/approval-cache.json

$GATED_RUN --task "unknown agent" --agent "unknown" --channel "unknown" --estimated-cost-usd 5.00 --non-interactive -- echo "test" > /tmp/test_unknown.json 2>&1
EXIT_CODE=$?
OUTPUT=$(cat /tmp/test_unknown.json)

assert_exit_code 3 $EXIT_CODE "Unknown agent/channel falls back to review (blocks)"

# ============================================================================
# Test Summary
# ============================================================================

echo ""
echo "========================================"
echo "TEST SUMMARY"
echo "========================================"
echo -e "${GREEN}Passed: $TESTS_PASSED${NC}"
echo -e "${RED}Failed: $TESTS_FAILED${NC}"

if [ $TESTS_FAILED -eq 0 ]; then
  echo -e "${GREEN}✓ All tests passed!${NC}"
  exit 0
else
  echo -e "${RED}✗ Some tests failed${NC}"
  exit 1
fi
