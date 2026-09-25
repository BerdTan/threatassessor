#!/usr/bin/env python3
"""
prompt-audit — Engine Item 16
Audit prompt templates as an adversarial security surface.

Six dimensions:
  PAU-1  Template enumeration        — locate all prompt templates in the codebase
  PAU-2  Injection path audit        — external content flowing into prompts without sanitisation
  PAU-3  Leakage check               — system prompts exposing internal config/paths
  PAU-4  Over-permission audit       — critic system prompts granting broader scope than role requires
  PAU-5  Instruction-override surface — user input escaping user-role into system-role context
  PAU-6  Critic scope tightness      — critic prompts susceptible to role-redirect via poisoned input

Distinct from promptsmith (quality lens vs security lens on prompt templates).
Relates to aisurface-audit (data-path level) — prompt-audit drills into prompt construction layer.

Exit codes: 0 = no CRITICAL/HIGH; 1 = CRITICAL/HIGH found; 2 = parse error
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent

if not (ROOT / "mcp_server" / "server.py").exists():
    print(f"[ERROR] Could not locate project root (tried {ROOT})", file=sys.stderr)
    sys.exit(2)

CHATBOT = ROOT / "chatbot"
CRITICS_DIR = CHATBOT / "modules" / "agents" / "critics"
AGENTS_DIR = CHATBOT / "modules" / "agents"
MODULES_DIR = CHATBOT / "modules"
HARNESS_DIR = CHATBOT / "harness"
MCP_DIR = ROOT / "mcp_server"

# ── Severity order ─────────────────────────────────────────────────────────────
_SEV_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}
_FINDINGS: list[dict] = []


def _find(dim: str, title: str, severity: str, detail: str, path: str = "") -> None:
    _FINDINGS.append({"dim": dim, "title": title, "severity": severity,
                      "detail": detail, "path": path})


def _read(path: Path) -> str:
    try:
        return path.read_text(errors="replace")
    except OSError:
        return ""


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _py_files(*dirs: Path) -> list[Path]:
    seen: set[Path] = set()
    files = []
    for d in dirs:
        if d.is_dir():
            for f in sorted(d.rglob("*.py")):
                resolved = f.resolve()
                if resolved not in seen:
                    seen.add(resolved)
                    files.append(f)
    return files


# ── PAU-1: Template enumeration ───────────────────────────────────────────────
# Locate all prompt template sites: SYSTEM_PROMPT constants, _build_system_prompt(),
# f-string constructions where external content is interpolated.

_SYSTEM_CONST_RE = re.compile(
    r'(SYSTEM_PROMPT\s*=\s*["\']|system_prompt\s*=\s*["\']|_build_system_prompt|_create_system_prompt)',
    re.IGNORECASE,
)
_FSTRING_PROMPT_RE = re.compile(
    r'(system_prompt|user_prompt|prompt)\s*=\s*f["\']',
    re.IGNORECASE,
)
_TRIPLE_FSTRING_RE = re.compile(
    r'(system_prompt|user_prompt|prompt)\s*=\s*f"""',
    re.IGNORECASE,
)

class TemplateRecord(NamedTuple):
    path: Path
    kind: str  # "constant", "builder", "fstring"
    line: int
    snippet: str


def _enumerate_templates() -> list[TemplateRecord]:
    records: list[TemplateRecord] = []
    scan_dirs = [CRITICS_DIR, AGENTS_DIR, MODULES_DIR, HARNESS_DIR, MCP_DIR]
    for f in _py_files(*scan_dirs):
        lines = _read(f).splitlines()
        for i, line in enumerate(lines, start=1):
            if _SYSTEM_CONST_RE.search(line):
                kind = "builder" if ("_build_system_prompt" in line or "_create_system_prompt" in line) else "constant"
                records.append(TemplateRecord(f, kind, i, line.strip()[:100]))
            elif _FSTRING_PROMPT_RE.search(line) or _TRIPLE_FSTRING_RE.search(line):
                records.append(TemplateRecord(f, "fstring", i, line.strip()[:100]))
    return records


