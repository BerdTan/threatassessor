#!/usr/bin/env python3
"""
critic_improve_loop.py — Score, prioritise, and track the critic self-improvement loop.

Modes:
  --score-only          Print priority table from latest bench run (or trigger one)
  --compare A B         Compare two bench run IDs; print delta + keep/revert verdicts
  --sm-lever <arch>     Diagnose SM's lever type (coverage vs completeness/breadth)

Usage:
  python3 .claude/skills/critic-improve-loop/scripts/critic_improve_loop.py \
      --arch 22_generic_ai_nodes --score-only

  python3 .claude/skills/critic-improve-loop/scripts/critic_improve_loop.py \
      --arch 22_generic_ai_nodes --compare 20260822_163006 20260823_090000
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
BENCH_RESULTS = ROOT / "bench_results"
REPORT_BASE   = ROOT / "report"

CRITIC_NAMES = ["architect", "tester", "red_team", "purple_team", "blackhat", "scrum_master"]
TARGET_DEFAULT = 11.5
MIN_DELTA      = 0.5   # minimum improvement to keep a rewrite

# Tie-break order (lower = higher priority when gap is equal)
PRIORITY_ORDER = {
    "red_team":    0,
    "blackhat":    1,
    "architect":   2,
    "tester":      3,
    "purple_team": 4,
    "scrum_master": 5,
}

ANSI = {
    "red":    "\033[91m",
    "yellow": "\033[93m",
    "green":  "\033[92m",
    "cyan":   "\033[96m",
    "dim":    "\033[2m",
    "bold":   "\033[1m",
    "reset":  "\033[0m",
}

def c(text: str, colour: str) -> str:
    return f"{ANSI[colour]}{text}{ANSI['reset']}"


# ── Bench summary helpers ─────────────────────────────────────────────────────

def _latest_summary(arch: str) -> tuple[str, dict] | tuple[None, None]:
    """Return (run_id, summary_dict) for the most recent complete bench run."""
    candidates = []
    for run_dir in sorted(BENCH_RESULTS.iterdir(), reverse=True):
        s = run_dir / "bench_summary.json"
        if not s.exists():
            continue
        try:
            data = json.loads(s.read_text())
        except Exception:
            continue
        if arch in data.get("archs", []):
            candidates.append((run_dir.name, data))
    if not candidates:
        return None, None
    return candidates[0]


def _scores_for_arch(summary: dict, arch: str) -> dict[str, dict[str, float | None]]:
    """Return {model: {critic: score}} for the arch."""
    models  = summary.get("models", [])
    results = summary.get("results", {}).get(arch, {})
    out = {}
    for model in models:
        depth = results.get(model, {}).get("depth", {})
        out[model] = {c: depth.get(c) for c in CRITIC_NAMES}
    return out


# ── SM lever diagnosis ────────────────────────────────────────────────────────

def _sm_lever(arch: str) -> dict:
    """
    Inspect 08_scrum_master.json and return lever diagnosis:
      lever: "coverage" | "completeness" | "breadth" | "healthy"
      metrics: {coverage, completeness, has_structural, has_immediate}
    """
    sm_path = REPORT_BASE / arch / "08_scrum_master.json"
    if not sm_path.exists():
        return {"lever": "unknown", "reason": "08_scrum_master.json not found"}

    sm = json.loads(sm_path.read_text())
    ap   = sm.get("action_plan", [])
    imps = sm.get("impediments_found", [])
    n_imp = max(1, len(imps))

    coverage    = len(ap) / n_imp
    tiers       = {(a.get("tier") or "").lower() for a in ap}
    has_struct  = "structural" in tiers
    has_immed   = "immediate" in tiers
    first_steps = sum(1 for a in ap if a.get("first_step", "").strip())
    completeness = first_steps / len(ap) if ap else 0.0

    if coverage < 0.6:
        lever  = "coverage"
        reason = (f"Only {len(ap)}/{len(imps)} impediments have action items "
                  f"({coverage:.0%}) — harmony branch exits early; code fix needed")
    elif not (has_struct and has_immed):
        lever  = "breadth"
        missing = "structural" if not has_struct else "immediate"
        reason = f"Tier '{missing}' missing from action plan — prompt fix for _formulate_proposals"
    elif completeness < 0.7:
        lever  = "completeness"
        reason = (f"Only {first_steps}/{len(ap)} action items have first_step "
                  f"({completeness:.0%}) — prompt fix for proposal specificity")
    else:
        lever  = "healthy"
        reason = "Coverage, breadth, and completeness all pass — target acceptance criteria next"

    return {
        "lever":        lever,
        "reason":       reason,
        "coverage":     round(coverage, 2),
        "completeness": round(completeness, 2),
        "has_structural": has_struct,
        "has_immediate":  has_immed,
        "action_items":   len(ap),
        "impediments":    len(imps),
    }


# ── Priority table ────────────────────────────────────────────────────────────

IMPROVE_HINTS = {
    "architect": [
        (10.0, "Deepen trust boundary + data flow threat enumeration"),
        (8.0,  "Add lateral trust violations + privilege boundary failures"),
        (0.0,  "Full trust model missing — add attack surface + data flows"),
    ],
    "tester": [
        (10.0, "Add negative test cases + dependency trust scenarios"),
        (8.0,  "Cover auth edge cases, race conditions, input validation"),
        (0.0,  "MITRE mappings unverified — add test coverage per TTP"),
    ],
    "red_team": [
        (10.0, "Extend post-exploit scenarios + multi-hop chains"),
        (8.0,  "Add privilege escalation + lateral movement depth"),
        (0.0,  "Attack paths sparse — expand adversarial TTP coverage"),
    ],
    "purple_team": [
        (10.0, "Strengthen correlation rules + threat hunt playbooks"),
        (8.0,  "Map D3FEND mitigations + close detection gaps"),
        (0.0,  "Detection parity weak — map TTPs to detection controls"),
    ],
    "blackhat": [
        (10.0, "Add zero-day analogues + advanced persistence vectors"),
        (8.0,  "Explore supply chain + insider threat scenarios"),
        (0.0,  "Novel vectors missing — add unconventional attack paths"),
    ],
    "scrum_master": [
        (10.0, "Tighten first_step specificity + add acceptance criteria"),
        (8.0,  "Ensure both structural + immediate tiers present in plan"),
        (0.0,  "Action plan coverage low — more impediments need plan items"),
    ],
}


def _hint(critic: str, score: float | None) -> str:
    if score is None:
        return "no score"
    bands = IMPROVE_HINTS.get(critic, [])
    for threshold, msg in bands:
        if score >= threshold:
            return msg
    return ""


def _lever_for(critic: str, score: float | None, arch: str) -> str:
    if critic != "scrum_master":
        return "prompt"
    if score is None:
        return "unknown"
    diag = _sm_lever(arch)
    lever = diag.get("lever", "unknown")
    return "code⚠" if lever == "coverage" else "prompt"


def print_priority_table(arch: str, scores: dict[str, float | None], target: float, run_id: str):
    """Print sorted priority table for one model's scores."""
    rows = []
    for critic in CRITIC_NAMES:
        score = scores.get(critic)
        gap   = round(target - score, 1) if score is not None else None
        lever = _lever_for(critic, score, arch)
        hint  = _hint(critic, score)
        rows.append((critic, score, gap, lever, hint))

    # Sort: passing critics last, then by gap desc, tie-break by PRIORITY_ORDER
    rows.sort(key=lambda r: (
        r[2] is None or r[2] <= 0,          # passing → to end
        -(r[2] or 0),                         # larger gap first
        PRIORITY_ORDER.get(r[0], 9),          # tie-break
    ))

    print(f"\n{c('Critic Priority Table', 'bold')} — arch: {c(arch, 'cyan')}  run: {c(run_id, 'dim')}  target: {target}/12\n")
    header = f"{'#':<3} {'Critic':<14} {'Score':>7} {'Gap':>6} {'Lever':<9} Hint"
    print(c(header, "dim"))
    print(c("─" * 80, "dim"))

    for i, (critic, score, gap, lever, hint) in enumerate(rows, 1):
        score_str = f"{score:.1f}/12" if score is not None else "  —   "
        gap_str   = f"-{gap:.1f}" if gap and gap > 0 else "pass"

        if gap is None or gap <= 0:
            score_col = c(score_str, "green")
            gap_col   = c(gap_str,   "green")
        elif gap >= 3:
            score_col = c(score_str, "red")
            gap_col   = c(gap_str,   "red")
        else:
            score_col = c(score_str, "yellow")
            gap_col   = c(gap_str,   "yellow")

        lever_col = c(lever, "red") if "⚠" in lever else c(lever, "dim")
        hint_col  = c(hint[:45], "dim")
        rank = c(f"{i}.", "dim") if (gap is None or gap <= 0) else f"{i}."

        print(f"{rank:<3} {critic:<14} {score_col:>7} {gap_col:>6}  {lever_col:<9} {hint_col}")

    passing = sum(1 for _, _, gap, _, _ in rows if gap is not None and gap <= 0)
    total   = len(rows)
    print(c("─" * 80, "dim"))
    print(f"  {passing}/{total} critics at target. "
          f"{total - passing} need work.\n")

    # SM detailed diagnosis if SM is in the improve list
    sm_row = next((r for r in rows if r[0] == "scrum_master" and (r[2] or 0) > 0), None)
    if sm_row:
        diag = _sm_lever(arch)
        print(c("  SM diagnosis:", "bold"))
        for k, v in diag.items():
            print(f"    {k:<16} {v}")
        print()


