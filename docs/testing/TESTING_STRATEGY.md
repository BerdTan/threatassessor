# Testing Strategy: Unified Test Suite

**Created:** 2026-05-01  
**Goal:** Port valuable tests from threatassessor, validate semantic search & LLM, maintain test coverage for both repos

---

## Current Testing Gap Analysis

### Main Repo (`/mnt/c/BACKUP/DEV-TEST/tests/`)
**Status:** ⚠️ Minimal coverage - Only documentation files, no automated tests

**Existing Files:**
- `TESTING.md` - Test strategy documentation
- `TESTING_GUIDE.md` - Manual testing guide
- `TEST_INTEGRATION.md` - Integration test docs
- `test_mitre.py` - Basic MITRE data loading (8 tests)
- `test_openrouter.py` - API validation (8 tests)
- `test_phase2_semantic_search.py` - End-to-end pipeline

**Missing:**
- ❌ Semantic search accuracy tests
- ❌ LLM output validation tests
- ❌ Agent routing tests
- ❌ Rate limiting tests
- ❌ Embedding cache tests

### Threatassessor Repo (`_codex/threatassessor-master/tests/`)
**Status:** ✅ Comprehensive - 13 test files with offline/online markers

**Valuable Tests:**
- ✅ `conftest.py` - Pytest fixtures (mini MITRE, markers)
- ✅ `eval_utils.py` - Evaluation metrics (top-k, recall, tactic matching)
- ✅ `test_semantic_eval.py` - Semantic search accuracy metrics
- ✅ `test_llm_contracts.py` - LLM output structure validation
- ✅ `test_agent_eval.py` - Agent routing and fallback
- ✅ `test_architecture_analysis.py` - Architecture threat modeling
- ✅ `test_mermaid_parser.py` - Diagram parsing
- ✅ `generate_test_datasets.py` - Synthetic test data generation

---

## Test Porting Strategy

### Phase 1: Port Shared Testing Infrastructure (30 min)

**Goal:** Establish common test fixtures and utilities in main repo

#### 1.1: Port Core Fixtures (15 min)
**Source:** `_codex/threatassessor-master/tests/conftest.py`  
**Target:** `/mnt/c/BACKUP/DEV-TEST/tests/conftest.py`

**What to port:**
```python
import pytest
from pathlib import Path
from chatbot.modules.mitre import MitreHelper

@pytest.fixture
def mini_mitre_path() -> str:
    """Path to lightweight MITRE dataset for testing."""
    return "tests/data/fixtures/mini_enterprise_attack.json"

@pytest.fixture
def mini_mitre(mini_mitre_path: str) -> MitreHelper:
    """Lightweight MITRE helper for offline tests."""
    return MitreHelper(use_local=True, local_path=mini_mitre_path)

def pytest_configure(config):
    """Register custom pytest markers."""
    config.addinivalue_line("markers", "offline: tests without API calls")
    config.addinivalue_line("markers", "online: tests requiring API access")
    config.addinivalue_line("markers", "slow: tests taking >5 seconds")

def has_api_key() -> bool:
    """Check if OpenRouter API key is configured."""
    import os
    return bool(os.getenv("OPENROUTER_API_KEY"))
```

**Action:**
```bash
cd /mnt/c/BACKUP/DEV-TEST
mkdir -p tests/data/fixtures
cp _codex/threatassessor-master/tests/conftest.py tests/
cp _codex/threatassessor-master/tests/data/fixtures/mini_enterprise_attack.json tests/data/fixtures/
```

#### 1.2: Port Evaluation Utilities (15 min)
**Source:** `_codex/threatassessor-master/tests/eval_utils.py`  
**Target:** `/mnt/c/BACKUP/DEV-TEST/tests/eval_utils.py`

**What to port:** All functions (critical for metrics)
- `load_jsonl()` - Load test datasets
- `tokenize()` - Simple tokenization
- `build_fake_cache()` - Offline testing without embeddings
- `fake_semantic_search()` - Token overlap fallback
- `top_k_hit()`, `recall_at_k()`, `tactic_match()` - Accuracy metrics
- `evaluate_records()` - Batch evaluation

**Action:**
```bash
cp _codex/threatassessor-master/tests/eval_utils.py tests/
```

---

### Phase 2: Test Semantic Search & LLM (1 hour)

**Priority: CRITICAL** - You haven't validated these yet!

#### 2.1: Test Semantic Search Accuracy (30 min)
**Source:** `_codex/threatassessor-master/tests/test_semantic_eval.py`  
**Target:** `/mnt/c/BACKUP/DEV-TEST/tests/test_semantic_search.py` (new)

