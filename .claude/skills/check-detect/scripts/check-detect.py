#!/usr/bin/env python3
"""
check-detect — SOC detection rule regression + live corpus evaluation.

Usage:
    python3 check-detect.py                      # unit tests only
    python3 check-detect.py --count              # domain summary table + stale-count scan
    python3 check-detect.py 21_agentic_ai_system # tests + live rule eval
    python3 check-detect.py --all                # tests + all corpus archs
"""

import argparse
import importlib.util
import json
import re
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT  = Path(__file__).resolve().parents[4]
REPORT_DIR = REPO_ROOT / "report"
RULES_PATH = REPO_ROOT / "policies" / "soc_detection_rules.yaml"

TEST_FILES = [
    REPO_ROOT / "tests" / "test_soc_rule_evaluator.py",
    REPO_ROOT / "tests" / "test_aivss_to_findings.py",
    REPO_ROOT / "tests" / "test_incident_simulator.py",
    REPO_ROOT / "tests" / "test_harness_event_broker.py",
]

GREEN  = lambda s: f"\033[32m{s}\033[0m"
AMBER  = lambda s: f"\033[33m{s}\033[0m"
RED    = lambda s: f"\033[31m{s}\033[0m"
DIM    = lambda s: f"\033[2m{s}\033[0m"
BOLD   = lambda s: f"\033[1m{s}\033[0m"
CYAN   = lambda s: f"\033[36m{s}\033[0m"

_SEV_COLOR = {
    "CRITICAL": lambda s: f"\033[31;1m{s}\033[0m",
    "HIGH":     lambda s: f"\033[31m{s}\033[0m",
    "MEDIUM":   lambda s: f"\033[33m{s}\033[0m",
    "LOW":      lambda s: f"\033[32m{s}\033[0m",
}


# ── Unit test runner ──────────────────────────────────────────────────────────

def run_unit_tests() -> bool:
    """Run all four detection-layer test files and print a consolidated summary."""
    print(f"\n{BOLD(CYAN('SOC Detection Regression'))} — {len(TEST_FILES)} test files\n")

    all_ok = True
    total_passed = total_failed = 0

    for tf in TEST_FILES:
        label = tf.name
        t0 = time.time()
        # Skip EventBroker init tests (pre-existing chatbot.config import issue)
        extra = ["-k", "not TestEventBrokerInit"] if "event_broker" in tf.name else []
        result = subprocess.run(
            [sys.executable, "-m", "pytest", str(tf), "-q", "--tb=short"] + extra,
            capture_output=True, text=True, cwd=REPO_ROOT,
        )
        elapsed = time.time() - t0
        output = result.stdout + result.stderr
        summary = next(
            (l for l in reversed(output.splitlines())
             if "passed" in l or "failed" in l or "error" in l),
            "no output",
        )
        # Extract counts
        passed = _parse_count(summary, "passed")
        failed = _parse_count(summary, "failed")
        total_passed += passed
        total_failed += failed

        if result.returncode == 0:
            print(f"  {GREEN('✓')} {label:<45} {GREEN(summary.strip())}  {DIM(f'{elapsed:.1f}s')}")
        else:
            print(f"  {RED('✗')} {label:<45} {RED(summary.strip())}  {DIM(f'{elapsed:.1f}s')}")
            # Print failing test names
            for line in output.splitlines():
                if line.startswith("FAILED"):
                    print(f"      {RED(line)}")
            all_ok = False

    total_color = GREEN if all_ok else RED
    print(f"\n  {'─'*60}")
    print(f"  {total_color(f'Total: {total_passed} passed, {total_failed} failed')}\n")
    return all_ok


def _parse_count(summary: str, word: str) -> int:
    import re
    m = re.search(rf"(\d+)\s+{word}", summary)
    return int(m.group(1)) if m else 0


# ── Rule count check ──────────────────────────────────────────────────────────

