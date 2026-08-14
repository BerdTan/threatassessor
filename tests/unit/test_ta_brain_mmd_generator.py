"""
Unit tests — Stage 8: Gap→MMD generator.

All tests are deterministic: no LLM calls, no network.
LLM is mocked at module level via patch("chatbot.modules.ta_brain_mmd_generator.generate_response_with_system").
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from chatbot.modules.ta_brain_mmd_generator import (
    ARCH_VOCABULARIES,
    MAX_DEFAULT,
    MIN_EDGES,
    MIN_NODES,
    build_generation_prompt,
    generate_mmd_for_gap,
    generate_synthetic_mmds,
    get_generation_summary,
    list_synthetic_queue,
    stage_result,
    update_synthetic_status,
    validate_mmd,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

VALID_MMD = """graph TD
    Client[Browser Client] --> APIGateway[API Gateway]
    APIGateway --> AuthService[Auth Service]
    APIGateway --> AppServer[App Server]
    AppServer --> DB[(Database)]
    AppServer --> Cache[Cache]
"""

VALID_MMD_AI = """graph TD
    User[User] --> APIGW[API Gateway]
    APIGW --> RateLimit[Rate Limiter]
    RateLimit --> LLMService[LLM]
    LLMService --> VectorDB[VectorDB]
    APIGW --> AuthSvc[Auth Service]
"""


def _make_gap(gid="GAP-001", arch_type="generic", priority=0.5, forced=False,
              gap_type="coverage_thin", gen_prompt=None):
    return {
        "id": gid,
        "region": f"arch_type:{arch_type}",
        "type": gap_type,
        "confidence_floor": 0.3,
        "generation_prompt": gen_prompt or f"Generate {arch_type} architecture with focus on security.",
        "priority": priority,
        "forced_gap": forced,
        "demand_weight": 0.0,
        "miss_count": 0,
        "variant_count": 0,
        "total_queries": 0,
    }


def _make_brain_json(gaps, tmp_path):
    brain = {"patterns": [], "gaps": gaps, "pattern_version": 1}
    brain_path = tmp_path / "ta_brain.json"
    brain_path.write_text(json.dumps(brain))
    return brain_path


def _write_meta(queue_dir, gen_id, gap_id, status="staged"):
    meta = {
        "gen_id": gen_id,
        "gap_id": gap_id,
        "arch_type": "generic",
        "gap_type": "coverage_thin",
        "generation_prompt": "test prompt",
        "status": status,
        "generated_ts": "2026-08-14T12:00:00+00:00",
        "mmd_file": f"{gen_id}.mmd",
        "valid": True,
        "validation_reason": "ok",
    }
    queue_dir.mkdir(parents=True, exist_ok=True)
    (queue_dir / f"{gen_id}.meta.json").write_text(json.dumps(meta))
    (queue_dir / f"{gen_id}.mmd").write_text(VALID_MMD)
    return meta


# ── validate_mmd ──────────────────────────────────────────────────────────────

def test_validate_mmd_valid():
    valid, reason = validate_mmd(VALID_MMD)
    assert valid is True
    assert reason == "ok"


def test_validate_mmd_no_header():
    bad = "NodeA --> NodeB\nNodeB --> NodeC\n"
    valid, reason = validate_mmd(bad)
    assert valid is False
    assert "header" in reason


def test_validate_mmd_too_few_nodes():
    # Only 2 node ids, below MIN_NODES=3
    bad = "graph TD\n    A --> B\n    B --> A\n"
    valid, reason = validate_mmd(bad)
    assert valid is False
    assert "node" in reason


def test_validate_mmd_too_few_edges():
    # Has 3 nodes defined but only 1 edge — below MIN_EDGES=2
    bad = "graph TD\n    A[NodeA]\n    B[NodeB]\n    C[NodeC]\n    A --> B\n"
    valid, reason = validate_mmd(bad)
    assert valid is False
    assert "edge" in reason


# ── build_generation_prompt ───────────────────────────────────────────────────

def test_build_generation_prompt_includes_arch_vocab():
    gap = _make_gap(arch_type="ai_system")
    system_msg, user_prompt = build_generation_prompt(gap)
    # ai_system vocab should contain "LLM"
    assert "LLM" in user_prompt
    assert "ai_system" in user_prompt


def test_build_generation_prompt_includes_generation_prompt():
    gap = _make_gap(arch_type="web_app", gen_prompt="Focus on authentication gaps.")
    _, user_prompt = build_generation_prompt(gap)
    assert "Focus on authentication gaps." in user_prompt


def test_build_generation_prompt_format_instruction():
    gap = _make_gap()
    _, user_prompt = build_generation_prompt(gap)
    assert "Output ONLY the Mermaid diagram" in user_prompt


# ── generate_mmd_for_gap ─────────────────────────────────────────────────────

def test_generate_mmd_for_gap_valid_response():
    gap = _make_gap(arch_type="web_app")
    mock_llm = MagicMock(return_value=VALID_MMD)
    result = generate_mmd_for_gap(gap, llm_client=mock_llm)
    assert result["valid"] is True
    assert result["gap_id"] == "GAP-001"
    assert result["arch_type"] == "web_app"
    mock_llm.assert_called_once()


def test_generate_mmd_for_gap_invalid_response():
    gap = _make_gap()
    mock_llm = MagicMock(return_value="This is not a Mermaid diagram at all.")
    result = generate_mmd_for_gap(gap, llm_client=mock_llm)
    assert result["valid"] is False
    assert result["validation_reason"] != "ok"


def test_generate_mmd_for_gap_strips_fences():
    """Model wraps output in ```mermaid fences — we strip them."""
    fenced = f"```mermaid\n{VALID_MMD}\n```"
    gap = _make_gap(arch_type="ai_system")
    mock_llm = MagicMock(return_value=fenced)
    result = generate_mmd_for_gap(gap, llm_client=mock_llm)
    assert result["valid"] is True
    assert "```" not in result["mmd_text"]


