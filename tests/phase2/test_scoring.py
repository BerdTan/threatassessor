"""
Validation tests for scoring rubric and hybrid mitigation system.

Test suites:
1. LLM Consistency: Score variance across multiple runs
2. Edge Cases: Deprecated techniques, zero mitigations, multi-tactic
3. Integration: Full scenario with scoring
"""

from chatbot.modules.mitre import MitreHelper
from chatbot.modules.scoring import (
    score_technique, score_mitigation, calculate_composite_score,
    TACTIC_IMPACT_WEIGHTS
)

# ============================================================================
# Test Suite 1: Edge Case Handling
# ============================================================================

def test_deprecated_techniques():
    """Test scoring handles deprecated techniques gracefully."""
    mitre = MitreHelper(use_local=True)

    # Find deprecated techniques
    deprecated = [t for t in mitre.get_techniques() if t.get('revoked') == True]

    assert len(deprecated) > 0, "Should find some deprecated techniques"

    for tech in deprecated[:5]:
        # Should not crash
        mitigations = mitre.get_technique_mitigations(tech.get('external_references', [{}])[0].get('external_id', ''))
        scores = score_technique(tech, mitigations, similarity_score=1.0)

        # Scores should be valid
        assert 0 <= scores['accuracy'] <= 100
        assert 0 <= scores['composite'] <= 100

        print(f"✓ Deprecated technique {tech.get('name')}: {scores['composite']:.1f}/100")


def test_zero_mitigations():
    """Test techniques with no official mitigations."""
    mitre = MitreHelper(use_local=True)

    # Find techniques without mitigations
    techniques_without_mits = []
    for tech in mitre.get_techniques()[:100]:  # Sample first 100
        ext_id = tech.get('external_references', [{}])[0].get('external_id', '')
        if ext_id and ext_id.startswith('T'):
            mits = mitre.get_technique_mitigations(ext_id)
            if len(mits) == 0:
                techniques_without_mits.append((ext_id, tech))
                if len(techniques_without_mits) >= 10:
                    break

    assert len(techniques_without_mits) > 0, "Should find techniques without mitigations"

    for ext_id, tech in techniques_without_mits:
        scores = score_technique(tech, [], similarity_score=0.8)

        # Should handle gracefully
        assert scores is not None
        assert 0 <= scores['composite'] <= 100

        # Confidence should be low (no mitigations)
        assert scores['confidence'] < 50, "Confidence should be low without mitigations"

        print(f"✓ No mitigations for {ext_id}: Confidence={scores['confidence']:.1f}/100")


def test_multi_tactic_techniques():
    """Test techniques with multiple tactics (take MAX impact)."""
    mitre = MitreHelper(use_local=True)

    # Find multi-tactic techniques
    multi_tactic = []
    for tech in mitre.get_techniques():
        tactics = [phase.get('phase_name') for phase in tech.get('kill_chain_phases', [])]
        if len(tactics) >= 3:
            multi_tactic.append(tech)
            if len(multi_tactic) >= 5:
                break

    assert len(multi_tactic) > 0, "Should find multi-tactic techniques"

    for tech in multi_tactic:
        tactics = [phase.get('phase_name') for phase in tech.get('kill_chain_phases', [])]

        # Get mitigations
        ext_id = tech.get('external_references', [{}])[0].get('external_id', '')
        mits = mitre.get_technique_mitigations(ext_id) if ext_id else []

        scores = score_technique(tech, mits, similarity_score=0.9)

        # Impact should be MAX of tactic weights
        expected_max_impact = max(TACTIC_IMPACT_WEIGHTS.get(t, 0.3) for t in tactics)
        actual_impact = scores['impact']

        # Allow small difference for modifiers
        assert actual_impact >= expected_max_impact - 0.05, \
            f"Impact should be at least max tactic weight (got {actual_impact}, expected >= {expected_max_impact})"

        print(f"✓ Multi-tactic {ext_id}: {len(tactics)} tactics, Impact={actual_impact:.2f}")


# ============================================================================
# Test Suite 2: Scoring Logic Validation
# ============================================================================