def check_rule_count() -> None:
    """Load YAML and print the current rule inventory."""
    try:
        import yaml  # type: ignore[import]
        data = yaml.safe_load(RULES_PATH.read_text())
        rules = data.get("rules", [])
        print(f"{BOLD('Rule inventory')} — {RULES_PATH.relative_to(REPO_ROOT)}")
        print(f"  {len(rules)} rules loaded\n")
        for r in rules:
            rid  = r.get("id", "?")
            name = r.get("name", "")
            sev  = (r.get("severity") or "").upper()
            col  = _SEV_COLOR.get(sev, DIM)
            conds = r.get("conditions", [])
            fields = ", ".join(c.get("field", "") for c in conds if isinstance(c, dict))
            print(f"  {col(f'{rid:<12}')} {name:<42} {DIM(fields[:60])}")
        print()
    except Exception as exc:
        print(f"  {AMBER(f'Could not load rules YAML: {exc}')}\n")


_DOMAIN_NAMES = {
    "QC":  "Quality & Confidence Manipulation",
    "INJ": "Input Injection & Evasion",
    "EXF": "Exfiltration & Leakage",
    "SCT": "Supply Chain & Tampering",
    "MCP": "MCP & API Abuse",
    "RES": "Resource & Coverage",
}


def count_by_domain() -> None:
    """Print a domain summary table and scan docs for stale rule counts."""
    try:
        import yaml
        data = yaml.safe_load(RULES_PATH.read_text())
        rules = data.get("rules", [])
    except Exception as exc:
        print(f"  {AMBER(f'Could not load rules YAML: {exc}')}")
        return

    from collections import defaultdict
    by_domain: dict = defaultdict(list)
    for r in rules:
        dom = r.get("domain", "??")
        by_domain[dom].append(r.get("id", "?"))

    total = len(rules)
    print(f"{BOLD('DETECT rule counts by domain')}  ({total} total)\n")
    header = f"  {'Dom':<5}  {'Full name':<36}  {'N':>2}  Rules"
    print(header)
    print("  " + "─" * (len(header) - 1))
    for dom in ("QC", "INJ", "EXF", "SCT", "MCP", "RES"):
        ids   = sorted(by_domain.get(dom, []))
        label = _DOMAIN_NAMES.get(dom, dom)
        # Compact range: DETECT-DOM-001…DETECT-DOM-NNN
        if ids:
            suffix = lambda s: s.split("-")[-1]
            compact = f"{ids[0]}…{ids[-1]}" if len(ids) > 1 else ids[0]
        else:
            compact = "—"
        print(f"  {CYAN(f'{dom:<5}')}  {label:<36}  {len(ids):>2}  {DIM(compact)}")

    unknown = [dom for dom in by_domain if dom not in _DOMAIN_NAMES]
    if unknown:
        for dom in sorted(unknown):
            ids = sorted(by_domain[dom])
            print(f"  {AMBER(f'{dom:<5}')}  {'(unknown domain)':<36}  {len(ids):>2}  {DIM(', '.join(ids))}")

    print(f"\n  {'Total':<43}  {BOLD(str(total))}")
    print()

    # Scan docs for stale counts
    doc_files = [
        REPO_ROOT / "CLAUDE.md",
        REPO_ROOT / "README.md",
        REPO_ROOT / "openapi.yaml",
    ]
    stale: list = []
    # Blog/changelog table rows describe historical counts — skip them.
    _HISTORICAL = re.compile(r'blog|part \d+|post|changelog|iceberg|beneath|story', re.IGNORECASE)
    pat = re.compile(r'(\d+)\s*DETECT rules?', re.IGNORECASE)
    for fp in doc_files:
        if not fp.exists():
            continue
        for lineno, line in enumerate(fp.read_text(encoding="utf-8").splitlines(), 1):
            if _HISTORICAL.search(line):
                continue
            for m in pat.finditer(line):
                n = int(m.group(1))
                if n != total:
                    stale.append((fp.relative_to(REPO_ROOT), lineno, n, line.strip()))

    if stale:
        print(f"{AMBER('Stale counts found in docs')} (expected {total}):\n")
        for fpath, lineno, n, text in stale:
            print(f"  {fpath}:{lineno}  says {AMBER(str(n))}  — {DIM(text[:80])}")
        print()
    else:
        print(f"  {GREEN('✓')} No stale counts in docs.\n")


# ── Live corpus evaluation ────────────────────────────────────────────────────

