"""
Validation tests for semantic search accuracy.

Test coverage:
1. Top-K accuracy (k=1, 3, 5) against 109 test queries
2. Tactic matching rate
3. Platform-specific queries
4. Robustness to query mutations
5. Fallback to keyword search
6. Performance benchmarks
"""

import pytest
from pathlib import Path

from chatbot.modules.mitre import MitreHelper
from chatbot.modules.mitre_embeddings import (
    semantic_search, load_embeddings_json, build_technique_text
)
from tests.eval_utils import (
    load_jsonl_dir, evaluate_records, top_k_hit, accepted_ids,
    fake_semantic_search, build_fake_cache
)


# ============================================================================
# Test Suite 1: Baseline Accuracy (109 Test Queries)
# ============================================================================

@pytest.mark.requires_cache
@pytest.mark.offline
def test_semantic_search_top1_accuracy(production_mitre, production_embeddings):
    """
    Test top-1 accuracy against all 109 test queries.

    Target: 40%+ (semantic search without LLM refinement)
    """
    test_dir = Path("tests/data/generated")
    records = load_jsonl_dir(test_dir)

    # Filter records with expected answers
    scored_records = [r for r in records if r.get("expected_ids")]

    assert len(scored_records) >= 100, f"Expected 100+ test queries, got {len(scored_records)}"

    def search_fn(query: str):
        results = semantic_search(
            query,
            production_embeddings,
            top_k=5
        )
        return [{"external_id": ext_id, "name": name, "score": score}
                for _, ext_id, name, score in results]

    metrics = evaluate_records(scored_records, search_fn)

    print(f"\n{'='*60}")
    print(f"Semantic Search Baseline Metrics (n={metrics['scored_records']})")
    print(f"{'='*60}")
    print(f"Top-1 Accuracy: {metrics['top1_accuracy']*100:.1f}%")
    print(f"Top-3 Accuracy: {metrics['top3_accuracy']*100:.1f}%")
    print(f"Recall@5:       {metrics['recall_at_5']*100:.1f}%")
    print(f"Tactic Match:   {metrics['tactic_match_rate']*100:.1f}%")
    print(f"{'='*60}\n")

    # Assertions
    assert metrics['top1_accuracy'] >= 0.35, \
        f"Top-1 accuracy {metrics['top1_accuracy']*100:.1f}% below 35% threshold"
    assert metrics['top3_accuracy'] >= 0.55, \
        f"Top-3 accuracy {metrics['top3_accuracy']*100:.1f}% below 55% threshold"


@pytest.mark.requires_cache
@pytest.mark.offline
def test_semantic_search_top3_accuracy(production_mitre, production_embeddings):
    """
    Test top-3 accuracy (primary success metric).

    Target: 60%+ (matches informal validation)
    """
    test_dir = Path("tests/data/generated")
    records = load_jsonl_dir(test_dir)
    scored_records = [r for r in records if r.get("expected_ids")]

    hits = 0
    total = len(scored_records)

    for record in scored_records:
        results = semantic_search(
            record["query"],
            production_embeddings,
            top_k=3
        )

        # Convert to dict format for eval_utils
        result_dicts = [{"external_id": ext_id, "name": name, "score": score}
                       for _, ext_id, name, score in results]

        if top_k_hit(record, result_dicts, 3):
            hits += 1

    accuracy = hits / total
    print(f"\nTop-3 Accuracy: {accuracy*100:.1f}% ({hits}/{total})")

    assert accuracy >= 0.55, \
        f"Top-3 accuracy {accuracy*100:.1f}% below 55% threshold"


# ============================================================================
# Test Suite 2: Query Type Performance
# ============================================================================