def pau1_template_enumeration() -> list[TemplateRecord]:
    dim = "PAU-1"
    templates = _enumerate_templates()

    by_file: dict[str, list[TemplateRecord]] = {}
    for t in templates:
        by_file.setdefault(_rel(t.path), []).append(t)

    critic_files = {_rel(f) for f in CRITICS_DIR.rglob("*.py") if f.suffix == ".py"}
    orchestrator_files = {_rel(f) for f in (AGENTS_DIR / "orchestrators").rglob("*.py")
                          if f.suffix == ".py"} if (AGENTS_DIR / "orchestrators").is_dir() else set()

    total = len(templates)
    critic_count = sum(1 for t in templates if _rel(t.path) in critic_files)
    orchestrator_count = sum(1 for t in templates if _rel(t.path) in orchestrator_files)
    other_count = total - critic_count - orchestrator_count

    _find(dim, f"Template inventory: {total} sites across {len(by_file)} files", "INFO",
          f"Critics: {critic_count} | Orchestrators: {orchestrator_count} | Other modules: {other_count}\n"
          f"Files: {', '.join(sorted(by_file.keys())[:8])}{'...' if len(by_file) > 8 else ''}",
          "")
    return templates


# ── PAU-2: Injection path audit ───────────────────────────────────────────────
# Identify paths where external (user-supplied or ingested) content flows into
# prompt construction without sanitisation. Focus: arch diagram text, TAclaw content,
# enrichment responses, MCP tool parameters.

# Variable names that carry external / untrusted content
_EXTERNAL_VARS = re.compile(
    r'\b(arch(?:itecture)?(?:_text|_content|_description|_input|_data|_diagram|_mmd)?'
    r'|mmd_content|diagram_text|user_input|user_content'
    r'|crawled_(?:content|text|data)'
    r'|taclaw_(?:output|result|content)'
    r'|enrichment_(?:result|response|data)'
    r'|mcp_(?:param|result|response|content|tool_output)'
    r'|external_(?:content|data|input)'
    r'|file_content|source_text|ingested_(?:content|data)'
    r'|component_name|node_(?:name|label|description)'
    r'|arch_name|architecture_name)\b',
    re.IGNORECASE,
)

_FSTRING_INTERP_RE = re.compile(r'\{[^}]+\}')

# Sanitisation indicators
_SANITISE_RE = re.compile(
    r'(sanitize|sanitise|sanitise_arch_name|sanitise_content|escape|strip_tags'
    r'|re\.sub\s*\(.*injection'
    r'|html\.escape|bleach\.|markupsafe|remove_prompt_injection'
    r'|clean_input|validate_arch|prompt_safety)',
    re.IGNORECASE,
)


def pau2_injection_paths(templates: list[TemplateRecord]) -> None:
    dim = "PAU-2"
    flagged = 0
    seen_sites: set[tuple[Path, int]] = set()

    for tmpl in templates:
        site_key = (tmpl.path.resolve(), tmpl.line)
        if site_key in seen_sites:
            continue
        seen_sites.add(site_key)
        if tmpl.kind not in ("fstring", "builder"):
            continue
        text = _read(tmpl.path)
        lines = text.splitlines()

        # Collect the fstring block (up to 30 lines from template site)
        block_lines = lines[max(0, tmpl.line - 1): tmpl.line + 30]
        block = "\n".join(block_lines)

        # Only flag vars that appear inside {…} interpolation braces — not as free text labels
        _BRACE_INTERP_RE = re.compile(r'\{([^}]+)\}')
        external_matches = []
        for m in _BRACE_INTERP_RE.finditer(block):
            expr = m.group(1)
            hit = _EXTERNAL_VARS.search(expr)
            if hit:
                external_matches.append(hit.group(0))
        if not external_matches:
            continue

        # Check if any sanitisation is applied near this site (200 lines upstream, 50 downstream)
        # The sanitisation call may be at variable assignment, which can be far above the f-string.
        context_start = max(0, tmpl.line - 200)
        context_end = min(len(lines), tmpl.line + 50)
        context = "\n".join(lines[context_start:context_end])
        has_sanitise = bool(_SANITISE_RE.search(context))

        if has_sanitise:
            _find(dim, f"{tmpl.path.name}:{tmpl.line} — external vars with sanitisation present",
                  "LOW",
                  f"External vars interpolated: {', '.join(set(external_matches[:5]))}. "
                  f"Sanitisation pattern detected nearby — verify it covers injection vectors.",
                  _rel(tmpl.path))
        else:
            severity = "HIGH" if tmpl.path.parent.name in ("critics", "orchestrators") else "MEDIUM"
            _find(dim, f"{tmpl.path.name}:{tmpl.line} — unsanitised external content in prompt",
                  severity,
                  f"External vars interpolated into prompt without detected sanitisation: "
                  f"{', '.join(set(external_matches[:5]))}. "
                  f"Injection vector: attacker-controlled content in architecture diagram or "
                  f"crawled source can embed system-role directives.",
                  _rel(tmpl.path))
            flagged += 1

    if flagged == 0:
        _find(dim, "No unsanitised external-content injections detected", "INFO",
              "Scanned all fstring/builder template sites for external variable interpolation. "
              "No HIGH/MEDIUM injection paths found (or sanitisation present at all sites).")