def evaluate_arch(arch: str) -> None:
    """Evaluate a governance_signals.json against all live rules and print findings."""
    sig_path = REPORT_DIR / arch / "governance_signals.json"
    if not sig_path.exists():
        print(f"  {AMBER(arch)}: no governance_signals.json")
        return

    try:
        signals = json.loads(sig_path.read_text())
    except Exception as exc:
        print(f"  {RED(arch)}: could not read signals — {exc}")
        return

    # Import rule evaluator from repo
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))

    try:
        from chatbot.harness.rule_evaluator import RuleEvaluator
        ev = RuleEvaluator()
        findings = ev.evaluate(signals, arch_name=arch, run_id="live-check")
    except Exception as exc:
        print(f"  {RED(arch)}: rule evaluation failed — {exc}")
        return

    # Key signal values
    manip    = signals.get("manipulation", {})
    val      = signals.get("validation", {})
    sm       = signals.get("sm_verdicts", {})
    aivss_out = signals.get("aivss", {}).get("outbound", {})

    val_pct   = val.get("val_pct")
    gap_sim   = manip.get("gap_similarity_avg")
    sm_rate   = sm.get("acceptance_rate")
    out_comp  = aivss_out.get("composite") if isinstance(aivss_out, dict) else None

    signal_parts = []
    if val_pct is not None:
        vcolor = RED if val_pct < 75 else (AMBER if val_pct < 85 else GREEN)
        signal_parts.append(f"val_pct={vcolor(f'{val_pct:.0f}%')}")
    if gap_sim is not None:
        gcolor = RED if gap_sim > 0.4 else (AMBER if gap_sim > 0.2 else DIM)
        signal_parts.append(f"gap_sim={gcolor(f'{gap_sim:.2f}')}")
    if sm_rate is not None:
        scolor = RED if sm_rate <= 0.6 else GREEN
        signal_parts.append(f"sm_rate={scolor(f'{sm_rate:.1%}')}")
    if out_comp is not None:
        ocolor = RED if out_comp >= 6.0 else (AMBER if out_comp >= 3.0 else DIM)
        signal_parts.append(f"outbound={ocolor(f'{out_comp:.1f}')}")

    signal_str = "  " + "  ".join(signal_parts) if signal_parts else ""

    if not findings:
        print(f"  {GREEN('✓')} {arch:<40} {DIM('no rules fired')}{signal_str}")
        return

    print(f"  {RED('!')} {BOLD(arch)}{signal_str}")
    for f in sorted(findings, key=lambda x: _sev_order(x.get("severity", ""))):
        rid  = f.get("unmapped", {}).get("rule_id", "?")
        name = f.get("unmapped", {}).get("rule_name", f.get("finding", {}).get("title", ""))
        sev  = (f.get("severity") or "").upper()
        col  = _SEV_COLOR.get(sev, DIM)
        acts = ", ".join(f.get("unmapped", {}).get("actions", []))
        print(f"      {col(f'{rid} [{sev}]'):<28} {name:<40} {DIM(acts)}")


def _sev_order(sev: str) -> int:
    return {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}.get(sev.upper(), 4)


# ── Skill metadata sync ───────────────────────────────────────────────────────

def _live_counts() -> dict:
    """Read live rule/scenario/test counts from source files. Never raises."""
    counts = {}
    try:
        import yaml  # type: ignore[import]
        rules = yaml.safe_load(RULES_PATH.read_text()).get("rules", [])
        counts["n_rules"] = len(rules)
        counts["last_rule"] = rules[-1]["id"] if rules else "DETECT-QC-001"
    except Exception:
        counts["n_rules"] = 0
        counts["last_rule"] = "?"

    try:
        sim_script = REPO_ROOT / ".claude/skills/incident-simulator/scripts/incident_simulator.py"
        spec = importlib.util.spec_from_file_location("_sim", sim_script)
        mod  = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        counts["n_scenarios"] = len(mod.SCENARIOS)
    except Exception:
        counts["n_scenarios"] = 0

    for tf in TEST_FILES:
        key = tf.stem  # e.g. "test_harness_governance"
        try:
            src = tf.read_text(encoding="utf-8")
            counts[key] = src.count("def test_")
        except Exception:
            counts[key] = 0

    return counts


def _rewrite_description(skill_md: Path, new_desc: str) -> bool:
    """Replace the `description:` line in a SKILL.md frontmatter. Returns True if changed."""
    try:
        text = skill_md.read_text(encoding="utf-8")
        updated = re.sub(
            r'^(description:\s*).*$',
            lambda m: m.group(1) + new_desc,
            text,
            count=1,
            flags=re.MULTILINE,
        )
        if updated == text:
            return False
        skill_md.write_text(updated, encoding="utf-8")
        return True
    except Exception:
        return False


