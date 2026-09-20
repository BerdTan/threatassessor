#!/usr/bin/env python3
"""
aisurface-audit — Engine Item 13
Enumerate all AI data ingest surfaces across ThreatAssessor and rate their gate coverage.

Six surfaces:
  SRF-1  Prompt surface       — user/external content → LLM context
  SRF-2  Skill script surface — .claude/skills/ executables vs SHA256 manifest
  SRF-3  Brain JSONL surface  — ta_brain_instances.jsonl integrity gate
  SRF-4  Enrichment surface   — /api/v1/enrich input paths
  SRF-5  TAclaw crawl surface — RepoCrawler file types → harness without injection check
  SRF-6  MCP parameter surface— 18-tool free-form string params (cross-ref to mcp-audit)

Exit codes: 0 = no CRITICAL/HIGH; 1 = CRITICAL/HIGH found; 2 = parse error
"""
from __future__ import annotations

import ast
import hashlib
import re
import sys
from pathlib import Path
from typing import Any

# ── Project root ──────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
if not (ROOT / "mcp_server" / "server.py").exists():
    print(f"[ERROR] Could not locate project root (tried {ROOT})", file=sys.stderr)
    sys.exit(2)

# ── Severity ordering ─────────────────────────────────────────────────────────
_SEV_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}

FINDINGS: list[dict[str, Any]] = []


def _find(surface: str, title: str, severity: str, detail: str, path: str = "") -> None:
    FINDINGS.append(
        {
            "surface": surface,
            "title": title,
            "severity": severity,
            "detail": detail,
            "path": path,
        }
    )


# ═══════════════════════════════════════════════════════════════════════════════
# SRF-1  Prompt surface
# ═══════════════════════════════════════════════════════════════════════════════

def _parse_file(path: Path) -> ast.Module | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return None


def _find_mmd_prompt_injections(tree: ast.Module) -> list[tuple[int, str]]:
    """Return (line, snippet) where mmd_content / arch_content flows into an f-string."""
    hits: list[tuple[int, str]] = []
    taint_names = {"mmd_content", "arch_content", "raw_mmd_content",
                   "_raw_mmd_content", "user_prompt"}
    for node in ast.walk(tree):
        if isinstance(node, (ast.JoinedStr,)):
            src = ast.unparse(node)
            for name in taint_names:
                if name in src and len(src) < 400:
                    hits.append((getattr(node, "lineno", 0), src[:120]))
    return hits