# ── PAU-3: Leakage check ──────────────────────────────────────────────────────
# Scan system prompts for exposed internal config: file paths, key names,
# module names, internal error text — content that assists targeted injection.

# Patterns that indicate internal detail leakage in a system prompt
_LEAK_PATH_RE = re.compile(
    r'(?<!["\'])(/(?:home|mnt|var|etc|usr|opt|chatbot|report|policies|mcp_server|\.claude)[^\s\'\"]{3,})',
)
_LEAK_KEY_RE = re.compile(
    r'\b(API_KEY|SECRET_KEY|DB_PASSWORD|OPENROUTER_API_KEY|TA_API_KEY'
    r'|LLM_PROVIDER|LANGFUSE_SECRET|BEDROCK_SECRET)\b',
)
_LEAK_MODULE_RE = re.compile(
    r'\b(ground_truth_generator|moe_orchestrator|ta_brain_query|policy_broker'
    r'|rule_evaluator|threat_analyst|exhaustive_mitigation_mapper)\b',
)
_LEAK_ERROR_RE = re.compile(
    r'(Traceback|ValueError|KeyError|AttributeError|JSONDecodeError'
    r'|ModuleNotFoundError|ImportError)[\s:]+',
)

# Find SYSTEM_PROMPT constant blocks
_SYSPROMPT_BLOCK_RE = re.compile(
    r'(?:SYSTEM_PROMPT|system_prompt)\s*=\s*(?:f?""")(.*?)(?:""")',
    re.DOTALL,
)
_SYSPROMPT_INLINE_RE = re.compile(
    r'(?:SYSTEM_PROMPT|system_prompt)\s*=\s*(?:f?["\'])(.*?)(?:["\'])',
)


def _extract_system_prompt_text(content: str) -> list[str]:
    blocks = []
    for m in _SYSPROMPT_BLOCK_RE.finditer(content):
        blocks.append(m.group(1))
    for m in _SYSPROMPT_INLINE_RE.finditer(content):
        blocks.append(m.group(1))
    return blocks