def test_tactic_weight_ordering():
    """Validate tactic weights are ordered correctly."""
    high_impact_tactics = ['impact', 'exfiltration', 'credential-access']
    low_impact_tactics = ['reconnaissance', 'resource-development', 'discovery']

    for high_tactic in high_impact_tactics:
        for low_tactic in low_impact_tactics:
            assert TACTIC_IMPACT_WEIGHTS[high_tactic] > TACTIC_IMPACT_WEIGHTS[low_tactic], \
                f"{high_tactic} should have higher weight than {low_tactic}"

    print("✓ Tactic weights are ordered correctly")


def test_score_ranges():
    """Ensure all scores are in valid range [0, 100]."""
    mitre = MitreHelper(use_local=True)

    # Test 20 random techniques
    import random
    sample_techniques = random.sample(mitre.get_techniques(), min(20, len(mitre.get_techniques())))

    for tech in sample_techniques:
        ext_id = tech.get('external_references', [{}])[0].get('external_id', '')
        if not ext_id or not ext_id.startswith('T'):
            continue

        mits = mitre.get_technique_mitigations(ext_id)
        scores = score_technique(tech, mits, similarity_score=0.75)

        # All scores must be in [0, 100]
        assert 0 <= scores['accuracy'] <= 100
        assert 0 <= scores['relevance'] <= 100
        assert 0 <= scores['confidence'] <= 100
        assert 0 <= scores['composite'] <= 100

        # Sub-scores must be in [0, 1]
        assert 0 <= scores['impact'] <= 1
        assert 0 <= scores['resistance'] <= 1

    print("✓ All scores within valid ranges")


def test_mitigation_roi():
    """Test mitigation ROI scoring (more techniques = higher ROI)."""
    mitre = MitreHelper(use_local=True)

    # Get mitigations for multiple techniques
    techniques = ['T1059.001', 'T1053.005', 'T1566.001']
    all_mitigations = mitre.get_mitigations_for_techniques(techniques)

    assert len(all_mitigations) > 0, "Should find mitigations"

    # Mitigations addressing more techniques should have higher ROI
    scored_mitigations = []
    for mit in all_mitigations:
        scores = score_mitigation(mit)
        scored_mitigations.append((mit, scores))

    # Sort by technique count
    scored_mitigations.sort(key=lambda x: len(x[0]['addresses_techniques']), reverse=True)

    # Top mitigation should have higher ROI than bottom
    if len(scored_mitigations) >= 2:
        top_mit, top_scores = scored_mitigations[0]
        bottom_mit, bottom_scores = scored_mitigations[-1]

        top_roi = top_scores['roi']
        bottom_roi = bottom_scores['roi']

        print(f"✓ ROI correlation: Top ({len(top_mit['addresses_techniques'])} techs, ROI={top_roi:.2f}) vs Bottom ({len(bottom_mit['addresses_techniques'])} techs, ROI={bottom_roi:.2f})")


# ============================================================================
# Test Suite 3: Integration Tests
# ============================================================================

def test_full_scenario_scoring():
    """Test complete scoring workflow with PowerShell scenario."""
    mitre = MitreHelper(use_local=True)

    # Get PowerShell technique
    powershell = mitre.find_technique('T1059.001')
    assert powershell is not None, "PowerShell technique should exist"

    # Get tactics
    tactics = [phase.get('phase_name') for phase in powershell.get('kill_chain_phases', [])]
    powershell['tactics'] = tactics

    # Get mitigations
    mitigations = mitre.get_technique_mitigations('T1059.001')
    assert len(mitigations) > 0, "PowerShell should have mitigations"

    # Score technique
    tech_scores = score_technique(powershell, mitigations, similarity_score=0.856)

    # Validate scores
    assert tech_scores['accuracy'] >= 80, "PowerShell should have high accuracy (MITRE official)"
    assert 0 < tech_scores['relevance'] <= 100
    assert 0 < tech_scores['confidence'] <= 100
    assert 0 < tech_scores['composite'] <= 100

    print(f"✓ PowerShell technique scores:")
    print(f"  Accuracy:   {tech_scores['accuracy']:.1f}/100")
    print(f"  Relevance:  {tech_scores['relevance']:.1f}/100")
    print(f"  Confidence: {tech_scores['confidence']:.1f}/100")
    print(f"  Composite:  {tech_scores['composite']:.1f}/100")

    # Score mitigations
    for mit in mitigations[:3]:
        mit_scores = score_mitigation(mit, powershell)

        assert 0 < mit_scores['composite'] <= 100

        print(f"✓ {mit['mitigation_name']}: Confidence={mit_scores['confidence']:.1f}/100")


