# Test Suite

**Version:** 1.4  
**Last Updated:** 2026-05-30

## Structure

```
tests/
├── unit/                        # Fast pytest unit tests (make test)
│   ├── test_mitre.py            # MITRE helper loading and lookup
│   └── test_control_detection.py
├── data/
│   ├── architectures/           # 25 .mmd test architectures (00–22, 99, random)
│   ├── ground_truth/            # 7 reference JSON snapshots for regression
│   └── agent_test_cases/        # MoE agent test inputs
├── conftest.py                  # Pytest fixtures
├── diagnostic_regression.py     # 5 regression checks (ground truth, validator, service)
├── test_database_coverage.py    # Database control coverage validation
├── test_services_concurrent.py  # Thread-safety and service isolation (6 tests)
├── smoke_test.sh                # Quick smoke test (runs demo_deterministic_engine.sh)
└── smoke_test_services.sh       # Service layer smoke test
```

## Running Tests

```bash
# Unit tests only (~30 s, no API key needed)
make test
# or: pytest tests/unit/ -v

# Regression check
python3 tests/diagnostic_regression.py

# Smoke test (requires API server running)
bash tests/smoke_test.sh
```

## Test Data

- **25 architectures** in `tests/data/architectures/` — minimal to complex enterprise, IoT, agentic AI, edge cases
- **7 ground truth snapshots** in `tests/data/ground_truth/` — used by `diagnostic_regression.py` to detect regressions
- **Agent test cases** in `tests/data/agent_test_cases/` — flawed assessment JSON for MoE critic testing

## Archive

Phase 2 scoring/semantic-search tests, phase 3C isolation tests, and generated JSONL query fixtures have been moved to `tests/archive/` (gitignored). They depend on phase-specific LLM calls and are no longer part of the active suite.
