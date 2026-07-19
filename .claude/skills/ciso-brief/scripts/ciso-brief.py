#!/usr/bin/env python3
"""
ciso-brief.py — CISO-ready one-page security brief.

Produces a structured visual brief: risk gauges, multi-critic-corroborated
top findings (sorted by critic breadth then severity), investment tier table
with risk-reduction bars, and a short LLM-generated narrative covering
the architect's verdict and recommended first action.

Sources: ground_truth.json + 07_moe_orchestrator.json + 08_scrum_master.json

Usage:
    python3 ciso-brief.py 21_agentic_ai_system      # single architecture
    python3 ciso-brief.py                            # most recent report
    python3 ciso-brief.py --corpus                   # all architectures, sorted by risk
    python3 ciso-brief.py --corpus --top 5           # top 5 highest-risk only
    python3 ciso-brief.py 21_agentic_ai_system --no-llm  # skip LLM narrative
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
def white(t):  return _c(t, "97")

def _bar(val, max_val=100, width=20, color_fn=None):
    filled = int(width * val / max_val)
    bar = "█" * filled + "░" * (width - filled)
    if color_fn:
        return color_fn(bar)
    if val >= 70: return green(bar)
    if val >= 40: return amber(bar)
    return red(bar)

def _risk_bar(val, width=20):
    # Risk: high val = bad, so invert the color
    filled = int(width * val / 100)
    bar = "█" * filled + "░" * (width - filled)
    if val >= 70: return red(bar)
    if val >= 40: return amber(bar)
    return green(bar)

def _conf_color(pct):
    if pct >= 85: return green
    if pct >= 70: return amber
    return red

def _interp_label(pct):
    if pct >= 90: return green("STRONG")
    if pct >= 80: return green("GOOD")
    if pct >= 70: return amber("ADEQUATE")
    if pct >= 60: return amber("NEEDS REVIEW")
    return red("ACTION REQUIRED")

# ── Critic source label ───────────────────────────────────────────────────────
CRITIC_LABELS = {
    "architect":    "Architect",
    "tester":       "Tester",
    "red_team":     "Red Team",
    "purple_team":  "Purple Team",
    "blackhat":     "Blackhat",
}

def _source_label(source: str) -> str:
    """Format source string for display. Multi-critic shown in green, single in dim."""
    parts = [CRITIC_LABELS.get(s.strip(), s.strip()) for s in source.split("+")]
    if len(parts) > 1:
        return green(" + ".join(parts))
    return dim(parts[0])

def _critic_count(source: str) -> int:
    return len(source.split("+"))

# ── Data loading ──────────────────────────────────────────────────────────────
def _load(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            pass
    return {}

def load_arch(report_dir: Path) -> dict:
    return {
        "gt":  _load(report_dir / "ground_truth.json"),
        "moe": _load(report_dir / "07_moe_orchestrator.json"),
        "sm":  _load(report_dir / "08_scrum_master.json"),
    }

# ── Finding selection: KNOWN only, multi-critic first ────────────────────────
def _top_findings(moe: dict, n: int = 5) -> list[dict]:
    """
    Select top N findings from KNOWN critical+high items only.
    Sort: multi-critic (source with "+") first, then by severity (CRITICAL > HIGH).
    UNSURE items excluded — too uncertain for CISO decision-making.
    """
    cr = moe.get("consensus_recommendations", {})
    sev_rank = {"CRITICAL": 2, "HIGH": 1}
    candidates = []
    for sev_key in ("critical", "high"):
        for r in cr.get(sev_key, []):
            if r.get("confidence_label") != "KNOWN":
                continue
            source = r.get("source", "")
            candidates.append({
                "description": r.get("description", ""),
                "recommendation": r.get("recommendation", ""),
                "severity": r.get("severity", sev_key.upper()),
                "source": source,
                "critic_count": _critic_count(source),
                "sev_rank": sev_rank.get(r.get("severity", "").upper(), 0),
            })
    # Sort: multi-critic first, then severity
    candidates.sort(key=lambda x: (-x["critic_count"], -x["sev_rank"]))
    return candidates[:n]

# ── LLM narrative ─────────────────────────────────────────────────────────────
def _generate_narrative(data: dict) -> tuple[str, str]:
    """
    Returns (verdict_sentence, action_sentence) from the LLM.
    Both are kept to ≤2 sentences each — tight, board-ready language.
    """
    try:
        from agentic.llm_client import LLMClient
        client = LLMClient()

        gt  = data["gt"]
        moe = data["moe"]
        sm  = data["sm"]
        arch = data["arch"]

        risk     = gt.get("expected_risk_score", 0)
        defence  = gt.get("expected_defensibility", 0)
        conf     = (moe.get("confidence") or {}).get("final", 0)
        redesign = sm.get("redesign_signal", False)
        n_paths  = len(gt.get("expected_attack_paths", []))

        top = _top_findings(moe, n=3)
        top_desc = "; ".join(f["description"][:80] for f in top[:2])

        io = moe.get("improvement_options", {})
        qw = io.get("quick_wins", {})
        rec = io.get("recommended", {})

        crit_actions = [
            a.get("action", "")[:80]
            for a in sm.get("action_plan", [])
            if a.get("priority") == "critical" and not a.get("is_antipattern")
        ][:2]

        prompt = f"""You are a security advisor writing a CISO brief for {arch}.

