#!/usr/bin/env python3
"""
Red Teamer Confidence Check - Step 2: Vulnerable vs Defended Contrast

Tests if LLM can discriminate between vulnerable and defended architectures.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.agent_testing.test_red_team_confidence import run_confidence_check


def main():
    """
    Test contrast between vulnerable and defended architectures.

    Success criteria:
    - Vulnerable: 70-90 (EASY to exploit = BAD defense)
    - Defended: 20-40 (HARD to exploit = GOOD defense)
    - Contrast: >30 points difference
    """

    print("="*70)
    print("RED TEAMER CONFIDENCE CHECK - Step 2: Vulnerable vs Defended Contrast")
    print("="*70)
    print("\nGoal: Verify LLM can discriminate between vulnerable and defended")
    print("\nExpected:")
    print("  • Vulnerable (no controls): 70-90 (HIGH/CRITICAL = Easy to exploit)")
    print("  • Defended (with controls): 20-40 (LOW = Hard to exploit)")
    print("  • Contrast: >30 points")
    print()

    # Test 1: Vulnerable architecture (no controls)
    print("TEST 1: Vulnerable Architecture (No Controls)")
    print("="*70)
    vuln_result = run_confidence_check(
        report_dir="report/01_minimal_vulnerable",
        expected_range=(70, 90)
    )

    print("\n\n")

    # Test 2: Defended architecture (with controls)
    print("TEST 2: Defended Architecture (With Controls)")
    print("="*70)
    def_result = run_confidence_check(
        report_dir="report/02_minimal_defended",
        expected_range=(20, 40)
    )

    # Calculate contrast
    print("\n" + "="*70)
    print("CONTRAST ANALYSIS")
    print("="*70)

    vuln_score = vuln_result["score"]
    def_score = def_result["score"]
    contrast = vuln_score - def_score

    print(f"\nVulnerable:  {vuln_score}/100  (Expected: 70-90)")
    print(f"Defended:    {def_score}/100  (Expected: 20-40)")
    print(f"Contrast:    {contrast} points (Expected: >30)")
    print()

    # Success criteria
    success = True
    issues = []

    if not vuln_result["in_range"]:
        success = False
        issues.append(f"Vulnerable score {vuln_score} not in range 70-90")

    if not def_result["in_range"]:
        success = False
        issues.append(f"Defended score {def_score} not in range 20-40")

    if contrast < 30:
        success = False
        issues.append(f"Contrast {contrast} points < 30 (insufficient discrimination)")

    # Final verdict
    print("="*70)
    print("FINAL VERDICT")
    print("="*70)
    print()

    if success:
        print("✅ PASS - LLM successfully discriminates vulnerable vs defended!")
        print()
        print(f"   Vulnerable:  {vuln_score}/100  ({'HIGH' if vuln_score >= 70 else 'CRITICAL'} = Easy to exploit = BAD)")
        print(f"   Defended:    {def_score}/100  (LOW = Hard to exploit = GOOD)")
        print(f"   Contrast:    {contrast} points (Strong discrimination)")
        print()
        print("   🎯 Confidence: HIGH (>75%)")
        print()
        print("   ➡️  PROCEED TO PHASE 2: Full Red Teamer Implementation")
        print("       Estimated: 4 hours for complete rubric + integration")
        print()
        return 0
    else:
        print("⚠️  NEEDS ADJUSTMENT - Issues detected:")
        print()
        for issue in issues:
            print(f"   • {issue}")
        print()
        print("   🎯 Confidence: LOW (<75%)")
        print()
        print("   ➡️  REVISE APPROACH:")
        print("       1. Add more examples to prompt")
        print("       2. Emphasize control impact (WAF, MFA, EDR)")
        print("       3. Re-test after adjustments")
        print()
        return 1


if __name__ == "__main__":
    sys.exit(main())
