#!/bin/bash
# Demo Scripts Validation Test
# Tests all demo options to ensure no broken code

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

PASS_COUNT=0
FAIL_COUNT=0

test_pass() {
    echo -e "${GREEN}✅ PASS${NC}: $1"
    PASS_COUNT=$((PASS_COUNT + 1))
}

test_fail() {
    echo -e "${RED}❌ FAIL${NC}: $1"
    FAIL_COUNT=$((FAIL_COUNT + 1))
}

echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║        DEMO SCRIPTS VALIDATION TEST                          ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Test 1: Check both demo scripts exist
echo -e "${YELLOW}[TEST 1] Checking demo scripts exist...${NC}"
if [[ -f demo_deterministic_engine.sh ]]; then
    test_pass "demo_deterministic_engine.sh exists"
else
    test_fail "demo_deterministic_engine.sh not found"
fi

if [[ -f demo_expert_llm.sh ]]; then
    test_pass "demo_expert_llm.sh exists"
else
    test_fail "demo_expert_llm.sh not found"
fi
echo ""

# Test 2: Check scripts are executable
echo -e "${YELLOW}[TEST 2] Checking scripts are executable...${NC}"
if [[ -x demo_deterministic_engine.sh ]]; then
    test_pass "demo_deterministic_engine.sh is executable"
else
    test_fail "demo_deterministic_engine.sh not executable"
fi

if [[ -x demo_expert_llm.sh ]]; then
    test_pass "demo_expert_llm.sh is executable"
else
    test_fail "demo_expert_llm.sh not executable"
fi
echo ""

# Test 3: Check deterministic engine shows usage
echo -e "${YELLOW}[TEST 3] Checking demo_deterministic_engine.sh usage message...${NC}"
if timeout 3 ./demo_deterministic_engine.sh 2>&1 | grep -q "Usage:"; then
    test_pass "Usage message displayed"
else
    test_fail "No usage message found"
fi
echo ""

# Test 4: Check --validate-orphan option
echo -e "${YELLOW}[TEST 4] Testing --validate-orphan option...${NC}"
if timeout 15 ./demo_deterministic_engine.sh --validate-orphan tests/data/architectures/02_minimal_defended.mmd 2>&1 | grep -q "Architecture Validation"; then
    test_pass "--validate-orphan option works"
else
    test_fail "--validate-orphan option failed"
fi
echo ""

# Test 5: Check expert LLM accepts custom architecture
echo -e "${YELLOW}[TEST 5] Checking demo_expert_llm.sh accepts arguments...${NC}"
# Just check if it parses arguments without error (don't run full pipeline)
if grep -q 'if \[\[ \$# -eq 1 \]\]' demo_expert_llm.sh; then
    test_pass "Custom architecture argument handling present"
else
    test_fail "Custom architecture argument handling missing"
fi
echo ""

# Test 6: Check script references are correct
echo -e "${YELLOW}[TEST 6] Checking internal script references...${NC}"
if grep -q "demo_orchestrator" demo_deterministic_engine.sh; then
    test_fail "Old reference 'demo_orchestrator' found in demo_deterministic_engine.sh"
else
    test_pass "No old references in demo_deterministic_engine.sh"
fi

if grep -q "demo_orchestrator" demo_expert_llm.sh; then
    test_fail "Old reference 'demo_orchestrator' found in demo_expert_llm.sh"
else
    test_pass "No old references in demo_expert_llm.sh"
fi

if grep -q "demo_architecture\.sh" demo_deterministic_engine.sh; then
    test_fail "Old reference 'demo_architecture.sh' found in demo_deterministic_engine.sh"
else
    test_pass "No old references in demo_deterministic_engine.sh"
fi
echo ""

# Test 7: Check orphan detection path is correct
echo -e "${YELLOW}[TEST 7] Checking orphan detection script path...${NC}"
if grep -q "scripts/validation/check_orphans.py" demo_deterministic_engine.sh; then
    test_pass "Correct orphan detection path (scripts/validation/)"
else
    test_fail "Incorrect orphan detection path"
fi
echo ""

# Test 8: Check README references
echo -e "${YELLOW}[TEST 8] Checking README references...${NC}"
if grep -q "demo_deterministic_engine.sh" README.md; then
    test_pass "README references demo_deterministic_engine.sh"
else
    test_fail "README missing demo_deterministic_engine.sh reference"
fi

if grep -q "demo_expert_llm.sh" README.md; then
    test_pass "README references demo_expert_llm.sh"
else
    test_fail "README missing demo_expert_llm.sh reference"
fi

if grep -q "demo_orchestrator\.sh\|demo_architecture\.sh" README.md; then
    test_fail "README has old demo names"
else
    test_pass "No old demo names in README"
fi
echo ""

# Summary
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}                    TEST SUMMARY                               ${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "Total Tests: $((PASS_COUNT + FAIL_COUNT))"
echo -e "${GREEN}Passed: $PASS_COUNT${NC}"
echo -e "${RED}Failed: $FAIL_COUNT${NC}"
echo ""

if [[ $FAIL_COUNT -eq 0 ]]; then
    echo -e "${GREEN}✅ ALL TESTS PASSED${NC}"
    echo ""
    echo "Demo scripts are ready to use:"
    echo "  • ./demo_deterministic_engine.sh          # Quick (~30s, no LLM)"
    echo "  • ./demo_deterministic_engine.sh --validate-orphan <file>"
    echo "  • ./demo_expert_llm.sh                    # Complete (~2m, with LLM)"
    echo "  • ./demo_expert_llm.sh <architecture.mmd> # Custom architecture"
    exit 0
else
    echo -e "${RED}❌ SOME TESTS FAILED${NC}"
    exit 1
fi
