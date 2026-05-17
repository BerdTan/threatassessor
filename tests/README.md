# Test Suite Documentation

---
**Last Updated:** 2026-05-17  
**Status:** Current  
**Phase:** 3C+ Complete (v1.3, orchestrator + improvement roadmaps)
---

## Directory Structure

```
tests/
├── conftest.py           # Pytest fixtures (MUST be at root for pytest discovery)
├── eval_utils.py         # Shared test utilities (used by multiple test phases)
├── __init__.py           # Package marker
├── unit/                 # Unit tests
│   ├── __init__.py
│   ├── test_mitre.py
│   └── test_control_detection.py
├── phase2/               # Phase 2 tests (scoring, semantic search - still active)
│   ├── __init__.py
│   ├── test_semantic_search.py
│   ├── test_scoring.py
│   └── (2 obsolete tests archived to archive/tests/phase2/)
├── phase3c/              # Phase 3C agent tests
│   └── (agent test files)
├── data/                 # Test data
│   ├── architectures/    # 22 .mmd test files
│   └── agent_test_cases/ # Agent test cases
└── results/              # Test results output
```

**Key Files:**
- **`conftest.py`** - Must stay at root per pytest convention; provides fixtures to all subdirectories
- **`eval_utils.py`** - Generic test utilities (load_jsonl, evaluate_records); shared across test phases
- **`__init__.py`** - Makes directories importable as Python packages

## Quick Start

```bash
# Run all tests
pytest tests/ -v

# Run specific test suites
pytest tests/unit/ -v                          # Unit tests only
pytest tests/phase2/ -v                        # Phase 2 tests only
pytest tests/unit/test_mitre.py -v             # Specific test file
pytest tests/phase2/test_semantic_search.py -v # Phase 2 specific

# Run self-test (quick 8-second validation)
python3 -m chatbot.main --self-test
```

---

## Test Coverage

### Overall Metrics (Phase 3C+ / v1.3)

| Metric | Result |
|--------|--------|
| **Deterministic confidence** | **99.5%** (6-check validation) |
| **LLM critique confidence** | **85%** (composite score) |
| **Architecture coverage** | **22/22** (100% pass) |
| **Orphan nodes** | **0** (all architectures) |
| **LLM provider tests** | **4/4** (100% pass) |
| **Agent framework** | **3 agents** (Architect, Tester, Red Teamer) |

---

## Test Files

### Unit Tests (`unit/`)

| File | Purpose |
|------|---------|
| `test_mitre.py` | MITRE ATT&CK data loading and access |
| `test_control_detection.py` | Security control detection accuracy |

### Phase 2 Tests (`phase2/`)

| File | Tests | Purpose |
|------|-------|---------|
| `test_semantic_search.py` | 11 | Semantic search accuracy, robustness, fallback |
| `test_scoring.py` | 9 | 3D scoring rubric validation (still used in Phase 3C+) |

**Archived:** `test_phase2_semantic_search.py`, `test_stage1_validation.py` (obsolete Phase 2 tests → archive/tests/phase2/)

### Phase 3C Tests (`phase3c/`)

Agent framework tests (Architect, Tester, Red Teamer critics).

See `scripts/agent_testing/` for agent test execution scripts.

### Test Infrastructure

| File | Purpose |
|------|---------|
| `conftest.py` | Pytest configuration, fixtures |
| `eval_utils.py` | Evaluation metrics, utilities |

### Test Data

| Location | Content |
|----------|---------|
| `data/generated/*.jsonl` | 146 test queries (109 original + 33 Stage 1) |

---

## Test Results

### Latest: Phase 3C+ (v1.3)

**Current Test Results:**
- LLM provider tests: `results/test_results_llm_providers.json` (4/4 passed)
- Agent framework tests: See `scripts/agent_testing/` for agent validation
- Architecture validation: 22/22 architectures pass (99.5% confidence)

**Archived:**
- Phase 2.2 results → `archive/tests/results/phase2.2/` (obsolete)

---

## Reference Documents

### Testing Documentation

All detailed testing documentation has been moved to `docs/testing/` for better organization:

- **[docs/testing/TEST_DATA_ASSESSMENT.md](../docs/testing/TEST_DATA_ASSESSMENT.md)** - Coverage analysis, confidence assessment
- **[docs/testing/FALLBACK_ANALYSIS.md](../docs/testing/FALLBACK_ANALYSIS.md)** - Keyword fallback quality (30% accuracy, acceptable)
- **[docs/testing/GROUND_TRUTH_GUIDE.md](../docs/testing/GROUND_TRUTH_GUIDE.md)** - Ground truth generation methodology
- **[docs/testing/TESTING_STRATEGY.md](../docs/testing/TESTING_STRATEGY.md)** - Overall testing strategy and methodology
- **[docs/testing/DATA_STRATEGY.md](../docs/testing/DATA_STRATEGY.md)** - Test data strategy and generation

