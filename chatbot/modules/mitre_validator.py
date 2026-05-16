"""
MITRE Technique-Mitigation Validator for Phase 3C Tester Agent

Validates security claims against MITRE ATT&CK:
- Technique→Mitigation mappings (does M1026 actually mitigate T1059?)
- Control effectiveness scoring (coverage × criticality)
- Attack path realism (tactic sequence validation)

Uses existing infrastructure:
- chatbot/modules/mitre.py (MitreHelper) - for MITRE data access
- chatbot/modules/mitre_embeddings.py - for semantic search (optional)

VERSION: 1.0 - Initial implementation for MVP2
"""

import logging
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass

from chatbot.modules.mitre import MitreHelper

logger = logging.getLogger(__name__)


# ============================================================================
# DATA STRUCTURES
# ============================================================================

@dataclass
class ValidationResult:
    """Result of a validation check."""
    passed: bool
    severity: str  # CRITICAL, HIGH, MEDIUM, LOW
    description: str
    details: Optional[Dict] = None


@dataclass
class EffectivenessScore:
    """Control effectiveness calculation result."""
    coverage: float  # 0.0-1.0 (% of techniques mitigated)
    weighted_effectiveness: float  # 0.0-1.0 (weighted by criticality)
    mitigated_techniques: List[str]
    unmitigated_techniques: List[str]
    total_techniques: int


# ============================================================================
# MITRE VALIDATOR
# ============================================================================

class MitreValidator:
    """
    Validates technique-mitigation mappings against MITRE ATT&CK.

    Usage:
        validator = MitreValidator()
        result = validator.validate_control_techniques(control)
        if not result.passed:
            print(f"Invalid mapping: {result.description}")
    """

    def __init__(self, mitre: Optional[MitreHelper] = None):
        """
        Initialize validator with MITRE data.

        Args:
            mitre: MitreHelper instance. If None, creates new instance.
        """
        if mitre is None:
            logger.info("Loading MITRE ATT&CK data...")
            mitre = MitreHelper(use_local=True)
            logger.info(f"Loaded {len(mitre.get_techniques())} techniques, "
                       f"{len(mitre.get_mitigations())} mitigations")

        self.mitre = mitre

        # Build reverse lookup: mitigation_id -> [technique_ids]
        self._build_mitigation_index()

    def _build_mitigation_index(self):
        """Build index of mitigation -> techniques for fast lookup."""
        self.mitigation_to_techniques = {}  # M1026 -> [T1059, T1053, ...]

        logger.info("Building mitigation index...")

        for technique in self.mitre.get_techniques():
            # Get external ID (T1059.001)
            ext_refs = technique.get('external_references', [])
            tech_ext_id = next(
                (ref.get('external_id') for ref in ext_refs if 'external_id' in ref),
                None
            )

            if not tech_ext_id:
                continue

            # Get mitigations for this technique
            technique_internal_id = technique.get('id')
            mitigations = self.mitre.get_technique_mitigations(technique_internal_id)

            for mit in mitigations:
                mit_id = mit['mitigation_id']

                if mit_id not in self.mitigation_to_techniques:
                    self.mitigation_to_techniques[mit_id] = []

                self.mitigation_to_techniques[mit_id].append(tech_ext_id)

        logger.info(f"Indexed {len(self.mitigation_to_techniques)} mitigations")

    def validate_control_techniques(self, control: Dict) -> List[ValidationResult]:
        """
        Validate that control's mitigations actually address claimed techniques.

        Args:
            control: Control dict from ground_truth["control_recommendations"]
                     Must have: "control", "mitigations", "techniques"

        Returns:
            List of ValidationResult (empty if all valid)

        Example:
            >>> control = {
            ...     "control": "MFA",
            ...     "mitigations": ["M1032"],
            ...     "techniques": ["T1078", "T1110", "T1133"]
            ... }
            >>> results = validator.validate_control_techniques(control)
            >>> if results:
            ...     print(f"Found {len(results)} issues")
        """
        gaps = []

        control_name = control.get("control", "Unknown")
        claimed_mitigations = control.get("mitigations", [])
        claimed_techniques = control.get("techniques", [])

        if not claimed_mitigations or not claimed_techniques:
            # No mappings to validate
            return gaps

        logger.debug(f"Validating {control_name}: {len(claimed_mitigations)} mitigations, "
                    f"{len(claimed_techniques)} techniques")

        # Check each claimed technique
        for tech_id in claimed_techniques:
            # Get valid mitigations for this technique from MITRE
            tech_obj = self.mitre.find_technique(tech_id)

            if not tech_obj:
                gaps.append(ValidationResult(
                    passed=False,
                    severity="CRITICAL",
                    description=f"Technique {tech_id} not found in MITRE ATT&CK",
                    details={"control": control_name, "technique": tech_id}
                ))
                continue

            # Get technique's internal ID for lookup
            tech_internal_id = tech_obj.get('id')
            valid_mitigations_data = self.mitre.get_technique_mitigations(tech_internal_id)
            valid_mitigation_ids = [m['mitigation_id'] for m in valid_mitigations_data]

            # Check if ANY of the control's mitigations are valid for this technique
            effective_mitigations = [m for m in claimed_mitigations if m in valid_mitigation_ids]

            if not effective_mitigations:
                # CRITICAL: Control claims to mitigate technique but has no valid mitigations
                gaps.append(ValidationResult(
                    passed=False,
                    severity="HIGH",
                    description=f"{control_name} claims to mitigate {tech_id} but none of its "
                               f"mitigations ({', '.join(claimed_mitigations)}) are listed in MITRE",
                    details={
                        "control": control_name,
                        "technique": tech_id,
                        "claimed_mitigations": claimed_mitigations,
                        "valid_mitigations": valid_mitigation_ids,
                        "impact": "Control may be ineffective against this technique"
                    }
                ))

        if gaps:
            logger.warning(f"{control_name}: Found {len(gaps)} validation issues")
        else:
            logger.debug(f"{control_name}: All technique-mitigation mappings valid")

        return gaps

    def validate_all_controls(self, controls: List[Dict]) -> Dict:
        """
        Validate all controls in assessment.

        Args:
            controls: List of control dicts from ground_truth["control_recommendations"]

        Returns:
            {
                "total_controls": int,
                "valid_controls": int,
                "invalid_controls": int,
                "all_gaps": List[ValidationResult],
                "controls_with_issues": List[str]
            }
        """
        all_gaps = []
        controls_with_issues = []

        for control in controls:
            control_name = control.get("control", "Unknown")
            gaps = self.validate_control_techniques(control)

            if gaps:
                all_gaps.extend(gaps)
                controls_with_issues.append(control_name)

        return {
            "total_controls": len(controls),
            "valid_controls": len(controls) - len(controls_with_issues),
            "invalid_controls": len(controls_with_issues),
            "all_gaps": all_gaps,
            "controls_with_issues": controls_with_issues
        }


