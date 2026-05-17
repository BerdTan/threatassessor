#!/bin/bash
################################################################################
# Demo: Full MoE Orchestrator Pipeline (Phase 3D)
#
# Purpose: Demonstrates the complete Phase 3D MoE validation flow
#   1. Deterministic Analysis (Layer 1) → ground_truth.json
#   2. MoE Validation (Layer 2) → 3 critics (Architect, Tester, Red Team)
#   3. Executive Dashboard (Layer 3) → Unified coherent report
#
# Output: 16 files in report/{architecture_name}/
#   00_executive_dashboard.md   ⭐ PRIMARY - CISO report (NEW Phase 3D)
#   01_executive_summary.md     - Business stakeholders
#   02_technical_report.md      - Technical teams
#   03_action_plan.md           - Implementation roadmap
#   04_architect_critique.json  - Design quality validation
#   05_tester_critique.json     - MITRE validation
#   06_red_team_critique.json   - Exploit difficulty assessment
#   07_moe_orchestrator.json    - MoE consensus (NEW Phase 3D)
#   08_improvement_summary.md   - Human-readable improvement plan
#   08a_quick_wins.mmd          - Quick wins (CRITICAL, 1-2 weeks)
#   08b_recommended_target.mmd  - Recommended (CRITICAL+HIGH, 1-3 months) ⭐
#   08c_maximum_security.mmd    - Maximum security (all controls, 6+ months)
#   before.mmd                  - Current architecture
#   after.mmd                   - With all recommended controls
#   ground_truth.json           - Deterministic analysis data
#
# Usage:
#   ./demo_expert_llm.sh                    # Use example_architecture
#   ./demo_expert_llm.sh my_arch.mmd        # Use custom architecture
#
# Status: Phase 3D Week 1-3 Complete ✅
################################################################################

