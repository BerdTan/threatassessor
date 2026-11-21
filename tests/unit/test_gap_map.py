"""Hijack/drift gap map (Entry 264 step 4): every rule is classified, mapping is sane."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "tmeval"))
import gap_map  # noqa: E402


def test_every_rule_classified_and_responded():
    rows = gap_map.build()["rows"]
    assert len(rows) == 70
    assert all(r["class"] in ("hijack", "drift") for r in rows)
    assert all(r["response"] in ("block", "throttle", "deploy_label", "alert_only") for r in rows)


def test_response_from_actions():
    assert gap_map.response({"actions": [{"type": "block_run"}, {"type": "audit_log"}]}) == "block"
    assert gap_map.response({"actions": [{"type": "reduce_budget"}]}) == "throttle"
    assert gap_map.response({"actions": [{"type": "block_deployment"}]}) == "deploy_label"
    assert gap_map.response({"actions": [{"type": "page_soc"}]}) == "alert_only"


def test_no_steer_response_exists_yet():
    """Honest gap: steer is reserved, so no rule may claim it."""
    assert all(r["response"] != "steer" for r in gap_map.build()["rows"])