def srf1_prompt_surface() -> None:
    """Check that mmd_content flows through governance gate before reaching LLM."""
    gtg = ROOT / "chatbot" / "modules" / "ground_truth_generator.py"
    stages = ROOT / "chatbot" / "harness" / "stages.py"
    governance = ROOT / "chatbot" / "harness" / "governance.py"

    if not gtg.exists():
        _find("SRF-1", "ground_truth_generator.py missing", "HIGH",
              "Cannot verify prompt injection path.", str(gtg))
        return

    # Check 1: mmd_content f-string in ground_truth_generator
    tree = _parse_file(gtg)
    if tree is None:
        _find("SRF-1", "ground_truth_generator.py parse error", "HIGH",
              "Cannot AST-parse file.", str(gtg))
        return

    hits = _find_mmd_prompt_injections(tree)
    if hits:
        for lineno, snippet in hits[:3]:
            _find(
                "SRF-1",
                f"mmd_content flows into f-string at line {lineno}",
                "INFO",
                f"Detected: {snippet!r}. "
                "Check governance gate is active on this path.",
                f"{gtg.relative_to(ROOT)}:{lineno}",
            )

    # Check 2: QualityStage.required
    if stages.exists():
        src = stages.read_text(encoding="utf-8", errors="replace")
        # QualityStage required=False means governance can be skipped
        if re.search(r"class QualityStage", src):
            # Find the required= assignment near QualityStage
            m = re.search(r"class QualityStage.*?required\s*=\s*(True|False)", src, re.DOTALL)
            if m and m.group(1) == "False":
                _find(
                    "SRF-1",
                    "QualityStage.required=False — governance gate is non-fatal",
                    "MEDIUM",
                    "QualityStage runs injection/evasion checks but required=False means "
                    "a parse failure in QualityStage does not block the pipeline. "
                    "Exploit: a stage bug lets malicious mmd_content reach LLM without "
                    "injection filtering. "
                    "Remediation: add a hard pre-filter before the first LLM call that "
                    "rejects CRITICAL injection payloads regardless of QualityStage health.",
                    str(stages.relative_to(ROOT)),
                )
        if re.search(r"class BouncerStage", src):
            m2 = re.search(r"class BouncerStage.*?required\s*=\s*(True|False)", src, re.DOTALL)
            if m2 and m2.group(1) == "True":
                _find(
                    "SRF-1",
                    "BouncerStage.required=True — hard gate present",
                    "INFO",
                    "BouncerStage halts the pipeline when exploitation.blocked=True or "
                    "_preflight_blocked=True. This is the primary hard gate.",
                    str(stages.relative_to(ROOT)),
                )

    # Check 3: check_input exists in governance.py
    if governance.exists():
        gov_src = governance.read_text(encoding="utf-8", errors="replace")
        if "def check_input(" in gov_src:
            _find(
                "SRF-1",
                "GovernanceAdapter.check_input() present — injection scanner active",
                "INFO",
                "Injection/evasion patterns are scanned before mmd_content enters analysis. "
                "GovernanceSignals feed BouncerStage and DETECT rules.",
                "chatbot/harness/governance.py",
            )
        else:
            _find(
                "SRF-1",
                "check_input() missing from governance.py",
                "HIGH",
                "No injection scanner found in GovernanceAdapter.",
                "chatbot/harness/governance.py",
            )

    # Check 4: critic prompt construction — do critics receive raw user-supplied text?
    critics_dir = ROOT / "chatbot" / "modules" / "agents" / "critics"
    if critics_dir.exists():
        critic_files = list(critics_dir.glob("*.py"))
        for cf in critic_files:
            ct = cf.read_text(encoding="utf-8", errors="replace")
            # Flag critics that embed mmd_content directly (not pre-processed data)
            if re.search(r"\bmmd_content\b", ct) or re.search(r"\barch_content\b", ct):
                _find(
                    "SRF-1",
                    f"{cf.name}: critic references raw mmd_content",
                    "MEDIUM",
                    f"This critic embeds raw architecture content in LLM prompt without "
                    "pre-processing. Adversarial payloads in input MMD reach this LLM call "
                    "only if QualityStage did not block them. "
                    "Remediation: pass pre-processed structured data, not raw mmd_content.",
                    str(cf.relative_to(ROOT)),
                )


# ═══════════════════════════════════════════════════════════════════════════════
# SRF-2  Skill script surface
# ═══════════════════════════════════════════════════════════════════════════════

def srf2_skill_surface() -> None:
    """Compare skills.sha256 manifest against all .py/.sh scripts under .claude/skills/."""
    manifest_path = ROOT / ".claude" / "skills" / "skills.sha256"
    skills_dir = ROOT / ".claude" / "skills"

    if not manifest_path.exists():
        _find(
            "SRF-2",
            "skills.sha256 manifest missing",
            "HIGH",
            "No SHA256 manifest found. Any skill script can be silently modified without "
            "detection. Engine Item 6 introduced this gate — regenerate with check-skills.",
            str(manifest_path),
        )
        return

    # Parse manifest: "hash  path" per line
    manifest: dict[str, str] = {}
    for line in manifest_path.read_text(encoding="utf-8").splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) == 2:
            manifest[parts[1]] = parts[0]

    # Enumerate all script files
    executables: list[Path] = []
    for ext in ("*.py", "*.sh"):
        executables.extend(skills_dir.rglob(ext))

    missing: list[str] = []
    tampered: list[str] = []

    for script in sorted(executables):
        # Relative path as stored in manifest (relative to ROOT)
        rel = str(script.relative_to(ROOT))
        rel_fwd = rel.replace("\\", "/")

        if rel_fwd not in manifest and rel not in manifest:
            missing.append(rel_fwd)
            continue

        expected_hash = manifest.get(rel_fwd) or manifest.get(rel)
        actual_hash = hashlib.sha256(script.read_bytes()).hexdigest()
        if actual_hash != expected_hash:
            tampered.append(rel_fwd)

    if tampered:
        for t in tampered[:5]:
            _find(
                "SRF-2",
                f"Skill script tampered: {t}",
                "CRITICAL",
                "SHA256 digest does not match manifest. Script may have been modified "
                "post-manifest. Regenerate manifest after verifying intent of change.",
                t,
            )

    if missing:
        _find(
            "SRF-2",
            f"{len(missing)} skill script(s) not in SHA256 manifest",
            "HIGH" if len(missing) > 3 else "MEDIUM",
            f"Scripts present on disk but not covered by skills.sha256: "
            f"{', '.join(missing[:5])}{'...' if len(missing) > 5 else ''}. "
            "These scripts can be modified without detection. "
            "Remediation: run check-skills to regenerate the manifest.",
            str(manifest_path),
        )
    else:
        _find(
            "SRF-2",
            "All skill scripts covered by SHA256 manifest",
            "INFO",
            f"Manifest covers {len(manifest)} entries; {len(executables)} scripts found on disk.",
            str(manifest_path.relative_to(ROOT)),
        )

    if not tampered and not missing:
        return  # already emitted INFO above

    # Manifest coverage %
    covered = len(executables) - len(missing)
    pct = covered / len(executables) * 100 if executables else 100
    if pct < 100 and not missing:  # sanity
        pass


