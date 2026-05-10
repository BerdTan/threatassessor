# Scripts Directory

Integration tests, validation utilities, and workflow automation scripts.

---

## Purpose

Scripts for:
- **Integration testing** - Cross-module validation
- **Workflow automation** - Batch operations and data generation
- **System validation** - End-to-end checks

**Not for:** Unit tests (use `tests/` with pytest)

---

## Integration Tests

### LLM Provider Testing
- **`test_llm_providers.py`** - Multi-provider LLM integration tests
  ```bash
  python3 scripts/test_llm_providers.py                    # All providers
  python3 scripts/test_llm_providers.py --provider bedrock # Specific provider
  python3 scripts/test_llm_providers.py --test-verify      # LLM as Judge
  ```
  Results: `tests/results/test_results_llm_providers.json`

- **`test_openrouter.py`** - OpenRouter API integration validation
  ```bash
  python3 scripts/test_openrouter.py
  ```

### Architecture Validation
- **`backtest_all_architectures.py`** - Validate all test architectures
  ```bash
  python3 scripts/backtest_all_architectures.py                          # All architectures
  python3 scripts/backtest_all_architectures.py --architectures 10_* 03_* # Specific ones
  ```

- **`validate_engine_accuracy.py`** - Engine accuracy against ground truth
  ```bash
  python3 scripts/validate_engine_accuracy.py
  ```

- **`validate_parser_harness.py`** - Parser correctness validation
  ```bash
  python3 scripts/validate_parser_harness.py
  ```

---

## Validation Utilities

- **`check_orphans.py`** - Check for orphan nodes in architectures
  ```bash
  python3 scripts/check_orphans.py                     # All architectures
  python3 scripts/check_orphans.py 10_complex 03_aws  # Specific ones
  ```

- **`validate_llm_config.py`** - Validate LLM provider configuration
  ```bash
  python3 scripts/validate_llm_config.py
  ```

---

## Data Generation & Utilities

- **`generate_ground_truth.py`** - Semi-automated ground truth generation
  ```bash
  python3 scripts/generate_ground_truth.py tests/data/architectures/06_azure_3tier.mmd
  ```

- **`batch_generate_ground_truth.sh`** - Batch ground truth generation
  ```bash
  ./scripts/batch_generate_ground_truth.sh
  ```

- **`demo_mitre_advice.py`** - Demo MITRE helper functionality
  ```bash
  python3 scripts/demo_mitre_advice.py
  ```

---

## Workflow Scripts

- **`sync_repos.sh`** - Repository synchronization utility
  ```bash
  ./scripts/sync_repos.sh
  ```

---

## Organization Principles

### scripts/ vs tests/
- **scripts/** - Integration tests, workflows, batch operations
- **tests/** - Unit tests (pytest), test data, test fixtures

### When to use scripts/
✅ Integration testing (cross-module validation)  
✅ Workflow automation (batch processing)  
✅ System validation (end-to-end checks)  
✅ Data generation utilities  
✅ Demo/example scripts

### When to use tests/
✅ Unit tests (pytest test_*.py)  
✅ Test fixtures and utilities (conftest.py, eval_utils.py)  
✅ Test data (tests/data/)  
✅ Test results (tests/results/)

---

## Running All Validations

```bash
# 1. Unit tests (pytest)
pytest tests/ -v

# 2. Architecture validation
python3 scripts/backtest_all_architectures.py

# 3. LLM provider validation
python3 scripts/validate_llm_config.py

# 4. Orphan detection
python3 scripts/check_orphans.py
```

---

**See Also:**
- [tests/README.md](../tests/README.md) - Unit test documentation
- [docs/testing/](../docs/testing/) - Testing strategy and methodology