# ── stage_result ──────────────────────────────────────────────────────────────

def test_stage_result_writes_files(tmp_path):
    result = {
        "gap_id": "GAP-001", "arch_type": "generic", "gap_type": "coverage_thin",
        "generation_prompt": "test", "mmd_text": VALID_MMD,
        "valid": True, "validation_reason": "ok",
    }
    meta = stage_result(result, queue_dir=tmp_path)
    assert meta is not None
    assert meta["status"] == "staged"
    assert (tmp_path / meta["mmd_file"]).exists()
    assert (tmp_path / f"{meta['gen_id']}.meta.json").exists()


def test_stage_result_idempotent(tmp_path):
    # Stage first time
    result = {
        "gap_id": "GAP-001", "arch_type": "generic", "gap_type": "coverage_thin",
        "generation_prompt": "test", "mmd_text": VALID_MMD,
        "valid": True, "validation_reason": "ok",
    }
    first = stage_result(result, queue_dir=tmp_path)
    assert first is not None
    # Second call for same gap_id → skip
    second = stage_result(result, queue_dir=tmp_path)
    assert second is None


def test_stage_result_invalid_not_staged(tmp_path):
    result = {
        "gap_id": "GAP-002", "arch_type": "generic", "gap_type": "coverage_thin",
        "generation_prompt": "test", "mmd_text": "garbage",
        "valid": False, "validation_reason": "missing graph header",
    }
    meta = stage_result(result, queue_dir=tmp_path)
    assert meta is None
    assert list(tmp_path.glob("*.mmd")) == []


# ── generate_synthetic_mmds ───────────────────────────────────────────────────

def test_generate_synthetic_mmds_respects_max(tmp_path):
    gaps = [_make_gap(f"GAP-{i:03d}", priority=0.5) for i in range(1, 6)]
    brain_path = _make_brain_json(gaps, tmp_path)
    queue_dir = tmp_path / "queue"
    mock_llm = MagicMock(return_value=VALID_MMD)

    staged = generate_synthetic_mmds(
        max_per_run=2,
        brain_path=brain_path,
        queue_dir=queue_dir,
        llm_client=mock_llm,
    )
    assert len(staged) == 2
    assert mock_llm.call_count == 2


