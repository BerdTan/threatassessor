# Testing Documentation

**Location:** `docs/testing/`  
**Purpose:** Centralized testing strategy and data documentation

---

## Documentation Index

### Core Strategy Documents

1. **[DATA_STRATEGY.md](DATA_STRATEGY.md)** - **START HERE**
   - How to use existing production data (89MB) for testing
   - Avoid duplicating MITRE data and embeddings
   - Only copy lightweight test queries (~30KB)
   - Production fixtures strategy

2. **[TESTING_STRATEGY.md](TESTING_STRATEGY.md)**
   - Complete testing approach
   - Port tests from threatassessor
   - Create semantic search & LLM validation tests
   - Test runner scripts

3. **[TEST_DATA_ASSESSMENT.md](TEST_DATA_ASSESSMENT.md)**
   - Detailed analysis of 109 test queries
   - Dataset purposes and priorities
   - Expected accuracy baselines
   - Reuse recommendations

4. **[README_TEST_DATA.md](README_TEST_DATA.md)**
   - Quick reference for test data
   - Copy commands
   - Sample query structure
   - Usage examples

---

## Quick Start

### 1. Read Strategy (5 min)
```bash
cat docs/testing/DATA_STRATEGY.md
```

**Key Insight:** Use production data (`chatbot/data/`) instead of copying fixtures!

### 2. Copy Test Infrastructure (2 min)
```bash
cd /mnt/c/BACKUP/DEV-TEST

# Copy test utilities (not data!)
cp _codex/threatassessor-master/tests/eval_utils.py tests/

# Copy test queries only (109 records, ~30KB)
mkdir -p tests/data/generated
cp _codex/threatassessor-master/tests/data/generated/*.jsonl tests/data/generated/

# conftest.py already created (uses production data)
```

### 3. Verify Setup (1 min)
```bash
# Check production data available
ls -lh chatbot/data/  # Should show enterprise-attack.json (44MB), technique_embeddings.json (45MB)

# Check test queries copied
ls tests/data/generated/  # Should show 8 .jsonl files
wc -l tests/data/generated/*.jsonl  # Should show 109 total

# Check fixtures work
pytest tests/ --collect-only  # Should show available tests
```

---

## Test Data Sources

### Production Data (Already Have - Don't Copy!)
```
chatbot/data/
├── enterprise-attack.json (44MB)      ← Full MITRE ATT&CK dataset
└── technique_embeddings.json (45MB)   ← Pre-computed embeddings (2048-dim)
```

**Used by all tests via fixtures in `tests/conftest.py`**

### Test Queries (Copy These - 30KB)
```
tests/data/generated/
├── technique_canonical.jsonl (24 records)   ← Exact names/IDs
├── technique_paraphrase.jsonl (24 records)  ← Real-world phrasings
├── tactic_queries.jsonl (15 records)        ← Tactic-level searches
├── robustness_mutations.jsonl (24)          ← Case variations
├── platform_queries.jsonl (6)               ← Platform-specific
├── benign_admin_queries.jsonl (12)          ← False positive tests
├── hard_negative_queries.jsonl (3)          ← Disambiguation
└── multi_step_chain_queries.jsonl (1)       ← Attack chains
```

**Total:** 109 validated test queries with expected results

---

## Testing Fixtures

### Production Fixtures (Recommended)

```python
# tests/conftest.py - Already created
@pytest.fixture(scope="session")
def production_mitre():
    """Use chatbot/data/enterprise-attack.json"""
    return MitreHelper(use_local=True)

@pytest.fixture(scope="session")
def production_embeddings():
    """Use chatbot/data/technique_embeddings.json"""
    return load_embeddings_json("chatbot/data/technique_embeddings.json")
```

**Benefits:**
- ✅ Test against actual production data
- ✅ No duplication (89MB → 0MB copied)
- ✅ Always in sync with production
- ✅ Fast offline tests with production cache

---

## Test Types

### Offline Tests (No API)
```python
@pytest.mark.offline
@pytest.mark.requires_cache
def test_semantic_search_offline(production_mitre, production_embeddings):
    """Uses production embedding cache - no API calls."""
    results = semantic_search(query, production_embeddings, production_mitre)
    assert len(results) > 0
```

**Run:** `pytest tests/ -m offline -v`

### Online Tests (Requires API)
```python
@pytest.mark.online
def test_semantic_search_online(production_mitre):
    """Makes live API calls to OpenRouter."""
    results = search_techniques(query, production_mitre)
    assert "T1059.001" in results[0]["external_id"]
```

**Run:** `pytest tests/ -m online -v` (needs OPENROUTER_API_KEY)

---

## Expected Baselines

| Test Type | Dataset | Top-1 Target | Top-3 Target |
|-----------|---------|--------------|--------------|
| **Offline** | Canonical | ≥ 70% | ≥ 85% |
| **Offline** | Paraphrase | ≥ 40% | ≥ 60% |
| **Online** | Canonical | ≥ 70% | ≥ 85% |
| **Online** | Paraphrase | ≥ 40% | ≥ 60% |

**Note:** Offline tests use production cache, online tests use live API

---

## Key Files

| File | Purpose | Status |
|------|---------|--------|
| `tests/conftest.py` | Fixtures using production data | ✅ Created |
| `tests/eval_utils.py` | Evaluation metrics | 📋 Copy from threatassessor |
| `tests/data/generated/*.jsonl` | 109 test queries | 📋 Copy from threatassessor |
| `chatbot/data/enterprise-attack.json` | Production MITRE data | ✅ Already exists |
| `chatbot/data/technique_embeddings.json` | Production embeddings | ✅ Already exists |

---

## Common Commands

**Setup tests:**
```bash
cp _codex/threatassessor-master/tests/eval_utils.py tests/
mkdir -p tests/data/generated
cp _codex/threatassessor-master/tests/data/generated/*.jsonl tests/data/generated/
```

**Run tests:**
```bash
pytest tests/ -m offline -v          # Fast offline tests
pytest tests/ -m online -v           # Tests with API calls
pytest tests/ -v                     # All tests
```

**Check coverage:**
```bash
pytest tests/ --collect-only         # List all tests
pytest tests/ -v | grep PASSED       # Count passing tests
```

---

## Documentation Organization

**Root directory:** Clean - Only essential docs  
**Testing docs:** `docs/testing/` - All testing-related documentation

This keeps the root directory uncluttered while maintaining comprehensive testing documentation.

---

*Testing documentation centralized in docs/testing/ - use production data strategy!*
