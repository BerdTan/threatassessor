"""TAwatch mapping integrity: guards against silent label mismatches."""
import json
from pathlib import Path

import pytest

from chatbot.modules import tawatch as T

CORPUS = T.INCIDENTS_PATH


def test_norm_labels_repairs_comma_split_and_whitespace():
    raw = ["Reconnaissance", ' "Intrusion', ' Evasion & Persistence"', " Social Engineering"]
    assert T._norm_labels(raw) == [
        "Reconnaissance", "Intrusion, Evasion & Persistence", "Social Engineering"]


def test_canon_ignores_commas_quotes_case():
    assert T._canon('Intrusion, Evasion & Persistence') == T._canon('intrusion evasion & persistence')


def test_intrusion_evasion_persistence_reaches_high_for_pipeline_domains():
    inc = {"mitre_tactics": ["Persistence", "Stealth"],
           "taxonomy_cats": ["Intrusion, Evasion & Persistence"]}
    r = T.IncidentAdapter().adapt(inc)
    assert r["PER"] == "high" and r["SCT"] == "high" and r["QC"] == "high"


def test_out_of_scope_capability_maps_to_no_domain():
    r = T.IncidentAdapter().adapt({"taxonomy_cats": ["Multimodal Generation"], "mitre_tactics": []})
    assert r == {}


def test_ai_role_target_and_weapon():
    a = T.IncidentAdapter()
    assert a.ai_role({"headline": "Malicious MCP Server poisons agent tool metadata"}) == "target"
    assert a.ai_role({"headline": "Scam centre uses ChatGPT to write phishing"}) == "weapon"


@pytest.mark.skipif(not CORPUS.exists(), reason="corpus is gitignored; regenerate via export script")
def test_corpus_has_no_unmapped_labels():
    tw = T.TAwatch().load()
    assert tw._adapter.unmapped_labels(tw._incidents) == {"tactics": {}, "capabilities": {}}


@pytest.mark.skipif(not CORPUS.exists(), reason="corpus is gitignored")
def test_every_domain_can_reach_high_confidence():
    tw = T.TAwatch().load()
    reached = {d for cov in tw._coverage.values() for d, c in cov.items() if c == "high"}
    # SEC has no capability channel in the tables; known limitation, tracked in DECISIONS
    assert {"QC", "INJ", "EXF", "SCT", "MCP", "RES", "ABU", "AGT", "PER"} <= reached


# ── DETECT-INJ-010 structural signal (derived from TAwatch AI-as-target gap) ──
from chatbot.harness.governance import InhouseGovernanceAdapter  # noqa: E402

_VULN = """graph TD
Issue["GitHub Issue Body"] --> Agent["Claude Triage LLM"]
Agent --> Publish["npm publish"]
"""
_GATED = _VULN + 'Agent --> Review["Human Approval Gate"]\n'
_BENIGN = """graph TD
Client["Browser"] --> Agent["Claude LLM"]
Agent --> DB["Results Store"]
"""


def _sov(mmd):
    return InhouseGovernanceAdapter().check_input(mmd, "t.mmd").sovereignty


def test_inj010_fires_on_issue_to_agent_to_publish():
    assert _sov(_VULN)["untrusted_to_privileged_agent"] is True


def test_inj010_suppressed_by_approval_gate():
    assert _sov(_GATED)["untrusted_to_privileged_agent"] is False


def test_inj010_quiet_on_benign():
    assert _sov(_BENIGN)["untrusted_to_privileged_agent"] is False


# ── DETECT-INJ-011 / DETECT-RES-005 (hand-labelled TAwatch targets, Entry 257) ──────────────

_GROK = """graph TD
Reply["Public Reply Thread"] --> Assistant["Grok LLM Assistant"]
Assistant --> Post["Publish Public Post"]
"""
_GROK_MOD = _GROK.replace('Assistant --> Post', 'Assistant --> Mod["Link Scanner"]\nMod --> Post')
_GROK_BENIGN = """graph TD
Reply["Public Reply Thread"] --> Assistant["Summariser LLM"]
Assistant --> Store["Analytics Store"]
"""
_OPEN = """graph TD
Net["Internet"] --> Ollama["Ollama Inference Server (no auth)"]
"""
_OPEN_GW = """graph TD
Net["Internet"] --> GW["API Gateway with Auth"]
GW --> Ollama["Ollama Inference Server"]
"""
_OPEN_BOTH = _OPEN_GW + 'Net --> Ollama\n'
_OPEN_KEYED = """graph TD
Net["Internet"] --> Ollama["Ollama Inference Server (API key)"]
"""


def test_inj011_fires_on_reply_to_llm_to_public_post():
    assert _sov(_GROK)["untrusted_to_trusted_channel"] is True


def test_inj011_suppressed_by_link_scanner():
    assert _sov(_GROK_MOD)["untrusted_to_trusted_channel"] is False


def test_inj011_quiet_when_output_is_internal():
    assert _sov(_GROK_BENIGN)["untrusted_to_trusted_channel"] is False


def test_inj011_does_not_require_a_credentialed_sink():
    # Grokking has no credential; INJ-010 stays quiet while INJ-011 fires.
    s = _sov(_GROK)
    assert s["untrusted_to_privileged_agent"] is False and s["untrusted_to_trusted_channel"] is True


def test_res005_fires_on_direct_internet_to_inference_endpoint():
    assert _sov(_OPEN)["exposed_inference_endpoint"] is True


def test_res005_quiet_behind_gateway():
    assert _sov(_OPEN_GW)["exposed_inference_endpoint"] is False


def test_res005_still_fires_when_a_second_direct_path_exists():
    assert _sov(_OPEN_BOTH)["exposed_inference_endpoint"] is True


def test_res005_quiet_when_endpoint_declares_its_own_control():
    assert _sov(_OPEN_KEYED)["exposed_inference_endpoint"] is False
