#!/usr/bin/env python3
"""
critic-gym — MoE critic system prompt auditor.

Reads each critic's system prompt, scores it on 6 dimensions,
diagnoses weak spots, and proposes targeted rewrites with human approval.
"""

import argparse
import ast
import re
import sys
import textwrap
from pathlib import Path
from typing import Optional

# ── Paths ────────────────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parents[4]
CRITICS_DIR = ROOT / "chatbot" / "modules" / "agents" / "critics"

CRITIC_FILES = {
    "architect":    CRITICS_DIR / "architect_critic.py",
    "tester":       CRITICS_DIR / "tester_critic.py",
    "red_team":     CRITICS_DIR / "red_teamer_critic.py",
    "purple_team":  CRITICS_DIR / "purple_teamer_critic.py",
    "blackhat":     CRITICS_DIR / "blackhat_critic.py",
    "scrum_master": CRITICS_DIR / "scrum_master_critic.py",
}

# ── Terminal helpers ─────────────────────────────────────────────────────────

def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m"

BOLD  = lambda t: _c("1", t)
RED   = lambda t: _c("31", t)
YLW   = lambda t: _c("33", t)
GRN   = lambda t: _c("32", t)
CYAN  = lambda t: _c("36", t)
DIM   = lambda t: _c("2", t)

# ── Prompt extraction ────────────────────────────────────────────────────────

def _extract_prompt(path: Path) -> Optional[str]:
    """Extract the primary system prompt text from a critic file."""
    if not path.exists():
        return None
    src = path.read_text()
    tq = '"""'  # triple-quote — kept as variable to avoid terminating this docstring

    # 1. Module-level constant: CRITIC_SYSTEM_PROMPT = """..."""
    m = re.search(
        r'[A-Z_]+_SYSTEM_PROMPT\s*=\s*' + re.escape(tq) + r'(.*?)' + re.escape(tq),
        src, re.DOTALL
    )
    if m:
        return m.group(1).strip()

    # 2. return """...""" inside _create_system_prompt / _build_system_prompt
    m = re.search(
        r'def\s+(?:_create_system_prompt|_build_system_prompt)\s*\([^)]*\).*?'
        r'return\s*' + re.escape(tq) + r'(.*?)' + re.escape(tq),
        src, re.DOTALL
    )
    if m:
        return m.group(1).strip()

    # 3. return f"""You are ... """ (f-string)
    m = re.search(
        r'return\s+f' + re.escape(tq) + r'(You are.*?)' + re.escape(tq),
        src, re.DOTALL
    )
    if m:
        return m.group(1).strip()

    # 4. Single-quoted multi-line string in return (...) block — purple/blackhat style:
    #    return (
    #        "You are a Purple Team assessor..."
    #        " continuation..."
    #    )
    m = re.search(
        r'return\s*\(\s*("You are.*?"(?:\s*"[^"]*?")*)\s*\)',
        src, re.DOTALL
    )
    if m:
        # Join the string fragments
        parts = re.findall(r'"(.*?)"', m.group(1), re.DOTALL)
        joined = " ".join(parts)
        if len(joined) > 100:
            return joined.strip()

    # 5. Fallback: first large triple-quoted block containing "You are"
    for m in re.finditer(re.escape(tq) + r'(.*?)' + re.escape(tq), src, re.DOTALL):
        t = m.group(1).strip()
        if "You are" in t and len(t) > 200:
            return t

    # 6. Last resort: collect all "You are..." single-quoted strings > 200 chars total
    all_sq = re.findall(r'"(You are[^"]{50,})"', src, re.DOTALL)
    if all_sq:
        return max(all_sq, key=len).strip()

    return None


# ── Scoring rubric ───────────────────────────────────────────────────────────

