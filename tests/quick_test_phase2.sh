#!/bin/bash
# Quick Phase 2A Test - Handles slow litellm imports
set -e

echo "==================================================================="
echo "Phase 2A Quick Test"
echo "==================================================================="
echo ""

source .venv/bin/activate

echo "✓ Virtual environment activated"
echo ""

echo "Testing imports (litellm is slow, please wait ~60s)..."
timeout 120 python3 << 'EOF'
print("  Importing standard modules...")
from chatbot.modules.mitre import MitreHelper
print("  ✓ mitre")

from chatbot.modules.embeddings import get_embedding
print("  ✓ embeddings")

from chatbot.modules.mitre_embeddings import search_techniques
print("  ✓ mitre_embeddings")

print("  Importing LLM modules (slow, ~30-60s)...")
from chatbot.modules.llm_mitre_analyzer import analyze_scenario
print("  ✓ llm_mitre_analyzer")

from chatbot.modules.agent import AgentManager
print("  ✓ AgentManager")

print("\n✅ All imports successful!")
EOF

echo ""
echo "Testing MITRE data load..."
python3 << 'EOF'
from chatbot.modules.mitre import MitreHelper
mitre = MitreHelper(use_local=True)
print(f"✓ Loaded {len(mitre.get_techniques())} techniques")
EOF

echo ""
echo "==================================================================="
echo "✅ Phase 2A Core Components Working!"
echo "==================================================================="
echo ""
echo "Note: LiteLLM imports are slow (~30-60s) but everything works."
echo ""
echo "Next: Generate embedding cache"
echo "Run: python3 -c \""
echo "from chatbot.modules.mitre import MitreHelper"
echo "from chatbot.modules.mitre_embeddings import build_technique_embeddings, save_embeddings_json"
echo "mitre = MitreHelper(use_local=True)"
echo "cache = build_technique_embeddings(mitre)"
echo "save_embeddings_json(cache, 'chatbot/data/technique_embeddings.json')"
echo "\""
echo ""
