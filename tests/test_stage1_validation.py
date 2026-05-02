"""
Stage 1 Validation: Tactic Smoke Tests

Quick validation of Stage 1 test data before full suite run.
Tests that all 14 MITRE tactics have at least 1 representative technique.
"""

import pytest
from pathlib import Path

from chatbot.modules.mitre import MitreHelper
from chatbot.modules.mitre_embeddings import semantic_search
from tests.eval_utils import load_jsonl_dir, top_k_hit


# All 14 MITRE ATT&CK tactics
ALL_TACTICS = [
    'reconnaissance',
    'resource-development',
    'initial-access',
    'execution',
    'persistence',
    'privilege-escalation',
    'defense-evasion',
    'credential-access',
    'discovery',
    'lateral-movement',
    'collection',
    'command-and-control',
    'exfiltration',
    'impact',
]


@pytest.mark.requires_cache
@pytest.mark.offline
def test_stage1_tactic_coverage(production_mitre, production_embeddings):
    """
    Validate that Stage 1 provides at least 1 technique per tactic.

    Success criteria:
    - All 14 tactics represented in test data
    - Each tactic has at least 1 test query
    """
    test_dir = Path("tests/data/generated")
    records = load_jsonl_dir(test_dir)

    # Count tactics in test data
    tactics_in_tests = set()
    for record in records:
        tactics_in_tests.update(record.get('expected_tactics', []))

    print(f"\n{'='*60}")
    print(f"Stage 1 Tactic Coverage")
    print(f"{'='*60}")
    print(f"Total tactics in MITRE: {len(ALL_TACTICS)}")
    print(f"Tactics in test data:   {len(tactics_in_tests)}")
    print(f"Coverage:               {len(tactics_in_tests)/len(ALL_TACTICS)*100:.1f}%")

    missing = set(ALL_TACTICS) - tactics_in_tests
    if missing:
        print(f"\n⚠️  Missing tactics: {sorted(missing)}")
    else:
        print(f"\n✅ All tactics covered!")

    print(f"{'='*60}\n")

    # Assert full coverage
    assert len(tactics_in_tests) >= 14, \
        f"Expected 14 tactics, found {len(tactics_in_tests)}. Missing: {missing}"


@pytest.mark.requires_cache
@pytest.mark.offline
def test_stage1_per_tactic_accuracy(production_mitre, production_embeddings):
    """
    Test accuracy for each tactic individually.

    Success criteria:
    - No tactic has <30% top-3 accuracy (systematic failure detection)
    - Overall accuracy ≥45% (smoke test threshold)
    """
    test_dir = Path("tests/data/generated")
    records = load_jsonl_dir(test_dir)
    scored_records = [r for r in records if r.get('expected_ids')]

    # Group by tactic
    tactic_results = {}
    for tactic in ALL_TACTICS:
        tactic_records = [r for r in scored_records if tactic in r.get('expected_tactics', [])]
        if not tactic_records:
            continue

        hits = 0
        total = len(tactic_records)

        for record in tactic_records:
            results = semantic_search(
                record['query'],
                production_embeddings,
                top_k=3
            )
            result_dicts = [{'external_id': ext_id} for _, ext_id, _, _ in results]
            if top_k_hit(record, result_dicts, 3):
                hits += 1

        accuracy = hits / total if total > 0 else 0.0
        tactic_results[tactic] = {
            'hits': hits,
            'total': total,
            'accuracy': accuracy
        }

    # Print results
    print(f"\n{'='*70}")
    print(f"Stage 1: Per-Tactic Accuracy")
    print(f"{'='*70}")
    print(f"{'Tactic':<25} {'Queries':<10} {'Top-3 Acc':<12} {'Status'}")
    print(f"{'-'*70}")

    failures = []
    for tactic in ALL_TACTICS:
        if tactic not in tactic_results:
            print(f"{tactic:<25} {'0':<10} {'N/A':<12} {'⚠️  No tests'}")
            continue

        result = tactic_results[tactic]
        accuracy = result['accuracy']
        status = '✅' if accuracy >= 0.30 else '❌ FAIL'

        print(f"{tactic:<25} {result['total']:<10} {accuracy*100:.1f}%{'':<7} {status}")

        if accuracy < 0.30:
            failures.append(tactic)

    # Overall accuracy
    total_hits = sum(r['hits'] for r in tactic_results.values())
    total_queries = sum(r['total'] for r in tactic_results.values())
    overall_accuracy = total_hits / total_queries if total_queries > 0 else 0.0

    print(f"{'-'*70}")
    print(f"{'OVERALL':<25} {total_queries:<10} {overall_accuracy*100:.1f}%{'':<7}")
    print(f"{'='*70}\n")

    # Assertions
    assert len(failures) == 0, \
        f"Tactics with <30% accuracy (systematic failure): {failures}"

    assert overall_accuracy >= 0.40, \
        f"Overall accuracy {overall_accuracy*100:.1f}% below 40% threshold (smoke test minimum)"


