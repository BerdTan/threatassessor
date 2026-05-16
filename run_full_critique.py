#!/usr/bin/env python3
"""
Run full critique pipeline: Architect → Tester (with roadmap).

Usage:
    python3 run_full_critique.py report/02_minimal_defended
"""

import sys
import json
from pathlib import Path

from chatbot.modules.artifact_extractor import extract_artifacts
from chatbot.modules.architect_critic import EnhancedArchitectCritic
from chatbot.modules.tester_critic import TesterCritic


def run_full_critique(report_dir: str):
    """
    Run Architect → Tester critique pipeline.

    Args:
        report_dir: Path to report directory (e.g., report/02_minimal_defended)
    """
    report_path = Path(report_dir)

    if not report_path.exists():
        print(f"❌ Error: {report_dir} does not exist")
        sys.exit(1)

    print(f"Running full critique on: {report_dir}")
    print("=" * 70)

    # Step 1: Extract artifacts
    print("\n[Step 1] Extracting artifacts...")
    artifacts = extract_artifacts(str(report_path))
    print(f"✅ Extracted {artifacts.completeness['overall']['present']}/10 artifacts")

    # Step 2: Run Architect
    print("\n[Step 2] Running Architect critic...")
    architect = EnhancedArchitectCritic()
    architect_score = architect.critique(artifacts)

    print(f"✅ Architect Score: {architect_score.score}/100 ({architect_score.rating})")
    print(f"   Breakdown:")
    for category, data in architect_score.breakdown.items():
        print(f"     {category}: {data.get('score', 0)}/{data.get('max', 0)}")
    print(f"   Gaps: {len(architect_score.gaps)}")
    print(f"   Roadmap: {len(architect_score.improvement_roadmap)} items")

    # Save Architect output
    architect_output = report_path / "04_architect_critique.json"
    with open(architect_output, 'w') as f:
        json.dump(architect_score.to_dict(), f, indent=2)
    print(f"   Saved: {architect_output}")

    # Step 3: Run Tester with Architect roadmap
    print("\n[Step 3] Running Tester critic (with Architect roadmap)...")
    tester = TesterCritic()
    tester_score = tester.critique(artifacts, architect_score)

    print(f"✅ Tester Score: {tester_score.score}/100 ({tester_score.rating})")
    print(f"   Breakdown:")
    for category, data in tester_score.breakdown.items():
        print(f"     {category}: {data.get('score', 0)}/{data.get('max', 0)}")
    print(f"   Gaps: {len(tester_score.gaps)}")

    # Save Tester output
    tester_output = report_path / "05_tester_critique.json"
    with open(tester_output, 'w') as f:
        json.dump(tester_score.to_dict(), f, indent=2)
    print(f"   Saved: {tester_output}")

    # Step 4: Summary
    print("\n" + "=" * 70)
    print("CRITIQUE SUMMARY")
    print("=" * 70)
    print(f"\nArchitect: {architect_score.score}/100 ({architect_score.rating})")
    print(f"  Focus: Design quality, threat modeling, defense-in-depth")
    print(f"  Roadmap: {len(architect_score.improvement_roadmap)} improvement items")

    print(f"\nTester: {tester_score.score}/100 ({tester_score.rating})")
    print(f"  Focus: MITRE validation, coverage, consistency, roadmap validation")
    print(f"  Roadmap validated: {'✅ YES' if architect_score.improvement_roadmap else '❌ NO'}")

    # Composite score (Architect 30%, Tester 30%, Red Team 40% - but Red Team not implemented)
    # For now: Architect 50%, Tester 50%
    composite = (architect_score.score * 0.5 + tester_score.score * 0.5)
    print(f"\nComposite Score (Architect 50% + Tester 50%): {composite:.1f}/100")

    if composite >= 85:
        print("  Rating: ⭐⭐⭐⭐⭐ EXCELLENT")
    elif composite >= 70:
        print("  Rating: ⭐⭐⭐⭐ GOOD")
    elif composite >= 50:
        print("  Rating: ⭐⭐⭐ FAIR")
    else:
        print("  Rating: ⭐⭐ POOR")

    print("\n" + "=" * 70)
    print(f"✅ Full critique complete!")
    print(f"   Architect: {architect_output}")
    print(f"   Tester:    {tester_output}")

    return architect_score, tester_score


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 run_full_critique.py <report_dir>")
        print("Example: python3 run_full_critique.py report/02_minimal_defended")
        sys.exit(1)

    report_dir = sys.argv[1]
    run_full_critique(report_dir)