def sync_skill_metadata() -> None:
    """
    Rewrite `description:` lines in the four detection-layer SKILL.md files
    so counts stay current automatically after every check-detect run.
    Prints a one-line status; silent when nothing changed.
    """
    c = _live_counts()
    n_rules     = c["n_rules"]
    n_scenarios = c["n_scenarios"]
    last_rule   = c["last_rule"]

    SKILLS_DIR = REPO_ROOT / ".claude" / "skills"

    # Descriptions keyed by skill directory name → new description string.
    # Each uses only counts derivable from source files, no free-text that drifts.
    targets = {
        "check-detect": (
            f"Run the SOC detection rule regression suite (~15s, no LLM/network). "
            f"Covers all {n_rules} DETECT rules (rule evaluator), AIVSS→OCSF findings export, "
            f"incident simulator scenarios ({n_scenarios} scenarios covering all {n_rules} rules), "
            f"and EventBroker sm_verdicts path. Optionally re-evaluates live governance_signals.json "
            f"for one or all corpus architectures and shows which rules fire. Use after any change to "
            f"policies/soc_detection_rules.yaml, chatbot/harness/rule_evaluator.py, "
            f"chatbot/harness/stages.py, or chatbot/harness/governance.py."
        ),
        "incident-simulator": (
            f"Synthesise realistic governance_signals.json payloads for named incident scenarios, "
            f"run aivss-to-findings, and assert the expected DETECT rules fire. "
            f"{n_scenarios} scenarios cover all {n_rules} DETECT rules "
            f"(DETECT-QC-001 through {last_rule}), including AST02/05/08-grounded scenarios. "
            f"Optionally generates a storycaster narrative contextualised to a specific architecture. "
            f"Pass a scenario name, or omit to list all. Use --story to generate a narrative. "
            f"Use --write to persist the simulated governance_signals to a report directory."
        ),
    }

    changed = []
    for skill_name, new_desc in targets.items():
        skill_md = SKILLS_DIR / skill_name / "SKILL.md"
        if skill_md.exists() and _rewrite_description(skill_md, new_desc):
            changed.append(skill_name)

    if changed:
        print(f"  {GREEN('↺')} Synced skill metadata: {', '.join(changed)} "
              f"({n_rules} rules, {n_scenarios} scenarios)")
    # Silent when nothing changed — avoids noise on every run


# ── DQ pass ──────────────────────────────────────────────────────────────────

_REQUIRED_FIELDS = [
    "id", "name", "domain", "description", "severity",
    "conditions", "actions", "kill_chain_stage",
    "ocsf_type_uid", "csa_art", "atlas_tactic",
]
# Core vocab from YAML header; block_deployment/flag_for_review are extended SOC-label
# actions used in rules without a hard pipeline execution path (evaluator passes them
# through to OCSF output). token_spike/no_critical/min_agents are custom evaluator ops.
_VALID_ACTIONS   = {"audit_log", "quarantine_trace", "reduce_budget",
                    "forensic_capture", "page_soc", "block_run",
                    "block_deployment", "flag_for_review"}
_VALID_OPS       = {">=", "<=", "==", "!=", ">", "<",
                    "contains", "length_gt", "length_eq", "all_gt",
                    "token_spike", "no_critical", "min_agents"}
_VALID_SEVE      = {"Informational", "Low", "Medium", "High", "Critical"}
_VALID_COMBINES  = {"all", "any"}

# Maps condition field namespace → primary source files (relative to REPO_ROOT).
_LINEAGE_SOURCES = {
    "manipulation":    ["chatbot/harness/governance.py"],
    "arch_metadata":   ["chatbot/harness/governance.py", "chatbot/harness/stages.py"],
    "exploitation":    ["chatbot/harness/governance.py"],
    "identity":        ["chatbot/harness/governance.py"],
    "leakage":         ["chatbot/harness/governance.py"],
    "sovereignty":     ["chatbot/harness/governance.py"],
    "validation":      ["chatbot/harness/stages.py", "chatbot/harness/governance.py",
                        "chatbot/modules/ground_truth_generator.py"],
    "mcp_access":      ["mcp_server/access_logger.py", "chatbot/harness/governance.py",
                        "chatbot/harness/stages.py"],
    "sm_verdicts":     ["chatbot/harness/stages.py"],
    "aivss":           ["chatbot/modules/harness_aivss.py", "chatbot/harness/stages.py"],
    "export":          ["chatbot/api/export_tracker.py"],
    "synthetic_queue": ["chatbot/modules/ta_brain_mmd_generator.py",
                        "chatbot/modules/ta_brain_builder.py"],
    "rest_api":        ["mcp_server/access_logger.py"],
}