DIMENSIONS = [
    (
        "role_specificity",
        "Role specificity",
        "Is the critic's unique angle clearly stated? Could another critic be confused for this one?",
        [
            ("You are", "Prompt opens with role statement"),
            (r"(NOT|do not|don't|avoid).{0,60}(overlap|duplicate|cover|handle)", "Explicitly separates from other critics"),
        ],
    ),
    (
        "rubric_clarity",
        "Rubric clarity",
        "Are scoring bands defined with concrete examples (not just 'high/medium/low')?",
        [
            (r"(\d+\s*(point|pts|/\s*\d+)|\d+[-–]\d+\s*[:=]\s*\w+|\d+[-–]\d+.*GOOD|EXCELLENT|POOR|CRITICAL|defense)",
             "Numeric scoring bands present"),
            (r"(example|e\.g\.|for instance|such as|GOOD:|BAD:|Example:).{0,200}"
             r"(finding|gap|issue|control|attacker|bypass|technique|node|path)",
             "Concrete examples in rubric"),
        ],
    ),
    (
        "output_schema",
        "Output schema",
        "Is the expected JSON shape fully specified with field names?",
        [
            (r'(json|JSON|Return valid|OUTPUT FORMAT|output format|response format)',
             "JSON output mentioned"),
            (r'"[a-z_]{3,30}"\s*:', "Field names specified in prompt"),
        ],
    ),
    (
        "adversarial_edge",
        "Adversarial edge cases",
        "Does the prompt tell the model what a weak or misleading finding looks like?",
        [
            (r"(weak|thin|vague|generic|superficial|boilerplate|incorrect|wrong|error|hallucin)"
             r".{0,80}(finding|gap|issue|result|mapping|claim|fact)",
             "Describes weak or incorrect findings"),
            (r"(penali[sz]e|avoid|reject|flag|report|note|do not).{0,80}"
             r"(generic|vague|boilerplate|superficial|hallucin|incorrect|wrong|missing)",
             "Instructs to flag or penalise weak output"),
        ],
    ),
    (
        "separation",
        "Critic separation",
        "Does the prompt say what this critic does NOT cover?",
        [
            (r"(NOT\s+YOURS|NOT YOUR|not yours|❌|outside|beyond|scope|do not cover|doesn'?t cover)"
             r".{0,120}(this|your|critic|role|review|cover)",
             "Explicit scope exclusion"),
            (r"(leave|defer|pass|that is|that'?s|belongs? to|owned? by).{0,80}"
             r"(other|another|separate|Red Team|Purple|Architect|Tester|Blackhat|ScrumMaster|critic|reviewer)",
             "Defers out-of-scope items to named critic"),
        ],
    ),
    (
        "actionability",
        "Actionability",
        "Do findings include enough detail for a sprint ticket?",
        [
            (r"(sprint|ticket|story|action|task|remediat|mitigat|hardening|recommendation|improvement_roadmap)"
             r".{0,80}(item|step|recommendation|task|action)",
             "Sprint/action framing"),
            (r"(specific|concrete|exact|precise|name the|names the|cite|citing|specific control|specific node|"
             r"sprint.ready|engineer.can act|act immediately).{0,100}",
             "Specificity requirement stated"),
        ],
    ),
]


def _score_dimension(prompt: str, patterns: list) -> int:
    """0 = both missing, 1 = one present, 2 = both present."""
    hits = 0
    for pat, _ in patterns:
        if re.search(pat, prompt, re.IGNORECASE | re.DOTALL):
            hits += 1
    return min(hits, 2)


def _audit_prompt(name: str, prompt: str) -> dict:
    scores = {}
    for dim_id, dim_label, dim_desc, patterns in DIMENSIONS:
        score = _score_dimension(prompt, patterns)
        hits = [desc for pat, desc in patterns if re.search(pat, prompt, re.IGNORECASE | re.DOTALL)]
        missing = [desc for pat, desc in patterns if not re.search(pat, prompt, re.IGNORECASE | re.DOTALL)]
        scores[dim_id] = {
            "label": dim_label,
            "desc": dim_desc,
            "score": score,
            "hits": hits,
            "missing": missing,
        }
    total = sum(d["score"] for d in scores.values())
    grade = "HEALTHY" if total >= 10 else ("TARGETED FIX" if total >= 7 else "REWRITE")
    return {"name": name, "total": total, "grade": grade, "dimensions": scores}


# ── Display ──────────────────────────────────────────────────────────────────

def _print_audit(result: dict, verbose: bool = True):
    name = result["name"]
    total = result["total"]
    grade = result["grade"]
    grade_col = GRN if grade == "HEALTHY" else (YLW if grade == "TARGETED FIX" else RED)

    print(f"\n{BOLD(CYAN(name.upper()))}  {grade_col(grade)}  {total}/12")
    print("─" * 50)

    if not verbose:
        return

    for dim_id, dim in result["dimensions"].items():
        score = dim["score"]
        col = GRN if score == 2 else (YLW if score == 1 else RED)
        bar = "██" if score == 2 else ("█░" if score == 1 else "░░")
        print(f"  {col(bar)} {dim['label']:<25} {score}/2")
        if dim["missing"] and score < 2:
            for m in dim["missing"]:
                print(f"       {DIM('✗')} {DIM(m)}")


