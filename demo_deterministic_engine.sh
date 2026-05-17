#!/bin/bash
# Architecture Threat Assessment Demonstration
# Showcases v1.0 residual risk analysis with BEFORE/AFTER comparison

# Function to check for orphan nodes
check_orphans() {
    local arch_file=$1
    local arch_name=$(basename "$arch_file" .mmd)

    echo "🔍 Checking for orphan nodes in $arch_name..."

    # Check if previous report exists to run orphan detection
    if [ ! -f "report/$arch_name/ground_truth.json" ]; then
        echo "   No previous report found - will check after generation"
        return 0
    fi

    # Run orphan detection
    python3 scripts/validation/check_orphans.py "$arch_name" 2>/dev/null | grep -q "No orphans"

    if [ $? -eq 0 ]; then
        echo "   ✅ No orphan nodes found"
        return 0
    else
        echo ""
        echo "   ⚠️  ORPHAN NODES DETECTED!"
        echo ""
        python3 scripts/validation/check_orphans.py "$arch_name" 2>/dev/null | grep -A 20 "ARCHITECTURES WITH ORPHANS"
        echo ""
        echo "   Orphan nodes are components that:"
        echo "   • Have outbound connections (can attack other components)"
        echo "   • Are unreachable from entry points (Internet, VPN, Users)"
        echo "   • Will NOT be analyzed in threat modeling"
        echo ""
        echo "   Impact: Confidence penalty (~16% per orphan)"
        echo ""
        echo "   Options:"
        echo "   1) Fix the architecture (add entry point or connection)"
        echo "   2) Skip this architecture for now"
        echo "   3) Continue anyway (NOT RECOMMENDED - incomplete analysis)"
        echo ""
        read -p "   Choose [1/2/3]: " choice

        case $choice in
            1)
                echo ""
                echo "   How to fix orphan nodes:"
                echo ""
                echo "   Pattern 1: Add entry point (if node is external access)"
                echo "     VPN((VPN Remote Access))"
                echo "     VPN --> OrphanNode"
                echo ""
                echo "   Pattern 2: Connect to existing path (if node is internal)"
                echo "     ExistingNode --> OrphanNode"
                echo ""
                echo "   Pattern 3: Remove node (if out of scope)"
                echo "     (Delete the orphan node from diagram)"
                echo ""
                echo "   📝 Edit: $arch_file"
                echo "   📚 See: docs/phases/ORPHAN_REMEDIATION.md for examples"
                echo ""
                echo "   After fixing, re-run this script."
                exit 1
                ;;
            2)
                echo "   ⏭️  Skipping $arch_name"
                return 1
                ;;
            3)
                echo "   ⚠️  Continuing with incomplete analysis..."
                return 0
                ;;
            *)
                echo "   Invalid choice. Skipping."
                return 1
                ;;
        esac
    fi
}

# Function to validate architecture before analysis
validate_architecture() {
    local arch_file=$1
    local arch_name=$(basename "$arch_file" .mmd)

    echo "📋 PRE-ANALYSIS VALIDATION: $arch_name"
    echo ""

    # Check 1: File exists
    if [ ! -f "$arch_file" ]; then
        echo "❌ File not found: $arch_file"
        return 1
    fi
    echo "✅ Architecture file found"

    # Check 2: Valid Mermaid syntax (basic check)
    if ! grep -q "flowchart\|graph" "$arch_file"; then
        echo "❌ Invalid Mermaid syntax (missing flowchart/graph declaration)"
        return 1
    fi
    echo "✅ Valid Mermaid syntax"

    # Check 3: Has nodes
    NODE_COUNT=$(grep -E "^\s*[A-Za-z0-9_]+\[|^\s*[A-Za-z0-9_]+\(|^\s*[A-Za-z0-9_]+\{" "$arch_file" | wc -l)
    if [ $NODE_COUNT -lt 2 ]; then
        echo "❌ Architecture too simple (need at least 2 nodes)"
        return 1
    fi
    echo "✅ Architecture has $NODE_COUNT nodes"

    # Check 4: Has edges
    EDGE_COUNT=$(grep -E "\-\->|\-\-\-" "$arch_file" | wc -l)
    if [ $EDGE_COUNT -lt 1 ]; then
        echo "❌ No connections found (need at least 1 edge)"
        return 1
    fi
    echo "✅ Architecture has $EDGE_COUNT connections"

    echo ""
    echo "🔍 Checking for orphan nodes..."

    # Check 5: Orphan nodes (if previous report exists)
    check_orphans "$arch_file"
    local orphan_status=$?

    if [ $orphan_status -eq 1 ]; then
        return 1  # Skip this architecture
    fi

    echo ""
    echo "✅ Validation complete - ready for analysis"
    echo ""

    return 0
}

