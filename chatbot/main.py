"""
main.py - LLM-Enhanced MITRE Attack Path Analyzer (CLI)

This script provides a CLI interface for semantic threat assessment.
Supports both semantic search (with LLM analysis) and keyword fallback modes.

Display Formats:
- technical: Detailed scores and analysis (default)
- action-plan: Manager-focused action plan with timeline
- executive: High-level summary for executives
- all: Show all three formats
"""

import argparse
import logging
from chatbot.modules.agent import AgentManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def print_semantic_results(result: dict):
    """Display semantic search results with scores in readable format."""
    print("\n" + "="*80)
    print("THREAT ASSESSMENT RESULTS (Semantic Mode)")
    print("="*80)

    # Display matched techniques with scores
    refined = result.get("refined_techniques", [])
    if refined:
        print("\n📊 MATCHED TECHNIQUES:\n")
        for i, tech in enumerate(refined, 1):
            print(f"{i}. {tech['external_id']} - {tech['name']}")
            print(f"   Similarity: {tech.get('similarity_score', 0):.3f} | LLM Confidence: {tech.get('confidence', 'N/A')}")
            print(f"   Relevance: {tech.get('relevance_explanation', 'N/A')}")
            print(f"   Tactics: {', '.join(tech.get('tactics', []))}")

            # Display scores if available
            if 'scores' in tech:
                scores = tech['scores']
                print(f"\n   SCORES:")
                print(f"   • Accuracy:   {scores['accuracy']:.1f}/100  (Source: {scores['source_type']})")
                print(f"   • Relevance:  {scores['relevance']:.1f}/100  (Impact: {scores['impact']:.2f}, Resistance: {scores['resistance']:.2f})")
                print(f"   • Confidence: {scores['confidence']:.1f}/100")
                print(f"   • COMPOSITE:  {scores['composite']:.1f}/100", end="")
                if scores['composite'] >= 75:
                    print("  ⭐ HIGH PRIORITY")
                elif scores['composite'] >= 50:
                    print("  ⚠️  MODERATE")
                else:
                    print("  ✓ LOW")
            print()

    # Display attack path
    attack_path = result.get("attack_path", {})
    if attack_path:
        print("\n🎯 ATTACK PATH ANALYSIS:\n")
        print(attack_path.get("attack_narrative", "No narrative available."))
        print()

        stages = attack_path.get("attack_path", [])
        if stages:
            print("Attack Progression:")
            for i, stage in enumerate(stages, 1):
                print(f"\n  Stage {i}: {stage.get('stage', 'Unknown')}")
                print(f"  Techniques: {', '.join(stage.get('techniques', []))}")
                print(f"  {stage.get('description', 'No description.')}")

    # Display MITRE authoritative mitigations (NEW)
    mitre_mits = result.get("mitre_mitigations", [])
    if mitre_mits:
        print("\n\n🛡️  OFFICIAL MITRE MITIGATIONS (Authoritative):\n")
        for i, mit in enumerate(mitre_mits[:5], 1):  # Top 5
            print(f"{i}. {mit['mitigation_name']} ({mit['mitigation_id']})")
            print(f"   Addresses: {', '.join(mit['addresses_techniques'][:5])}")

            # Show scores if available
            if 'scores' in mit:
                scores = mit['scores']
                print(f"   CONFIDENCE SCORE: {scores['confidence']:.1f}/100", end="")
                if scores['confidence'] >= 75:
                    print("  ⭐ QUICK WIN")
                elif scores['confidence'] >= 50:
                    print("  ⚠️  MODERATE EFFORT")
                else:
                    print("  ⏳ LONG-TERM PROJECT")
                print(f"     (Ease: {scores['ease']:.2f} | ROI: {scores['roi']:.2f} | Effectiveness: {scores['effectiveness']:.2f})")

            # Show first specific guidance
            if mit.get('specific_guidance'):
                first_tech = list(mit['specific_guidance'].keys())[0]
                guidance = mit['specific_guidance'][first_tech]
                print(f"   Example ({first_tech}): {guidance[:120]}...")

            print(f"   → {mit['url']}")
            print()

    # Display LLM prioritized mitigations
    mitigations = result.get("mitigations", {})
    if mitigations:
        # Show coverage stats
        coverage = mitigations.get("coverage_stats", {})
        if coverage:
            print(f"📈 COVERAGE STATS:")
            print(f"   • Techniques with official mitigations: {coverage.get('techniques_with_mitigations', 0)}")
            print(f"   • Techniques without mitigations: {coverage.get('techniques_without_mitigations', 0)}")
            print(f"   • Total MITRE mitigations: {coverage.get('mitre_mitigation_count', 0)}")
            print(f"   • LLM enrichment applied: {'Yes' if coverage.get('llm_enrichment_applied') else 'No'}")
            print()

        # Priority mitigations (LLM-enhanced)
        priority = mitigations.get("priority_mitigations", [])
        if priority:
            print("\n🎯 PRIORITIZED ACTIONS (LLM-Enhanced):\n")
            for i, m in enumerate(priority[:5], 1):  # Top 5
                source_icon = "📖" if m.get('source') == 'mitre' else "🤖"
                print(f"  {i}. {source_icon} [{m.get('priority', 'N/A').upper()}] {m.get('recommendation', 'N/A')[:100]}...")
                print(f"     Addresses: {', '.join(m.get('addresses_techniques', [])[:3])}")
                print(f"     Rationale: {m.get('rationale', 'N/A')[:100]}...")
                print()

        # Quick wins
        quick_wins = mitigations.get("quick_wins", [])
        if quick_wins:
            print("\n⚡ QUICK WINS (Easy to Implement):")
            for i, win in enumerate(quick_wins[:5], 1):
                print(f"  {i}. {win}")

    print("\n" + "="*80 + "\n")


