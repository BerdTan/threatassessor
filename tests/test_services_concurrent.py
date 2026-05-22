"""
Unit test for service layer thread safety.

Tests concurrent request handling to ensure:
- No race conditions
- Proper request isolation
- Thread-safe MITRE cache access

Run: python3 -m pytest tests/test_services_concurrent.py -v
"""

import pytest
import threading
import time
from pathlib import Path

from chatbot.services import (
    ThreatAnalysisService,
    ValidationService,
    ServiceContext
)


class TestConcurrentRequests:
    """Test concurrent request handling."""

    @pytest.fixture
    def analysis_service(self):
        """Get threat analysis service."""
        return ThreatAnalysisService()

    @pytest.fixture
    def minimal_architecture(self):
        """Get path to minimal test architecture."""
        return "tests/data/architectures/02_minimal_defended.mmd"

    def test_concurrent_analysis(self, analysis_service, minimal_architecture):
        """Test 3 concurrent analysis requests."""

        results = []
        errors = []

        def analyze():
            try:
                result = analysis_service.safe_execute(
                    architecture_path=minimal_architecture,
                    include_validation=False  # Skip validation for speed
                )
                results.append(result)
            except Exception as e:
                errors.append(e)

        # Launch 3 concurrent threads
        threads = [threading.Thread(target=analyze) for _ in range(3)]

        for t in threads:
            t.start()

        for t in threads:
            t.join(timeout=30)  # 30s timeout per thread

        # Verify results
        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert len(results) == 3, f"Expected 3 results, got {len(results)}"

        # All should succeed
        assert all(r.success for r in results), "Some requests failed"

        # All should have unique request IDs
        request_ids = [r.request_id for r in results]
        assert len(set(request_ids)) == 3, "Request IDs not unique"

        # All should have same architecture analysis
        arch_names = [r.data["architecture_name"] for r in results]
        assert all(name == "02_minimal_defended" for name in arch_names)

    def test_mitre_cache_singleton(self):
        """Test MITRE cache is singleton across threads."""
        from chatbot.services.base_service import MitreCache

        caches = []

        def get_cache():
            cache = MitreCache()
            caches.append(id(cache))

        # Launch 5 threads
        threads = [threading.Thread(target=get_cache) for _ in range(5)]

        for t in threads:
            t.start()

        for t in threads:
            t.join()

        # All should be same instance
        assert len(set(caches)) == 1, "MitreCache not singleton"

    def test_context_isolation(self, analysis_service):
        """Test request contexts are isolated."""

        contexts = []

        def create_contexts():
            ctx1 = analysis_service.create_context(metadata={"test": "1"})
            ctx2 = analysis_service.create_context(metadata={"test": "2"})
            contexts.append((ctx1.request_id, ctx2.request_id))

        # Launch 3 threads creating 2 contexts each
        threads = [threading.Thread(target=create_contexts) for _ in range(3)]

        for t in threads:
            t.start()

        for t in threads:
            t.join()

        # Should have 6 unique contexts
        all_ids = [cid for pair in contexts for cid in pair]
        assert len(all_ids) == 6, "Expected 6 contexts"
        assert len(set(all_ids)) == 6, "Context IDs not unique"


class TestServiceValidation:
    """Test input validation."""

    def test_missing_architecture(self):
        """Test error when no architecture provided."""
        service = ThreatAnalysisService()

        result = service.safe_execute()  # No inputs

        assert not result.success
        assert "Validation error" in result.error
        assert "architecture" in result.error.lower()

    def test_missing_file(self):
        """Test error when file doesn't exist."""
        service = ThreatAnalysisService()

        result = service.safe_execute(
            architecture_path="/nonexistent/file.mmd"
        )

        assert not result.success
        assert "not found" in result.error.lower()

    def test_wrong_extension(self):
        """Test error for non-.mmd file."""
        service = ThreatAnalysisService()

        # Create a temp file with wrong extension
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("test content")
            temp_path = f.name

        try:
            result = service.safe_execute(
                architecture_path=temp_path
            )

            assert not result.success
            assert ".mmd" in result.error.lower()
        finally:
            # Cleanup
            Path(temp_path).unlink(missing_ok=True)


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
