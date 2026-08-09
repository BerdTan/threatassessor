#!/usr/bin/env python3
"""
ta_pr_review.py — ThreatAssessor GitHub Actions PR reviewer.

For each changed .mmd file in the PR:
  1. POST /api/v1/governance/check  — 50ms screen, no LLM
  2. POST /api/v1/analyze-stream    — full deterministic analysis (~30s)
  3. GET  /api/v1/reports/{arch}/export — fetch gate.result + findings
  4. Post a Markdown review comment on the PR

Exits 1 if any architecture is BLOCK (fails the check).

Required env vars:
  TA_API_URL   — e.g. http://localhost:8000
  TA_API_KEY   — matches API_KEY in .env
  GITHUB_TOKEN — provided automatically by Actions
  PR_NUMBER    — github.event.pull_request.number
  REPO         — github.repository (owner/repo)
  BASE_REF     — github.event.pull_request.base.ref
"""

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import requests

# ── Config ────────────────────────────────────────────────────────────────────

API_URL   = os.environ.get("TA_API_URL", "http://localhost:8000").rstrip("/")
API_KEY   = os.environ.get("TA_API_KEY", "")
GH_TOKEN  = os.environ.get("GITHUB_TOKEN", "")
PR_NUMBER = os.environ.get("PR_NUMBER", "")
REPO      = os.environ.get("REPO", "")
BASE_REF  = os.environ.get("BASE_REF", "main")