def pau3_leakage_check() -> None:
    dim = "PAU-3"
    flagged = 0

    for f in _py_files(CRITICS_DIR, AGENTS_DIR, MODULES_DIR, HARNESS_DIR):
        content = _read(f)
        if not content:
            continue

        prompt_blocks = _extract_system_prompt_text(content)
        if not prompt_blocks:
            continue

        # Strip example/recommendation lines (GOOD:/BAD: patterns) before leakage scan
        # to avoid false positives on example filesystem paths in threat recommendations.
        _EXAMPLE_LINE_RE = re.compile(r'^\s*(GOOD|BAD|Example|e\.g\.|e\.g,|\*\s+GOOD|\*\s+BAD)[\s:"\']', re.IGNORECASE | re.MULTILINE)
        combined_raw = "\n".join(prompt_blocks)
        combined = "\n".join(
            line for line in combined_raw.splitlines()
            if not _EXAMPLE_LINE_RE.match(line)
        )
        issues: list[tuple[str, str]] = []

        path_hits = _LEAK_PATH_RE.findall(combined)
        if path_hits:
            issues.append(("filesystem paths", ", ".join(path_hits[:3])))

        key_hits = _LEAK_KEY_RE.findall(combined)
        if key_hits:
            issues.append(("env-key names", ", ".join(key_hits[:3])))

        module_hits = _LEAK_MODULE_RE.findall(combined)
        if module_hits:
            issues.append(("internal module names", ", ".join(module_hits[:3])))

        error_hits = _LEAK_ERROR_RE.findall(combined)
        if error_hits:
            issues.append(("exception class names", ", ".join(error_hits[:2])))

        if issues:
            severity = "HIGH" if key_hits else ("MEDIUM" if path_hits or module_hits else "LOW")
            detail_parts = [f"{label}: {vals}" for label, vals in issues]
            _find(dim, f"{f.name} — system prompt leaks internal detail",
                  severity,
                  "System prompt text contains: " + "; ".join(detail_parts) + ". "
                  "An attacker who can read the system prompt gains a map for targeted injection.",
                  _rel(f))
            flagged += 1

    if flagged == 0:
        _find(dim, "No internal-detail leakage detected in system prompts", "INFO",
              "Scanned all system prompt constant blocks for path/key/module/error leakage. "
              "No HIGH/MEDIUM findings.")


# ── PAU-4: Over-permission audit ──────────────────────────────────────────────
# Assess whether each critic system prompt grants broader permissions than the
# critic role requires. A blackhat critic prompted to "be helpful" is over-permissioned.

# Helpful/generic LLM phrases that should not appear in a security critic's system prompt
_HELPFUL_PHRASES = [
    "be helpful",
    "be as helpful",
    "help the user",
    "assist the user",
    "please help",
    "I am here to help",
    "happy to help",
    "answer any question",
    "answer all questions",
    "do your best",
    "feel free to",
]

# Role-widening phrases
_ROLE_WIDEN_PHRASES = [
    "you can also",
    "you may also",
    "in addition to your role",
    "you are also capable",
    "you can perform",
    "general assistant",
    "general-purpose",
    "any task",
    "any request",
]

# Role-narrowing phrases (desirable — critic should be constrained)
_NARROWING_PHRASES = [
    "your sole",
    "your only",
    "exclusively",
    "only your task is",
    "do not",
    "must not",
    "you must not",
    "do not answer",
    "do not provide",
    "refuse",
    "out of scope",
]


def _critic_role(filename: str) -> str:
    role_map = {
        "blackhat": "adversarial attacker simulation — must not assist attacker",
        "red_teamer": "red team scenario generation",
        "purple_teamer": "combined red+blue hybrid analysis",
        "architect": "architecture security review",
        "tester": "test case security review",
        "scrum_master": "pipeline output quality gate",
    }
    for key, desc in role_map.items():
        if key in filename.lower():
            return desc
    return "unknown critic role"