Architecture facts:
- Attack risk score: {risk}/100 (higher = more exposed)
- Defensibility: {defence}/100
- Expert review confidence: {conf:.1f}% ({_interp_label(conf).replace(chr(27)+'['+str(92)+'m','').replace(chr(27)+'[0m','')})
- Attack paths: {n_paths}
- Redesign signal: {redesign}
- Top confirmed findings: {top_desc}
- Quick Win: {qw.get('cost','?')} / {qw.get('effort','?')} → {qw.get('risk_reduction','?')}
- Recommended: {rec.get('cost','?')} / {rec.get('effort','?')} → {rec.get('risk_reduction','?')}
- Critical SM actions: {'; '.join(crit_actions)}

Write exactly two outputs, each one sentence, separated by a newline:
1. VERDICT: One sentence describing the current security posture and the single biggest structural risk. No jargon. Board-level language. State the concrete consequence if unaddressed.
2. ACTION: One sentence naming the single most important first step and why it addresses the top risk. Be specific about what, where, and expected outcome. No semicolons.

No headers, no bullet points, just the two sentences."""

        resp = client.generate(prompt, max_tokens=200, temperature=0.2)
        lines = [l.strip() for l in (resp.content or "").strip().splitlines() if l.strip()]
        # Strip any "VERDICT:"/"ACTION:" prefixes the LLM might add
        lines = [re.sub(r"^(VERDICT|ACTION)\s*:\s*", "", l, flags=re.I) for l in lines]
        verdict = lines[0] if lines else ""
        action  = lines[1] if len(lines) > 1 else ""
        return verdict, action
    except Exception as e:
        return f"[LLM unavailable: {e}]", ""


# ── Single-arch brief printer ─────────────────────────────────────────────────
def print_brief(arch: str, data: dict, use_llm: bool = True, compact: bool = False) -> dict:
    gt  = data["gt"]
    moe = data["moe"]
    sm  = data["sm"]

    risk    = gt.get("expected_risk_score", 0)
    defence = gt.get("expected_defensibility", 0)
    n_paths = len(gt.get("expected_attack_paths", []))
    n_tech  = len({t for ap in gt.get("expected_attack_paths", [])
                   for t in ap.get("techniques", [])})

    conf_data = moe.get("confidence") or {}
    conf      = conf_data.get("final") or 0
    interp    = conf_data.get("interpretation", "")

    io  = moe.get("improvement_options", {})
    qw  = io.get("quick_wins",  {})
    rec = io.get("recommended", {})
    mx  = io.get("maximum",     {})

    cr           = moe.get("consensus_recommendations", {})
    known_crit   = [r for r in cr.get("critical", []) if r.get("confidence_label") == "KNOWN"]
    known_high   = [r for r in cr.get("critical", []) + cr.get("high", [])
                    if r.get("confidence_label") == "KNOWN"]
    unsure_count = len(cr.get("review", []))

    redesign    = sm.get("redesign_signal", False)
    sm_conf     = sm.get("final_confidence", 0)
    has_sm      = bool(sm)

    top_findings = _top_findings(moe, n=5)

    W = 60  # box width

    # ── Header ───────────────────────────────────────────────────────────────
    date_str = ""
    try:
        import datetime
        date_str = datetime.date.today().isoformat()
    except Exception:
        pass

    print()
    print("┌" + "─" * W + "┐")
    title = f"  CISO BRIEF — {arch}"
    print("│" + bold(title) + " " * (W - len(title)) + "│")
    subtitle = f"  {date_str}   Confidence: {conf:.1f}%  {_interp_label(conf)}"
    # strip ANSI for length calc
    sub_clean = re.sub(r'\033\[[^m]*m', '', subtitle)
    print("│" + subtitle + " " * max(0, W - len(sub_clean)) + "│")
    print("└" + "─" * W + "┘")

    # ── Risk at a glance ─────────────────────────────────────────────────────
    print()
    print(bold("  RISK AT A GLANCE"))
    conf_c = _conf_color(conf)
    print(f"  Confidence    {conf:.1f}%  {_bar(conf, color_fn=conf_c)}  {_interp_label(conf)}")
    print(f"  Attack risk   {risk:>3}/100  {_risk_bar(risk)}  {'HIGH EXPOSURE' if risk >= 70 else 'MEDIUM' if risk >= 40 else 'MANAGED'}")
    print(f"  Defensibility {defence:>3}/100  {_bar(defence)}  {'STRONG' if defence >= 70 else 'PARTIAL' if defence >= 40 else 'WEAK'}")
    print(f"  Attack paths  {n_paths}   ({len(known_crit)} critical confirmed by reviewers · {n_tech} techniques)")
    if redesign:
        print(f"  {red('⚠ REDESIGN SIGNAL')}  Architecture changes required — controls alone cannot close all gaps")

    # ── Top findings (multi-critic first) ────────────────────────────────────
    print()
    multi = [f for f in top_findings if f["critic_count"] > 1]
    single = [f for f in top_findings if f["critic_count"] == 1]
    label_suffix = f"  ({len(multi)} multi-critic · {len(single)} single-critic confirmed)"
    print(bold(f"  TOP FINDINGS — KNOWN CONFIRMED{label_suffix}"))
    print(f"  {dim('Sorted by: critic breadth (multi-critic first) then severity')}")
    print()

    for i, f in enumerate(top_findings, 1):
        sev = f["severity"].upper()
        sev_c = red if sev == "CRITICAL" else amber
        desc = f["description"]
        # Trim at first sentence
        m = re.match(r"^(.{20,}?[.!?])(?:\s|$)", desc)
        desc_short = m.group(1) if m else desc[:110]
        rec_text = f["recommendation"]
        rec_m = re.match(r"^(.{20,}?[.!?])(?:\s|$)", rec_text)
        rec_short = rec_m.group(1) if rec_m else rec_text[:90]

        print(f"  {dim(str(i) + '.')} {sev_c(sev):<10}  [{_source_label(f['source'])}]")
        print(f"     {desc_short}")
        if rec_short:
            print(f"     {dim('→')} {dim(rec_short)}")
        print()

    if unsure_count:
        print(f"  {amber(f'{unsure_count} UNSURE')} items excluded — run {cyan('/review-unsure ' + arch)} to triage")
        print()

    # ── Investment options ────────────────────────────────────────────────────
    def _tier_row(label, tier: dict, width=10):
        if not tier:
            return
        cost    = tier.get("cost", "—")
        effort  = tier.get("effort", "—")
        rr_raw  = tier.get("risk_reduction", "")
        verdict = (tier.get("practical_verdict") or "").split("—")[0].strip()
        # Parse risk_reduction for the bar: e.g. "50.2 → ~28 (estimated 44%...)"
        nums = re.findall(r"[\d.]+", rr_raw)
        try:
            before_r, after_r = float(nums[0]), float(nums[1])
            pct_red = round((before_r - after_r) / before_r * 100)
            bar_len = 12
            after_bar = int(bar_len * after_r / before_r)
            bar = red("█" * after_bar) + green("░" * (bar_len - after_bar))
            risk_str = f"{int(before_r)} → {int(after_r)}  {bar}  −{pct_red}%"
        except Exception:
            risk_str = rr_raw[:40] if rr_raw else "—"
        verdict_str = f"  [{amber(verdict[:8])}]" if verdict else ""
        print(f"  {bold(label):<16}  {cost:<14}  {effort:<12}  {risk_str}{verdict_str}")

    print(bold("  INVESTMENT OPTIONS"))
    print(f"  {'Tier':<16}  {'Cost':<14}  {'Effort':<12}  {'Risk score after controls'}")
    print(f"  {'─'*16}  {'─'*14}  {'─'*12}  {'─'*30}")
    _tier_row("Quick Win",   qw)
    _tier_row("Recommended", rec)
    _tier_row("Maximum",     mx)
    print()

    # ── LLM narrative ────────────────────────────────────────────────────────
    if use_llm and moe:
        verdict_txt, action_txt = _generate_narrative({"arch": arch, **data})
        if verdict_txt or action_txt:
            print(bold("  ASSESSMENT"))
            if verdict_txt:
                print(f"  {verdict_txt}")
            if action_txt:
                print()
                print(bold("  RECOMMENDED FIRST ACTION"))
                print(f"  {action_txt}")
            print()

    # ── Footer ───────────────────────────────────────────────────────────────
    print("  " + dim("─" * (W - 2)))
    has_moe_str = f"ER confidence: {conf:.0f}%  " if moe else "No ER run  "
    sm_str      = f"SM: {'redesign' if redesign else 'OK'}  " if has_sm else "No SM  "
    unsure_str  = f"{unsure_count} UNSURE pending  " if unsure_count else ""
    print(f"  {dim(has_moe_str + sm_str + unsure_str)}")
    print()

    return {
        "arch": arch, "risk": risk, "defensibility": defence,
        "confidence": conf, "redesign": redesign,
        "known_critical": len(known_crit), "known_high": len(known_high),
        "unsure": unsure_count, "has_sm": has_sm,
    }


# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    ap = argparse.ArgumentParser(description="CISO security brief")
    ap.add_argument("arch",    nargs="?", help="Architecture name")
    ap.add_argument("--corpus",action="store_true", help="Run on all architectures")
    ap.add_argument("--top",   type=int, default=0, help="Corpus mode: show top N by risk score")
    ap.add_argument("--no-llm",action="store_true", help="Skip LLM narrative")
    args = ap.parse_args()

    report_root = REPO / "report"
    use_llm = not args.no_llm

    if args.corpus:
        dirs = sorted(
            [d for d in report_root.iterdir() if d.is_dir()
             and (d / "ground_truth.json").exists()],
            key=lambda d: d.name
        )
        results = []
        for d in dirs:
            data = load_arch(d)
            if not data["gt"]:
                continue
            r = print_brief(d.name, data, use_llm=use_llm, compact=True)
            results.append(r)

        # Corpus summary at the end
        if results:
            results.sort(key=lambda x: -x["risk"])
            if args.top:
                results = results[:args.top]
            print(bold(f"\n  CORPUS SUMMARY — {len(results)} architectures"))
            print(f"  {'Architecture':<35}  {'Risk':>4}  {'Conf':>5}  {'KNOWN Crit':>10}  {'Status'}")
            print(f"  {'─'*35}  {'─'*4}  {'─'*5}  {'─'*10}  {'─'*14}")
            for r in results:
                risk_c = red if r["risk"] >= 70 else amber if r["risk"] >= 40 else green
                conf_c = _conf_color(r["confidence"])
                redesign_flag = red(" ⚠") if r["redesign"] else ""
                conf_str = conf_c(f"{r['confidence']:.0f}%")
                print(f"  {r['arch']:<35}  {risk_c(str(r['risk'])):>4}  "
                      f"{conf_str}  "
                      f"{r['known_critical']:>10}  "
                      f"{_interp_label(r['confidence'])}{redesign_flag}")
            print()
    else:
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
        if not report_dir.exists():
            print(red(f"No report directory for '{arch}'"), file=sys.stderr)
            sys.exit(1)

        data = load_arch(report_dir)
        if not data["gt"]:
            print(red(f"No ground_truth.json for '{arch}'"), file=sys.stderr)
            sys.exit(1)

        print_brief(arch, data, use_llm=use_llm)


if __name__ == "__main__":
    main()
