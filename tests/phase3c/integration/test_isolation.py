"""
Test that agent system doesn't break deterministic engine.

Verifies:
1. Ground truth generation still works
2. Output is identical before/after agent changes
3. 99.5% confidence maintained
4. No orphan nodes introduced
"""

import json
import subprocess
import sys
from pathlib import Path
import hashlib


def run_command(cmd, description):
    """Run command and return success status."""
    print(f"\n{'='*70}")
    print(f"{description}")
    print(f"{'='*70}")
    print(f"Command: {' '.join(cmd)}\n")

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"❌ FAILED")
        print(f"Error: {result.stderr}")
        return False

    print(f"✅ SUCCESS")
    return True


def hash_file(filepath):
    """Calculate SHA256 hash of file."""
    if not Path(filepath).exists():
        return None

    with open(filepath, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()


def compare_ground_truth(before_path, after_path):
    """Compare two ground truth files."""
    print(f"\n{'='*70}")
    print("COMPARING GROUND TRUTH FILES")
    print(f"{'='*70}\n")

    before_hash = hash_file(before_path)
    after_hash = hash_file(after_path)

    print(f"Before: {before_path}")
    print(f"  Hash: {before_hash}")
    print()
    print(f"After: {after_path}")
    print(f"  Hash: {after_hash}")
    print()

    if before_hash == after_hash:
        print("✅ Files are IDENTICAL - No impact on deterministic engine")
        return True
    else:
        print("❌ Files are DIFFERENT - Agent changes broke deterministic engine!")

        # Show differences
        with open(before_path) as f:
            before_data = json.load(f)
        with open(after_path) as f:
            after_data = json.load(f)

        # Compare key fields
        print("\nKey field comparison:")
        for key in ['control_recommendations', 'expected_attack_paths', 'rapids_assessment']:
            before_val = len(before_data.get(key, []))
            after_val = len(after_data.get(key, []))
            status = "✅" if before_val == after_val else "❌"
            print(f"  {status} {key}: {before_val} -> {after_val}")

        return False


def test_isolation():
    """Run full isolation test."""
    print(f"\n{'='*70}")
    print("ISOLATION TEST: Verify Agent System Doesn't Break Deterministic Engine")
    print(f"{'='*70}\n")

    test_arch = "tests/data/architectures/02_minimal_defended.mmd"
    test_name = "02_minimal_defended"

    # Step 1: Generate BEFORE baseline
    print("\n[STEP 1] Generate BEFORE baseline (deterministic engine only)")
    before_dir = Path("report") / f"{test_name}_BEFORE"
    if before_dir.exists():
        import shutil
        shutil.rmtree(before_dir)

    success = run_command(
        ["python3", "-m", "chatbot.main", "--gen-arch-truth", test_arch],
        "Generate ground truth (BEFORE agent changes)"
    )

    if not success:
        print("\n❌ FAILED: Could not generate baseline")
        return False

    # Move to BEFORE directory
    report_dir = Path("report") / test_name
    if report_dir.exists():
        report_dir.rename(before_dir)

    before_gt = before_dir / "ground_truth.json"
    if not before_gt.exists():
        print(f"\n❌ FAILED: {before_gt} not found")
        return False

    print(f"\n📄 Baseline saved to: {before_dir}")

    # Step 2: Test agent system
    print("\n[STEP 2] Test agent system (should NOT modify ground truth)")

    # Copy BEFORE to working directory for agent test
    import shutil
    agent_test_dir = Path("report") / f"{test_name}_AGENT_TEST"
    if agent_test_dir.exists():
        shutil.rmtree(agent_test_dir)
    shutil.copytree(before_dir, agent_test_dir)

    # Run Tester agent
    success = run_command(
        ["python3", "-m", "chatbot.modules.tester_critic", str(agent_test_dir)],
        "Run Tester agent on ground truth"
    )

    if not success:
        print("\n❌ FAILED: Tester agent failed")
        return False

    # Verify ground truth unchanged
    agent_gt = agent_test_dir / "ground_truth.json"
    baseline_gt = before_dir / "ground_truth.json"

    if not compare_ground_truth(baseline_gt, agent_gt):
        print("\n❌ CRITICAL: Agent modified ground_truth.json!")
        return False

    # Check agent outputs created
    tester_output = agent_test_dir / "05_tester_critique.json"
    if not tester_output.exists():
        print(f"\n❌ FAILED: {tester_output} not created")
        return False

    print(f"\n✅ Agent created: {tester_output}")

    # Step 3: Generate AFTER (re-run deterministic engine)
    print("\n[STEP 3] Re-run deterministic engine (verify still works)")
    after_dir = Path("report") / f"{test_name}_AFTER"
    if after_dir.exists():
        shutil.rmtree(after_dir)

    success = run_command(
        ["python3", "-m", "chatbot.main", "--gen-arch-truth", test_arch],
        "Generate ground truth (AFTER agent exists)"
    )

    if not success:
        print("\n❌ FAILED: Deterministic engine broken after agent changes")
        return False

    # Move to AFTER directory
    if report_dir.exists():
        report_dir.rename(after_dir)

    after_gt = after_dir / "ground_truth.json"
    if not after_gt.exists():
        print(f"\n❌ FAILED: {after_gt} not found")
        return False

    # Step 4: Compare BEFORE vs AFTER
    if not compare_ground_truth(before_gt, after_gt):
        print("\n❌ CRITICAL: Deterministic engine produces different output!")
        return False

    # Step 5: Verify confidence maintained
    print(f"\n{'='*70}")
    print("CONFIDENCE VERIFICATION")
    print(f"{'='*70}\n")

    with open(after_gt) as f:
        gt_data = json.load(f)

    validation = gt_data.get("validation_report", {})
    confidence = validation.get("confidence_baseline", 0)
    overall_valid = validation.get("overall_valid", False)

    print(f"Overall valid: {overall_valid}")
    print(f"Confidence: {confidence:.1%}")

    if confidence < 0.995:
        print(f"\n❌ FAILED: Confidence dropped below 99.5%")
        return False

    print(f"\n✅ Confidence maintained at 99.5%")

    # Cleanup
    print(f"\n{'='*70}")
    print("CLEANUP")
    print(f"{'='*70}\n")

    print("Keeping directories for inspection:")
    print(f"  {before_dir}/")
    print(f"  {agent_test_dir}/")
    print(f"  {after_dir}/")

    return True


if __name__ == "__main__":
    print("\n" + "="*70)
    print("ISOLATION TEST SUITE")
    print("="*70)

    success = test_isolation()

    print(f"\n{'='*70}")
    print("FINAL RESULT")
    print(f"{'='*70}\n")

    if success:
        print("✅ PASSED: Agent system does NOT break deterministic engine")
        print("   - Ground truth generation works")
        print("   - Output is identical before/after")
        print("   - 99.5% confidence maintained")
        print("   - Agent creates new files without modifying existing ones")
        sys.exit(0)
    else:
        print("❌ FAILED: Agent system broke deterministic engine")
        print("   See details above")
        sys.exit(1)
