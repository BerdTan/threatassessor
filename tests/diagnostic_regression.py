"""
Regression Diagnostic for Stage 1 & 2A Changes

Tests:
1. Deterministic engine integrity
2. Node-level technique mapping
3. Attack path generation
4. Validation completeness
5. Confidence calculation
6. Service layer integration

Run: python3 tests/diagnostic_regression.py
"""

import json
import sys
from pathlib import Path

print("=" * 80)
print("REGRESSION DIAGNOSTIC - Stage 1 & 2A Changes")
print("=" * 80)

# Test 1: Direct ground truth generation
print("\n[TEST 1] Direct Ground Truth Generation")
print("-" * 80)

try:
    from chatbot.modules import ground_truth_generator

    test_arch = "tests/data/architectures/03_aws_3tier.mmd"
    print(f"Generating ground truth for: {test_arch}")

    ground_truth = ground_truth_generator.generate_ground_truth(test_arch)

    print(f"✓ Generation successful")
    print(f"  Type: {type(ground_truth)}")
    print(f"  Keys: {len(ground_truth.keys()) if isinstance(ground_truth, dict) else 'N/A'}")

    if isinstance(ground_truth, dict):
        print(f"\n  Top-level keys:")
        for key in sorted(ground_truth.keys())[:10]:
            val = ground_truth[key]
            if isinstance(val, (list, dict)):
                print(f"    - {key}: {type(val).__name__} (len={len(val)})")
            else:
                print(f"    - {key}: {type(val).__name__}")

        # Check critical fields
        attack_paths = ground_truth.get('expected_attack_paths', [])
        print(f"\n  Attack paths: {len(attack_paths)}")
        if attack_paths:
            path = attack_paths[0]
            path_nodes = path.get('path', [])  # Correct field: 'path' not 'steps'
            print(f"    Path #1: {len(path_nodes)} nodes ({path.get('hop_count', 0)} hops)")
            if path_nodes:
                print(f"      Path: {' → '.join(path_nodes)}")
                per_node = path.get('per_node_techniques', {})
                if per_node:
                    print(f"      Per-node techniques: {len(per_node)} nodes mapped")

        # Check node mapping
        metadata = ground_truth.get('metadata', {})
        parsed_nodes = metadata.get('parsed_nodes', {})
        print(f"\n  Parsed nodes: {len(parsed_nodes)}")
        for node_id in list(parsed_nodes.keys())[:5]:
            print(f"    - {node_id}")

        TEST1_PASS = len(attack_paths) > 0 and len(path_nodes) >= 3  # Should have 3+ nodes in path
        if TEST1_PASS:
            print("\n✅ TEST 1 PASSED: Ground truth generation intact")
        else:
            print("\n❌ TEST 1 FAILED: Attack paths or steps empty")
    else:
        print(f"❌ TEST 1 FAILED: Expected dict, got {type(ground_truth)}")
        TEST1_PASS = False

except Exception as e:
    print(f"❌ TEST 1 FAILED: {e}")
    import traceback
    traceback.print_exc()
    TEST1_PASS = False


# Test 2: ThreatAnalyst wrapper
print("\n[TEST 2] ThreatAnalyst Service Wrapper")
print("-" * 80)

try:
    from chatbot.modules.agents.analysts.threat_analyst import ThreatAnalyst

    analyst = ThreatAnalyst()
    print("✓ ThreatAnalyst initialized")

    context = {
        "architecture_path": "tests/data/architectures/03_aws_3tier.mmd"
    }

    result = analyst.execute(context)
    print(f"✓ Analysis complete")
    print(f"  Type: {type(result)}")
    print(f"  Confidence: {result.confidence}")
    print(f"  Attack paths: {len(result.attack_paths)}")
    print(f"  Techniques: {len(result.techniques)}")

    TEST2_PASS = result.confidence > 0.9 and len(result.attack_paths) > 0
    if TEST2_PASS:
        print("\n✅ TEST 2 PASSED: ThreatAnalyst wrapper intact")
    else:
        print(f"\n❌ TEST 2 FAILED: Confidence={result.confidence}, paths={len(result.attack_paths)}")

except Exception as e:
    print(f"❌ TEST 2 FAILED: {e}")
    import traceback
    traceback.print_exc()
    TEST2_PASS = False


# Test 3: Validation completeness
print("\n[TEST 3] Completeness Validator")
print("-" * 80)