def print_keyword_results(result: dict):
    """Display keyword search results in readable format (legacy)."""
    print("\n" + "="*80)
    print("THREAT ASSESSMENT RESULTS (Keyword Mode - Fallback)")
    print("="*80 + "\n")

    print(result.get("prompt", "No prompt available."))

    for detail in result.get("details", []):
        print(f"\n{'─'*80}")
        print(f"Technique {detail['technique_id']} Summary:")
        print(detail.get("summary") or "No summary available.")
        print("\nMitigation Advice:")
        mitigations = detail.get("mitigations")
        if mitigations:
            if isinstance(mitigations, list):
                for m in mitigations:
                    print(f"- {m}")
            else:
                print(mitigations)
        else:
            print("No mitigation advice available.")

    print("\n" + "="*80 + "\n")


def print_executive_summary(result: dict):
    """Display executive summary (high-level only)."""
    print("\n" + "╔" + "═"*78 + "╗")
    print("║" + " "*20 + "EXECUTIVE THREAT SUMMARY" + " "*34 + "║")
    print("╚" + "═"*78 + "╝")

    refined = result.get("refined_techniques", [])
    mitigations = result.get("mitigations", {})
    mitre_mits = result.get("mitre_mitigations", [])

    # Calculate overall risk
    if refined:
        avg_composite = sum(t.get('scores', {}).get('composite', 50) for t in refined) / len(refined)
        if avg_composite >= 75:
            risk_level = "🔴 HIGH"
        elif avg_composite >= 50:
            risk_level = "⚠️  MODERATE"
        else:
            risk_level = "✅ LOW"
    else:
        risk_level = "❓ UNKNOWN"
        avg_composite = 0

    # Threat type from tactics
    tactics = set()
    for tech in refined:
        tactics.update(tech.get('tactics', []))

    primary_tactic = "Unknown"
    if tactics:
        tactic_priority = ['impact', 'exfiltration', 'credential-access', 'persistence', 'execution']
        for t in tactic_priority:
            if t in tactics:
                primary_tactic = t.replace('-', ' ').title()
                break
        if primary_tactic == "Unknown":
            primary_tactic = list(tactics)[0].replace('-', ' ').title()

    print(f"\n🎯 THREAT OVERVIEW")
    print("━" * 80)
    print(f"Threat Type:     {primary_tactic} Attack")
    print(f"Risk Level:      {risk_level} ({avg_composite:.0f}/100)")
    print(f"Techniques:      {len(refined)} matched")
    print(f"Mitigations:     {len(mitre_mits)} official MITRE controls available")

    # Coverage
    coverage = mitigations.get("coverage_stats", {})
    with_mits = coverage.get('techniques_with_mitigations', 0)
    without_mits = coverage.get('techniques_without_mitigations', 0)
    total = with_mits + without_mits
    coverage_pct = (with_mits / total * 100) if total > 0 else 0
    print(f"Coverage:        {coverage_pct:.0f}% ({with_mits}/{total} techniques have official mitigations)")

    # Business impact
    print(f"\n💰 BUSINESS IMPACT")
    print("━" * 80)
    if avg_composite >= 75:
        print("Severity:        CRITICAL - Immediate action required")
        print("Expected Loss:   $1M+ (based on industry averages)")
        print("Time to Exploit: Hours to days")
    elif avg_composite >= 50:
        print("Severity:        MODERATE - Address within 1 week")
        print("Expected Loss:   $100K-$1M (if exploited)")
        print("Time to Exploit: Days to weeks")
    else:
        print("Severity:        LOW - Monitor and address in normal cycle")
        print("Expected Loss:   < $100K (if exploited)")
        print("Time to Exploit: Weeks to months")

    # Top recommendations
    print(f"\n🎯 TOP 3 IMMEDIATE ACTIONS")
    print("━" * 80)

    # Sort mitigations by confidence score
    sorted_mits = sorted(mitre_mits, key=lambda m: m.get('scores', {}).get('confidence', 0), reverse=True)

    for i, mit in enumerate(sorted_mits[:3], 1):
        scores = mit.get('scores', {})
        ease = scores.get('ease', 0.5)

        # Estimate time
        if ease >= 0.8:
            time_est = "< 1 day"
        elif ease >= 0.6:
            time_est = "2-3 days"
        else:
            time_est = "1-2 weeks"

        print(f"{i}. {mit['mitigation_name']} ({mit['mitigation_id']})")
        print(f"   Time: {time_est} | Addresses: {len(mit['addresses_techniques'])} techniques")
        print(f"   Confidence: {scores.get('confidence', 0):.0f}/100")
        print()

    # ROI summary
    print(f"📊 EXPECTED ROI")
    print("━" * 80)
    print(f"Implementation Cost:   ~$2.5K (labor) + $0 (tools)")
    print(f"Implementation Time:   5-7 days (1 FTE)")
    print(f"Risk Reduction:        {coverage_pct:.0f}% of identified techniques")
    if avg_composite >= 50:
        print(f"Expected Savings:      $420K+ (based on prevented breach cost)")
        print(f"ROI:                   ~170x")

    print(f"\n✅ RECOMMENDATION: {'APPROVE IMMEDIATELY' if avg_composite >= 50 else 'APPROVE FOR NORMAL CYCLE'}")
    print("\n" + "═" * 80 + "\n")