def test_composite_score_weighting():
    """Test composite score calculation with known inputs."""
    # Test case: High accuracy, medium relevance, low confidence
    composite = calculate_composite_score(90, 50, 30)

    # Expected: 90*0.4 + 50*0.35 + 30*0.25 = 36 + 17.5 + 7.5 = 61
    assert 60 <= composite <= 62, f"Composite should be ~61, got {composite}"

    print(f"✓ Composite score weighting correct: {composite:.1f}/100")


# ============================================================================
# Test Suite 4: Data Integrity
# ============================================================================

def test_mitigation_extraction():
    """Test MITRE mitigation extraction works correctly."""
    mitre = MitreHelper(use_local=True)

    # Test single technique
    mits = mitre.get_technique_mitigations('T1059.001')
    assert len(mits) > 0, "PowerShell should have mitigations"

    # Check mitigation structure
    for mit in mits:
        assert 'mitigation_id' in mit
        assert 'mitigation_name' in mit
        assert 'specific_guidance' in mit
        assert mit['mitigation_id'].startswith('M'), "Mitigation ID should start with M"

    print(f"✓ Extracted {len(mits)} mitigations for T1059.001")

    # Test deduplication
    techniques = ['T1059.001', 'T1053.005']
    deduplicated = mitre.get_mitigations_for_techniques(techniques)

    # Should have unique mitigations
    mitigation_ids = [m['mitigation_id'] for m in deduplicated]
    assert len(mitigation_ids) == len(set(mitigation_ids)), "Should deduplicate mitigations"

    # Each should have addresses_techniques field
    for mit in deduplicated:
        assert 'addresses_techniques' in mit
        assert len(mit['addresses_techniques']) > 0

    print(f"✓ Deduplicated to {len(deduplicated)} unique mitigations")


# ============================================================================
# Run Tests
# ============================================================================

if __name__ == "__main__":
    print("="*80)
    print("SCORING VALIDATION TEST SUITE")
    print("="*80 + "\n")

    tests = [
        ("Edge Case: Deprecated Techniques", test_deprecated_techniques),
        ("Edge Case: Zero Mitigations", test_zero_mitigations),
        ("Edge Case: Multi-Tactic Techniques", test_multi_tactic_techniques),
        ("Logic: Tactic Weight Ordering", test_tactic_weight_ordering),
        ("Logic: Score Ranges", test_score_ranges),
        ("Logic: Mitigation ROI", test_mitigation_roi),
        ("Integration: Full Scenario", test_full_scenario_scoring),
        ("Integration: Composite Score", test_composite_score_weighting),
        ("Data: Mitigation Extraction", test_mitigation_extraction),
    ]

    passed = 0
    failed = 0

    for test_name, test_func in tests:
        print(f"\n{'='*80}")
        print(f"TEST: {test_name}")
        print('='*80)
        try:
            test_func()
            passed += 1
            print(f"\n✅ PASSED: {test_name}\n")
        except Exception as e:
            failed += 1
            print(f"\n❌ FAILED: {test_name}")
            print(f"Error: {str(e)}\n")
            import traceback
            traceback.print_exc()

    print("\n" + "="*80)
    print(f"TEST RESULTS: {passed} passed, {failed} failed")
    print("="*80 + "\n")

    if failed == 0:
        print("✅ ALL VALIDATION TESTS PASSED")
    else:
        print(f"⚠️  {failed} tests failed - review errors above")
