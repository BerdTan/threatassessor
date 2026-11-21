"""TAprover slice 1: technique_grounding + tactic_correctness (Entry 249)."""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("taprover", ROOT / ".claude/skills/taprover/scripts/taprover.py")
tp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tp)

CAT = {
    "T1190": {"name": "Exploit Public-Facing Application", "tactics": {"initial-access"}, "deprecated": False, "revoked": False},
    "T1078": {"name": "Valid Accounts", "tactics": {"defense-evasion", "persistence", "privilege-escalation", "initial-access"}, "deprecated": False, "revoked": False},
    "T9000": {"name": "Old", "tactics": {"execution"}, "deprecated": True, "revoked": False},
}


def tm(**kw):
    ap = {"path_id": "P1", "technique_id": "T1190", "technique_name": "Exploit Public-Facing Application", "tactic": "Initial Access"}
    ap.update(kw)
    return {"spec_version": "0.1", "architecture_id": "a", "attack_paths": [ap]}


ALL = {"enterprise", "ics", "atlas"}
SLICE1 = {"technique_grounding", "tactic_correctness"}


def verdicts(t, **kw):
    kw.setdefault("loaded", ALL)  # hand-built CAT stands in for all three catalogs unless a test says otherwise
    a = tp.prove(t, CAT, **kw)
    return {(c["category"]): c["verdict"] for c in a["claims"] if c["category"] in SLICE1}, a


def test_valid_claim_verified():
    v, a = verdicts(tm())
    assert v == {"technique_grounding": "VERIFIED", "tactic_correctness": "VERIFIED"}
    assert a["overall"] == "VERIFIED"  # coverage also verifies: one path citing one technique


def test_name_mismatch_refuted():
    v, _ = verdicts(tm(technique_name="Valid Accounts"))
    assert v["technique_grounding"] == "REFUTED"


def test_wrong_tactic_refuted():
    v, a = verdicts(tm(tactic="Impact"))
    assert v["tactic_correctness"] == "REFUTED" and a["overall"] == "REFUTED"


def test_non_tactic_string_refuted():
    v, _ = verdicts(tm(tactic="Sneaky Stuff"))
    assert v["tactic_correctness"] == "REFUTED"


def test_tactic_spelling_normalised():
    v, _ = verdicts(tm(tactic="initial_access"))
    assert v["tactic_correctness"] == "VERIFIED"


def test_empty_id_is_no_claim_not_refuted():
    a = tp.prove(tm(technique_id=""), CAT)
    assert all(c["verdict"] == "UNVERIFIABLE" and c["reason"] in ("no_claim", "empty_path") for c in a["claims"])
    assert a["overall"] == "UNVERIFIABLE"


def test_malformed_id_refuted():
    assert verdicts(tm(technique_id="T12"))[0]["technique_grounding"] == "REFUTED"


def test_unknown_id_refuted_by_default_unverifiable_lenient():
    assert verdicts(tm(technique_id="T1999"))[0]["technique_grounding"] == "REFUTED"
    assert verdicts(tm(technique_id="T1999"), lenient=True)[0]["technique_grounding"] == "UNVERIFIABLE"


def test_every_claim_has_reason():
    a = tp.prove(tm(technique_id="T1999", tactic="Impact"), CAT)
    assert all(c.get("reason") for c in a["claims"])


def test_deprecated_refuted():
    assert verdicts(tm(technique_id="T9000", technique_name="Old"))[0]["technique_grounding"] == "REFUTED"


def test_no_tactic_means_no_tactic_claim():
    v, _ = verdicts(tm(tactic=None))
    assert "tactic_correctness" not in v


def test_zero_claims_not_verified():
    a = tp.prove({"spec_version": "0.1", "attack_paths": []}, CAT)
    assert a["overall"] == "UNVERIFIABLE"


def test_ta_export_format_grounding_only():
    ex = {"schema": "ta-export/1.0", "assessment": {"architecture": "x", "attack_paths": [
        {"id": "AP-1", "techniques": ["T1190", "T1078"], "technique_names": ["Exploit Public-Facing Application", "Valid Accounts"]}]}}
    a = tp.prove(ex, CAT)
    g = [c for c in a["claims"] if c["category"] == "technique_grounding"]
    assert len(g) == 2 and all(c["verdict"] == "VERIFIED" for c in g) and not any(c["category"] == "tactic_correctness" for c in a["claims"])


