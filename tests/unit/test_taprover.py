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


def verdicts(t, **kw):
    kw.setdefault("loaded", ALL)  # hand-built CAT stands in for all three catalogs unless a test says otherwise
    a = tp.prove(t, CAT, **kw)
    return {(c["category"]): c["verdict"] for c in a["claims"]}, a


def test_valid_claim_verified():
    v, a = verdicts(tm())
    assert v == {"technique_grounding": "VERIFIED", "tactic_correctness": "VERIFIED"}
    assert a["overall"] == "VERIFIED"


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
    assert all(c["verdict"] == "UNVERIFIABLE" and c["reason"] == "no_claim" for c in a["claims"])
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
    assert a["counts"]["VERIFIED"] == 2 and all(c["category"] == "technique_grounding" for c in a["claims"])


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
