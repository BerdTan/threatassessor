#!/usr/bin/env python3
"""
arch_to_graph.py — Render a .mmd architecture diagram side-by-side with its
in-memory graph representation (adjacency list + hub scores).

Usage:
    python3 arch_to_graph.py <path-to-file.mmd>
    python3 arch_to_graph.py <path-to-file.mmd> --ground-truth report/<arch>/ground_truth.json

Output: a fenced code block ready to paste into a blog post or doc.
"""

import sys
import json
import argparse
from pathlib import Path
from collections import defaultdict, Counter

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

ENTRY_KW  = {"user","visitor","employee","client","browser","mobile","internet",
              "external","attacker","citizen","customer","frontend","public"}
TARGET_KW = {"database","db","storage","secret","vault","credential","cache",
              "queue","bucket","blob","datastore","registry","keystore","backup"}
INFRA_KW  = {"load balancer","loadbalancer","router","switch","firewall","nat",
              "cdn","gateway","balancer","proxy"}


def compute_degrees(edges):
    out_deg = Counter()
    in_deg  = Counter()
    for e in edges:
        out_deg[e["source"]] += 1
        in_deg[e["target"]]  += 1
    return in_deg, out_deg


def annotate(nid, label, out_deg, in_deg, hub_scores=None):
    l = label.lower()
    is_entry  = any(kw in l for kw in ENTRY_KW) and in_deg.get(nid, 0) == 0
    is_target = any(kw in l for kw in TARGET_KW)
    # gateway is infra unless "api" or "auth" is also in the label (application-layer signal)
    is_infra  = any(kw in l for kw in INFRA_KW) and not any(ak in l for ak in ("api", "auth", "app"))
    score     = hub_scores.get(nid, 0) if hub_scores else out_deg.get(nid, 0)

    if score == 0:
        marker = "← terminal"
    elif is_entry:
        marker = "← entry, not hub"
    elif is_target:
        marker = "← target"
    elif is_infra:
        marker = "← infra"
    elif score >= 3:
        marker = "← fan-out point"
    else:
        marker = ""
    return score, marker


def hub_scores_from_gt(gt_path):
    gt = json.loads(Path(gt_path).read_text())
    paths = gt.get("expected_attack_paths", [])
    succ = defaultdict(set)
    for p in paths:
        hops = p.get("path", [])
        for i in range(len(hops) - 1):
            succ[hops[i]].add(hops[i + 1])
    return {node: len(s) for node, s in succ.items()}


def mmd_display_lines(text, max_lines=20):
    """Return the most informative lines of the MMD source for the left column."""
    lines = [l for l in text.splitlines() if l.strip()]
    # Strip frontmatter
    if lines and lines[0].startswith("---"):
        end = next((i for i, l in enumerate(lines[1:], 1) if l.startswith("---")), None)
        if end:
            lines = lines[end + 1:]
    # Drop subgraph open/end lines to reduce noise; keep node+edge lines
    kept = []
    for l in lines:
        s = l.strip()
        if s.startswith("%%"):
            continue
        kept.append(l.rstrip())
        if len(kept) >= max_lines:
            kept.append("  ...")
            break
    return kept


def side_by_side(left_lines, right_lines, left_width=44):
    """Merge two lists of lines into a side-by-side string."""
    rows = max(len(left_lines), len(right_lines))
    out  = []
    for i in range(rows):
        l = left_lines[i]  if i < len(left_lines)  else ""
        r = right_lines[i] if i < len(right_lines) else ""
        out.append(f"{l:<{left_width}} {r}")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mmd", help="Path to .mmd file")
    ap.add_argument("--ground-truth", dest="gt", default=None,
                    help="Path to ground_truth.json for real attack-path hub scores")
    args = ap.parse_args()

    mmd_path = Path(args.mmd)
    if not mmd_path.exists():
        print(f"ERROR: {mmd_path} not found"); sys.exit(1)

    try:
        from chatbot.parsers.mermaid_parser import MermaidParser
    except ImportError as e:
        print(f"ERROR: Cannot import MermaidParser — run from project root: {e}"); sys.exit(1)

    text = mmd_path.read_text(encoding="utf-8")
    if text.startswith("---"):
        end = text.find("---", 3)
        if end > 0:
            text = text[end + 3:].lstrip()

    result = MermaidParser().parse(text)
    nodes, edges = result["nodes"], result["edges"]
    in_deg, out_deg = compute_degrees(edges)

    hub_sc = hub_scores_from_gt(args.gt) if args.gt else None
    score_label = "hub score (unique successors, from attack paths):" if args.gt \
                  else "hub score (out-degree, structural proxy):"

    # ── Adjacency list ───────────────────────────────────────────────────────
    adj = defaultdict(list)
    for e in edges:
        adj[e["source"]].append(e["target"])

    right = ["nodes:"]
    for nid, info in nodes.items():
        label   = info.get("label", nid)
        targets = adj.get(nid, [])
        tstr    = f"[{', '.join(targets)}]" if targets else "[]"
        score, marker = annotate(nid, label, out_deg, in_deg, hub_sc)
        suffix  = f"  {marker}" if marker else ""
        right.append(f"  {nid:<20} → {tstr}{suffix}")

    right.append("")
    right.append(score_label)
    for nid, info in nodes.items():
        label = info.get("label", nid)
        score, marker = annotate(nid, label, out_deg, in_deg, hub_sc)
        if score > 0 or marker:
            suffix = f"  {marker}" if marker else ""
            right.append(f"  {nid}: {score}{suffix}")

    # ── Left column: MMD source ──────────────────────────────────────────────
    left_header  = "Architecture diagram (.mmd)"
    right_header = "Graph in memory (adjacency list)"
    sep          = "─" * len(left_header)
    rsep         = "─" * len(right_header)

    left_lines  = [left_header, sep] + mmd_display_lines(mmd_path.read_text(encoding="utf-8"))
    right_lines = [right_header, rsep] + right

    LEFT_W = max(len(l) for l in left_lines) + 2

    print()
    print("```")
    print(side_by_side(left_lines, right_lines, LEFT_W))
    print("```")
    print()
    source = "attack-path data" if args.gt else "parsed edge out-degree (no ground_truth.json)"
    print(f"Hub scores from: {source}")
    print(f"Arch: {mmd_path.name}  |  {len(nodes)} nodes  |  {len(edges)} edges")


if __name__ == "__main__":
    main()
