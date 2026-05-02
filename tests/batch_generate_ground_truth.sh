#!/bin/bash
# Batch Ground Truth Generation
# Generates ground truth for all .mmd files that don't have labels yet

set -e

ARCH_DIR="tests/data/architectures"
GT_DIR="tests/data/ground_truth"

# Count total architectures
TOTAL=$(ls -1 "$ARCH_DIR"/*.mmd | wc -l)
EXISTING=$(ls -1 "$GT_DIR"/*.json 2>/dev/null | wc -l || echo 0)
REMAINING=$((TOTAL - EXISTING))

echo "============================================"
echo "Batch Ground Truth Generation"
echo "============================================"
echo "Total architectures: $TOTAL"
echo "Existing ground truth: $EXISTING"
echo "Remaining: $REMAINING"
echo ""

if [ "$REMAINING" -eq 0 ]; then
    echo "✅ All architectures have ground truth!"
    exit 0
fi

echo "Generating ground truth for remaining architectures..."
echo ""

# Find .mmd files without ground truth
for mmd_file in "$ARCH_DIR"/*.mmd; do
    basename=$(basename "$mmd_file" .mmd)
    gt_file="$GT_DIR/${basename}.json"

    if [ ! -f "$gt_file" ]; then
        echo "📋 Processing: $basename"
        echo "   Input: $mmd_file"
        echo "   Output: $gt_file"
        echo ""

        # Generate with LLM (will prompt for validation)
        python3 tests/generate_ground_truth.py "$mmd_file"

        echo ""
        echo "─────────────────────────────────────────"
        echo ""
    fi
done

echo "============================================"
echo "Batch Generation Complete"
echo "============================================"

# Run validation on all ground truth
echo ""
echo "Running full validation suite..."
PYTHONPATH=. python3 tests/validate_parser_harness.py

echo ""
echo "✅ Done! All ground truth generated and validated."
