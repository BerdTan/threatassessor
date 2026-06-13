"""
Artifact Extractor for Phase 3C

Extracts 10 artifacts from report directory for LLM critic agents:

TIER 1 (Critical - 80% confidence weight):
1. Attack Paths - expected_attack_paths with per-node techniques
2. Control Recommendations - control_recommendations with hop analysis
3. Residual Risk - rapids_assessment (BEFORE/AFTER)
4. Validation Results - validation_report (6 checks)
5. RAPIDS Assessment - rapids_assessment (6 categories)

TIER 2 (Important - 22% confidence weight):
6. before.mmd - Original architecture diagram
7. after.mmd - Architecture with controls
8. 02_technical_report.md - Detailed analysis
9. 01_executive_summary.md - Business summary
10. 03_action_plan.md - Implementation roadmap

Design:
- Fail fast if Tier 1 missing (critical for analysis)
- Warn if Tier 2 missing (reduces confidence, doesn't block)
- Build indexes for efficient agent queries
- Validate completeness for each tier

VERSION: 1.0 - Initial implementation
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


# ============================================================================
# DATA STRUCTURES
# ============================================================================

@dataclass
class ArtifactSet:
    """
    Complete artifact set for LLM critics.

    Contains all 10 artifacts + indexes for efficient querying.
    """
    # Tier 1: Critical (from ground_truth.json)
    tier1_critical: Dict[str, Any]

    # Tier 2: Important (from report files)
    tier2_important: Dict[str, Any]

    # Completeness tracking
    completeness: Dict[str, Any]

    # Indexes for efficient agent queries
    indexes: Dict[str, Any] = field(default_factory=dict)

    # StoryCaster output (additive — empty dict if not generated)
    user_stories: Dict[str, Any] = field(default_factory=dict)


# ============================================================================
# ARTIFACT EXTRACTOR
# ============================================================================

class ArtifactExtractor:
    """
    Extract and validate 10 artifacts from report directory.

    Usage:
        artifacts = ArtifactExtractor.extract_all(
            report_dir="report/02_minimal_defended",
            ground_truth=gt_dict
        )
    """

    @staticmethod
    def extract_all(report_dir: str, ground_truth: Dict) -> ArtifactSet:
        """
        Extract all 10 artifacts from report directory.

        Args:
            report_dir: Path to report directory (e.g., "report/02_minimal_defended")
            ground_truth: Parsed ground_truth.json dictionary

        Returns:
            ArtifactSet with all artifacts + indexes

        Raises:
            ValueError: If any Tier 1 artifact missing (critical failure)
        """
        logger.info(f"🔍 Extracting artifacts from: {report_dir}")

        # Extract Tier 1 (Critical) - MUST succeed
        tier1 = ArtifactExtractor._extract_tier1(ground_truth)
        logger.info(f"  ✅ Tier 1: {tier1['completeness']['count']}/5 critical artifacts")

        # Extract Tier 2 (Important) - Warn if missing
        tier2 = ArtifactExtractor._extract_tier2(report_dir)
        logger.info(f"  ✅ Tier 2: {tier2['completeness']['count']}/5 important artifacts")

        # Build indexes
        indexes = ArtifactExtractor._build_indexes(tier1, tier2)

        # Story index — separate from structural indexes, built from user_stories key
        user_stories = ground_truth.get("user_stories", {})
        indexes["story_index"] = ArtifactExtractor._build_story_index(user_stories)

        logger.info(f"  ✅ Indexes: {len(indexes)} created")

        # Calculate overall completeness
        completeness = {
            "tier1": tier1["completeness"],
            "tier2": tier2["completeness"],
            "overall": {
                "total": 10,
                "present": tier1["completeness"]["count"] + tier2["completeness"]["count"],
                "confidence_bonus": tier2["completeness"]["confidence_bonus"]
            }
        }

        logger.info(f"✅ Extraction complete: {completeness['overall']['present']}/10 artifacts")

        return ArtifactSet(
            tier1_critical=tier1,
            tier2_important=tier2,
            completeness=completeness,
            indexes=indexes,
            user_stories=ground_truth.get("user_stories", {}),
        )

    # ========================================================================
    # TIER 1: CRITICAL ARTIFACTS (from ground_truth.json)
    # ========================================================================

    @staticmethod
    def _extract_tier1(ground_truth: Dict) -> Dict:
        """
        Extract 5 critical artifacts from ground_truth.json.

        All Tier 1 artifacts MUST be present (fail fast if missing).
        """
        tier1 = {}
        missing = []

        # Artifact 1: Attack Paths
        try:
            tier1["artifact_1_attack_paths"] = ArtifactExtractor._extract_attack_paths(ground_truth)
        except KeyError as e:
            missing.append(f"Artifact 1 (Attack Paths): {e}")

        # Artifact 2: Control Recommendations
        try:
            tier1["artifact_2_controls"] = ArtifactExtractor._extract_controls(ground_truth)
        except KeyError as e:
            missing.append(f"Artifact 2 (Controls): {e}")

        # Artifact 3: Residual Risk
        try:
            tier1["artifact_3_residual_risk"] = ArtifactExtractor._extract_residual_risk(ground_truth)
        except KeyError as e:
            missing.append(f"Artifact 3 (Residual Risk): {e}")

        # Artifact 4: Validation Results
        try:
            tier1["artifact_4_validation"] = ArtifactExtractor._extract_validation(ground_truth)
        except KeyError as e:
            missing.append(f"Artifact 4 (Validation): {e}")

        # Artifact 5: RAPIDS Assessment
        try:
            tier1["artifact_5_rapids"] = ArtifactExtractor._extract_rapids(ground_truth)
        except KeyError as e:
            missing.append(f"Artifact 5 (RAPIDS): {e}")

        # Calculate present count
        present_count = 5 - len(missing)

        # Fail fast if any missing
        if missing:
            error_msg = "CRITICAL: Missing Tier 1 artifacts:\n  - " + "\n  - ".join(missing)
            logger.error(error_msg)
            raise ValueError(error_msg)

        tier1["completeness"] = {
            "count": present_count,
            "total": 5,
            "missing": missing,
            "confidence_weight": 0.80
        }

        return tier1

    @staticmethod
    def _extract_attack_paths(gt: Dict) -> Dict:
        """
        Extract Artifact 1: Attack Paths with per-node techniques.

        Returns: {
            "paths": List[Dict],
            "count": int,
            "node_to_paths": Dict[str, List[int]],
            "technique_to_paths": Dict[str, List[int]]
        }
        """
        paths = gt["expected_attack_paths"]

        # Build indexes
        node_to_paths = {}
        technique_to_paths = {}

        for path_idx, path in enumerate(paths):
            # Index nodes in path (if present - some test data may not have full paths)
            if "path" in path:
                for node in path["path"]:
                    if node not in node_to_paths:
                        node_to_paths[node] = []
                    node_to_paths[node].append(path_idx)

            # Index techniques (stored as strings like "T1213")
            for technique_id in path.get("techniques", []):
                if technique_id not in technique_to_paths:
                    technique_to_paths[technique_id] = []
                technique_to_paths[technique_id].append(path_idx)

        return {
            "paths": paths,
            "count": len(paths),
            "node_to_paths": node_to_paths,
            "technique_to_paths": technique_to_paths
        }

    @staticmethod
    def _extract_controls(gt: Dict) -> Dict:
        """
        Extract Artifact 2: Control Recommendations with hop analysis.

        Returns: {
            "controls": List[Dict],
            "count": int,
            "control_to_paths": Dict[str, List[int]],
            "control_to_techniques": Dict[str, List[str]]
        }
        """
        controls = gt["control_recommendations"]

        # Build indexes
        control_to_paths = {}
        control_to_techniques = {}

        for control in controls:
            # Use "control" field as ID (e.g., "least privilege")
            control_id = control["control"]

            # Index paths affected (field is "attack_paths")
            affected_paths = control.get("attack_paths", [])
            control_to_paths[control_id] = affected_paths

            # Index techniques mitigated (already as strings)
            techniques = control.get("techniques", [])
            control_to_techniques[control_id] = techniques

        return {
            "controls": controls,
            "count": len(controls),
            "control_to_paths": control_to_paths,
            "control_to_techniques": control_to_techniques
        }

    @staticmethod
    def _extract_residual_risk(gt: Dict) -> Dict:
        """
        Extract Artifact 3: Residual Risk (BEFORE/AFTER).

        Returns: {
            "before": Dict,
            "after": Dict,
            "reduction": Dict
        }
        """
        # Residual risk stored at top level
        before_risks = gt.get("residual_risks_before", {})
        after_risks = gt.get("residual_risks_after", {})

        # Overall risk score
        # BEFORE: Uses expected_risk_score (RAPIDS-driven, before controls)
        # AFTER: Uses overall_residual (calculated residual after controls)
        before_score = gt.get("expected_risk_score", 0)

        # Try multiple field names for robustness
        after_score = (
            after_risks.get("overall_residual") or  # Correct field name
            after_risks.get("overall_risk") or      # Fallback for compatibility
            before_risks.get("overall_residual") or # Use before if after missing
            before_score                             # Last resort: assume no change
        )

        reduction = before_score - after_score
        reduction_pct = (reduction / before_score * 100) if before_score > 0 else 0

        # Defensibility: percentage of threats in acceptable range
        # Before: from RAPIDS assessment
        # After: from residual risk calculation
        before_defensibility = gt.get("expected_defensibility", 0)
        after_defensibility = (
            after_risks.get("overall_defensibility") or
            after_risks.get("defensibility_pct") or
            before_defensibility  # Fallback
        )

        return {
            "before": {
                "score": before_score,
                "defensibility": before_defensibility,
                "risks": before_risks
            },
            "after": {
                "score": after_score,
                "defensibility": after_defensibility,
                "risks": after_risks
            },
            "reduction": {
                "absolute": reduction,
                "percentage": reduction_pct
            }
        }

    @staticmethod
    def _extract_validation(gt: Dict) -> Dict:
        """
        Extract Artifact 4: Validation Results (6 checks).

        Returns: {
            "overall_valid": bool,
            "validations": Dict,
            "confidence_baseline": float,
            "confidence_adjustments": Dict,
            "issues": List[str]
        }

        Note: Final confidence (99.5%) is calculated by completeness_validator,
        not stored in ground_truth.json. We use 0.995 as the deterministic baseline.
        """
        val_report = gt["validation_report"]

        return {
            "overall_valid": val_report["overall_valid"],
            "validations": val_report["validations"],  # Dict with 3 validation types
            "confidence_baseline": 0.995,  # Phase 3B+ deterministic confidence
            "confidence_adjustments": val_report["confidence_adjustments"],  # Per-control adjustments
            "issues": val_report["issues_found"]
        }

    @staticmethod
    def _extract_rapids(gt: Dict) -> Dict:
        """
        Extract Artifact 5: RAPIDS Assessment (6 threat categories).

        Returns: {
            "categories": Dict[str, Dict],
            "metadata": Dict
        }
        """
        rapids = gt["rapids_assessment"]

        # Extract 6 threat category assessments
        # (ransomware, application_vulns, phishing, insider_threat, dos, supply_chain)
        categories = {}
        for key in rapids.keys():
            if key != "_metadata":
                categories[key] = rapids[key]

        return {
            "categories": categories,
            "metadata": rapids.get("_metadata", {})
        }

    # ========================================================================
    # TIER 2: IMPORTANT ARTIFACTS (from report files)
    # ========================================================================

    @staticmethod
    def _extract_tier2(report_dir: str) -> Dict:
        """
        Extract 5 important artifacts from report files.

        Warn if missing (don't fail), as they reduce confidence but don't block.
        """
        report_path = Path(report_dir)
        tier2 = {}
        missing = []

        # Artifact 6: before.mmd
        try:
            tier2["artifact_6_before_mmd"] = ArtifactExtractor._read_file(report_path / "before.mmd")
        except FileNotFoundError:
            missing.append("Artifact 6 (before.mmd)")
            tier2["artifact_6_before_mmd"] = None

        # Artifact 7: after.mmd
        try:
            tier2["artifact_7_after_mmd"] = ArtifactExtractor._read_file(report_path / "after.mmd")
        except FileNotFoundError:
            missing.append("Artifact 7 (after.mmd)")
            tier2["artifact_7_after_mmd"] = None

        # Artifact 8: Technical Report
        try:
            tier2["artifact_8_technical_report"] = ArtifactExtractor._read_file(report_path / "02_technical_report.md")
        except FileNotFoundError:
            missing.append("Artifact 8 (02_technical_report.md)")
            tier2["artifact_8_technical_report"] = None

        # Artifact 9: Executive Summary
        try:
            tier2["artifact_9_executive_summary"] = ArtifactExtractor._read_file(report_path / "01_executive_summary.md")
        except FileNotFoundError:
            missing.append("Artifact 9 (01_executive_summary.md)")
            tier2["artifact_9_executive_summary"] = None

        # Artifact 10: Action Plan
        try:
            tier2["artifact_10_action_plan"] = ArtifactExtractor._read_file(report_path / "03_action_plan.md")
        except FileNotFoundError:
            missing.append("Artifact 10 (03_action_plan.md)")
            tier2["artifact_10_action_plan"] = None

        # Warn if missing (don't fail)
        present_count = 5 - len(missing)
        if missing:
            logger.warning(f"⚠️  Missing Tier 2 artifacts ({len(missing)}/5): {', '.join(missing)}")
            logger.warning(f"   Confidence bonus reduced: {present_count * 0.044:.1%}")

        # Calculate confidence bonus (4.4% per artifact, max 22%)
        confidence_bonus = present_count * 0.044

        tier2["completeness"] = {
            "count": present_count,
            "total": 5,
            "missing": missing,
            "confidence_bonus": confidence_bonus,
            "confidence_weight": 0.22
        }

        return tier2

    @staticmethod
    def _read_file(file_path: Path) -> str:
        """Read file content, raise FileNotFoundError if missing."""
        if not file_path.exists():
            raise FileNotFoundError(f"{file_path.name} not found")

        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()

    # ========================================================================
    # INDEXES
    # ========================================================================

    @staticmethod
    def _build_indexes(tier1: Dict, tier2: Dict) -> Dict:
        """
        Build cross-artifact indexes for efficient agent queries.

        Returns: {
            "node_to_paths": Dict[str, List[int]],
            "technique_to_paths": Dict[str, List[int]],
            "control_to_paths": Dict[str, List[int]],
            "control_to_techniques": Dict[str, List[str]],
            "after_mmd_controls": int  # Count of NEW_* nodes in after.mmd
        }
        """
        indexes = {}

        # Already built in artifact extraction
        indexes["node_to_paths"] = tier1["artifact_1_attack_paths"]["node_to_paths"]
        indexes["technique_to_paths"] = tier1["artifact_1_attack_paths"]["technique_to_paths"]
        indexes["control_to_paths"] = tier1["artifact_2_controls"]["control_to_paths"]
        indexes["control_to_techniques"] = tier1["artifact_2_controls"]["control_to_techniques"]

        # Count UNIQUE NEW_* node definitions in after.mmd (if present)
        # Each control appears 3x: definition, connections, styling
        # We only want to count definitions (lines with NEW_CONTROLNAME[)
        after_mmd = tier2.get("artifact_7_after_mmd")
        if after_mmd:
            # Count unique NEW_ node definitions (lines with pattern: NEW_NAME[...)
            import re
            node_pattern = r'^\s*NEW_([A-Z]+)\['
            unique_nodes = set()
            for line in after_mmd.split('\n'):
                match = re.match(node_pattern, line)
                if match:
                    unique_nodes.add(match.group(1))
            indexes["after_mmd_controls"] = len(unique_nodes)
        else:
            indexes["after_mmd_controls"] = 0

        return indexes

    @staticmethod
    def _build_story_index(user_stories: Dict) -> Dict:
        """
        Build story_index from user_stories for critic context injection.

        Returns:
            by_type:      story_type → count (edge micro-stories)
            high_risk:    journey stories with Initial Access or Lateral Movement tactics
            attacker_only: journey stories with no_user_story=True
            corroborated:  journey stories with no_user_story=False
            summary:      one-line distribution string for prompt injection
        """
        from collections import Counter
        edges = user_stories.get("edges", [])
        journeys = user_stories.get("journeys", [])

        by_type = Counter(
            s["story_type"] for s in edges if not s.get("infra_only")
        )

        high_risk = [
            j for j in journeys
            if not j.get("no_user_story")
            and any(t in j.get("threat_relevance", [])
                    for t in ["Initial Access", "Lateral Movement", "Privilege Escalation"])
        ]

        attacker_only = [j for j in journeys if j.get("no_user_story")]
        corroborated  = [j for j in journeys if not j.get("no_user_story")]

        type_str = ", ".join(f"{t}×{c}" for t, c in by_type.most_common())
        summary = (
            f"{len(corroborated)} corroborated journey(s), "
            f"{len(attacker_only)} attacker-only path(s). "
            f"Edge flow types: {type_str or 'none'}."
        )

        return {
            "by_type":       dict(by_type),
            "high_risk":     high_risk,
            "attacker_only": attacker_only,
            "corroborated":  corroborated,
            "summary":       summary,
        }


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def extract_artifacts(report_dir: str, ground_truth_path: Optional[str] = None) -> ArtifactSet:
    """
    Convenience function to extract artifacts from report directory.

    Args:
        report_dir: Path to report directory
        ground_truth_path: Optional path to ground_truth.json (defaults to report_dir/ground_truth.json)

    Returns:
        ArtifactSet with all artifacts
    """
    if ground_truth_path is None:
        ground_truth_path = Path(report_dir) / "ground_truth.json"

    # Load ground truth
    with open(ground_truth_path, 'r', encoding='utf-8') as f:
        ground_truth = json.load(f)

    # Extract artifacts
    return ArtifactExtractor.extract_all(report_dir, ground_truth)


# ============================================================================
# MAIN (for testing)
# ============================================================================

if __name__ == "__main__":
    import sys

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s"
    )

    if len(sys.argv) < 2:
        print("Usage: python3 -m chatbot.modules.artifact_extractor <report_dir>")
        print("Example: python3 -m chatbot.modules.artifact_extractor report/02_minimal_defended")
        sys.exit(1)

    report_dir = sys.argv[1]

    try:
        artifacts = extract_artifacts(report_dir)

        print("\n" + "="*60)
        print("ARTIFACT EXTRACTION SUMMARY")
        print("="*60)

        print(f"\n📦 Tier 1 (Critical): {artifacts.completeness['tier1']['count']}/5")
        print(f"   - Attack Paths: {artifacts.tier1_critical['artifact_1_attack_paths']['count']} paths")
        print(f"   - Controls: {artifacts.tier1_critical['artifact_2_controls']['count']} controls")

        residual_risk = artifacts.tier1_critical['artifact_3_residual_risk']
        print(f"   - Residual Risk: {residual_risk['before']['score']} → {residual_risk['after']['score']} ({residual_risk['reduction']['percentage']:.1f}% reduction)")

        print(f"   - Validation: {artifacts.tier1_critical['artifact_4_validation']['confidence_baseline']:.1%} baseline confidence")
        print(f"   - RAPIDS: {len(artifacts.tier1_critical['artifact_5_rapids']['categories'])} threat categories")

        print(f"\n📄 Tier 2 (Important): {artifacts.completeness['tier2']['count']}/5")
        print(f"   - before.mmd: {'✅' if artifacts.tier2_important['artifact_6_before_mmd'] else '❌'}")
        print(f"   - after.mmd: {'✅' if artifacts.tier2_important['artifact_7_after_mmd'] else '❌'}")
        print(f"   - Technical Report: {'✅' if artifacts.tier2_important['artifact_8_technical_report'] else '❌'}")
        print(f"   - Executive Summary: {'✅' if artifacts.tier2_important['artifact_9_executive_summary'] else '❌'}")
        print(f"   - Action Plan: {'✅' if artifacts.tier2_important['artifact_10_action_plan'] else '❌'}")
        print(f"   - Confidence Bonus: +{artifacts.completeness['tier2']['confidence_bonus']:.1%}")

        print(f"\n🔍 Indexes:")
        print(f"   - node_to_paths: {len(artifacts.indexes['node_to_paths'])} nodes")
        print(f"   - technique_to_paths: {len(artifacts.indexes['technique_to_paths'])} techniques")
        print(f"   - control_to_paths: {len(artifacts.indexes['control_to_paths'])} controls")
        print(f"   - after.mmd controls: {artifacts.indexes['after_mmd_controls']} NEW_* nodes")

        print(f"\n✅ Overall: {artifacts.completeness['overall']['present']}/10 artifacts present")

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        sys.exit(1)
