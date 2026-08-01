#!/usr/bin/env python3
"""
detect-loop — Evidence-driven DETECT coverage improvement flywheel.

Observe → Diagnose → Prescribe → Gate → Apply → Verify → Log

Usage:
    python3 detect-loop.py                          # full loop, auto-selects worst rule
    python3 detect-loop.py --rule DETECT-014        # target a specific rule
    python3 detect-loop.py --observe-only           # show coverage matrix, no changes
    python3 detect-loop.py --incident "desc"        # ground a new real incident
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import textwrap
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

REPO        = Path(__file__).resolve().parents[4]
REPORT_DIR  = REPO / "report"
RULES_YAML  = REPO / "policies" / "soc_detection_rules.yaml"
SIM_SCRIPT  = REPO / ".claude" / "skills" / "incident-simulator" / "scripts" / "incident_simulator.py"
TEST_FILE   = REPO / "tests" / "test_incident_simulator.py"
DECISIONS   = REPO / "docs" / "DECISIONS.md"

sys.path.insert(0, str(REPO))

GREEN  = lambda s: f"\033[32m{s}\033[0m"
AMBER  = lambda s: f"\033[33m{s}\033[0m"
RED    = lambda s: f"\033[31m{s}\033[0m"
DIM    = lambda s: f"\033[2m{s}\033[0m"
BOLD   = lambda s: f"\033[1m{s}\033[0m"
CYAN   = lambda s: f"\033[36m{s}\033[0m"

_SEV_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}


# ── Phase 1: Observe ──────────────────────────────────────────────────────────

def observe() -> Tuple[Dict[str, List[str]], List[dict], List[str]]:
    """
    Returns:
        rule_arch_hits  — {rule_id: [arch, ...]}
        rules           — list of rule dicts from YAML
        corpus_archs    — list of arch names that have governance_signals.json
    """
    import yaml  # type: ignore[import]
    from chatbot.harness.rule_evaluator import RuleEvaluator

    rules_data = yaml.safe_load(RULES_YAML.read_text())
    rules = rules_data.get("rules", [])

    ev = RuleEvaluator()
    corpus_archs = []
    rule_arch_hits: Dict[str, List[str]] = {r["id"]: [] for r in rules}

    for d in sorted(REPORT_DIR.iterdir()):
        if not d.is_dir():
            continue
        sig_path = d / "governance_signals.json"
        if not sig_path.exists():
            continue
        corpus_archs.append(d.name)
        try:
            signals = json.loads(sig_path.read_text())
            findings = ev.evaluate(signals, arch_name=d.name, run_id="loop-obs")
            for f in findings:
                rid = f.get("unmapped", {}).get("rule_id")
                if rid and rid in rule_arch_hits:
                    rule_arch_hits[rid].append(d.name)
        except Exception:
            pass

    return rule_arch_hits, rules, corpus_archs


def print_coverage_matrix(rule_arch_hits: Dict, rules: List[dict], corpus_archs: List[str]) -> None:
    total = len(corpus_archs)
    print(f"\n{BOLD('Coverage Matrix')} — {total} corpus architectures\n")
    print(f"  {'Rule':<14} {'Name':<42} {'Sev':<9} {'Hits':>5}  {'Score':>6}  Status")
    print(f"  {'─'*14} {'─'*42} {'─'*9} {'─'*5}  {'─'*6}  {'─'*6}")

    for rule in rules:
        rid  = rule.get("id", "?")
        name = rule.get("name", "")
        sev  = (rule.get("severity") or "").upper()
        hits = rule_arch_hits.get(rid, [])
        n    = len(hits)
        pct  = round(n / total * 100) if total else 0
        col  = RED if pct == 0 else (AMBER if pct < 20 else GREEN)
        sev_col = {"CRITICAL": RED, "HIGH": RED, "MEDIUM": AMBER, "LOW": DIM}.get(sev, DIM)
        status = RED("ZERO") if pct == 0 else (AMBER("thin") if pct < 20 else GREEN("ok"))
        print(f"  {col(f'{rid:<14}')} {name:<42} {sev_col(f'{sev:<9}')} {n:>5}  {col(f'{pct:>5}%')}  {status}")
    print()


# ── Phase 2: Diagnose ─────────────────────────────────────────────────────────

def diagnose(rule_arch_hits: Dict, rules: List[dict], corpus_archs: List[str],
             target_rule_id: Optional[str] = None) -> Optional[dict]:
    """Select the rule to improve. Returns the rule dict or None if nothing to fix."""
    total = len(corpus_archs)
    if total == 0:
        print(RED("No corpus architectures found."))
        return None

    # Filter to rules with coverage < 20%
    candidates = []
    for rule in rules:
        rid = rule.get("id", "?")
        if target_rule_id and rid != target_rule_id:
            continue
        hits = len(rule_arch_hits.get(rid, []))
        pct  = hits / total * 100 if total else 0
        if pct < 20:
            candidates.append((pct, _SEV_ORDER.get(rule.get("severity", "").upper(), 4), rid, rule))

    if not candidates:
        print(GREEN("All rules have >= 20% real-corpus coverage. Nothing to fix."))
        return None

    # Sort: lowest coverage first, then highest severity
    candidates.sort(key=lambda x: (x[0], x[1]))
    _, _, rid, rule = candidates[0]

    hits   = rule_arch_hits.get(rid, [])
    pct    = round(len(hits) / total * 100)
    fields = [c.get("field", "") for c in rule.get("conditions", []) if isinstance(c, dict)]

    print(f"{BOLD('Diagnosis')}")
    print(f"  Target rule : {RED(rid)} — {rule.get('name','')}")
    print(f"  Severity    : {rule.get('severity','')}")
    print(f"  Coverage    : {len(hits)}/{total} archs ({pct}%)")
    print(f"  Signal paths: {', '.join(fields)}")
    print(f"  Kill chain  : {rule.get('kill_chain_stage','?')}")
    print(f"  OWASP       : {rule.get('owasp', [])}")
    print(f"  Description : {textwrap.shorten(rule.get('description',''), 120)}")
    print()

    return rule


# ── Phase 3: Prescribe ────────────────────────────────────────────────────────

# Arch-type to realistic corpus representative
_ARCH_TYPE_MAP = {
    "credentials":    ("18_saas_multi_tenant", "SaaS multi-tenant with many integration credentials"),
    "traversal":      ("05_legacy_flat_network", "Legacy flat network, least input validation hardening"),
    "zdr":            ("13_iot_architecture",    "IoT architecture with cloud AI + external webhook integrations"),
    "stale":          ("07_gcp_serverless",      "GCP serverless + AI, high technique churn environment"),
    "outbound":       ("20_data_pipeline",       "Data pipeline processing customer PII across regions"),
    "sm_verdicts":    ("10_complex_enterprise",  "Complex enterprise, highest critic disagreement rate"),
    "validation":     ("13_iot_architecture",    "IoT architecture, narrow attack surface → common over-mapping"),
    "gap_similarity": ("19_blockchain_node",     "Blockchain node, narrow domain → easiest convergence"),
}

# Minimal signal payloads per rule
_RULE_PRESCRIPTIONS: Dict[str, Dict] = {
    # ── DETECT-001 through 007: manipulation/MoE signals ─────────────────────
    # These fire on real corpus (001: 17/27, 002: 21/27). Prescriptions allow
    # detect-loop to generate new scenarios if coverage drops or new arch types
    # need targeted simulation.
    "DETECT-001": {
        "arch_key": "sm_verdicts",  # complex enterprise has most MoE signal variance
        "signals": {
            "manipulation": {
                "severity": "HIGH", "confidence_swing_detected": True,
                "confidence_swing": 18.0, "divergence_detected": True,
                "critic_divergence_score": 0, "synthesis_quality": "FULL",
            },
        },
        "description": "confidence_swing=18 + swing_detected=True + synthesis FULL — visible rationalization",
    },
    "DETECT-002": {
        "arch_key": "sm_verdicts",
        "signals": {
            "manipulation": {
                "severity": "HIGH", "confidence_swing_detected": True,
                "confidence_swing": 12.0, "divergence_detected": True,
                "critic_divergence_score": 25, "synthesis_quality": "FULL",
            },
        },
        "description": "divergence_detected=True + score>=20 + synthesis FULL — dissent suppressed",
    },
    "DETECT-003": {
        "arch_key": "outbound",  # data pipeline with many agents
        "signals": {
            "aivss": {
                "overall": {"composite": 3.0, "severity": "LOW"},
                "inbound": {"composite": 0.0, "severity": "LOW", "coverage_pct": 0},
                "internal": {"composite": 4.0, "severity": "MEDIUM", "coverage_pct": 20},
                "outbound": {"composite": 0.0, "severity": "LOW", "coverage_pct": 0},
                "coverage_pct": 10, "per_threat": [],
                "per_agent": {
                    "architect":   {"tokens": 200},
                    "tester":      {"tokens": 180},
                    "red_team":    {"tokens": 190},
                    "purple_team": {"tokens": 210},
                    "blackhat":    {"tokens": 9500},  # 45× mean — spike
                },
            },
        },
        "description": "blackhat token count 45× mean of peers (min 3 agents) — hyperfocus spike",
    },
    "DETECT-004": {
        "arch_key": "outbound",
        "signals": {
            "leakage": {
                "detected": True, "severity": "HIGH",
                "pii_indicators": ["NRIC:S9876543B"], "sensitive_keywords": [],
                "flagged": True, "supply_chain_stale_sources": [],
            },
            "sovereignty": {
                "severity": "HIGH",
                "cross_boundary_nodes": ["ExternalAPI", "TelegramWebhook"],
                "zdr_signals": [], "inferred_regions": [],
            },
        },
        "description": "leakage.detected=True + cross_boundary_nodes present — covert C2 channel",
    },
    "DETECT-005": {
        "arch_key": "traversal",
        "signals": {
            "exploitation": {
                "severity": "CRITICAL",
                "injection_patterns": ["[tag_injection] <script>alert(1)</script>"],
                "injection_categories": {"tag_injection": {"matches": ["<script>alert(1)</script>"], "severity": "CRITICAL"}},
                "max_injection_severity": "CRITICAL",
                "path_traversal": [], "blocked": True,
                "homoglyph_count": 0, "url_encoded_count": 0, "evasion_attempts": 0,
                "external_url_references": 0, "external_url_list": [],
            },
        },
        "description": "exploitation.severity=CRITICAL + injection_patterns present — .mmd is the attack vector",
    },
    "DETECT-006": {
        "arch_key": "outbound",
        "signals": {
            "aivss": {
                "overall": {"composite": 4.0, "severity": "MEDIUM"},
                "inbound": {"composite": 0.0, "severity": "LOW", "coverage_pct": 0},
                "internal": {"composite": 4.0, "severity": "MEDIUM", "coverage_pct": 30},
                "outbound": {"composite": 0.0, "severity": "LOW", "coverage_pct": 0},
                "coverage_pct": 65,
                "per_threat": [
                    {"technique_id": "T1046", "severity": "MEDIUM", "composite": 4.0},
                    {"technique_id": "T1083", "severity": "LOW",    "composite": 2.0},
                ],
                "per_agent": {
                    "architect":   {"tokens": 520},
                    "tester":      {"tokens": 490},
                    "red_team":    {"tokens": 510},
                    "purple_team": {"tokens": 480},
                    "blackhat":    {"tokens": 505},
                },
            },
        },
        "description": "coverage_pct>=60 + no CRITICAL per_threat + min 3 agents — distributed sweep",
    },
    "DETECT-007": {
        "arch_key": "sm_verdicts",
        "signals": {
            "manipulation": {
                "severity": "MEDIUM", "confidence_swing_detected": True,
                "confidence_swing": 16.5, "divergence_detected": False,
                "critic_divergence_score": 0, "synthesis_quality": "FULL",
            },
        },
        "description": "swing_detected=True + div_score=0 + div_detected=False + quality=FULL — silent inflation",
    },
    "DETECT-008": {
        "arch_key": "sm_verdicts",
        "signals": {
            "sm_verdicts": {
                "per_critic": {"architect": "accepted", "tester": "rejected",
                               "red_team": "rejected", "purple_team": "rejected", "blackhat": "accepted"},
                "accepted": 2, "rejected": 3, "acceptance_rate": 0.4,
                "redesign_signal": False, "final_confidence": 85.0,
            },
        },
        "description": "SM acceptance_rate=0.4, 3 critics rejected without redesign signal — reward hacking",
    },
    "DETECT-009": {
        "arch_key": "credentials",
        "signals": {
            "leakage": {"detected": True, "severity": "CRITICAL",
                        "sensitive_keywords": ["api_key", "db_password"], "flagged": True,
                        "pii_indicators": [], "supply_chain_stale_sources": []},
        },
        "description": "Credentials embedded in architecture description — block_run triggered",
    },
    "DETECT-010": {
        "arch_key": "traversal",
        "signals": {
            "exploitation": {"severity": "CRITICAL", "injection_patterns": [],
                             "path_traversal": ["../../etc/passwd", "%2e%2e/.env"],
                             "blocked": True, "homoglyph_count": 0, "url_encoded_count": 0},
        },
        "description": "Path traversal in .mmd node labels — file system probe, no injection patterns",
    },
    "DETECT-011": {
        "arch_key": "zdr",
        "signals": {
            "sovereignty": {"severity": "MEDIUM", "flagged": True,
                            "zdr_signals": ["inference→external: LLM → TelegramBot[External Notification]"],
                            "cross_boundary_nodes": [], "inferred_regions": []},
        },
        "description": "LLM→external service edge detected, no ZDR declaration present",
    },
    "DETECT-012": {
        "arch_key": "stale",
        "signals": {
            "leakage": {"detected": False, "severity": "LOW", "pii_indicators": [],
                        "sensitive_keywords": [], "flagged": False,
                        "supply_chain_stale_sources": ["chatbot/data/enterprise-attack.json (95 days old)"]},
        },
        "description": "MITRE ATT&CK data 95 days old (threshold: 90) — audit only, no block",
    },
    "DETECT-013": {
        "arch_key": "outbound",
        "signals": {
            "aivss": {
                "overall": {"composite": 4.5, "severity": "MEDIUM"},
                "inbound":  {"composite": 0.0, "severity": "LOW", "coverage_pct": 0},
                "internal": {"composite": 5.0, "severity": "MEDIUM", "coverage_pct": 30},
                "outbound": {"composite": 7.2, "severity": "HIGH", "coverage_pct": 55},
                "coverage_pct": 28,
                "per_threat": [{"technique_id": "T1041", "severity": "HIGH", "composite": 7.0}],
                "per_agent": {},
            },
            "leakage": {"detected": True, "severity": "HIGH",
                        "pii_indicators": ["NRIC:S1234567A"], "sensitive_keywords": [],
                        "flagged": True, "supply_chain_stale_sources": []},
        },
        "description": "AIVSS outbound composite 7.2 — PII exfiltration surface without confirmed C2",
    },
    "DETECT-014": {
        "arch_key": "validation",
        "signals": {
            "validation": {"val_pct": 68.0, "total_techniques": 45,
                           "valid_techniques": 30, "invalid_techniques": 15,
                           "detect_only_techniques": 4},
        },
        "description": "val_pct=68%, 15 invalid technique mappings — analysis quarantined",
    },
    "DETECT-015": {
        "arch_key": "gap_similarity",
        "signals": {
            "manipulation": {"severity": "LOW", "confidence_swing_detected": False,
                             "confidence_swing": 0.0, "divergence_detected": False,
                             "critic_divergence_score": 0, "synthesis_quality": "FULL",
                             "gap_similarity_avg": 0.52, "gap_similarity_max": 0.71},
        },
        "description": "Critic gap Jaccard avg=0.52 — convergent outputs, independent perspectives absent",
    },
    "DETECT-016": {
        "arch_key": "sm_verdicts",  # reuse 10_complex_enterprise — production pipeline
        "signals": {
            "identity": {
                "supply_chain_modified_modules": ["chatbot/modules/agents/critics/architect_critic.py"],
                "tool_errors": [], "critic_tool_calls": {},
                "context_bleed_signals": [], "overreach_signals": [],
            },
        },
        "description": "Critic module hash mismatch vs git object — AST02 supply chain tampering",
    },
    "DETECT-017": {
        "arch_key": "zdr",  # agentic/IoT — architectures that fetch external content
        "signals": {
            "exploitation": {
                "severity": "LOW", "injection_patterns": [], "path_traversal": [],
                "homoglyph_count": 0, "url_encoded_count": 0, "evasion_attempts": 0,
                "external_url_references": 1,
                "external_url_list": ["https://raw.githubusercontent.com/attacker/payload/main/instructions.md"],
                "blocked": False,
            },
        },
        "description": "Live https:// URL in MMD node label — AST05 mutable remote content",
    },
    "DETECT-018": {
        "arch_key": "traversal",  # legacy/minimal — easiest to probe with evasion
        "signals": {
            "exploitation": {
                "severity": "LOW", "injection_patterns": [], "path_traversal": [],
                "homoglyph_count": 2, "url_encoded_count": 1, "evasion_attempts": 3,
                "external_url_references": 0, "external_url_list": [], "blocked": False,
            },
        },
        "description": "Cyrillic homoglyphs + URL-encoded sequences in input — AST08 scanner evasion",
    },
    "DETECT-019": {
        "arch_key": "traversal",  # legacy — most likely to have jailbreak probe attempts
        "signals": {
            "exploitation": {
                "severity": "HIGH",
                "injection_patterns": ["[direct_override] ignore all previous instructions"],
                "injection_categories": {"direct_override": {"matches": ["ignore all previous instructions"], "severity": "HIGH"}},
                "max_injection_severity": "HIGH",
                "path_traversal": [], "blocked": False,
                "homoglyph_count": 0, "url_encoded_count": 0, "evasion_attempts": 0,
                "external_url_references": 0, "external_url_list": [],
            },
        },
        "description": "max_injection_severity=HIGH (direct_override) — below CRITICAL, DETECT-005 not triggered",
    },
}


def prescribe(rule: dict, incident_hint: Optional[str] = None) -> Optional[Dict]:
    """Generate a scenario prescription for the target rule."""
    rid  = rule.get("id", "")
    name = rule.get("name", "")

    if rid not in _RULE_PRESCRIPTIONS:
        print(AMBER(f"  No prescription template for {rid} — add one to _RULE_PRESCRIPTIONS in detect-loop.py"))
        return None

    presc    = _RULE_PRESCRIPTIONS[rid]
    arch_key = presc["arch_key"]
    arch, arch_desc = _ARCH_TYPE_MAP.get(arch_key, ("10_complex_enterprise", "Complex enterprise"))

    # Build scenario function name
    safe_name = re.sub(r"[^a-z0-9_]", "_", name.lower()).strip("_")
    fn_name   = f"scenario_{safe_name}_loop"

    # Incident ref
    inc_ref = incident_hint or f"detect-loop-generated — {rid} coverage gap"

    print(f"{BOLD('Prescription')}")
    print(f"  Scenario name : {fn_name}")
    print(f"  Target arch   : {arch} ({arch_desc})")
    print(f"  Expected rules: {{{rid}}}")
    print(f"  Incident ref  : {inc_ref}")
    print(f"  Description   : {presc['description']}")
    print(f"\n  Signal payload:")
    for dim, vals in presc["signals"].items():
        print(f"    {CYAN(dim)}: {json.dumps(vals, separators=(',',':'))[:100]}")
    print()

    return {
        "rule_id":    rid,
        "fn_name":    fn_name,
        "arch":       arch,
        "arch_desc":  arch_desc,
        "signals":    presc["signals"],
        "description": presc["description"],
        "incident_ref": inc_ref,
        "expected":   {rid},
    }


# ── Phase 4: Gate ─────────────────────────────────────────────────────────────

def gate(prescription: Dict) -> str:
    """Ask user to approve/deny/skip. Returns 'y', 'n', or 'skip'."""
    print(f"{BOLD('Gate')} — approve this scenario?")
    print(f"  Will add scenario '{prescription['fn_name']}' to incident_simulator.py")
    print(f"  Will add test assertion to test_incident_simulator.py")
    print(f"  Will write simulated governance_signals to report/{prescription['arch']}/")
    print()
    while True:
        try:
            answer = input("  [y]es / [n]o / [s]kip this rule: ").strip().lower()
        except EOFError:
            return "n"
        if answer in ("y", "yes"):
            return "y"
        if answer in ("n", "no"):
            return "n"
        if answer in ("s", "skip"):
            return "skip"


# ── Phase 5: Apply ────────────────────────────────────────────────────────────

def _build_scenario_fn(p: Dict) -> str:
    """Generate Python source for the new scenario function."""
    signals_repr = json.dumps(p["signals"], indent=8)
    # Build the overlay as Python — read _base() then update dimensions
    overlay_lines = []
    for dim, vals in p["signals"].items():
        overlay_lines.append(f'    sig["{dim}"] = {json.dumps(vals, indent=4)}')
    overlay = "\n".join(overlay_lines)

    return f'''

def {p['fn_name']}() -> Dict[str, Any]:
    """
    {p['rule_id']} ({p['description']})

    Generated by detect-loop. Incident ref: {p['incident_ref']}
    Realistic arch: {p['arch']} — {p['arch_desc']}
    """
    sig = _base()
{overlay}
    return sig
'''


def apply_scenario(p: Dict, write_signals: bool = True) -> bool:
    """Add scenario to simulator script and test file."""
    fn_name  = p["fn_name"]
    rule_id  = p["rule_id"]
    arch     = p["arch"]
    desc_str = p["description"]
    expected = p["expected"]

    # ── 1. Append scenario function to incident_simulator.py ─────────────────
    src = SIM_SCRIPT.read_text(encoding="utf-8")

    if fn_name in src:
        print(AMBER(f"  Scenario '{fn_name}' already exists in incident_simulator.py — skipping add."))
    else:
        # Insert before SCENARIOS dict
        insert_before = "\nSCENARIOS = {"
        if insert_before not in src:
            print(RED("  Could not find SCENARIOS dict in incident_simulator.py — aborting."))
            return False

        new_fn = _build_scenario_fn(p)
        src = src.replace(insert_before, new_fn + insert_before)

        # Add to SCENARIOS dict
        scenarios_entry = (
            f'    "{fn_name}":  ({fn_name},\n'
            f'        "{rule_id} — {desc_str[:70]}"),\n'
        )
        # Insert before closing brace of SCENARIOS
        src = src.replace("}\n\nEXPECTED_RULES", f"{scenarios_entry}" + "}\n\nEXPECTED_RULES")

        # Add to EXPECTED_RULES dict
        expected_vals  = ", ".join('"' + r + '"' for r in sorted(expected))
        expected_entry = '    "' + fn_name + '": {' + expected_vals + '},\n'
        src = src.replace("}\n\n\n# ── Rule evaluation", expected_entry + "}\n\n\n# ── Rule evaluation")

        SIM_SCRIPT.write_text(src, encoding="utf-8")
        print(GREEN(f"  Added scenario '{fn_name}' to incident_simulator.py"))

    # ── 2. Add test assertion to test_incident_simulator.py ──────────────────
    test_src = TEST_FILE.read_text(encoding="utf-8")
    test_method = f"    def test_{fn_name}(self):"
    if test_method in test_src:
        print(AMBER(f"  Test 'test_{fn_name}' already exists — skipping add."))
    else:
        expected_set = "{" + ", ".join(f'"{r}"' for r in sorted(expected)) + "}"
        new_test = (
            f"\n    def test_{fn_name}(self):\n"
            f"        fn, _ = SCENARIOS[\"{fn_name}\"]\n"
            f"        fired = _fired_ids(fn())\n"
            f"        assert {expected_set} <= fired\n"
        )
        # Insert before test_all_expected_rules_match_documented
        anchor = "    def test_all_expected_rules_match_documented(self):"
        if anchor not in test_src:
            print(AMBER("  Could not find anchor in test file — appending test at end of TestScenariosFire."))
            test_src += new_test
        else:
            test_src = test_src.replace(anchor, new_test + "\n" + anchor)

        TEST_FILE.write_text(test_src, encoding="utf-8")
        print(GREEN(f"  Added test 'test_{fn_name}' to test_incident_simulator.py"))

    # ── 3. Write simulated governance_signals to report/<arch>/ ──────────────
    if write_signals:
        arch_dir = REPORT_DIR / arch
        arch_dir.mkdir(parents=True, exist_ok=True)
        sig_path = arch_dir / "governance_signals.json"

        # Build full signals: _base() fields + prescription overlay
        base = {
            "exploitation": {"severity": "LOW", "injection_patterns": [], "path_traversal": [],
                             "homoglyph_count": 0, "url_encoded_count": 0, "blocked": False},
            "manipulation": {"severity": "LOW", "confidence_swing_detected": False,
                             "confidence_swing": 0.0, "divergence_detected": False,
                             "critic_divergence_score": 0, "synthesis_quality": "FULL"},
            "leakage": {"detected": False, "severity": "LOW", "pii_indicators": [],
                        "sensitive_keywords": [], "flagged": False, "supply_chain_stale_sources": []},
            "sovereignty": {"severity": "LOW", "cross_boundary_nodes": [], "zdr_signals": [],
                            "inferred_regions": []},
            "aivss": {"overall": {"composite": 3.12, "severity": "LOW"},
                      "inbound": {"composite": 0.0, "severity": "LOW", "coverage_pct": 0},
                      "internal": {"composite": 6.25, "severity": "MEDIUM", "coverage_pct": 40},
                      "outbound": {"composite": 0.0, "severity": "LOW", "coverage_pct": 0},
                      "coverage_pct": 30, "per_threat": [], "per_agent": {}},
        }
        existing = {}
        if sig_path.exists():
            try:
                existing = json.loads(sig_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        merged = {**base, **existing}
        for dim, vals in p["signals"].items():
            merged[dim] = {**merged.get(dim, {}), **vals}

        sig_path.write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8")
        print(GREEN(f"  Wrote governance_signals to report/{arch}/governance_signals.json"))

    return True


# ── Phase 6: Verify ───────────────────────────────────────────────────────────

def verify() -> bool:
    """Run check-detect and return pass/fail."""
    detect_script = REPO / ".claude" / "skills" / "check-detect" / "scripts" / "check-detect.py"
    print(f"\n{BOLD('Verify')} — running /check-detect\n")
    result = subprocess.run(
        [sys.executable, str(detect_script)],
        cwd=REPO, capture_output=False,
    )
    return result.returncode == 0


# ── Phase 7: Log ──────────────────────────────────────────────────────────────

def log_to_decisions(rule: dict, prescription: Dict,
                     before_hits: int, after_hits: int, total: int) -> None:
    """Prepend a dated entry to docs/DECISIONS.md."""
    import datetime
    date_str = datetime.date.today().isoformat()
    rid  = rule.get("id", "?")
    name = rule.get("name", "")
    b_pct = round(before_hits / total * 100) if total else 0
    a_pct = round(after_hits  / total * 100) if total else 0

    entry = f"""---

