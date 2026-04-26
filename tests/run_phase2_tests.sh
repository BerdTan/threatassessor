#!/bin/bash
# Phase 2A Testing Script - Step-by-Step Guide
# Run with: bash run_phase2_tests.sh

set -e  # Exit on error

echo "========================================================================"
echo "Phase 2A Testing Guide - LLM-Enhanced Semantic Search"
echo "========================================================================"
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Step 1: Activate virtual environment
echo -e "${YELLOW}Step 1: Activating Virtual Environment${NC}"
echo "------------------------------------------------------------------------"
source .venv/bin/activate
echo -e "${GREEN}✓ Virtual environment activated${NC}"
echo ""

# Step 2: Install dependencies
echo -e "${YELLOW}Step 2: Installing Dependencies${NC}"
echo "------------------------------------------------------------------------"
echo "Installing: numpy, scikit-learn, requests, python-dotenv, openai..."
pip install --quiet numpy scikit-learn requests python-dotenv openai
echo -e "${GREEN}✓ Dependencies installed${NC}"
echo ""

# Step 3: Verify API key
echo -e "${YELLOW}Step 3: Verifying API Configuration${NC}"
echo "------------------------------------------------------------------------"
if [ -f .env ]; then
    if grep -q "OPENROUTER_API_KEY" .env; then
        KEY_LENGTH=$(grep "OPENROUTER_API_KEY" .env | cut -d'=' -f2 | wc -c)
        echo -e "${GREEN}✓ API key found (${KEY_LENGTH} characters)${NC}"
    else
        echo -e "${RED}✗ OPENROUTER_API_KEY not found in .env${NC}"
        exit 1
    fi
else
    echo -e "${RED}✗ .env file not found${NC}"
    exit 1
fi
echo ""

# Step 4: Quick module import test
echo -e "${YELLOW}Step 4: Testing Module Imports${NC}"
echo "------------------------------------------------------------------------"
python3 << 'EOF'
try:
    from chatbot.modules.mitre import MitreHelper
    from chatbot.modules.embeddings import get_embedding
    from chatbot.modules.mitre_embeddings import search_techniques
    from chatbot.modules.llm_mitre_analyzer import analyze_scenario
    from chatbot.modules.agent import AgentManager
    print("✓ All modules imported successfully")
except ImportError as e:
    print(f"✗ Import failed: {e}")
    exit(1)
EOF
echo ""

# Step 5: Check MITRE data
echo -e "${YELLOW}Step 5: Verifying MITRE Data${NC}"
echo "------------------------------------------------------------------------"
python3 << 'EOF'
from chatbot.modules.mitre import MitreHelper
mitre = MitreHelper(use_local=True)
techniques = mitre.get_techniques()
print(f"✓ Loaded {len(techniques)} MITRE ATT&CK techniques")
EOF
echo ""

# Step 6: Check embedding cache status
echo -e "${YELLOW}Step 6: Checking Embedding Cache Status${NC}"
echo "------------------------------------------------------------------------"
if [ -f "chatbot/data/technique_embeddings.json" ]; then
    SIZE=$(du -h chatbot/data/technique_embeddings.json | cut -f1)
    echo -e "${GREEN}✓ Embedding cache exists (${SIZE})${NC}"
    echo "  Location: chatbot/data/technique_embeddings.json"
    echo ""
    echo "  Skip cache generation? (yes/no)"
    read -p "  > " SKIP_CACHE
    echo ""
else
    echo -e "${YELLOW}⚠ Embedding cache not found${NC}"
    echo "  Cache will be generated (takes ~10-15 minutes)"
    SKIP_CACHE="no"
fi

# Step 7: Generate or load cache
if [[ "$SKIP_CACHE" == "no" || "$SKIP_CACHE" == "n" ]]; then
    echo -e "${YELLOW}Step 7: Generating Embedding Cache${NC}"
    echo "------------------------------------------------------------------------"
    echo "⏱️  This will take 10-15 minutes due to rate limiting (20 req/min)"
    echo "   You can safely interrupt (Ctrl+C) and resume later"
    echo ""

    python3 << 'EOF'
import time
from chatbot.modules.mitre import MitreHelper
from chatbot.modules.mitre_embeddings import build_technique_embeddings, save_embeddings_json

print("Starting cache generation...")
print("")

mitre = MitreHelper(use_local=True)
start_time = time.time()

cache = build_technique_embeddings(mitre)
save_embeddings_json(cache, 'chatbot/data/technique_embeddings.json')

elapsed = time.time() - start_time
print(f"\n✓ Cache generation complete in {elapsed/60:.1f} minutes")
EOF
    echo ""
else
    echo -e "${GREEN}Step 7: Using Existing Cache${NC}"
    echo "------------------------------------------------------------------------"
    echo "✓ Skipping cache generation"
    echo ""
fi

# Step 8: Run comprehensive tests
echo -e "${YELLOW}Step 8: Running Comprehensive Test Suite${NC}"
echo "------------------------------------------------------------------------"
python3 test_phase2_semantic_search.py
echo ""

# Step 9: Interactive CLI demo
echo -e "${YELLOW}Step 9: Interactive CLI Demo${NC}"
echo "------------------------------------------------------------------------"
echo "The CLI is ready! You can now test with real queries."
echo ""
echo "Example queries to try:"
echo "  1. Attacker used PowerShell to execute malicious scripts"
echo "  2. Phishing email with malicious Excel macro"
echo "  3. Lateral movement using stolen credentials"
echo ""
echo "Would you like to try the CLI now? (yes/no)"
read -p "> " RUN_CLI

if [[ "$RUN_CLI" == "yes" || "$RUN_CLI" == "y" ]]; then
    echo ""
    python3 chatbot/main.py
fi

echo ""
echo "========================================================================"
echo "Phase 2A Testing Complete!"
echo "========================================================================"
echo ""
echo "✓ All tests passed"
echo "✓ Semantic search working"
echo "✓ LLM analysis functional"
echo ""
echo "Next Steps:"
echo "  1. Review test results above"
echo "  2. Test with more scenarios via: python3 chatbot/main.py"
echo "  3. When ready, proceed to Phase 3 (Web API)"
echo ""
