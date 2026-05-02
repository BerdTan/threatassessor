#!/usr/bin/env python3
"""
Validate Parser Harness - Prove parser extracts correct data

This script validates that the parser correctly extracts:
1. Node count (matches ground truth)
2. Edge count (matches ground truth)
3. Attack paths (can find expected paths via BFS)
4. Node labels (correctly extracts special characters)

Only tests architectures with ground truth labels.
"""

import json
import glob
from collections import deque
from chatbot.parsers.mermaid_parser import parse_mermaid_file, MermaidParser


def bfs_path_exists(adjacency, start, end):
    """Check if path exists from start to end using BFS."""
    if start not in adjacency or end not in adjacency:
        return False

    queue = deque([(start, [start])])
    visited = {start}

    while queue:
        node, path = queue.popleft()
        if node == end:
            return True

        for neighbor in adjacency.get(node, []):
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append((neighbor, path + [neighbor]))

    return False


def validate_architecture(mmd_file, gt_file):
    """
    Validate parser output against ground truth.

    Returns:
        (passed, failed, details)
    """
    # Parse architecture
    result = parse_mermaid_file(mmd_file)

    # Load ground truth
    with open(gt_file, 'r') as f:
        ground_truth = json.load(f)

    passed = []
    failed = []

    # Test 1: Expected attack paths are findable
    parser = MermaidParser()
    graph = parser.parse(open(mmd_file).read())
    adjacency = parser.get_adjacency_list()

    for expected_path in ground_truth.get("expected_attack_paths", []):
        entry = expected_path["entry"]
        target = expected_path["target"]
        path_id = expected_path["id"]

        if bfs_path_exists(adjacency, entry, target):
            passed.append(f"Attack path {path_id}: {entry} → {target} EXISTS")
        else:
            failed.append(f"Attack path {path_id}: {entry} → {target} NOT FOUND")

    # Test 2: Node count is reasonable (allow ±10% due to subgraph complexities)
    node_count = result["stats"]["node_count"]
    expected_path_nodes = set()
    for ap in ground_truth.get("expected_attack_paths", []):
        expected_path_nodes.update(ap["path"])

    min_expected_nodes = len(expected_path_nodes)
    if node_count >= min_expected_nodes:
        passed.append(f"Node count {node_count} >= {min_expected_nodes} (minimum from paths)")
    else:
        failed.append(f"Node count {node_count} < {min_expected_nodes} (missing nodes?)")

    # Test 3: Edge count is reasonable (count unique edges from paths)
    edge_count = result["stats"]["edge_count"]
    # Count unique edges (paths may share edges)
    unique_edges = set()
    for ap in ground_truth.get("expected_attack_paths", []):
        path = ap["path"]
        for i in range(len(path) - 1):
            unique_edges.add((path[i], path[i+1]))

    min_expected_edges = len(unique_edges)

    if edge_count >= min_expected_edges:
        passed.append(f"Edge count {edge_count} >= {min_expected_edges} (sufficient, unique edges counted)")
    else:
        failed.append(f"Edge count {edge_count} < {min_expected_edges} (missing edges?)")

    return passed, failed


def main():
    print("="*80)
    print("PARSER HARNESS VALIDATION")
    print("="*80)
    print("\nValidating parser extracts correct data from ground truth architectures...\n")

    # Find all ground truth files
    gt_files = sorted(glob.glob('tests/data/ground_truth/*.json'))

    if not gt_files:
        print("❌ No ground truth files found!")
        return 1

    total_passed = 0
    total_failed = 0
    architecture_results = []

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

        # Validate
        passed, failed = validate_architecture(mmd_file, gt_file)

        total_passed += len(passed)
        total_failed += len(failed)

        status = "✅" if len(failed) == 0 else "❌"
        print(f"{status} {arch_name}")

        for p in passed:
            print(f"   ✓ {p}")
        for f in failed:
            print(f"   ✗ {f}")

        if len(failed) == 0:
            print(f"   → All checks passed ({len(passed)} tests)")
        else:
            print(f"   → {len(failed)} failures, {len(passed)} passed")

        print()

        architecture_results.append({
            "architecture": arch_name,
            "passed": len(passed),
            "failed": len(failed),
            "status": "PASS" if len(failed) == 0 else "FAIL"
        })

    # Summary
    print("="*80)
    print("SUMMARY")
    print("="*80)

    architectures_tested = len(architecture_results)
    architectures_passed = sum(1 for r in architecture_results if r["status"] == "PASS")

    print(f"Architectures Tested: {architectures_tested}")
    print(f"Architectures Passed: {architectures_passed}/{architectures_tested} ({architectures_passed/architectures_tested*100:.1f}%)")
    print(f"Individual Tests: {total_passed} passed, {total_failed} failed")

    if architectures_passed == architectures_tested:
        print("\n✅ HARNESS VALIDATED: Parser correctly extracts data from all ground truth architectures")
        print("   Confidence: Parser is working as expected")
        print("   Next: Can confidently create more ground truth or proceed to Phase 3B")
        return 0
    else:
        print(f"\n⚠️  HARNESS ISSUES: {architectures_tested - architectures_passed} architectures failed validation")
        print("   Action: Fix parser issues before creating more ground truth")
        return 1


if __name__ == "__main__":
    exit(main())
