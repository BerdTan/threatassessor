#!/usr/bin/env python3
"""
Full 3-Agent Pipeline Test

Tests complete orchestration: Architect → Tester → Red Team → Unified Report
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from chatbot.modules.orchestrator import orchestrate_full_critique


def print_section(title: str):
    """Print section header."""
    print(f"\n{'='*70}")
    print(f"{title}")
    print(f"{'='*70}\n")


def main():
    """Run full 3-agent pipeline on defended architecture."""

    print_section("FULL 3-AGENT PIPELINE TEST - Phase 3C+")

    print("This test runs the complete orchestration:")
    print("  1. Architect → Design quality assessment")
    print("  2. Tester → MITRE validation (with Architect roadmap)")
    print("  3. Red Team → Exploit difficulty (with Tester gaps)")
    print("  4. Orchestrator → Unified assessment + roadmap")
    print()
    print("Target: 95% final confidence")
    print()

    # Test architecture
    report_dir = "report/02_minimal_defended"

    print_section("Running 3-Agent Orchestration")
    print(f"Architecture: {report_dir}")
    print()

    try:
        # Run orchestration
        result = orchestrate_full_critique(report_dir)

        print_section("RESULTS")

        # Individual scores
        print("Individual Agent Scores:")
        print(f"  Architect:  {result.architect_score}/100  (Design quality)")
        print(f"  Tester:     {result.tester_score}/100  (Validation)")
        print(f"  Red Team:   {result.red_team_exploit_score}/100 exploit")
        print(f"              {result.red_team_defense_score}/100 defense (inverted)")
        print()

        # Composite
        print(f"Composite Score: {result.composite_score}/100 ({result.composite_rating})")
        print(f"  Formula: ({result.architect_score}×0.3) + ({result.tester_score}×0.3) "
              f"+ ({result.red_team_defense_score}×0.4)")
        print()

        # Confidence
        print(f"Final Confidence: {result.final_confidence:.1f}%")
        print(f"  Deterministic base: {result.deterministic_confidence:.1f}%")
        print(f"  Gap penalty: -{result.gap_penalty*100:.1f}%")
        print(f"  Validated: {result.validated_confidence:.1f}%")
        print(f"  Consensus bonus: +{result.consensus_bonus:.1f}%")
        print(f"  Agent agreement: {result.agent_agreement}")
        print()

        # Unified roadmap
        print_section("UNIFIED IMPROVEMENT ROADMAP")

        print(f"Current: {result.recommended_target['current_composite']}/100")
        print(f"Target:  {result.recommended_target['target_composite']}/100")
        print(f"Improvement: +{result.recommended_target['improvement_needed']} points")
        print()

        print(f"Priority Recommendations ({len(result.unified_roadmap)} total):")
        print()

        # Show top 5
        for i, rec in enumerate(result.unified_roadmap[:5], 1):
            priority = rec.get("priority", "UNKNOWN")
            source = rec.get("source", "Unknown")
            action = rec.get("action", "Unknown")[:60]
            impact = rec.get("impact", "Unknown")
            effort = rec.get("effort", "Unknown")
            practical = rec.get("practical", "Unknown")

            print(f"{i}. [{priority}] {action}...")
            print(f"   Source: {source}")
            print(f"   Impact: {impact}")
            print(f"   Effort: {effort}")
            print(f"   Practical: {practical}")
            print()

        # Validation
        print_section("VALIDATION")

        success = True
        issues = []

        # Check composite score
        if result.composite_score < 75:
            issues.append(f"Composite score {result.composite_score} < 75")
            success = False

        # Check confidence
        if result.final_confidence < 90:
            issues.append(f"Final confidence {result.final_confidence:.1f}% < 90%")
            success = False

        # Check agents ran
        if result.architect_score == 0:
            issues.append("Architect score is 0")
            success = False

        if result.tester_score == 0:
            issues.append("Tester score is 0")
            success = False

        if result.red_team_exploit_score == 0:
            issues.append("Red Team score is 0")
            success = False

        # Check roadmap
        if len(result.unified_roadmap) == 0:
            issues.append("No unified roadmap generated")
            success = False

        if success:
            print("✅ ALL VALIDATIONS PASSED")
            print()
            print(f"   Composite: {result.composite_score}/100 ✅")
            print(f"   Confidence: {result.final_confidence:.1f}% ✅")
            print(f"   Roadmap: {len(result.unified_roadmap)} items ✅")
            print()
        else:
            print("⚠️  SOME VALIDATIONS FAILED")
            print()
            for issue in issues:
                print(f"   • {issue}")
            print()

        # Output files
        print_section("OUTPUT FILES")

        output_path = Path(report_dir) / "07_orchestrator_report.json"
        print(f"Orchestrator report: {output_path}")

        architect_path = Path(report_dir) / "04_architect_critique.json"
        tester_path = Path(report_dir) / "05_tester_critique.json"
        red_team_path = Path(report_dir) / "06_red_team_critique.json"

        print(f"Architect critique:  {architect_path if architect_path.exists() else 'Not saved'}")
        print(f"Tester critique:     {tester_path if tester_path.exists() else 'Not saved'}")
        print(f"Red Team critique:   {red_team_path if red_team_path.exists() else 'Not saved'}")
        print()

        # Summary
        print_section("SUMMARY")

        print("Phase 3C+ Full Pipeline:")
        print(f"  ✅ 3 agents completed successfully")
        print(f"  ✅ Composite score: {result.composite_score}/100 ({result.composite_rating})")
        print(f"  ✅ Final confidence: {result.final_confidence:.1f}%")
        print(f"  ✅ Unified roadmap: {len(result.unified_roadmap)} recommendations")
        print()

        if result.final_confidence >= 95:
            print(f"🎯 TARGET ACHIEVED: {result.final_confidence:.1f}% ≥ 95%")
        elif result.final_confidence >= 90:
            print(f"✅ EXCELLENT: {result.final_confidence:.1f}% (Close to target)")
        else:
            print(f"⚠️  BELOW TARGET: {result.final_confidence:.1f}% < 90%")

        print()

        return 0 if success else 1

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
