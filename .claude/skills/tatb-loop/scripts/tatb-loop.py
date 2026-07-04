#!/usr/bin/env python3
"""
tatb-loop.py — TATB feedback loop agent.

Observe → Diagnose → Prescribe → Gate (human approval) → Apply → Verify → Log

Usage:
    python3 tatb-loop.py                          # corpus, auto-select weakest signal
    python3 tatb-loop.py --arch 01_minimal_vulnerable_2
    python3 tatb-loop.py --target hop_pct
    python3 tatb-loop.py --diagnose-only          # show prescription, do not apply
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import textwrap
import time
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
CORPUS_SCRIPT = REPO / ".claude/skills/tatb-corpus/scripts/tatb-corpus.py"
SCORE_SCRIPT  = REPO / ".claude/skills/tatb-score/scripts/tatb-score.py"

# ─── Colour helpers ──────────────────────────────────────────────────────────

def _c(t, code): return f"\033[{code}m{t}\033[0m" if sys.stdout.isatty() else t
def bold(t):  return _c(t, "1")
def green(t): return _c(t, "92")
def amber(t): return _c(t, "33")
def red(t):   return _c(t, "31")
def grey(t):  return _c(t, "2")
def cyan(t):  return _c(t, "36")


# ─── Prescription catalogue ──────────────────────────────────────────────────
# Each entry describes one targeted fix: what signal it repairs, which file
# and what text to find/replace, and how to verify the change is already there.

def _prescriptions():
    """
    Returns a list of prescription descriptors, ordered by expected corpus impact.
    Each descriptor has:
        signal      : TATB sub-signal name (matches tatb-corpus JSON key)
        label       : human-readable name
        stage       : pipeline stage responsible
        file        : repo-relative path
        check       : string that MUST be present in file for the change to be needed
                      (if absent, change is already applied or different version)
        already_done: string that indicates the change is already in place (skip)
        old_text    : exact text to replace (or None for append)
        new_text    : replacement text
        description : plain-English explanation of why this fixes the signal
        impact      : estimated % improvement if applied to corpus
    """
    return [
        # ── hop_pct: exhaustive_mitigation_mapper _infer_dir_category keyword expansion ──
        {
            "signal":      "hop_pct",
            "label":       "Hop layer coverage",
            "stage":       "ReportStage → exhaustive_mitigation_mapper._infer_dir_category",
            "file":        "chatbot/modules/exhaustive_mitigation_mapper.py",
            "check":       '"backup", "recover", "restore", "incident", "response"',
            "already_done": '"edr", "patching"',
            "old_text": (
                '    if any(kw in control_lower for kw in ["backup", "recover", "restore", '
                '"incident", "response", "rollback", "failover", "reimage", "forensic"]):\n'
                '        return "respond"'
            ),
            "new_text": (
                '    # Respond: recovery, remediation, incident response, patching (closes known vulns)\n'
                '    if any(kw in control_lower for kw in [\n'
                '        "backup", "recover", "restore", "incident", "response",\n'
                '        "rollback", "failover", "reimage", "forensic",\n'
                '        "patch", "patching", "remediat", "edr", "endpoint detection",\n'
                '        "vulnerability management", "hotfix",\n'
                '    ]):\n'
                '        return "respond"'
            ),
            "description": (
                "The respond-category keyword list is too narrow. Controls like 'edr', "
                "'patching', and 'vulnerability management' are categorised as 'prevention' "
                "instead of 'respond', so ADR hops never get a respond-layer control assigned. "
                "Adding these keywords raises hop_pct because more hops get full 4-layer coverage."
            ),
            "impact": "+15–25% hop_pct corpus average",
        },

        # ── hop_pct (isolate): expand isolate keywords ──
        {
            "signal":      "hop_pct",
            "label":       "Hop layer coverage — isolate keywords",
            "stage":       "ReportStage → exhaustive_mitigation_mapper._infer_dir_category",
            "file":        "chatbot/modules/exhaustive_mitigation_mapper.py",
            "check":       '"segment", "privilege", "rbac", "isolat"',
            "already_done": '"zero.trust", "micro.segmentation"',
            "old_text": (
                '    if any(kw in control_lower for kw in ["segment", "privilege", "rbac", '
                '"isolat", "contain", "acl", "vlan", "quarantine", "dlp", "timeout", "lockout"]):\n'
                '        return "isolate"'
            ),
            "new_text": (
                '    # Isolate: access control, segmentation, containment, zero-trust enforcement\n'
                '    if any(kw in control_lower for kw in [\n'
                '        "segment", "privilege", "rbac", "isolat", "contain",\n'
                '        "acl", "vlan", "quarantine", "dlp", "timeout", "lockout",\n'
                '        "zero trust", "zero-trust", "micro-segment", "microsegment",\n'
                '        "least privilege", "network isolation", "firewall rule",\n'
                '    ]):\n'
                '        return "isolate"'
            ),
            "description": (
                "Zero-trust and micro-segmentation controls are not matched by the isolate "
                "keywords and fall through to prevention. Adding these improves ADR hop "
                "layer coverage."
            ),
            "impact": "+5–10% hop_pct corpus average (combined with respond fix)",
        },

        # ── closure_pct: SM prompt AP-ID injection ──
        # (already applied this session — check will detect it and skip)
        {
            "signal":      "closure_pct",
            "label":       "AP plan closure",
            "stage":       "ScrumMasterStage → _build_action_plan prompt",
            "file":        "chatbot/modules/agents/critics/scrum_master_critic.py",
            "check":       '"Return the top 5 as a JSON array. For each item:\\n"',
            "already_done": "REQUIREMENT: For each CRITICAL attack path",
            "old_text":    None,  # append-only — check already_done
            "new_text":    None,
            "description": (
                "SM prompt now injects CRITICAL AP-IDs and requires each action item to "
                "reference the relevant AP-ID. Change was applied earlier this session — "
                "already in place."
            ),
            "impact": "Already applied — expected +35% closure_pct",
        },

        # ── val_pct: self_validation PLAUSIBLE prefix ──
        # (already applied this session — check will detect it and skip)
        {
            "signal":      "val_pct",
            "label":       "Validation depth",
            "stage":       "QualityStage → self_validation._validate_technique_for_path",
            "file":        "chatbot/modules/self_validation.py",
            "check":       'f"Generic match ({overlap} keywords overlap)"',
            "already_done": "[PLAUSIBLE]",
            "old_text":    None,
            "new_text":    None,
            "description": (
                "self_validation now tags heuristic matches with [PLAUSIBLE] prefix so TATB "
                "weights them at 0.5× rather than 1.0×. Change applied earlier this session."
            ),
            "impact": "Already applied — validation scoring now correctly weighted",
        },
    ]


# ─── Score runner ─────────────────────────────────────────────────────────────

def run_corpus_scores(arch: Optional[str] = None) -> dict:
    """Run tatb-corpus (or tatb-score for single arch) and return JSON scores."""
    if arch:
        cmd = [sys.executable, str(SCORE_SCRIPT), arch, "--json"]
    else:
        cmd = [sys.executable, str(CORPUS_SCRIPT), "--json"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO, timeout=120)
        data = json.loads(result.stdout)
        return data
    except Exception as e:
        print(red(f"Score run failed: {e}"), file=sys.stderr)
        if result.stderr:
            print(grey(result.stderr[:500]), file=sys.stderr)
        return {}


def extract_signal_averages(scores_data, arch: Optional[str] = None) -> dict:
    """
    Extract per-signal averages from corpus JSON (list of arch dicts)
    or single-arch JSON (one dict).
    Returns {signal_name: average_score, ...}
    """
    SUB_KEYS = {
        "hop_pct":       ("risk",   "hop_pct"),
        "closure_pct":   ("plan",   "closure_pct"),
        "val_pct":       ("ttp",    "val_pct"),
        "mitre_pct":     ("ttp",    "mitre_pct"),
        "cross_pct":     ("ttp",    "cross_pct"),
        "node_binding":  ("threat", "node_binding"),
        "tech_variety":  ("threat", "tech_variety"),
        "node_coverage": ("threat", "node_coverage"),
        "tech_cov":      ("risk",   "tech_cov"),
        "hard_pct":      ("risk",   "hard_pct"),
        "comp_pct":      ("plan",   "comp_pct"),
        "meas_pct":      ("plan",   "meas_pct"),
        "spec_pct":      ("plan",   "spec_pct"),
    }
    totals = {k: [] for k in SUB_KEYS}

    records = scores_data if isinstance(scores_data, list) else [scores_data]
    for rec in records:
        scores = rec.get("scores", rec)  # handle both corpus and single-arch shapes
        for sig, (rubric, sub) in SUB_KEYS.items():
            rubric_data = scores.get(rubric, {})
            if isinstance(rubric_data, dict):
                val = rubric_data.get(sub) or (rubric_data.get("subs") or {}).get(sub)
                if val is not None:
                    totals[sig].append(float(val))

    return {
        sig: round(sum(vals) / len(vals)) if vals else None
        for sig, vals in totals.items()
    }


# ─── Prescription engine ──────────────────────────────────────────────────────

def select_prescription(signal_avgs: dict, target: Optional[str] = None) -> Optional[dict]:
    """
    Pick the most impactful applicable prescription.
    If --target is specified, use that signal. Otherwise pick the lowest-scoring
    signal that has an applicable prescription.
    """
    prescriptions = _prescriptions()

    if target:
        candidates = [p for p in prescriptions if p["signal"] == target]
    else:
        # Sort signals by average score (lowest first), filter to those with prescriptions
        scored = [(sig, avg) for sig, avg in signal_avgs.items() if avg is not None]
        scored.sort(key=lambda x: x[1])
        ranked_signals = [s for s, _ in scored]
        candidates = []
        for sig in ranked_signals:
            for p in prescriptions:
                if p["signal"] == sig:
                    candidates.append(p)
            if candidates:
                break

    if not candidates:
        return None

    # Filter out already-applied prescriptions
    for p in candidates:
        file_path = REPO / p["file"]
        if not file_path.exists():
            continue
        content = file_path.read_text()
        if p["already_done"] in content:
            print(grey(f"  ⊘ Prescription '{p['label']}' already applied — skipping."))
            continue
        if p["check"] not in content:
            print(amber(f"  ⚠ Prescription '{p['label']}' — check text not found in {p['file']} "
                        f"(different version?). Skipping."))
            continue
        return p

    return None


def show_diff(p: dict) -> str:
    """Return a coloured unified diff string for the prescription."""
    if not p["old_text"] or not p["new_text"]:
        return grey("  (no code change — informational only)")

    old_lines = p["old_text"].splitlines()
    new_lines = p["new_text"].splitlines()
    diff_lines = []
    for line in old_lines:
        diff_lines.append(red(f"  - {line}"))
    for line in new_lines:
        diff_lines.append(green(f"  + {line}"))
    return "\n".join(diff_lines)


def apply_prescription(p: dict) -> bool:
    """Write the approved change. Returns True on success."""
    if not p["old_text"] or not p["new_text"]:
        print(grey("  Nothing to write — informational prescription."))
        return True

    file_path = REPO / p["file"]
    content = file_path.read_text()
    if p["old_text"] not in content:
        print(red(f"  ERROR: old_text not found in {p['file']} — file may have changed."))
        return False

    new_content = content.replace(p["old_text"], p["new_text"], 1)
    file_path.write_text(new_content)
    print(green(f"  ✓ Applied to {p['file']}"))
    return True


def verify_syntax(file_path: str) -> bool:
    """Check Python syntax of changed file."""
    result = subprocess.run(
        [sys.executable, "-c", f"import ast; ast.parse(open({repr(file_path)}).read()); print('OK')"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(red(f"  Syntax check FAILED: {result.stderr.strip()}"))
        return False
    return True


def log_to_decisions(p: dict, before: dict, after: dict, arch: Optional[str]):
    """Append a dated entry to docs/DECISIONS.md."""
    decisions_path = REPO / "docs/DECISIONS.md"
    if not decisions_path.exists():
        return

    date = datetime.date.today().isoformat()
    scope = f"arch={arch}" if arch else "corpus"
    before_score = before.get(p["signal"], "N/A")
    after_score  = after.get(p["signal"], "N/A")
    delta = (after_score - before_score) if (isinstance(after_score, (int, float))
                                              and isinstance(before_score, (int, float))) else "?"

    entry = f"""
