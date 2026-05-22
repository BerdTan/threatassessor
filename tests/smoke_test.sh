#!/bin/bash
set -e

echo "=== Phase 1 Smoke Test ==="

# Check if .venv exists and activate
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Test imports
echo "→ Testing imports..."
python3 -c "from chatbot.modules.agents import run_moe_pipeline; print('  ✓ MoE pipeline imports OK')"

# Quick analysis test
echo "→ Testing deterministic engine..."
./demo_deterministic_engine.sh tests/data/architectures/02_minimal_defended.mmd >/dev/null 2>&1

echo "✓ SMOKE TEST PASSED"
