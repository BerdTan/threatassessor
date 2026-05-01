"""
Scoring rubric for attack paths and mitigations.

This module implements three-dimensional scoring:
- ACCURACY (0-100): Attribution to authoritative sources
- RELEVANCE (0-100): Impact vs resistance analysis
- CONFIDENCE (0-100): Work factor and ROI assessment

Scores guide prioritization of mitigations and attack path analysis.
"""

import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

# ============================================================================
# Tactic Impact Weights (based on attack chain progression)
# ============================================================================

TACTIC_IMPACT_WEIGHTS = {
    # High impact: Direct damage or access
    'impact': 1.0,                    # Direct damage to CIA triad
    'exfiltration': 0.95,             # Data loss (highest business impact)
    'command-and-control': 0.9,       # Persistent access established
    'credential-access': 0.85,        # Enables lateral movement
    'privilege-escalation': 0.8,      # Expands attack surface
    'lateral-movement': 0.75,         # Spreads within network

    # Medium impact: Enablers
    'persistence': 0.7,               # Maintains long-term access
    'defense-evasion': 0.65,          # Enables other tactics
    'execution': 0.6,                 # Code runs on target
    'initial-access': 0.55,           # Foothold established
    'collection': 0.5,                # Data gathered (not yet stolen)

    # Low impact: Reconnaissance
    'discovery': 0.4,                 # Information gathering
    'resource-development': 0.2,      # Pre-attack preparation
    'reconnaissance': 0.1,            # External probing
}


# ============================================================================
# DIMENSION 1: ACCURACY SCORING (0-100)
# ============================================================================

def calculate_source_authority(source_type: str) -> float:
    """
    Calculate authority weight based on source type.

    Args:
        source_type: Type of source (mitre_technique, mitre_relationship, etc.)

    Returns:
        Authority weight (0-1)
    """
    weights = {
        'mitre_technique': 1.0,       # Official MITRE technique
        'mitre_relationship': 1.0,    # Official mitigation mapping
        'external_research': 0.8,     # Peer-reviewed research
        'vendor_docs': 0.7,           # Microsoft, Cisco, etc.
        'llm_validated': 0.5,         # LLM with MITRE context
        'llm_speculative': 0.3        # LLM fills gaps (no MITRE data)
    }
    return weights.get(source_type, 0.3)


def calculate_match_confidence(similarity_score: float) -> float:
    """
    Convert similarity score to confidence weight.

    Args:
        similarity_score: Semantic similarity (0-1)

    Returns:
        Confidence weight (0-1)
    """
    if similarity_score >= 0.8:
        return 1.0      # Excellent match
    elif similarity_score >= 0.7:
        return 0.85     # Strong match
    elif similarity_score >= 0.6:
        return 0.7      # Good match
    elif similarity_score >= 0.5:
        return 0.55     # Moderate match
    elif similarity_score >= 0.4:
        return 0.4      # Weak match
    else:
        return 0.2      # Poor match


def calculate_reference_depth(reference_count: int) -> float:
    """
    Calculate score based on number of external references.

    Args:
        reference_count: Number of external citations

    Returns:
        Reference depth score (0-1)
    """
    if reference_count >= 10:
        return 1.0      # Extensively documented
    elif reference_count >= 5:
        return 0.8      # Well documented
    elif reference_count >= 2:
        return 0.6      # Documented
    elif reference_count == 1:
        return 0.4      # Minimally documented
    else:
        return 0.2      # Self-documented only


def calculate_accuracy_score(
    source_type: str,
    similarity_score: float = 1.0,
    reference_count: int = 1,
    mitigation_count: int = 0
) -> float:
    """
    Calculate composite accuracy score (0-100).

    Args:
        source_type: Source authority type
        similarity_score: Semantic match confidence
        reference_count: Number of external references
        mitigation_count: Number of official mitigations (validation consensus)

    Returns:
        Accuracy score (0-100)
    """
    # Component weights
    source_authority = calculate_source_authority(source_type)
    match_confidence = calculate_match_confidence(similarity_score)
    reference_depth = calculate_reference_depth(reference_count)

    # Validation consensus (more mitigations = more validated)
    if mitigation_count >= 5:
        validation_consensus = 1.0
    elif mitigation_count >= 3:
        validation_consensus = 0.8
    elif mitigation_count >= 1:
        validation_consensus = 0.6
    else:
        validation_consensus = 0.3  # No official mitigations

    # Composite score
    accuracy = (
        source_authority * 0.4 +
        match_confidence * 0.3 +
        reference_depth * 0.2 +
        validation_consensus * 0.1
    ) * 100

    return round(accuracy, 1)


