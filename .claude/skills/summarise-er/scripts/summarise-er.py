#!/usr/bin/env python3
"""
summarise-er.py — One-page ER digest: verdict + key findings per critic,
cross-expert consensus, confidence waterfall.

Draws from: 07_moe_orchestrator.json (verdicts, gaps, confidence) +
            individual critic JSONs (04_, 05_, 06_, 06b_, 06c_).

No LLM calls — purely deterministic synthesis from existing ER data.

Usage:
    python3 summarise-er.py 21_agentic_ai_system
    python3 summarise-er.py 21_agentic_ai_system --json
    python3 summarise-er.py                          # most recent report
"""
import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))

# ── Colour helpers ────────────────────────────────────────────────────────────
def _c(t, code): return f"\033[{code}m{t}\033[0m"
def bold(t):   return _c(t, "1")
def green(t):  return _c(t, "92")
def amber(t):  return _c(t, "33")
def red(t):    return _c(t, "31")
def cyan(t):   return _c(t, "36")
def dim(t):    return _c(t, "2")
def blue(t):   return _c(t, "34")

SEV_COLOR  = {"CRITICAL": red, "HIGH": red, "MEDIUM": amber, "LOW": dim, "PASS": green}
SEV_RANK   = {"CRITICAL": 3, "HIGH": 2, "MEDIUM": 1, "LOW": 0}
CRIT_ICON  = {"architect": "🏛", "tester": "🔬", "red_team": "🎯",
              "purple_team": "🟣", "blackhat": "⚔"}
CRIT_LABEL = {"architect": "Architect", "tester": "Tester", "red_team": "Red Team",
              "purple_team": "Purple Team", "blackhat": "Blackhat"}

WORST_DIM_LABEL = {
    "threat_completeness": "threat coverage", "control_appropriateness": "control fit",
    "defense_in_depth": "defence depth", "rapids_alignment": "RAPIDS alignment",
    "diagram_completeness": "diagram completeness", "report_quality": "report quality",
    "validation_checks": "validation", "coverage_metrics": "coverage",
    "internal_consistency": "consistency", "roadmap_validation": "roadmap",
    "technique_coverage": "technique coverage", "detection_chain": "detection chain",
    "adr_tm_coherence": "ADR coherence",
    "cross_path_chain_feasibility": "chain feasibility",
    "least_resistance_path": "least-resistance path",
    "stealth_potential": "stealth", "mitigation_chain_coverage": "mitigation coverage",
}


# ── Verdict synthesis (same logic as dashboard.js) ────────────────────────────

def _first_sent(text: str, max_len: int = 120) -> str:
    """Take first complete sentence (≥25 chars before terminal punctuation)."""
    if not text:
        return ""
    m = re.match(r"^(.{25,}?[.!?])(?:\s|$)", text)
    result = m.group(1) if m else text[:max_len]
    return result.strip().rstrip(".")


def _synth_verdict(v: dict) -> str:
    """Derive a single-sentence verdict from a critic's expert_validation entry."""
    reasoning = (v.get("reasoning") or "").strip()

    # Cap to 1 tight sentence — hard cap at 120 chars
    if reasoning:
        m = re.match(r"^(.{20,}?[.!?])(?:\s|$)", reasoning)
        sent = m.group(1) if m else reasoning
        if len(sent) > 120:
            cut = sent[:120]
            last_break = max(cut.rfind(", "), cut.rfind(" — "), cut.rfind(" - "))
            sent = (cut[:last_break] if last_break > 60 else cut) + "…"
        return sent

    # No reasoning: synthesise from worst breakdown dim
    bkd  = v.get("breakdown") or {}
    gaps = v.get("gaps") or []

    worst_dim = None
    worst_pts_lost = -1
    for key, s in bkd.items():
        if isinstance(s, dict) and s.get("reasoning") and isinstance(s.get("score"), (int, float)):
            pts_lost = s.get("max", 0) - s.get("score", 0)
            if pts_lost > worst_pts_lost:
                worst_pts_lost = pts_lost
                worst_dim = (key, s)

    if worst_dim:
        label = WORST_DIM_LABEL.get(worst_dim[0], worst_dim[0].replace("_", " "))
        sent  = _first_sent(worst_dim[1]["reasoning"])
        if sent.lower().startswith(label.lower()):
            return f"{sent}."
        # If reasoning starts with "Category label: ..." strip outer prefix
        colon_idx = sent.find(": ")
        if 0 < colon_idx < 30:
            return f"{sent[colon_idx + 2:]}."
        return f"{label}: {sent}."

    # Fall back to top gap description
    top_gap = next(
        (g for g in gaps if (g.get("severity") or "").upper() in ("CRITICAL", "HIGH")),
        gaps[0] if gaps else None,
    )
    if top_gap:
        return _first_sent(top_gap.get("description") or "") + "."

    return ""