def test_attestation_carries_grouping_fields():
    a = tp.prove(tm(), CAT, stix_sha="s", src_sha="i", run_id="r1")
    for k in ("run_id", "arch", "model_id", "routing_mode", "input_sha256", "evidence_sha256", "schema"):
        assert k in a
    assert a["run_id"] == "r1"


def test_independence_no_pipeline_imports():
    import ast
    tree = ast.parse((ROOT / ".claude/skills/taprover/scripts/taprover.py").read_text())
    mods = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            mods |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            mods.add((n.module or "").split(".")[0])
    assert not mods & {"chatbot", "agentic", "mcp_server", "taclaw"}


def test_real_stix_grounds_known_technique():
    stix = ROOT / tp.DEFAULT_STIX
    if not stix.exists():
        pytest.skip("STIX bundle absent")
    cat = tp.load_catalog(stix)
    assert cat["T1190"]["name"] == "Exploit Public-Facing Application"
    assert "initial-access" in cat["T1190"]["tactics"]


# ── ICS + ATLAS (real catalogs; skipped if the data files are absent) ─────────────────
ICS_PATH, ATLAS_PATH = ROOT / tp.DEFAULT_ICS, ROOT / tp.DEFAULT_ATLAS


@pytest.fixture(scope="module")
def full_cat():
    if not (ICS_PATH.exists() and (ATLAS_PATH / "techniques.yaml").exists() and (ROOT / tp.DEFAULT_STIX).exists()):
        pytest.skip("ICS/ATLAS/Enterprise data absent")
    cat = tp.load_catalog(ROOT / tp.DEFAULT_STIX)
    cat.update(tp.load_ics(ICS_PATH))
    cat.update(tp.load_atlas(ATLAS_PATH))
    return cat


def one(cat, **kw):
    a = tp.prove(tm(**kw), cat)
    return {c["category"]: c for c in a["claims"]}


def test_catalog_domains_disjoint_and_sized(full_cat):
    doms = {d: sum(e["domain"] == d for e in full_cat.values()) for d in ("enterprise", "ics", "atlas")}
    assert doms["enterprise"] >= 800 and doms["ics"] >= 100 and doms["atlas"] >= 150


def test_atlas_known_technique_verified(full_cat):
    r = one(full_cat, technique_id="AML.T0043", technique_name="Craft Adversarial Data", tactic="AI Attack Staging")
    assert r["technique_grounding"]["verdict"] == "VERIFIED" and r["tactic_correctness"]["verdict"] == "VERIFIED"


def test_atlas_old_ml_tactic_name_accepted(full_cat):
    assert one(full_cat, technique_id="AML.T0043", technique_name=None, tactic="ML Attack Staging")["tactic_correctness"]["verdict"] == "VERIFIED"


def test_atlas_subtechnique_inherits_parent_tactic(full_cat):
    assert full_cat["AML.T0000.000"]["tactics"] == full_cat["AML.T0000"]["tactics"] != set()


def test_atlas_invented_id_refuted(full_cat):
    assert one(full_cat, technique_id="AML.T9999", technique_name=None, tactic=None)["technique_grounding"]["verdict"] == "REFUTED"


def test_atlas_wrong_tactic_refuted(full_cat):
    assert one(full_cat, technique_id="AML.T0043", technique_name=None, tactic="Reconnaissance")["tactic_correctness"]["verdict"] == "REFUTED"


def _live_ics(full_cat):
    return next((k, e) for k, e in full_cat.items() if e["domain"] == "ics" and not e["revoked"] and not e["deprecated"] and e["tactics"])


def test_ics_live_technique_verified(full_cat):
    k, e = _live_ics(full_cat)
    r = one(full_cat, technique_id=k, technique_name=e["name"], tactic=sorted(e["tactics"])[0])
    assert r["technique_grounding"]["verdict"] == "VERIFIED" and r["tactic_correctness"]["verdict"] == "VERIFIED"


def test_ics_revoked_id_refuted_with_replacement(full_cat):
    # ATT&CK v20.1 revoked legacy ICS T0855 in favour of a T1xxx ID; the evidence must name the successor
    if not full_cat.get("T0855", {}).get("revoked"):
        pytest.skip("T0855 not revoked in this bundle version")
    r = one(full_cat, technique_id="T0855", technique_name=None, tactic=None)["technique_grounding"]
    assert r["verdict"] == "REFUTED" and r["reason"] == "deprecated" and "replaced by" in r["evidence"]