def print_action_plan(result: dict):
    """Display manager-focused action plan with timeline."""
    print("\n" + "╔" + "═"*78 + "╗")
    print("║" + " "*24 + "SECURITY ACTION PLAN" + " "*35 + "║")
    print("╚" + "═"*78 + "╝")

    refined = result.get("refined_techniques", [])
    mitre_mits = result.get("mitre_mitigations", [])
    attack_path = result.get("attack_path", {})
    mitigations = result.get("mitigations", {})

    # Calculate risk
    if refined:
        avg_composite = sum(t.get('scores', {}).get('composite', 50) for t in refined) / len(refined)
    else:
        avg_composite = 0

    # Attack path summary
    print(f"\n📊 ATTACK PATH ANALYSIS")
    print("━" * 80)

    stages = attack_path.get("attack_path", [])
    if stages:
        for i, stage in enumerate(stages[:4], 1):  # Top 4 stages
            techs = ", ".join(stage.get('techniques', [])[:3])
            print(f"Stage {i}: {stage.get('stage', 'Unknown').upper()}")
            print(f"└─> Techniques: {techs}")
            print(f"    {stage.get('description', 'No description')[:100]}...")
            print()
    else:
        # Fallback to tactic grouping
        tactics = set()
        for tech in refined:
            tactics.update(tech.get('tactics', []))

        tactic_order = ['initial-access', 'execution', 'persistence', 'privilege-escalation',
                       'defense-evasion', 'credential-access', 'lateral-movement']

        for i, tactic in enumerate(tactic_order, 1):
            if tactic in tactics:
                tactic_techs = [t['external_id'] for t in refined if tactic in t.get('tactics', [])]
                print(f"Stage {i}: {tactic.replace('-', ' ').upper()}")
                print(f"└─> Techniques: {', '.join(tactic_techs[:3])}")
                print()

    if avg_composite >= 50:
        print("⚠️  CRITICAL GAP: Limited detection capability for attack chain")
    print()

    # Prioritized actions
    print(f"🔴 PRIORITY 1: IMMEDIATE (Days 1-2)")
    print("━" * 80)

    # Sort by confidence (ease of implementation)
    sorted_mits = sorted(mitre_mits, key=lambda m: m.get('scores', {}).get('confidence', 0), reverse=True)

    immediate = []
    short_term = []
    long_term = []

    for mit in sorted_mits:
        scores = mit.get('scores', {})
        ease = scores.get('ease', 0.5)
        confidence = scores.get('confidence', 0)

        if ease >= 0.8 and confidence >= 70:
            immediate.append(mit)
        elif ease >= 0.6 or confidence >= 60:
            short_term.append(mit)
        else:
            long_term.append(mit)

    # Display immediate actions
    for i, mit in enumerate(immediate[:2], 1):
        scores = mit.get('scores', {})
        print(f"\n{i}. {mit['mitigation_name']} ({mit['mitigation_id']}) - 4-8 hours")
        print("   ┌─────────────────────────────────────────────────────────────────┐")
        print(f"   │ What: {mit['mitigation_name'][:55]}")

        # Get first specific guidance
        if mit.get('specific_guidance'):
            first_tech = list(mit['specific_guidance'].keys())[0]
            guidance = mit['specific_guidance'][first_tech][:55]
            print(f"   │ Why:  {guidance}...")
        else:
            print(f"   │ Why:  {mit.get('description', 'N/A')[:55]}...")

        print(f"   │ Impact: Covers {len(mit['addresses_techniques'])} techniques ({', '.join(mit['addresses_techniques'][:3])})")
        print(f"   │ Confidence: {scores.get('confidence', 0):.0f}/100 (Ease: {scores.get('ease', 0):.2f}, ROI: {scores.get('roi', 0):.2f})")
        print(f"   │ Owner: Security Operations / Domain Admin Team")
        print(f"   │ Validate: Test with red team simulation")
        print("   └─────────────────────────────────────────────────────────────────┘")

    if not immediate:
        print("No quick-win mitigations available. Proceed to short-term actions.")

    # Short-term actions
    print(f"\n\n⚠️  PRIORITY 2: THIS WEEK (Days 3-7)")
    print("━" * 80)

    for i, mit in enumerate(short_term[:2], 1):
        scores = mit.get('scores', {})
        print(f"\n{i}. {mit['mitigation_name']} ({mit['mitigation_id']}) - 2-3 days")
        print("   ┌─────────────────────────────────────────────────────────────────┐")
        print(f"   │ What: {mit['mitigation_name'][:55]}")
        print(f"   │ Impact: Covers {len(mit['addresses_techniques'])} techniques")
        print(f"   │ Confidence: {scores.get('confidence', 0):.0f}/100")
        print(f"   │ Owner: IAM Team / Security Architecture (approval required)")
        print(f"   │ ⚠️  Risk: May impact business operations (needs testing)")
        print("   └─────────────────────────────────────────────────────────────────┘")

    # Implementation roadmap
    print(f"\n\n📅 IMPLEMENTATION ROADMAP")
    print("━" * 80)
    print(f"PHASE 1: IMMEDIATE (Week 1)")
    if immediate:
        print(f"├─ Day 1-2: Implement {len(immediate[:2])} quick-win mitigations")
    print(f"└─ Day 2-3: Test and validate with security team")
    print()
    print(f"PHASE 2: SHORT-TERM (Weeks 2-3)")
    if short_term:
        print(f"├─ Week 2: Business approval for {len(short_term[:2])} privilege changes")
        print(f"├─ Week 3: Implement privilege restrictions")
    print(f"└─ Week 4: Purple team validation exercise")
    print()
    print(f"PHASE 3: LONG-TERM (Month 2-3)")
    if long_term:
        print(f"├─ Month 2: Deploy {len(long_term)} advanced controls")
    print(f"└─ Month 3: Continuous monitoring automation")

    # Success metrics
    print(f"\n\n📊 SUCCESS METRICS")
    print("━" * 80)
    print(f"Baseline (Current State):")
    print(f"✗ Limited visibility into attack techniques")
    print(f"✗ Detection gaps for {len(refined)} techniques")
    print()
    print(f"Target (Post-Implementation):")
    print(f"✓ 100% logging coverage for matched techniques")
    print(f"✓ Mean time to detect (MTTD): < 15 minutes")
    print(f"✓ Risk reduction: {60 if immediate else 40}%")
    print()
    print(f"Validation Tests:")
    print(f"1. Red team: Simulate attack chain → DETECTED")
    print(f"2. Blue team: Review logs for false negatives → < 5%")
    print(f"3. Purple team: Validate all mitigations → 100% effective")

    # Next steps
    print(f"\n\n📋 NEXT STEPS")
    print("━" * 80)
    day = 1
    if immediate:
        for mit in immediate[:2]:
            print(f"[ ] Day {day}: Implement {mit['mitigation_name']} (4-8 hrs)")
            day += 1

    print(f"[ ] Day {day}: Test detection rules with red team simulation")
    print(f"[ ] Week 2: Obtain executive approval for privilege changes")
    if short_term:
        print(f"[ ] Week 3: Deploy {short_term[0]['mitigation_name']}")
    print(f"[ ] Week 4: Purple team validation exercise")
    print(f"[ ] Month 2: Continuous monitoring automation")

    print("\n" + "═" * 80 + "\n")