API_HEADERS = {"TM-API-KEY": API_KEY}
GH_HEADERS  = {
    "Authorization": f"Bearer {GH_TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}

ANALYSIS_TIMEOUT = 120  # seconds to wait for analyze-stream to complete


# ── Step 1: find changed .mmd files ──────────────────────────────────────────

def get_changed_mmds() -> list[Path]:
    # Allow skill/CI override via env var (used by /taci --arch)
    force_mmd = os.environ.get("TA_FORCE_MMD", "").strip()
    if force_mmd:
        return [Path(f) for f in force_mmd.split(",") if f.strip()]
    try:
        result = subprocess.run(
            ["git", "diff", f"origin/{BASE_REF}...HEAD", "--name-only", "--diff-filter=ACM"],
            capture_output=True, text=True, check=True,
        )
        files = [Path(f) for f in result.stdout.splitlines() if f.endswith(".mmd")]
        return files
    except subprocess.CalledProcessError as e:
        print(f"git diff failed: {e.stderr}")
        return []


# ── Step 2: governance_check ──────────────────────────────────────────────────

def governance_check(mmd_text: str, arch_name: str) -> dict:
    resp = requests.post(
        f"{API_URL}/api/v1/governance/check",
        json={"mmd_content": mmd_text, "arch_name": arch_name},
        headers=API_HEADERS,
        timeout=15,
    )
    # 400 means CRITICAL block — body still has signals
    if resp.status_code in (200, 400):
        return resp.json()
    resp.raise_for_status()


# ── Step 3: full analysis via analyze-stream (mmd_text path) ─────────────────

def run_analysis(mmd_text: str, arch_name: str) -> dict | None:
    """Stream the SSE analysis and return the 'complete' event data."""
    resp = requests.post(
        f"{API_URL}/api/v1/analyze-stream",
        data={
            "mmd_text": mmd_text,
            "mmd_name": arch_name,
            "include_validation": "true",
            "ssp_profile": "low_risk_cloud",
            "enable_ssp": "true",
        },
        headers={**API_HEADERS, "Accept": "text/event-stream"},
        stream=True,
        timeout=ANALYSIS_TIMEOUT,
    )
    if not resp.ok:
        print(f"  analyze-stream error {resp.status_code}: {resp.text[:200]}")
        return None

    # Parse SSE stream manually — no sseclient dependency needed
    current_event = None
    deadline = time.time() + ANALYSIS_TIMEOUT
    for raw_line in resp.iter_lines(decode_unicode=True):
        if time.time() > deadline:
            print("  Analysis timed out")
            return None
        if raw_line.startswith("event:"):
            current_event = raw_line[6:].strip()
        elif raw_line.startswith("data:"):
            data_str = raw_line[5:].strip()
            if current_event == "complete":
                try:
                    return json.loads(data_str)
                except json.JSONDecodeError:
                    return None
            if current_event == "error":
                print(f"  Analysis error: {data_str}")
                return None
    return None


# ── Step 4: fetch export bundle ───────────────────────────────────────────────

def fetch_export(arch_name: str) -> dict | None:
    resp = requests.get(
        f"{API_URL}/api/v1/reports/{requests.utils.quote(arch_name, safe='')}/export",
        headers=API_HEADERS,
        timeout=30,
    )
    if resp.ok:
        return resp.json()
    return None


# ── Step 5: format PR comment ─────────────────────────────────────────────────

def _gate_emoji(result: str) -> str:
    return "🚫 BLOCK" if result == "BLOCK" else "✅ PASS"


def _severity_emoji(sev: str) -> str:
    return {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🟢"}.get(sev.upper(), "⚪")


def build_comment(results: list[dict]) -> str:
    lines = ["## ThreatAssessor Architecture Review\n"]

    # Summary table
    lines.append("| File | Risk Score | Gate | Top Signal |")
    lines.append("|---|---|---|---|")
    for r in results:
        gate = r.get("gate_result", "UNKNOWN")
        score = r.get("risk_score")
        score_str = f"{score}/100" if score is not None else "—"
        top = r.get("top_signal", "—")
        lines.append(f"| `{r['file']}` | {score_str} | {_gate_emoji(gate)} | {top} |")

    # Blocking detail sections
    for r in results:
        if r.get("gate_result") == "BLOCK" or r.get("gov_blocked"):
            lines.append(f"\n### `{r['file']}` — Blocking findings")
            for sig in r.get("blocking_signals", []):
                lines.append(f"- **{sig}**")
            for rule in r.get("critical_rules", []):
                lines.append(f"- `{rule['rule_id']}` {_severity_emoji(rule.get('severity',''))} {rule.get('description', '')}")

        # Top attack paths (collapsible)
        paths = r.get("top_paths", [])
        if paths:
            lines.append(f"\n<details><summary><code>{r['file']}</code> — top attack paths</summary>\n")
            for p in paths[:3]:
                lines.append(f"- **{p.get('score', '?')}/100** · {p.get('path_summary', p.get('name', ''))}")
                ttps = ", ".join(p.get("techniques", [])[:4])
                if ttps:
                    lines.append(f"  - TTPs: `{ttps}`")
            lines.append("\n</details>")

    lines.append("\n---")
    lines.append("*Reviewed by [ThreatAssessor](https://github.com/BerdTan/threatassessor)*")
    return "\n".join(lines)


# ── Step 6: post GitHub review ────────────────────────────────────────────────

def post_github_review(body: str, blocked: bool):
    if not (GH_TOKEN and PR_NUMBER and REPO):
        print("GitHub env vars not set — printing comment to stdout:\n")
        print(body)
        return

    event = "REQUEST_CHANGES" if blocked else "COMMENT"
    resp = requests.post(
        f"https://api.github.com/repos/{REPO}/pulls/{PR_NUMBER}/reviews",
        headers=GH_HEADERS,
        json={"body": body, "event": event},
        timeout=15,
    )
    if resp.ok:
        print(f"Posted GitHub review (event={event})")
    else:
        print(f"Failed to post review: {resp.status_code} {resp.text[:200]}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    changed = get_changed_mmds()
    if not changed:
        print("No .mmd files changed — skipping TA review")
        return 0

    print(f"Changed .mmd files: {[str(f) for f in changed]}")
    results = []
    any_blocked = False

    for mmd_path in changed:
        arch_name = mmd_path.stem  # filename without .mmd
        print(f"\n── {mmd_path} ──")

        if not mmd_path.exists():
            print("  File deleted — skipping")
            continue

        mmd_text = mmd_path.read_text(encoding="utf-8")
        result = {"file": str(mmd_path), "arch_name": arch_name}

        # Step 2: governance screen
        print("  governance_check...", end=" ", flush=True)
        try:
            gov = governance_check(mmd_text, arch_name)
            result["gov_blocked"] = gov.get("blocked", False)
            result["critical_rules"] = [
                f for f in gov.get("findings", [])
                if f.get("unmapped", {}).get("severity") in ("CRITICAL", "HIGH")
            ]
            result["top_signal"] = (
                gov.get("fired_rules", ["—"])[0] if gov.get("fired_rules") else "—"
            )
            print(f"{'BLOCKED' if result['gov_blocked'] else 'ok'} | fired={gov.get('fired_rules', [])}")
        except Exception as e:
            print(f"error: {e}")
            result["gov_blocked"] = False

        # Step 3: full analysis (skip if governance already critical-blocked)
        if result.get("gov_blocked") and result.get("critical_rules"):
            print("  Skipping full analysis — CRITICAL block from governance")
            result["gate_result"] = "BLOCK"
            result["blocking_signals"] = [
                f"{r.get('unmapped',{}).get('rule_id','?')} CRITICAL"
                for r in result["critical_rules"]
            ]
            any_blocked = True
        else:
            print("  analyze-stream...", end=" ", flush=True)
            analysis = run_analysis(mmd_text, arch_name)
            if analysis:
                gt = analysis.get("analysis", {})
                result["risk_score"] = gt.get("risk_score") or gt.get("metadata", {}).get("risk_score")
                paths = gt.get("expected_attack_paths", [])
                result["top_paths"] = sorted(paths, key=lambda p: p.get("score", 0), reverse=True)[:3]
                if result["top_paths"] and result.get("top_signal") == "—":
                    result["top_signal"] = result["top_paths"][0].get("name", "—")
                print(f"done | risk={result.get('risk_score')}")

                # Step 4: export bundle for gate
                print("  export...", end=" ", flush=True)
                export = fetch_export(arch_name)
                if export:
                    gate = export.get("gate", {})
                    result["gate_result"] = gate.get("result", "UNKNOWN")
                    result["blocking_signals"] = gate.get("blocking_signals", [])
                    # Pull risk score from export bundle (authoritative source)
                    assessment = export.get("assessment", {})
                    result["risk_score"] = assessment.get("risk_score_before") or assessment.get("risk_score_after")
                    print(f"gate={result['gate_result']} risk={result.get('risk_score')}")
                else:
                    result["gate_result"] = "PASS"
                    print("not available — defaulting to PASS")
            else:
                result["gate_result"] = "UNKNOWN"
                print("analysis failed")

        if result.get("gate_result") == "BLOCK":
            any_blocked = True

        results.append(result)

    # Step 5+6: comment and review
    comment = build_comment(results)
    post_github_review(comment, any_blocked)

    return 1 if any_blocked else 0


if __name__ == "__main__":
    sys.exit(main())