# ============================================================================
# DIMENSION 2: RELEVANCE SCORING (0-100)
# ============================================================================

def calculate_impact_score(technique: Dict) -> float:
    """
    Calculate impact score based on tactic position and detection difficulty.

    Args:
        technique: Technique dict with tactics and x_mitre_detection

    Returns:
        Impact score (0-1)
    """
    # Extract tactics from kill_chain_phases if not already in 'tactics' field
    tactics = technique.get('tactics', [])
    if not tactics and 'kill_chain_phases' in technique:
        tactics = [phase.get('phase_name') for phase in technique.get('kill_chain_phases', [])]

    if not tactics:
        return 0.3  # Unknown impact

    # Take MAX tactic weight (worst-case impact)
    base_impact = max(
        TACTIC_IMPACT_WEIGHTS.get(tactic, 0.3)
        for tactic in tactics
    )

    # Modifiers
    modifiers = 0.0

    # Explicit impact type (38/835 techniques have this)
    impact_types = technique.get('x_mitre_impact_type', [])
    if 'Availability' in impact_types:
        modifiers += 0.1  # Denial of service
    if 'Integrity' in impact_types:
        modifiers += 0.05  # Data corruption

    # Detection difficulty (harder to detect = higher impact)
    detection_text = technique.get('x_mitre_detection', '').lower()
    if 'difficult' in detection_text or 'challenging' in detection_text:
        modifiers += 0.05

    final_impact = min(base_impact + modifiers, 1.0)  # Cap at 1.0

    return final_impact


def calculate_resistance_score(technique: Dict, mitigations: List[Dict]) -> float:
    """
    Calculate resistance score (how hard for attackers to execute).

    Args:
        technique: Technique dict
        mitigations: List of available mitigations

    Returns:
        Resistance score (0-1, higher = harder for attackers)
    """
    mitigation_count = len(mitigations)

    # Base resistance from mitigation availability
    if mitigation_count >= 7:
        base_resistance = 0.9    # Highly defendable
    elif mitigation_count >= 5:
        base_resistance = 0.7    # Moderately defendable
    elif mitigation_count >= 3:
        base_resistance = 0.5    # Some defenses
    elif mitigation_count >= 1:
        base_resistance = 0.3    # Limited defenses
    else:
        base_resistance = 0.1    # Weak defenses

    # Modifiers
    detection = technique.get('x_mitre_detection', '').lower()

    if 'monitor' in detection and 'log' in detection:
        base_resistance += 0.1  # Good visibility

    if 'difficult to detect' in detection:
        base_resistance -= 0.1  # Poor visibility

    # Platform modifier (some platforms easier to defend)
    platforms = technique.get('x_mitre_platforms', [])
    if 'Windows' in platforms:
        base_resistance += 0.05  # Mature defenses available
    if any(p in platforms for p in ['ESXi', 'Firmware']):
        base_resistance -= 0.05  # Harder to defend

    return min(max(base_resistance, 0.0), 1.0)  # Clamp to [0, 1]


def calculate_relevance_score(
    technique: Dict,
    mitigations: List[Dict]
) -> float:
    """
    Calculate composite relevance score (0-100).

    Formula: High impact + Low resistance = High relevance

    Args:
        technique: Technique dict
        mitigations: Available mitigations

    Returns:
        Relevance score (0-100)
    """
    impact = calculate_impact_score(technique)
    resistance = calculate_resistance_score(technique, mitigations)

    # High impact + low resistance = high relevance
    relevance = (
        impact * 0.6 +
        (1 - resistance) * 0.4  # Invert resistance
    ) * 100

    return round(relevance, 1)


# ============================================================================
# DIMENSION 3: CONFIDENCE SCORING (0-100)
# ============================================================================