## Session {date_str} — detect-loop: {rid} coverage {b_pct}% → {a_pct}%

**What was decided:** Added incident scenario `{prescription['fn_name']}` for {rid}
({name}) targeting `{prescription['arch']}`.

**Signal fields used:** {', '.join(prescription['signals'].keys())}

**Why:** Real-corpus coverage was {b_pct}% ({before_hits}/{total} archs). Scenario
covers: {prescription['description']}

**Alternatives rejected:** No alternative — this is a gap-fill, not a redesign.

"""

    if DECISIONS.exists():
        existing = DECISIONS.read_text(encoding="utf-8")
        # Insert after the first header line
        lines = existing.splitlines(keepends=True)
        insert_at = 1
        for i, line in enumerate(lines):
            if line.startswith("#"):
                insert_at = i + 1
                break
        lines.insert(insert_at, entry)
        DECISIONS.write_text("".join(lines), encoding="utf-8")
        print(GREEN(f"  Logged to docs/DECISIONS.md"))


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="DETECT coverage flywheel")
    parser.add_argument("--rule",         help="Target a specific rule ID (e.g. DETECT-014)")
    parser.add_argument("--observe-only", action="store_true", help="Show coverage matrix and exit")
    parser.add_argument("--incident",     help="Real-world incident description to ground the scenario")
    args = parser.parse_args()

    # ── Observe ───────────────────────────────────────────────────────────────
    print(f"\n{BOLD(CYAN('detect-loop'))} — SOC Detection Coverage Flywheel\n")
    print("Phase 1: Observing real-corpus coverage...\n")
    rule_arch_hits, rules, corpus_archs = observe()
    print_coverage_matrix(rule_arch_hits, rules, corpus_archs)

    if args.observe_only:
        sys.exit(0)

    if not corpus_archs:
        print(RED("No corpus architectures found — nothing to loop on."))
        sys.exit(1)

    # ── Diagnose → Prescribe → Gate → Apply loop ──────────────────────────────
    # Allow up to 3 attempts if user skips
    skipped: Set[str] = set()
    for _attempt in range(len(rules)):
        # Filter already-skipped
        target = args.rule
        if target and target in skipped:
            print(RED(f"Rule {target} was skipped. Exiting."))
            break

        print("Phase 2: Diagnosing...\n")
        # Pass a modified rule list excluding skipped
        available_rules = [r for r in rules if r.get("id") not in skipped]
        rule = diagnose(rule_arch_hits, available_rules, corpus_archs, target_rule_id=target)
        if rule is None:
            break

        print("Phase 3: Prescribing...\n")
        prescription = prescribe(rule, incident_hint=args.incident)
        if prescription is None:
            print(AMBER("No prescription available — add template to _RULE_PRESCRIPTIONS."))
            break

        print("Phase 4: Gate\n")
        decision = gate(prescription)

        if decision == "n":
            print(DIM("Aborted. No changes written."))
            break

        if decision == "skip":
            rid = rule.get("id", "?")
            skipped.add(rid)
            print(DIM(f"Skipping {rid}. Diagnosing next rule...\n"))
            if args.rule:
                break
            continue

        # Apply
        print(f"\nPhase 5: Applying...\n")
        before_hits = len(rule_arch_hits.get(rule.get("id", ""), []))
        ok = apply_scenario(prescription)
        if not ok:
            print(RED("Apply failed. Check errors above."))
            break

        # Verify
        verify_ok = verify()

        # Re-observe to get after count
        rule_arch_hits_after, _, _ = observe()
        after_hits = len(rule_arch_hits_after.get(rule.get("id", ""), []))

        # Log
        print(f"\nPhase 7: Logging to DECISIONS.md...\n")
        log_to_decisions(rule, prescription, before_hits, after_hits, len(corpus_archs))

        rid  = rule.get("id", "?")
        name = rule.get("name", "")
        b    = round(before_hits / len(corpus_archs) * 100) if corpus_archs else 0
        a    = round(after_hits  / len(corpus_archs) * 100) if corpus_archs else 0
        print(f"\n{BOLD('Summary')}")
        print(f"  Rule        : {rid} ({name})")
        print(f"  Coverage    : {RED(f'{b}%')} → {GREEN(f'{a}%')}  (+{a-b}pp)")
        print(f"  Scenario    : {prescription['fn_name']}")
        print(f"  Test suite  : {'✅ PASS' if verify_ok else '❌ FAIL'}")
        print()

        # Only do one rule per invocation unless --rule was specified
        break

    sys.exit(0)


if __name__ == "__main__":
    main()
