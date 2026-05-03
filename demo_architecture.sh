#!/bin/bash
# Architecture Threat Assessment Demonstration
# Showcases v1.0 residual risk analysis with BEFORE/AFTER comparison

echo "╔══════════════════════════════════════════════════════════════════════╗"
echo "║     MITRE Chatbot - Architecture Threat Assessment (v1.0)           ║"
echo "╚══════════════════════════════════════════════════════════════════════╝"
echo ""
echo "This demo compares two architectures:"
echo "  1️⃣  Vulnerable baseline (no security controls)"
echo "  2️⃣  Defended architecture (with controls)"
echo ""
echo "For each, the system generates:"
echo "  • RAPIDS threat assessment (6 threat categories)"
echo "  • Residual risk scores (BEFORE/AFTER)"
echo "  • Prevention + DIR control recommendations"
echo "  • Attack path analysis with hop-by-hop defense"
echo "  • ROI calculation showing risk reduction"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Activate virtual environment
source .venv/bin/activate

# Clean previous reports
rm -rf report/01_minimal_vulnerable report/02_minimal_defended 2>/dev/null

echo "🔍 SCENARIO 1: Vulnerable Baseline Architecture"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Architecture: Internet → Web Server → Database"
echo "Controls: None (baseline)"
echo ""
echo "Running analysis..."
python3 -m chatbot.main --gen-arch-truth tests/data/architectures/01_minimal_vulnerable.mmd 2>&1 | \
    grep -v "LiteLLM\|INFO\|WARNING\|🔄" | \
    grep -E "✓|✅|⚠️|📊|Risk score|BEFORE|AFTER|report/" || echo "Analysis complete"

if [ -f "report/01_minimal_vulnerable/01_executive_summary.md" ]; then
    echo ""
    echo "📊 KEY FINDINGS:"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    # Extract residual risk section
    awk '/## Residual Risk/,/^##/ {print}' report/01_minimal_vulnerable/01_executive_summary.md | head -n 15

    echo ""
    echo "📁 Full report: report/01_minimal_vulnerable/"
    ls -lh report/01_minimal_vulnerable/*.md report/01_minimal_vulnerable/*.mmd 2>/dev/null | awk '{print "   ", $9, "(" $5 ")"}'
fi

echo ""
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "🛡️  SCENARIO 2: Defended Architecture"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Architecture: Internet → WAF → ALB → MFA → Web Server (EDR) → Database (Encrypted)"
echo "Controls: WAF, MFA, EDR, Encryption"
echo ""
echo "Running analysis..."
python3 -m chatbot.main --gen-arch-truth tests/data/architectures/02_minimal_defended.mmd 2>&1 | \
    grep -v "LiteLLM\|INFO\|WARNING\|🔄" | \
    grep -E "✓|✅|⚠️|📊|Risk score|BEFORE|AFTER|report/" || echo "Analysis complete"

if [ -f "report/02_minimal_defended/01_executive_summary.md" ]; then
    echo ""
    echo "📊 KEY FINDINGS:"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    # Extract residual risk section
    awk '/## Residual Risk/,/^##/ {print}' report/02_minimal_defended/01_executive_summary.md | head -n 15

    echo ""
    echo "📁 Full report: report/02_minimal_defended/"
    ls -lh report/02_minimal_defended/*.md report/02_minimal_defended/*.mmd 2>/dev/null | awk '{print "   ", $9, "(" $5 ")"}'
fi

echo ""
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔬 COMPARISON SUMMARY"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "                           Vulnerable    →    Defended"
echo "────────────────────────────────────────────────────────────────────────"

# Extract BEFORE risk scores from both reports
if [ -f "report/01_minimal_vulnerable/ground_truth.json" ] && [ -f "report/02_minimal_defended/ground_truth.json" ]; then
    VULN_BEFORE=$(python3 -c "import json; data=json.load(open('report/01_minimal_vulnerable/ground_truth.json')); print(f\"{data.get('residual_risk_assessment', {}).get('before', {}).get('overall_score', 'N/A'):.1f}\")" 2>/dev/null || echo "N/A")
    DEF_BEFORE=$(python3 -c "import json; data=json.load(open('report/02_minimal_defended/ground_truth.json')); print(f\"{data.get('residual_risk_assessment', {}).get('before', {}).get('overall_score', 'N/A'):.1f}\")" 2>/dev/null || echo "N/A")

    echo "BEFORE (current state):    $VULN_BEFORE/100      →    $DEF_BEFORE/100"
    echo ""
    echo "Impact of adding controls: $(python3 -c "print(f'{float('$VULN_BEFORE') - float('$DEF_BEFORE'):.1f}')" 2>/dev/null || echo "N/A") point reduction"
fi

echo ""
echo "Key architectural differences:"
echo "  • Perimeter defense:  ❌ None          →  ✅ WAF + ALB"
echo "  • Authentication:     ❌ None          →  ✅ MFA"
echo "  • Endpoint security:  ❌ None          →  ✅ EDR"
echo "  • Data protection:    ❌ Plaintext     →  ✅ Encrypted"
echo ""

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ DEMONSTRATION COMPLETE"
echo ""
echo "📖 Output Structure (for each architecture):"
echo "   report/<architecture_name>/"
echo "   ├── 01_executive_summary.md    # Business summary with ROI"
echo "   ├── 02_technical_report.md     # MITRE mapping + attack paths"
echo "   ├── 03_action_plan.md          # 8-week implementation roadmap"
echo "   ├── ground_truth.json          # Full analysis data"
echo "   ├── before.mmd                 # Current architecture diagram"
echo "   └── after.mmd                  # With recommended controls"
echo ""
echo "🚀 Try with your own architecture:"
echo "   python3 -m chatbot.main --gen-arch-truth your_architecture.mmd"
echo ""
echo "📚 More samples available in tests/data/architectures/:"
echo "   • 03_aws_3tier.mmd         - AWS 3-tier web app"
echo "   • 04_zero_trust.mmd        - Zero trust architecture"
echo "   • 05_legacy_flat_network.mmd - Legacy network risks"
echo "   • 09_hybrid_cloud.mmd      - Hybrid cloud design"
echo ""