def test_generate_synthetic_mmds_forced_gap_first(tmp_path):
    gaps = [
        _make_gap("GAP-LOW", priority=0.3, forced=False),
        _make_gap("GAP-HIGH", priority=0.9, forced=True),
    ]
    brain_path = _make_brain_json(gaps, tmp_path)
    queue_dir = tmp_path / "queue"
    mock_llm = MagicMock(return_value=VALID_MMD)

    staged = generate_synthetic_mmds(
        max_per_run=1,
        brain_path=brain_path,
        queue_dir=queue_dir,
        llm_client=mock_llm,
    )
    assert len(staged) == 1
    assert staged[0]["gap_id"] == "GAP-HIGH"


def test_generate_synthetic_mmds_skips_already_staged(tmp_path):
    gaps = [_make_gap("GAP-001"), _make_gap("GAP-002")]
    brain_path = _make_brain_json(gaps, tmp_path)
    queue_dir = tmp_path / "queue"
    # Pre-stage GAP-001
    _write_meta(queue_dir, "GEN-GAP-001-20260814T120000Z", "GAP-001", status="staged")
    mock_llm = MagicMock(return_value=VALID_MMD)

    staged = generate_synthetic_mmds(
        max_per_run=3,
        brain_path=brain_path,
        queue_dir=queue_dir,
        llm_client=mock_llm,
    )
    gap_ids_staged = {m["gap_id"] for m in staged}
    assert "GAP-001" not in gap_ids_staged
    assert "GAP-002" in gap_ids_staged


# ── list_synthetic_queue ──────────────────────────────────────────────────────

def test_list_synthetic_queue_sorted(tmp_path):
    _write_meta(tmp_path, "GEN-GAP-001-20260814T100000Z", "GAP-001")
    _write_meta(tmp_path, "GEN-GAP-002-20260814T120000Z", "GAP-002")
    _write_meta(tmp_path, "GEN-GAP-003-20260814T110000Z", "GAP-003")
    queue = list_synthetic_queue(queue_dir=tmp_path)
    # Should be newest first
    assert queue[0]["gen_id"] == "GEN-GAP-002-20260814T120000Z"
    assert queue[-1]["gen_id"] == "GEN-GAP-001-20260814T100000Z"


# ── update_synthetic_status ───────────────────────────────────────────────────

def test_update_synthetic_status_approve(tmp_path):
    gen_id = "GEN-GAP-001-20260814T120000Z"
    _write_meta(tmp_path, gen_id, "GAP-001", status="staged")
    meta = update_synthetic_status(gen_id, "approved", queue_dir=tmp_path)
    assert meta["status"] == "approved"
    # Verify persisted
    on_disk = json.loads((tmp_path / f"{gen_id}.meta.json").read_text())
    assert on_disk["status"] == "approved"


def test_update_synthetic_status_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        update_synthetic_status("GEN-GAP-999-20260101T000000Z", "approved", queue_dir=tmp_path)


# ── get_generation_summary ────────────────────────────────────────────────────

def test_get_generation_summary_counts(tmp_path):
    _write_meta(tmp_path, "GEN-GAP-001-20260814T100000Z", "GAP-001", status="staged")
    _write_meta(tmp_path, "GEN-GAP-001-20260814T110000Z", "GAP-001", status="approved")
    _write_meta(tmp_path, "GEN-GAP-002-20260814T120000Z", "GAP-002", status="rejected")
    summary = get_generation_summary(queue_dir=tmp_path)
    assert summary["total"] == 3
    assert summary["by_status"]["staged"] == 1
    assert summary["by_status"]["approved"] == 1
    assert summary["by_status"]["rejected"] == 1
    assert summary["by_gap_id"]["GAP-001"] == 2
    assert "GAP-001" in summary["gaps_covered"]
    assert "GAP-002" in summary["gaps_covered"]
