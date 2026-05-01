#!/bin/bash
# Demonstration of all output formats

QUERY="Attacker used PowerShell to create scheduled tasks"

echo "╔══════════════════════════════════════════════════════════════════════╗"
echo "║          MITRE Chatbot - Output Format Demonstration                ║"
echo "╚══════════════════════════════════════════════════════════════════════╝"
echo ""
echo "Query: $QUERY"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Activate virtual environment
source .venv/bin/activate

echo "1️⃣  EXECUTIVE FORMAT (for C-level / Board)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
python3 -m chatbot.main --format executive --query "$QUERY" 2>&1 | \
    grep -v "LiteLLM\|INFO\|WARNING\|ERROR\|🔄 Analyzing"

echo ""
echo ""
echo "2️⃣  ACTION PLAN FORMAT (for Security Managers)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
python3 -m chatbot.main --format action-plan --query "$QUERY" 2>&1 | \
    grep -v "LiteLLM\|INFO\|WARNING\|ERROR\|🔄 Analyzing" | head -n 100

echo ""
echo ""
echo "3️⃣  TECHNICAL FORMAT (for Security Analysts)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "(Showing first 50 lines only - use --verbose for full details)"
python3 -m chatbot.main --format technical --query "$QUERY" 2>&1 | \
    grep -v "LiteLLM\|INFO\|WARNING\|ERROR\|🔄 Analyzing" | head -n 50

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ DEMONSTRATION COMPLETE"
echo ""
echo "Usage:"
echo "  python3 -m chatbot.main --format executive     # High-level summary"
echo "  python3 -m chatbot.main --format action-plan   # Manager roadmap"
echo "  python3 -m chatbot.main --format technical     # Detailed analysis"
echo "  python3 -m chatbot.main --format all           # Show all three"
echo ""
