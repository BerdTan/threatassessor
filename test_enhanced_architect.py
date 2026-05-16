"""Test Enhanced Architect Critic with 10 artifacts"""

import sys
import json
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(message)s")

from chatbot.modules.artifact_extractor import extract_artifacts
from chatbot.modules.architect_critic import EnhancedArchitectCritic

def test_enhanced_architect(report_dir: str):
    """Test Enhanced Architect on a complete report."""

    print(f"\n{'='*70}")
    print(f"TESTING ENHANCED ARCHITECT")
    print(f"Report: {report_dir}")
    print(f"{'='*70}\n")

    # Extract artifacts
    print("Step 1: Extracting artifacts...")
    artifacts = extract_artifacts(report_dir)

    print(f"\n✅ Extracted {artifacts.completeness['overall']['present']}/10 artifacts")
    print(f"   Tier 1: {artifacts.completeness['tier1']['count']}/5")
    print(f"   Tier 2: {artifacts.completeness['tier2']['count']}/5")
    print(f"   Confidence bonus: +{artifacts.completeness['tier2']['confidence_bonus']:.1%}")

    # Create Enhanced Architect
    print("\nStep 2: Creating Enhanced Architect agent...")
    critic = EnhancedArchitectCritic()

    # Run critique
    print("\nStep 3: Running critique on all 10 artifacts...")
    score = critic.critique(artifacts)

    # Display results
    print(f"\n{'='*70}")
    print(f"CRITIQUE RESULTS")
    print(f"{'='*70}\n")

    print(f"Score: {score.score}/{score.max_score} ({score.rating})")

    print(f"\n📊 Breakdown:")
    tier1_total = 0
    tier2_total = 0
    for category, data in score.breakdown.items():
        cat_score = data.get('score', 0)
        cat_max = data.get('max', 0)

        # Check tier
        if category in ['threat_completeness', 'control_appropriateness', 'defense_in_depth', 'rapids_alignment']:
            tier1_total += cat_score
            tier_label = "[Tier 1]"
        else:
            tier2_total += cat_score
            tier_label = "[Tier 2]"

        print(f"  {tier_label} {category}: {cat_score}/{cat_max}")

    print(f"\n  Tier 1 subtotal: {tier1_total}/80")
    print(f"  Tier 2 subtotal: {tier2_total}/20")

    print(f"\n🔍 Gaps Found: {len(score.gaps)}")
    for i, gap in enumerate(score.gaps[:5], 1):  # Show first 5
        severity = gap.get('severity', 'UNKNOWN')
        category = gap.get('category', 'Unknown')
        desc = gap.get('description', 'No description')
        print(f"  {i}. [{severity}] {category}: {desc}")

    if len(score.gaps) > 5:
        print(f"  ... +{len(score.gaps) - 5} more gaps")

    print(f"\n✅ Strengths: {len(score.strengths)}")
    for i, strength in enumerate(score.strengths[:3], 1):
        print(f"  {i}. {strength}")

    print(f"\n{'='*70}")
    print(f"IMPROVEMENT ROADMAP")
    print(f"{'='*70}\n")

    if score.improvement_roadmap:
        total_gain = sum(item.get('points_gained', 0) for item in score.improvement_roadmap)
        target = min(score.score + total_gain, 100)
        print(f"Current: {score.score}/100 → Target: {target}/100 (+{total_gain} points)\n")

        for item in score.improvement_roadmap[:5]:  # Show first 5
            priority = item.get('priority', '?')
            action = item.get('action', 'N/A')
            points = item.get('points_gained', 0)
            effort = item.get('effort', 'N/A')
            verification = item.get('verification_method', 'N/A')

            print(f"Priority {priority}: {action}")
            print(f"  Points: +{points} | Effort: {effort}")
            print(f"  Verification: {verification}\n")

        if len(score.improvement_roadmap) > 5:
            print(f"... +{len(score.improvement_roadmap) - 5} more items")
    else:
        print("(No roadmap provided)")

    # Save results
    output_path = Path(report_dir) / "04_architect_critique.json"
    with open(output_path, 'w') as f:
        json.dump(score.to_dict(), f, indent=2)

    print(f"\n✅ Saved to: {output_path}\n")

    return score


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_enhanced_architect.py <report_dir>")
        print("Example: python test_enhanced_architect.py report/02_minimal_defended")
        sys.exit(1)

    report_dir = sys.argv[1]
    test_enhanced_architect(report_dir)
