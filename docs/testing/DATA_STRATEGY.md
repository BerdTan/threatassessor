# Data Strategy: Leveraging Existing Assets

**Last Updated:** 2026-05-01  
**Goal:** Use existing production data for testing instead of duplicating

---

## Existing Production Data (Main Repo)

### `chatbot/data/enterprise-attack.json` (44MB)
**Source:** MITRE ATT&CK official dataset via internal lib  
**Size:** 44MB  
**Content:** Full MITRE ATT&CK dataset with ~823 techniques  
**Status:** ✅ Production-ready, already in use

**Reuse Strategy:**
```python
# tests/test_semantic_search.py
from chatbot.modules.mitre import MitreHelper

@pytest.fixture
def production_mitre():
    """Use production MITRE data for testing."""
    return MitreHelper(use_local=True)  # Uses chatbot/data/enterprise-attack.json

# No need to copy or duplicate!
```

**Benefits:**
- ✅ Test against actual production data
- ✅ No duplication (don't need mini_enterprise_attack.json)
- ✅ Always up-to-date with production
- ✅ Tests validate real system behavior

---

### `chatbot/data/technique_embeddings.json` (45MB)
**Source:** Generated using nvidia/llama-nemotron-embed-vl-1b-v2 (past session)  
**Size:** 45MB  
**Content:** Pre-computed embeddings for all 823 MITRE techniques (2048-dim vectors)  
**Status:** ✅ Production cache, enables offline testing

**Reuse Strategy:**
```python
# tests/test_semantic_search.py
from chatbot.modules.mitre_embeddings import load_embeddings_json

@pytest.fixture
def production_embeddings():
    """Use production embedding cache for testing."""
    return load_embeddings_json("chatbot/data/technique_embeddings.json")

# Test semantic search with actual production cache!
```

**Benefits:**
- ✅ No API calls needed for testing (offline tests)
- ✅ Test actual production embeddings
- ✅ Fast tests (~1s vs 10-15 min cache generation)
- ✅ Validates cache integrity

---

## Test Data (Threatassessor)

### Test Queries (109 records, ~30KB)
**Source:** `_codex/threatassessor-master/tests/data/generated/*.jsonl`  
**Purpose:** Validated test queries with expected results

**Reuse Strategy:**
```bash
# Copy lightweight test queries only (not data files)
cd /mnt/c/BACKUP/DEV-TEST
mkdir -p tests/data/generated
cp _codex/threatassessor-master/tests/data/generated/*.jsonl tests/data/generated/
```

**What to copy:**
- ✅ Test queries (109 records, ~30KB) - Lightweight
- ❌ Mini MITRE fixture - **NOT NEEDED** (use production data instead)
- ✅ Sample architecture input - For architecture tests only

---

## Updated Test Fixtures Strategy

### Production Data Fixtures (Preferred)

```python
# tests/conftest.py
import pytest
from pathlib import Path
from chatbot.modules.mitre import MitreHelper
from chatbot.modules.mitre_embeddings import load_embeddings_json


@pytest.fixture(scope="session")
def production_mitre():
    """
    Use production MITRE data for all tests.
    Scope: session (load once per test session).
    """
    return MitreHelper(use_local=True)  # Uses chatbot/data/enterprise-attack.json


@pytest.fixture(scope="session")
def production_embeddings():
    """
    Use production embedding cache for offline tests.
    Scope: session (load once per test session).
    """
    cache_path = Path("chatbot/data/technique_embeddings.json")
    if cache_path.exists():
        return load_embeddings_json(str(cache_path))
    return None  # Cache not built yet


@pytest.fixture
def has_embedding_cache(production_embeddings):
    """Check if production embedding cache exists."""
    return production_embeddings is not None


# Pytest markers
def pytest_configure(config):
    config.addinivalue_line("markers", "offline: tests without API calls")
    config.addinivalue_line("markers", "online: tests requiring API access")
    config.addinivalue_line("markers", "slow: tests taking >5 seconds")
    config.addinivalue_line("markers", "requires_cache: needs embedding cache")
```

---

## Testing Strategy with Production Data

### Offline Tests (Fast, No API)

**Use production embeddings + test queries:**
```python
@pytest.mark.offline
@pytest.mark.requires_cache
def test_semantic_search_offline(production_mitre, production_embeddings):
    """Test semantic search using production embedding cache."""
    if production_embeddings is None:
        pytest.skip("Embedding cache not built yet")
    
    from chatbot.modules.mitre_embeddings import semantic_search
    
    # Test with production cache
    results = semantic_search(
        "PowerShell script execution",
        production_embeddings,
        production_mitre,
        top_k=5
    )
    
    assert len(results) > 0
    assert results[0][3] > 0.3  # similarity_score
    
    # Check T1059.001 found
    external_ids = [r[1] for r in results]
    assert "T1059.001" in external_ids or "T1059" in external_ids
```

### Online Tests (Requires API)

**Test actual API calls:**
```python
@pytest.mark.online
def test_semantic_search_online(production_mitre):
    """Test semantic search with live API calls."""
    from chatbot.modules.mitre_embeddings import search_techniques
    
    # Uses production MITRE data, makes API calls
    results = search_techniques(
        "attacker used Remote Desktop Protocol",
        production_mitre,
        top_k=5
    )
    
    assert len(results) > 0
    assert "T1021" in results[0]["external_id"]
```

---

## Data Dependencies Matrix

| Test Type | MITRE Data | Embeddings | API Key | Test Queries |
|-----------|------------|------------|---------|--------------|
| **Offline Unit** | ✅ Production | ✅ Production | ❌ No | ❌ No |
| **Offline Accuracy** | ✅ Production | ✅ Production | ❌ No | ✅ 109 queries |
| **Online Integration** | ✅ Production | 🔶 Optional | ✅ Yes | 🔶 Optional |
| **Online Accuracy** | ✅ Production | 🔶 Optional | ✅ Yes | ✅ 109 queries |

**Key Insight:** Production data is sufficient for most tests!

---

## File Organization

### Keep in Production (Don't Duplicate)
```
chatbot/data/
├── enterprise-attack.json (44MB)     ✅ Use for all tests
└── technique_embeddings.json (45MB)  ✅ Use for offline tests
```

### Test-Specific Data (Copy These)
```
tests/data/
└── generated/
    ├── technique_canonical.jsonl (24 records)
    ├── technique_paraphrase.jsonl (24 records)
    ├── tactic_queries.jsonl (15 records)
    └── ... (5 more datasets, 109 total)
```

### Don't Copy These (Use Production Instead)
```
❌ tests/data/fixtures/mini_enterprise_attack.json  # Use chatbot/data/enterprise-attack.json
❌ tests/data/fixtures/sample_architecture_input.txt  # Only if testing architecture analysis
```

---

## Updated Copy Commands

### Minimal Copy (Recommended)

```bash
cd /mnt/c/BACKUP/DEV-TEST

# Create structure
mkdir -p tests/data/generated

# Copy ONLY test queries (109 records, ~30KB)
cp _codex/threatassessor-master/tests/data/generated/*.jsonl tests/data/generated/

# Copy utilities
cp _codex/threatassessor-master/tests/conftest.py tests/
cp _codex/threatassessor-master/tests/eval_utils.py tests/

# DON'T copy mini_enterprise_attack.json - use production data instead!
```

**Total copied:** ~35KB (queries + utils)  
**Production data reused:** 89MB (MITRE + embeddings)

---

## Verification Tests

### Test 1: Production Data Available
```bash
# Check production data exists
ls -lh chatbot/data/enterprise-attack.json  # Should show 44MB
ls -lh chatbot/data/technique_embeddings.json  # Should show 45MB

# Verify loadable
python3 -c "
from chatbot.modules.mitre import MitreHelper
mitre = MitreHelper(use_local=True)
techniques = mitre.get_techniques()
print(f'✓ Loaded {len(techniques)} techniques from production data')
"
```

### Test 2: Embedding Cache Valid
```bash
# Verify cache structure
python3 -c "
from chatbot.modules.mitre_embeddings import load_embeddings_json
cache = load_embeddings_json('chatbot/data/technique_embeddings.json')
print(f'✓ Loaded {len(cache)} technique embeddings')
first_key = next(iter(cache))
print(f'✓ Embedding dimension: {cache[first_key][\"dimension\"]}')
"
```

### Test 3: Test Queries Available
```bash
# Check test queries copied
ls tests/data/generated/*.jsonl
wc -l tests/data/generated/*.jsonl  # Should show 109 total
```

---

## Benefits of This Strategy

### 1. No Duplication ✅
- Don't copy 44MB MITRE data (use production)
- Don't copy 45MB embeddings (use production cache)
- Only copy 30KB test queries

### 2. Tests Validate Production ✅
- Tests run against actual production data
- Validates real system behavior
- Catches production data issues

### 3. Fast Offline Tests ✅
- Production embedding cache enables offline testing
- No API calls = fast tests (~1s)
- CI/CD friendly

### 4. Easy Updates ✅
- Update MITRE data: Just regenerate production cache
- Tests automatically use new data
- No test data sync needed

---

## Migration Path

### From Mini Fixtures → Production Data

**Old approach (threatassessor):**
```python
@pytest.fixture
def mini_mitre(mini_mitre_path: str):
    return MitreHelper(use_local=True, local_path=mini_mitre_path)
```

**New approach (main repo):**
```python
@pytest.fixture(scope="session")
def production_mitre():
    return MitreHelper(use_local=True)  # Uses chatbot/data/enterprise-attack.json
```

**Benefits:**
- ✅ Test full 823 techniques, not just 5-10
- ✅ More realistic test coverage
- ✅ No fixture maintenance

---

## Quick Reference

**Production data locations:**
- MITRE: `chatbot/data/enterprise-attack.json` (44MB)
- Embeddings: `chatbot/data/technique_embeddings.json` (45MB)

**Copy command (minimal):**
```bash
mkdir -p tests/data/generated
cp _codex/threatassessor-master/tests/data/generated/*.jsonl tests/data/generated/
cp _codex/threatassessor-master/tests/{conftest.py,eval_utils.py} tests/
```

**Total size copied:** ~35KB  
**Production data reused:** 89MB

---

*Leverage existing production data - don't duplicate what you already have!*