set -e  # Exit on error

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration (with argument support)
if [[ $# -eq 1 ]]; then
    # Custom architecture provided
    ARCHITECTURE_FILE="$1"
    ARCHITECTURE_NAME=$(basename "$ARCHITECTURE_FILE" .mmd)
    REPORT_DIR="report/$ARCHITECTURE_NAME"
    echo -e "${YELLOW}Using custom architecture: $ARCHITECTURE_FILE${NC}"
else
    # Default: Use minimal_vulnerable architecture
    ARCHITECTURE_FILE="tests/data/architectures/01_minimal_vulnerable.mmd"
    ARCHITECTURE_NAME=$(basename "$ARCHITECTURE_FILE" .mmd)
    REPORT_DIR="report/$ARCHITECTURE_NAME"
    echo -e "${YELLOW}Using default architecture: $ARCHITECTURE_FILE${NC}"
fi

echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║       Phase 3D Complete Pipeline Demo                       ║${NC}"
echo -e "${BLUE}║       MoE Validation + Coherent Dashboard                    ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Check environment
echo -e "${YELLOW}[1/6] Checking environment...${NC}"
if [[ "$VIRTUAL_ENV" == "" ]]; then
    echo -e "${RED}ERROR: Virtual environment not activated${NC}"
    echo "Run: source .venv/bin/activate"
    exit 1
fi

if [[ ! -f "$ARCHITECTURE_FILE" ]]; then
    echo -e "${RED}ERROR: Architecture file not found: $ARCHITECTURE_FILE${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Environment OK${NC}"
echo ""

# Clean existing reports
echo -e "${YELLOW}[2/6] Cleaning existing reports...${NC}"
if [[ -d "$REPORT_DIR" ]]; then
    # Remove all generated files
    rm -rf "$REPORT_DIR"/*.md "$REPORT_DIR"/*.json "$REPORT_DIR"/*.mmd 2>/dev/null || true
    echo -e "${GREEN}✅ Cleaned existing reports${NC}"
else
    mkdir -p "$REPORT_DIR"
    echo -e "${GREEN}✅ Created report directory${NC}"
fi
echo ""

# Show architecture
echo -e "${YELLOW}[3/6] Analyzing architecture...${NC}"
echo -e "${BLUE}Architecture:${NC}"
cat "$ARCHITECTURE_FILE"
echo ""

# Step 1: Generate deterministic analysis (ground_truth.json)
echo -e "${YELLOW}[4/6] Step 1: Deterministic Analysis (Layer 1)${NC}"
echo "Running: python3 -m chatbot.main --gen-arch-truth $ARCHITECTURE_FILE"
echo ""

python3 -m chatbot.main --gen-arch-truth "$ARCHITECTURE_FILE" 2>&1 | grep -E "Generating|✅|WARNING|ERROR" || true

if [[ ! -f "$REPORT_DIR/ground_truth.json" ]]; then
    echo -e "${RED}ERROR: ground_truth.json not generated${NC}"
    echo "Expected: $REPORT_DIR/ground_truth.json"
    echo "Check: report/ directory for actual location"
    exit 1
fi

echo ""
echo -e "${GREEN}✅ Deterministic analysis complete${NC}"
echo "   Files: ground_truth.json, 01-03 MD, before.mmd, after.mmd"
echo ""

# Step 2: Run MoE validation (Layer 2)
echo -e "${YELLOW}[5/6] Step 2: MoE Validation (Layer 2 - 3 Critics)${NC}"
echo "Running MoE pipeline..."
echo ""

python3 -c "
from chatbot.modules.agents import run_moe_pipeline
import sys

try:
    result = run_moe_pipeline('$REPORT_DIR')
    print('✅ MoE validation complete')
    print(f'   Final confidence: {result.final_confidence:.1f}%')
    print(f'   Critical items: {len(result.critical_recommendations)}')
    print(f'   High priority: {len(result.high_recommendations)}')
except Exception as e:
    print(f'ERROR: MoE validation failed: {e}', file=sys.stderr)
    import traceback
    traceback.print_exc()
    sys.exit(1)
" 2>&1

if [[ ! -f "$REPORT_DIR/07_moe_orchestrator.json" ]]; then
    echo -e "${RED}ERROR: MoE orchestrator output not generated${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}✅ MoE validation complete${NC}"
echo "   Files: 04-07 JSON (architect, tester, red_team, moe_orchestrator)"
echo ""

# Step 3: Generate executive dashboard (Layer 3)
echo -e "${YELLOW}[6/6] Step 3: Executive Dashboard (Layer 3)${NC}"
echo "Running: python3 -m chatbot.modules.executive_dashboard_generator $REPORT_DIR"
echo ""

python3 -m chatbot.modules.executive_dashboard_generator "$REPORT_DIR" 2>&1 | grep -E "Generating|✅|dashboard|ERROR" || true

if [[ ! -f "$REPORT_DIR/00_executive_dashboard.md" ]]; then
    echo -e "${RED}ERROR: Executive dashboard not generated${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}✅ Executive dashboard complete${NC}"
echo "   Files: 00_executive_dashboard.md"
echo ""

# Validation: Check all files
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}                    VALIDATION REPORT                          ${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo ""

FILE_COUNT=$(ls -1 "$REPORT_DIR" | wc -l)
echo -e "${YELLOW}Generated Files:${NC} $FILE_COUNT (expected: 16)"
echo ""

# Check required files
REQUIRED_FILES=(
    "ground_truth.json"
    "00_executive_dashboard.md"
    "01_executive_summary.md"
    "02_technical_report.md"
    "03_action_plan.md"
    "04_architect_critique.json"
    "05_tester_critique.json"
    "06_red_team_critique.json"
    "07_moe_orchestrator.json"
    "08_improvement_summary.md"
    "08a_quick_wins.mmd"
    "08b_recommended_target.mmd"
    "08c_maximum_security.mmd"
    "before.mmd"
    "after.mmd"
)

MISSING=0
for file in "${REQUIRED_FILES[@]}"; do
    if [[ -f "$REPORT_DIR/$file" ]]; then
        echo -e "${GREEN}✅${NC} $file"
    else
        echo -e "${RED}❌${NC} $file (MISSING)"
        MISSING=$((MISSING + 1))
    fi
done

echo ""

if [[ $MISSING -gt 0 ]]; then
    echo -e "${RED}ERROR: $MISSING files missing${NC}"
    exit 1
fi

echo -e "${GREEN}✅ All 15 files generated${NC}"
echo ""

# Extract key metrics from dashboard
echo -e "${YELLOW}Key Metrics (from dashboard):${NC}"
echo ""

if [[ -f "$REPORT_DIR/00_executive_dashboard.md" ]]; then
    # Extract risk values
    CURRENT_RISK=$(grep -oP "Current Risk: \K\d+" "$REPORT_DIR/00_executive_dashboard.md" | head -1)
    TARGET_RISK=$(grep -oP "Target Risk.*: \K\d+" "$REPORT_DIR/00_executive_dashboard.md" | head -1)
    REDUCTION=$(grep -oP "Risk Reduction: \K\d+%" "$REPORT_DIR/00_executive_dashboard.md" | head -1)
    CONFIDENCE=$(grep -oP "Confidence:\*\* \K[0-9.]+%" "$REPORT_DIR/00_executive_dashboard.md" | head -1)

    echo -e "  ${BLUE}Current Risk:${NC} $CURRENT_RISK/100"
    echo -e "  ${BLUE}Target Risk:${NC} $TARGET_RISK/100"
    echo -e "  ${BLUE}Risk Reduction:${NC} $REDUCTION"
    echo -e "  ${BLUE}Confidence:${NC} $CONFIDENCE"
    echo ""
fi

# Check dashboard narrative
echo -e "${YELLOW}Dashboard Narrative Check:${NC}"
if grep -q "Layer 1: Deterministic" "$REPORT_DIR/00_executive_dashboard.md"; then
    echo -e "${GREEN}✅${NC} Layer 1 (Deterministic) present"
fi
if grep -q "Layer 2: AI Validation" "$REPORT_DIR/00_executive_dashboard.md"; then
    echo -e "${GREEN}✅${NC} Layer 2 (AI Validation) present"
fi
if grep -q "Layer 3: This Dashboard" "$REPORT_DIR/00_executive_dashboard.md"; then
    echo -e "${GREEN}✅${NC} Layer 3 (Dashboard) present"
fi
echo ""

# Coherence check: Compare risk values across files
echo -e "${YELLOW}Coherence Check (Risk Values):${NC}"
DASHBOARD_RISK=$(grep -oP "Current Risk: \K\d+" "$REPORT_DIR/00_executive_dashboard.md" | head -1)
SUMMARY_RISK=$(grep -oP "Current Risk Score: \K\d+" "$REPORT_DIR/01_executive_summary.md" 2>/dev/null | head -1 || echo "N/A")

echo -e "  Dashboard (00_): ${BLUE}$DASHBOARD_RISK/100${NC}"
echo -e "  Summary (01_):   ${BLUE}$SUMMARY_RISK/100${NC}"

if [[ "$DASHBOARD_RISK" == "$SUMMARY_RISK" ]] || [[ "$SUMMARY_RISK" == "N/A" ]]; then
    echo -e "  ${GREEN}✅ Coherent${NC} (values match or N/A)"
else
    echo -e "  ${YELLOW}⚠️  Different values${NC} (may need regeneration of 01-03)"
fi
echo ""

# Success summary
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}                    ✅ DEMO COMPLETE                            ${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "${YELLOW}Next Steps:${NC}"
echo ""
echo -e "1. View primary report:"
echo -e "   ${BLUE}cat $REPORT_DIR/00_executive_dashboard.md${NC}"
echo ""
echo -e "2. View supporting details:"
echo -e "   ${BLUE}cat $REPORT_DIR/01_executive_summary.md${NC}   # Business summary"
echo -e "   ${BLUE}cat $REPORT_DIR/02_technical_report.md${NC}    # MITRE details"
echo -e "   ${BLUE}cat $REPORT_DIR/03_action_plan.md${NC}         # Implementation roadmap"
echo ""
echo -e "3. View validation data:"
echo -e "   ${BLUE}cat $REPORT_DIR/07_moe_orchestrator.json${NC}  # MoE consensus"
echo ""
echo -e "4. View improvement diagrams:"
echo -e "   ${BLUE}cat $REPORT_DIR/08b_recommended_target.mmd${NC} # Recommended roadmap ⭐"
echo ""
echo -e "${GREEN}Report location: $REPORT_DIR${NC}"
echo ""