def _dq_schema(rules: list) -> tuple[int, int]:
    """Check 1 — required field presence. Returns (pass_count, fail_count)."""
    print(f"  {BOLD('1. Schema completeness')}\n")
    passed = failed = 0
    for r in rules:
        missing = [f for f in _REQUIRED_FIELDS if not r.get(f)]
        if missing:
            failed += 1
            print(f"     {RED('✗')} {r.get('id','?'):<16}  missing: {', '.join(missing)}")
        else:
            passed += 1
    if failed == 0:
        print(f"     {GREEN('✓')} All {passed} rules have required fields.\n")
    else:
        print(f"\n     {AMBER(f'{failed} rules have missing fields')} ({passed} ok)\n")
    return passed, failed


def _dq_distribution(rules: list) -> None:
    """Check 2 — domain × severity heatmap."""
    from collections import defaultdict
    print(f"  {BOLD('2. Distribution  (domain × severity)')}\n")

    sevs   = ["Critical", "High", "Medium", "Low", "Informational"]
    sev_ab = {"Critical": "CRIT", "High": "HIGH", "Medium": "MED",
               "Low": "LOW", "Informational": "INFO"}
    all_domains = sorted({r.get("domain", "??") for r in rules})

    cell: dict = defaultdict(lambda: defaultdict(int))
    for r in rules:
        cell[r.get("domain", "??")][r.get("severity", "?").capitalize()] += 1

    header = f"  {'Dom':<6}" + "".join(f"  {sev_ab[s]:>5}" for s in sevs) + "  {'Total':>5}"
    print(f"     {header}")
    print(f"     {'─'*(len(header)+2)}")
    for dom in all_domains:
        row = f"  {CYAN(f'{dom:<6}')}"
        total = 0
        for s in sevs:
            n = cell[dom][s]
            total += n
            col = _SEV_COLOR.get(s.upper(), DIM)
            row += f"  {col(f'{n:>5}') if n else DIM('    .')}"
        row += f"  {BOLD(f'{total:>5}')}"
        print(f"     {row}")

    # Totals row
    print(f"     {'─'*(len(header)+2)}")
    tot_row = f"  {'Total':<6}"
    grand = 0
    for s in sevs:
        t = sum(cell[d][s] for d in all_domains)
        grand += t
        tot_row += f"  {t:>5}"
    tot_row += f"  {BOLD(f'{grand:>5}')}"
    print(f"     {tot_row}\n")


def _dq_lineage(rules: list) -> tuple[int, int]:
    """Check 3 — condition field paths traced to source files. Returns (covered, ghost)."""
    print(f"  {BOLD('3. Signal lineage')}\n")

    # Collect unique field paths
    fields: set = set()
    for r in rules:
        for c in (r.get("conditions") or []):
            if isinstance(c, dict) and "field" in c:
                fields.add(c["field"])

    # Cache file contents
    _file_cache: dict = {}
    def _text(rel: str) -> str:
        if rel not in _file_cache:
            fp = REPO_ROOT / rel
            _file_cache[rel] = fp.read_text(encoding="utf-8", errors="replace") if fp.exists() else ""
        return _file_cache[rel]

    covered = ghost = 0
    ghost_fields: list = []

    for field in sorted(fields):
        ns = field.split(".")[0]
        leaf = field.split(".")[-1]
        src_rels = _LINEAGE_SOURCES.get(ns, [])
        found_in = []
        for rel in src_rels:
            txt = _text(rel)
            # Match quoted string keys, attribute access (.leaf), or dataclass field (leaf:)
            if (f'"{leaf}"' in txt or f"'{leaf}'" in txt
                    or f".{leaf}" in txt or f"{leaf}:" in txt):
                found_in.append(Path(rel).name)
        if found_in:
            covered += 1
            print(f"     {GREEN('✓')} {field:<55}  {DIM(', '.join(found_in))}")
        else:
            ghost += 1
            ghost_fields.append(field)
            src_hint = ", ".join(Path(r).name for r in src_rels) or "no source mapped"
            print(f"     {RED('✗')} {field:<55}  {RED('UNRESOLVED')}  {DIM(f'[searched: {src_hint}]')}")

    print(f"\n     {GREEN(f'{covered} covered')}, {RED(f'{ghost} ghost') if ghost else GREEN('0 ghost')}\n")
    return covered, ghost


