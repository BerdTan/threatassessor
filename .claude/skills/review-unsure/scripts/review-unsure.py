#!/usr/bin/env python3
"""
review-unsure.py — Triage UNSURE cross-expert findings from a ThreatAssessor ER run.

For each UNSURE item in consensus_recommendations.review[], runs a deterministic
check against the report artefacts (ground_truth.json, after.mmd, control list).
Items that pass a deterministic check are auto-dismissed with a reason.
Items that cannot be auto-dismissed are escalated to an LLM for a verdict + ADR patch
(requires LLM keys; use --dry-run to skip LLM and print prompts only).

Usage:
    python3 review-unsure.py 21_agentic_ai_system
    python3 review-unsure.py 21_agentic_ai_system --dry-run
    python3 review-unsure.py 21_agentic_ai_system --severity MEDIUM
    python3 review-unsure.py                           # most recent report
"""
import argparse
import json
import os
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
def blue(t):  return _c(t, "34")

SEV_COLOR = {"LOW": dim, "MEDIUM": amber, "HIGH": red, "CRITICAL": red}
SEV_RANK  = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}

# ── Deterministic checks ──────────────────────────────────────────────────────

def _controls_lower(gt: dict) -> list[str]:
    return [c.get("control", "").lower() for c in gt.get("control_recommendations", [])]

def _new_nodes_in_after(report_dir: Path) -> tuple[int, list[str]]:
    after = report_dir / "after.mmd"
    if not after.exists():
        return 0, []
    content = after.read_text(encoding="utf-8")
    nodes = sorted(set(re.findall(r"\bNEW_\w+", content)))
    return len(nodes), nodes

def _validation_errors(gt: dict) -> list:
    return gt.get("validation_results", {}).get("errors", []) or []

def _check_deterministic(item: dict, gt: dict, report_dir: Path) -> Optional[str]:
    """
    Returns a dismissal reason string if the item can be auto-dismissed,
    or None if it needs LLM review.
    """
    cat  = item.get("category", "")
    desc = item.get("description", "").lower()
    controls = _controls_lower(gt)
    ctrl_count = len(gt.get("control_recommendations", []))

    # ── implementation_status: check NEW_* node count vs control count ────────
    if cat == "implementation_status":
        new_n, _ = _new_nodes_in_after(report_dir)
        if new_n >= ctrl_count:
            return (
                f"after.mmd has {new_n} NEW_* nodes vs {ctrl_count} recommended controls "
                f"— all controls are diagrammed. Item is outdated."
            )
        gap = ctrl_count - new_n
        return None  # real gap — needs LLM review with gap={gap}

    # ── detection_tuning: check whether UEBA / behavioral analytics present ───
    if cat in ("detection_tuning", "detection_baseline", "detection_precision"):
        keywords = ["ueba", "behavioral", "anomaly", "baseline", "user behavior"]
        matched = [c for c in controls if any(k in c for k in keywords)]
        if matched:
            return f"Control '{matched[0]}' already addresses behavioral detection. Dismiss."
        return None

    # ── human_layer: check whether user training / phishing sim present ───────
    if cat == "human_layer":
        keywords = ["training", "phishing", "awareness", "simulation"]
        matched = [c for c in controls if any(k in c for k in keywords)]
        if matched:
            return f"Control '{matched[0]}' already addresses the human layer. Dismiss."
        return None

    # ── validation: check if ground_truth validation is VALID ─────────────────
    if cat == "validation":
        errors = _validation_errors(gt)
        status = gt.get("validation_status", "")
        if status in ("VALID", "MOSTLY_VALID") and not errors:
            return f"Ground truth validation status is {status} with no blocking errors. Dismiss."
        if "environmental" in desc and status not in ("INVALID", "FAILED"):
            return (
                "Validation issues are environmental (not structural) and MITRE mappings are "
                "confirmed correct by tester. Dismiss as informational."
            )
        return None

    # ── diagram_completeness / implementation_status: compare counts ──────────
    if cat in ("diagram_completeness", "diagram_consistency"):
        new_n, _ = _new_nodes_in_after(report_dir)
        if new_n >= ctrl_count:
            return (
                f"after.mmd has {new_n} NEW_* nodes covering {ctrl_count} controls. "
                "Diagram is complete."
            )
        return None

    # ── detection_operability: check for detection SLA / alert fatigue controls
    if cat == "detection_operability":
        keywords = ["sla", "alert", "fatigue", "latency", "siem", "soar", "triage"]
        matched = [c for c in controls if any(k in c for k in keywords)]
        if matched:
            return f"Control '{matched[0]}' addresses detection operability. Dismiss."
        # Low severity — often an operational recommendation, not a gap
        if item.get("severity", "").upper() == "LOW":
            return (
                "LOW severity detection operability note — no blocking control gap. "
                "Flag as advisory for next architecture review."
            )
        return None

    # ── control_gap / coverage_gap: check control exists ─────────────────────
    if cat in ("control_gap", "coverage_gap", "control_specification", "control_completeness"):
        # Extract technique or control name from description
        t_codes = re.findall(r"\bT\d{4}(?:\.\d{3})?\b", desc)
        if t_codes:
            # Check if any control maps this technique
            for ctrl in gt.get("control_recommendations", []):
                if any(t in ctrl.get("techniques", []) for t in t_codes):
                    return (
                        f"Technique(s) {', '.join(t_codes)} are covered by "
                        f"'{ctrl.get('control')}'. Dismiss."
                    )
        return None

    # Unknown category — send to LLM
    return None