## {date} — TATB loop: {p['label']}

**Signal:** `{p['signal']}` · **Stage:** {p['stage']} · **Scope:** {scope}

**Change:** {p['description']}

**Before:** `{p['signal']}` = {before_score}%
**After:**  `{p['signal']}` = {after_score}%
**Delta:**  {'+' if isinstance(delta,(int,float)) and delta >= 0 else ''}{delta}pp

**File changed:** `{p['file']}`
"""
    content = decisions_path.read_text()
    # Insert after the first "---" separator
    if "\n---\n" in content:
        idx = content.index("\n---\n") + 5
        content = content[:idx] + entry + content[idx:]
    else:
        content += entry
    decisions_path.write_text(content)
    print(green(f"  ✓ Logged to docs/DECISIONS.md"))


# ─── Main loop ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="TATB Feedback Loop Agent")
    parser.add_argument("--arch",          help="Single architecture name (default: corpus)")
    parser.add_argument("--target",        help="Target a specific signal (e.g. hop_pct)")
    parser.add_argument("--diagnose-only", action="store_true",
                        help="Show prescription without prompting to apply")
    parser.add_argument("--no-verify",     action="store_true",
                        help="Skip re-run after applying (faster, less assurance)")
    args = parser.parse_args()

    print()
    print(bold("🔄 TATB Loop Agent"))
    scope_label = f"arch: {args.arch}" if args.arch else "corpus"
    print(grey(f"   scope={scope_label}  target={args.target or 'auto'}  "
               f"diagnose_only={args.diagnose_only}"))
    print()

    # ── Phase 1: Observe ───────────────────────────────────────────────────────
    print(bold("① Observe — running TATB scorer…"))
    t0 = time.monotonic()
    scores_before = run_corpus_scores(args.arch)
    if not scores_before:
        print(red("No scores returned. Is the API server running? (./scripts/api/api_start.sh)"))
        sys.exit(1)
    signal_avgs_before = extract_signal_averages(scores_before, args.arch)
    elapsed = round(time.monotonic() - t0, 1)
    print(f"  Scored in {elapsed}s. Key signals:")
    for sig, avg in sorted(signal_avgs_before.items(), key=lambda x: (x[1] or 100)):
        if avg is None: continue
        col = green if avg >= 70 else (amber if avg >= 50 else red)
        print(f"    {sig:<22} {col(str(avg) + '%')}")
    print()

    # ── Phase 2: Diagnose ──────────────────────────────────────────────────────
    print(bold("② Diagnose — selecting prescription…"))
    prescription = select_prescription(signal_avgs_before, args.target)
    if not prescription:
        print(green("  ✓ No applicable prescriptions found — all signals at target or already fixed."))
        sys.exit(0)

    sig    = prescription["signal"]
    score  = signal_avgs_before.get(sig)
    print(f"  Target signal : {amber(sig)}  current avg = {red(str(score) + '%') if score and score < 50 else amber(str(score) + '%')}")
    print(f"  Stage         : {prescription['stage']}")
    print(f"  File          : {prescription['file']}")
    print(f"  Expected gain : {prescription['impact']}")
    print()
    print(grey(textwrap.fill(prescription["description"], width=80, initial_indent="  ",
                             subsequent_indent="  ")))
    print()

    # ── Phase 3: Prescribe ─────────────────────────────────────────────────────
    print(bold("③ Prescription (proposed change):"))
    diff_str = show_diff(prescription)
    print(diff_str)
    print()

    if args.diagnose_only:
        print(grey("  --diagnose-only: stopping before apply gate."))
        sys.exit(0)

    # ── Phase 4: Gate ──────────────────────────────────────────────────────────
    print(bold("④ Gate — human approval required"))
    print(amber("  Apply this change? [y = yes / n = no / s = skip signal] "), end="", flush=True)
    try:
        answer = input().strip().lower()
    except (EOFError, KeyboardInterrupt):
        answer = "n"

    if answer == "s":
        print(grey("  Skipped — no change made."))
        sys.exit(0)
    if answer != "y":
        print(grey("  Declined — no change made."))
        sys.exit(0)

    # ── Phase 5: Apply ─────────────────────────────────────────────────────────
    print()
    print(bold("⑤ Apply — writing change…"))
    ok = apply_prescription(prescription)
    if not ok:
        print(red("  Apply failed — no change written."))
        sys.exit(1)

    # Syntax check immediately after apply
    file_abs = str(REPO / prescription["file"])
    if not verify_syntax(file_abs):
        print(red("  Syntax check failed — reverting…"))
        subprocess.run(["git", "checkout", "--", prescription["file"]], cwd=REPO)
        print(amber("  Reverted."))
        sys.exit(1)
    print(green("  ✓ Syntax check passed"))

    if args.no_verify:
        print(grey("  --no-verify: skipping re-run."))
        sys.exit(0)

    # ── Phase 6: Verify ────────────────────────────────────────────────────────
    print()
    print(bold("⑥ Verify — re-running TATB to measure delta…"))
    print(grey("  Note: code changes only affect newly-run analyses. Re-running TATB on "
               "existing report files measures signal consistency, not analysis quality change. "
               "Run a full analysis on target architectures to see the full impact."))
    t1 = time.monotonic()
    scores_after = run_corpus_scores(args.arch)
    signal_avgs_after = extract_signal_averages(scores_after, args.arch) if scores_after else {}
    elapsed2 = round(time.monotonic() - t1, 1)
    print(f"  Verified in {elapsed2}s.")
    print()
    print(bold("  Before → After delta:"))
    for s in [sig] + [k for k in signal_avgs_before if k != sig]:
        bef = signal_avgs_before.get(s)
        aft = signal_avgs_after.get(s)
        if bef is None and aft is None: continue
        bef_s = str(bef) + "%" if bef is not None else "N/A"
        aft_s = str(aft) + "%" if aft is not None else "N/A"
        if bef is not None and aft is not None:
            d = aft - bef
            d_s = (green(f"+{d}pp") if d > 0 else (red(f"{d}pp") if d < 0 else grey("±0")))
        else:
            d_s = grey("N/A")
        marker = " ◀ target" if s == sig else ""
        print(f"    {s:<22} {bef_s:<8} → {aft_s:<8} {d_s}{marker}")
    print()

    # ── Phase 7: Log ───────────────────────────────────────────────────────────
    print(bold("⑦ Log — recording to docs/DECISIONS.md…"))
    log_to_decisions(prescription, signal_avgs_before, signal_avgs_after, args.arch)
    print()
    print(bold("Loop complete."))
    print(grey("  Next step: run a full analysis on target architectures (./demo_expert_llm.sh)"))
    print(grey("  then re-run this loop to confirm corpus-wide improvement."))
    print()


if __name__ == "__main__":
    main()
