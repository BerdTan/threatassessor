#!/usr/bin/env python3
"""
adr-patch.py — Collect "add to ADR" signals from all ER sources and write
structured hop-level entries into 10_adr_report.md.

Sources scanned:
  1. SM action_plan immediate items (non-structural, have "add to the architecture ADR" in first_step)
  2. KNOWN critical/high findings in consensus_recommendations
  3. Expert gaps with severity CRITICAL/HIGH that name a specific node + technique
  4. resolved[] items with verdict=REAL from review-unsure output

Usage:
    python3 adr-patch.py 21_agentic_ai_system
    python3 adr-patch.py 21_agentic_ai_system --dry-run    # show patches without writing
    python3 adr-patch.py 21_agentic_ai_system --source sm  # only SM items
    python3 adr-patch.py 21_agentic_ai_system --source known
    python3 adr-patch.py 21_agentic_ai_system --source gaps
    python3 adr-patch.py                                   # most recent report
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))

# ── Colour helpers ────────────────────────────────────────────────────────────
def _c(t, code): return f"\033[{code}m{t}\033[0m"
def bold(t):  return _c(t, "1")
def green(t): return _c(t, "92")
def amber(t): return _c(t, "33")
def red(t):   return _c(t, "31")
def cyan(t):  return _c(t, "36")
def dim(t):   return _c(t, "2")

SEV_RANK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}

# Known architecture node names — used for extraction heuristics
_ARCH_NODES = [
    "WebUI", "AgentOrchestrator", "ToolRegistry", "DatabaseTool", "UserDB",
    "VectorDB", "EmbeddingService", "CodeExecution", "PromptManager",
    "APIIntegrations", "WebSearch", "Users",
]

# ── Signal collection ─────────────────────────────────────────────────────────

def _extract_nodes(text: str) -> list[str]:
    found = []
    for n in _ARCH_NODES:
        if n in text:
            found.append(n)
    return found

def _extract_techniques(text: str) -> list[str]:
    return list(dict.fromkeys(re.findall(r"\bT\d{4}(?:\.\d{3})?\b", text)))

def _extract_aps(text: str) -> list[str]:
    return list(dict.fromkeys(re.findall(r"\bAP-\d+\b", text)))


def collect_signals(moe: dict, sm: dict, source_filter: Optional[str]) -> list[dict]:
    """
    Return a deduplicated list of patch signals, each with:
      technique, nodes, aps, control, description, recommendation, source, severity
    """
    signals = []

    # ── Source 1: SM action_plan immediate (non-structural) ───────────────────
    if source_filter in (None, "sm"):
        for item in sm.get("action_plan", []):
            if item.get("tier") == "structural":
                continue
            fs = item.get("first_step", "")
            action = item.get("action", "")
            if "adr" not in fs.lower() and "adr" not in action.lower():
                continue
            techs = _extract_techniques(action + " " + fs)
            nodes = _extract_nodes(action + " " + fs)
            aps   = _extract_aps(action + " " + fs)
            if not techs and not nodes:
                continue
            signals.append({
                "source":         "sm_action_plan",
                "severity":       item.get("priority", "high").upper(),
                "technique":      techs[0] if techs else "",
                "techniques":     techs,
                "nodes":          nodes,
                "aps":            aps,
                "control":        _infer_control(action),
                "description":    action,
                "recommendation": item.get("first_step", ""),
            })

    # ── Source 2: KNOWN critical/high consensus findings ─────────────────────
    # Only include findings where the description names an "unmapped" technique
    # at a specific node — not cross-path pivot summaries (those belong in BH section).
    if source_filter in (None, "known"):
        cr = moe.get("consensus_recommendations", {})
        for item in cr.get("critical", []) + cr.get("high", []):
            if item.get("confidence_label") != "KNOWN":
                continue
            desc = item.get("description", "")
            rec  = item.get("recommendation", "")
            # Skip pivot/chain summaries — they contain "pivot", "fan out", "chain"
            # but no specific "unmapped" technique attribution
            if any(w in desc.lower() for w in ["pivot enables", "fan out", "chains ap-", "sequential chain"]):
                continue
            # Skip if no specific node named alongside a technique
            techs = _extract_techniques(desc)
            nodes = _extract_nodes(desc)
            aps   = _extract_aps(desc)
            if not techs or not nodes:
                continue
            # Only include if recommendation has an actionable control name
            ctrl = _infer_control(rec)
            if len(ctrl) > 60 or not ctrl:  # long = fell back to raw text = not a control name
                continue
            signals.append({
                "source":         f"known_{item.get('source','?')}",
                "severity":       item.get("severity", "HIGH").upper(),
                "technique":      techs[0] if techs else "",
                "techniques":     techs,
                "nodes":          nodes,
                "aps":            aps,
                "control":        ctrl,
                "description":    desc,
                "recommendation": rec,
            })

    # ── Source 3: Expert gaps CRITICAL/HIGH with node + technique ─────────────
    # Only include gaps with exactly one primary node (descriptions about one
    # specific node are actionable; multi-node descriptions are cross-path summaries).
    if source_filter in (None, "gaps"):
        ev = moe.get("expert_validations", {})
        for critic_name, v in ev.items():
            for g in v.get("gaps", []):
                sev = g.get("severity", "").upper()
                if SEV_RANK.get(sev, 0) < SEV_RANK["HIGH"]:
                    continue
                desc = g.get("description", "")
                rec  = g.get("recommendation", "")
                techs = _extract_techniques(desc)
                nodes = _extract_nodes(desc)
                aps   = _extract_aps(desc)
                if not techs or not nodes:
                    continue
                # Require a clean control name in the recommendation
                ctrl = _infer_control(rec)
                if len(ctrl) > 70 or not ctrl:
                    continue
                # Restrict to primary node only (first named node — most specific)
                primary_node = nodes[:1]
                signals.append({
                    "source":         f"gap_{critic_name}",
                    "severity":       sev,
                    "technique":      techs[0] if techs else "",
                    "techniques":     techs[:2],
                    "nodes":          primary_node,
                    "aps":            aps,
                    "control":        ctrl,
                    "description":    desc,
                    "recommendation": rec,
                })

    # ── Source 4: resolved REAL items from review-unsure ─────────────────────
    if source_filter in (None, "resolved"):
        cr = moe.get("consensus_recommendations", {})
        for item in cr.get("resolved", []):
            if item.get("verdict") != "REAL":
                continue
            desc = item.get("description", "")
            res  = item.get("resolution", "")
            techs = _extract_techniques(desc)
            nodes = _extract_nodes(desc)
            aps   = _extract_aps(desc)
            if not nodes:
                continue
            signals.append({
                "source":         f"resolved_{item.get('source','?')}",
                "severity":       item.get("severity", "MEDIUM").upper(),
                "technique":      techs[0] if techs else "",
                "techniques":     techs,
                "nodes":          nodes,
                "aps":            aps,
                "control":        _infer_control(res),
                "description":    desc,
                "recommendation": res,
            })

    return _deduplicate(signals)


def _infer_control(text: str) -> str:
    """Extract a short control name from a recommendation or description."""
    text = text.strip()
    # Known control name patterns
    patterns = [
        r"\bFile Integrity Monitoring\b",
        r"\bFIM\b",
        r"\bHIDS\b",
        r"\bHost.Based Intrusion Detection\b",
        r"\bMandatory Access Control\b",
        r"\bMAC\b",
        r"\bUEBA\b",
        r"\bWAF\b",
        r"\bEDR\b",
        r"\bSIEM\b",
        r"\bMFA\b",
        r"\bSandbox(?:ing)?\b",
        r"\bRASP\b",
        r"\bCapability.based access control\b",
    ]
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            return m.group(0)
    # Fall back: first imperative verb phrase (Deploy X, Add X, Apply X, etc.)
    # Extract just the noun phrase (stops at "with", "at", "for", "between", "to")
    m = re.match(
        r"(?:Deploy|Add|Apply|Implement|Configure|Enable|Enforce)\s+"
        r"(.{4,35}?)(?:\s+(?:with|at|for|between|to|and)\b|[\.\,;]|$)",
        text
    )
    if m:
        return m.group(1).strip().rstrip(".;,")
    return text[:40].rstrip(".;,")


def _deduplicate(signals: list[dict]) -> list[dict]:
    """Group by (technique, frozenset(nodes)) — keep highest severity per group."""
    seen = {}
    for s in signals:
        key = (s["technique"], frozenset(s["nodes"]))
        if key not in seen:
            seen[key] = s
        else:
            if SEV_RANK.get(s["severity"], 0) > SEV_RANK.get(seen[key]["severity"], 0):
                seen[key] = s
    # Sort: CRITICAL first, then by technique
    return sorted(seen.values(),
                  key=lambda x: (-SEV_RANK.get(x["severity"], 0), x["technique"]))


# ── ADR builder ───────────────────────────────────────────────────────────────

def _build_adr_block(signal: dict) -> str:
    """
    Build a markdown hop-level ADR block for a single signal.
    Format mirrors existing hop control entries in 10_adr_report.md.
    """
    ctrl     = signal["control"] or "Control (see recommendation)"
    techs    = ", ".join(signal["techniques"]) if signal["techniques"] else "see below"
    nodes    = ", ".join(signal["nodes"])
    aps_str  = ", ".join(signal["aps"]) if signal["aps"] else "all affected paths"
    sev      = signal["severity"]
    rec      = signal["recommendation"] or signal["description"]
    src      = signal["source"].replace("_", " ")

    # Shorten recommendation to one sentence
    rec_one = rec.split(". ")[0].rstrip(".,;") + "."

    primary_tech = signal["technique"] or (signal["techniques"][0] if signal["techniques"] else "")
    lines = [
        f"\n**{ctrl}** [{sev}] — Detect  _(added via /adr-patch · source: {src})_",
        f"> {primary_tech} at {nodes} across {aps_str}",
        f"> {rec_one}",
        f"> Risk: unmitigated → partially mitigated ({primary_tech} coverage gap addressed)",
    ]
    return "\n".join(lines) + "\n"


# ── ADR file patcher ──────────────────────────────────────────────────────────

def _get_adr_ap_map(adr_content: str) -> dict[str, tuple[int, int]]:
    """
    Return {ap_id: (start_line_index, end_line_index)} for each ADR section.
    end is the line before the next '## ADR-' header or EOF.
    """
    lines = adr_content.splitlines(keepends=True)
    adr_map = {}
    current_ap = None
    start_idx  = 0
    for i, line in enumerate(lines):
        m = re.match(r"^## ADR-\d+ — (AP-\d+)", line)
        if m:
            if current_ap:
                adr_map[current_ap] = (start_idx, i)
            current_ap = m.group(1)
            start_idx  = i
    if current_ap:
        adr_map[current_ap] = (start_idx, len(lines))
    return adr_map, lines


def patch_adr_file(adr_path: Path, signals: list[dict], dry_run: bool) -> int:
    """
    For each signal, find the hop-level section inside the relevant ADR(s)
    and append the new control block before the section's last control.
    Returns the number of patches written.
    """
    content = adr_path.read_text(encoding="utf-8")
    adr_map, lines = _get_adr_ap_map(content)

    patched = 0
    # Track which (ap, node, technique) combos we've already patched this run
    already_done = set()

    # Build list of (insertion_point, block_text) in reverse order so indexes stay valid
    insertions = []  # list of (line_idx, text)

    for signal in signals:
        ctrl_marker = f"_(added via /adr-patch"
        # Skip if already patched in a previous run
        if signal["control"] and signal["control"] in content and ctrl_marker in content:
            existing = re.search(
                re.escape(signal["control"]) + r".*?added via /adr-patch",
                content, re.DOTALL
            )
            if existing:
                continue

        target_aps = signal["aps"] or list(adr_map.keys())

        for ap_id in target_aps:
            if ap_id not in adr_map:
                continue
            ap_start, ap_end = adr_map[ap_id]

            for node in signal["nodes"]:
                combo = (ap_id, node, signal["technique"])
                if combo in already_done:
                    continue

                # Find the node hop header inside this ADR section
                node_pattern = rf"#### `{re.escape(node)}`"
                node_idx = None
                for i in range(ap_start, ap_end):
                    if re.search(node_pattern, lines[i]):
                        node_idx = i
                        break

                if node_idx is None:
                    continue  # Node not in this ADR

                # Check if this technique+control is already attributed at this hop
                hop_end = ap_end
                for i in range(node_idx + 1, ap_end):
                    if lines[i].startswith("#### "):
                        hop_end = i
                        break
                hop_text = "".join(lines[node_idx:hop_end])

                if signal["technique"] in hop_text and (
                    signal["control"].lower() in hop_text.lower()
                    or "added via /adr-patch" in hop_text
                ):
                    continue  # Already attributed

                # Insert block just before the hop section ends
                # (before the next #### or _Next step_ within the hop)
                insert_at = hop_end
                for i in range(node_idx + 1, hop_end):
                    if lines[i].startswith("_Next step") or lines[i].startswith("#### "):
                        insert_at = i
                        break

                block = _build_adr_block(signal)
                insertions.append((insert_at, block))
                already_done.add(combo)
                patched += 1

    if not dry_run and insertions:
        # Apply in reverse order (highest line index first) to preserve positions
        insertions.sort(key=lambda x: -x[0])
        for idx, block in insertions:
            lines.insert(idx, block)
        adr_path.write_text("".join(lines), encoding="utf-8")

    return patched, insertions


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    ap_parser = argparse.ArgumentParser(description="Patch ADR report with 'add to ADR' signals")
    ap_parser.add_argument("arch", nargs="?")
    ap_parser.add_argument("--dry-run", action="store_true",
                           help="Show patches without writing to file")
    ap_parser.add_argument("--source", choices=["sm", "known", "gaps", "resolved"],
                           help="Limit to a single signal source")
    args = ap_parser.parse_args()

    report_root = REPO / "report"

    if args.arch:
        arch = args.arch
    else:
        dirs = sorted(
            [d for d in report_root.iterdir() if d.is_dir()],
            key=lambda d: d.stat().st_mtime, reverse=True
        )
        if not dirs:
            print(red("No report directories found."), file=sys.stderr)
            sys.exit(1)
        arch = dirs[0].name

    report_dir = report_root / arch
    moe_path   = report_dir / "07_moe_orchestrator.json"
    sm_path    = report_dir / "08_scrum_master.json"
    adr_path   = report_dir / "10_adr_report.md"

    missing = [p for p in [moe_path, adr_path] if not p.exists()]
    if missing:
        for p in missing:
            print(red(f"Missing: {p}"), file=sys.stderr)
        print(dim("  Run /run-er first to generate ER files."), file=sys.stderr)
        sys.exit(1)

    moe = json.loads(moe_path.read_text())
    sm  = json.loads(sm_path.read_text()) if sm_path.exists() else {}

    print()
    print(bold(f"  ADR Patch — {arch}"))
    src_label = f"source: {args.source}" if args.source else "all sources"
    mode_label = dim("  [DRY-RUN — no file changes]") if args.dry_run else ""
    print(dim(f"  {src_label}") + ("  " + mode_label if mode_label else ""))
    print(dim("  ─" * 35))
    print()

    signals = collect_signals(moe, sm, args.source)

    if not signals:
        print(f"  {green('✓')} No 'add to ADR' signals found for the requested source(s).")
        print()
        return

    print(f"  {len(signals)} signal{'s' if len(signals) != 1 else ''} collected:")
    print()
    for s in signals:
        sev_color = {"CRITICAL": red, "HIGH": amber, "MEDIUM": amber, "LOW": dim}.get(s["severity"], dim)
        print(f"  {sev_color(s['severity'][:3])}  "
              f"{cyan(s['technique'] or '—')}  "
              f"{bold(', '.join(s['nodes']) or '—')}  "
              f"{dim('APs: ' + ', '.join(s['aps'][:4]) + ('+' if len(s['aps']) > 4 else '') if s['aps'] else 'all')}")
        print(f"     control:  {s['control'] or dim('(inferred from recommendation)')}")
        print(f"     source:   {dim(s['source'])}")
        print(f"     rec:      {dim(s['recommendation'][:90] if s['recommendation'] else s['description'][:90])}")
        print()

    print(dim("  ─" * 35))

    n_patched, insertions = patch_adr_file(adr_path, signals, args.dry_run)

    if args.dry_run:
        print(f"  {amber('DRY-RUN')} — {n_patched} insertion(s) would be written.")
        if insertions:
            print()
            print(dim("  Preview (first 2):"))
            for idx, block in insertions[:2]:
                print(dim(f"    → line {idx}: {block.strip()[:100]}"))
    else:
        if n_patched:
            print(f"  {green(f'✓ {n_patched} insertion(s) written')} to {adr_path.name}")
            print()
            print(dim("  Next steps:"))
            print(dim("  1. Review 10_adr_report.md — search 'added via /adr-patch' to find new entries"))
            print(dim("  2. Assign owners and target sprint in each patched hop section"))
            print(dim("  3. Re-run /tatb-score to check Plan-Actionable improvement"))
            print(dim("  4. Re-run /run-er when controls are implemented to close the ER loop"))
        else:
            print(f"  {green('✓')} All signals already attributed — no new patches needed.")
    print()


if __name__ == "__main__":
    main()