# ── LLM verdict ───────────────────────────────────────────────────────────────

def _call_llm(prompt: str) -> str:
    """Call the LLM client (same as TA uses) and return the response text."""
    try:
        from agentic.llm_client import LLMClient
        client = LLMClient()
        resp = client.generate(prompt, max_tokens=600, temperature=0.2)
        return (resp.content or "").strip()
    except Exception as e:
        return f"[LLM call failed: {e}]"


def _build_llm_prompt(item: dict, gt: dict, report_dir: Path) -> str:
    ctrl_count = len(gt.get("control_recommendations", []))
    new_n, new_names = _new_nodes_in_after(report_dir)
    controls_sample = ", ".join(_controls_lower(gt)[:15])
    attack_paths = [
        f"  {ap.get('id','?')} [{ap.get('criticality_tier','?')}]: "
        f"{' → '.join(ap.get('path', [])[:5])}"
        for ap in gt.get("expected_attack_paths", [])[:5]
    ]

    return f"""You are a security architect triaging an UNSURE finding from a threat model review.

UNSURE FINDING:
  Category: {item.get('category')}
  Severity: {item.get('severity')}
  Source critic: {item.get('source')}
  Description: {item.get('description')}
  Evidence: {item.get('evidence')}

ARCHITECTURE FACTS:
  Control recommendations ({ctrl_count} total): {controls_sample} …
  NEW_* nodes in after.mmd: {new_n}
  Attack paths (first 5):
{chr(10).join(attack_paths)}

TASK: Determine in 2 sentences whether this finding is REAL (the gap exists and matters) or DISMISS (not a real gap, or not in scope, or already covered).

Respond in this exact format:
VERDICT: REAL | DISMISS
REASON: <one sentence — cite the specific control or node that confirms or refutes the gap>
ADR_PATCH: <one sentence — if REAL: the exact ADR entry to add. If DISMISS: "None.">"""


# ── Report printer ────────────────────────────────────────────────────────────

def _sev_bar(sev: str) -> str:
    bars = {"LOW": "▪", "MEDIUM": "▪▪", "HIGH": "▪▪▪", "CRITICAL": "▪▪▪▪"}
    color = SEV_COLOR.get(sev.upper(), dim)
    return color(bars.get(sev.upper(), "▪"))


