#!/usr/bin/env python3
"""
Test Control Detection Against Ground Truth

Validates control detection accuracy using ground truth labels.
Tests precision, recall, and coverage metrics.
"""

import json
import glob
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from chatbot.parsers.mermaid_parser import parse_mermaid_file
from tests.data.architectures.control_detection import (
    detect_controls_in_architecture,
    identify_missing_controls,
    calculate_control_coverage,
)


def load_ground_truth(gt_file: str) -> dict:
    """Load ground truth JSON."""
    with open(gt_file, 'r') as f:
        return json.load(f)


def calculate_precision_recall(detected: set, expected: set) -> tuple:
    """
    Calculate precision and recall.

    Precision: Of detected controls, how many are correct?
    Recall: Of expected controls, how many were detected?

    Special cases:
    - Both empty: Perfect match (P=1.0, R=1.0)
    - Expected empty, detected non-empty: False positives (P=0.0, R=1.0)
    - Detected empty, expected non-empty: Missed all (P=1.0, R=0.0)
    """
    # Special case: both empty = perfect match
    if not detected and not expected:
        return 1.0, 1.0

    # Detected empty but expected non-empty = missed all
    if not detected and expected:
        return 1.0, 0.0

    # Expected empty but detected non-empty = false positives
    if detected and not expected:
        return 0.0, 1.0

    true_positives = detected & expected
    precision = len(true_positives) / len(detected)
    recall = len(true_positives) / len(expected)

    return precision, recall


def calculate_f1(precision: float, recall: float) -> float:
    """Calculate F1 score (harmonic mean of precision and recall)."""
    if precision + recall == 0:
        return 0.0
    return 2 * (precision * recall) / (precision + recall)


def test_control_detection(mmd_file: str, gt_file: str) -> dict:
    """
    Test control detection against ground truth.

    Returns:
        dict: Test results with precision, recall, F1
    """
    # Parse architecture
    parsed = parse_mermaid_file(mmd_file)

    # Convert nodes dict to list format
    nodes = [
        {"id": node_id, "label": node_data.get("label", node_id)}
        for node_id, node_data in parsed["nodes"].items()
    ]

    # Edges are already in list format, just ensure label field exists
    edges = [
        {
            "source": edge["source"],
            "target": edge["target"],
            "label": edge.get("label") or ""
        }
        for edge in parsed["edges"]
    ]

    # Extract subgraphs for segmentation detection
    subgraphs = [
        {"id": sg_id, "label": sg_data.get("label", sg_id)}
        for sg_id, sg_data in parsed.get("subgraphs", {}).items()
    ]

    # Detect controls
    detection_result = detect_controls_in_architecture(nodes, edges, subgraphs)
    detected_controls = set(detection_result["controls_present"])

    # Load ground truth
    ground_truth = load_ground_truth(gt_file)
    expected_present = set(ground_truth.get("controls_present", []))
    expected_missing = set(ground_truth.get("controls_missing", []))

    # Calculate metrics for controls present
    precision_present, recall_present = calculate_precision_recall(
        detected_controls, expected_present
    )
    f1_present = calculate_f1(precision_present, recall_present)

    # Check for false positives (detected but should be missing)
    false_positives = detected_controls & expected_missing

    # Check for false negatives (expected but not detected)
    false_negatives = expected_present - detected_controls

    return {
        "detected": sorted(detected_controls),
        "expected_present": sorted(expected_present),
        "expected_missing": sorted(expected_missing),
        "true_positives": sorted(detected_controls & expected_present),
        "false_positives": sorted(false_positives),
        "false_negatives": sorted(false_negatives),
        "precision": precision_present,
        "recall": recall_present,
        "f1": f1_present,
        "evidence": detection_result["control_evidence"],
    }


def main():
    print("="*80)
    print("CONTROL DETECTION VALIDATION")
    print("="*80)
    print("\nValidating control detection against ground truth labels...\n")

    # Find all ground truth files
    gt_files = sorted(glob.glob('tests/data/ground_truth/*.json'))

    if not gt_files:
        print("❌ No ground truth files found!")
        return 1

    results = []
    total_precision = 0.0
    total_recall = 0.0
    total_f1 = 0.0

    for gt_file in gt_files:
        # Get corresponding architecture file
        arch_num = gt_file.split('/')[-1].split('_')[0]
        mmd_file = f'tests/data/architectures/{arch_num}_*.mmd'
        mmd_files = glob.glob(mmd_file)

        if not mmd_files:
            print(f"⚠️  No .mmd file found for {gt_file}")
            continue

        mmd_file = mmd_files[0]
        arch_name = mmd_file.split('/')[-1].replace('.mmd', '')

        # Test control detection
        result = test_control_detection(mmd_file, gt_file)

        # Status indicator
        if result["f1"] >= 0.80:
            status = "✅"
        elif result["f1"] >= 0.60:
            status = "⚠️"
        else:
            status = "❌"

        print(f"{status} {arch_name}")
        print(f"   Precision: {result['precision']:.1%}  Recall: {result['recall']:.1%}  F1: {result['f1']:.1%}")

        if result["true_positives"]:
            print(f"   ✓ Correctly detected: {', '.join(result['true_positives'][:5])}")
            if len(result['true_positives']) > 5:
                print(f"     ... and {len(result['true_positives']) - 5} more")

        if result["false_positives"]:
            print(f"   ✗ False positives: {', '.join(result['false_positives'])}")

        if result["false_negatives"]:
            print(f"   ✗ Missed controls: {', '.join(result['false_negatives'][:3])}")
            if len(result['false_negatives']) > 3:
                print(f"     ... and {len(result['false_negatives']) - 3} more")

        print()

        total_precision += result["precision"]
        total_recall += result["recall"]
        total_f1 += result["f1"]
        results.append({
            "architecture": arch_name,
            "f1": result["f1"],
            "precision": result["precision"],
            "recall": result["recall"],
        })

    # Summary
    print("="*80)
    print("SUMMARY")
    print("="*80)

    architectures_tested = len(results)
    avg_precision = total_precision / architectures_tested if architectures_tested > 0 else 0.0
    avg_recall = total_recall / architectures_tested if architectures_tested > 0 else 0.0
    avg_f1 = total_f1 / architectures_tested if architectures_tested > 0 else 0.0

    print(f"Architectures Tested: {architectures_tested}")
    print(f"Average Precision: {avg_precision:.1%}")
    print(f"Average Recall: {avg_recall:.1%}")
    print(f"Average F1 Score: {avg_f1:.1%}")

    # Performance rating
    if avg_f1 >= 0.80:
        rating = "EXCELLENT"
        emoji = "✅"
    elif avg_f1 >= 0.60:
        rating = "GOOD"
        emoji = "⚠️"
    else:
        rating = "NEEDS IMPROVEMENT"
        emoji = "❌"

    print(f"\n{emoji} Control Detection Performance: {rating}")

    if avg_f1 >= 0.70:
        print("   Confidence: Control detection is working as expected")
        print("   Next: Can proceed to Phase 3C (Risk Scoring Validation)")
        return 0
    else:
        print(f"   Action: Improve keyword matching or expand CONTROL_KEYWORDS")
        print(f"   Target: F1 >= 0.70 for production readiness")
        return 1


if __name__ == "__main__":
    exit(main())