def pau4_over_permission() -> None:
    dim = "PAU-4"
    flagged = 0

    for f in sorted(CRITICS_DIR.rglob("*.py")):
        if f.name == "__init__.py":
            continue
        content = _read(f)
        if not content:
            continue

        prompt_blocks = _extract_system_prompt_text(content)
        if not prompt_blocks:
            continue

        combined = "\n".join(prompt_blocks).lower()
        role = _critic_role(f.name)

        helpful_hits = [p for p in _HELPFUL_PHRASES if p in combined]
        widen_hits = [p for p in _ROLE_WIDEN_PHRASES if p in combined]
        narrowing_hits = [p for p in _NARROWING_PHRASES if p in combined]

        narrowing_score = len(narrowing_hits)
        permission_issues: list[str] = []

        if helpful_hits:
            permission_issues.append(f"generic helpfulness phrases: {helpful_hits[:2]}")
        if widen_hits:
            permission_issues.append(f"role-widening phrases: {widen_hits[:2]}")

        if permission_issues:
            # Blackhat critic getting "helpful" phrasing is a HIGH
            is_blackhat = "blackhat" in f.name.lower()
            severity = "HIGH" if is_blackhat else "MEDIUM"
            narrowing_note = f" Narrowing constraints present: {narrowing_hits[:3]}." if narrowing_hits else " No narrowing constraints detected."
            _find(dim, f"{f.name} — system prompt may be over-permissioned",
                  severity,
                  f"Critic role: {role}.\n"
                  f"Permission issues: {'; '.join(permission_issues)}.\n"
                  f"Narrowing score: {narrowing_score} constraints.{narrowing_note}\n"
                  "Risk: attacker-supplied input can leverage helpfulness bias to redirect critic behaviour.",
                  _rel(f))
            flagged += 1
        elif narrowing_score < 2:
            _find(dim, f"{f.name} — system prompt has few narrowing constraints ({narrowing_score})",
                  "LOW",
                  f"Critic role: {role}. Narrowing constraints: {narrowing_hits}. "
                  "Consider adding explicit 'do not' / 'must not' / 'refuse' directives to tighten scope.",
                  _rel(f))
        else:
            _find(dim, f"{f.name} — scope looks tight ({narrowing_score} narrowing constraints)",
                  "INFO",
                  f"Critic role: {role}. Narrowing constraints: {narrowing_hits[:4]}.")

    if flagged == 0 and not any(f["dim"] == dim and f["severity"] in ("HIGH", "MEDIUM")
                                for f in _FINDINGS):
        _find(dim, "No over-permissioned critic system prompts detected", "INFO",
              "All critic system prompts reviewed for generic helpfulness / role-widening phrases.")


# ── PAU-5: Instruction-override surface ───────────────────────────────────────
# For each prompt template, assess whether user input can escape the user-role
# boundary into system-role context (prompt injection escalation path).

# Structural patterns that create injection risk
_ROLE_BOUNDARY_RE = re.compile(
    r'(messages\s*=\s*\[.*?"role"\s*:\s*"user".*?f["\']|'
    r'"content"\s*:\s*f["\']|'
    r'content=f["\']|'
    r'"content"\s*:\s*f""")',
    re.DOTALL,
)

# Patterns indicating an injection-resistant structure (explicit instruction-first)
_INSTRUCTION_FIRST_RE = re.compile(
    r'(system_prompt.*?\n.*?user_prompt|'
    r'"role"\s*:\s*"system".*?"role"\s*:\s*"user")',
    re.DOTALL,
)

# Patterns where the prompt is entirely constructed as one string (higher risk)
_SINGLE_BLOCK_INTERP_RE = re.compile(
    r'(prompt\s*=\s*f""".*?\{[^}]+\}.*?"""|'
    r'prompt\s*\+=\s*f""")',
    re.DOTALL,
)

# Direct system-prompt contamination: external var in system role
_SYSTEM_ROLE_EXTERNAL_RE = re.compile(
    r'"role"\s*:\s*"system"[^}]{0,200}f["\'].*?\{(' +
    _EXTERNAL_VARS.pattern + r')',
    re.DOTALL,
)