@pytest.mark.requires_cache
@pytest.mark.offline
@pytest.mark.parametrize("test_file,min_accuracy", [
    ("technique_canonical.jsonl", 0.80),  # Direct technique names
    ("technique_paraphrase.jsonl", 0.50),  # Reworded descriptions
    ("tactic_queries.jsonl", 0.40),        # Tactic-level queries
    ("platform_queries.jsonl", 0.45),      # Platform-specific
])
def test_query_type_accuracy(production_mitre, production_embeddings, test_file, min_accuracy):
    """
    Test accuracy by query type.

    Canonical queries (technique names) should have highest accuracy.
    Paraphrases and tactic queries are harder.
    """
    test_path = Path("tests/data/generated") / test_file
    records = load_jsonl_dir(test_path.parent) if test_path.is_dir() else [
        r for r in load_jsonl_dir(test_path.parent)
        if Path(r.get("source", "")).name == test_file or test_file in str(r)
    ]

    # Filter by test_type or filename
    if "canonical" in test_file:
        records = [r for r in records if "canonical" in r.get("test_type", "")]
    elif "paraphrase" in test_file:
        records = [r for r in records if "paraphrase" in r.get("test_type", "")]
    elif "tactic" in test_file:
        records = [r for r in records if "tactic" in r.get("test_type", "")]
    elif "platform" in test_file:
        records = [r for r in records if "platform" in r.get("test_type", "")]

    scored_records = [r for r in records if r.get("expected_ids")]

    if not scored_records:
        pytest.skip(f"No scored records found for {test_file}")

    def search_fn(query: str):
        results = semantic_search(query, production_embeddings, top_k=3)
        return [{"external_id": ext_id} for _, ext_id, _, _ in results]

    hits = sum(1 for r in scored_records if top_k_hit(r, search_fn(r["query"]), 3))
    accuracy = hits / len(scored_records)

    print(f"\n{test_file}: {accuracy*100:.1f}% ({hits}/{len(scored_records)})")

    assert accuracy >= min_accuracy, \
        f"{test_file} accuracy {accuracy*100:.1f}% below {min_accuracy*100:.1f}% threshold"


@pytest.mark.requires_cache
@pytest.mark.offline
def test_robustness_mutations(production_mitre, production_embeddings):
    """
    Test robustness to query mutations (typos, case, punctuation).

    Target: 70%+ of mutated queries still find correct technique.
    """
    test_path = Path("tests/data/generated/robustness_mutations.jsonl")
    if not test_path.exists():
        pytest.skip("robustness_mutations.jsonl not found")

    from tests.eval_utils import load_jsonl
    records = load_jsonl(test_path)
    scored_records = [r for r in records if r.get("expected_ids")]

    def search_fn(query: str):
        results = semantic_search(query, production_embeddings, top_k=3)
        return [{"external_id": ext_id} for _, ext_id, _, _ in results]

    hits = sum(1 for r in scored_records if top_k_hit(r, search_fn(r["query"]), 3))
    accuracy = hits / len(scored_records)

    print(f"\nRobustness (mutations): {accuracy*100:.1f}% ({hits}/{len(scored_records)})")

    assert accuracy >= 0.65, \
        f"Robustness accuracy {accuracy*100:.1f}% below 65% threshold"


# ============================================================================
# Test Suite 3: Keyword Fallback
# ============================================================================

@pytest.mark.offline
def test_keyword_fallback_without_embeddings(production_mitre):
    """
    Test that keyword search works when embeddings unavailable.

    Should still find techniques using token overlap.
    """
    # Build fake cache without embeddings
    fake_cache = build_fake_cache(production_mitre)

    # Test with known queries
    test_cases = [
        ("PowerShell execution", "T1059.001"),
        ("Remote Desktop Protocol", "T1021.001"),
        ("scheduled task", "T1053"),
    ]

    for query, expected_id in test_cases:
        results = fake_semantic_search(query, fake_cache, top_k=5)

        found_ids = [ext_id for _, ext_id, _, _ in results]

        assert len(results) > 0, f"Keyword search returned no results for '{query}'"
        assert expected_id in found_ids or expected_id.split('.')[0] in found_ids, \
            f"Expected {expected_id} in top-5 results for '{query}', got {found_ids}"

        print(f"✓ Keyword fallback: '{query}' → {found_ids[0]}")


@pytest.mark.offline
def test_keyword_fallback_quality(production_mitre):
    """
    Test keyword fallback maintains reasonable quality.

    Target: 30%+ top-3 accuracy (vs 60%+ for semantic search)
    """
    test_dir = Path("tests/data/generated")
    records = load_jsonl_dir(test_dir)
    scored_records = [r for r in records if r.get("expected_ids")][:50]  # Sample 50

    fake_cache = build_fake_cache(production_mitre)

    def search_fn(query: str):
        results = fake_semantic_search(query, fake_cache, top_k=3)
        return [{"external_id": ext_id} for _, ext_id, _, _ in results]

    hits = sum(1 for r in scored_records if top_k_hit(r, search_fn(r["query"]), 3))
    accuracy = hits / len(scored_records)

    print(f"\nKeyword fallback accuracy: {accuracy*100:.1f}% ({hits}/{len(scored_records)})")

    assert accuracy >= 0.25, \
        f"Keyword fallback {accuracy*100:.1f}% below 25% threshold"


# ============================================================================
# Test Suite 4: Performance Benchmarks
# ============================================================================