@pytest.mark.requires_cache
@pytest.mark.offline
def test_stage1_smoke_techniques(production_mitre, production_embeddings):
    """
    Test specific Stage 1 smoke test techniques.

    These 8 techniques represent the newly covered tactics.
    """
    STAGE1_TECHNIQUES = [
        ('T1595', 'Active Scanning', 'reconnaissance'),
        ('T1583', 'Acquire Infrastructure', 'resource-development'),
        ('T1566', 'Phishing', 'initial-access'),
        ('T1548', 'Abuse Elevation Control Mechanism', 'privilege-escalation'),
        ('T1027', 'Obfuscated Files or Information', 'defense-evasion'),
        ('T1110', 'Brute Force', 'credential-access'),
        ('T1071', 'Application Layer Protocol', 'command-and-control'),
        ('T1486', 'Data Encrypted for Impact', 'impact'),
    ]

    print(f"\n{'='*70}")
    print(f"Stage 1: Smoke Test Techniques")
    print(f"{'='*70}")

    results = []
    for tech_id, name, tactic in STAGE1_TECHNIQUES:
        # Test with canonical name
        search_results = semantic_search(
            name,
            production_embeddings,
            top_k=3
        )

        found_ids = [ext_id for _, ext_id, _, _ in search_results]
        found = tech_id in found_ids

        results.append(found)
        status = '✅' if found else '❌'

        print(f"{status} {tech_id:<10} {name:<40} ({tactic})")
        if found:
            top_result = search_results[0]
            print(f"   → Found at rank {found_ids.index(tech_id) + 1}, score: {top_result[3]:.3f}")

    accuracy = sum(results) / len(results)
    print(f"\n{'='*70}")
    print(f"Smoke test accuracy: {accuracy*100:.1f}% ({sum(results)}/{len(results)})")
    print(f"{'='*70}\n")

    # At least 6/8 techniques should be found (75%)
    assert sum(results) >= 6, \
        f"Only {sum(results)}/8 smoke test techniques found (expected ≥6)"


@pytest.mark.requires_cache
@pytest.mark.offline
def test_stage1_data_quality(production_mitre, production_embeddings):
    """
    Validate Stage 1 test data quality.

    Checks:
    - All queries have expected_ids
    - All queries have expected_tactics
    - No duplicate queries
    - Technique IDs are valid
    """
    test_dir = Path("tests/data/generated")
    stage1_file = test_dir / "stage1_tactic_smoke_tests.jsonl"

    if not stage1_file.exists():
        pytest.skip("Stage 1 test file not found")

    from tests.eval_utils import load_jsonl
    records = load_jsonl(stage1_file)

    print(f"\n{'='*60}")
    print(f"Stage 1: Data Quality Validation")
    print(f"{'='*60}")

    # Check structure
    queries = set()
    issues = []

    for i, record in enumerate(records, 1):
        # Check required fields
        if not record.get('expected_ids'):
            issues.append(f"Query {i}: Missing expected_ids")
        if not record.get('expected_tactics'):
            issues.append(f"Query {i}: Missing expected_tactics")
        if not record.get('query'):
            issues.append(f"Query {i}: Missing query text")

        # Check for duplicates
        query_text = record.get('query', '')
        if query_text in queries:
            issues.append(f"Query {i}: Duplicate query '{query_text[:50]}'")
        queries.add(query_text)

        # Validate technique IDs format
        for tech_id in record.get('expected_ids', []):
            if not tech_id.startswith('T'):
                issues.append(f"Query {i}: Invalid technique ID '{tech_id}'")

    print(f"Total queries:        {len(records)}")
    print(f"Unique queries:       {len(queries)}")
    print(f"Queries with answers: {sum(1 for r in records if r.get('expected_ids'))}")
    print(f"Data quality issues:  {len(issues)}")

    if issues:
        print(f"\n⚠️  Issues found:")
        for issue in issues[:10]:  # Show first 10
            print(f"   - {issue}")
    else:
        print(f"\n✅ All data quality checks passed!")

    print(f"{'='*60}\n")

    assert len(issues) == 0, f"Data quality issues: {issues}"
    assert len(records) == 24, f"Expected 24 queries (8 tactics × 3), got {len(records)}"


if __name__ == "__main__":
    # Allow running tests directly
    import sys
    sys.exit(pytest.main([__file__, "-v", "-s"]))