**Create:** `/mnt/c/BACKUP/DEV-TEST/tests/test_semantic_search.py`

```python
"""Test semantic search accuracy against known queries."""
import pytest
from chatbot.modules.mitre import MitreHelper
from chatbot.modules.mitre_embeddings import search_techniques
from tests.eval_utils import evaluate_records, load_jsonl_dir
from pathlib import Path


@pytest.mark.online
def test_semantic_search_basic():
    """Test basic semantic search functionality."""
    mitre = MitreHelper(use_local=True)
    
    # Test query: PowerShell execution
    results = search_techniques("PowerShell script execution", mitre, top_k=5)
    
    assert len(results) > 0, "Should return results"
    assert results[0]["similarity_score"] > 0.3, "Top result should have decent score"
    
    # Check T1059.001 is in top 5
    external_ids = [r["external_id"] for r in results]
    assert "T1059.001" in external_ids or "T1059" in external_ids, "Should find PowerShell technique"


@pytest.mark.online
@pytest.mark.slow
def test_semantic_search_accuracy_metrics():
    """Test semantic search accuracy on test dataset."""
    # Load test data (if exists)
    test_data_dir = Path("tests/data/generated")
    if not test_data_dir.exists():
        pytest.skip("No generated test datasets found")
    
    records = load_jsonl_dir(test_data_dir)
    if not records:
        pytest.skip("No test records to evaluate")
    
    mitre = MitreHelper(use_local=True)
    
    def search_fn(query: str):
        return search_techniques(query, mitre, top_k=5)
    
    metrics = evaluate_records(records, search_fn)
    
    # Assertions based on AI analysis report requirements
    assert metrics["top1_accuracy"] >= 0.30, f"Top-1 accuracy {metrics['top1_accuracy']} too low"
    assert metrics["top3_accuracy"] >= 0.50, f"Top-3 accuracy {metrics['top3_accuracy']} too low"
    assert metrics["tactic_match_rate"] >= 0.60, f"Tactic match rate {metrics['tactic_match_rate']} too low"
    
    print("\n=== Semantic Search Metrics ===")
    print(f"Top-1 Accuracy: {metrics['top1_accuracy']:.2%}")
    print(f"Top-3 Accuracy: {metrics['top3_accuracy']:.2%}")
    print(f"Tactic Match:   {metrics['tactic_match_rate']:.2%}")


@pytest.mark.offline
def test_semantic_search_offline():
    """Test semantic search with fake embeddings (offline)."""
    from tests.eval_utils import build_fake_cache, fake_semantic_search
    
    mitre = MitreHelper(use_local=True)
    cache = build_fake_cache(mitre)
    
    # Test with token overlap
    results = fake_semantic_search("PowerShell execution", cache, top_k=5)
    
    assert len(results) > 0, "Should return results with token overlap"
    assert results[0][3] > 0.0, "Should have positive score"
```

**Run test:**
```bash
# Offline test (fast)
pytest tests/test_semantic_search.py::test_semantic_search_offline -v

# Online test (requires API + cache)
pytest tests/test_semantic_search.py::test_semantic_search_basic -v

# Accuracy test (slow, comprehensive)
pytest tests/test_semantic_search.py::test_semantic_search_accuracy_metrics -v
```

#### 2.2: Test LLM Output Validation (30 min)
**Source:** `_codex/threatassessor-master/tests/test_llm_contracts.py`  
**Target:** `/mnt/c/BACKUP/DEV-TEST/tests/test_llm_analysis.py` (new)

**Create:** `/mnt/c/BACKUP/DEV-TEST/tests/test_llm_analysis.py`