# ═══════════════════════════════════════════════════════════════════════════════
# SRF-3  Brain JSONL surface
# ═══════════════════════════════════════════════════════════════════════════════

def srf3_brain_surface() -> None:
    """Verify JSONL integrity gate and check for unknown-provenance instances."""
    builder = ROOT / "chatbot" / "modules" / "ta_brain_builder.py"
    jsonl_path = ROOT / "report" / "brain" / "ta_brain_instances.jsonl"

    if not builder.exists():
        _find("SRF-3", "ta_brain_builder.py missing", "HIGH",
              "Cannot verify brain JSONL integrity gate.", str(builder))
        return

    src = builder.read_text(encoding="utf-8", errors="replace")

    # Check 1: BrainGuardian.ingest_guard present
    if "class BrainGuardian" in src and "def ingest_guard" in src:
        _find(
            "SRF-3",
            "BrainGuardian.ingest_guard() present — circular ingest gate active",
            "INFO",
            "Engine Item 6 gate: blocks instances with generated_by=brain_fast from "
            "entering the training corpus.",
            str(builder.relative_to(ROOT)),
        )
    else:
        _find(
            "SRF-3",
            "BrainGuardian.ingest_guard() missing",
            "HIGH",
            "No circular ingest protection found. brain_fast outputs could contaminate "
            "the training corpus.",
            str(builder.relative_to(ROOT)),
        )

    # Check 2: pipeline_provenance field populated
    if re.search(r'pipeline_provenance.*routing_mode.*"unknown"', src) or \
       re.search(r'"pipeline_provenance".*unknown', src):
        _find(
            "SRF-3",
            'pipeline_provenance defaults to "unknown" for missing routing_mode',
            "MEDIUM",
            "Instances ingested before Engine Item 10 routing_mode stamping have "
            'pipeline_provenance="unknown". These are not blocked by BrainGuardian. '
            "Remediation: audit existing JSONL for unknown-provenance entries and "
            "verify they are pre-gate historical instances (not post-gate injections).",
            str(builder.relative_to(ROOT)),
        )

    # Check 3: JSONL existence and spot-check
    if not jsonl_path.exists():
        _find(
            "SRF-3",
            "ta_brain_instances.jsonl not found",
            "LOW",
            "JSONL file absent — brain may not be built yet. "
            "No instance-level checks possible.",
            str(jsonl_path),
        )
        return

    import json as _json
    unknown_lines: list[int] = []
    brain_fast_lines: list[int] = []
    total = 0
    with jsonl_path.open(encoding="utf-8", errors="replace") as fh:
        for i, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            total += 1
            try:
                inst = _json.loads(line)
            except _json.JSONDecodeError:
                continue
            prov = inst.get("pipeline_provenance", "")
            gen_by = inst.get("generated_by", "")
            if prov == "unknown":
                unknown_lines.append(i)
            if gen_by == "brain_fast":
                brain_fast_lines.append(i)

    if brain_fast_lines:
        _find(
            "SRF-3",
            f"{len(brain_fast_lines)} brain_fast instance(s) in JSONL",
            "HIGH",
            f"Lines {brain_fast_lines[:5]} have generated_by=brain_fast. "
            "BrainGuardian should have blocked these at ingest time. "
            "Investigate whether the guard was bypassed or disabled.",
            str(jsonl_path.relative_to(ROOT)),
        )
    else:
        _find(
            "SRF-3",
            "No brain_fast instances in JSONL — circular ingest gate effective",
            "INFO",
            f"Checked {total} instances; none carry generated_by=brain_fast.",
            str(jsonl_path.relative_to(ROOT)),
        )

    if unknown_lines:
        _find(
            "SRF-3",
            f"{len(unknown_lines)}/{total} instances have pipeline_provenance=unknown",
            "LOW" if len(unknown_lines) < 10 else "MEDIUM",
            f"These instances were ingested before routing_mode stamping (Engine Item 10). "
            "Not blocked by BrainGuardian (expected for pre-gate corpus). "
            "If new instances appear with unknown provenance after Engine Item 10 was "
            "deployed, investigate the ingest path.",
            str(jsonl_path.relative_to(ROOT)),
        )


