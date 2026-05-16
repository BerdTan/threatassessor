#!/bin/bash
# LLM Critic Demonstration - Phase 3C
# Showcases Architect and Tester agents analyzing threat assessment quality

echo "╔═══════════════════════════════════════════════════════════════════════╗"
echo "║     MITRE Chatbot - LLM Critic Agents (v1.1 Phase 3C)                ║"
echo "╚═══════════════════════════════════════════════════════════════════════╝"
echo ""
echo "This demo showcases LLM-powered critique agents that evaluate"
echo "threat assessment quality beyond deterministic validation."
echo ""
echo "🤖 Two specialized agents:"
echo ""
echo "  1️⃣  ARCHITECT (Design Quality)"
echo "     • Threat modeling completeness"
echo "     • Control appropriateness"
echo "     • Defense-in-depth strategy"
echo "     • RAPIDS alignment"
echo "     • Improvement roadmap"
echo ""
echo "  2️⃣  TESTER (MITRE Validation)"
echo "     • MITRE ATT&CK accuracy"
echo "     • Coverage completeness"
echo "     • Internal consistency"
echo "     • Validation checks"
echo "     • Gap detection"
echo ""
echo "📊 Output: Composite score = (Architect × 50%) + (Tester × 50%)"
echo ""
echo "⏱️  Time: ~5-10 seconds per architecture"
echo "🎯 Target: 85/100 composite (EXCELLENT)"
echo ""
echo ""

# Activate virtual environment
source .venv/bin/activate

# Function to run critique on a single architecture
run_critique() {
    local arch_name=$1
    local description=$2

    echo "═══════════════════════════════════════════════════════════════════════"
    echo "🔍 $description"
    echo "═══════════════════════════════════════════════════════════════════════"
    echo ""

    # Check if report exists
    if [ ! -f "report/$arch_name/ground_truth.json" ]; then
        echo "❌ No report found for $arch_name"
        echo "   Run threat analysis first:"
        echo "   python3 -m chatbot.main --gen-arch-truth tests/data/architectures/${arch_name}.mmd"
        echo ""
        return 1
    fi

    echo "📋 Architecture: $arch_name"
    echo ""
    echo "Running critique pipeline..."
    echo "  ⏳ Step 1: Architect agent (design quality assessment)..."
    echo "  ⏳ Step 2: Tester agent (MITRE validation)..."
    echo "  ⏳ Step 3: Composite scoring..."
    echo ""

    # Run full critique pipeline
    python3 scripts/agent_testing/run_full_critique.py "report/$arch_name" 2>&1 | \
        grep -v "LiteLLM\|INFO\|WARNING\|🔄\|Bedrock" || echo ""

    echo ""

    # Check if critique files were generated
    if [ -f "report/$arch_name/04_architect_critique.json" ] && [ -f "report/$arch_name/05_tester_critique.json" ]; then
        echo "✅ Critique complete"
        echo ""

        # Extract scores
        ARCH_SCORE=$(python3 -c "import json; d=json.load(open('report/$arch_name/04_architect_critique.json')); print(d.get('score', 'N/A'))" 2>/dev/null || echo "N/A")
        TEST_SCORE=$(python3 -c "import json; d=json.load(open('report/$arch_name/05_tester_critique.json')); print(d.get('score', 'N/A'))" 2>/dev/null || echo "N/A")

        # Calculate composite
        if [ "$ARCH_SCORE" != "N/A" ] && [ "$TEST_SCORE" != "N/A" ]; then
            COMPOSITE=$(python3 -c "print(f'{(float('$ARCH_SCORE') * 0.5 + float('$TEST_SCORE') * 0.5):.1f}')" 2>/dev/null || echo "N/A")

            echo "📊 SCORES:"
            echo ""
            echo "   Architect:  $ARCH_SCORE/100  (Design quality, threat modeling)"
            echo "   Tester:     $TEST_SCORE/100  (MITRE validation, coverage)"
            echo "   ───────────────────────────────────────────────"
            echo "   Composite:  $COMPOSITE/100  (Weighted average)"
            echo ""

            # Rating
            if [ $(echo "$COMPOSITE >= 85" | bc 2>/dev/null || echo 0) -eq 1 ]; then
                echo "   Rating: ⭐⭐⭐⭐⭐ EXCELLENT"
            elif [ $(echo "$COMPOSITE >= 75" | bc 2>/dev/null || echo 0) -eq 1 ]; then
                echo "   Rating: ⭐⭐⭐⭐ GOOD"
            elif [ $(echo "$COMPOSITE >= 65" | bc 2>/dev/null || echo 0) -eq 1 ]; then
                echo "   Rating: ⭐⭐⭐ ACCEPTABLE"
            else
                echo "   Rating: ⭐⭐ NEEDS IMPROVEMENT"
            fi
            echo ""
        fi

        # Show top gaps/recommendations (from Architect)
        echo "💡 TOP RECOMMENDATIONS (from Architect):"
        echo ""
        python3 -c "
import json
data = json.load(open('report/$arch_name/04_architect_critique.json'))
roadmap = data.get('improvement_roadmap', [])
if roadmap:
    for i, item in enumerate(roadmap[:3], 1):
        print(f'   {i}. {item.get(\"issue\", \"N/A\")}')
        print(f'      Impact: +{item.get(\"impact_points\", 0)} points')
        print()
else:
    print('   No major improvements needed')
    print()
" 2>/dev/null || echo "   (Unable to extract recommendations)"

        echo ""
        echo "📁 Critique artifacts:"
        echo "   report/$arch_name/04_architect_critique.json"
        echo "   report/$arch_name/05_tester_critique.json"
        echo ""

    else
        echo "❌ Critique generation failed"
        echo "   Check if LLM is configured (bedrock or openrouter)"
        echo "   See .env file for configuration"
        echo ""
        return 1
    fi

    return 0
}