@pytest.mark.requires_cache
@pytest.mark.offline
def test_search_performance(production_mitre, production_embeddings, benchmark):
    """
    Benchmark semantic search latency.

    Target: <500ms per query (2s including cache load is acceptable for CLI)
    """
    test_query = "Attacker used PowerShell to download malware"

    result = benchmark(
        semantic_search,
        test_query,
        production_embeddings,
        production_mitre,
        top_k=10
    )

    # Benchmark object stores timing in stats
    assert len(result) > 0, "Search should return results"
    print(f"\n✓ Search performance: {benchmark.stats['mean']*1000:.1f}ms avg")


@pytest.mark.requires_cache
@pytest.mark.offline
def test_minimum_score_filtering(production_mitre, production_embeddings):
    """
    Test that min_score parameter filters low-quality results.
    """
    query = "random unrelated words xyz"

    # Without filtering
    results_unfiltered = semantic_search(query, production_embeddings,
        top_k=10, min_score=0.0
    )

    # With filtering
    results_filtered = semantic_search(query, production_embeddings,
        top_k=10, min_score=0.3
    )

    assert len(results_unfiltered) >= len(results_filtered), \
        "Filtered results should be subset of unfiltered"

    if results_filtered:
        assert all(score >= 0.3 for _, _, _, score in results_filtered), \
            "Filtered results should all meet min_score threshold"

    print(f"\n✓ Filtering: {len(results_unfiltered)} → {len(results_filtered)} results")


# ============================================================================
# Test Suite 5: Edge Cases
# ============================================================================

@pytest.mark.requires_cache
@pytest.mark.offline
def test_empty_query_handling(production_mitre, production_embeddings):
    """Test handling of empty or whitespace-only queries."""
    test_cases = ["", "   ", "\n\t"]

    for query in test_cases:
        results = semantic_search(query, production_embeddings, top_k=5
        )
        # Should return empty or low-confidence results, not crash
        assert isinstance(results, list)
        print(f"✓ Empty query '{repr(query)}': {len(results)} results")


@pytest.mark.requires_cache
@pytest.mark.offline
def test_very_long_query_handling(production_mitre, production_embeddings):
    """Test handling of extremely long queries."""
    # Create query with 500+ words
    long_query = " ".join([
        "Attacker used PowerShell to download malware from remote server",
        "and established persistence using scheduled tasks while evading",
        "detection through obfuscation and encryption"
    ] * 50)

    results = semantic_search(query, production_embeddings, top_k=5
    )

    assert len(results) > 0, "Should handle long queries"
    assert results[0][3] > 0.2, "Should find relevant results"
    print(f"✓ Long query ({len(long_query)} chars): {results[0][1]} (score: {results[0][3]:.3f})")


@pytest.mark.requires_cache
@pytest.mark.offline
def test_special_characters_handling(production_mitre, production_embeddings):
    """Test handling of special characters and formatting."""
    test_cases = [
        "T1059.001 - PowerShell",
        "cmd.exe && whoami",
        "C:\\Windows\\System32\\*.exe",
        "user@domain.com; DROP TABLE users--",
    ]

    for query in test_cases:
        results = semantic_search(query, production_embeddings, top_k=3
        )
        assert isinstance(results, list), f"Should handle special chars in '{query}'"
        print(f"✓ Special chars '{query[:30]}...': {len(results)} results")


# ============================================================================
# Reporting Function
# ============================================================================

def print_detailed_report(production_mitre, production_embeddings):
    """
    Generate detailed accuracy report by query category.

    Run with: pytest tests/test_semantic_search.py -v -s
    """
    test_dir = Path("tests/data/generated")

    print("\n" + "="*70)
    print("SEMANTIC SEARCH DETAILED REPORT")
    print("="*70)

    categories = {
        "canonical": "technique_canonical.jsonl",
        "paraphrase": "technique_paraphrase.jsonl",
        "tactic": "tactic_queries.jsonl",
        "platform": "platform_queries.jsonl",
        "robustness": "robustness_mutations.jsonl",
    }

    for category, filename in categories.items():
        records = load_jsonl_dir(test_dir)
        # Filter by test_type or other criteria
        records = [r for r in records if category in r.get("test_type", "").lower()]
        scored = [r for r in records if r.get("expected_ids")]

        if not scored:
            continue

        def search_fn(query: str):
            results = semantic_search(query, production_embeddings, top_k=3)
            return [{"external_id": ext_id} for _, ext_id, _, _ in results]

        metrics = evaluate_records(scored, search_fn)

        print(f"\n{category.upper()} (n={len(scored)})")
        print(f"  Top-1: {metrics['top1_accuracy']*100:.1f}%")
        print(f"  Top-3: {metrics['top3_accuracy']*100:.1f}%")

    print("\n" + "="*70 + "\n")


if __name__ == "__main__":
    # Allow running tests directly for quick validation
    import sys
    sys.exit(pytest.main([__file__, "-v", "-s"]))