def estimate_ease_of_implementation(mitigation: Dict) -> float:
    """
    Estimate implementation difficulty from mitigation characteristics.

    Args:
        mitigation: Mitigation dict with name and description

    Returns:
        Ease score (0-1, higher = easier)
    """
    name = mitigation.get('mitigation_name', '').lower()
    description = mitigation.get('description', '').lower()

    # Pattern matching for difficulty
    easy_patterns = [
        'update', 'patch', 'filter', 'restrict', 'limit',
        'disable', 'audit', 'log', 'enable', 'configure'
    ]

    medium_patterns = [
        'deploy', 'implement', 'monitor', 'enforce', 'train',
        'authentication', 'encryption', 'policy'
    ]

    hard_patterns = [
        'application control', 'execution prevention',
        'network segmentation', 'privileged account management',
        'architecture', 'redesign', 'replace'
    ]

    if any(p in name or p in description for p in easy_patterns):
        return 0.9  # Quick wins
    elif any(p in name or p in description for p in medium_patterns):
        return 0.6  # Moderate effort
    elif any(p in name or p in description for p in hard_patterns):
        return 0.3  # Major project
    else:
        return 0.5  # Unknown (moderate assumption)


def calculate_roi_score(mitigation: Dict) -> float:
    """
    Calculate ROI based on techniques addressed vs effort.

    Args:
        mitigation: Mitigation dict with addresses_techniques

    Returns:
        ROI score (0-1)
    """
    techniques_addressed = len(mitigation.get('addresses_techniques', []))
    ease = estimate_ease_of_implementation(mitigation)

    # Normalize coverage (assume max 120 techniques for one mitigation)
    coverage_ratio = min(techniques_addressed / 120.0, 1.0)

    # ROI = high coverage + low effort
    roi = (coverage_ratio * 0.6 + ease * 0.4)

    return roi


def estimate_effectiveness(mitigation: Dict, technique: Dict = None) -> float:
    """
    Estimate mitigation effectiveness from description keywords.

    Args:
        mitigation: Mitigation dict
        technique: Optional technique for specific guidance

    Returns:
        Effectiveness score (0-1)
    """
    # Check specific guidance if available
    if technique:
        tech_id = technique.get('external_id', '')
        specific_guidance = mitigation.get('specific_guidance', {})

        # Handle both dict and string formats
        if isinstance(specific_guidance, dict):
            description = specific_guidance.get(tech_id, '').lower()
        elif isinstance(specific_guidance, str):
            description = specific_guidance.lower()
        else:
            description = mitigation.get('description', '').lower()
    else:
        description = mitigation.get('description', '').lower()

    # Strength indicators
    strong_indicators = ['prevent', 'block', 'stop', 'eliminate']
    moderate_indicators = ['reduce', 'limit', 'restrict', 'hinder']
    weak_indicators = ['detect', 'monitor', 'log', 'identify']

    if any(ind in description for ind in strong_indicators):
        return 1.0  # Preventive control
    elif any(ind in description for ind in moderate_indicators):
        return 0.7  # Deterrent control
    elif any(ind in description for ind in weak_indicators):
        return 0.4  # Detective control
    else:
        return 0.6  # Unknown (assume moderate)


def calculate_confidence_score(mitigation: Dict) -> float:
    """
    Calculate composite confidence score (0-100).

    Confidence = ease of implementation + ROI + effectiveness

    Args:
        mitigation: Mitigation dict

    Returns:
        Confidence score (0-100)
    """
    ease = estimate_ease_of_implementation(mitigation)
    roi = calculate_roi_score(mitigation)
    effectiveness = estimate_effectiveness(mitigation)

    confidence = (
        ease * 0.4 +
        roi * 0.35 +
        effectiveness * 0.25
    ) * 100

    return round(confidence, 1)


# ============================================================================
# COMPOSITE SCORE
# ============================================================================

def calculate_composite_score(
    accuracy: float,
    relevance: float,
    confidence: float
) -> float:
    """
    Calculate weighted composite score.

    Args:
        accuracy: Accuracy score (0-100)
        relevance: Relevance score (0-100)
        confidence: Confidence score (0-100)

    Returns:
        Composite score (0-100)
    """
    weights = {
        'accuracy': 0.40,    # Most important: trust the data
        'relevance': 0.35,   # Second: address real threats
        'confidence': 0.25   # Third: practical to implement
    }

    composite = (
        accuracy * weights['accuracy'] +
        relevance * weights['relevance'] +
        confidence * weights['confidence']
    )

    return round(composite, 1)


# ============================================================================
# HIGH-LEVEL SCORING FUNCTIONS
# ============================================================================

