"""
Corpus fixture validation — verifies every MMD in tests/data/architectures/ is
non-empty and starts with a valid Mermaid diagram type declaration.

This test has no API or LLM dependency; it runs in <1s. Its primary purpose is to
ensure orphaned fixture files are intentional and parseable, not accidentally empty
or truncated. Architectures that do not have dedicated unit tests are registered here.
"""

import re
from pathlib import Path

import pytest

ARCH_DIR = Path(__file__).parent / "data" / "architectures"

VALID_DIAGRAM_STARTS = re.compile(
    r"^\s*(flowchart|graph|sequenceDiagram|classDiagram|stateDiagram|erDiagram|gantt|pie|gitGraph)",
    re.MULTILINE,
)

# These fixtures have dedicated unit tests in other test files.
# Listed here for documentation; they are NOT re-tested below.
TESTED_ELSEWHERE = {
    "00_serviceentry.mmd",        # test_adapters.py / test_mmd_adapter
    "01_minimal_vulnerable.mmd",  # test_*_evaluator, test_rule_evaluator
    "02_minimal_defended.mmd",    # test_services_concurrent.py
    "03_aws_3tier.mmd",           # diagnostic_regression.py
    "04_zero_trust.mmd",          # test_rule_evaluator
    "05_legacy_flat_network.mmd", # test_rule_evaluator
    "07_gcp_serverless.mmd",      # test_rule_evaluator
    "08_dmz_architecture.mmd",    # test_rule_evaluator
    "09_hybrid_cloud.mmd",        # test_rule_evaluator
    "10_complex_enterprise.mmd",  # test_rule_evaluator
    "12_microservices.mmd",       # test_rule_evaluator
    "13_iot_architecture.mmd",    # test_rule_evaluator
    "14_container_orchestration.mmd",  # test_rule_evaluator
    "17_multi_region.mmd",        # test_rule_evaluator
    "18_saas_multi_tenant.mmd",   # test_rule_evaluator
    "19_blockchain_node.mmd",     # test_rule_evaluator
    "20_data_pipeline.mmd",       # test_rule_evaluator
    "21_agentic_ai_system.mmd",   # test_rule_evaluator / test_detect_rules
    "22_generic_name_with_ai_nodes.mmd",  # test_detect_rules
    "id001_sso_federation.mmd",   # test_detect_rules (DETECT-SEC-002)
}

# Corpus-only fixtures: validated here (structure only, no analysis run).
CORPUS_ONLY = {
    "06_azure_hub_spoke.mmd",
    "11_edge_case_special_chars.mmd",
    "15_cdn_architecture.mmd",
    "16_vpn_remote_access.mmd",
    "23_bookservices.mmd",
    "24_eservices_serverless.mmd",
    "25_fintech_webapp_cloud.mmd",
    "26_healthcare_api_hybrid.mmd",
    "27_govtech_agentic_cloud.mmd",
    "28_ecommerce_microservices_cloud.mmd",
    "29_iot_edge_hybrid.mmd",
    "30_saas_llm_cloud.mmd",
    "99_naked_vulnerable.mmd",
    "ad002_hybrid_identity_adcs.mmd",
    "on_prem_ad_domain.mmd",
    "random_low_TB_seed42.mmd",
}


def _all_mmds():
    if not ARCH_DIR.exists():
        return []
    return sorted(ARCH_DIR.glob("*.mmd"))


def test_no_missing_from_registry():
    """Every MMD file must be registered in TESTED_ELSEWHERE or CORPUS_ONLY."""
    on_disk = {f.name for f in _all_mmds()}
    known = TESTED_ELSEWHERE | CORPUS_ONLY
    unregistered = on_disk - known
    assert not unregistered, (
        f"Unregistered fixture(s) found — add to CORPUS_ONLY or TESTED_ELSEWHERE:\n"
        + "\n".join(sorted(unregistered))
    )


def test_no_ghost_entries():
    """Every entry in CORPUS_ONLY must have a file on disk (no ghost names)."""
    on_disk = {f.name for f in _all_mmds()}
    ghosts = CORPUS_ONLY - on_disk
    assert not ghosts, (
        f"CORPUS_ONLY entries with no file on disk:\n" + "\n".join(sorted(ghosts))
    )


@pytest.mark.parametrize("mmd_file", [f for f in _all_mmds() if f.name in CORPUS_ONLY])
def test_corpus_fixture_valid_mermaid(mmd_file: Path):
    """Corpus fixtures must be non-empty and start with a Mermaid diagram keyword."""
    text = mmd_file.read_text(encoding="utf-8").strip()
    assert text, f"{mmd_file.name} is empty"
    assert VALID_DIAGRAM_STARTS.search(text), (
        f"{mmd_file.name} does not start with a recognised Mermaid diagram type.\n"
        f"First 100 chars: {text[:100]!r}"
    )
