"""detect_architecture_type: a bare 'agent' label is not an AI signal (Entry 263)."""
import pytest
from chatbot.modules.ground_truth_generator import detect_architecture_type


def t(*labels):
    return detect_architecture_type([{"label": l} for l in labels], [], [])


@pytest.mark.parametrize("labels", [
    ("Hybrid Join Agent", "Enrollment Service"),
    ("ImplantAgent", "C2 Server"),
    ("CI Agent", "Registry"),
])
def test_non_ai_agent_labels_are_not_ai_system(labels):
    assert t(*labels) != "ai_system"


@pytest.mark.parametrize("labels", [
    ("LLM Gateway", "Agent"),
    ("Vector DB", "API"),
    ("Embedding Service",),
    ("Copilot Agent Orchestrator",),
    ("AI Agent", "Tool Registry"),
    ("Agentic Planner",),
    ("OpenAI API",),
])
def test_ai_signals_still_ai_system(labels):
    assert t(*labels) == "ai_system"


def test_other_types_unchanged():
    assert t("Web Server", "Load Balancer") == "web_app"
    assert t("S3 Bucket", "Lambda") == "cloud"
