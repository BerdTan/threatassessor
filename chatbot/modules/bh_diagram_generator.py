"""
Blackhat Diagram Generator — Layer 2D post-processing.

Reads after.mmd (per-path controls) and overlays:
  1. Cross-path chain edges  — dashed orange/red arrows between shared pivot nodes
  2. BH gap controls         — NEW_BH_* nodes for mitigation gaps identified only by Blackhat
  3. Stealth technique paths — thin dotted edges annotated with stealth technique IDs

Output: after_bh.mmd (alongside after.mmd in report dir).

Called automatically after Blackhat critique completes in the MoE pipeline.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Orange = chain pivot, red = critical chain, purple = stealth
_CHAIN_COLORS = {
    "CRITICAL": ("fill:#ff4d4d,stroke:#c92a2a", "#ff4d4d"),
    "HIGH":     ("fill:#ff8c00,stroke:#e67700", "#ff8c00"),
    "MEDIUM":   ("fill:#ffd43b,stroke:#fab005", "#ffd43b"),
    "LOW":      ("fill:#74c0fc,stroke:#339af0", "#74c0fc"),
}
_BH_GAP_NODE_STYLE   = "fill:#d63384,stroke:#a61e4d,stroke-width:2px,color:#ffffff"
_STEALTH_EDGE_STYLE  = "stroke:#cc5de8,stroke-width:1px,stroke-dasharray:4 2"
_CHAIN_EDGE_CRITICAL = "stroke:#ff4d4d,stroke-width:2px,stroke-dasharray:6 3"
_CHAIN_EDGE_HIGH     = "stroke:#ff8c00,stroke-width:2px,stroke-dasharray:6 3"
_CHAIN_EDGE_DEFAULT  = "stroke:#ffd43b,stroke-width:1px,stroke-dasharray:4 2"


def _node_id(name: str) -> str:
    """Convert a display name to a safe Mermaid node ID."""
    return re.sub(r"[^a-zA-Z0-9_]", "", name.replace(" ", ""))


def _gap_node_id(gap: str, idx: int) -> str:
    safe = re.sub(r"[^a-zA-Z0-9]", "", gap[:24].replace(" ", ""))
    return f"NEW_BH_{safe}_{idx}" if safe else f"NEW_BH_GAP{idx}"


def generate_bh_diagram(report_dir: str) -> Optional[str]:
    """
    Generate after_bh.mmd for a completed BH run.

    Returns: path to written file, or None if prerequisites missing.
    """
    report_path = Path(report_dir)
    after_mmd_path  = report_path / "after.mmd"
    gt_path         = report_path / "ground_truth.json"
    out_path        = report_path / "after_bh.mmd"

    if not after_mmd_path.exists():
        logger.warning("bh_diagram: after.mmd not found — skipping")
        return None
    if not gt_path.exists():
        logger.warning("bh_diagram: ground_truth.json not found — skipping")
        return None

    with open(gt_path) as f:
        gt = json.load(f)

    bh = gt.get("blackhat_critique")
    if not bh:
        logger.info("bh_diagram: no blackhat_critique in ground_truth — skipping")
        return None

    with open(after_mmd_path) as f:
        base = f.read()

    overlay_lines: List[str] = []
    style_lines:   List[str] = []
    link_styles:   List[str] = []
    link_counter = _count_existing_links(base)

    # ── 1. BH gap control nodes ──────────────────────────────────────────────
    chain_gaps: List[str] = bh.get("mitigation_gaps_for_chains", [])
    shared_nodes: Dict = bh.get("shared_nodes", {})
    bh_gap_node_ids: List[str] = []

    if chain_gaps:
        overlay_lines.append("")
        overlay_lines.append("    %% ━━ BLACKHAT LAYER 2D: CROSS-PATH CHAIN GAPS ━━")
        overlay_lines.append("    %% ⚔️  Controls missing across chained attack paths (not caught by per-path analysis)")

        for idx, gap in enumerate(chain_gaps[:8]):
            nid = _gap_node_id(gap, idx)
            label = gap[:60].replace('"', "'")
            overlay_lines.append(f'    {nid}["⚔️ {label}"]')
            style_lines.append(f"    style {nid} {_BH_GAP_NODE_STYLE}")
            bh_gap_node_ids.append(nid)

    # ── 2. Cross-path chain edges (shared pivot nodes → chain) ───────────────
    least_resistance: List[Dict] = bh.get("least_resistance_paths", [])
    chained_findings: List[str]  = bh.get("chained_exploit_findings", [])

    overlay_lines.append("")
    overlay_lines.append("    %% ━━ BLACKHAT: CROSS-PATH PIVOT EDGES ━━")
    overlay_lines.append("    %% Dashed coloured edges = chain routes Blackhat identified across APs")

    added_edges: set = set()

    # From structured least_resistance_paths (dicts with chain/pivot/chain_criticality)
    for chain_entry in least_resistance[:6]:
        if not isinstance(chain_entry, dict):
            continue
        chain_aps  = chain_entry.get("chain", [])
        pivot      = chain_entry.get("pivot", "")
        criticality = chain_entry.get("chain_criticality", "MEDIUM").upper()
        if len(chain_aps) < 2:
            continue

        # Draw AP-i → AP-j edge through the pivot node
        src_id  = _node_id(chain_aps[0])
        dst_id  = _node_id(chain_aps[1])
        edge_key = f"{src_id}_{dst_id}"
        if edge_key in added_edges:
            continue
        added_edges.add(edge_key)

        pivot_label = f"via {pivot}" if pivot else "chain"
        overlay_lines.append(f'    {src_id} -.->|"⚔️ {pivot_label}"| {dst_id}')
        edge_style = _CHAIN_EDGE_CRITICAL if criticality == "CRITICAL" else (
            _CHAIN_EDGE_HIGH if criticality == "HIGH" else _CHAIN_EDGE_DEFAULT
        )
        link_styles.append(f"    linkStyle {link_counter} {edge_style}")
        link_counter += 1

    # From string findings "AP-i → AP-j via `pivot` [CRITICALITY]"
    _finding_re = re.compile(r"(AP-\w+)\s*→\s*(AP-\w+)\s*via\s*`([^`]+)`\s*\[([A-Z]+)\]")
    for finding in chained_findings[:6]:
        m = _finding_re.search(str(finding))
        if not m:
            continue
        ap_src, ap_dst, pivot, criticality = m.groups()
        # Map AP IDs to path first-node (rough anchor)
        src_id  = _node_id(ap_src)
        dst_id  = _node_id(ap_dst)
        edge_key = f"{src_id}_{dst_id}_f"
        if edge_key in added_edges:
            continue
        added_edges.add(edge_key)

        overlay_lines.append(f'    {src_id} -.->|"⚔️ via {pivot}"| {dst_id}')
        edge_style = _CHAIN_EDGE_CRITICAL if criticality == "CRITICAL" else (
            _CHAIN_EDGE_HIGH if criticality == "HIGH" else _CHAIN_EDGE_DEFAULT
        )
        link_styles.append(f"    linkStyle {link_counter} {edge_style}")
        link_counter += 1

    # ── 3. Anchor gap nodes to their shared pivot nodes ──────────────────────
    if bh_gap_node_ids and shared_nodes:
        overlay_lines.append("")
        overlay_lines.append("    %% BH gap controls anchored to shared pivot nodes")
        pivot_list = list(shared_nodes.keys())[:len(bh_gap_node_ids)]
        for i, nid in enumerate(bh_gap_node_ids):
            pivot = pivot_list[i] if i < len(pivot_list) else None
            if pivot:
                pivot_id = _node_id(pivot)
                overlay_lines.append(f"    {pivot_id} -.->|missing| {nid}")
                link_styles.append(f"    linkStyle {link_counter} stroke:#d63384,stroke-width:1px,stroke-dasharray:3 2")
                link_counter += 1

    # ── 4. Stealth technique annotation (subgraph) ───────────────────────────
    stealth_score: int   = bh.get("stealth_score", 0)
    stealth_techs: List  = bh.get("stealthy_techniques", [])

    if stealth_score > 0 or stealth_techs:
        techs_label = ", ".join(str(t) for t in stealth_techs[:5]) or "—"
        overlay_lines.append("")
        overlay_lines.append("    %% ━━ BLACKHAT: STEALTH ASSESSMENT ━━")
        overlay_lines.append(f'    BH_STEALTH["🕵️ Stealth Score: {stealth_score}/100<br/>Techniques: {techs_label}"]')
        style_lines.append("    style BH_STEALTH fill:#5c0099,stroke:#8b5cf6,stroke-width:2px,color:#ffffff")

    # ── Assemble final diagram ────────────────────────────────────────────────
    # Strip trailing style block from base, re-append after overlays
    style_block_start = _find_style_block_start(base)
    if style_block_start >= 0:
        base_body   = base[:style_block_start].rstrip()
        base_styles = "\n" + base[style_block_start:]
    else:
        base_body   = base.rstrip()
        base_styles = ""

    bh_header = (
        "\n\n    %% ════════════════════════════════════════════════════\n"
        "    %% ⚔️  BLACKHAT LAYER 2D — CROSS-PATH CHAIN OVERLAY\n"
        "    %% Chains, pivot edges, and gap controls not visible\n"
        "    %% from individual per-path analysis (after.mmd).\n"
        "    %% ════════════════════════════════════════════════════"
    )

    result = (
        base_body
        + bh_header
        + "\n".join(overlay_lines)
        + base_styles
        + ("\n" + "\n".join(style_lines) if style_lines else "")
        + ("\n" + "\n".join(link_styles)  if link_styles  else "")
        + "\n"
    )

    with open(out_path, "w") as f:
        f.write(result)

    logger.info(f"bh_diagram: wrote {out_path} ({len(bh_gap_node_ids)} gap nodes, {len(added_edges)} chain edges)")
    return str(out_path)


def _count_existing_links(mmd: str) -> int:
    """Count --> and -.-> edges in existing diagram so linkStyle indices are correct."""
    return len(re.findall(r"-+->|==>|~~~", mmd))


def _find_style_block_start(mmd: str) -> int:
    """Return index of first 'style ' line, or -1."""
    for i, line in enumerate(mmd.split("\n")):
        if line.strip().startswith("style "):
            # Convert line index to char index
            return sum(len(l) + 1 for l in mmd.split("\n")[:i])
    return -1