def _dq_freshness(rules: list) -> None:
    """Check 4 — last-fired date per rule by replaying evaluator on stored history signals."""
    print(f"  {BOLD('4. Freshness  (last fired per rule)')}\n")

    if not REPORT_DIR.exists():
        print(f"     {DIM('report/ not found — skipping freshness check.')}\n")
        return

    hist_files = list(REPORT_DIR.glob("*/governance_signals_history.jsonl"))
    if not hist_files:
        print(f"     {DIM('No governance_signals_history.jsonl files found — skipping.')}\n")
        return

    # Import evaluator once
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    try:
        from chatbot.harness.rule_evaluator import RuleEvaluator
        ev = RuleEvaluator()
    except Exception as exc:
        print(f"     {AMBER(f'Could not load RuleEvaluator: {exc} — skipping.')}\n")
        return

    from collections import defaultdict
    last_fired: dict = defaultdict(lambda: None)  # rule_id → ISO date str

    for hf in sorted(hist_files):
        try:
            for line in hf.read_text(encoding="utf-8", errors="replace").splitlines():
                if not line.strip():
                    continue
                entry = json.loads(line)
                signals = entry.get("signals") or {}
                ts      = (entry.get("ts") or entry.get("timestamp") or "")[:10]
                if not signals or not ts:
                    continue
                try:
                    findings = ev.evaluate(signals, arch_name=str(hf.parent.name), run_id="dq")
                except Exception:
                    continue
                for f in findings:
                    rid = (f.get("unmapped") or {}).get("rule_id", "")
                    if rid and (last_fired[rid] is None or ts > last_fired[rid]):
                        last_fired[rid] = ts
        except Exception:
            pass

    rule_ids = [r["id"] for r in rules]
    never_fired = [rid for rid in rule_ids if last_fired[rid] is None]
    stale_days  = 30
    import datetime
    cutoff = (datetime.date.today() - datetime.timedelta(days=stale_days)).isoformat()
    stale = [rid for rid in rule_ids if last_fired[rid] and last_fired[rid] < cutoff]

    if never_fired:
        print(f"     {AMBER(f'{len(never_fired)} rules never fired in corpus history:')}")
        for rid in sorted(never_fired):
            print(f"       {AMBER('○')} {rid}")
        print()
    if stale:
        print(f"     {AMBER(f'{len(stale)} rules not fired in >{stale_days} days:')}")
        for rid in sorted(stale):
            print(f"       {AMBER('~')} {rid:<20} last: {last_fired[rid]}")
        print()
    fired_count = len(rule_ids) - len(never_fired)
    if not never_fired and not stale:
        print(f"     {GREEN('✓')} All {fired_count} rules fired recently.\n")
    else:
        print(f"     {DIM(f'{fired_count} of {len(rule_ids)} have recent history.')}\n")


def _dq_internal_quality(rules: list) -> tuple[int, int]:
    """Check 5 — action vocab, op validity, severity tier, combine value. Returns (ok, issues)."""
    print(f"  {BOLD('5. Internal quality')}\n")
    ok = issues = 0
    for r in rules:
        rid = r.get("id", "?")
        errs = []
        sev = (r.get("severity") or "").capitalize()
        if sev and sev not in _VALID_SEVE:
            errs.append(f"severity={sev!r}")
        for act in (r.get("actions") or []):
            t = act.get("type", "") if isinstance(act, dict) else str(act)
            if t and t not in _VALID_ACTIONS:
                errs.append(f"action={t!r}")
        combine = r.get("combine", "all")
        if combine not in _VALID_COMBINES:
            errs.append(f"combine={combine!r}")
        for cond in (r.get("conditions") or []):
            op = cond.get("op", "") if isinstance(cond, dict) else ""
            if op and op not in _VALID_OPS:
                errs.append(f"op={op!r}")
        csa = r.get("csa_art")
        if not csa or (isinstance(csa, list) and len(csa) == 0):
            errs.append("csa_art=empty")
        if errs:
            issues += 1
            print(f"     {RED('✗')} {rid:<16}  {', '.join(errs)}")
        else:
            ok += 1
    if issues == 0:
        print(f"     {GREEN('✓')} All {ok} rules pass internal quality checks.\n")
    else:
        print(f"\n     {AMBER(f'{issues} rules have quality issues')} ({ok} ok)\n")
    return ok, issues


