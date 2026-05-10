# Scripts Directory

Integration tests, validation utilities, and data generation scripts organized by purpose.

---

## Directory Structure

```
scripts/
├── integration/          # Integration tests (cross-module validation)
│   ├── test_llm_providers.py
│   ├── test_openrouter.py
│   ├── backtest_all_architectures.py
│   ├── validate_engine_accuracy.py
│   └── validate_parser_harness.py
├── validation/           # Quick validation utilities
│   ├── check_orphans.py
│   └── validate_llm_config.py
├── generation/           # Data generation & demo utilities
│   ├── generate_ground_truth.py
│   ├── batch_generate_ground_truth.sh
│   └── demo_mitre_advice.py
└── personal/             # Personal workflow utilities (gitignored)
    └── sync_repos.sh
```

---

## Integration Tests

### LLM Provider Testing (`integration/`)

**`test_llm_providers.py`** - Multi-provider LLM integration tests
```bash
python3 scripts/integration/test_llm_providers.py                    # All providers
python3 scripts/integration/test_llm_providers.py --provider bedrock # Specific provider
python3 scripts/integration/test_llm_providers.py --test-verify      # LLM as Judge
```
Results: `tests/results/test_results_llm_providers.json`

**`test_openrouter.py`** - OpenRouter API integration validation
```bash
python3 scripts/integration/test_openrouter.py
```

### Architecture Validation (`integration/`)

**`backtest_all_architectures.py`** - Validate all test architectures
```bash
python3 scripts/integration/backtest_all_architectures.py                          # All
python3 scripts/integration/backtest_all_architectures.py --architectures 10_* 03_* # Specific
```

**`validate_engine_accuracy.py`** - Engine accuracy against ground truth
```bash
python3 scripts/integration/validate_engine_accuracy.py
```

**`validate_parser_harness.py`** - Parser correctness validation
```bash
python3 scripts/integration/validate_parser_harness.py
```

---

## Validation Utilities (`validation/`)

**`check_orphans.py`** - Check for orphan nodes in architectures
```bash
python3 scripts/validation/check_orphans.py                     # All architectures
python3 scripts/validation/check_orphans.py 10_complex 03_aws  # Specific ones
```

**`validate_llm_config.py`** - Validate LLM provider configuration
```bash
python3 scripts/validation/validate_llm_config.py
```

---

## Data Generation (`generation/`)

**`generate_ground_truth.py`** - Semi-automated ground truth generation
```bash
python3 scripts/generation/generate_ground_truth.py tests/data/architectures/06_azure_3tier.mmd
```

**`batch_generate_ground_truth.sh`** - Batch ground truth generation
```bash
./scripts/generation/batch_generate_ground_truth.sh
```

**`demo_mitre_advice.py`** - Demo MITRE helper functionality
```bash
python3 scripts/generation/demo_mitre_advice.py
```

---

## Personal Utilities (`personal/`)

**`sync_repos.sh`** - Repository synchronization (personal workflow)
```bash
./scripts/personal/sync_repos.sh
```

*Note: This directory is gitignored for personal workflow scripts.*

---

## Organization Principles

### Directory Purpose

| Directory | Purpose | Examples |
|-----------|---------|----------|
| **integration/** | Cross-module integration tests | LLM providers, architecture backtesting |
| **validation/** | Quick validation checks | Orphan detection, config validation |
| **generation/** | Data generation & demos | Ground truth generation, MITRE demos |
| **personal/** | Personal workflow utilities (gitignored) | Repository sync |

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
python3 scripts/integration/backtest_all_architectures.py

# 3. LLM provider validation
python3 scripts/validation/validate_llm_config.py

# 4. Orphan detection
python3 scripts/validation/check_orphans.py

# 5. Engine accuracy
python3 scripts/integration/validate_engine_accuracy.py
```

---

## Quick Reference

**Integration Testing:**
```bash
cd scripts/integration/
python3 test_llm_providers.py
python3 backtest_all_architectures.py
```

**Validation:**
```bash
cd scripts/validation/
python3 check_orphans.py
python3 validate_llm_config.py
```

**Data Generation:**
```bash
cd scripts/generation/
python3 generate_ground_truth.py ../tests/data/architectures/your_arch.mmd
```

---

**See Also:**
- [tests/README.md](../tests/README.md) - Unit test documentation
- [docs/testing/](../docs/testing/) - Testing strategy and methodology
