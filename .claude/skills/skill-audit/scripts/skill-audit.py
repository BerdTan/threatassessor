#!/usr/bin/env python3
"""
skill-audit — Engine Item 15
Audit the .claude/skills/ corpus as an adversarial execution surface.

Six dimensions:
  AUD-1  Parameter injection      — unsanitised user args into shell/subprocess
  AUD-2  Privilege path audit     — writes to sensitive paths (report/, chatbot/data/, .env, policies/)
  AUD-3  Skill chaining map       — skills invoking other skills; blast-radius of compromised downstream
  AUD-4  Output injection         — skill writes to shared docs (DECISIONS.md, docs/blog/) that feed other skills
  AUD-5  Manifest coverage gap    — .py/.sh files in corpus not covered by skills.sha256
  AUD-6  Execution scope drift    — skills with network/write ops that lack allowed-tools declaration

Distinct from check-skills (tamper detection):
  check-skills = did someone modify this file?
  skill-audit  = if a skill is modified or receives adversarial input, what is the blast radius?

Exit codes: 0 = no CRITICAL/HIGH; 1 = CRITICAL/HIGH found; 2 = parse error
"""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
SKILLS_DIR = ROOT / ".claude" / "skills"
MANIFEST_PATH = SKILLS_DIR / "skills.sha256"

if not (ROOT / "mcp_server" / "server.py").exists():
    print(f"[ERROR] Could not locate project root (tried {ROOT})", file=sys.stderr)
    sys.exit(2)

# ── Severity order ────────────────────────────────────────────────────────────
_SEV_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}

_FINDINGS: list[dict] = []


def _find(dim: str, title: str, severity: str, detail: str, path: str = "") -> None:
    _FINDINGS.append({"dim": dim, "title": title, "severity": severity,
                      "detail": detail, "path": path})


# ── Helpers ───────────────────────────────────────────────────────────────────

def _skill_scripts() -> list[Path]:
    """All .py and .sh files under skills/*/scripts/."""
    scripts = []
    for skill_dir in sorted(SKILLS_DIR.iterdir()):
        if not skill_dir.is_dir() or skill_dir.name == "skills.sha256":
            continue
        scripts_dir = skill_dir / "scripts"
        if scripts_dir.is_dir():
            for f in sorted(scripts_dir.iterdir()):
                if f.suffix in {".py", ".sh"}:
                    scripts.append(f)
    return scripts


def _skill_name(script: Path) -> str:
    return script.parent.parent.name


def _skill_md(skill_name: str) -> Path:
    return SKILLS_DIR / skill_name / "skill.md"


def _read(path: Path) -> str:
    try:
        return path.read_text(errors="replace")
    except OSError:
        return ""


# ── AUD-1: Parameter injection ────────────────────────────────────────────────
# Look for skills that:
#   a) accept sys.argv / argparse args  AND
#   b) pass those args to subprocess with shell=True or build shell strings with them

_SHELL_TRUE_RE = re.compile(r"shell\s*=\s*True")
_OS_SYSTEM_RE = re.compile(r"\bos\.system\s*\(")
_EVAL_RE = re.compile(r"(?<![a-z_A-Z\-])eval\(")
_ARGV_RE = re.compile(r"\bsys\.argv\b|\bargparse\b|\bargs\.\w+")
_SUBPROCESS_STR_RE = re.compile(
    r"subprocess\.[a-z_]+\s*\(\s*f['\"]|subprocess\.[a-z_]+\s*\(\s*['\"].*\{",
    re.DOTALL,
)