def _print_item(idx: int, item: dict, verdict: str, reason: str,
                adr_patch: str, dry_run: bool) -> None:
    sev   = item.get("severity", "?").upper()
    cat   = item.get("category", "?").replace("_", " ")
    src   = item.get("source", "?")
    desc  = item.get("description", "")
    color = SEV_COLOR.get(sev, dim)

    print(f"  {dim(str(idx) + '.')} {_sev_bar(sev)} {color(sev):<8}  {bold(cat)}  {dim('← ' + src)}")
    print(f"     {desc}")
    print()

    if verdict == "DISMISS":
        print(f"     {green('✓ DISMISS')}  {dim(reason)}")
    elif verdict == "REAL":
        print(f"     {red('✗ REAL')}    {reason}")
        if adr_patch and adr_patch.lower() not in ("none", "none.", "n/a"):
            print(f"     {amber('→ ADR:')}    {adr_patch}")
    elif verdict == "PENDING":
        if dry_run:
            print(f"     {amber('~ DRY-RUN')}  Would call LLM. Use without --dry-run to get verdict.")
        else:
            print(f"     {dim('? PENDING')}  {reason}")
    print()


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="Triage UNSURE ER findings")
    ap.add_argument("arch", nargs="?", help="Architecture name (e.g. 21_agentic_ai_system)")
    ap.add_argument("--severity", default="LOW",
                    help="Minimum severity to process (LOW/MEDIUM/HIGH/CRITICAL, default: LOW)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Run deterministic checks only — skip LLM calls, print prompts")
    ap.add_argument("--json", action="store_true", help="Output results as JSON")
    args = ap.parse_args()

    report_root = REPO / "report"
    min_rank = SEV_RANK.get(args.severity.upper(), 0)

    # Resolve architecture
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
    gt_path    = report_dir / "ground_truth.json"

    for path, label in [(moe_path, "07_moe_orchestrator.json"),
                        (gt_path, "ground_truth.json")]:
        if not path.exists():
            print(red(f"Missing: {path}"), file=sys.stderr)
            print(dim(f"  Run ER on '{arch}' first: /run-er {arch}"), file=sys.stderr)
            sys.exit(1)

    moe = json.loads(moe_path.read_text())
    gt  = json.loads(gt_path.read_text())

    review_items = moe.get("consensus_recommendations", {}).get("review", [])
    review_items = [
        r for r in review_items
        if SEV_RANK.get(r.get("severity", "LOW").upper(), 0) >= min_rank
    ]

    # Sort by severity desc
    review_items.sort(key=lambda r: -SEV_RANK.get(r.get("severity", "LOW").upper(), 0))

    if not review_items:
        print(bold(f"\n  {arch}"))
        print(f"  {green('✓')} No UNSURE items at severity ≥ {args.severity}. Nothing to triage.")
        return

    print()
    print(bold(f"  UNSURE Triage — {arch}"))
    sev_label = f"severity ≥ {args.severity}" if args.severity != "LOW" else "all severities"
    print(dim(f"  {len(review_items)} item{'s' if len(review_items) != 1 else ''} · {sev_label}"))
    print(dim("  ─" * 35))
    print()

    results = []
    dismissed = real = pending = 0

    for idx, item in enumerate(review_items, 1):
        # Step 1: deterministic check
        dismiss_reason = _check_deterministic(item, gt, report_dir)

        if dismiss_reason:
            verdict = "DISMISS"
            reason  = dismiss_reason
            adr     = "None"
            dismissed += 1
        elif args.dry_run:
            verdict = "PENDING"
            reason  = "(dry-run — LLM skipped)"
            adr     = ""
            pending += 1
        else:
            # Step 2: LLM verdict
            prompt   = _build_llm_prompt(item, gt, report_dir)
            raw      = _call_llm(prompt)
            verdict  = "REAL"
            reason   = raw
            adr      = ""

            # Parse structured response
            for line in raw.splitlines():
                if line.startswith("VERDICT:"):
                    v = line.split(":", 1)[1].strip().upper()
                    verdict = "DISMISS" if "DISMISS" in v else "REAL"
                elif line.startswith("REASON:"):
                    reason = line.split(":", 1)[1].strip()
                elif line.startswith("ADR_PATCH:"):
                    adr = line.split(":", 1)[1].strip()

            if verdict == "DISMISS":
                dismissed += 1
            else:
                real += 1

        if not args.json:
            _print_item(idx, item, verdict, reason, adr, args.dry_run)

        results.append({
            "description": item.get("description"),
            "category":    item.get("category"),
            "severity":    item.get("severity"),
            "source":      item.get("source"),
            "verdict":     verdict,
            "reason":      reason,
            "adr_patch":   adr,
        })

    if args.json:
        print(json.dumps({"arch": arch, "results": results}, indent=2))
        return

    # Summary
    print(dim("  ─" * 35))
    print(f"  {green(f'✓ {dismissed} dismissed')}  "
          f"{red(f'✗ {real} real gaps') if real else dim('0 real gaps')}  "
          f"{amber(f'~ {pending} pending LLM') if pending else ''}")

    if real:
        print()
        print(amber("  Real gaps require ADR updates. Run with --dry-run removed to get ADR patches,"))
        print(amber("  or open the ER tab in the dashboard and use the re-run buttons to update critics."))
    if pending:
        print()
        print(dim(f"  Re-run without --dry-run to get LLM verdicts for {pending} item(s)."))
    print()


if __name__ == "__main__":
    main()
