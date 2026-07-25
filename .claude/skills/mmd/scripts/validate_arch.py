#!/usr/bin/env python3
"""
validate_arch.py — Validate an architecture .mmd file before running the engine.

Part of the /mmd skill. Checks structural rules the engine requires.
For context-graph validation (.claude/graphs/) use validate_graphs.py instead.

Checks:
  1. First-line keyword is 'flowchart' (not 'graph')
  2. No YAML frontmatter (--- block breaks the engine parser)
  3. No orphan nodes (nodes defined but not referenced in any edge)
  4. At least one entry-point candidate
  5. At least one sensitive-target candidate
  6. Subgraph IDs are unique

Usage:
    python3 .claude/skills/mmd/scripts/validate_arch.py <path.mmd> [<path2.mmd> ...]
    python3 .claude/skills/mmd/scripts/validate_arch.py tests/data/architectures/*.mmd

Exit 0 = all clean.  Exit 1 = one or more issues found.
"""

import re
import sys
from pathlib import Path

ENTRY_KW = {
    "user", "visitor", "employee", "client", "browser", "mobile",
    "internet", "external", "attacker", "citizen", "customer",
    "frontend", "webapp", "web app", "public",
}

TARGET_KW = {
    "database", "db", "storage", "secret", "vault", "credential",
    "cache", "queue", "bucket", "blob", "datastore", "data store",
    "registry", "keystore", "key store", "backup",
}


def _extract_node_labels(content: str) -> dict[str, str]:
    """Return {node_id: label} for every node definition line."""
    nodes = {}
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("%%") or line.startswith("subgraph") or line == "end":
            continue
        # Node with label: ID[label], ID(label), ID((label)), ID[(label)]
        m = re.match(r'^(\w+)\s*[\[\(\{]([^\]\)\}]*)', line)
        if m:
            nodes[m.group(1)] = m.group(2).strip()
    return nodes


def _extract_edge_node_ids(content: str) -> set[str]:
    """Return all node IDs that appear in edge definitions."""
    refs = set()
    for line in content.splitlines():
        line = line.strip()
        if "-->" in line or "---" in line or "<-->" in line or "-.-> " in line:
            # Extract all word-token sequences not inside |...|
            clean = re.sub(r'\|[^|]*\|', '', line)
            refs.update(re.findall(r'\b(\w+)\b', clean))
    return refs


def check_file(path: Path) -> list[str]:
    issues = []
    content = path.read_text(encoding="utf-8")
    lines = content.splitlines()
    raw_lines = [l.strip() for l in lines if l.strip() and not l.strip().startswith("%%")]

    # ── 1. YAML frontmatter ──────────────────────────────────────────────────
    if content.startswith("---"):
        issues.append("YAML frontmatter present (--- block) — engine parser requires raw MMD; remove the frontmatter")

    # Work on stripped content for remaining checks
    stripped = re.sub(r'^---.*?---\s*', '', content, flags=re.DOTALL).strip()
    s_lines = [l.strip() for l in stripped.splitlines() if l.strip() and not l.strip().startswith("%%")]

    # ── 2. First keyword must be 'flowchart' ────────────────────────────────
    if s_lines:
        first = s_lines[0]
        if first.startswith("graph "):
            issues.append(
                f"First line uses 'graph' mode: '{first}' — change to 'flowchart {first.split()[1]}'; "
                "'graph' mode returns 0 nodes from the engine parser"
            )
        elif not first.startswith("flowchart"):
            issues.append(f"First line is not a flowchart declaration: '{first[:60]}'")

    # ── 3. Orphan nodes ──────────────────────────────────────────────────────
    node_labels = _extract_node_labels(stripped)
    edge_refs = _extract_edge_node_ids(stripped)
    orphans = [nid for nid in node_labels if nid not in edge_refs]
    if orphans:
        issues.append(f"Orphan nodes (no edges — contribute 0 techniques): {orphans}")

    # ── 4. Entry-point candidate ─────────────────────────────────────────────
    has_entry = any(
        any(kw in lbl.lower() for kw in ENTRY_KW)
        for lbl in node_labels.values()
    )
    if not has_entry:
        issues.append(
            "No entry-point candidate found (no node label containing: "
            + ", ".join(sorted(ENTRY_KW)[:8]) + ", …). "
            "Add an external actor node (User, Browser, Client, Internet, etc.)"
        )

    # ── 5. Sensitive-target candidate ────────────────────────────────────────
    has_target = any(
        any(kw in lbl.lower() for kw in TARGET_KW)
        for lbl in node_labels.values()
    )
    if not has_target:
        issues.append(
            "No sensitive-target candidate found (no node label containing: "
            + ", ".join(sorted(TARGET_KW)[:8]) + ", …). "
            "Add a database, storage, cache, or secret node for meaningful attack paths."
        )

    # ── 6. Duplicate subgraph IDs ────────────────────────────────────────────
    sg_ids = re.findall(r'^\s*subgraph\s+(\w+)', stripped, re.M)
    seen = set()
    for sg in sg_ids:
        if sg in seen:
            issues.append(f"Duplicate subgraph ID: '{sg}'")
        seen.add(sg)

    return issues


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 validate_arch.py <file.mmd> [file2.mmd ...]")
        sys.exit(1)

    paths = [Path(a) for a in sys.argv[1:]]
    total_issues = 0

    for path in paths:
        if not path.exists():
            print(f"ERROR: File not found: {path}")
            total_issues += 1
            continue

        issues = check_file(path)
        if issues:
            print(f"\n✗  {path}")
            for i in issues:
                print(f"   • {i}")
            total_issues += len(issues)
        else:
            print(f"✓  {path}")

    if total_issues:
        print(f"\n{total_issues} issue(s) found.")
        sys.exit(1)
    else:
        print(f"\nAll clean ({len(paths)} file(s)).")
        sys.exit(0)


if __name__ == "__main__":
    main()