def pau5_instruction_override() -> None:
    dim = "PAU-5"
    flagged = 0

    for f in _py_files(CRITICS_DIR, AGENTS_DIR, MODULES_DIR, HARNESS_DIR):
        content = _read(f)
        if not content:
            continue

        # Check for external content flowing into a "user" role message
        role_boundary_hits = _ROLE_BOUNDARY_RE.findall(content)
        single_block_hits = _SINGLE_BLOCK_INTERP_RE.findall(content)
        system_role_hits = _SYSTEM_ROLE_EXTERNAL_RE.findall(content)

        # Direct system-role contamination is HIGH
        if system_role_hits:
            _find(dim, f"{f.name} — external content interpolated into system role",
                  "HIGH",
                  f"External variables {system_role_hits[:3]} detected within system-role message content. "
                  "Attacker-controlled content can reach the system-role boundary directly.",
                  _rel(f))
            flagged += 1
            continue

        if not role_boundary_hits and not single_block_hits:
            continue

        # Check if external vars appear in {…} interpolations in this file
        _PAU5_BRACE_RE = re.compile(r'\{([^}]+)\}')
        has_external = any(
            _EXTERNAL_VARS.search(m.group(1))
            for m in _PAU5_BRACE_RE.finditer(content)
        )
        if not has_external:
            continue

        # Single-block prompts with external vars: no clear role separation
        if single_block_hits and has_external:
            severity = "MEDIUM"
            _find(dim, f"{f.name} — single-block prompt with external var interpolation",
                  severity,
                  "Prompt is constructed as a single block (no explicit system/user role split) "
                  "and interpolates external content. A carefully crafted input could attempt to "
                  "prepend 'Ignore previous instructions' style overrides.",
                  _rel(f))
            flagged += 1
        elif role_boundary_hits and has_external:
            _find(dim, f"{f.name} — external content in user-role message (nominal)",
                  "LOW",
                  "External content flows into user-role messages. "
                  "This is expected but ensure system prompt precedes all user content "
                  "and that no user message can be made to appear before the system role.",
                  _rel(f))

    if flagged == 0:
        _find(dim, "No instruction-override escalation paths detected", "INFO",
              "No system-role contamination or single-block-with-external-var patterns found "
              "in critic/agent template sites.")


# ── PAU-6: Critic scope tightness ─────────────────────────────────────────────
# Verify the five critic prompts are scoped such that poisoned architecture input
# cannot redirect the critic's role or elicit out-of-role behaviour.
# Connects to DETECT-QC-009 (endogenous constraint evasion).

# Phrases that anchor the critic to its task (desirable)
_ANCHOR_PHRASES = [
    "your task is",
    "your role is",
    "you are a",
    "evaluate only",
    "assess only",
    "your assessment",
    "return a json",
    "respond only",
    "do not deviate",
    "stay within",
    "scope: ",
]

# Phrases that indicate the critic could be redirected by input content
_REDIRECT_RISK_PHRASES = [
    "follow any instructions",
    "if the user asks",
    "if asked",
    "as requested",
    "modify your response based on",
    "adjust based on",
    "based on feedback",
    "as the architecture specifies",
]

_EXPECTED_CRITICS = {
    "blackhat_critic.py", "red_teamer_critic.py", "purple_teamer_critic.py",
    "architect_critic.py", "tester_critic.py",
}

_OUTPUT_FORMAT_RE = re.compile(
    r'(return.*json|respond.*json|json.*code block|```json|"json_schema"'
    r'|single\s+json\s+object|exact\s+shape|OUTPUT\s+FORMAT.*JSON'
    r'|response\s+must\s+be.*json|reply\s+with.*json)',
    re.IGNORECASE,
)


