# Test Suite Documentation

---
**Last Updated:** 2026-05-02  
**Status:** Current  
**Phase:** 2.2 Complete (84.9% accuracy validated)
---

## Quick Start

```bash
# Run all tests
pytest tests/ -v

# Run specific test suite
pytest tests/test_semantic_search.py -v
pytest tests/test_stage1_validation.py -v
pytest tests/test_scoring.py -v

# Run self-test (quick 8-second validation)
python3 -m chatbot.main --self-test
```

---

## Test Coverage

### Overall Metrics (Phase 2.2)

| Metric | Result |
|--------|--------|
| **Overall accuracy** | **84.9%** (146 queries) |
| **Tactic coverage** | **14/14** (100%) |
| **Min per-tactic** | **75%** (lateral-movement) |
| **Stage 1 smoke** | **100%** (8/8 new techniques) |
| **Robustness** | **100%** (24/24 mutations) |
| **Confidence** | **79%** (production-ready) |

---

## Test Files

### Production Test Suites

| File | Tests | Purpose |
|------|-------|---------|
| `test_semantic_search.py` | 11 | Semantic search accuracy, robustness, fallback |
| `test_stage1_validation.py` | 4 | Tactic coverage, per-tactic accuracy, smoke tests |
| `test_scoring.py` | 9 | 3D scoring rubric validation |

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

### Latest: Phase 2.2

See [results/phase2.2/summary.md](results/phase2.2/summary.md) for complete results.

**Highlights:**
- 84.9% overall accuracy (exceeded 60% target by 41%)
- All 14 tactics validated (no blind spots)
- 100% on robustness and Stage 1 smoke tests

---

## Reference Documents

### Testing Analysis

- **[TEST_DATA_ASSESSMENT.md](TEST_DATA_ASSESSMENT.md)** - Coverage analysis, confidence assessment
- **[FALLBACK_ANALYSIS.md](FALLBACK_ANALYSIS.md)** - Keyword fallback quality (30% accuracy, acceptable)

### Related Documentation

- **[../docs/testing/](../docs/testing/)** - Testing strategy and methodology
- **[../docs/SELF_TEST.md](../docs/SELF_TEST.md)** - Self-test feature documentation

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