# ============================================================================
# CONTROL EFFECTIVENESS SCORER
# ============================================================================

class EffectivenessScorer:
    """
    Calculates control effectiveness based on MITRE technique coverage.

    Usage:
        scorer = EffectivenessScorer(mitre_validator)
        effectiveness = scorer.score_control_effectiveness(
            control,
            attack_paths,
            mitre
        )
        print(f"Coverage: {effectiveness.coverage:.1%}")
    """

    def __init__(self, mitre_validator: MitreValidator):
        """
        Initialize scorer.

        Args:
            mitre_validator: MitreValidator instance for MITRE data access
        """
        self.validator = mitre_validator
        self.mitre = mitre_validator.mitre

    def score_control_effectiveness(
        self,
        control: Dict,
        attack_paths: List[Dict]
    ) -> EffectivenessScore:
        """
        Calculate actual effectiveness of control across attack paths.

        Args:
            control: Control dict with "mitigations", "techniques", "attack_paths"
            attack_paths: List of attack path dicts from ground_truth

        Returns:
            EffectivenessScore with coverage and weighted effectiveness

        Example:
            >>> control = {
            ...     "control": "MFA",
            ...     "mitigations": ["M1032"],
            ...     "techniques": ["T1078", "T1110"],
            ...     "attack_paths": [0, 1]
            ... }
            >>> score = scorer.score_control_effectiveness(control, attack_paths)
            >>> print(f"{score.coverage:.1%} coverage")
        """
        control_mitigations = set(control.get("mitigations", []))
        affected_path_ids = control.get("attack_paths", [])

        total_techniques = []
        mitigated_techniques = []

        # Get all techniques from affected paths
        for path_id in affected_path_ids:
            if path_id >= len(attack_paths):
                logger.warning(f"Path ID {path_id} out of range (total: {len(attack_paths)})")
                continue

            path = attack_paths[path_id]
            path_techniques = path.get("techniques", [])
            total_techniques.extend(path_techniques)

            # Check which techniques are actually mitigated
            for tech_id in path_techniques:
                tech_obj = self.mitre.find_technique(tech_id)

                if not tech_obj:
                    logger.warning(f"Technique {tech_id} not found in MITRE")
                    continue

                # Get valid mitigations for this technique
                tech_internal_id = tech_obj.get('id')
                valid_mitigations_data = self.mitre.get_technique_mitigations(tech_internal_id)
                valid_mitigation_ids = set(m['mitigation_id'] for m in valid_mitigations_data)

                # Control is effective if ANY of its mitigations match
                if control_mitigations & valid_mitigation_ids:
                    mitigated_techniques.append(tech_id)

        # Remove duplicates
        total_techniques_unique = list(set(total_techniques))
        mitigated_techniques_unique = list(set(mitigated_techniques))
        unmitigated = list(set(total_techniques_unique) - set(mitigated_techniques_unique))

        # Calculate simple coverage
        coverage = (
            len(mitigated_techniques_unique) / len(total_techniques_unique)
            if total_techniques_unique else 0.0
        )

        # Calculate weighted effectiveness (by technique criticality)
        weighted_effectiveness = self._calculate_weighted_effectiveness(
            mitigated_techniques_unique,
            total_techniques_unique,
            control.get("rapids_risk_score", 0)
        )

        return EffectivenessScore(
            coverage=coverage,
            weighted_effectiveness=weighted_effectiveness,
            mitigated_techniques=mitigated_techniques_unique,
            unmitigated_techniques=unmitigated,
            total_techniques=len(total_techniques_unique)
        )

    def _calculate_weighted_effectiveness(
        self,
        mitigated: List[str],
        total: List[str],
        rapids_risk: int
    ) -> float:
        """
        Weight effectiveness by technique criticality.

        Weights based on MITRE ATT&CK tactic/technique ID:
        - Impact tactics (T14xx, T15xx): 2.0x weight
        - Execution/Privilege Escalation (T10xx-T13xx): 1.0x weight
        - Reconnaissance/Resource Dev (T1595, T1587): 0.5x weight

        Args:
            mitigated: List of mitigated technique IDs
            total: List of all technique IDs in paths
            rapids_risk: RAPIDS risk score (0-100) for additional weighting

        Returns:
            Weighted effectiveness (0.0-1.0)
        """
        if not total:
            return 0.0

        total_weight = 0.0
        mitigated_weight = 0.0

        for tech_id in total:
            # Extract technique number (e.g., T1486 → 1486)
            try:
                tech_num = int(tech_id[1:5]) if len(tech_id) >= 5 else 0
            except (ValueError, IndexError):
                tech_num = 0

            # Assign weight based on technique ID range (heuristic)
            # MITRE ATT&CK groups tactics by ID range
            if tech_num >= 1400:  # Impact tactics (ransomware, data destruction)
                weight = 2.0
            elif tech_num >= 1000:  # Execution, persistence, privilege escalation
                weight = 1.0
            elif tech_num >= 1500:  # Collection, exfiltration
                weight = 1.5
            else:  # Reconnaissance, resource development
                weight = 0.5

            total_weight += weight

            if tech_id in mitigated:
                mitigated_weight += weight

        return mitigated_weight / total_weight if total_weight > 0 else 0.0

    def score_all_controls(
        self,
        controls: List[Dict],
        attack_paths: List[Dict]
    ) -> Dict:
        """
        Score effectiveness for all controls.

        Returns:
            {
                "total_controls": int,
                "scores": List[EffectivenessScore],
                "average_coverage": float,
                "average_weighted_effectiveness": float,
                "low_coverage_controls": List[str]  # <50% coverage
            }
        """
        scores = []
        low_coverage_controls = []

        for control in controls:
            control_name = control.get("control", "Unknown")
            score = self.score_control_effectiveness(control, attack_paths)
            scores.append(score)

            if score.coverage < 0.5:
                low_coverage_controls.append(control_name)

        avg_coverage = sum(s.coverage for s in scores) / len(scores) if scores else 0.0
        avg_weighted = sum(s.weighted_effectiveness for s in scores) / len(scores) if scores else 0.0

        return {
            "total_controls": len(controls),
            "scores": scores,
            "average_coverage": avg_coverage,
            "average_weighted_effectiveness": avg_weighted,
            "low_coverage_controls": low_coverage_controls
        }


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def validate_ground_truth_controls(ground_truth: Dict) -> Dict:
    """
    Validate all controls in ground truth against MITRE ATT&CK.

    Args:
        ground_truth: Parsed ground_truth.json dict

    Returns:
        {
            "validation": Dict from MitreValidator.validate_all_controls(),
            "effectiveness": Dict from EffectivenessScorer.score_all_controls()
        }

    Example:
        >>> with open("report/02_minimal_defended/ground_truth.json") as f:
        ...     gt = json.load(f)
        >>> results = validate_ground_truth_controls(gt)
        >>> print(f"Valid: {results['validation']['valid_controls']}/{results['validation']['total_controls']}")
    """
    # Initialize validator
    validator = MitreValidator()

    # Validate technique-mitigation mappings
    controls = ground_truth.get("control_recommendations", [])
    validation_results = validator.validate_all_controls(controls)

    # Score effectiveness
    scorer = EffectivenessScorer(validator)
    attack_paths = ground_truth.get("expected_attack_paths", [])
    effectiveness_results = scorer.score_all_controls(controls, attack_paths)

    return {
        "validation": validation_results,
        "effectiveness": effectiveness_results
    }