def aud1_parameter_injection() -> None:
    dim = "AUD-1"
    flagged = 0

    for script in _skill_scripts():
        # Skip self — the audit script contains pattern strings that would self-match
        if _skill_name(script) == "skill-audit":
            continue

        text = _read(script)
        skill = _skill_name(script)
        rel = str(script.relative_to(ROOT))

        has_args = bool(_ARGV_RE.search(text))

        # shell=True with any argument-derived variable is the highest risk
        shell_true = bool(_SHELL_TRUE_RE.search(text))
        os_system = bool(_OS_SYSTEM_RE.search(text))
        uses_eval = bool(_EVAL_RE.search(text))
        fstring_subprocess = bool(_SUBPROCESS_STR_RE.search(text))

        if uses_eval:
            _find(dim, f"{skill}: eval() call", "HIGH",
                  "eval() with potentially externally-derived content; arbitrary code execution if "
                  "adversarial input reaches this path.",
                  rel)
            flagged += 1
            continue

        if shell_true and has_args:
            _find(dim, f"{skill}: shell=True with arg-sourced input", "HIGH",
                  "subprocess call with shell=True and script accepts sys.argv/argparse args. "
                  "Unsanitised user-controlled arg could reach shell interpreter.",
                  rel)
            flagged += 1

        elif shell_true:
            _find(dim, f"{skill}: shell=True (no direct arg path detected)", "MEDIUM",
                  "shell=True subprocess call. Verify no external content reaches this call at runtime.",
                  rel)
            flagged += 1

        elif os_system:
            _find(dim, f"{skill}: os.system() call", "MEDIUM",
                  "os.system() is shell-invoking; equivalent risk to shell=True.",
                  rel)
            flagged += 1

        elif fstring_subprocess and has_args:
            _find(dim, f"{skill}: f-string subprocess with arg-sourced input", "MEDIUM",
                  "subprocess call built with f-string interpolation and script accepts user args. "
                  "Verify args are validated/escaped before reaching subprocess.",
                  rel)
            flagged += 1

    if flagged == 0:
        _find(dim, "No parameter injection patterns detected", "INFO",
              f"No shell=True, eval(), or os.system() with unsanitised argv paths across "
              f"{len(_skill_scripts())} skill scripts.")


# ── AUD-2: Privilege path audit ───────────────────────────────────────────────
# Skills that write to sensitive project paths

_SENSITIVE_WRITES: list[tuple[str, re.Pattern, str]] = [
    ("report/",      re.compile(r'["\']report/|ROOT\s*/\s*"report"'), "Generated report outputs"),
    ("chatbot/data/", re.compile(r'["\']chatbot/data/|chatbot["\s]*/["\s]*data'), "Large data/embedding files"),
    (".env",          re.compile(r'open\([^)]*["\']\.env["\']|write.*\.env|Path.*\.env.*write'), "API keys / environment"),
    ("policies/",     re.compile(r'["\']policies/|ROOT\s*/\s*"policies".*write|\.write_text.*policies'), "Policy config files"),
    ("docs/DECISIONS", re.compile(r'DECISIONS\.md.*write|write.*DECISIONS|open.*DECISIONS.*w'), "DECISIONS.md (shared doc)"),
    ("docs/blog/",    re.compile(r'["\']docs/blog/|docs.*blog.*write'), "Blog drafts"),
    ("skills.sha256", re.compile(r'skills\.sha256.*write|MANIFEST.*write_text'), "SHA256 manifest"),
]

_OPEN_WRITE_RE = re.compile(r'open\s*\([^)]+["\']w[b]?["\']|\.write_text\(|\.write\(|json\.dump\s*\(')