# ═══════════════════════════════════════════════════════════════════════════════
# SRF-4  Enrichment API surface
# ═══════════════════════════════════════════════════════════════════════════════

def srf4_enrichment_surface() -> None:
    """Verify enrichment endpoint does not pass user input to LLM context."""
    enrich = ROOT / "chatbot" / "api" / "routes" / "enrich.py"

    if not enrich.exists():
        _find("SRF-4", "enrich.py missing", "MEDIUM",
              "Cannot verify enrichment surface.", str(enrich))
        return

    src = enrich.read_text(encoding="utf-8", errors="replace")

    # Check 1: no LLM call in enrich.py
    llm_calls = re.findall(
        r"(generate_response|llm_client|call_llm|LLMClient|openai\.chat|anthropic\.|bedrock)",
        src,
    )
    if llm_calls:
        _find(
            "SRF-4",
            f"LLM call detected in enrich.py: {llm_calls[0]}",
            "HIGH",
            "User-supplied component/finding fields flow into an LLM call without "
            "a content trust gate. This is an injection path. "
            "Remediation: add GovernanceAdapter.check_input() on user fields before "
            "constructing the LLM message.",
            str(enrich.relative_to(ROOT)),
        )
    else:
        _find(
            "SRF-4",
            "enrich.py — no LLM call; deterministic read-only path",
            "INFO",
            "Enrichment endpoint reads existing ground_truth.json. "
            "User-supplied component label is used only for fuzzy matching against "
            "pre-existing node labels (no LLM context injection possible).",
            str(enrich.relative_to(ROOT)),
        )

    # Check 2: API key gate present
    if "verify_api_key" in src or "Depends(verify_api_key)" in src:
        _find(
            "SRF-4",
            "enrich.py — API key gate present",
            "INFO",
            "verify_api_key dependency applied; unauthenticated callers cannot reach "
            "the enrichment endpoint.",
            str(enrich.relative_to(ROOT)),
        )
    else:
        _find(
            "SRF-4",
            "enrich.py — API key gate missing",
            "HIGH",
            "Enrichment endpoint has no authentication gate. Any caller can read "
            "architecture reports and attack paths.",
            str(enrich.relative_to(ROOT)),
        )

    # Check 3: arch_name path traversal — is arch_name sanitised before use as directory?
    if re.search(r"resolve_arch_dir\(", src):
        # Check resolve_arch_dir for traversal protection
        reports_py = ROOT / "chatbot" / "api" / "routes" / "reports.py"
        if reports_py.exists():
            rep_src = reports_py.read_text(encoding="utf-8", errors="replace")
            traversal_guard = re.search(
                r"def resolve_arch_dir.*?\n.*?(\.\.|\.\s*parent|Path.*arch_name|sanitiz|reject)",
                rep_src, re.DOTALL,
            )
            if not re.search(r"\.\.", rep_src[rep_src.find("def resolve_arch_dir"):
                                              rep_src.find("def resolve_arch_dir") + 400]):
                _find(
                    "SRF-4",
                    "resolve_arch_dir() — no path traversal check visible",
                    "MEDIUM",
                    "arch_name from user input is passed to resolve_arch_dir(). "
                    "If the function does not reject '..' or absolute paths, an attacker "
                    "could read arbitrary report directories. "
                    "Remediation: add Path('.').resolve() containment check in resolve_arch_dir.",
                    str(reports_py.relative_to(ROOT)),
                )


