#!/usr/bin/env python3
"""
validate_graphs.py — Lint .claude/graphs/*.mmd for known Mermaid rendering failures.

Part of the /codemap skill. Run after any graph edit.

Checks:
  1. Multi-line YAML frontmatter values (bad indentation → YAML parse error)
  2. graph TD/LR with subgraph IDs used directly in edges (needs flowchart mode)
  3. <br/> inside edge labels  |"text<br/>more"| (HTML not supported in edge labels)
  4. Literal \\n in node labels (renders as text, not newline — use <br/>)
  5. Duplicate node IDs (causes silent mis-renders)
  6. Node IDs that are Mermaid reserved keywords (end, graph, subgraph, style, etc.)

Exit 0 = all clean. Exit 1 = one or more issues found.

Usage:
    python3 .claude/skills/codemap/scripts/validate_graphs.py            # all *.mmd in .claude/graphs/
    python3 .claude/skills/codemap/scripts/validate_graphs.py file.mmd   # specific file
"""

import re
import sys
from pathlib import Path
from collections import Counter

MERMAID_KEYWORDS = {
    "end", "graph", "subgraph", "style", "classDef", "class",
    "click", "direction", "LR", "TD", "TB", "BT", "RL",
    "flowchart", "sequenceDiagram", "gantt", "pie",
}

GRAPH_MODES = {"graph TD", "graph LR", "graph TB", "graph BT", "graph RL"}


def check_file(path: Path) -> list[str]:
    issues = []
    content = path.read_text(encoding="utf-8")
    lines = content.splitlines()

    # ── 1. YAML frontmatter multi-line values ────────────────────────────────
    if content.startswith("---"):
        fm_end = content.find("---", 3)
        if fm_end > 0:
            fm_lines = content[3:fm_end].splitlines()
            in_scalar = False
            scalar_key = ""
            for i, line in enumerate(fm_lines, 1):
                if re.match(r"^\w[\w-]*:", line):
                    in_scalar = True
                    scalar_key = line.split(":")[0]
                elif in_scalar and line.startswith(" ") and not line.strip().startswith("#"):
                    issues.append(
                        f"L{i}: YAML multi-line value for '{scalar_key}' — "
                        f"use a quoted single-line string instead: {line.strip()[:60]}"
                    )
                    in_scalar = False  # report once per key
                elif line and not line.startswith(" "):
                    in_scalar = False

    # Detect the diagram mode
    mode_m = re.search(r"^(flowchart|graph)\s+(\w+)", content, re.M)
    mode = f"{mode_m.group(1)} {mode_m.group(2)}" if mode_m else "unknown"
    is_graph_mode = mode in GRAPH_MODES

    # ── 2. Subgraph IDs used in edges (only illegal in graph mode) ───────────
    subgraph_ids = set(re.findall(r"^\s*subgraph\s+(\w+)", content, re.M))
    if is_graph_mode and subgraph_ids:
        edge_lhs = set(re.findall(r"^\s+(\w+)\s*(?:-->|-.->|---|==>)", content, re.M))
        edge_rhs = set(re.findall(r"(?:-->|-.->|---|==>)\s*(\w+)", content))
        edge_nodes = edge_lhs | edge_rhs
        collisions = subgraph_ids & edge_nodes
        if collisions:
            issues.append(
                f"'graph' mode with subgraph IDs used in edges — "
                f"change to 'flowchart {mode.split()[1]}'. "
                f"Offending IDs: {sorted(collisions)}"
            )

    # ── 3. <br/> inside edge labels ──────────────────────────────────────────
    for i, line in enumerate(lines, 1):
        edge_labels = re.findall(r'\|"([^"]+)"\|', line)
        for label in edge_labels:
            if "<br/>" in label:
                issues.append(
                    f"L{i}: <br/> inside edge label (not supported) — "
                    f"use plain text or / separator: {label[:60]}"
                )

    # ── 4. Literal \\n in node labels ────────────────────────────────────────
    for i, line in enumerate(lines, 1):
        if "\\n" in line:
            issues.append(
                f"L{i}: literal \\n in label — use <br/> for line breaks: {line.strip()[:70]}"
            )

    # ── 5. Duplicate node IDs ────────────────────────────────────────────────
    node_ids = re.findall(r"^\s+(\w+)\s*[\[\({/]", content, re.M)
    dupes = [k for k, v in Counter(node_ids).items() if v > 1]
    if dupes:
        issues.append(f"Duplicate node IDs (causes mis-renders): {sorted(dupes)}")

    # ── 6. Reserved keywords as node IDs ────────────────────────────────────
    for nid in set(node_ids):
        if nid.lower() in {k.lower() for k in MERMAID_KEYWORDS}:
            issues.append(
                f"Reserved Mermaid keyword used as node ID: '{nid}' — rename it"
            )

    return issues


def main() -> int:
    if len(sys.argv) > 1:
        paths = [Path(p) for p in sys.argv[1:]]
    else:
        graphs_dir = Path(__file__).parents[3] / "graphs"
        paths = sorted(graphs_dir.glob("*.mmd"))

    if not paths:
        print("No .mmd files found.")
        return 0

    total_issues = 0
    for path in paths:
        if not path.exists():
            print(f"✗ {path}: file not found")
            total_issues += 1
            continue
        issues = check_file(path)
        if issues:
            print(f"\n✗ {path.name} — {len(issues)} issue(s):")
            for iss in issues:
                print(f"    • {iss}")
            total_issues += len(issues)
        else:
            print(f"✓ {path.name}")

    print()
    if total_issues:
        print(f"  {total_issues} issue(s) found — fix before committing.")
    else:
        print("  All graphs valid.")
    return 1 if total_issues else 0


if __name__ == "__main__":
    sys.exit(main())