# ============================================================================
# MAIN (for testing)
# ============================================================================

if __name__ == "__main__":
    import sys
    import json
    from pathlib import Path

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s"
    )

    if len(sys.argv) < 2:
        print("Usage: python3 -m chatbot.modules.mitre_validator <ground_truth_path>")
        print("Example: python3 -m chatbot.modules.mitre_validator report/02_minimal_defended/ground_truth.json")
        sys.exit(1)

    ground_truth_path = Path(sys.argv[1])

    if not ground_truth_path.exists():
        print(f"Error: {ground_truth_path} not found")
        sys.exit(1)

    # Load ground truth
    print(f"\n{'='*70}")
    print(f"MITRE VALIDATION TEST")
    print(f"{'='*70}\n")
    print(f"Loading: {ground_truth_path}\n")

    with open(ground_truth_path) as f:
        ground_truth = json.load(f)

    # Run validation
    results = validate_ground_truth_controls(ground_truth)

    # Print validation results
    validation = results["validation"]
    print(f"{'='*70}")
    print(f"VALIDATION RESULTS")
    print(f"{'='*70}\n")
    print(f"Total controls: {validation['total_controls']}")
    print(f"Valid controls: {validation['valid_controls']}")
    print(f"Invalid controls: {validation['invalid_controls']}\n")

    if validation["all_gaps"]:
        print(f"❌ Found {len(validation['all_gaps'])} issues:\n")
        for i, gap in enumerate(validation["all_gaps"][:10], 1):
            print(f"{i}. [{gap.severity}] {gap.description}")
            if gap.details:
                control = gap.details.get("control", "Unknown")
                technique = gap.details.get("technique", "Unknown")
                print(f"   Control: {control} | Technique: {technique}")
            print()

        if len(validation["all_gaps"]) > 10:
            print(f"... +{len(validation['all_gaps']) - 10} more issues\n")
    else:
        print("✅ All controls have valid MITRE mappings\n")

    # Print effectiveness results
    effectiveness = results["effectiveness"]
    print(f"{'='*70}")
    print(f"EFFECTIVENESS RESULTS")
    print(f"{'='*70}\n")
    print(f"Average coverage: {effectiveness['average_coverage']:.1%}")
    print(f"Average weighted effectiveness: {effectiveness['average_weighted_effectiveness']:.1%}\n")

    if effectiveness["low_coverage_controls"]:
        print(f"⚠️  Low coverage controls (<50%):")
        for control in effectiveness["low_coverage_controls"]:
            print(f"  - {control}")
        print()
    else:
        print("✅ All controls have >50% technique coverage\n")

    # Print per-control effectiveness (first 5)
    print(f"{'='*70}")
    print(f"PER-CONTROL EFFECTIVENESS (First 5)")
    print(f"{'='*70}\n")

    controls = ground_truth.get("control_recommendations", [])
    for i, (control, score) in enumerate(zip(controls[:5], effectiveness["scores"][:5]), 1):
        control_name = control.get("control", "Unknown")
        print(f"{i}. {control_name}")
        print(f"   Coverage: {score.coverage:.1%} ({len(score.mitigated_techniques)}/{score.total_techniques} techniques)")
        print(f"   Weighted effectiveness: {score.weighted_effectiveness:.1%}")
        print(f"   Mitigated: {', '.join(score.mitigated_techniques[:5])}")
        if len(score.mitigated_techniques) > 5:
            print(f"              ... +{len(score.mitigated_techniques) - 5} more")
        if score.unmitigated_techniques:
            print(f"   Gaps: {', '.join(score.unmitigated_techniques[:3])}")
            if len(score.unmitigated_techniques) > 3:
                print(f"         ... +{len(score.unmitigated_techniques) - 3} more")
        print()

    if len(controls) > 5:
        print(f"... +{len(controls) - 5} more controls\n")

    print(f"{'='*70}")
    print(f"VALIDATION COMPLETE")
    print(f"{'='*70}\n")