# Check for validation-only mode
if [ "$1" == "--validate-orphan" ]; then
    if [ -z "$2" ]; then
        echo "Usage: $0 --validate-orphan <architecture.mmd>"
        echo ""
        echo "Checks your architecture for orphan nodes before running analysis."
        echo ""
        echo "Orphan nodes are components that:"
        echo "  • Have outbound connections (can attack other nodes)"
        echo "  • Are unreachable from entry points (Internet, VPN, etc.)"
        echo "  • Will NOT be analyzed in threat modeling (confidence penalty)"
        echo ""
        echo "Example:"
        echo "  $0 --validate-orphan my_architecture.mmd"
        exit 1
    fi

    echo "║     Architecture Validation - Orphan Node Check                     ║"
    echo ""

    source .venv/bin/activate

    validate_architecture "$2"
    exit_code=$?

    if [ $exit_code -eq 0 ]; then
        echo ""
        echo "✅ Architecture is ready for threat analysis!"
        echo ""
        echo "Run analysis:"
        echo "  python3 -m chatbot.main --gen-arch-truth $2"
    else
        echo ""
        echo "❌ Please fix the issues above before running analysis"
    fi

    exit $exit_code
fi

echo "║     MITRE Chatbot - Architecture Threat Assessment (v1.0)           ║"
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
echo "ℹ️  Usage:"
echo "  Demo mode:           $0"
echo "  Check for orphans:   $0 --validate-orphan your_architecture.mmd"
echo ""
echo ""

# Activate virtual environment
source .venv/bin/activate

# Validate both architectures before starting
echo "🔬 Pre-Analysis Validation"
echo ""

ARCH1="tests/data/architectures/01_minimal_vulnerable.mmd"
ARCH2="tests/data/architectures/02_minimal_defended.mmd"

# Validate first architecture
validate_architecture "$ARCH1"
if [ $? -ne 0 ]; then
    echo ""
    echo "❌ Validation failed for vulnerable architecture"
    echo "   Fix the issues and re-run the demo"
    exit 1
fi

echo ""

# Validate second architecture
validate_architecture "$ARCH2"
if [ $? -ne 0 ]; then
    echo ""
    echo "❌ Validation failed for defended architecture"
    echo "   Fix the issues and re-run the demo"
    exit 1
fi

echo ""
echo ""

# Clean previous reports
rm -rf report/01_minimal_vulnerable report/02_minimal_defended 2>/dev/null

echo "🔍 SCENARIO 1: Vulnerable Baseline Architecture"
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
    # Extract residual risk section
    awk '/## Residual Risk/,/^##/ {print}' report/01_minimal_vulnerable/01_executive_summary.md | head -n 15

    echo ""
    echo "📁 Full report: report/01_minimal_vulnerable/"
    ls -lh report/01_minimal_vulnerable/*.md report/01_minimal_vulnerable/*.mmd 2>/dev/null | awk '{print "   ", $9, "(" $5 ")"}'
fi

echo ""
echo ""
echo ""
echo "🛡️  SCENARIO 2: Defended Architecture"
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
    # Extract residual risk section
    awk '/## Residual Risk/,/^##/ {print}' report/02_minimal_defended/01_executive_summary.md | head -n 15

    echo ""
    echo "📁 Full report: report/02_minimal_defended/"
    ls -lh report/02_minimal_defended/*.md report/02_minimal_defended/*.mmd 2>/dev/null | awk '{print "   ", $9, "(" $5 ")"}'
fi

echo ""
echo ""
echo "🔬 COMPARISON SUMMARY"
echo ""
echo "                           Vulnerable    →    Defended"
echo ""

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
echo "   # Check for orphan nodes first (recommended)"
echo "   ./demo_deterministic_engine.sh --validate-orphan your_architecture.mmd"
echo ""
echo "   # Run full analysis"
echo "   python3 -m chatbot.main --gen-arch-truth your_architecture.mmd"
echo ""
echo "📚 More samples available in tests/data/architectures/:"
echo "   • 03_aws_3tier.mmd         - AWS 3-tier web app"
echo "   • 04_zero_trust.mmd        - Zero trust architecture"
echo "   • 05_legacy_flat_network.mmd - Legacy network risks"
echo "   • 09_hybrid_cloud.mmd      - Hybrid cloud design"
echo ""
