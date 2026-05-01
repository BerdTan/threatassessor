"""
Pytest configuration and fixtures for main repo tests.

Strategy: Use production data from chatbot/data/ instead of copying fixtures.
"""
import os
from pathlib import Path

import pytest

from chatbot.modules.mitre import MitreHelper
from chatbot.modules.mitre_embeddings import load_embeddings_json


# ==============================================================================
# Production Data Fixtures (Recommended)
# ==============================================================================

@pytest.fixture(scope="session")
def production_mitre():
    """
    Load production MITRE data for all tests.

    Uses: chatbot/data/enterprise-attack.json (44MB, ~823 techniques)
    Scope: session (loaded once per test run)

    Benefits:
    - Test against actual production data
    - No duplication needed
    - Always in sync with production
    """
    return MitreHelper(use_local=True)


@pytest.fixture(scope="session")
def production_embeddings():
    """
    Load production embedding cache for offline tests.

    Uses: chatbot/data/technique_embeddings.json (45MB, 2048-dim vectors)
    Scope: session (loaded once per test run)

    Returns:
        dict or None: Embedding cache if exists, None if not built yet
    """
    cache_path = Path("chatbot/data/technique_embeddings.json")
    if cache_path.exists():
        return load_embeddings_json(str(cache_path))
    return None


@pytest.fixture
def has_embedding_cache(production_embeddings):
    """
    Check if production embedding cache is available.

    Use this to conditionally skip tests that require embeddings.

    Example:
        @pytest.mark.skipif(not has_embedding_cache, reason="No cache")
        def test_semantic_search(production_embeddings):
            ...
    """
    return production_embeddings is not None


# ==============================================================================
# Test Data Fixtures
# ==============================================================================

@pytest.fixture
def test_queries_dir() -> Path:
    """Path to generated test queries directory."""
    return Path("tests/data/generated")


@pytest.fixture
def has_test_queries(test_queries_dir: Path) -> bool:
    """Check if test query datasets are available."""
    return test_queries_dir.exists() and any(test_queries_dir.glob("*.jsonl"))


# ==============================================================================
# Temporary Directory Fixtures
# ==============================================================================

@pytest.fixture
def temp_output_dir(tmp_path: Path) -> Path:
    """Temporary directory for test outputs."""
    output_dir = tmp_path / "test_output"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


# ==============================================================================
# Pytest Configuration
# ==============================================================================

def pytest_configure(config):
    """Register custom pytest markers."""
    config.addinivalue_line(
        "markers",
        "offline: tests that don't require API access (use production cache)"
    )
    config.addinivalue_line(
        "markers",
        "online: tests that require API access (OpenRouter)"
    )
    config.addinivalue_line(
        "markers",
        "slow: tests taking longer than 5 seconds"
    )
    config.addinivalue_line(
        "markers",
        "requires_cache: tests that need production embedding cache"
    )


def has_api_key() -> bool:
    """Check if OpenRouter API key is configured."""
    return bool(os.getenv("OPENROUTER_API_KEY"))


def pytest_collection_modifyitems(config, items):
    """
    Auto-skip tests based on available resources.

    - Skip @online tests if no API key
    - Skip @requires_cache tests if no embedding cache
    """
    skip_online = pytest.mark.skip(reason="OPENROUTER_API_KEY not set")
    skip_cache = pytest.mark.skip(reason="Embedding cache not built")

    # Check resources
    has_key = has_api_key()
    cache_path = Path("chatbot/data/technique_embeddings.json")
    has_cache = cache_path.exists()

    for item in items:
        # Skip online tests without API key
        if "online" in item.keywords and not has_key:
            item.add_marker(skip_online)

        # Skip cache-requiring tests without cache
        if "requires_cache" in item.keywords and not has_cache:
            item.add_marker(skip_cache)