# ═══════════════════════════════════════════════════════════════════════════════
# SRF-5  TAclaw crawl surface
# ═══════════════════════════════════════════════════════════════════════════════

def srf5_taclaw_surface() -> None:
    """Check RepoCrawler file type acceptance and environment-injection gap."""
    crawler = ROOT / "chatbot" / "adapters" / "crawler.py"
    prose_adapter = ROOT / "chatbot" / "adapters" / "prose.py"
    taclaw_route = ROOT / "chatbot" / "api" / "routes" / "taclaw.py"

    if not crawler.exists():
        _find("SRF-5", "crawler.py missing", "HIGH",
              "Cannot audit TAclaw crawl surface.", str(crawler))
        return

    crawler_src = crawler.read_text(encoding="utf-8", errors="replace")
    prose_src = prose_adapter.read_text(encoding="utf-8", errors="replace") if prose_adapter.exists() else ""

    # Check 1: Prose adapter accepts markdown/text files
    if re.search(r"\.(md|txt|pdf|docx)", prose_src):
        _find(
            "SRF-5",
            "Prose adapter accepts .md, .txt, .pdf, .docx from crawled repos",
            "HIGH",
            "RepoCrawler ingests README.md, docs/, prose, and YAML files via the prose "
            "adapter. These file types can contain adversarial payloads (e.g., "
            "'Ignore previous instructions...'). No environment-injection check runs "
            "on crawled prose before content enters the TA analysis pipeline. "
            "Gap identified in DECISIONS Entry 178. "
            "Remediation: add a content trust gate on crawled files with source_trust "
            "set from RepoCrawler (external/unverified) before harness submission.",
            str(prose_adapter.relative_to(ROOT)) if prose_adapter.exists() else "chatbot/adapters/prose.py",
        )
    else:
        _find(
            "SRF-5",
            "Prose adapter file type scope unclear",
            "MEDIUM",
            "Could not confirm prose adapter accepts .md/.txt. Manual review needed.",
            str(prose_adapter.relative_to(ROOT)) if prose_adapter.exists() else "",
        )

    # Check 2: source_trust assignment in crawled artifacts
    if "source_trust" not in crawler_src:
        _find(
            "SRF-5",
            "RepoCrawler does not set source_trust on crawled artifacts",
            "HIGH",
            "CrawledArtifact carries no source_trust field. ArchitectureGraph "
            "produced from crawled content defaults to source_trust=unverified (base.py). "
            "check_preflight() in GovernanceAdapter checks source_trust=adversarial but "
            "unverified content bypasses this gate. "
            "Remediation: RepoCrawler should stamp CrawledArtifact.source_trust='external' "
            "and GovernanceAdapter should apply injection check to external-trust content.",
            str(crawler.relative_to(ROOT)),
        )

    # Check 3: MAX_FILES and MAX_FILE_SIZE present (resource limits)
    if "MAX_FILES" in crawler_src and "MAX_FILE_SIZE" in crawler_src:
        m_files = re.search(r"MAX_FILES\s*=\s*(\d+)", crawler_src)
        m_size = re.search(r"MAX_FILE_SIZE\s*=\s*(\d+)\s*\*\s*1024", crawler_src)
        files_val = int(m_files.group(1)) if m_files else "?"
        size_kb = int(m_size.group(1)) if m_size else "?"
        _find(
            "SRF-5",
            f"Resource limits present: MAX_FILES={files_val}, MAX_FILE_SIZE={size_kb}KB",
            "INFO",
            "TAclaw crawl is bounded; DoS via repo size is mitigated.",
            str(crawler.relative_to(ROOT)),
        )
    else:
        _find(
            "SRF-5",
            "MAX_FILES or MAX_FILE_SIZE missing from crawler.py",
            "MEDIUM",
            "Unbounded crawl could exhaust memory on a malicious large repository.",
            str(crawler.relative_to(ROOT)),
        )

    # Check 4: TAclaw route — check_preflight called before harness
    if taclaw_route.exists():
        taclaw_src = taclaw_route.read_text(encoding="utf-8", errors="replace")
        if "check_preflight" in taclaw_src or "_preflight_blocked" in taclaw_src:
            _find(
                "SRF-5",
                "TAclaw route: check_preflight() wired",
                "INFO",
                "Pre-flight authority gate runs before the TA pipeline for TAclaw submissions.",
                str(taclaw_route.relative_to(ROOT)),
            )
        else:
            _find(
                "SRF-5",
                "TAclaw route: check_preflight() not wired",
                "MEDIUM",
                "TAclaw does not explicitly call check_preflight() in the route handler. "
                "The BouncerStage reads ctx['_preflight_blocked'] which must be set by "
                "the adapter layer before the harness runs. "
                "Verify the adapter-layer preflight fires for all TAclaw code paths.",
                str(taclaw_route.relative_to(ROOT)),
            )


