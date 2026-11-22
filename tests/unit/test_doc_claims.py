"""TAprover checks docs, not just threat models (Blog P44 principle 9).

Pipeline side exports the real stage order to JSON; the verifier checks stage-order claims
against it without importing the pipeline. The old, false wording must be REFUTED.
"""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load(rel, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


tp = _load(".claude/skills/taprover/scripts/taprover.py", "taprover_docs")
exp = _load("scripts/validation/export_stage_manifest.py", "stage_export")

OLD_README = ("**Governance gate** — `BouncerStage` (`required=True`) halts the pipeline on "
              "`CRITICAL` signals before any LLM token is spent.")
OLD_COMMENT = "# BouncerStage between QualityStage and CriticStage: blocks adversarial\n# inputs before any LLM call is made."
SCAN = ["README.md", "docs/ARCHITECTURE.md", "docs/HARNESS.md",
        "chatbot/harness/controller.py", "chatbot/harness/stages.py"]


def test_manifest_puts_analysis_before_the_bouncer():
    m = exp.build()
    assert m["schema"] == "stage-manifest/0.1"
    assert m["scenarios"]["full_moe"].index("analysis") < m["scenarios"]["full_moe"].index("bouncer")


def test_old_wording_is_refuted_in_readme_and_in_code():
    m = exp.build()
    for text in (OLD_README, OLD_COMMENT):
        att = tp.prove_docs(m, {"x": text})
        assert att["overall"] == "REFUTED" and att["checked"] == 1
        assert "after analysis" in att["claims"][0]["evidence"]


def test_a_true_claim_is_verified_when_bouncer_is_first():
    m = {"scenarios": {"s": ["bouncer", "analysis"]}}
    assert tp.prove_docs(m, {"x": OLD_README})["overall"] == "VERIFIED"


def test_manifest_without_a_bouncer_is_unverifiable_not_verified():
    att = tp.prove_docs({"scenarios": {"s": ["analysis"]}}, {"x": OLD_README})
    assert att["overall"] == "UNVERIFIABLE"


def test_unrelated_before_any_llm_line_is_not_a_claim():
    t = "flagged by the completeness validator before any LLM ran."
    assert tp.prove_docs(exp.build(), {"x": t})["checked"] == 0


def test_current_docs_and_code_make_no_false_stage_claim(tmp_path):
    m = tmp_path / "m.json"
    m.write_text(json.dumps(exp.build()))
    docs = [str(ROOT / p) for p in SCAN]
    assert tp.main(["--prove-docs", str(m), "--docs", *docs]) == 0
