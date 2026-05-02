#!/usr/bin/env python3
"""
Engine Accuracy Validator

Validates the threat modeling engine against human-labeled ground truths.
Measures:
- Control detection precision/recall/F1
- Attack path accuracy
- Risk score correlation

This demonstrates that our validated engine is more robust than blind LLM usage.
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple

# Add project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from chatbot.modules.ground_truth_generator import generate_ground_truth


def load_ground_truth(file_path: str) -> Dict:
    """Load ground truth JSON."""
    with open(file_path, 'r') as f:
        return json.load(f)


def calculate_precision_recall_f1(
    predicted: Set[str],
    actual: Set[str]
) -> Tuple[float, float, float]:
    """
    Calculate precision, recall, and F1 score.

    Precision = TP / (TP + FP)
    Recall = TP / (TP + FN)
    F1 = 2 * (Precision * Recall) / (Precision + Recall)
    """
    if not predicted and not actual:
        return (1.0, 1.0, 1.0)  # Perfect match if both empty

    if not predicted:
        return (0.0, 0.0, 0.0)  # No predictions

    if not actual:
        return (0.0, 0.0, 0.0)  # No ground truth

    true_positives = len(predicted & actual)
    false_positives = len(predicted - actual)
    false_negatives = len(actual - predicted)

    precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) > 0 else 0.0
    recall = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) > 0 else 0.0
    f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

    return (precision, recall, f1)


def validate_control_detection(generated: Dict, ground_truth: Dict) -> Dict:
    """Validate control detection accuracy."""
    gen_controls = set(generated["controls_present"])
    gt_controls = set(ground_truth["controls_present"])

    precision, recall, f1 = calculate_precision_recall_f1(gen_controls, gt_controls)

    false_positives = list(gen_controls - gt_controls)
    false_negatives = list(gt_controls - gen_controls)

    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "false_positives": false_positives,
        "false_negatives": false_negatives,
        "generated_count": len(gen_controls),
        "ground_truth_count": len(gt_controls)
    }


def validate_risk_scores(generated: Dict, ground_truth: Dict) -> Dict:
    """Validate risk score correlation."""
    gen_risk = generated["expected_risk_score"]
    gt_risk = ground_truth["expected_risk_score"]

    gen_def = generated["expected_defensibility"]
    gt_def = ground_truth["expected_defensibility"]

    # Allow ±20 point tolerance (scoring is heuristic-based)
    risk_diff = abs(gen_risk - gt_risk)
    def_diff = abs(gen_def - gt_def)

    risk_match = risk_diff <= 20
    def_match = def_diff <= 20

    return {
        "risk_score_diff": risk_diff,
        "defensibility_diff": def_diff,
        "risk_within_tolerance": risk_match,
        "defensibility_within_tolerance": def_match,
        "generated_risk": gen_risk,
        "ground_truth_risk": gt_risk,
        "generated_defensibility": gen_def,
        "ground_truth_defensibility": gt_def
    }


def validate_single_architecture(mmd_file: str, ground_truth_file: str) -> Dict:
    """Validate engine against single architecture."""
    print(f"\n{'='*80}")
    print(f"Validating: {Path(mmd_file).name}")
    print(f"{'='*80}")

    # Generate with engine
    generated = generate_ground_truth(mmd_file, use_llm=False)

    # Load ground truth
    ground_truth = load_ground_truth(ground_truth_file)

    # Validate controls
    control_metrics = validate_control_detection(generated, ground_truth)

    # Validate scores
    score_metrics = validate_risk_scores(generated, ground_truth)

    # Display results
    print(f"\n📊 CONTROL DETECTION:")
    print(f"   Precision: {control_metrics['precision']:.2%}")
    print(f"   Recall:    {control_metrics['recall']:.2%}")
    print(f"   F1 Score:  {control_metrics['f1']:.2%}")
    print(f"   Generated: {control_metrics['generated_count']}, Ground Truth: {control_metrics['ground_truth_count']}")

    if control_metrics['false_positives']:
        print(f"   False Positives: {', '.join(control_metrics['false_positives'])}")
    if control_metrics['false_negatives']:
        print(f"   False Negatives: {', '.join(control_metrics['false_negatives'])}")

    print(f"\n🎯 RISK SCORING:")
    print(f"   Risk Score:     {generated['expected_risk_score']:3d} vs {ground_truth['expected_risk_score']:3d} (diff: {score_metrics['risk_score_diff']:2d}) {'✓' if score_metrics['risk_within_tolerance'] else '✗'}")
    print(f"   Defensibility:  {generated['expected_defensibility']:3d} vs {ground_truth['expected_defensibility']:3d} (diff: {score_metrics['defensibility_diff']:2d}) {'✓' if score_metrics['defensibility_within_tolerance'] else '✗'}")

    print(f"\n🔗 ATTACK PATHS:")
    print(f"   Generated: {len(generated['expected_attack_paths'])}")
    print(f"   Ground Truth: {len(ground_truth['expected_attack_paths'])}")

    return {
        "architecture": Path(mmd_file).name,
        "control_metrics": control_metrics,
        "score_metrics": score_metrics,
        "attack_path_count_gen": len(generated["expected_attack_paths"]),
        "attack_path_count_gt": len(ground_truth["expected_attack_paths"])
    }


def main():
    """Run validation on all available ground truths."""
    ground_truth_dir = Path("tests/data/ground_truth")
    architectures_dir = Path("tests/data/architectures")

    # Find all ground truths with corresponding .mmd files
    test_pairs = []
    for gt_file in ground_truth_dir.glob("*.json"):
        mmd_file = architectures_dir / f"{gt_file.stem}.mmd"
        if mmd_file.exists():
            test_pairs.append((str(mmd_file), str(gt_file)))

    if not test_pairs:
        print("❌ No test pairs found (ground truth + .mmd)")
        return 1

    print(f"\n{'='*80}")
    print(f"ENGINE ACCURACY VALIDATION")
    print(f"{'='*80}")
    print(f"Found {len(test_pairs)} test cases\n")

    results = []
    for mmd_file, gt_file in test_pairs:
        result = validate_single_architecture(mmd_file, gt_file)
        results.append(result)

    # Aggregate metrics
    print(f"\n{'='*80}")
    print(f"AGGREGATE RESULTS")
    print(f"{'='*80}\n")

    avg_precision = sum(r["control_metrics"]["precision"] for r in results) / len(results)
    avg_recall = sum(r["control_metrics"]["recall"] for r in results) / len(results)
    avg_f1 = sum(r["control_metrics"]["f1"] for r in results) / len(results)

    risk_within_tolerance_count = sum(1 for r in results if r["score_metrics"]["risk_within_tolerance"])
    def_within_tolerance_count = sum(1 for r in results if r["score_metrics"]["defensibility_within_tolerance"])

    print(f"📊 CONTROL DETECTION (across {len(results)} architectures):")
    print(f"   Average Precision: {avg_precision:.2%}")
    print(f"   Average Recall:    {avg_recall:.2%}")
    print(f"   Average F1 Score:  {avg_f1:.2%}")

    print(f"\n🎯 RISK SCORING:")
    print(f"   Risk scores within ±20:        {risk_within_tolerance_count}/{len(results)} ({risk_within_tolerance_count/len(results):.0%})")
    print(f"   Defensibility within ±20:      {def_within_tolerance_count}/{len(results)} ({def_within_tolerance_count/len(results):.0%})")

    print(f"\n🔗 ATTACK PATHS:")
    total_gen = sum(r["attack_path_count_gen"] for r in results)
    total_gt = sum(r["attack_path_count_gt"] for r in results)
    print(f"   Total generated: {total_gen}")
    print(f"   Total ground truth: {total_gt}")
    print(f"   Average per architecture: {total_gen/len(results):.1f} generated vs {total_gt/len(results):.1f} ground truth")

    # Pass/fail criteria
    print(f"\n{'='*80}")
    print(f"VALIDATION RESULT")
    print(f"{'='*80}")

    passing = (
        avg_f1 >= 0.60 and  # F1 should be at least 60%
        risk_within_tolerance_count / len(results) >= 0.70  # 70% risk scores within tolerance
    )

    if passing:
        print(f"✅ PASS - Engine meets accuracy thresholds")
        print(f"   ✓ F1 score: {avg_f1:.2%} (target: ≥60%)")
        print(f"   ✓ Risk accuracy: {risk_within_tolerance_count/len(results):.0%} (target: ≥70%)")
        return 0
    else:
        print(f"❌ FAIL - Engine needs improvement")
        if avg_f1 < 0.60:
            print(f"   ✗ F1 score: {avg_f1:.2%} (target: ≥60%)")
        if risk_within_tolerance_count / len(results) < 0.70:
            print(f"   ✗ Risk accuracy: {risk_within_tolerance_count/len(results):.0%} (target: ≥70%)")
        return 1


if __name__ == "__main__":
    sys.exit(main())