def aud2_privilege_paths() -> None:
    dim = "AUD-2"
    flagged = 0

    for script in _skill_scripts():
        text = _read(script)
        skill = _skill_name(script)
        rel = str(script.relative_to(ROOT))

        has_write = bool(_OPEN_WRITE_RE.search(text))
        if not has_write:
            continue

        for path_label, pattern, sensitivity in _SENSITIVE_WRITES:
            if pattern.search(text):
                # skills.sha256 write is expected in check-skills (--regen) — downgrade
                if path_label == "skills.sha256" and skill == "check-skills":
                    _find(dim, f"{skill}: writes skills.sha256 (expected)", "INFO",
                          "check-skills --regen intentionally regenerates the manifest.", rel)
                elif path_label in ("docs/DECISIONS", "docs/blog/"):
                    _find(dim, f"{skill}: writes to {path_label}", "MEDIUM",
                          f"Skill writes to {sensitivity}. If output is adversarially influenced, "
                          "content injected here may be parsed by other skills (recall, gen-blog, session-cleanup).",
                          rel)
                    flagged += 1
                elif path_label == ".env":
                    _find(dim, f"{skill}: writes .env", "HIGH",
                          "Writing to .env overwrites API keys. Any skill that accepts external "
                          "input and writes here is a credential-clobber vector.",
                          rel)
                    flagged += 1
                else:
                    _find(dim, f"{skill}: writes to {path_label}", "LOW",
                          f"Writes to {sensitivity} ({path_label}). Intended by design for most skills; "
                          "verify write path is not user-controlled.",
                          rel)

    if flagged == 0 and not any(f["dim"] == dim and f["severity"] in ("CRITICAL", "HIGH")
                                for f in _FINDINGS):
        _find(dim, "No critical privilege path writes detected", "INFO",
              "No skill found writing to .env or other critical paths with unsanitised input.")


# ── AUD-3: Skill chaining map ─────────────────────────────────────────────────
# Skills that invoke other skills; compromised downstream = upstream blast radius

_SKILL_INVOKE_RE = re.compile(
    r"check-skills|check-detect|check-mcp|check-governance|check-eventbroker|"
    r"check-brain|check-sip|check-connector|check-routing|qualify-corpus|"
    r"bench-loop|critic-gym|detect-loop|session-cleanup|health-audit|"
    r"docs-health|recall|mcp-audit|aisurface-audit|model-audit|skill-audit"
)

# Also catch subprocess.run(["python3", "...skills/..."])
_SUBPROCESS_SKILL_RE = re.compile(r'python3[^"\']*skills/|skills/[^"\']+\.py')


def aud3_skill_chaining() -> None:
    dim = "AUD-3"
    chains: list[tuple[str, str]] = []  # (invoker, invoked)

    for script in _skill_scripts():
        # Skip self — pattern strings in this script would match itself as a chain hub
        if _skill_name(script) == "skill-audit":
            continue

        text = _read(script)
        skill = _skill_name(script)

        invoked_names = set(_SKILL_INVOKE_RE.findall(text))
        invoked_paths = set(_SUBPROCESS_SKILL_RE.findall(text))

        # Remove self-references
        invoked_names.discard(skill)

        all_invoked = invoked_names | {p.split("/skills/")[-1].split(".")[0]
                                       for p in invoked_paths if "skills/" in p}
        all_invoked.discard(skill)
        all_invoked.discard("")  # remove empty strings from regex noise

        for inv in all_invoked:
            chains.append((skill, inv))

    if not chains:
        _find(dim, "No skill-chaining detected", "INFO",
              "No skill invokes another skill by name in its script body.")
        return

    # Group by invoker
    by_invoker: dict[str, list[str]] = {}
    for invoker, invoked in chains:
        by_invoker.setdefault(invoker, []).append(invoked)

    # Multi-hop chains are higher risk (downstream compromise propagates up)
    # Flag chains where an invoked skill itself also has dependencies
    invoked_set = {inv for _, inv in chains}
    invoker_set = {inv for inv, _ in chains}
    transitive_risk = invoked_set & invoker_set  # skills that are both invoked AND invoke others

    for invoker, invoked_list in sorted(by_invoker.items()):
        rel = str(_skill_md(invoker).relative_to(ROOT)) if _skill_md(invoker).exists() else invoker
        inv_str = ", ".join(sorted(invoked_list))
        has_transitive = any(inv in transitive_risk for inv in invoked_list)
        sev = "MEDIUM" if has_transitive else "LOW"
        _find(dim, f"{invoker} → {inv_str}",
              sev,
              f"{'Multi-hop chain: ' if has_transitive else ''}{invoker} invokes {inv_str}. "
              f"If {inv_str} output is compromised (tampered script or injected output), "
              f"{invoker} inherits the blast radius.",
              rel)

    if transitive_risk:
        _find(dim, f"Transitive chain nodes: {', '.join(sorted(transitive_risk))}", "MEDIUM",
              "These skills appear as both invoker and invoked — a compromise propagates "
              "through multiple hops. Verify each has a clean SHA256 entry.")


