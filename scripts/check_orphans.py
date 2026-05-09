#!/usr/bin/env python3
"""
Quick Orphan Detection Check

Checks existing ground truth files for orphan nodes without regenerating.

Usage:
    python3 scripts/check_orphans.py
    python3 scripts/check_orphans.py 10_complex_enterprise 03_aws_3tier
"""

import sys
import json
from pathlib import Path
from collections import defaultdict

def check_orphans(arch_name: str) -> dict:
    """Check if architecture has orphan nodes."""
    gt_path = f"report/{arch_name}/ground_truth.json"

    if not Path(gt_path).exists():
        return {"status": "no_report", "orphans": []}

    with open(gt_path) as f:
        gt = json.load(f)

    # Get graph data
    metadata = gt.get('metadata', {})
    nodes = metadata.get('parsed_nodes', {})
    edges = metadata.get('parsed_edges', [])

    if not nodes or not edges:
        return {"status": "no_graph_data", "orphans": []}

    # Get entry points from attack paths
    attack_paths = gt.get('expected_attack_paths', [])
    entry_points = set()
    for path in attack_paths:
        if path.get('entry'):
            entry_points.add(path['entry'])
        if path.get('path') and len(path['path']) > 0:
            entry_points.add(path['path'][0])

    # Build graph
    graph = defaultdict(list)
    has_outbound = set()
    for edge in edges:
        source = edge.get('source', '')
        target = edge.get('target', '')
        if source and target:
            graph[source].append(target)
            has_outbound.add(source)

    # BFS from entry points
    reachable = set()
    queue = list(entry_points)
    while queue:
        node = queue.pop(0)
        if node in reachable:
            continue
        reachable.add(node)
        queue.extend(graph.get(node, []))

    # Find orphans: nodes with outbound connections but unreachable
    orphans = []
    for node_id in has_outbound:
        if node_id not in reachable:
            outbound = graph[node_id]
            orphans.append({
                "node": node_id,
                "label": nodes.get(node_id, {}).get("label", node_id),
                "connects_to": outbound
            })

    return {
        "status": "ok",
        "orphans": orphans,
        "entry_points": list(entry_points),
        "total_nodes": len(nodes)
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Check architectures for orphan nodes")
    parser.add_argument("architectures", nargs="*", help="Specific architectures to check")
    args = parser.parse_args()

    # Find architectures
    if args.architectures:
        arch_names = args.architectures
    else:
        arch_dir = Path("tests/data/architectures")
        arch_names = [f.stem for f in sorted(arch_dir.glob("*.mmd"))]

    print(f"\n🔍 Checking {len(arch_names)} architectures for orphan nodes...\n")

    results = {}
    for arch_name in arch_names:
        results[arch_name] = check_orphans(arch_name)

    # Summary
    total = len(results)
    with_orphans = sum(1 for r in results.values() if r.get("orphans"))
    no_report = sum(1 for r in results.values() if r.get("status") == "no_report")

    print("="*80)
    print("ORPHAN DETECTION SUMMARY")
    print("="*80)
    print(f"\nTotal: {total} architectures")
    print(f"With orphans: {with_orphans}")
    print(f"No report: {no_report}")
    print()

    # Detailed results
    if with_orphans > 0:
        print("-"*80)
        print("ARCHITECTURES WITH ORPHANS")
        print("-"*80)

        for arch_name, result in results.items():
            orphans = result.get("orphans", [])
            if orphans:
                print(f"\n📍 {arch_name}")
                print(f"   Entry points: {', '.join(result.get('entry_points', []))}")
                for orphan in orphans:
                    connects = ', '.join(orphan['connects_to'][:3])
                    if len(orphan['connects_to']) > 3:
                        connects += f" +{len(orphan['connects_to']) - 3} more"
                    print(f"   ❌ {orphan['node']} ({orphan['label']}) → {connects}")
    else:
        print("✅ No orphans found in any architecture!")

    print("\n" + "="*80)

    # Recommendations
    if with_orphans > 0:
        print("\n💡 How to Fix Orphans:")
        print("\n1. Add entry point (recommended):")
        print("   VPN((VPN Remote Access))")
        print("   VPN --> OrphanNode")
        print("\n2. Connect to existing path:")
        print("   ExistingNode --> OrphanNode")
        print("\n3. Remove if out of scope:")
        print("   (Delete the orphan node from diagram)")
        print()


if __name__ == "__main__":
    main()