# ── Key findings extractor ────────────────────────────────────────────────────

def _top_gaps(v: dict, n: int = 2) -> list[dict]:
    """Top N gaps by severity, then first occurrence."""
    gaps = v.get("gaps") or []
    sorted_gaps = sorted(gaps, key=lambda g: -SEV_RANK.get((g.get("severity") or "").upper(), 0))
    return sorted_gaps[:n]


def _conf_bar(pct: float, width: int = 20) -> str:
    filled = int(width * pct / 100)
    bar = "█" * filled + "░" * (width - filled)
    color = green if pct >= 90 else amber if pct >= 70 else red
    return color(bar)


def _adj_label(adj: float) -> str:
    pct = round(adj * 100, 1)
    s = (f"+{pct}" if pct > 0 else str(pct)) + "%"
    return green(s) if pct >= 0 else red(s)


# ── Printer ───────────────────────────────────────────────────────────────────

def print_summary(arch: str, moe: dict, critic_files: dict) -> dict:
    ev          = moe.get("expert_validations") or {}
    conf        = moe.get("confidence") or {}
    cr          = moe.get("consensus_recommendations") or {}
    final_conf  = conf.get("final") or 0
    base_conf   = conf.get("base") or 99.5
    interp      = conf.get("interpretation") or ""
    adjustments = conf.get("adjustments") or {}

    print()
    print(bold(f"  ER Summary — {arch}"))
    interp_color = green if "PASS" in interp.upper() else amber if "REVIEW" in interp.upper() else red
    print(dim(f"  {interp_color(interp)}"))
    print()

    # ── Confidence waterfall ─────────────────────────────────────────────────
    print(bold("  Confidence waterfall"))
    print(f"  {dim('Base'):<6} {base_conf:.1f}%", end="")
    critic_order = ["architect", "tester", "red_team", "purple_team", "blackhat"]
    for key in critic_order:
        if key in adjustments:
            adj = adjustments[key]
            print(f"  →  {CRIT_LABEL[key]} {_adj_label(adj)}", end="")
    print(f"  →  {bold('Final')} {(green if final_conf >= 90 else amber if final_conf >= 70 else red)(f'{final_conf:.1f}%')}")
    print(f"  {_conf_bar(final_conf)}")
    print()

    # ── Per-critic verdicts + top findings ───────────────────────────────────
    print(bold("  Per-critic verdicts"))
    print()

    result_critics = []
    for key in critic_order:
        v = ev.get(key)
        if not v:
            continue
        icon   = CRIT_ICON.get(key, "•")
        label  = CRIT_LABEL.get(key, key)
        score  = v.get("original_score", 0)
        status = (v.get("validation_status") or "").replace("_", " ")
        adj    = adjustments.get(key, 0)
        verdict = _synth_verdict(v)
        top_findings = _top_gaps(v, n=2)

        adj_str = _adj_label(adj)
        status_col = green if "PASS" in status.upper() else amber if "MINOR" in status.upper() else red

        print(f"  {icon} {bold(label):<18} {dim(str(score) + '/100'):<10} {status_col(status):<18} {adj_str}")
        if verdict:
            print(f"    {dim('→')} {verdict}")
        for g in top_findings:
            sev = (g.get("severity") or "").upper()
            sc  = SEV_COLOR.get(sev, dim)
            desc = _first_sent(g.get("description") or "")
            rec  = _first_sent(g.get("recommendation") or "")
            print(f"    {sc('▪ ' + sev):<12} {desc}")
            if rec:
                print(f"    {dim('    →')} {dim(rec)}")
        print()
        result_critics.append({
            "critic": key, "score": score, "status": status,
            "adj": adj, "verdict": verdict,
            "top_findings": [{"sev": g.get("severity"), "desc": g.get("description"),
                              "rec": g.get("recommendation")} for g in top_findings],
        })

    # ── Cross-expert consensus ────────────────────────────────────────────────
    known_crit = [r for r in cr.get("critical", []) if r.get("confidence_label") == "KNOWN"]
    known_high = [r for r in cr.get("high", [])     if r.get("confidence_label") == "KNOWN"]
    unsure     = cr.get("review") or []

    if known_crit or known_high:
        print(bold(f"  Cross-expert consensus  ({len(known_crit)} critical · {len(known_high)} high · {len(unsure)} UNSURE)"))
        print()
        for item in (known_crit + known_high)[:5]:
            sev = (item.get("severity") or "CRITICAL").upper()
            sc  = SEV_COLOR.get(sev, dim)
            src = item.get("source") or "?"
            desc = _first_sent(item.get("description") or "")
            rec  = _first_sent(item.get("recommendation") or "")
            print(f"  {sc('▪ ' + sev):<12} [{dim(src)}]  {desc}")
            if rec:
                print(f"  {dim('            →')} {dim(rec)}")
        if len(known_crit) + len(known_high) > 5:
            print(f"  {dim(f'  … and {len(known_crit)+len(known_high)-5} more — see ER tab for full list')}")
        if unsure:
            print()
            print(f"  {amber(f'{len(unsure)} UNSURE')} items need review — run {cyan('/review-unsure ' + arch)}")
        print()

    # ── Bottom line ──────────────────────────────────────────────────────────
    print(dim("  ─" * 35))
    conf_label = "PASS" if final_conf >= 90 else "NEEDS REVIEW" if final_conf >= 70 else "ACTION REQUIRED"
    conf_col   = green if final_conf >= 90 else amber if final_conf >= 70 else red
    print(f"  {conf_col(conf_label)}")

    total_gaps = sum(len(v.get("gaps") or []) for v in ev.values())
    crit_gaps  = sum(
        sum(1 for g in (v.get("gaps") or []) if (g.get("severity") or "").upper() in ("CRITICAL", "HIGH"))
        for v in ev.values()
    )
    print(f"  {total_gaps} findings total · {red(str(crit_gaps) + ' critical/high')} · {len(known_crit + known_high)} multi-critic KNOWN")
    if unsure:
        print(f"  {len(unsure)} UNSURE → run {cyan('/review-unsure')} · {len(cr.get('resolved', []))} already resolved")
    print()

    return {
        "arch": arch, "final_confidence": final_conf, "interpretation": interp,
        "critics": result_critics,
        "known_critical": len(known_crit), "known_high": len(known_high),
        "unsure": len(unsure), "total_gaps": total_gaps, "critical_high_gaps": crit_gaps,
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="One-page ER digest")
    ap.add_argument("arch", nargs="?", help="Architecture name")
    ap.add_argument("--json", action="store_true", help="Output as JSON")
    args = ap.parse_args()

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

    if not moe_path.exists():
        print(red(f"Missing: {moe_path}"), file=sys.stderr)
        print(dim(f"  Run /run-er {arch} first."), file=sys.stderr)
        sys.exit(1)

    moe = json.loads(moe_path.read_text())

    # Load individual critic files for richer data if needed
    critic_files = {}
    for fname in ["04_architect_critique.json", "05_tester_critique.json",
                  "06_red_team_critique.json", "06b_purple_team_critique.json",
                  "06c_blackhat_critique.json"]:
        p = report_dir / fname
        if p.exists():
            critic_files[fname.split("_")[1].split(".")[0]] = json.loads(p.read_text())

    result = print_summary(arch, moe, critic_files)

    if args.json:
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