# Function to show architecture comparison
show_comparison() {
    echo ""
    echo "═══════════════════════════════════════════════════════════════════════"
    echo "📊 ARCHITECTURE COMPARISON"
    echo "═══════════════════════════════════════════════════════════════════════"
    echo ""

    if [ -f "report/01_minimal_vulnerable/05_tester_critique.json" ] && \
       [ -f "report/02_minimal_defended/05_tester_critique.json" ]; then

        # Extract scores
        V_ARCH=$(python3 -c "import json; d=json.load(open('report/01_minimal_vulnerable/04_architect_critique.json')); print(d.get('score', 0))" 2>/dev/null || echo "0")
        V_TEST=$(python3 -c "import json; d=json.load(open('report/01_minimal_vulnerable/05_tester_critique.json')); print(d.get('score', 0))" 2>/dev/null || echo "0")
        V_COMP=$(python3 -c "print(f'{(float('$V_ARCH') * 0.5 + float('$V_TEST') * 0.5):.1f}')" 2>/dev/null || echo "0")

        D_ARCH=$(python3 -c "import json; d=json.load(open('report/02_minimal_defended/04_architect_critique.json')); print(d.get('score', 0))" 2>/dev/null || echo "0")
        D_TEST=$(python3 -c "import json; d=json.load(open('report/02_minimal_defended/05_tester_critique.json')); print(d.get('score', 0))" 2>/dev/null || echo "0")
        D_COMP=$(python3 -c "print(f'{(float('$D_ARCH') * 0.5 + float('$D_TEST') * 0.5):.1f}')" 2>/dev/null || echo "0")

        echo "                         Vulnerable    →    Defended"
        echo ""
        echo "Architect (design):       $V_ARCH/100      →    $D_ARCH/100"
        echo "Tester (validation):      $V_TEST/100      →    $D_TEST/100"
        echo "───────────────────────────────────────────────────────────"
        echo "Composite:                $V_COMP/100      →    $D_COMP/100"
        echo ""

        IMPROVEMENT=$(python3 -c "print(f'{float('$D_COMP') - float('$V_COMP'):.1f}')" 2>/dev/null || echo "N/A")
        echo "Quality improvement: +$IMPROVEMENT points"
        echo ""

        echo "Key insights:"
        echo "  • Adding controls improves both design quality and MITRE validation"
        echo "  • Defended architecture shows better defense-in-depth strategy"
        echo "  • Higher Tester score indicates better MITRE ATT&CK alignment"
        echo ""
    else
        echo "Unable to generate comparison (missing critique files)"
        echo ""
    fi
}

