#!/usr/bin/env python3
"""
tmbench-check.py — Score a threat model JSON against threatmodel.md spec v0.1.

Modes:
  --score <file>    Score one TM JSON
  --compare <dir>   Leaderboard across all JSONs in a directory
  --spec-review     Surface spec gaps from patterns across all scored runs
  --all             All three in sequence
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SPEC_PATH = ROOT / "docs/tmbench/threatmodel.md"
RESULTS_DIR = ROOT / "docs/tmbench/results"
CHANGELOG_PATH = ROOT / "docs/tmbench/CHANGELOG.md"

SPEC_VERSION = "threatmodel/0.1"
PASS_THRESHOLD = 8
ZERO_DIMENSION_FAIL = True  # any TATB dimension at 0 → automatic Reject

# Complexity tier thresholds (component count → min attack paths)
TIER_THRESHOLDS = [(5, 3), (15, 5), (30, 8), (999, 8)]

# ── helpers ──────────────────────────────────────────────────────────────────

def min_paths_for_arch(component_count: int) -> int:
    for limit, minimum in TIER_THRESHOLDS:
        if component_count <= limit:
            return minimum
    return 8


def load_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  [error] cannot load {path.name}: {e}", file=sys.stderr)
        return None


def field(obj: dict, *keys, default=None):
    for k in keys:
        if not isinstance(obj, dict):
            return default
        obj = obj.get(k, default)
        if obj is None:
            return default
    return obj


# ── section completeness checks ──────────────────────────────────────────────

def check_architecture_summary(tm: dict) -> list[tuple[str, str]]:
    """Returns list of (severity, message) gaps."""
    gaps = []
    arch = tm.get("architecture_summary", {})
    if not arch:
        return [("Critical", "architecture_summary section missing")]
    components = arch.get("components", [])
    if not components:
        gaps.append(("Critical", "architecture_summary.components is empty"))
    if not arch.get("trust_boundaries"):
        gaps.append(("High", "architecture_summary.trust_boundaries is empty"))
    if not arch.get("data_classification"):
        gaps.append(("Medium", "architecture_summary.data_classification missing"))
    if not arch.get("operational_context"):
        gaps.append(("Low", "architecture_summary.operational_context missing"))
    return gaps


def check_threat_actors(tm: dict) -> list[tuple[str, str]]:
    gaps = []
    actors = tm.get("threat_actors", [])
    if not actors:
        return [("Critical", "threat_actors section missing or empty")]
    for i, actor in enumerate(actors):
        name = actor.get("name", f"actor[{i}]")
        if not actor.get("motivation"):
            gaps.append(("Medium", f"threat_actor '{name}': motivation missing"))
        if not actor.get("capability_tier"):
            gaps.append(("Medium", f"threat_actor '{name}': capability_tier missing"))
        if not actor.get("initial_access_vector"):
            gaps.append(("High", f"threat_actor '{name}': initial_access_vector missing"))
        non_caps = actor.get("non_capabilities", [])
        if not non_caps:
            gaps.append(("Medium", f"threat_actor '{name}': non_capabilities empty — severity inflation risk"))
    return gaps


def check_attack_paths(tm: dict) -> list[tuple[str, str]]:
    gaps = []
    paths = tm.get("attack_paths", [])
    components = tm.get("architecture_summary", {}).get("components", [])
    component_count = len(components)
    min_paths = min_paths_for_arch(component_count)

    if not paths:
        return [("Critical", "attack_paths section missing or empty")]

    if len(paths) < min_paths:
        gaps.append(("High", f"attack path count {len(paths)} below minimum {min_paths} for {component_count}-component architecture"))

    required_fields = ["technique_id", "technique_name", "tactic", "target_component", "entry_point", "impact", "likelihood"]
    for path in paths:
        pid = path.get("path_id", "?")
        for f_name in required_fields:
            if not path.get(f_name):
                gaps.append(("High", f"attack_path '{pid}': {f_name} missing"))

        tech_id = path.get("technique_id", "")
        if tech_id and not re.match(r"^(T\d{4}(\.\d{3})?|AML\.T\d{4})$", tech_id):
            gaps.append(("High", f"attack_path '{pid}': technique_id '{tech_id}' does not match ATT&CK/ATLAS format"))

        if not path.get("target_component"):
            gaps.append(("Medium", f"attack_path '{pid}': no component grounding (target_component missing)"))

    # Check for ATLAS technique if agentic architecture
    is_agentic = bool(tm.get("governance", {}).get("agentic"))
    if not is_agentic:
        # Check component roles
        comp_roles = [c.get("role", "").lower() for c in components]
        is_agentic = any(r in ("agent", "llm", "tool_caller", "ai", "ml") for r in comp_roles)

    if is_agentic:
        has_atlas = any(
            p.get("technique_id", "").startswith("AML.")
            for p in paths
        )
        if not has_atlas:
            gaps.append(("High", "agentic architecture requires at least one MITRE ATLAS technique (AML.T*)"))

    return gaps


def check_mitigations(tm: dict) -> list[tuple[str, str]]:
    gaps = []
    paths = tm.get("attack_paths", [])
    mitigations = tm.get("mitigations", [])

    if not mitigations:
        if paths:
            return [("Critical", "mitigations section empty — every attack path must have at least one mitigation")]
        return []

    addressed = set()
    for m in mitigations:
        for tid in m.get("addresses_technique", []):
            addressed.add(tid)
        if not m.get("control_id"):
            gaps.append(("Medium", f"mitigation '{m.get('mitigation_id','?')}': control_id missing"))
        if not m.get("implementation_status"):
            gaps.append(("Low", f"mitigation '{m.get('mitigation_id','?')}': implementation_status missing"))

    for path in paths:
        tid = path.get("technique_id")
        if tid and tid not in addressed:
            gaps.append(("High", f"attack_path '{path.get('path_id','?')}' technique {tid} has no mitigation"))

    return gaps


def check_findings(tm: dict) -> list[tuple[str, str]]:
    gaps = []
    findings = tm.get("findings", [])
    paths = tm.get("attack_paths", [])

    if not findings:
        if paths:
            return [("Critical", "findings section empty — every attack path must produce at least one finding")]
        return []

    severities = [f.get("severity") for f in findings if f.get("severity")]
    if len(set(severities)) == 1 and len(severities) > 2:
        gaps.append(("High", f"all {len(severities)} findings have the same severity '{severities[0]}' — Risk-Defensible likely 0 or 1"))

    for finding in findings:
        fid = finding.get("finding_id", "?")
        if not finding.get("severity"):
            gaps.append(("High", f"finding '{fid}': severity missing"))
        if not finding.get("severity_rationale"):
            gaps.append(("Medium", f"finding '{fid}': severity_rationale missing"))
        sev = finding.get("severity", "")
        if sev in ("Critical", "High") and not finding.get("severity_vector"):
            gaps.append(("Medium", f"finding '{fid}': severity_vector (CVSS/AIVSS) required for {sev} findings"))
        if not finding.get("remediation_priority"):
            gaps.append(("Low", f"finding '{fid}': remediation_priority missing"))

    return gaps


def check_governance(tm: dict) -> list[tuple[str, str]]:
    gaps = []
    gov = tm.get("governance", {})
    if not gov:
        return [("High", "governance section missing")]

    if not gov.get("data_sovereignty"):
        gaps.append(("Medium", "governance.data_sovereignty missing"))
    if "compliance_scope" not in gov:
        gaps.append(("Medium", "governance.compliance_scope missing (empty list acceptable if justified)"))
    if "third_party_dependencies" not in gov:
        gaps.append(("Low", "governance.third_party_dependencies missing"))

    # Agentic check
    components = tm.get("architecture_summary", {}).get("components", [])
    comp_roles = [c.get("role", "").lower() for c in components]
    is_agentic = any(r in ("agent", "llm", "tool_caller", "ai", "ml") for r in comp_roles)

    if is_agentic and not gov.get("agentic"):
        gaps.append(("Critical", "agentic governance block required — architecture has agent/LLM component"))
    elif gov.get("agentic"):
        agentic = gov["agentic"]
        for field_name in ["agent_autonomy_level", "tool_call_scope", "blast_radius", "human_oversight_points", "model_provenance"]:
            if not agentic.get(field_name):
                gaps.append(("Medium", f"governance.agentic.{field_name} missing"))

    return gaps


# ── TATB rubric scoring ───────────────────────────────────────────────────────

def score_threat_relevant(tm: dict) -> tuple[int, str]:
    paths = tm.get("attack_paths", [])
    components = {c.get("id") for c in tm.get("architecture_summary", {}).get("components", [])}
    if not paths:
        return 0, "no attack paths"

    grounded = sum(1 for p in paths if p.get("target_component") and p.get("entry_point"))
    ratio = grounded / len(paths)
    if ratio == 1.0:
        return 3, "all paths grounded to specific components and entry points"
    elif ratio >= 0.8:
        return 2, f"{len(paths) - grounded} path(s) lack component or entry point grounding"
    elif ratio >= 0.5:
        return 1, f"{len(paths) - grounded}/{len(paths)} paths are generic (missing component/entry point)"
    return 0, "most paths lack architecture grounding"


def score_ttp_accurate(tm: dict) -> tuple[int, str]:
    paths = tm.get("attack_paths", [])
    if not paths:
        return 0, "no attack paths"

    valid_pattern = re.compile(r"^(T\d{4}(\.\d{3})?|AML\.T\d{4})$")
    valid = sum(1 for p in paths if valid_pattern.match(p.get("technique_id", "")))
    has_tactic = sum(1 for p in paths if p.get("tactic"))
    ratio = valid / len(paths)

    if ratio == 1.0 and has_tactic == len(paths):
        return 3, "all technique IDs valid ATT&CK/ATLAS format with tactic phases"
    elif ratio >= 0.9:
        return 2, f"{len(paths) - valid} technique ID(s) malformed or missing"
    elif ratio >= 0.5:
        return 1, f"{len(paths) - valid}/{len(paths)} technique IDs invalid or missing"
    return 0, "most technique IDs absent or invalid"


def score_risk_defensible(tm: dict) -> tuple[int, str]:
    findings = tm.get("findings", [])
    mitigations = tm.get("mitigations", [])
    if not findings:
        return 0, "no findings"

    severities = [f.get("severity") for f in findings if f.get("severity")]
    if not severities:
        return 0, "no severity ratings"

    all_same = len(set(severities)) == 1
    has_rationale = sum(1 for f in findings if f.get("severity_rationale"))
    has_residual = sum(1 for m in mitigations if m.get("residual_risk"))

    if all_same and len(severities) > 2:
        return 0, f"all {len(severities)} findings rated '{severities[0]}' — no differentiation"
    if has_rationale / max(len(findings), 1) >= 0.9 and has_residual >= len(mitigations) * 0.5:
        return 3, "severity ratings differentiated with rationale; residual risk assessed"
    elif has_rationale / max(len(findings), 1) >= 0.7:
        return 2, "most ratings have rationale; some residual risk gaps"
    return 1, "ratings present but inconsistent or mostly unrationalised"


def score_plan_actionable(tm: dict) -> tuple[int, str]:
    mitigations = tm.get("mitigations", [])
    findings = tm.get("findings", [])
    if not mitigations:
        return 0, "no mitigations"

    has_control_id = sum(1 for m in mitigations if m.get("control_id"))
    has_status = sum(1 for m in mitigations if m.get("implementation_status"))
    findings_with_priority = sum(1 for f in findings if f.get("remediation_priority"))

    ratio_control = has_control_id / max(len(mitigations), 1)
    ratio_priority = findings_with_priority / max(len(findings), 1)

    if ratio_control >= 0.95 and ratio_priority >= 0.9 and has_status == len(mitigations):
        return 3, "every mitigation has control reference + status; every finding has priority"
    elif ratio_control >= 0.7 and ratio_priority >= 0.7:
        return 2, "most mitigations actionable; some gaps in control refs or priority"
    elif ratio_control >= 0.4:
        return 1, "mitigations present but control references sparse or generic"
    return 0, "mitigations have no control references or remediation guidance"


# ── bonus points ─────────────────────────────────────────────────────────────

def bonus_completeness(tm: dict, all_gaps: list[tuple[str, str]]) -> tuple[int, str]:
    critical_gaps = [g for sev, g in all_gaps if sev == "Critical"]
    high_gaps = [g for sev, g in all_gaps if sev == "High"]
    if not critical_gaps and not high_gaps:
        return 1, "all checklist items pass"
    return 0, f"{len(critical_gaps)} critical + {len(high_gaps)} high gaps present"


def bonus_agentic(tm: dict) -> tuple[int, str]:
    components = tm.get("architecture_summary", {}).get("components", [])
    comp_roles = [c.get("role", "").lower() for c in components]
    is_agentic = any(r in ("agent", "llm", "tool_caller", "ai", "ml") for r in comp_roles)
    if not is_agentic:
        return 0, "n/a — no agentic component"

    paths = tm.get("attack_paths", [])
    has_atlas = any(p.get("technique_id", "").startswith("AML.") for p in paths)
    has_agentic_gov = bool(tm.get("governance", {}).get("agentic"))

    if has_atlas and has_agentic_gov:
        return 1, "ATLAS technique present + agentic governance block complete"
    return 0, f"agentic architecture: atlas={'yes' if has_atlas else 'no'}, gov_block={'yes' if has_agentic_gov else 'no'}"


# ── confidence standing ───────────────────────────────────────────────────────

def confidence_label(score: int, max_score: int, any_zero: bool) -> str:
    if any_zero:
        return "Reject — TATB dimension at zero"
    pct = score / max_score
    if score >= 12:
        return "Solid — production-grade TM"
    elif score >= 10:
        return "Good — minor gaps, addressable in one pass"
    elif score >= PASS_THRESHOLD:
        return "Pass (borderline) — gaps present, not blocking"
    elif score >= 5:
        return "Fail — multiple dimension weaknesses"
    return "Reject — fundamental coverage missing"


# ── main score function ───────────────────────────────────────────────────────

def score_tm(tm: dict, arch_id: str | None = None) -> dict:
    arch_id = arch_id or tm.get("architecture_id", "unknown")
    produced_by = tm.get("produced_by", "unknown")

    gaps: list[tuple[str, str]] = []
    gaps += check_architecture_summary(tm)
    gaps += check_threat_actors(tm)
    gaps += check_attack_paths(tm)
    gaps += check_mitigations(tm)
    gaps += check_findings(tm)
    gaps += check_governance(tm)

    tr_score, tr_note = score_threat_relevant(tm)
    tta_score, tta_note = score_ttp_accurate(tm)
    rd_score, rd_note = score_risk_defensible(tm)
    pa_score, pa_note = score_plan_actionable(tm)

    comp_bonus, comp_note = bonus_completeness(tm, gaps)
    ag_bonus, ag_note = bonus_agentic(tm)

    # Agentic bonus subsumes completeness bonus — both bonuses combined are worth +1 max.
    # This keeps the universal ceiling at 13 (12 base + 1 bonus).
    effective_bonus = min(comp_bonus + ag_bonus, 1)
    total = tr_score + tta_score + rd_score + pa_score + effective_bonus
    max_score = 13
    any_zero = any(s == 0 for s in [tr_score, tta_score, rd_score, pa_score])
    status = "PASS" if total >= PASS_THRESHOLD and not any_zero else "FAIL"
    label = confidence_label(total, max_score, any_zero)

    return {
        "arch_id": arch_id,
        "produced_by": produced_by,
        "spec_version": SPEC_VERSION,
        "tatb": {
            "threat_relevant": (tr_score, tr_note),
            "ttp_accurate": (tta_score, tta_note),
            "risk_defensible": (rd_score, rd_note),
            "plan_actionable": (pa_score, pa_note),
        },
        "bonus": {
            "completeness": (comp_bonus, comp_note),
            "agentic": (ag_bonus, ag_note),
        },
        "total": total,
        "max_score": max_score,
        "status": status,
        "confidence": label,
        "gaps": gaps,
    }


def print_score_report(result: dict) -> None:
    print(f"\nTMbench Score Report")
    print(f"Architecture: {result['arch_id']}")
    print(f"Produced by:  {result['produced_by']}")
    print(f"Spec version: {result['spec_version']}\n")

    print("TATB Rubric:")
    for dim, (score, note) in result["tatb"].items():
        label = dim.replace("_", " ").title().replace("Ttp", "TTP")
        zero_flag = "  ← ZERO (auto-Reject)" if score == 0 else ""
        print(f"  {label:<20} {score}/3  — {note}{zero_flag}")

    print("\nBonus:")
    for dim, (score, note) in result["bonus"].items():
        print(f"  {dim.title():<20} +{score}  — {note}")

    total = result["total"]
    max_s = result["max_score"]
    status = result["status"]
    print(f"\nScore: {total}/{max_s}  [{status} — threshold {PASS_THRESHOLD}]")
    print(f"Confidence: {result['confidence']}\n")

    if result["gaps"]:
        priority_order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
        sorted_gaps = sorted(result["gaps"], key=lambda g: priority_order.get(g[0], 4))
        print("Gaps (priority order):")
        for sev, msg in sorted_gaps:
            print(f"  [{sev}] {msg}")
    else:
        print("Gaps: none — all checks pass")


# ── compare mode ─────────────────────────────────────────────────────────────

def run_compare(results_dir: Path) -> list[dict]:
    files = sorted(results_dir.glob("*.json"))
    if not files:
        print(f"No JSON files found in {results_dir}")
        return []

    results = []
    for f in files:
        tm = load_json(f)
        if tm:
            result = score_tm(tm, arch_id=f.stem)
            results.append(result)

    print(f"\nTMbench Leaderboard  (spec {SPEC_VERSION})")
    print(f"  {'Tool / Run':<35} {'TR':>3} {'TA':>3} {'RD':>3} {'PA':>3} {'Score':>6}  Status")
    print(f"  {'-'*35} {'--':>3} {'--':>3} {'--':>3} {'--':>3} {'------':>6}  ------")

    for r in sorted(results, key=lambda x: -x["total"]):
        tr = r["tatb"]["threat_relevant"][0]
        ta = r["tatb"]["ttp_accurate"][0]
        rd = r["tatb"]["risk_defensible"][0]
        pa = r["tatb"]["plan_actionable"][0]
        label = f"{r['arch_id']} / {r['produced_by']}"[:35]
        print(f"  {label:<35} {tr:>3} {ta:>3} {rd:>3} {pa:>3} {r['total']:>4}/{r['max_score']}  {r['status']}")

    return results


# ── spec review mode ──────────────────────────────────────────────────────────

def run_spec_review(results_dir: Path) -> None:
    files = sorted(results_dir.glob("*.json"))
    if not files:
        print(f"No JSON files found in {results_dir} — run --score first to populate results")
        return

    all_gaps: list[tuple[str, str]] = []
    n = 0
    for f in files:
        tm = load_json(f)
        if tm:
            result = score_tm(tm, arch_id=f.stem)
            all_gaps.extend(result["gaps"])
            n += 1

    if not all_gaps:
        print(f"\nSpec Review ({n} runs): no gaps found — spec fully satisfied by all submissions")
        return

    # Cluster gaps by message prefix (first 50 chars)
    clusters: dict[str, list[str]] = defaultdict(list)
    for sev, msg in all_gaps:
        key = msg[:60]
        clusters[key].append(sev)

    # Sort by frequency
    ranked = sorted(clusters.items(), key=lambda x: -len(x[1]))

    print(f"\nSpec Review — patterns across {n} scored run(s)")
    print(f"Total gap instances: {len(all_gaps)}\n")

    spec_patches = {
        "non_capabilities empty": (
            "§1.2 non_capabilities",
            "field present but tools leave it empty — add minimum 2 entries requirement + worked examples"
        ),
        "all findings rated": (
            "§2.3 Risk-Defensible",
            "spec does not define 'materially different exposure' — add worked example showing expected rating spread"
        ),
        "agentic governance block required": (
            "§1.6 agentic trigger",
            "trigger condition ambiguous — add explicit component role list: (agent|llm|tool_caller|ai|ml)"
        ),
        "technique_id": (
            "§1.3 ATT&CK grounding",
            "validation pattern may be too strict for sub-techniques or custom IDs — review regex"
        ),
        "ATLAS technique": (
            "§1.3 ATLAS requirement",
            "ATLAS requirement may need clearer component role trigger list"
        ),
    }

    print("Spec improvement candidates (ranked by frequency):")
    shown = 0
    for msg_prefix, severities in ranked[:8]:
        count = len(severities)
        freq = f"{count}/{n}"
        # Find matching spec patch suggestion
        patch = None
        for kw, (section, suggestion) in spec_patches.items():
            if kw.lower() in msg_prefix.lower():
                patch = (section, suggestion)
                break
        print(f"\n  [{count}x] {msg_prefix}")
        if patch:
            print(f"    Spec section: {patch[0]}")
            print(f"    Suggested patch: {patch[1]}")
        else:
            print(f"    Spec section: review required — no auto-match")
        shown += 1

    print(f"\nNext action: apply patches to {SPEC_PATH.relative_to(ROOT)}")
    print(f"Then re-score same TMs to verify gaps shrink — log spec version in docs/tmbench/CHANGELOG.md")


# ── entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="TMbench spec scorer")
    parser.add_argument("--score", metavar="FILE", help="Score one TM JSON file")
    parser.add_argument("--compare", metavar="DIR", nargs="?", const=str(RESULTS_DIR),
                        help="Leaderboard across all JSONs in a directory")
    parser.add_argument("--spec-review", action="store_true",
                        help="Surface spec gaps from patterns across all scored runs")
    parser.add_argument("--all", action="store_true", help="--compare + --spec-review")
    args = parser.parse_args()

    if args.score:
        path = Path(args.score)
        tm = load_json(path)
        if tm:
            result = score_tm(tm, arch_id=path.stem)
            print_score_report(result)

    if args.compare or args.all:
        dir_path = Path(args.compare) if args.compare else RESULTS_DIR
        run_compare(dir_path)

    if args.spec_review or args.all:
        results_dir = Path(args.compare) if args.compare else RESULTS_DIR
        run_spec_review(results_dir)

    if not any([args.score, args.compare, args.spec_review, args.all]):
        parser.print_help()


if __name__ == "__main__":
    main()