def _print_summary_table(results: list):
    print(f"\n{BOLD('── Critic Gym Summary ──────────────────────────────')}")
    print(f"  {'Critic':<16} {'Score':>5}  {'Grade'}")
    print("  " + "─" * 40)
    for r in results:
        grade_col = GRN if r["grade"] == "HEALTHY" else (YLW if r["grade"] == "TARGETED FIX" else RED)
        print(f"  {r['name']:<16} {r['total']:>4}/12  {grade_col(r['grade'])}")
    avg = sum(r["total"] for r in results) / len(results)
    print(f"\n  {'Average':<16} {avg:>4.1f}/12")


# ── Diagnosis ────────────────────────────────────────────────────────────────

def _diagnose(result: dict) -> list:
    """Return list of (dimension, diagnosis, suggestion) for weak dimensions."""
    diagnoses = []
    for dim_id, dim in result["dimensions"].items():
        if dim["score"] < 2:
            for missing_desc in dim["missing"]:
                suggestion = _SUGGESTIONS.get(dim_id, {}).get(missing_desc, "Add explicit guidance for this dimension.")
                diagnoses.append((dim["label"], missing_desc, suggestion))
    return diagnoses


_SUGGESTIONS = {
    "role_specificity": {
        "Explicitly separates from other critics": (
            'Add a "SCOPE EXCLUSIONS" section: "Do NOT cover X — that is the [other critic]\'s domain."'
        ),
    },
    "rubric_clarity": {
        "Concrete examples in rubric": (
            'Add at least one example: "A strong finding states X. A weak finding says only Y."'
        ),
    },
    "output_schema": {
        "JSON output mentioned": "Add an OUTPUT FORMAT section specifying the JSON shape.",
        "Field names specified in prompt": 'List each field: "findings: [{title, severity, evidence, recommendation}]"',
    },
    "adversarial_edge": {
        "Describes weak findings": (
            'Add: "Penalise findings that are generic (e.g. \'improve logging\') without citing specific nodes or techniques."'
        ),
        "Instructs to penalise weak output": (
            'Add: "A finding without a specific architecture node, MITRE technique, or control reference scores 0 on evidence."'
        ),
    },
    "separation": {
        "Explicit scope exclusion": (
            'Add: "This review covers X only. Do not duplicate findings that belong to the [Y] critic."'
        ),
        "Defers out-of-scope items": (
            'Add: "If you identify an issue outside your rubric, note it as \'out of scope for this review\' rather than scoring it."'
        ),
    },
    "actionability": {
        "Sprint/action framing": (
            'Add: "Each recommendation must be expressible as a sprint task: [verb] [component] to [outcome]."'
        ),
        "Specificity requirement stated": (
            'Add: "Avoid recommendations like \'add monitoring\'. Specify: \'Add CloudWatch alarm on Lambda error rate > 5% for [function name]\'."'
        ),
    },
}


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Critic-gym: audit and improve MoE critic prompts")
    parser.add_argument("--audit-only", action="store_true", help="Read-only audit, no rewrites")
    parser.add_argument("--critic", default=None, help="Audit/rewrite a single critic by name")
    parser.add_argument("--rewrite", default=None, metavar="CRITIC", help="Propose rewrite for a critic (gated)")
    parser.add_argument("--delta", default=None, metavar="ARCH", help="Run TATB before/after delta on arch (requires API)")
    args = parser.parse_args()

    target_critics = [args.critic or args.rewrite] if (args.critic or args.rewrite) else list(CRITIC_FILES.keys())
    target_critics = [c for c in target_critics if c in CRITIC_FILES]

    if not target_critics:
        print(RED(f"Unknown critic. Valid names: {', '.join(CRITIC_FILES)}"))
        sys.exit(1)

    results = []
    prompts = {}

    # ── Phase 1+2: Inventory + Score ────────────────────────────────────────
    print(f"\n{BOLD('── Phase 1+2: Inventory + Score ─────────────────────')}")
    for name in target_critics:
        path = CRITIC_FILES[name]
        prompt = _extract_prompt(path)
        if prompt is None:
            print(f"  {YLW('WARN')} Could not extract prompt from {path.name}")
            continue
        prompts[name] = prompt
        result = _audit_prompt(name, prompt)
        results.append(result)
        _print_audit(result, verbose=True)

    if not results:
        print(RED("No prompts extracted. Check critic file paths."))
        sys.exit(1)

    _print_summary_table(results)

    if args.audit_only:
        print(f"\n{DIM('Audit-only mode — no rewrites proposed.')}")
        return

    # ── Phase 3: Diagnose ────────────────────────────────────────────────────
    rewrite_targets = [r for r in results if r["grade"] != "HEALTHY"]
    if args.rewrite:
        rewrite_targets = [r for r in results if r["name"] == args.rewrite]

    if not rewrite_targets:
        print(f"\n{GRN('All audited critics are HEALTHY — no rewrites needed.')}")
        return

    print(f"\n{BOLD('── Phase 3: Diagnoses ───────────────────────────────')}")
    for result in rewrite_targets:
        diagnoses = _diagnose(result)
        if not diagnoses:
            continue
        print(f"\n{BOLD(result['name'].upper())} — {len(diagnoses)} issue(s):")
        for dim_label, missing, suggestion in diagnoses:
            print(f"  {YLW('▸')} [{dim_label}] {missing}")
            print(f"    {DIM('→')} {suggestion}")

    # ── Phase 4: Rewrite (gated) ─────────────────────────────────────────────
    print(f"\n{BOLD('── Phase 4: Rewrite (gated) ──────────────────────────')}")
    print(DIM("For each critic: review the diagnosis above, then propose inline additions."))
    print(DIM("This skill proposes additions — it does not replace the full prompt."))
    print()

    for result in rewrite_targets:
        name = result["name"]
        diagnoses = _diagnose(result)
        if not diagnoses:
            continue

        print(f"{BOLD(CYAN(name.upper()))}")
        print("Proposed additions based on diagnosis:\n")

        additions = []
        for dim_label, missing, suggestion in diagnoses:
            additions.append(f"# [{dim_label}] {missing}\n{suggestion}")

        for i, addition in enumerate(additions, 1):
            print(f"  {i}. {addition}\n")

        print(f"Apply these additions to {CRITIC_FILES[name].name}?")
        try:
            choice = input("  [y / n / skip]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            choice = "n"

        if choice == "y":
            # Append additions as a comment block at the end of the system prompt
            path = CRITIC_FILES[name]
            src = path.read_text()
            addition_block = "\n\n# ── critic-gym additions ─────────────────────────────\n"
            addition_block += "\n".join(f"# {line}" for a in additions for line in a.split("\n"))

            # Find the closing triple-quote of the primary system prompt and insert before it
            # Pattern: last occurrence of triple-quote before first function def after the prompt
            prompt_text = prompts[name]
            insert_pos = src.find(prompt_text) + len(prompt_text)
            new_src = src[:insert_pos] + addition_block + src[insert_pos:]
            path.write_text(new_src)
            print(f"  {GRN('✓')} Additions written to {path.name}")

            # ── Phase 5: TATB delta ──────────────────────────────────────────
            if args.delta:
                print(f"\n{BOLD('── Phase 5: TATB delta ──────────────────────────────')}")
                _run_tatb_delta(args.delta, name)

        elif choice == "skip":
            print(f"  {DIM('Skipped.')}")
        else:
            print(f"  {DIM('No changes made.')}")


def _run_tatb_delta(arch: str, critic_name: str):
    """Run TATB before/after delta. Requires API running and tatb-score skill."""
    import subprocess
    print(f"  Running TATB on {arch} (this takes ~3s)...")
    try:
        r = subprocess.run(
            ["python3", str(ROOT / ".claude/skills/tatb-score/scripts/tatb_score.py"), arch],
            capture_output=True, text=True, timeout=30, cwd=str(ROOT),
        )
        if r.returncode == 0:
            print(r.stdout[-800:])
        else:
            print(YLW(f"  TATB returned non-zero. Run manually: /tatb-score {arch}"))
    except Exception as e:
        print(YLW(f"  TATB delta skipped: {e}. Run /tatb-score {arch} manually after rewrite."))


if __name__ == "__main__":
    main()
