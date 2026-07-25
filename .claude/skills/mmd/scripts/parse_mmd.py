#!/usr/bin/env python3
"""
parse_mmd.py — Dry-run the engine parser on a .mmd file and print structural summary.

Part of the /mmd skill. Use to confirm node/edge extraction before running the full engine.

Usage:
    python3 .claude/skills/mmd/scripts/parse_mmd.py <path-to-file.mmd>

Output:
    Nodes, edges, entry/target candidates, hub nodes (out_degree >= 3), subgraphs.
    Exit 0 = parsed OK.  Exit 1 = parse error or file not found.
"""

import sys
import json
from pathlib import Path
from collections import Counter

# Ensure project root is on path
ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))


def compute_degrees(edges):
    out_degree = Counter()
    in_degree = Counter()
    for e in edges:
        src = e.get("source", "")
        tgt = e.get("target", "")
        if src:
            out_degree[src] += 1
        if tgt:
            in_degree[tgt] += 1
    return in_degree, out_degree


ENTRY_KW = {
    "user", "visitor", "employee", "client", "browser", "mobile",
    "internet", "external", "attacker", "citizen", "customer",
    "frontend", "app", "webapp", "web app", "public",
}

TARGET_KW = {
    "database", "db", "storage", "secret", "vault", "credential",
    "cache", "queue", "bucket", "blob", "datastore", "data store",
    "registry", "keystore", "key store", "backup",
}

INFRA_KW = {
    "load balancer", "router", "switch", "firewall", "nat", "cdn",
    "gateway", "balancer", "proxy",
}


def classify_nodes(nodes, in_degree, out_degree):
    entries, targets, hubs, infra = [], [], [], []
    for nid, info in nodes.items():
        label = info.get("label", nid).lower()
        od = out_degree.get(nid, 0)
        id_ = in_degree.get(nid, 0)

        if any(kw in label for kw in ENTRY_KW) and id_ == 0:
            entries.append(nid)
        elif any(kw in label for kw in TARGET_KW):
            targets.append(nid)
        elif od >= 3 and not any(kw in label for kw in INFRA_KW):
            hubs.append((nid, od))
        elif any(kw in label for kw in INFRA_KW):
            infra.append(nid)

    return entries, targets, hubs, infra


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 parse_mmd.py <path-to-file.mmd>")
        sys.exit(1)

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"ERROR: File not found: {path}")
        sys.exit(1)

    try:
        from chatbot.parsers.mermaid_parser import MermaidParser
    except ImportError as e:
        print(f"ERROR: Cannot import MermaidParser — run from project root: {e}")
        sys.exit(1)

    text = path.read_text(encoding="utf-8")

    # Strip YAML frontmatter if present (engine expects raw MMD)
    if text.startswith("---"):
        end = text.find("---", 3)
        if end > 0:
            text = text[end + 3:].lstrip()
            print("WARNING: YAML frontmatter stripped — engine expects raw MMD (no --- block)")

    parser = MermaidParser()
    result = parser.parse(text)

    nodes = result["nodes"]
    edges = result["edges"]
    subgraphs = result["subgraphs"]
    stats = result["stats"]

    in_deg, out_deg = compute_degrees(edges)
    entries, targets, hubs, infra = classify_nodes(nodes, in_deg, out_deg)

    # ── Print summary ────────────────────────────────────────────────────────
    print(f"\n{'─'*60}")
    print(f"  {path.name}")
    print(f"{'─'*60}")
    print(f"Direction : {result.get('direction', 'unknown')}")
    print(f"Nodes     : {stats['node_count']}")
    print(f"Edges     : {stats['edge_count']}")
    print(f"Subgraphs : {stats['subgraph_count']}")

    # Node list
    print(f"\nAll nodes ({stats['node_count']}):")
    for nid, info in nodes.items():
        label = info.get("label", nid)
        shape = info.get("shape", "rect")
        sg = info.get("subgraph")
        od = out_deg.get(nid, 0)
        id_ = in_deg.get(nid, 0)
        sg_str = f"  [{sg}]" if sg else ""
        print(f"  {nid:<25} {label:<30} shape={shape} in={id_} out={od}{sg_str}")

    # Edge list
    print(f"\nEdges ({stats['edge_count']}):")
    for e in edges:
        lbl = f"  label={e['label']!r}" if e.get("label") else ""
        print(f"  {e['source']} → {e['target']}{lbl}")

    # Subgraphs
    if subgraphs:
        print(f"\nSubgraphs ({stats['subgraph_count']}):")
        for sg_id, sg_info in subgraphs.items():
            if isinstance(sg_info, dict):
                display = sg_info.get("display_name", sg_id)
                sg_nodes = sg_info.get("nodes", [])
            else:
                display = sg_id
                sg_nodes = sg_info
            print(f"  {sg_id} [{display}]  nodes: {sg_nodes}")

    # Structural signals
    print(f"\nEntry candidates    : {entries if entries else '(none detected)'}")
    print(f"Target candidates   : {targets if targets else '(none detected)'}")
    print(f"Hub nodes (out≥3)   : {[f'{n}(out={d})' for n,d in hubs] if hubs else '(none)'}")
    print(f"Infra nodes (skip)  : {infra if infra else '(none)'}")

    # Warnings
    all_edge_nodes = {e["source"] for e in edges} | {e["target"] for e in edges}
    orphans = [nid for nid in nodes if nid not in all_edge_nodes]
    if orphans:
        print(f"\nWARNING — orphan nodes (no edges): {orphans}")
    if not entries:
        print("\nWARNING — no entry points detected; check external-actor nodes have outbound edges")
    if not targets:
        print("\nWARNING — no sensitive targets detected; check DB/storage/cache nodes exist")

    print(f"{'─'*60}\n")


if __name__ == "__main__":
    main()