```python
"""Test LLM analysis output structure and quality."""
import pytest
from chatbot.modules.llm_mitre_analyzer import (
    refine_technique_matches,
    generate_attack_path,
    generate_mitigation_advice,
    analyze_scenario
)
from chatbot.modules.mitre import MitreHelper
from chatbot.modules.mitre_embeddings import search_techniques


@pytest.mark.online
def test_refine_technique_matches():
    """Test LLM-based technique refinement."""
    query = "Attacker used PowerShell to download malware"
    mitre = MitreHelper(use_local=True)
    
    # Get initial matches
    initial = search_techniques(query, mitre, top_k=5)
    
    # Refine with LLM
    refined = refine_technique_matches(query, initial)
    
    # Validate structure
    assert isinstance(refined, list), "Should return list"
    assert len(refined) > 0, "Should return refined techniques"
    
    for technique in refined:
        assert "external_id" in technique, "Should have external_id"
        assert "name" in technique, "Should have name"
        assert "relevance_score" in technique or "similarity_score" in technique, "Should have score"
        assert "reasoning" in technique or "explanation" in technique, "Should have reasoning"


@pytest.mark.online
def test_generate_attack_path():
    """Test LLM-based attack path generation."""
    query = "Phishing email leads to ransomware deployment"
    mitre = MitreHelper(use_local=True)
    
    techniques = search_techniques(query, mitre, top_k=5)
    attack_path = generate_attack_path(query, techniques)
    
    # Validate structure
    assert isinstance(attack_path, dict), "Should return dict"
    assert "attack_path" in attack_path or "stages" in attack_path, "Should have path/stages"
    assert "attack_narrative" in attack_path or "description" in attack_path, "Should have narrative"
    
    # Check stages
    stages = attack_path.get("attack_path") or attack_path.get("stages", [])
    assert len(stages) > 0, "Should have at least one stage"
    
    for stage in stages[:3]:  # Check first 3
        assert "stage_name" in stage or "name" in stage, "Stage should have name"
        assert "techniques" in stage or "technique_ids" in stage, "Stage should have techniques"


@pytest.mark.online
def test_generate_mitigation_advice():
    """Test LLM-based mitigation generation."""
    query = "Credential theft via keylogging"
    mitre = MitreHelper(use_local=True)
    
    techniques = search_techniques(query, mitre, top_k=3)
    mitigations = generate_mitigation_advice(query, techniques)
    
    # Validate structure
    assert isinstance(mitigations, list) or isinstance(mitigations, dict), "Should return list or dict"
    
    if isinstance(mitigations, list):
        assert len(mitigations) > 0, "Should have mitigations"
        for mitigation in mitigations[:2]:
            assert "title" in mitigation or "name" in mitigation, "Should have title"
            assert "description" in mitigation, "Should have description"
    else:
        assert "mitigations" in mitigations, "Should have mitigations key"


@pytest.mark.online
@pytest.mark.slow
def test_analyze_scenario_end_to_end():
    """Test complete scenario analysis pipeline."""
    scenario = """
    An attacker sends a phishing email with a malicious attachment.
    When opened, it runs PowerShell to download and execute ransomware.
    """
    
    result = analyze_scenario(scenario)
    
    # Validate complete analysis
    assert isinstance(result, dict), "Should return dict"
    assert "techniques" in result or "matched_techniques" in result, "Should identify techniques"
    assert "attack_path" in result or "attack_chain" in result, "Should generate attack path"
    assert "mitigations" in result, "Should provide mitigations"
    
    print("\n=== LLM Analysis Result ===")
    print(f"Techniques found: {len(result.get('techniques', result.get('matched_techniques', [])))}")
    print(f"Attack stages: {len(result.get('attack_path', {}).get('stages', []))}")
    print(f"Mitigations: {len(result.get('mitigations', []))}")


@pytest.mark.offline
def test_llm_fallback_graceful():
    """Test that LLM functions fail gracefully without API."""
    import os
    
    # Temporarily remove API key
    original_key = os.environ.get("OPENROUTER_API_KEY")
    if original_key:
        del os.environ["OPENROUTER_API_KEY"]
    
    try:
        query = "test query"
        techniques = [{"external_id": "T1059", "name": "Command Execution", "similarity_score": 0.8}]
        
        # Should not crash, should return fallback or empty
        result = refine_technique_matches(query, techniques)
        assert isinstance(result, list), "Should return list even on failure"
        
    finally:
        # Restore API key
        if original_key:
            os.environ["OPENROUTER_API_KEY"] = original_key
```

**Run test:**
```bash
# Individual tests
pytest tests/test_llm_analysis.py::test_refine_technique_matches -v
pytest tests/test_llm_analysis.py::test_generate_attack_path -v

# Full suite (slow)
pytest tests/test_llm_analysis.py -v
```

---

### Phase 3: Test Agent & Integration (30 min)

#### 3.1: Test Agent Routing (15 min)
**Source:** `_codex/threatassessor-master/tests/test_agent_eval.py`  
**Target:** `/mnt/c/BACKUP/DEV-TEST/tests/test_agent.py` (new)