# ── AUD-4: Output injection ───────────────────────────────────────────────────
# Skills that write to shared docs consumed by other skills (recall, gen-blog, session-cleanup)

_DECISIONS_WRITE_RE = re.compile(
    r'DECISIONS|decisions\.md', re.IGNORECASE
)
_BLOG_WRITE_RE = re.compile(r'docs/blog|draft_', re.IGNORECASE)
_DOCS_WRITE_RE = re.compile(r'docs/[A-Z]|write.*docs/', re.IGNORECASE)

# Skills whose output feeds other skills
_CONSUMER_SKILLS = {"recall", "gen-blog", "session-cleanup", "docs-health", "health-audit"}


def aud4_output_injection() -> None:
    dim = "AUD-4"
    flagged = 0

    for script in _skill_scripts():
        text = _read(script)
        skill = _skill_name(script)
        rel = str(script.relative_to(ROOT))

        # Check for writes to shared docs
        writes_decisions = bool(_DECISIONS_WRITE_RE.search(text) and _OPEN_WRITE_RE.search(text))
        writes_blog = bool(_BLOG_WRITE_RE.search(text) and _OPEN_WRITE_RE.search(text))
        writes_docs = bool(_DOCS_WRITE_RE.search(text) and _OPEN_WRITE_RE.search(text))

        if writes_decisions:
            _find(dim, f"{skill}: writes DECISIONS.md", "MEDIUM",
                  "DECISIONS.md is read by recall, session-cleanup, gen-blog, docs-health. "
                  "If this skill's output is adversarially influenced, injected content reaches "
                  "all downstream consumers in the next session.",
                  rel)
            flagged += 1

        if writes_blog:
            _find(dim, f"{skill}: writes docs/blog/", "LOW",
                  "Blog draft files are not parsed by the harness but may be read by gen-blog. "
                  "Injection risk is bounded to blog output quality.",
                  rel)

        if writes_docs and not writes_decisions and not writes_blog:
            _find(dim, f"{skill}: writes to docs/", "LOW",
                  "Writes to docs/ hierarchy. Verify output does not contain shell metacharacters "
                  "that could affect downstream consumers (session-cleanup, health-audit).",
                  rel)

    if flagged == 0:
        _find(dim, "No high-risk output injection paths detected", "INFO",
              "No skill found writing adversarially-reachable content to DECISIONS.md "
              "or other shared doc paths.")


# ── AUD-5: Manifest coverage gap ──────────────────────────────────────────────
# Cross-ref skills.sha256 against full corpus — ongoing drift detection