# Main demo flow
echo "🚀 DEMONSTRATION: Critic Agent Pipeline"
echo ""
echo "We'll analyze two architectures and show how the critic agents"
echo "evaluate quality differences between vulnerable and defended designs."
echo ""
echo ""

# Demo 1: Vulnerable architecture
run_critique "01_minimal_vulnerable" "Scenario 1: Vulnerable Baseline (No Controls)"

echo ""
echo ""
read -p "Press Enter to continue to defended architecture..."
echo ""
echo ""

# Demo 2: Defended architecture
run_critique "02_minimal_defended" "Scenario 2: Defended Architecture (With Controls)"

# Show comparison
show_comparison

echo ""
echo "═══════════════════════════════════════════════════════════════════════"
echo "✅ DEMONSTRATION COMPLETE"
echo "═══════════════════════════════════════════════════════════════════════"
echo ""
echo "🎯 What You Learned:"
echo ""
echo "1. Architect agent evaluates design quality and threat modeling"
echo "2. Tester agent validates MITRE ATT&CK accuracy and coverage"
echo "3. Composite score shows overall assessment quality"
echo "4. Improvement roadmap guides next steps"
echo ""
echo "📖 Understanding the Scores:"
echo ""
echo "   85-100: ⭐⭐⭐⭐⭐ EXCELLENT   (Production-ready, comprehensive)"
echo "   75-84:  ⭐⭐⭐⭐ GOOD        (Minor improvements needed)"
echo "   65-74:  ⭐⭐⭐ ACCEPTABLE   (Functional but gaps exist)"
echo "   <65:    ⭐⭐ NEEDS WORK    (Significant improvements required)"
echo ""
echo "🔬 Behind the Scenes:"
echo ""
echo "   Phase 3C uses a hybrid MITRE approach:"
echo "   • Defense-in-depth: Multiple mitigations per control"
echo "   • Strict validation: Only claim what MITRE officially maps"
echo "   • Multi-layer LLM validation: Few-shot + post-processing"
echo ""
echo "   Result: 95% validation accuracy (38/40 checks)"
echo ""
echo "🚀 Try With Your Own Architecture:"
echo ""
echo "   # Step 1: Run threat analysis"
echo "   python3 -m chatbot.main --gen-arch-truth your_architecture.mmd"
echo ""
echo "   # Step 2: Run critique agents"
echo "   python3 scripts/agent_testing/run_full_critique.py report/your_architecture"
echo ""
echo "   # Or use this demo script:"
echo "   ./demo_llm_critique.sh"
echo ""
echo "📚 More Architectures to Try:"
echo ""
echo "   • 03_aws_3tier          - AWS 3-tier web application"
echo "   • 04_zero_trust         - Zero trust architecture"
echo "   • 10_complex_enterprise - Large enterprise (17 nodes, 5 paths)"
echo ""
echo "   All architectures in: tests/data/architectures/"
echo ""
echo "📖 Documentation:"
echo ""
echo "   • docs/phases/phase3c/85_PERCENT_ACHIEVED.md   - Achievement summary"
echo "   • docs/phases/phase3c/core/                    - Implementation details"
echo "   • docs/phases/phase3c/agents/                  - Agent specifications"
echo ""
echo "💡 Pro Tips:"
echo ""
echo "   1. Run threat analysis first (demo_architecture.sh or --gen-arch-truth)"
echo "   2. Check validation output in ground_truth.json"
echo "   3. Use critique agents to identify improvement opportunities"
echo "   4. Compare before/after scores when adding controls"
echo ""
echo "🎉 Phase 3C MVP: 85/100 composite confidence achieved!"
echo ""
