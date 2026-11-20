"""ta_exporter must read the engine's `expected_attack_paths` (Entry 261 addendum)."""
from chatbot.modules.ta_exporter import _build_assessment

AP = {"id": "AP-1", "entry": "A", "target": "B", "criticality_tier": "HIGH", "techniques": ["T1078"], "hop_count": 2}


def test_engine_key_is_exported():
    a = _build_assessment({"expected_attack_paths": [AP]})
    assert a["attack_paths"][0]["id"] == "AP-1" and a["attack_paths"][0]["techniques"] == ["T1078"]


def test_legacy_key_still_exported():
    assert len(_build_assessment({"attack_paths": [AP]})["attack_paths"]) == 1


def test_empty_is_empty():
    assert _build_assessment({})["attack_paths"] == []
