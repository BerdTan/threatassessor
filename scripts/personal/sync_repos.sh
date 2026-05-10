#!/bin/bash
# Bidirectional sync between main DEV-TEST and threatassessor-master
# Usage: bash scripts/sync_repos.sh

set -e  # Exit on error

MAIN_ROOT="/mnt/c/BACKUP/DEV-TEST"
THREAT_ROOT="$MAIN_ROOT/_codex/threatassessor-master"

echo "=================================================="
echo "📚 Repository Synchronization Script"
echo "=================================================="
echo ""

# Verify directories exist
if [ ! -d "$MAIN_ROOT" ]; then
    echo "❌ Error: Main repo not found at $MAIN_ROOT"
    exit 1
fi

if [ ! -d "$THREAT_ROOT" ]; then
    echo "❌ Error: Threatassessor repo not found at $THREAT_ROOT"
    exit 1
fi

echo "✓ Repositories found"
echo ""

# Documentation Sync
echo "📚 Syncing Documentation..."
echo "  Main → threatassessor (context)"
cp "$MAIN_ROOT/CLAUDE.md" "$THREAT_ROOT/docs/MAIN_REPO_CONTEXT.md"
echo "    ✓ Copied CLAUDE.md to threatassessor/docs/MAIN_REPO_CONTEXT.md"

echo "  threatassessor → Main (architecture docs)"
if [ -f "$THREAT_ROOT/docs/ARCHITECTURE_ANALYSIS.md" ]; then
    cp "$THREAT_ROOT/docs/ARCHITECTURE_ANALYSIS.md" "$MAIN_ROOT/docs/ARCHITECTURE_EXTENDED.md"
    echo "    ✓ Copied ARCHITECTURE_ANALYSIS.md to docs/ARCHITECTURE_EXTENDED.md"
else
    echo "    ⚠ ARCHITECTURE_ANALYSIS.md not found, skipping"
fi
echo ""

# Shared Modules Sync
echo "🔧 Syncing Shared Modules..."
echo "  Main → threatassessor (stable modules)"

# Check and sync individual modules
for module in mitre embeddings rate_limiter; do
    if [ -f "$MAIN_ROOT/chatbot/modules/${module}.py" ]; then
        rsync -a "$MAIN_ROOT/chatbot/modules/${module}.py" "$THREAT_ROOT/chatbot/modules/"
        echo "    ✓ Synced chatbot/modules/${module}.py"
    else
        echo "    ⚠ chatbot/modules/${module}.py not found, skipping"
    fi
done

if [ -f "$MAIN_ROOT/agentic/llm.py" ]; then
    rsync -a "$MAIN_ROOT/agentic/llm.py" "$THREAT_ROOT/agentic/"
    echo "    ✓ Synced agentic/llm.py"
else
    echo "    ⚠ agentic/llm.py not found, skipping"
fi
echo ""

# Test Utilities Sync
echo "🧪 Syncing Test Utilities..."
for test_file in conftest eval_utils; do
    if [ -f "$MAIN_ROOT/tests/${test_file}.py" ]; then
        rsync -a "$MAIN_ROOT/tests/${test_file}.py" "$THREAT_ROOT/tests/"
        echo "    ✓ Synced tests/${test_file}.py"
    else
        echo "    ⚠ tests/${test_file}.py not found, skipping"
    fi
done
echo ""

echo "=================================================="
echo "✅ Sync complete!"
echo "=================================================="
echo ""
echo "Next steps:"
echo "1. Review changes: git diff"
echo "2. Stage changes: git add -p"
echo "3. Commit: git commit -m 'Sync: Documentation and shared modules'"
echo ""