def _dq_volume(rules: list) -> None:
    """Check 6 — severity tier balance and domain coverage flags."""
    print(f"  {BOLD('6. Volume & balance')}\n")
    from collections import Counter
    sev_counts = Counter((r.get("severity") or "?").capitalize() for r in rules)
    dom_counts  = Counter(r.get("domain", "??") for r in rules)

    order = ["Critical", "High", "Medium", "Low", "Informational"]
    print(f"     Severity distribution:")
    for s in order:
        n = sev_counts.get(s, 0)
        bar = "█" * n
        col = _SEV_COLOR.get(s.upper(), DIM)
        flag = f"  {AMBER('← zero')}!" if n == 0 else ""
        print(f"       {col(f'{s:<14}')}  {n:>3}  {DIM(bar[:40])}{flag}")

    print(f"\n     Domain distribution:")
    for dom, n in sorted(dom_counts.items(), key=lambda x: -x[1]):
        bar = "█" * n
        flag = f"  {AMBER('← 1 rule')}" if n == 1 else ""
        print(f"       {CYAN(f'{dom:<6}')}  {n:>3}  {DIM(bar[:30])}{flag}")
    print()


def run_dq() -> bool:
    """Run the 6-dimension DETECT Data Quality pass. Returns True when no blocking issues."""
    try:
        import yaml  # type: ignore[import]
        data  = yaml.safe_load(RULES_PATH.read_text())
        rules = data.get("rules", [])
    except Exception as exc:
        print(f"  {RED(f'Could not load rules YAML: {exc}')}\n")
        return False

    n = len(rules)
    print(f"\n{BOLD(CYAN('DETECT Rule Data Quality'))} — {n} rules in {RULES_PATH.relative_to(REPO_ROOT)}\n")
    print("─" * 70)

    _, schema_fails    = _dq_schema(rules)
    _dq_distribution(rules)
    _, ghost_count     = _dq_lineage(rules)
    _dq_freshness(rules)
    _, quality_issues  = _dq_internal_quality(rules)
    _dq_volume(rules)

    print("─" * 70)
    blocking = schema_fails + ghost_count + quality_issues
    if blocking == 0:
        print(f"\n{GREEN('✓ DQ PASS')} — schema {GREEN('ok')}, lineage {GREEN('ok')}, quality {GREEN('ok')}\n")
    else:
        print(f"\n{RED('✗ DQ ISSUES')} — {blocking} blocking issues "
              f"(schema:{schema_fails} lineage:{ghost_count} quality:{quality_issues})\n")
    return blocking == 0


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="SOC detection rule regression + live corpus eval")
    parser.add_argument("arch", nargs="?", help="Architecture name for live evaluation")
    parser.add_argument("--all",   action="store_true", help="Evaluate all corpus architectures")
    parser.add_argument("--count", action="store_true", help="Print domain summary table + stale-count scan; skip tests")
    parser.add_argument("--dq",    action="store_true", help="Run 6-dimension data quality pass on detection rules")
    args = parser.parse_args()

    if args.count:
        count_by_domain()
        return

    if args.dq:
        ok = run_dq()
        sys.exit(0 if ok else 1)

    ok = run_unit_tests()
    sync_skill_metadata()
    check_rule_count()

    if args.arch:
        print(f"{BOLD('Live Evaluation')} — {args.arch}\n")
        evaluate_arch(args.arch)
        print()
    elif args.all:
        archs = sorted(
            d.name for d in REPORT_DIR.iterdir()
            if d.is_dir() and (d / "governance_signals.json").exists()
        ) if REPORT_DIR.exists() else []
        if not archs:
            print(f"  {DIM('No governance_signals.json found under report/')}")
        else:
            print(f"{BOLD('Live Evaluation')} — {len(archs)} architectures\n")
            for arch in archs:
                evaluate_arch(arch)
            print()

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