def pau6_critic_scope_tightness() -> None:
    dim = "PAU-6"
    found_critics: set[str] = set()

    for f in sorted(CRITICS_DIR.rglob("*.py")):
        if f.name == "__init__.py":
            continue
        content = _read(f)
        if not content:
            continue

        prompt_blocks = _extract_system_prompt_text(content)
        if not prompt_blocks:
            # Check builder methods too
            full_prompt_re = re.compile(
                r'def\s+(?:_build_system_prompt|_create_system_prompt)\s*\([^)]*\).*?return\s+f?"""(.*?)"""',
                re.DOTALL,
            )
            builder_blocks = full_prompt_re.findall(content)
            if builder_blocks:
                prompt_blocks = builder_blocks

        if not prompt_blocks:
            continue

        found_critics.add(f.name)
        combined = "\n".join(prompt_blocks).lower()

        anchor_hits = [p for p in _ANCHOR_PHRASES if p in combined]
        redirect_hits = [p for p in _REDIRECT_RISK_PHRASES if p in combined]
        has_output_format = bool(_OUTPUT_FORMAT_RE.search(combined))

        anchor_score = len(anchor_hits)
        role = _critic_role(f.name)

        issues: list[str] = []
        if redirect_hits:
            issues.append(f"redirect-risk phrases: {redirect_hits[:2]}")
        if anchor_score < 2:
            issues.append(f"low anchor score ({anchor_score}/10)")
        if not has_output_format:
            issues.append("no output-format constraint (JSON schema not enforced)")

        if redirect_hits:
            severity = "HIGH"
            _find(dim, f"{f.name} — critic prompt contains redirect-risk phrases",
                  severity,
                  f"Critic role: {role}.\n"
                  f"Redirect-risk phrases found: {redirect_hits}.\n"
                  "A poisoned architecture diagram could embed these phrases to trick the critic "
                  "into deviating from its security assessment role (DETECT-QC-009 vector).",
                  _rel(f))
        elif anchor_score < 2 or not has_output_format:
            severity = "MEDIUM"
            _find(dim, f"{f.name} — critic scope could be tighter",
                  severity,
                  f"Critic role: {role}. Issues: {'; '.join(issues)}. "
                  "Low anchor count and missing output-format constraint increase susceptibility "
                  "to role-redirect via poisoned input.",
                  _rel(f))
        else:
            _find(dim, f"{f.name} — critic scope appears tight",
                  "INFO",
                  f"Critic role: {role}. Anchor score: {anchor_score}. "
                  f"Output format constraint: {'yes' if has_output_format else 'no'}. "
                  f"Anchors: {anchor_hits[:4]}.")

    # Flag missing expected critics
    missing = _EXPECTED_CRITICS - found_critics
    if missing:
        _find(dim, f"Expected critic files not found: {missing}", "MEDIUM",
              "Could not locate system prompts in expected critic files. "
              "Either the files are missing or prompts are constructed dynamically "
              "in a way this audit cannot parse.",
              str(CRITICS_DIR.relative_to(ROOT)))


# ── Report ─────────────────────────────────────────────────────────────────────

def _sev_badge(s: str) -> str:
    return {"CRITICAL": "🔴 CRITICAL", "HIGH": "🟠 HIGH",
            "MEDIUM": "🟡 MEDIUM", "LOW": "🔵 LOW", "INFO": "✅ INFO"}.get(s, s)


def print_report() -> None:
    counts = {s: 0 for s in _SEV_ORDER}
    for f in _FINDINGS:
        counts[f["severity"]] += 1

    print("\n── prompt-audit ────────────────────────────────────────────────────────────")
    print(f"Engine Item 16 | {len(_FINDINGS)} findings | "
          f"C:{counts['CRITICAL']} H:{counts['HIGH']} M:{counts['MEDIUM']} "
          f"L:{counts['LOW']} I:{counts['INFO']}\n")

    dims_seen: list[str] = []
    by_dim: dict[str, list[dict]] = {}
    for f in _FINDINGS:
        if f["dim"] not in by_dim:
            dims_seen.append(f["dim"])
        by_dim.setdefault(f["dim"], []).append(f)

    dim_labels = {
        "PAU-1": "Template enumeration",
        "PAU-2": "Injection path audit",
        "PAU-3": "Leakage check",
        "PAU-4": "Over-permission audit",
        "PAU-5": "Instruction-override surface",
        "PAU-6": "Critic scope tightness",
    }

    for dim in dims_seen:
        dim_findings = sorted(by_dim[dim], key=lambda x: _SEV_ORDER[x["severity"]])
        worst = dim_findings[0]["severity"] if dim_findings else "INFO"
        print(f"  {dim}  {dim_labels.get(dim, dim):<30}  [{_sev_badge(worst)}]")
        for f in dim_findings:
            badge = _sev_badge(f["severity"])
            print(f"    {badge:<18}  {f['title']}")
            for line in f["detail"].split("\n"):
                print(f"                       {line}")
            if f["path"]:
                print(f"                       → {f['path']}")
        print()


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> int:
    try:
        templates = pau1_template_enumeration()
        pau2_injection_paths(templates)
        pau3_leakage_check()
        pau4_over_permission()
        pau5_instruction_override()
        pau6_critic_scope_tightness()
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