def score_technique(
    technique: Dict,
    mitigations: List[Dict],
    similarity_score: float = 1.0
) -> Dict:
    """
    Calculate all scores for a technique.

    Args:
        technique: Technique dict
        mitigations: Available mitigations
        similarity_score: Semantic search similarity

    Returns:
        Dict with all scores and metadata
    """
    # Count external references
    reference_count = len(technique.get('external_references', []))

    # Determine source type
    source_type = 'mitre_technique' if reference_count > 0 else 'llm_speculative'

    # Calculate scores
    accuracy = calculate_accuracy_score(
        source_type=source_type,
        similarity_score=similarity_score,
        reference_count=reference_count,
        mitigation_count=len(mitigations)
    )

    relevance = calculate_relevance_score(technique, mitigations)

    # Confidence is average of mitigation confidence scores
    if mitigations:
        confidence = sum(calculate_confidence_score(m) for m in mitigations) / len(mitigations)
    else:
        confidence = 30.0  # Low confidence without mitigations

    composite = calculate_composite_score(accuracy, relevance, confidence)

    return {
        'accuracy': accuracy,
        'relevance': relevance,
        'confidence': confidence,
        'composite': composite,
        'source_type': source_type,
        'impact': calculate_impact_score(technique),
        'resistance': calculate_resistance_score(technique, mitigations)
    }


def score_mitigation(mitigation: Dict, technique: Dict = None) -> Dict:
    """
    Calculate all scores for a mitigation.

    Args:
        mitigation: Mitigation dict
        technique: Optional technique for specific guidance

    Returns:
        Dict with all scores
    """
    # Source type for mitigations from relationships
    has_addresses = len(mitigation.get('addresses_techniques', [])) > 0
    source_type = 'mitre_relationship' if has_addresses else 'llm_speculative'

    # Accuracy (mitigations from MITRE are authoritative)
    accuracy = calculate_accuracy_score(
        source_type=source_type,
        similarity_score=1.0,  # Direct mapping
        reference_count=1,  # Has MITRE reference
        mitigation_count=len(mitigation.get('addresses_techniques', []))
    )

    # Relevance is based on coverage
    techniques_count = len(mitigation.get('addresses_techniques', []))
    relevance = min(techniques_count / 10.0, 1.0) * 100  # Normalize

    # Confidence
    confidence = calculate_confidence_score(mitigation)

    composite = calculate_composite_score(accuracy, relevance, confidence)

    return {
        'accuracy': accuracy,
        'relevance': relevance,
        'confidence': confidence,
        'composite': composite,
        'source_type': source_type,
        'ease': estimate_ease_of_implementation(mitigation),
        'roi': calculate_roi_score(mitigation),
        'effectiveness': estimate_effectiveness(mitigation, technique)
    }


if __name__ == "__main__":
    # Test scoring module
    print("Testing scoring module...\n")

    # Mock technique
    mock_technique = {
        'external_id': 'T1059.001',
        'name': 'PowerShell',
        'tactics': ['execution'],
        'x_mitre_detection': 'Monitor for PowerShell execution logs',
        'x_mitre_platforms': ['Windows'],
        'external_references': [{'source_name': 'mitre-attack'}] * 5
    }

    # Mock mitigations
    mock_mitigations = [
        {
            'mitigation_id': 'M1042',
            'mitigation_name': 'Disable or Remove Feature or Program',
            'description': 'Disable PowerShell when not needed',
            'addresses_techniques': ['T1059.001', 'T1059.003']
        },
        {
            'mitigation_id': 'M1045',
            'mitigation_name': 'Code Signing',
            'description': 'Enforce execution of signed scripts only',
            'addresses_techniques': ['T1059.001'] * 120  # High ROI
        }
    ]

    # Test technique scoring
    print("=== Technique Scoring ===")
    tech_scores = score_technique(mock_technique, mock_mitigations, similarity_score=0.856)
    print(f"Accuracy:   {tech_scores['accuracy']}/100")
    print(f"Relevance:  {tech_scores['relevance']}/100")
    print(f"Confidence: {tech_scores['confidence']}/100")
    print(f"Composite:  {tech_scores['composite']}/100")
    print()

    # Test mitigation scoring
    print("=== Mitigation Scoring ===")
    for mit in mock_mitigations:
        scores = score_mitigation(mit, mock_technique)
        print(f"{mit['mitigation_name']} ({mit['mitigation_id']})")
        print(f"  Confidence: {scores['confidence']}/100 (Ease: {scores['ease']:.2f}, ROI: {scores['roi']:.2f})")
        print(f"  Composite:  {scores['composite']}/100")
        print()

    print("✅ Scoring module test complete")