try:
    from chatbot.modules.completeness_validator import validate_completeness

    # Load existing ground truth (already generated in TEST 1)
    import json
    with open("report/03_aws_3tier/ground_truth.json") as f:
        ground_truth = json.load(f)

    result = validate_completeness(ground_truth)  # Pass dict, not string
    print(f"✓ Validation complete")
    print(f"  Type: {type(result)}")

    if isinstance(result, dict):
        # confidence_adjustment is 0.0-1.0 scale (100% = 1.0)
        adjustment = result.get('confidence_adjustment', 0)
        print(f"  Confidence adjustment: {adjustment * 100:.1f}%")
        print(f"  Issues: {result.get('total_issues', 'N/A')}")
        print(f"  Validation passed: {result.get('validation_passed', False)}")

        TEST3_PASS = adjustment >= 0.90  # 90% or higher (0.90 on 0-1 scale)
        if TEST3_PASS:
            print("\n✅ TEST 3 PASSED: Validator intact")
        else:
            print(f"\n❌ TEST 3 FAILED: Low confidence {result.get('confidence_adjustment')}%")
    else:
        print(f"❌ TEST 3 FAILED: Expected dict, got {type(result)}")
        TEST3_PASS = False

except Exception as e:
    print(f"❌ TEST 3 FAILED: {e}")
    import traceback
    traceback.print_exc()
    TEST3_PASS = False


# Test 4: Service layer
print("\n[TEST 4] Service Layer Integration")
print("-" * 80)

try:
    from chatbot.services import ThreatAnalysisService

    service = ThreatAnalysisService()
    print("✓ Service initialized")

    result = service.safe_execute(
        architecture_path="tests/data/architectures/03_aws_3tier.mmd",
        include_validation=False  # Skip validation for now
    )

    print(f"✓ Service execution complete")
    print(f"  Success: {result.success}")
    print(f"  Request ID: {result.request_id}")

    if result.success:
        data = result.data
        analysis = data.get('analysis', {})
        attack_paths = analysis.get('attack_paths', [])
        print(f"  Attack paths: {len(attack_paths)}")
        print(f"  Confidence: {data.get('confidence', 'N/A')}")

        TEST4_PASS = len(attack_paths) > 0
        if TEST4_PASS:
            print("\n✅ TEST 4 PASSED: Service layer intact")
        else:
            print("\n❌ TEST 4 FAILED: No attack paths in service result")
    else:
        print(f"❌ TEST 4 FAILED: Service error: {result.error}")
        TEST4_PASS = False

except Exception as e:
    print(f"❌ TEST 4 FAILED: {e}")
    import traceback
    traceback.print_exc()
    TEST4_PASS = False


# Test 5: Node-level technique mapping
print("\n[TEST 5] Node-Level Technique Mapping")
print("-" * 80)

try:
    # Load fresh ground truth
    gt_path = Path("report/03_aws_3tier/ground_truth.json")

    if gt_path.exists():
        with open(gt_path) as f:
            gt = json.load(f)

        # Check if techniques mapped to nodes in attack paths
        attack_paths = gt.get('expected_attack_paths', [])

        if attack_paths:
            path = attack_paths[0]
            path_nodes = path.get('path', [])  # Correct field
            per_node = path.get('per_node_techniques', {})

            print(f"✓ Attack path analysis:")
            print(f"  Path nodes: {len(path_nodes)}")
            print(f"  Nodes: {' → '.join(path_nodes)}")
            print(f"  Per-node techniques: {len(per_node)} nodes mapped")

            # Check if techniques mapped to nodes
            total_techniques = sum(len(techs) for techs in per_node.values())
            print(f"  Total techniques mapped: {total_techniques}")

            TEST5_PASS = len(per_node) >= 3 and total_techniques >= 6  # Should have 3+ nodes with 6+ techniques
            if TEST5_PASS:
                print("\n✅ TEST 5 PASSED: Nodes mapped in attack paths")
            else:
                print(f"\n❌ TEST 5 FAILED: Only {len(nodes_in_path)} nodes in paths")
        else:
            print("❌ TEST 5 FAILED: No attack paths found")
            TEST5_PASS = False
    else:
        print(f"❌ TEST 5 FAILED: Ground truth not found at {gt_path}")
        TEST5_PASS = False

except Exception as e:
    print(f"❌ TEST 5 FAILED: {e}")
    import traceback
    traceback.print_exc()
    TEST5_PASS = False


# Summary
print("\n" + "=" * 80)
print("DIAGNOSTIC SUMMARY")
print("=" * 80)

tests = {
    "Ground Truth Generation": TEST1_PASS,
    "ThreatAnalyst Wrapper": TEST2_PASS,
    "Completeness Validator": TEST3_PASS,
    "Service Layer": TEST4_PASS,
    "Node-Level Mapping": TEST5_PASS
}

passed = sum(1 for v in tests.values() if v)
total = len(tests)

for test_name, result in tests.items():
    status = "✅ PASS" if result else "❌ FAIL"
    print(f"  {status}: {test_name}")

print(f"\nOverall: {passed}/{total} tests passed ({passed/total*100:.0f}%)")

if passed == total:
    print("\n✅ ALL TESTS PASSED - No regressions detected")
    sys.exit(0)
else:
    print(f"\n❌ REGRESSIONS DETECTED - {total - passed} test(s) failed")
    print("\nRecommendation: Rollback to baseline-phase1-start tag")
    sys.exit(1)