```python
"""Test AgentManager routing and mode selection."""
import pytest
from chatbot.modules.agent import AgentManager


@pytest.mark.online
def test_agent_semantic_mode():
    """Test agent in semantic search mode."""
    agent = AgentManager(use_semantic_search=True)
    
    result = agent.handle_input("PowerShell script execution", top_k=3)
    
    assert "mode" in result, "Should indicate mode"
    assert result["mode"] == "semantic", "Should use semantic mode"
    assert "techniques" in result or "matched_techniques" in result, "Should return techniques"
    assert len(result.get("techniques", result.get("matched_techniques", []))) > 0, "Should find techniques"


@pytest.mark.offline
def test_agent_keyword_fallback():
    """Test agent falls back to keyword search."""
    agent = AgentManager(use_semantic_search=False)
    
    result = agent.handle_input("T1059 PowerShell", top_k=3)
    
    assert "mode" in result, "Should indicate mode"
    assert result["mode"] == "keyword", "Should use keyword mode"
    assert "techniques" in result or "matched_techniques" in result, "Should return techniques"


@pytest.mark.online
def test_agent_handles_invalid_query():
    """Test agent handles nonsense query gracefully."""
    agent = AgentManager(use_semantic_search=True)
    
    result = agent.handle_input("asdfghjkl zxcvbnm qwerty", top_k=3)
    
    # Should not crash
    assert isinstance(result, dict), "Should return dict"
    # May return empty results or low-confidence matches
    techniques = result.get("techniques", result.get("matched_techniques", []))
    assert isinstance(techniques, list), "Techniques should be list"
```

**Run test:**
```bash
pytest tests/test_agent.py -v
```

---

### Phase 4: Create Test Runner Scripts (15 min)

#### 4.1: Quick Test Script
**Create:** `/mnt/c/BACKUP/DEV-TEST/tests/quick_test.sh`

```bash
#!/bin/bash
# Quick test: Offline tests only (~30 seconds)

set -e

echo "=========================================="
echo "Quick Test Suite (Offline)"
echo "=========================================="
echo ""

cd "$(dirname "$0")/.."

echo "Running offline tests..."
pytest tests/ -m offline -v --tb=short

echo ""
echo "=========================================="
echo "✓ Quick tests passed!"
echo "Run 'bash tests/full_test.sh' for comprehensive validation"
echo "=========================================="
```

#### 4.2: Full Test Script
**Create:** `/mnt/c/BACKUP/DEV-TEST/tests/full_test.sh`

```bash
#!/bin/bash
# Full test: Offline + Online tests (~5 minutes)

set -e

echo "=========================================="
echo "Full Test Suite (Offline + Online)"
echo "=========================================="
echo ""

cd "$(dirname "$0")/.."

# Check API key
if [ -z "$OPENROUTER_API_KEY" ]; then
    echo "⚠️  OPENROUTER_API_KEY not set"
    echo "Loading from .env..."
    export $(cat .env | grep OPENROUTER_API_KEY)
fi

if [ -z "$OPENROUTER_API_KEY" ]; then
    echo "❌ Error: OPENROUTER_API_KEY required for online tests"
    exit 1
fi

echo "Step 1: Offline tests (fast)..."
pytest tests/ -m offline -v --tb=short

echo ""
echo "Step 2: Online tests (slower, requires API)..."
pytest tests/ -m online -v --tb=short

echo ""
echo "Step 3: Integration tests..."
pytest tests/ -m "not slow" -v --tb=short

echo ""
echo "=========================================="
echo "✓ All tests passed!"
echo "=========================================="
```

**Make executable:**
```bash
chmod +x tests/quick_test.sh tests/full_test.sh
```

---

## Test Execution Plan

### Immediate (Next Session - 1 hour)

**Step 1: Port infrastructure (30 min)**
```bash
cd /mnt/c/BACKUP/DEV-TEST

# Create test structure
mkdir -p tests/data/fixtures

# Port fixtures
cp _codex/threatassessor-master/tests/conftest.py tests/
cp _codex/threatassessor-master/tests/eval_utils.py tests/
cp -r _codex/threatassessor-master/tests/data/fixtures/ tests/data/

# Verify
ls tests/
```

**Step 2: Create semantic search tests (30 min)**
```bash
# Copy template from this doc
cat > tests/test_semantic_search.py << 'EOF'
[Copy code from Section 2.1]
EOF

# Run offline test first
pytest tests/test_semantic_search.py::test_semantic_search_offline -v

# Then online test
pytest tests/test_semantic_search.py::test_semantic_search_basic -v
```

### Short-term (This Week - 2 hours)

**Step 3: Create LLM validation tests (1 hour)**
```bash
# Create test file
cat > tests/test_llm_analysis.py << 'EOF'
[Copy code from Section 2.2]
EOF

# Run tests
pytest tests/test_llm_analysis.py -v
```

**Step 4: Create agent tests (30 min)**
```bash
# Create test file
cat > tests/test_agent.py << 'EOF'
[Copy code from Section 3.1]
EOF

# Run tests
pytest tests/test_agent.py -v
```