def aud5_manifest_coverage() -> None:
    dim = "AUD-5"

    if not MANIFEST_PATH.exists():
        _find(dim, "skills.sha256 manifest missing", "HIGH",
              "No SHA256 manifest found. Run: python3 .claude/skills/check-skills/scripts/check-skills.py --regen",
              str(MANIFEST_PATH.relative_to(ROOT)))
        return

    # Load manifest
    manifest_paths: set[str] = set()
    for line in MANIFEST_PATH.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("  ", 1)
        if len(parts) == 2:
            manifest_paths.add(parts[1])

    # Current .py/.sh corpus (security-relevant executables only)
    current_scripts: dict[str, str] = {}
    for script in _skill_scripts():
        rel = str(script.relative_to(ROOT))
        digest = hashlib.sha256(script.read_bytes()).hexdigest()
        current_scripts[rel] = digest

    not_in_manifest = {p for p in current_scripts if p not in manifest_paths}
    in_manifest_not_on_disk = {p for p in manifest_paths
                                if p.endswith((".py", ".sh"))
                                and not (ROOT / p).exists()}

    if not_in_manifest:
        _find(dim, f"{len(not_in_manifest)} script(s) not in SHA256 manifest", "HIGH",
              "These files exist in the corpus but are not in skills.sha256 — "
              "tamper detection has a blind spot. "
              "Run: python3 .claude/skills/check-skills/scripts/check-skills.py --regen\n"
              "  " + "\n  ".join(sorted(not_in_manifest)[:20]))
    else:
        _find(dim, "All corpus scripts covered by SHA256 manifest", "INFO",
              f"{len(manifest_paths)} manifest entries; {len(current_scripts)} corpus files. "
              "No coverage gaps.")

    if in_manifest_not_on_disk:
        _find(dim, f"{len(in_manifest_not_on_disk)} manifest entries not on disk (ghost entries)",
              "LOW",
              "Manifest references files that no longer exist. Regenerate to clean stale entries.\n"
              "  " + "\n  ".join(sorted(in_manifest_not_on_disk)[:10]))


# ── AUD-6: Execution scope drift ──────────────────────────────────────────────
# Skills operating outside declared allowed-tools scope

_NET_RE = re.compile(r'\brequests\b|\bhttpx\b|\burllib\b|http\.client|aiohttp|websocket', re.IGNORECASE)
_WRITE_OP_RE = re.compile(r'\.write_text\(|open\([^)]+["\']w|json\.dump\s*\(|shutil\.(copy|move|rmtree)')
_SUBPROCESS_RE = re.compile(r'\bsubprocess\b|\bos\.system\b|\bos\.popen\b')

# Patterns that indicate network or write ops in skill.md allowed-tools
_AT_NET_RE = re.compile(r'WebFetch|WebSearch|curl', re.IGNORECASE)
_AT_WRITE_RE = re.compile(r'\bWrite\b|\bEdit\b', re.IGNORECASE)
_AT_BASH_RE = re.compile(r'\bBash\b', re.IGNORECASE)


def aud6_execution_scope() -> None:
    dim = "AUD-6"
    flagged = 0

    for skill_dir in sorted(SKILLS_DIR.iterdir()):
        if not skill_dir.is_dir() or skill_dir.name == "skills.sha256":
            continue

        skill = skill_dir.name
        skill_md_path = skill_dir / "skill.md"
        scripts_dir = skill_dir / "scripts"

        if not scripts_dir.is_dir():
            continue

        # Read all scripts for this skill
        combined = ""
        for f in scripts_dir.iterdir():
            if f.suffix in {".py", ".sh"}:
                combined += _read(f)

        if not combined:
            continue

        skill_md_text = _read(skill_md_path)
        has_allowed_tools = "allowed-tools" in skill_md_text.lower()

        uses_network = bool(_NET_RE.search(combined))
        uses_write = bool(_WRITE_OP_RE.search(combined))
        uses_subprocess = bool(_SUBPROCESS_RE.search(combined))

        at_declares_net = bool(_AT_NET_RE.search(skill_md_text))
        at_declares_write = bool(_AT_WRITE_RE.search(skill_md_text))
        at_declares_bash = bool(_AT_BASH_RE.search(skill_md_text))

        issues: list[str] = []

        if uses_network and not at_declares_net and has_allowed_tools:
            issues.append("network calls (requests/httpx/urllib) but allowed-tools does not include WebFetch/WebSearch")

        if uses_write and not at_declares_write and not at_declares_bash and has_allowed_tools:
            issues.append("file write ops (write_text/open-w/json.dump) but allowed-tools lacks Write/Edit/Bash")

        if uses_subprocess and not at_declares_bash and has_allowed_tools:
            issues.append("subprocess calls but allowed-tools does not include Bash")

        if issues:
            rel = str(skill_md_path.relative_to(ROOT)) if skill_md_path.exists() else skill
            for issue in issues:
                _find(dim, f"{skill}: scope mismatch — {issue.split(' but')[0]}", "MEDIUM",
                      f"{skill} {issue}. Declared allowed-tools may be understating actual scope.",
                      rel)
                flagged += 1

        # No allowed-tools at all — check if skill does anything significant
        if not has_allowed_tools and (uses_network or uses_write or uses_subprocess):
            rel = str(skill_md_path.relative_to(ROOT)) if skill_md_path.exists() else skill
            ops = []
            if uses_network:
                ops.append("network")
            if uses_write:
                ops.append("write")
            if uses_subprocess:
                ops.append("subprocess")
            _find(dim, f"{skill}: no allowed-tools declaration ({', '.join(ops)} ops detected)",
                  "LOW",
                  "Skill performs significant operations but skill.md has no allowed-tools line. "
                  "Implicit wildcard scope — no declared constraint on what Claude can invoke.",
                  rel)

    if flagged == 0 and not any(f["dim"] == dim and f["severity"] in ("CRITICAL", "HIGH")
                                for f in _FINDINGS):
        _find(dim, "No critical scope drift detected", "INFO",
              "All skills with allowed-tools declarations appear consistent with their script operations.")