---

## Running Tests

### Full Test Suite

```bash
# All tests (takes ~7-8 minutes)
pytest tests/ -v

# Expected output:
# ✅ test_semantic_search.py: 11 tests
# ✅ test_stage1_validation.py: 4 tests
# ✅ test_scoring.py: 9 tests
# Total: 24 tests passed
```

### Quick Validation (Self-Test)

```bash
# Fast validation (8 seconds)
python3 -m chatbot.main --self-test

# Expected output:
# ✅ 9/9 tests passed
# ✅ 5/5 accuracy (100%)
# Confidence: 79% (production-ready)
```

### Specific Test Categories

```bash
# Semantic search only
pytest tests/test_semantic_search.py -v

# Robustness tests only
pytest tests/test_semantic_search.py::test_robustness_mutations -v

# Stage 1 validation only
pytest tests/test_stage1_validation.py -v
```

---

## Test Development

### Adding New Tests

1. **Add test queries** to `data/generated/*.jsonl`
2. **Create test function** in appropriate test_*.py file
3. **Run tests** to validate
4. **Update results** in results/phase2.2/

### Test Query Format

```json
{
  "query": "PowerShell execution",
  "expected_ids": ["T1059.001"],
  "expected_tactics": ["execution"],
  "test_type": "canonical_name",
  "difficulty": "easy"
}
```

---

## Continuous Testing

### Daily

```bash
# Quick health check
python3 -m chatbot.main --self-test-quiet
```

### Weekly

```bash
# Full test suite
pytest tests/ -v
```

### Per Release

```bash
# Complete validation
pytest tests/ -v --tb=short
python3 -m chatbot.main --self-test
```

---

## Test Philosophy

### What We Test

✅ **Critical path** - Core functionality (semantic search, MITRE data)  
✅ **Accuracy claims** - Validate 84.9% accuracy assertion  
✅ **Robustness** - Handle variations, mutations, edge cases  
✅ **Coverage** - All 14 MITRE tactics represented  
✅ **Quality** - Scoring, mitigations, fallbacks

### What We Don't Test

❌ **Every technique** - Only 2.4% coverage (17/703)  
❌ **Real-world patterns** - Production data needed  
❌ **LLM output quality** - Variable (33% uptime)  
❌ **UI/UX** - CLI-only for now

### Testing Strategy

**Iterative validation:**
- Stage 0: Infrastructure (65% confidence)
- Stage 1: Tactic coverage (75% confidence)
- Stage 2: Common techniques (planned)
- Stage 4: Production feedback (ongoing)

See [../docs/testing/TESTING_STRATEGY.md](../docs/testing/TESTING_STRATEGY.md) for details.

---

## Troubleshooting Tests

### Tests Fail: Missing Data

```bash
# Check data files
ls -lh chatbot/data/*.json

# Regenerate if missing
python3 -c "from chatbot.modules.mitre_embeddings import build_technique_embeddings, save_embeddings_json; from chatbot.modules.mitre import MitreHelper; mitre = MitreHelper(use_local=True); cache = build_technique_embeddings(mitre); save_embeddings_json(cache)"
```

### Tests Fail: Import Errors

```bash
# Check module path
export PYTHONPATH=/mnt/c/BACKUP/DEV-TEST:$PYTHONPATH

# Or run with python -m
python3 -m pytest tests/ -v
```

### Tests Slow: Rate Limiting

```bash
# Expected: ~7-8 minutes for full suite
# Reason: Embedding API rate limiting (20 req/min)
# Solution: Run selectively or use --self-test for quick validation
```

---

## See Also

- **[STATUS_AND_PLAN.md](../STATUS_AND_PLAN.md)** - Project status
- **[docs/testing/](../docs/testing/)** - Testing documentation
- **[docs/SELF_TEST.md](../docs/SELF_TEST.md)** - Self-test feature
- **[CLAUDE.md](../CLAUDE.md)** - Developer guidelines

---

**Test Suite Status:** ✅ Complete and Production-Ready  
**Confidence:** 79% (validated with 146 queries)  
**Next:** Deploy and collect production data (Stage 4)
