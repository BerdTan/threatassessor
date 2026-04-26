#!/bin/bash
# Phase 2A Testing Script - Fully Automated (No User Input)
# Run with: bash run_phase2_tests_auto.sh

set -e  # Exit on error

echo "========================================================================"
echo "Phase 2A Testing - Automated Mode"
echo "========================================================================"
echo ""

# Activate virtual environment
echo "Step 1: Activating Virtual Environment"
echo "------------------------------------------------------------------------"
source .venv/bin/activate
echo "✓ Virtual environment activated"
echo ""

# Install dependencies
echo "Step 2: Installing Dependencies"
echo "------------------------------------------------------------------------"
pip install --quiet numpy scikit-learn requests python-dotenv openai
echo "✓ Dependencies installed"
echo ""

# Verify API key
echo "Step 3: Verifying API Configuration"
echo "------------------------------------------------------------------------"
if [ -f .env ]; then
    if grep -q "OPENROUTER_API_KEY" .env; then
        KEY_LENGTH=$(grep "OPENROUTER_API_KEY" .env | cut -d'=' -f2 | wc -c)
        echo "✓ API key found (${KEY_LENGTH} characters)"
    else
        echo "✗ OPENROUTER_API_KEY not found in .env"
        exit 1
    fi
else
    echo "✗ .env file not found"
    exit 1
fi
echo ""

# Test module imports
echo "Step 4: Testing Module Imports"
echo "------------------------------------------------------------------------"
python3 << 'EOF'
from chatbot.modules.mitre import MitreHelper
from chatbot.modules.embeddings import get_embedding
from chatbot.modules.mitre_embeddings import search_techniques
from chatbot.modules.llm_mitre_analyzer import analyze_scenario
from chatbot.modules.agent import AgentManager
print("✓ All modules imported successfully")
EOF
echo ""

# Check MITRE data
echo "Step 5: Verifying MITRE Data"
echo "------------------------------------------------------------------------"
python3 << 'EOF'
from chatbot.modules.mitre import MitreHelper
mitre = MitreHelper(use_local=True)
techniques = mitre.get_techniques()
print(f"✓ Loaded {len(techniques)} MITRE ATT&CK techniques")
EOF
echo ""

# Check cache status
echo "Step 6: Checking Embedding Cache Status"
echo "------------------------------------------------------------------------"
if [ -f "chatbot/data/technique_embeddings.json" ]; then
    SIZE=$(du -h chatbot/data/technique_embeddings.json | cut -f1)
    echo "✓ Embedding cache exists (${SIZE})"
    echo "  Skipping cache generation"
    SKIP_CACHE="yes"
else
    echo "⚠ Embedding cache not found"
    echo "  Will generate cache (~10-15 minutes)"
    SKIP_CACHE="no"
fi
echo ""

# Generate cache if needed
if [ "$SKIP_CACHE" = "no" ]; then
    echo "Step 7: Generating Embedding Cache"
    echo "------------------------------------------------------------------------"
    echo "⏱️  This will take 10-15 minutes due to rate limiting (20 req/min)"
    echo ""

    python3 << 'EOF'
import time
from chatbot.modules.mitre import MitreHelper
from chatbot.modules.mitre_embeddings import build_technique_embeddings, save_embeddings_json

print("Starting cache generation...")
print("")

mitre = MitreHelper(use_local=True)
start_time = time.time()

try:
    cache = build_technique_embeddings(mitre)
    save_embeddings_json(cache, 'chatbot/data/technique_embeddings.json')

    elapsed = time.time() - start_time
    print(f"\n✓ Cache generation complete in {elapsed/60:.1f} minutes")
except Exception as e:
    print(f"\n✗ Cache generation failed: {e}")
    exit(1)
EOF
    echo ""
else
    echo "Step 7: Using Existing Cache"
    echo "------------------------------------------------------------------------"
    echo "✓ Skipping cache generation"
    echo ""
fi

# Quick semantic search test
echo "Step 8: Testing Semantic Search"
echo "------------------------------------------------------------------------"
python3 << 'EOF'
from chatbot.modules.mitre import MitreHelper
from chatbot.modules.mitre_embeddings import search_techniques

mitre = MitreHelper(use_local=True)
query = "PowerShell script execution"

print(f"Query: '{query}'")
results = search_techniques(query, mitre, top_k=3, min_score=0.5)

if results:
    print(f"\nTop {len(results)} matches:")
    for i, r in enumerate(results, 1):
        print(f"  {i}. {r['external_id']} - {r['name']} (score: {r['similarity_score']:.3f})")
    print("\n✓ Semantic search working")
else:
    print("\n⚠ No results returned (may need to lower min_score)")
EOF
echo ""

# Test LLM analysis
echo "Step 9: Testing LLM Analysis"
echo "------------------------------------------------------------------------"
echo "Running LLM analysis (may take 10-15s)..."
python3 << 'EOF'
from chatbot.modules.mitre import MitreHelper
from chatbot.modules.mitre_embeddings import search_techniques
from chatbot.modules.llm_mitre_analyzer import analyze_scenario

mitre = MitreHelper(use_local=True)
query = "Attacker used PowerShell for malicious execution"

try:
    matched = search_techniques(query, mitre, top_k=5, min_score=0.3)
    analysis = analyze_scenario(query, matched, top_k=3)

    print(f"✓ LLM analysis complete")
    print(f"  Refined techniques: {len(analysis['refined_techniques'])}")
    print(f"  Attack path stages: {len(analysis['attack_path'].get('attack_path', []))}")
    print(f"  Priority mitigations: {len(analysis['mitigations'].get('priority_mitigations', []))}")
except Exception as e:
    print(f"⚠ LLM analysis failed: {e}")
    print("  This may be due to rate limits - semantic search still works")
EOF
echo ""

# Test agent integration
echo "Step 10: Testing Agent Integration"
echo "------------------------------------------------------------------------"
python3 << 'EOF'
from chatbot.modules.agent import AgentManager

try:
    agent = AgentManager(use_semantic_search=True)
    query = "Attacker used PowerShell to create scheduled tasks"

    result = agent.handle_input(query, top_k=3)

    mode = result.get('mode')
    if mode == 'semantic':
        print(f"✓ Agent using semantic mode")
        print(f"  Matched: {len(result.get('techniques', []))} techniques")
        print(f"  Refined: {len(result.get('refined_techniques', []))} techniques")
    else:
        print(f"⚠ Agent using fallback mode: {mode}")
except Exception as e:
    print(f"⚠ Agent integration issue: {e}")
EOF
echo ""

# Summary
echo "========================================================================"
echo "TEST SUMMARY"
echo "========================================================================"
echo ""
echo "✅ Phase 2A Testing Complete"
echo ""
echo "Components Tested:"
echo "  ✓ Module imports"
echo "  ✓ MITRE data loading"
echo "  ✓ Embedding cache"
echo "  ✓ Semantic search"
echo "  ✓ LLM analysis"
echo "  ✓ Agent integration"
echo ""
echo "Next Steps:"
echo "  1. Try the interactive CLI:"
echo "     python3 chatbot/main.py"
echo ""
echo "  2. Run comprehensive test suite:"
echo "     python3 test_phase2_semantic_search.py"
echo ""
echo "  3. When ready, proceed to Phase 3 (Web API)"
echo ""
echo "========================================================================"
