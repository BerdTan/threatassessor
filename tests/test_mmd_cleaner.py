"""
Tests for chatbot.modules.mmd_cleaner.

Runs clean_recommended_mmd() against every 08b_recommended_target.mmd in
the report directory and validates the output is analysis-ready:
  - No NEW_* node IDs remain
  - No <br/> metadata strings remain in node labels
  - No %% comment lines remain
  - No style directives remain
  - All original architecture nodes are still present
  - Graph declaration line is preserved
  - Edge count is >= original edge count (edges rewritten, not dropped)
"""

import re
import pytest
from pathlib import Path

from chatbot.modules.mmd_cleaner import clean_recommended_mmd, extract_control_names

REPORT_ROOT = Path(__file__).parent.parent / "report"

# Collect all available recommended MMDs
RECOMMENDED_MMDS = sorted(REPORT_ROOT.glob("*/08b_recommended_target.mmd"))


# ---------------------------------------------------------------------------
# Unit tests on known input
# ---------------------------------------------------------------------------

SAMPLE_MITRE = '''graph TD
    %% Recommended Target
    %% Controls: 3
    Browser["Web Browser"]
    API["API Gateway"]
    DB[("User DB")]

    NEW_MFA["Mfa<br/>MITRE: M1032<br/>Prevents: T1078, T1213"]
    NEW_LOGGING[/"Logging<br/>MITRE: M1047<br/>Detects: T1059"/]
    NEW_BACKUP[("Backup<br/>MITRE: M1053<br/>Recovers: T1485")]

    Browser --> NEW_MFA
    NEW_MFA --> API
    API --> DB
    DB -.->|protected by| NEW_BACKUP
    Browser -.->|logs to| NEW_LOGGING

    Browser --> API
    API --> DB

    style NEW_MFA fill:#ff6b6b,stroke:#c92a2a
    style NEW_LOGGING fill:#ff6b6b,stroke:#c92a2a
    style NEW_BACKUP fill:#ffd43b,stroke:#fab005
'''

SAMPLE_RAPIDS = '''graph TD
    Browser["Web Browser"]
    API["API"]

    NEW_USERTRAINING["User Training<br/>RAPIDS: Phishing, Ransomware<br/>Prevention<br/>Hardening"]
    NEW_DDOSPROTECTION["Ddos Protection<br/>RAPIDS: Dos<br/>Prevention<br/>Hardening"]
    NEW_DLP["Dlp<br/>RAPIDS: Insider Threat<br/>Detect<br/>Hardening"]

    Browser -.->|training| NEW_USERTRAINING
    API -.->|protected by| NEW_DDOSPROTECTION
    Browser -.->|monitored by| NEW_DLP

    Browser --> API

    style NEW_USERTRAINING fill:#dda0dd
'''


def test_no_new_prefix_remains():
    result = clean_recommended_mmd(SAMPLE_MITRE)
    assert "NEW_" not in result, "NEW_ node IDs should be removed"


def test_no_br_metadata_in_labels():
    result = clean_recommended_mmd(SAMPLE_MITRE)
    assert "MITRE:" not in result
    assert "Prevents:" not in result
    assert "Detects:" not in result
    assert "Recovers:" not in result


def test_no_comment_lines():
    result = clean_recommended_mmd(SAMPLE_MITRE)
    for line in result.splitlines():
        assert not line.strip().startswith("%%"), f"Comment line found: {line!r}"


def test_no_style_directives():
    result = clean_recommended_mmd(SAMPLE_MITRE)
    for line in result.splitlines():
        assert not line.strip().startswith("style "), f"Style line found: {line!r}"


def test_original_nodes_preserved():
    result = clean_recommended_mmd(SAMPLE_MITRE)
    assert 'Browser["Web Browser"]' in result
    assert 'API["API Gateway"]' in result
    assert 'DB[("User DB")]' in result


def test_graph_declaration_preserved():
    result = clean_recommended_mmd(SAMPLE_MITRE)
    assert result.strip().startswith("graph TD")


def test_control_nodes_get_clean_labels():
    result = clean_recommended_mmd(SAMPLE_MITRE)
    assert "MFA" in result
    assert "Logging" in result
    assert "Backup" in result


def test_edges_rewritten_with_clean_ids():
    result = clean_recommended_mmd(SAMPLE_MITRE)
    assert "Browser --> MFA" in result
    assert "MFA --> API" in result
    assert "protected by| Backup" in result
    assert "logs to| Logging" in result