# ── Delta comparison ──────────────────────────────────────────────────────────

def compare_runs(arch: str, run_a: str, run_b: str, target: float):
    def load(run_id: str) -> dict[str, float | None]:
        s = BENCH_RESULTS / run_id / "bench_summary.json"
        if not s.exists():
            print(f"Run not found: {run_id}", file=sys.stderr)
            sys.exit(1)
        data  = json.loads(s.read_text())
        model = (data.get("models") or ["current"])[0]
        depth = data.get("results", {}).get(arch, {}).get(model, {}).get("depth", {})
        return {c: depth.get(c) for c in CRITIC_NAMES}

    before = load(run_a)
    after  = load(run_b)

    print(f"\n{c('Improvement Delta', 'bold')} — arch: {c(arch, 'cyan')}")
    print(f"  Before: {c(run_a, 'dim')}  →  After: {c(run_b, 'dim')}\n")
    header = f"{'Critic':<14} {'Before':>7} {'After':>7} {'Delta':>7} {'Verdict'}"
    print(c(header, "dim"))
    print(c("─" * 55, "dim"))

    any_revert = False
    for critic in CRITIC_NAMES:
        b = before.get(critic)
        a = after.get(critic)
        delta = round(a - b, 1) if (a is not None and b is not None) else None
        b_str = f"{b:.1f}" if b is not None else " —"
        a_str = f"{a:.1f}" if a is not None else " —"
        d_str = (f"+{delta:.1f}" if delta and delta >= 0 else f"{delta:.1f}") if delta is not None else " —"

        if delta is None:
            verdict = c("no data", "dim")
        elif delta >= MIN_DELTA:
            verdict = c("✓ keep", "green")
        elif delta > 0:
            verdict = c(f"↑ {delta:.1f} (below threshold — revert)", "yellow")
            any_revert = True
        elif delta == 0:
            verdict = c("no change — revert", "dim")
            any_revert = True
        else:
            verdict = c(f"↓ regressed — revert", "red")
            any_revert = True

        delta_col = c(d_str, "green") if (delta and delta >= MIN_DELTA) else c(d_str, "yellow" if delta and delta > 0 else "red")
        print(f"  {critic:<14} {b_str:>7} {a_str:>7} {delta_col:>7}   {verdict}")

    print(c("─" * 55, "dim"))
    if any_revert:
        print(c("\n  Revert instructions for unchanged/regressed critics:", "yellow"))
        print("    git checkout HEAD -- chatbot/modules/agents/critics/<critic>_critic.py\n")
    else:
        print(c("\n  All changes kept. Ready to contribute to Brain.\n", "green"))

    return not any_revert


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Critic self-improvement loop helper")
    parser.add_argument("--arch",       required=True, help="Architecture name")
    parser.add_argument("--target",     type=float, default=TARGET_DEFAULT, help="Target score /12 (default 11.5)")
    parser.add_argument("--score-only", action="store_true", help="Print priority table from latest bench run")
    parser.add_argument("--compare",    nargs=2, metavar=("RUN_A", "RUN_B"), help="Compare two bench run IDs")
    parser.add_argument("--sm-lever",   action="store_true", help="Diagnose SM lever type for this arch")
    args = parser.parse_args()

    if args.sm_lever:
        diag = _sm_lever(args.arch)
        print(f"\nSM lever diagnosis — arch: {c(args.arch, 'cyan')}\n")
        for k, v in diag.items():
            flag = c("⚠", "red") if k == "lever" and v == "coverage" else ""
            print(f"  {k:<18} {v} {flag}")
        print()
        return

    if args.compare:
        ok = compare_runs(args.arch, args.compare[0], args.compare[1], args.target)
        sys.exit(0 if ok else 1)

    if args.score_only:
        run_id, summary = _latest_summary(args.arch)
        if summary is None:
            print(f"No bench run found for arch '{args.arch}'.")
            print(f"Run: python3 scripts/bench_critics.py --mode critics --archs {args.arch}")
            sys.exit(1)
        model_scores = _scores_for_arch(summary, args.arch)
        for model, scores in model_scores.items():
            print_priority_table(args.arch, scores, args.target, run_id)
        return

    parser.print_help()


if __name__ == "__main__":
    main()
