#!/bin/bash
# Quick test script for agent framework validation

set -e

AGENT_TEST_DIR="tests/data/agent_test_cases"
TEST_CASE="test_flawed_assessment"

echo "=========================================="
echo "Agent Framework Test Runner"
echo "=========================================="
echo ""

# Activate virtual environment
source .venv/bin/activate

# Set up test data
echo "Setting up test data..."
mkdir -p "report/$TEST_CASE"
cp "$AGENT_TEST_DIR/$TEST_CASE.json" "report/$TEST_CASE/ground_truth.json"

echo "Running Architect critique..."
python3 -m chatbot.modules.architect_critic "$TEST_CASE"

echo ""
echo "=========================================="
echo "Test Complete"
echo "=========================================="
echo ""
echo "Results saved to: report/$TEST_CASE/04_architect_critique.json"
echo ""
echo "Expected findings:"
echo "  - Score: 20-30/100 (POOR)"
echo "  - Gap: Ransomware rationale contradiction (backup)"
echo "  - Gap: DoS priority mismatch (risk=80, priority=low)"
echo "  - Gap: App Vulns coverage gap (risk=90, 1 technique)"