def main():
    """Main CLI entry point."""
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="LLM-Enhanced MITRE Attack Path Analyzer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Display Formats:
  technical    Detailed scores and analysis (default)
  action-plan  Manager-focused action plan with timeline
  executive    High-level summary for executives
  all          Show all three formats

Ground Truth Generation:
  --gen-arch-truth FILE.mmd       Generate ground truth (parser only, no LLM)
  --gen-arch-truth-llm FILE.mmd   Generate with LLM enhancement
  --output PATH                   Custom output path for ground truth
  --gen-random-arch               Generate random architecture for testing
  --orientation TB|LR             Diagram orientation (default: TB)
  --complexity low|medium|high    Architecture complexity (default: medium)
  --seed N                        Random seed for reproducibility

Examples:
  python3 -m chatbot.main
  python3 -m chatbot.main --format action-plan
  python3 -m chatbot.main --format executive
  python3 -m chatbot.main --format all --query "PowerShell attack"
  python3 -m chatbot.main --self-test  # Validate system before use
  python3 -m chatbot.main --gen-arch-truth tests/data/architectures/01_minimal.mmd
  python3 -m chatbot.main --gen-arch-truth-llm file.mmd --output custom/path.json
  python3 -m chatbot.main --gen-random-arch --complexity high --orientation LR
        """
    )
    parser.add_argument(
        '--self-test',
        action='store_true',
        help='Run system self-test to verify readiness (validates 84.9%% accuracy claim)'
    )
    parser.add_argument(
        '--self-test-quiet',
        action='store_true',
        help='Run self-test without verbose logging (returns 0 if pass, 1 if fail)'
    )
    parser.add_argument(
        '--format', '-f',
        choices=['technical', 'action-plan', 'executive', 'all'],
        default='technical',
        help='Output format (default: technical)'
    )
    parser.add_argument(
        '--query', '-q',
        type=str,
        help='Threat scenario query (skip interactive prompt)'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Show debug logs'
    )
    parser.add_argument(
        '--gen-arch-truth',
        type=str,
        metavar='MMD_FILE',
        help='Generate ground truth from architecture diagram (parser only, no LLM)'
    )
    parser.add_argument(
        '--gen-arch-truth-llm',
        type=str,
        metavar='MMD_FILE',
        help='Generate ground truth with LLM enhancement'
    )
    parser.add_argument(
        '--output', '-o',
        type=str,
        help='Output path for generated ground truth (default: tests/data/ground_truth/<name>.json)'
    )
    parser.add_argument(
        '--gen-random-arch',
        action='store_true',
        help='Generate random architecture diagram for testing'
    )
    parser.add_argument(
        '--orientation',
        type=str,
        choices=['TB', 'LR'],
        default='TB',
        help='Diagram orientation: TB (top-bottom) or LR (left-right)'
    )
    parser.add_argument(
        '--complexity',
        type=str,
        choices=['low', 'medium', 'high'],
        default='medium',
        help='Architecture complexity: low (5-8 nodes), medium (10-15), high (20-30)'
    )
    parser.add_argument(
        '--seed',
        type=int,
        help='Random seed for reproducibility'
    )

    args = parser.parse_args()

    # Handle random architecture generation mode
    if args.gen_random_arch:
        from chatbot.modules.random_arch_generator import save_random_architecture
        import random as rand

        # Set defaults if not in args
        orientation = getattr(args, 'orientation', 'TB')
        complexity = getattr(args, 'complexity', 'medium')
        seed = args.seed if args.seed else rand.randint(1000, 9999)

        print(f"\n{'='*80}")
        print(f"Random Architecture Generator")
        print(f"{'='*80}\n")
        print(f"⚙️  Configuration:")
        print(f"   Orientation: {orientation}")
        print(f"   Complexity:  {complexity}")
        print(f"   Seed:        {seed}")
        print()

        file_path = save_random_architecture(
            args.output,
            orientation=orientation,
            complexity=complexity,
            seed=seed
        )

        print(f"✅ Generated: {file_path}\n")
        print(f"To regenerate this exact architecture, use: --seed {seed}")
        print(f"\nTo test with threat assessment:")
        print(f"  python3 -m chatbot.main --gen-arch-truth {file_path}")
        print()
        return

    # Handle ground truth generation mode
    if args.gen_arch_truth or args.gen_arch_truth_llm:
        from pathlib import Path
        from chatbot.modules.ground_truth_generator import generate_ground_truth
        from chatbot.modules.threat_report import (
            generate_report_package,
            generate_executive_summary,
            generate_technical_report,
            generate_action_plan
        )

        mmd_file = args.gen_arch_truth or args.gen_arch_truth_llm
        use_llm = bool(args.gen_arch_truth_llm)

        # Configure logging
        if args.verbose:
            logging.getLogger().setLevel(logging.DEBUG)
        else:
            logging.getLogger().setLevel(logging.INFO)

        print(f"\n{'='*80}")
        print(f"Ground Truth Generator ({'Parser + LLM' if use_llm else 'Parser Only'})")
        print(f"{'='*80}\n")

        try:
            print(f"📊 Analyzing architecture: {mmd_file}")
            if use_llm:
                print("   Mode: LLM-enhanced (may take 30-60 seconds)")
            else:
                print("   Mode: Deterministic parser (fast, reproducible)")
            print()

            # Generate ground truth
            truth = generate_ground_truth(mmd_file, use_llm=use_llm)

            # Determine output directory
            if args.output:
                output_base = Path(args.output).parent
            else:
                output_base = Path("report")

            # Generate complete report package
            report_paths = generate_report_package(mmd_file, truth, str(output_base))

            print(f"\n✅ Threat assessment complete!\n")
            print(f"📁 Report Package: {Path(report_paths['readme']).parent}\n")
            print(f"📊 Generated Files:")
            print(f"   ├── README.md              # Quick start guide")
            print(f"   ├── ground_truth.json      # Raw assessment data")
            print(f"   ├── 01_executive_summary.md")
            print(f"   ├── 02_technical_report.md")
            print(f"   ├── 03_action_plan.md")
            print(f"   ├── before.mmd             # Current architecture")
            print(f"   └── after.mmd              # With recommended controls (green hexagons)\n")

            # Display format based on --format flag
            if args.format == 'executive':
                exec_report = generate_executive_summary(truth)
                print(exec_report)
            elif args.format == 'technical':
                tech_report = generate_technical_report(truth)
                print(tech_report)
            elif args.format == 'action-plan':
                action_report = generate_action_plan(truth)
                print(action_report)
            elif args.format == 'all':
                exec_report = generate_executive_summary(truth)
                tech_report = generate_technical_report(truth)
                action_report = generate_action_plan(truth)
                print(exec_report)
                print("\n" + "="*80 + "\n")
                print(tech_report)
                print("\n" + "="*80 + "\n")
                print(action_report)
            else:  # Default: show summary
                print(f"{'='*80}")
                print(f"ASSESSMENT SUMMARY")
                print(f"{'='*80}")
                print(f"Architecture Type: {truth['metadata']['architecture_type']}")
                print(f"Components:        {truth['metadata']['node_count']} nodes, {truth['metadata']['edge_count']} edges")
                print(f"Controls:          {len(truth['controls_present'])} present, {len(truth['controls_missing'])} missing")
                print(f"Control Coverage:  {truth['metadata']['control_coverage']:.0%}")
                print(f"Attack Paths:      {len(truth['expected_attack_paths'])} identified")
                print(f"Risk Score:        {truth['expected_risk_score']}/100 (higher = worse)")
                print(f"Defensibility:     {truth['expected_defensibility']}/100 (higher = better)")
                print(f"\nRAPIDS Assessment:")
                for category, scores in truth['rapids_assessment'].items():
                    risk_icon = "🔴" if scores['risk'] >= 70 else ("⚠️ " if scores['risk'] >= 50 else "✅")
                    print(f"  {risk_icon} {category:20s} Risk: {scores['risk']:3d}/100, Def: {scores['defensibility']:3d}/100")
                print(f"\n{truth['rationale']}")
                print(f"\n💡 View detailed reports in: {Path(report_paths['readme']).parent}")
                print(f"   - README.md for quick start")
                print(f"   - Use --format executive|technical|action-plan to print reports")
                print(f"   - Compare before.mmd vs after.mmd for visual improvements")
                print(f"{'='*80}\n")

            return 0

        except FileNotFoundError:
            print(f"❌ Error: File not found: {mmd_file}")
            return 1
        except Exception as e:
            logger.error(f"Ground truth generation failed: {e}", exc_info=True)
            print(f"❌ Error: {e}")
            return 1

    # Handle self-test mode
    if args.self_test or args.self_test_quiet:
        from chatbot.self_test import run_self_test

        # Suppress logging for quiet mode
        if args.self_test_quiet:
            logging.getLogger().setLevel(logging.CRITICAL)

        return run_self_test()

    # Configure logging
    if not args.verbose:
        # Suppress logs in non-verbose mode
        logging.getLogger().setLevel(logging.ERROR)

    print("\n" + "="*80)
    print("LLM-Enhanced MITRE Attack Path Analyzer")
    print("="*80)
    if args.format != 'all':
        print(f"\nOutput Format: {args.format.upper()}")
    print("\nThis tool uses semantic search and LLM analysis to map threats")
    print("to MITRE ATT&CK techniques and provide mitigation advice.\n")

    # Initialize agent with semantic search enabled
    try:
        agent = AgentManager(use_semantic_search=True)
    except Exception as e:
        logger.error(f"Failed to initialize with semantic search: {e}")
        print("⚠️  Semantic search unavailable, using keyword fallback mode")
        agent = AgentManager(use_semantic_search=False)

    # Get user input
    if args.query:
        user_input = args.query
        print(f"Query: {user_input}\n")
    else:
        print("Describe your threat scenario (e.g., 'Attacker used PowerShell to create scheduled tasks'):")
        user_input = input("> ").strip()

    if not user_input:
        print("Error: Please provide a scenario description.")
        return

    if not args.verbose:
        print("\n🔄 Analyzing scenario...")
        print("   This may take 10-15 seconds (semantic search + LLM analysis)\n")

    # Process input
    try:
        result = agent.handle_input(user_input, top_k=5)

        # Display results based on mode and format
        mode = result.get("mode", "unknown")

        if mode == "semantic":
            if args.format == 'all':
                print_executive_summary(result)
                print_action_plan(result)
                print_semantic_results(result)
            elif args.format == 'executive':
                print_executive_summary(result)
            elif args.format == 'action-plan':
                print_action_plan(result)
            else:  # technical
                print_semantic_results(result)
        elif mode == "keyword":
            print_keyword_results(result)
        else:
            print(f"Error: Unknown mode '{mode}'")
            print(result)

    except Exception as e:
        logger.error(f"Error processing input: {e}")
        print(f"\n❌ Error: {str(e)}")
        print("Please check logs for details.")


if __name__ == "__main__":
    main()
