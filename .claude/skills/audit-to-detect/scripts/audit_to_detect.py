#!/usr/bin/env python3
"""
audit-to-detect — Translate /harden-audit findings into new DETECT rules.

Reads security-assessment/REPORT.md, filters findings to those that are
structurally detectable, not already covered, and High/Critical severity.
Proposes DETECT rule YAML, gates on human approval, applies to
policies/soc_detection_rules.yaml, then verifies with /check-detect.
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
REPORT_PATH   = ROOT / "security-assessment" / "REPORT.md"
RULES_FILE    = ROOT / "policies" / "soc_detection_rules.yaml"
CHECK_DETECT  = ROOT / ".claude/skills/check-detect/scripts/check-detect.py"

# ── Terminal helpers ──────────────────────────────────────────────────────────

def _c(code, t): return f"\033[{code}m{t}\033[0m"
BOLD  = lambda t: _c("1", t)
RED   = lambda t: _c("31", t)
GRN   = lambda t: _c("32", t)
YLW   = lambda t: _c("33", t)
CYAN  = lambda t: _c("36", t)
DIM   = lambda t: _c("2", t)
SEP   = lambda: print(_c("2", "─" * 56))

# ── Filter criteria ───────────────────────────────────────────────────────────

# Known governance_signals fields that could carry finding signals
_DETECTABLE_SIGNALS = {
    "exploitation", "injection", "manipulation", "sovereignty",
    "mcp_access", "aivss", "arch_metadata",
}

# Findings that map to structural/architectural patterns (not pure code bugs)
_DETECT_CANDIDATES = {
    "RT-02": {
        "title": "LLM-generated output injection — prompt injection in generated architecture diagram",
        "rationale": (
            "An authenticated caller can inject instructions into /generate-mmd via the 'extra' field, "
            "causing the LLM to produce a malicious Mermaid diagram. If that diagram is stored and "
            "later analysed, it becomes an indirect prompt injection into the TA pipeline — "
            "and if it contains HTML comments targeting AI coding agents, it triggers DETECT-027 "
            "in downstream consumers. The structural signal is: a generated MMD that contains "
            "injection markers or agent-targeting comments."
        ),
        "signal_path": "exploitation.injection_categories",
        "owasp": ["A01", "A03"],
        "atlas": "AML.TA0001",
        "kill_chain": "initial_access",
        "severity": "High",
        "incident_ref": "ta-harden-audit-2026-08-09-rt02",
        "proposed_rule": {
            "id": "DETECT-029",
            "name": "llm_generated_mmd_injection",
            "description": (
                "An LLM-generated architecture diagram contains prompt injection markers or "
                "agent-targeting instructions. Indicates the generate-mmd endpoint was used to "
                "produce a malicious diagram that could poison the TA pipeline or downstream AI "
                "coding agents. Grounded in TA harden-audit 2026-08-09 RT-02: unsanitised 'extra' "
                "field allowed full LLM instruction override."
            ),
            "conditions": [
                {"field": "exploitation.injection_categories", "op": "length_gt", "value": 0},
                {"field": "exploitation.severity", "op": "==", "value": "HIGH"},
            ],
            "combine": "all",
            "severity": "High",
            "actions": ["audit_log", "quarantine_trace", "page_soc"],
        },
    },
    "RT-06": {
        "title": "Unauthenticated MCP tool exposure — architecture exposes MCP-style tools without transport auth",
        "rationale": (
            "An architecture that exposes MCP-compatible tool APIs over a network transport without "
            "authentication is structurally equivalent to the RT-06 finding: any caller can invoke "
            "analysis, retrieval, and governance tools without credentials. This is detectable as an "
            "architecture signal when an agentic system exposes tool-calling endpoints with no auth "
            "node in the diagram — extending the existing MCP recon/flood rules (DETECT-020/021/022)."
        ),
        "signal_path": "mcp_access.unauthenticated_tool_calls",
        "owasp": ["A02"],
        "atlas": "AML.TA0003",
        "kill_chain": "initial_access",
        "severity": "High",
        "incident_ref": "ta-harden-audit-2026-08-09-rt06",
        "proposed_rule": {
            "id": "DETECT-030",
            "name": "unauthenticated_mcp_tool_exposure",
            "description": (
                "An agentic architecture exposes MCP-compatible tool APIs over a network transport "
                "with no authentication layer. All tools are callable without credentials — any caller "
                "can trigger analysis jobs, read reports, and access governance signals. Extends "
                "DETECT-020/021/022 (MCP recon/flood/auth-probe) with a structural pre-condition check. "
                "Grounded in TA harden-audit 2026-08-09 RT-06: MCP server accepted network transport "
                "with no auth gate."
            ),
            "conditions": [
                {"field": "arch_metadata.is_agentic", "op": "==", "value": True},
                {"field": "mcp_access.tool_calls_total", "op": ">", "value": 0},
                {"field": "mcp_access.auth_failures", "op": "==", "value": 0},
            ],
            "combine": "all",
            "severity": "High",
            "actions": ["audit_log", "page_soc"],
        },
    },
}

# Findings explicitly NOT suitable for DETECT rules (code bugs, not arch patterns)
_NOT_CANDIDATES = {
    "RT-01": "Path traversal in API endpoint — code bug, not an architecture signal",
    "RT-03": "Timing side-channel in API key comparison — implementation detail, not detectable in MMD",
    "RT-04": "Error message leakage — deployment misconfiguration, not structural",
    "RT-05": "Missing request size cap — API hardening, not an architecture pattern",
    "RT-07": "CI env var path traversal — CI-local attack surface, not in MMD/governance signals",
}


# ── Report parser ─────────────────────────────────────────────────────────────

def parse_report(path: Path) -> list[dict]:
    """Extract finding IDs and severities from REPORT.md."""
    if not path.exists():
        print(RED(f"Report not found: {path}"))
        print(f"  Run /harden-audit first to generate a report.")
        return []

    text = path.read_text(encoding="utf-8")
    findings = []
    for m in re.finditer(r'\|\s*(RT-\d+)\s*\|\s*\*\*?(Critical|High|Medium|Low)\*\*?\s*\|([^\|]+)\|', text):
        findings.append({
            "id": m.group(1).strip(),
            "severity": m.group(2).strip(),
            "summary": m.group(3).strip(),
        })
    return findings


# ── Existing rule checker ─────────────────────────────────────────────────────

def get_existing_rule_ids() -> set[str]:
    if not RULES_FILE.exists():
        return set()
    text = RULES_FILE.read_text(encoding="utf-8")
    return set(re.findall(r'id:\s*(DETECT-\d+)', text))


def get_next_detect_id(existing: set[str]) -> str:
    nums = [int(r.split("-")[1]) for r in existing if r.startswith("DETECT-")]
    return f"DETECT-{max(nums) + 1:03d}" if nums else "DETECT-029"


# ── YAML builder ─────────────────────────────────────────────────────────────

def build_rule_yaml(candidate: dict, rule_id: str) -> str:
    r = candidate["proposed_rule"].copy()
    r["id"] = rule_id  # use next available ID, not hardcoded

    cond_lines = ""
    for c in r["conditions"]:
        cond_lines += f"      - field: {c['field']}\n"
        cond_lines += f"        op: \"{c['op']}\"\n"
        val = c["value"]
        cond_lines += f"        value: {str(val).lower() if isinstance(val, bool) else val}\n"

    action_lines = ""
    for a in r["actions"]:
        action_lines += f"      - type: {a}\n"

    return f"""
  # {r['id']}: {r['name'].replace('_', ' ').title()}
  #
  # {r['description'][:120]}...
  #
  # Grounded in: {candidate['incident_ref']}
  # OWASP: {', '.join(candidate['owasp'])}  ATLAS: {candidate['atlas']}
  # Kill chain: {candidate['kill_chain']}
  # ─────────────────────────────────────────────────────────────────────────────
  - id: {r['id']}
    name: {r['name']}
    description: >
      {r['description']}
    incident_refs:
      - {candidate['incident_ref']}
    owasp: {candidate['owasp']}
    atlas_tactic: {candidate['atlas']}
    kill_chain_stage: {candidate['kill_chain']}
    ocsf_class: 2004
    ocsf_type_uid: 200406
    severity: {r['severity']}
    conditions:
{cond_lines}    combine: {r.get('combine', 'all')}
    actions:
{action_lines}"""


# ── Apply rule ────────────────────────────────────────────────────────────────

def apply_rule(yaml_block: str):
    text = RULES_FILE.read_text(encoding="utf-8")
    # Append before end of file (after last rule)
    if text.endswith("\n"):
        text += yaml_block + "\n"
    else:
        text += "\n" + yaml_block + "\n"
    RULES_FILE.write_text(text, encoding="utf-8")
    print(GRN(f"  Written to {RULES_FILE.relative_to(ROOT)}"))


# ── Verify ───────────────────────────────────────────────────────────────────

def run_check_detect() -> bool:
    if not CHECK_DETECT.exists():
        print(YLW("  /check-detect script not found — skipping verification"))
        return True
    result = subprocess.run([sys.executable, str(CHECK_DETECT)], cwd=ROOT, capture_output=True, text=True)
    if result.returncode == 0:
        print(GRN("  /check-detect passed"))
    else:
        print(RED("  /check-detect FAILED"))
        print(result.stdout[-500:])
    return result.returncode == 0


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="audit-to-detect — findings → DETECT rules")
    parser.add_argument("--report", default=str(REPORT_PATH), help="Path to REPORT.md")
    parser.add_argument("--observe-only", action="store_true", help="Show candidates, no changes")
    parser.add_argument("--finding", metavar="RT-ID", help="Process only this finding ID")
    args = parser.parse_args()

    report_path = Path(args.report)
    print(f"\n{BOLD('── audit-to-detect ──────────────────────────────────')}")
    print(f"  Report : {report_path}")
    print(f"  Rules  : {RULES_FILE.relative_to(ROOT)}")
    if args.observe_only:
        print(f"  Mode   : {CYAN('observe-only (no changes)')}")
    SEP()

    # Parse report
    findings = parse_report(report_path)
    if not findings:
        print(YLW("No findings parsed from report — nothing to do."))
        return 0

    existing_ids = get_existing_rule_ids()
    next_id = get_next_detect_id(existing_ids)

    # Show all findings, classify each
    print(f"\n{BOLD('Findings from report:')}")
    for f in findings:
        fid = f["id"]
        if fid in _NOT_CANDIDATES:
            print(f"  {DIM(fid)}  {DIM('✗ not a DETECT candidate')}  — {DIM(_NOT_CANDIDATES[fid])}")
        elif fid in _DETECT_CANDIDATES:
            cand = _DETECT_CANDIDATES[fid]
            print(f"  {GRN(fid)}  {GRN('✓ DETECT candidate')}  — {cand['title']}")
        else:
            print(f"  {YLW(fid)}  {YLW('? no mapping defined')}  — {f['summary'][:60]}")

    # Filter to candidates
    candidates = {
        fid: cand for fid, cand in _DETECT_CANDIDATES.items()
        if (args.finding is None or args.finding == fid)
    }

    if not candidates:
        print(f"\n{YLW('No DETECT candidates to process.')}")
        return 0

    if args.observe_only:
        print(f"\n{BOLD('Candidate details:')}")
        for fid, cand in candidates.items():
            SEP()
            print(f"\n{BOLD(fid)} — {cand['title']}")
            print(f"\n{DIM('Rationale:')}")
            print(f"  {cand['rationale']}")
            rule_id = get_next_detect_id(existing_ids)
            print(f"\n{DIM('Proposed rule:')} {rule_id} ({cand['proposed_rule']['name']})")
            existing_ids.add(rule_id)
        return 0

    # Gate → apply cycle
    applied = []
    current_existing = set(existing_ids)

    for fid, cand in candidates.items():
        SEP()
        rule_id = get_next_detect_id(current_existing)
        print(f"\n{BOLD(fid)} → {rule_id}: {cand['title']}")
        print(f"\n{DIM('Rationale:')}")
        print(f"  {cand['rationale']}")

        yaml_block = build_rule_yaml(cand, rule_id)
        print(f"\n{DIM('Proposed YAML:')}")
        print(CYAN(yaml_block))

        # Gate
        try:
            answer = input(f"\n  Apply this rule? [{GRN('y')} / {RED('n')} / {YLW('q')}uit] > ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\nAborted.")
            break

        if answer == "y":
            apply_rule(yaml_block)
            current_existing.add(rule_id)
            applied.append((fid, rule_id))
            print(GRN(f"  Applied {rule_id}"))
        elif answer == "q":
            print("Quit.")
            break
        else:
            print(DIM(f"  Skipped {fid}"))

    SEP()
    if applied:
        print(f"\n{BOLD('Applied:')} {', '.join(f'{fid}→{rid}' for fid, rid in applied)}")
        print(f"\n{DIM('Running /check-detect to verify...')}")
        run_check_detect()
        print(f"\n{DIM('Next steps:')}")
        print(f"  1. Add incident scenarios to incident_simulator.py for each new rule")
        print(f"  2. Run /detect-loop to verify real-corpus coverage")
        print(f"  3. Commit: git add policies/soc_detection_rules.yaml && git commit")
    else:
        print(f"\n{DIM('No rules applied.')}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
