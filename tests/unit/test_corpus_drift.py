"""
Unit tests for corpus drift signal + BrainGuardian quality gate (Engine Items 7.2 + 7.3).
"""

import json
import pytest
from pathlib import Path

from chatbot.modules.ta_brain_builder import (
    BrainGuardian,
    compute_drift_score,
    get_last_brain_instance,
    DRIFT_THRESHOLD,
)


# ── fixtures ──────────────────────────────────────────────────────────────────

def _inst(arch_id="arch1", arch_type="web_app", node_count=8, techniques=None):
    return {
        "arch_id": arch_id,
        "arch_type": arch_type,
        "node_count": node_count,
        "techniques": techniques or ["T1190", "T1078", "T1021"],
        "aivss_composite": 5.5,
        "source": "real",
    }


@pytest.fixture
def instances_file(tmp_path):
    p = tmp_path / "ta_brain_instances.jsonl"
    inst = _inst()
    p.write_text(json.dumps(inst) + "\n")
    return p


# ── compute_drift_score ───────────────────────────────────────────────────────

def test_drift_zero_when_identical():
    inst = _inst()
    assert compute_drift_score(inst, inst) == pytest.approx(0.0)


def test_drift_arch_type_flip():
    current = _inst(arch_type="agentic")
    last    = _inst(arch_type="web_app")
    score = compute_drift_score(current, last)
    # arch_type_change weight = 0.30 → minimum component contribution
    assert score >= 0.30


def test_drift_large_node_increase():
    current = _inst(node_count=30)
    last    = _inst(node_count=8)
    score = compute_drift_score(current, last)
    # node_delta = (30-8)/8 = 2.75 → capped at 1.0; weight 0.5
    assert score >= 0.50


def test_drift_large_ttp_drop():
    current = _inst(techniques=["T1190"])
    last    = _inst(techniques=["T1190", "T1078", "T1021", "T1059", "T1203"])
    score = compute_drift_score(current, last)
    # ttp_delta = 4/5 = 0.8; weight 0.2 → 0.16
    assert score >= 0.16


def test_drift_capped_at_one():
    current = _inst(arch_type="agentic", node_count=100, techniques=list("ABCDEFGHIJ"))
    last    = _inst(arch_type="web_app",  node_count=5,   techniques=["T1"])
    score = compute_drift_score(current, last)
    assert score <= 1.0


def test_drift_above_threshold_for_major_change():
    current = _inst(arch_type="agentic", node_count=20)
    last    = _inst(arch_type="web_app",  node_count=5)
    score = compute_drift_score(current, last)
    assert score >= DRIFT_THRESHOLD


# ── get_last_brain_instance ───────────────────────────────────────────────────

def test_get_last_brain_instance_returns_correct(instances_file):
    result = get_last_brain_instance("arch1", instances_file)
    assert result is not None
    assert result["arch_id"] == "arch1"


def test_get_last_brain_instance_unknown_arch(instances_file):
    assert get_last_brain_instance("no_such_arch", instances_file) is None


def test_get_last_brain_instance_missing_file(tmp_path):
    assert get_last_brain_instance("arch1", tmp_path / "missing.jsonl") is None


def test_get_last_brain_instance_last_write_wins(tmp_path):
    p = tmp_path / "ta_brain_instances.jsonl"
    inst1 = _inst(node_count=5)
    inst2 = _inst(node_count=10)  # later write, same arch_id
    p.write_text(json.dumps(inst1) + "\n" + json.dumps(inst2) + "\n")
    result = get_last_brain_instance("arch1", p)
    assert result["node_count"] == 10


# ── BrainGuardian.ingest_guard ────────────────────────────────────────────────

def test_ingest_guard_blocks_brain_fast():
    gt = {"metadata": {"generated_by": "brain_fast"}}
    ok, reason = BrainGuardian().ingest_guard(gt)
    assert ok is False
    assert "circular" in reason


def test_ingest_guard_passes_real():
    gt = {"metadata": {"generated_by": "full_moe"}}
    ok, reason = BrainGuardian().ingest_guard(gt)
    assert ok is True


# ── BrainGuardian.quality_guard ───────────────────────────────────────────────

def test_quality_guard_passes_clean():
    ok, reason = BrainGuardian().quality_guard(_inst(), fidelity=1.0)
    assert ok is True
    assert reason == "ok"


def test_quality_guard_rejects_low_fidelity():
    ok, reason = BrainGuardian().quality_guard(_inst(), fidelity=0.3)
    assert ok is False
    assert "fidelity" in reason


def test_quality_guard_passes_at_threshold():
    ok, _ = BrainGuardian().quality_guard(_inst(), fidelity=BrainGuardian.FIDELITY_THRESHOLD)
    assert ok is True


def test_quality_guard_rejects_high_drift(tmp_path):
    instances_file = tmp_path / "ta_brain_instances.jsonl"
    last = _inst(arch_type="web_app", node_count=5, techniques=["T1190"])
    instances_file.write_text(json.dumps(last) + "\n")

    current = _inst(arch_type="agentic", node_count=25, techniques=["T1059", "T1203", "T1547"])
    ok, reason = BrainGuardian().quality_guard(
        current, fidelity=1.0, instances_path=instances_file
    )
    assert ok is False
    assert "drift" in reason


def test_quality_guard_drift_score_attached_to_instance(tmp_path):
    instances_file = tmp_path / "ta_brain_instances.jsonl"
    last = _inst(arch_type="agentic", node_count=5)
    instances_file.write_text(json.dumps(last) + "\n")

    current = _inst(arch_type="web_app", node_count=30)
    BrainGuardian().quality_guard(current, fidelity=1.0, instances_path=instances_file)
    assert "_drift_score" in current


def test_quality_guard_no_drift_check_when_no_prior(tmp_path):
    instances_file = tmp_path / "empty.jsonl"
    instances_file.write_text("")
    # No prior instance → no drift check → passes
    ok, _ = BrainGuardian().quality_guard(_inst(), fidelity=1.0, instances_path=instances_file)
    assert ok is True


def test_quality_guard_no_instances_path_skips_drift():
    # instances_path=None → drift check skipped, only fidelity check
    ok, _ = BrainGuardian().quality_guard(_inst(), fidelity=1.0, instances_path=None)
    assert ok is True