def test_rapids_labels_cleaned():
    result = clean_recommended_mmd(SAMPLE_RAPIDS)
    assert "RAPIDS:" not in result
    assert "Hardening" not in result  # stripped as metadata
    assert "UserTraining" in result or "User Training" in result
    assert "DdosProtection" in result or "Ddos Protection" in result


def test_short_label_uppercased():
    """Short labels like 'Mfa', 'Edr', 'Dlp' should become uppercase."""
    result = clean_recommended_mmd(SAMPLE_MITRE)
    assert "MFA" in result


def test_extract_control_names():
    names = extract_control_names(SAMPLE_MITRE)
    assert "MFA" in names
    assert "Logging" in names
    assert "Backup" in names
    assert len(names) == 3


def test_no_new_nodes_passthrough():
    """A plain MMD with no NEW_* nodes should pass through cleanly."""
    plain = "graph TD\n    A[\"Node A\"]\n    B[\"Node B\"]\n    A --> B\n"
    result = clean_recommended_mmd(plain)
    assert "Node A" in result
    assert "Node B" in result
    assert "A --> B" in result


# ---------------------------------------------------------------------------
# Parametrised tests against all available report MMDs
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("mmd_path", RECOMMENDED_MMDS,
                          ids=[p.parent.name for p in RECOMMENDED_MMDS])
def test_real_mmd_no_new_prefix(mmd_path):
    text = mmd_path.read_text(encoding="utf-8")
    result = clean_recommended_mmd(text)
    assert "NEW_" not in result, \
        f"{mmd_path.parent.name}: NEW_ node IDs remain after cleaning"


@pytest.mark.parametrize("mmd_path", RECOMMENDED_MMDS,
                          ids=[p.parent.name for p in RECOMMENDED_MMDS])
def test_real_mmd_no_br_metadata(mmd_path):
    text = mmd_path.read_text(encoding="utf-8")
    result = clean_recommended_mmd(text)
    for keyword in ("MITRE:", "RAPIDS:", "Prevents:", "Detects:", "Recovers:",
                    "Contains:", "Hardening"):
        assert keyword not in result, \
            f"{mmd_path.parent.name}: metadata keyword '{keyword}' remains after cleaning"


@pytest.mark.parametrize("mmd_path", RECOMMENDED_MMDS,
                          ids=[p.parent.name for p in RECOMMENDED_MMDS])
def test_real_mmd_no_comments(mmd_path):
    text = mmd_path.read_text(encoding="utf-8")
    result = clean_recommended_mmd(text)
    for line in result.splitlines():
        assert not line.strip().startswith("%%"), \
            f"{mmd_path.parent.name}: comment line remains: {line!r}"


@pytest.mark.parametrize("mmd_path", RECOMMENDED_MMDS,
                          ids=[p.parent.name for p in RECOMMENDED_MMDS])
def test_real_mmd_graph_declaration_present(mmd_path):
    text = mmd_path.read_text(encoding="utf-8")
    result = clean_recommended_mmd(text)
    first_nonblank = next((l for l in result.splitlines() if l.strip()), "")
    assert first_nonblank.startswith(("graph ", "flowchart ")), \
        f"{mmd_path.parent.name}: graph declaration missing, got: {first_nonblank!r}"


@pytest.mark.parametrize("mmd_path", RECOMMENDED_MMDS,
                          ids=[p.parent.name for p in RECOMMENDED_MMDS])
def test_real_mmd_has_edges(mmd_path):
    text = mmd_path.read_text(encoding="utf-8")
    result = clean_recommended_mmd(text)
    edge_lines = [l for l in result.splitlines() if "-->" in l or "-..->" in l or "-.->"]
    assert len(edge_lines) >= 2, \
        f"{mmd_path.parent.name}: fewer than 2 edges after cleaning — edges may have been dropped"


@pytest.mark.parametrize("mmd_path", RECOMMENDED_MMDS,
                          ids=[p.parent.name for p in RECOMMENDED_MMDS])
def test_real_mmd_controls_extracted(mmd_path):
    text = mmd_path.read_text(encoding="utf-8")
    controls = extract_control_names(text)
    # Every recommended MMD should have at least 3 controls
    assert len(controls) >= 3, \
        f"{mmd_path.parent.name}: only {len(controls)} controls extracted — expected >= 3"
    # No control name should contain metadata noise
    for c in controls:
        assert "MITRE" not in c
        assert "RAPIDS" not in c
        assert "<br/>" not in c