def test_ics_only_id_not_refuted_when_ics_unloaded():
    ent_only = {k: v for k, v in CAT.items()}
    a = tp.prove(tm(technique_id="T1692.001", technique_name=None, tactic=None), ent_only, loaded={"enterprise"})
    assert a["claims"][0]["verdict"] == "UNVERIFIABLE" and a["claims"][0]["reason"] == "catalog_not_loaded"


def test_ics_tactic_not_valid_for_enterprise_technique(full_cat):
    # 'impair-process-control' is an ICS tactic; claiming it on an Enterprise technique is wrong
    assert one(full_cat, technique_id="T1190", technique_name=None, tactic="Impair Process Control")["tactic_correctness"]["verdict"] == "REFUTED"


def test_ics_invented_id_refuted(full_cat):
    assert one(full_cat, technique_id="T0899", technique_name=None, tactic=None)["technique_grounding"]["verdict"] == "REFUTED"


def test_unloaded_domain_unverifiable_not_refuted():
    # catalog without ICS/ATLAS: those IDs cannot be proven, and must not be called false
    a = tp.prove(tm(technique_id="AML.T0043", technique_name=None, tactic=None), CAT)
    assert a["claims"][0]["reason"] == "catalog_not_loaded" and a["overall"] == "UNVERIFIABLE"


def test_drift_labels_only_baseline_accepted_refutations():
    old = {"T1562": {"name": "Impair Defenses", "tactics": {"defense-evasion"}, "deprecated": False, "revoked": False}}
    new = {"T1562": {"name": "Impair Defenses", "tactics": {"defense-impairment"}, "deprecated": False, "revoked": False}}
    t = {"spec_version": "0.1", "architecture_id": "a", "attack_paths": [
        {"path_id": "P1", "technique_id": "T1562", "technique_name": "Impair Defenses", "tactic": "Defense Evasion"},
        {"path_id": "P2", "technique_id": "T1562", "technique_name": "Wrong Name", "tactic": "Defense Evasion"}]}
    latest = tp.prove(t, new, loaded=ALL)
    att = tp.mark_drift(latest, tp.prove(t, old, loaded=ALL))
    assert att["counts"]["DRIFT"] >= 1 and att["counts"]["REFUTED"] >= 1  # name_mismatch is real, tactic move is drift
    assert att["overall"] == "REFUTED"


# ---- slice 2: logic checks -------------------------------------------------
ATLAS_CAT = dict(CAT, **{"AML.T0051": {"name": "LLM Prompt Injection", "tactics": {"initial-access"}, "deprecated": False, "revoked": False, "domain": "atlas"}})
MIT = {"M1030": {"name": "Network Segmentation", "deprecated": False, "revoked": False},
       "M9999": {"name": "Old Mitigation", "deprecated": True, "revoked": False}}


def export(techs, summary=None, agentic=False, mitre=None):
    ex = {"schema": "ta-export/1.0", "architecture": {"name": "x", "type": "ai_system" if agentic else "cloud"},
          "assessment": {"attack_paths": [{"id": "AP-1", "techniques": techs}], "mitre_techniques": summary if summary is not None else techs}}
    if mitre:
        ex["otm"] = {"mitigations": [{"mitre_mitigations": mitre}]}
    return ex


def by_cat(a, cat):
    return [c for c in a["claims"] if c["category"] == cat]


def test_agentic_without_atlas_refuted():
    a = tp.prove(export(["T1190"], agentic=True), ATLAS_CAT)
    r = by_cat(a, "agentic_trigger_parity")[0]
    assert r["verdict"] == "REFUTED" and r["reason"] == "agentic_no_atlas" and a["overall"] == "REFUTED"


def test_agentic_with_atlas_in_summary_only_verified():
    a = tp.prove(export(["T1190"], summary=["T1190", "AML.T0051"], agentic=True), ATLAS_CAT)
    assert by_cat(a, "agentic_trigger_parity")[0]["verdict"] == "VERIFIED"
    assert any(c["path"] == "ARCH" and c["technique_id"] == "AML.T0051" for c in a["claims"])  # summary-level ATLAS is proven too


def test_non_agentic_has_no_parity_check():
    assert not by_cat(tp.prove(export(["T1190"]), ATLAS_CAT), "agentic_trigger_parity")