**Step 5: Create test runners (30 min)**
```bash
# Create scripts
cat > tests/quick_test.sh << 'EOF'
[Copy code from Section 4.1]
EOF

cat > tests/full_test.sh << 'EOF'
[Copy code from Section 4.2]
EOF

chmod +x tests/*.sh

# Run quick test
bash tests/quick_test.sh
```

---

## Test Coverage Goals

| Component | Current | Target | Test File |
|-----------|---------|--------|-----------|
| **Main Repo** | | | |
| MITRE data loading | ✅ 100% | 100% | `test_mitre.py` (exists) |
| OpenRouter API | ✅ 100% | 100% | `test_openrouter.py` (exists) |
| Semantic search accuracy | ❌ 0% | 90% | `test_semantic_search.py` (NEW) |
| LLM output validation | ❌ 0% | 80% | `test_llm_analysis.py` (NEW) |
| Agent routing | ❌ 0% | 90% | `test_agent.py` (NEW) |
| Rate limiting | ❌ 0% | 70% | `test_rate_limiter.py` (future) |
| **Threatassessor** | | | |
| Architecture analysis | ✅ 90% | 95% | `test_architecture_analysis.py` |
| Mermaid parsing | ✅ 85% | 95% | `test_mermaid_parser.py` |
| Confidence scoring | ❌ 0% | 100% | Add to `test_architecture_analysis.py` |
| Mermaid generation | ❌ 0% | 100% | Add to `test_mermaid_parser.py` |

---

## Success Criteria

### Phase 1: Infrastructure (DONE when)
- [ ] `conftest.py` ported with fixtures and markers
- [ ] `eval_utils.py` ported with metric functions
- [ ] Mini MITRE fixture available
- [ ] Can run: `pytest tests/ --collect-only` (shows available tests)

### Phase 2: Semantic Search Validation (DONE when)
- [ ] Basic semantic search test passes
- [ ] Offline token-overlap test passes
- [ ] Accuracy metrics test passes (if test data available)
- [ ] Top-3 accuracy ≥ 50%
- [ ] Can confirm semantic search is working correctly

### Phase 3: LLM Validation (DONE when)
- [ ] LLM refinement test passes
- [ ] Attack path generation test passes
- [ ] Mitigation generation test passes
- [ ] End-to-end scenario analysis passes
- [ ] Can confirm LLM integration is working correctly

### Phase 4: Integration (DONE when)
- [ ] Agent routing tests pass
- [ ] Quick test script runs in <1 min
- [ ] Full test script runs in <5 min
- [ ] All offline tests pass
- [ ] All online tests pass (with API key)

---

## Integration with STATUS_AND_PLAN.md

**Add to Phase 2 (before implementing gaps):**

```markdown
### Phase 2: Port Tests & Validate (1 hour) - NEW PRIORITY

**Goal:** Validate semantic search and LLM are working before implementing gaps

**Why first:** We haven't tested semantic search or LLM yet! Need baseline.

#### Step 2.1: Port Test Infrastructure (30 min)
[Follow TESTING_STRATEGY.md Section "Immediate"]

#### Step 2.2: Run Semantic Search Tests (15 min)
```bash
pytest tests/test_semantic_search.py -v
```

#### Step 2.3: Run LLM Tests (15 min)
```bash
pytest tests/test_llm_analysis.py::test_refine_technique_matches -v
pytest tests/test_llm_analysis.py::test_generate_attack_path -v
```

**Success Criteria:**
- [ ] Semantic search finds T1059.001 for "PowerShell"
- [ ] LLM returns structured refinements
- [ ] LLM generates attack path with stages
- [ ] Top-3 accuracy measured (document result)
```

---

## Quick Commands Reference

**Port tests:**
```bash
cd /mnt/c/BACKUP/DEV-TEST
mkdir -p tests/data/fixtures
cp _codex/threatassessor-master/tests/{conftest.py,eval_utils.py} tests/
cp -r _codex/threatassessor-master/tests/data/fixtures/ tests/data/
```

**Run tests:**
```bash
# Offline (fast, no API)
pytest tests/ -m offline -v

# Online (requires API)
pytest tests/ -m online -v

# Specific test
pytest tests/test_semantic_search.py::test_semantic_search_basic -v

# All tests
pytest tests/ -v --tb=short
```

**Check coverage:**
```bash
pytest tests/ --collect-only  # List all tests
pytest tests/ -v | grep -E "(PASSED|FAILED)"  # Summary
```

---

*Testing strategy integrated with STATUS_AND_PLAN.md action plan*  
*Priority: Validate semantic search & LLM before implementing gaps*
