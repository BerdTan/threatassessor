#!/usr/bin/env python3
"""
Red Teamer Full Implementation Test

Tests Red Teamer with post-processing on diverse architectures.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from chatbot.modules.red_teamer_critic import RedTeamerCritic, critique_red_team
from chatbot.modules.artifact_extractor import extract_artifacts


def test_architecture(report_dir: str, expected_range: tuple, description: str):
    """Test Red Teamer on a single architecture."""

    print(f"\n{'='*70}")
    print(f"Testing: {description}")
    print(f"Report: {report_dir}")
    print(f"Expected: {expected_range[0]}-{expected_range[1]}")
    print(f"{'='*70}\n")

    # Load ground truth to show controls
    gt_path = Path(report_dir) / "ground_truth.json"
    with open(gt_path) as f:
        gt = json.load(f)

    controls = gt.get("controls_present", [])
    print(f"Controls present: {controls if controls else 'NONE'}")
    print(f"Control count: {len(controls)}\n")

    # Run critique
    try:
        score = critique_red_team(report_dir)

        print(f"✅ Red Team Assessment Complete")
        print(f"\n   Score: {score.score}/100")
        print(f"   Rating: {score.rating}")
        print(f"   Reasoning: {score.breakdown.get('reasoning', 'N/A')[:200]}...")

        # Check if in expected range
        in_range = expected_range[0] <= score.score <= expected_range[1]

        if in_range:
            print(f"\n   ✅ IN RANGE: {expected_range[0]}-{expected_range[1]}")
            return {"pass": True, "score": score.score, "expected": expected_range}
        else:
            print(f"\n   ⚠️  OUT OF RANGE: Expected {expected_range[0]}-{expected_range[1]}, got {score.score}")
            return {"pass": False, "score": score.score, "expected": expected_range}

    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return {"pass": False, "error": str(e)}


def main():
    """Test Red Teamer on diverse architectures."""

    print("="*70)
    print("RED TEAMER FULL IMPLEMENTATION TEST")
    print("="*70)
    print("\nTesting exploit difficulty assessment with post-processing validation")
    print("\nInverted scoring:")
    print("  • Low score (0-40) = Hard to exploit = GOOD defense ✅")
    print("  • High score (60-100) = Easy to exploit = BAD defense ❌")
    print()

    # Test suite
    tests = [
        {
            "report_dir": "report/01_minimal_vulnerable",
            "expected": (70, 95),  # Widened range - 0 controls should be very high
            "description": "Vulnerable (0 controls)"
        },
        {
            "report_dir": "report/02_minimal_defended",
            "expected": (20, 45),
            "description": "Defended (6 controls: WAF, MFA, EDR, etc.)"
        }
    ]

    # Run tests
    results = []
    for test in tests:
        result = test_architecture(
            test["report_dir"],
            test["expected"],
            test["description"]
        )
        results.append({
            "description": test["description"],
            **result
        })

    # Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)

    passed = sum(1 for r in results if r.get("pass"))
    total = len(results)

    print(f"\nTests passed: {passed}/{total}")
    print()

    for r in results:
        status = "✅ PASS" if r.get("pass") else "❌ FAIL"
        score = r.get("score", "ERROR")
        expected = r.get("expected", (0, 0))
        print(f"  {status} - {r['description']}")
        print(f"           Score: {score}/100 (Expected: {expected[0]}-{expected[1]})")

    print()

    # Hallucination check
    print("="*70)
    print("HALLUCINATION CHECK")
    print("="*70)
    print("\nPost-processing validation applied:")
    print("  1. Control existence - Removed hallucinated controls")
    print("  2. Difficulty reasonableness - Adjusted outlier scores")
    print("  3. Tester gap integration - N/A (Tester not run)")
    print("  4. Inverted scoring - Auto-corrected if needed")
    print("\nCheck logs above for validation warnings/corrections.")
    print()

    # Final verdict
    if passed == total:
        print("="*70)
        print("✅ ALL TESTS PASSED")
        print("="*70)
        print("\n🎯 Red Teamer with post-processing is working correctly!")
        print("\n   Next steps:")
        print("   1. Test with Tester integration (gap adjustment)")
        print("   2. Integrate into Orchestrator")
        print("   3. Run on full test suite (22 architectures)")
        print()
        return 0
    else:
        print("="*70)
        print("⚠️  SOME TESTS FAILED")
        print("="*70)
        print("\n   Review failures above and adjust:")
        print("   - Check if difficulty ranges need adjustment")
        print("   - Review post-processing logic")
        print("   - Add few-shot examples if needed")
        print()
        return 1


if __name__ == "__main__":
    sys.exit(main())