# ── Report ────────────────────────────────────────────────────────────────────

def _sev_badge(s: str) -> str:
    return {"CRITICAL": "🔴 CRITICAL", "HIGH": "🟠 HIGH",
            "MEDIUM": "🟡 MEDIUM", "LOW": "🔵 LOW", "INFO": "✅ INFO"}.get(s, s)


def print_report() -> None:
    counts = {s: 0 for s in _SEV_ORDER}
    for f in _FINDINGS:
        counts[f["severity"]] += 1

    print("\n── skill-audit ─────────────────────────────────────────────────────────────")
    print(f"Engine Item 15 | {len(_FINDINGS)} findings | "
          f"C:{counts['CRITICAL']} H:{counts['HIGH']} M:{counts['MEDIUM']} "
          f"L:{counts['LOW']} I:{counts['INFO']}\n")

    # Group by dim
    dims_seen = []
    by_dim: dict[str, list[dict]] = {}
    for f in _FINDINGS:
        if f["dim"] not in by_dim:
            dims_seen.append(f["dim"])
        by_dim.setdefault(f["dim"], []).append(f)

    for dim in dims_seen:
        dim_findings = sorted(by_dim[dim], key=lambda x: _SEV_ORDER[x["severity"]])
        worst = dim_findings[0]["severity"] if dim_findings else "INFO"
        dim_labels = {
            "AUD-1": "Parameter injection",
            "AUD-2": "Privilege path audit",
            "AUD-3": "Skill chaining map",
            "AUD-4": "Output injection",
            "AUD-5": "Manifest coverage gap",
            "AUD-6": "Execution scope drift",
        }
        print(f"  {dim}  {dim_labels.get(dim, dim):<28}  [{_sev_badge(worst)}]")
        for f in dim_findings:
            badge = _sev_badge(f["severity"])
            print(f"    {badge:<18}  {f['title']}")
            detail_lines = f["detail"].split("\n")
            for line in detail_lines:
                print(f"                       {line}")
            if f["path"]:
                print(f"                       → {f['path']}")
        print()


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    try:
        aud1_parameter_injection()
        aud2_privilege_paths()
        aud3_skill_chaining()
        aud4_output_injection()
        aud5_manifest_coverage()
        aud6_execution_scope()
    except Exception as exc:
        import traceback
        print(f"[ERROR] Audit aborted: {exc}", file=sys.stderr)
        traceback.print_exc()
        return 2

    print_report()

    has_critical_high = any(f["severity"] in ("CRITICAL", "HIGH") for f in _FINDINGS)
    return 1 if has_critical_high else 0


if __name__ == "__main__":
    sys.exit(main())