def test_agentic_atlas_catalog_missing_is_unverifiable_not_refuted():
    a = tp.prove(export(["T1190"], summary=["T1190", "AML.T0051"], agentic=True), CAT, loaded={"enterprise", "ics"})
    assert by_cat(a, "agentic_trigger_parity")[0]["verdict"] == "UNVERIFIABLE"


def test_threatmodel_agentic_flag_triggers_parity():
    t = tm()
    t["architecture_summary"] = {"is_agentic": True}
    assert by_cat(tp.prove(t, CAT), "agentic_trigger_parity")[0]["reason"] == "agentic_no_atlas"
    t2 = tm(); t2["governance"] = {"agentic": {"agent_autonomy_level": "supervised"}}
    assert by_cat(tp.prove(t2, CAT), "agentic_trigger_parity")


def test_coverage_path_technique_missing_from_summary_refuted():
    a = tp.prove(export(["T1190", "T1078"], summary=["T1190"]), CAT)
    assert by_cat(a, "coverage")[0]["reason"] == "not_in_summary"


def test_coverage_empty_path_unverifiable():
    a = tp.prove(export([], summary=["T1190"]), CAT)
    assert by_cat(a, "coverage")[0]["verdict"] == "UNVERIFIABLE"


def test_mitigation_unknown_and_deprecated_refuted_known_verified():
    base = dict(tm(), mitigations=[
        {"control_id": "M1030", "addresses_technique": ["T1190"]},
        {"control_id": "M9999", "addresses_technique": ["T1190"]},
        {"control_id": "M1234", "addresses_technique": ["T1190"]}])
    a = tp.prove(base, CAT, mitigations=MIT)
    reasons = [c["reason"] for c in by_cat(a, "mitigation_validity")]
    assert reasons == ["ok", "deprecated", "unknown_mitigation"]


def test_mitigation_addressing_technique_not_in_model_refuted():
    t = dict(tm(), mitigations=[{"control_id": "M1030", "addresses_technique": ["T1078"]}])
    assert by_cat(tp.prove(t, CAT, mitigations=MIT), "mitigation_validity")[0]["reason"] == "addresses_unknown_technique"


def test_mitigation_external_framework_unverifiable_and_gap_noted():
    t = dict(tm(), mitigations=[{"control_id": "NIST PR.AC-1", "addresses_technique": []}])
    a = tp.prove(t, CAT, mitigations=MIT)
    assert by_cat(a, "mitigation_validity")[0]["reason"] == "external_framework"
    assert not by_cat(a, "mitigation_coverage")  # nothing addressed -> no coverage claim to test


def test_mitigation_path_coverage_gap_unverifiable():
    t = dict(tm(), mitigations=[{"control_id": "M1030", "addresses_technique": ["T1190"]}])
    t["attack_paths"].append({"path_id": "P2", "technique_id": "T1078", "technique_name": "Valid Accounts", "tactic": "Persistence"})
    assert by_cat(tp.prove(t, CAT, mitigations=MIT), "mitigation_coverage")[0]["reason"] == "path_unmitigated"


def test_no_mitigations_key_emits_nothing():
    assert not by_cat(tp.prove(tm(), CAT, mitigations=MIT), "mitigation_validity")


def test_export_mitre_mitigations_checked():
    a = tp.prove(export(["T1190"], mitre=["M1030", "M1234"]), CAT, mitigations=MIT)
    assert [c["reason"] for c in by_cat(a, "mitigation_validity")] == ["ok", "unknown_mitigation"]


def test_aggregate_pass_at_k_vs_pass_pow_k():
    ok = {"arch": "a", "overall": "VERIFIED"}
    drift = {"arch": "a", "overall": "DRIFT"}
    bad = {"arch": "a", "overall": "REFUTED"}
    g = tp.aggregate([ok, bad, ok, {"arch": "b", "overall": "UNVERIFIABLE"}, drift])["archs"]
    assert g["a"] == {"k": 4, "passes": 3, "pass_at_k": True, "pass_pow_k": False}
    assert g["b"]["pass_pow_k"] is True  # UNVERIFIABLE is not a failure: no REFUTED claim
    r = tp.aggregate([ok, bad, {"arch": "b", "overall": "VERIFIED"}])
    assert r["pass_at_k_rate"] == 1.0 and r["pass_pow_k_rate"] == 0.5