# ═══════════════════════════════════════════════════════════════════════════════
# SRF-6  MCP parameter surface (cross-reference)
# ═══════════════════════════════════════════════════════════════════════════════

def srf6_mcp_surface() -> None:
    """Cross-reference MCP surface — detailed audit in mcp-audit; this enumerates coverage."""
    server = ROOT / "mcp_server" / "server.py"
    mcp_audit = ROOT / ".claude" / "skills" / "mcp-audit" / "scripts" / "mcp-audit.py"

    if not server.exists():
        _find("SRF-6", "mcp_server/server.py missing", "HIGH",
              "Cannot enumerate MCP parameter surface.", str(server))
        return

    src = server.read_text(encoding="utf-8", errors="replace")

    # Count @mcp.tool() decorated functions
    tool_count = len(re.findall(r"@mcp\.tool\(\)", src))

    # Check for free-form string params that flow to LLM/crawler
    free_form_hits = re.findall(
        r"def (run_taco_agent|run_taclaw|analyze_architecture|run_expert_review|"
        r"generate_synthetic_architectures|query_ta_brain)",
        src,
    )

    # Check content trust gate
    has_content_trust = "_mcp_content_trust_check" in src
    has_taclaw_gate = "_validate_taclaw_target" in src

    if tool_count > 0:
        _find(
            "SRF-6",
            f"MCP surface: {tool_count} tools exposed; {len(free_form_hits)} accept free-form string input",
            "INFO" if has_content_trust and has_taclaw_gate else "MEDIUM",
            f"Tools with free-form input: {', '.join(free_form_hits)}. "
            f"Content trust gate (_mcp_content_trust_check): {'PRESENT' if has_content_trust else 'MISSING'}. "
            f"TAclaw target gate (_validate_taclaw_target): {'PRESENT' if has_taclaw_gate else 'MISSING'}. "
            "Run mcp-audit for full DIM-2 parameter validation analysis.",
            str(server.relative_to(ROOT)),
        )

    if not mcp_audit.exists():
        _find(
            "SRF-6",
            "mcp-audit skill not found",
            "LOW",
            "Engine Item 12 mcp-audit provides depth on this surface. "
            "Run: python3 .claude/skills/mcp-audit/scripts/mcp-audit.py",
            str(mcp_audit),
        )
    else:
        _find(
            "SRF-6",
            "mcp-audit skill available for MCP depth analysis",
            "INFO",
            "Run mcp-audit for DIM-1 through DIM-6 analysis of the MCP attack surface. "
            "aisurface-audit cross-references; mcp-audit provides depth.",
            str(mcp_audit.relative_to(ROOT)),
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Output
# ═══════════════════════════════════════════════════════════════════════════════

_SEVERITY_ICON = {
    "CRITICAL": "🔴",
    "HIGH":     "🟠",
    "MEDIUM":   "🟡",
    "LOW":      "🔵",
    "INFO":     "✅",
}

_GATE_LABEL = {
    "CRITICAL": "OPEN",
    "HIGH":     "OPEN",
    "MEDIUM":   "PARTIAL",
    "LOW":      "PARTIAL",
    "INFO":     "COVERED",
}

_GAP_LABEL = {
    "CRITICAL": "open",
    "HIGH":     "open",
    "MEDIUM":   "partial",
    "LOW":      "partial",
    "INFO":     "covered",
}


def _surface_worst(surface: str) -> str:
    sev = [f["severity"] for f in FINDINGS if f["surface"] == surface]
    if not sev:
        return "INFO"
    return min(sev, key=lambda s: _SEV_ORDER.get(s, 99))


def print_report() -> None:
    # Sort by severity then surface
    sorted_findings = sorted(
        FINDINGS,
        key=lambda f: (_SEV_ORDER.get(f["severity"], 99), f["surface"]),
    )

    counts: dict[str, int] = {s: 0 for s in _SEV_ORDER}
    for f in sorted_findings:
        counts[f["severity"]] = counts.get(f["severity"], 0) + 1

    print()
    print("═" * 70)
    print("  aisurface-audit — AI Ingest Surface Enumeration  (Engine Item 13)")
    print("═" * 70)
    print()

    # Ranked surface table
    surfaces = ["SRF-1", "SRF-2", "SRF-3", "SRF-4", "SRF-5", "SRF-6"]
    surface_names = {
        "SRF-1": "Prompt surface (mmd_content → LLM)",
        "SRF-2": "Skill script surface (SHA256 manifest)",
        "SRF-3": "Brain JSONL surface (integrity gate)",
        "SRF-4": "Enrichment API surface (/api/v1/enrich)",
        "SRF-5": "TAclaw crawl surface (RepoCrawler)",
        "SRF-6": "MCP parameter surface (18 tools)",
    }
    print(f"{'Surface':<8} {'Name':<42} {'Worst':<10} {'Coverage':<10}")
    print("-" * 70)
    for srf in surfaces:
        worst = _surface_worst(srf)
        icon = _SEVERITY_ICON.get(worst, "")
        gap = _GAP_LABEL.get(worst, "?")
        print(f"{srf:<8} {surface_names[srf]:<42} {icon} {worst:<8} {gap}")
    print()

    # Findings by severity (skip INFO)
    shown = [f for f in sorted_findings if f["severity"] != "INFO"]
    if shown:
        print("── Findings ──────────────────────────────────────────────────────────")
        for f in shown:
            icon = _SEVERITY_ICON.get(f["severity"], "")
            print()
            print(f"  {icon} [{f['severity']}] {f['surface']} — {f['title']}")
            if f["path"]:
                print(f"     Path: {f['path']}")
            # Word-wrap detail at 68 chars
            detail = f["detail"]
            words = detail.split()
            line = "     "
            for w in words:
                if len(line) + len(w) + 1 > 72:
                    print(line)
                    line = "     " + w + " "
                else:
                    line += w + " "
            if line.strip():
                print(line)
        print()

    # Summary
    crit = counts.get("CRITICAL", 0)
    high = counts.get("HIGH", 0)
    med  = counts.get("MEDIUM", 0)
    low  = counts.get("LOW", 0)
    info = counts.get("INFO", 0)
    print("── Summary ───────────────────────────────────────────────────────────")
    print(f"  Critical: {crit}  High: {high}  Medium: {med}  Low: {low}  Info: {info}")
    print()
    if crit or high:
        print("  ❌ Exit 1 — CRITICAL or HIGH findings present.")
    else:
        print("  ✅ Exit 0 — No CRITICAL or HIGH findings.")
    print()


def main() -> int:
    try:
        srf1_prompt_surface()
        srf2_skill_surface()
        srf3_brain_surface()
        srf4_enrichment_surface()
        srf5_taclaw_surface()
        srf6_mcp_surface()
    except Exception as exc:
        print(f"[ERROR] Audit aborted: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        return 2

    print_report()

    worst = min(
        (_SEV_ORDER.get(f["severity"], 99) for f in FINDINGS),
        default=99,
    )
    return 1 if worst <= _SEV_ORDER["HIGH"] else 0


if __name__ == "__main__":
    sys.exit(main())
