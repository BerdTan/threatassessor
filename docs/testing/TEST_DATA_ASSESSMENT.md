# Test Data Assessment & Reuse Strategy

**Date:** 2026-05-01  
**Source:** `_codex/threatassessor-master/tests/data/`  
**Total Test Records:** 109 queries across 8 datasets

---

## Test Data Inventory

### Fixtures Directory (`tests/data/fixtures/`)

| File | Size | Purpose | Reuse Priority |
|------|------|---------|----------------|
| `mini_enterprise_attack.json` | 5.9KB | Lightweight MITRE dataset (~5-10 techniques) for offline tests | ✅ **CRITICAL** |
| `sample_architecture_input.txt` | 446B | Example Mermaid diagram + risk notes for architecture tests | ✅ **HIGH** |

**Assessment:**
- ✅ **`mini_enterprise_attack.json`** - Essential for offline testing without full MITRE dataset
- ✅ **`sample_architecture_input.txt`** - Perfect example for testing architecture analysis

---

### Generated Directory (`tests/data/generated/`)

**Total:** 109 test queries in JSONL format (JSON Lines)

| Dataset | Records | Purpose | Example Query | Reuse Priority |
|---------|---------|---------|---------------|----------------|
| `technique_canonical.jsonl` | 24 | Exact technique names, IDs, descriptions | "Remote Desktop Protocol" | ✅ **CRITICAL** |
| `technique_paraphrase.jsonl` | 24 | Real-world phrasings | "attacker used RDP" | ✅ **CRITICAL** |
| `tactic_queries.jsonl` | 15 | Tactic-level searches | "execution techniques" | ✅ **HIGH** |
| `robustness_mutations.jsonl` | 24 | Case/whitespace variations | "pOwErShElL" | ✅ **MEDIUM** |
| `platform_queries.jsonl` | 6 | Platform-specific queries | "Windows T1059.001" | ✅ **MEDIUM** |
| `benign_admin_queries.jsonl` | 12 | Legitimate admin activities | "scheduled backup" | ✅ **MEDIUM** |
| `hard_negative_queries.jsonl` | 3 | Disambiguation tests | "T1059 not T1053" | 🔶 **LOW** |
| `multi_step_chain_queries.jsonl` | 1 | Attack chain scenarios | "phishing → PowerShell → persist" | 🔶 **LOW** |

---

## Test Data Quality Analysis

### Sample Record Structure
```json
{
  "query": "attacker used Remote Desktop Protocol",
  "expected_ids": ["T1021.001"],
  "allowed_ids": ["T1021"],
  "expected_tactics": ["lateral-movement"],
  "platforms": ["Windows"],
  "test_type": "paraphrase",
  "difficulty": "medium",
  "source": "generated_from_mitre"
}
```

**Fields:**
- `query` - Input text to search
- `expected_ids` - Techniques that MUST be found (exact match)
- `allowed_ids` - Parent techniques that are acceptable (e.g., T1021 for T1021.001)
- `expected_tactics` - Expected MITRE tactics
- `platforms` - Expected platforms (Windows, Linux, macOS)
- `difficulty` - easy/medium/hard
- `test_type` - canonical/paraphrase/tactic/mutation/etc.

---

## Reuse Strategy by Dataset

### 1. **technique_canonical.jsonl** (24 records) - ✅ CRITICAL

**Purpose:** Validate semantic search finds techniques by exact names/IDs/descriptions

**Coverage:**
- Technique names: "Remote Desktop Protocol"
- Technique IDs: "T1021.001"
- Descriptions: "Adversaries may use RDP to log into remote systems..."
- Keywords: "adversaries remote desktop protocol"

**Why Critical:** These are the **easiest queries** - if semantic search can't find these, it's broken.

**Reuse:**
```bash
# Copy to main repo
cp _codex/threatassessor-master/tests/data/generated/technique_canonical.jsonl \
   tests/data/generated/
```

**Test Usage:**
```python
# tests/test_semantic_search.py
def test_semantic_search_canonical_queries():
    """Test semantic search with exact technique names/IDs."""
    records = load_jsonl(Path("tests/data/generated/technique_canonical.jsonl"))
    metrics = evaluate_records(records, search_fn)
    
    # Canonical queries should have very high accuracy
    assert metrics["top1_accuracy"] >= 0.70, "Canonical queries should be easy"
    assert metrics["top3_accuracy"] >= 0.85, "Should almost always be in top-3"
```

---

### 2. **technique_paraphrase.jsonl** (24 records) - ✅ CRITICAL

**Purpose:** Validate real-world query patterns (how users actually describe threats)

**Examples:**
- "attacker used Remote Desktop Protocol"
- "malicious use of RDP"
- "abuse of PowerShell for execution"

**Why Critical:** This tests **real usage** - users won't say "T1021.001", they'll say "attacker used RDP"

**Reuse:**
```bash
cp _codex/threatassessor-master/tests/data/generated/technique_paraphrase.jsonl \
   tests/data/generated/
```

**Test Usage:**
```python
def test_semantic_search_paraphrase_queries():
    """Test semantic search with real-world phrasings."""
    records = load_jsonl(Path("tests/data/generated/technique_paraphrase.jsonl"))
    metrics = evaluate_records(records, search_fn)
    
    # Paraphrases are harder but should still work
    assert metrics["top1_accuracy"] >= 0.40, "Should handle paraphrases"
    assert metrics["top3_accuracy"] >= 0.60, "Should be in top-3 most of the time"
```

---

### 3. **tactic_queries.jsonl** (15 records) - ✅ HIGH

**Purpose:** Validate tactic-level searches (broader than technique-specific)

**Examples:**
- "execution techniques"
- "lateral movement methods"
- "privilege escalation"

**Why Important:** Users often search by **tactic first**, then narrow down.

**Reuse:**
```bash
cp _codex/threatassessor-master/tests/data/generated/tactic_queries.jsonl \
   tests/data/generated/
```

**Test Usage:**
```python
def test_semantic_search_tactic_queries():
    """Test tactic-level searches return relevant techniques."""
    records = load_jsonl(Path("tests/data/generated/tactic_queries.jsonl"))
    metrics = evaluate_records(records, search_fn)
    
    # Tactic queries: Just need correct tactic, not specific technique
    assert metrics["tactic_match_rate"] >= 0.70, "Should match correct tactic"
```

---

### 4. **robustness_mutations.jsonl** (24 records) - ✅ MEDIUM

**Purpose:** Test system handles variations (case, whitespace, typos)

**Examples:**
- "pOwErShElL" (mixed case)
- "powershell  execution" (extra spaces)
- "power shell" (split words)

**Why Useful:** Real users make typos and don't always format perfectly.

**Reuse:**
```bash
cp _codex/threatassessor-master/tests/data/generated/robustness_mutations.jsonl \
   tests/data/generated/
```

**Test Usage:**
```python
def test_semantic_search_robustness():
    """Test search handles case/whitespace variations."""
    records = load_jsonl(Path("tests/data/generated/robustness_mutations.jsonl"))
    metrics = evaluate_records(records, search_fn)
    
    # Should be robust to formatting
    assert metrics["top3_accuracy"] >= 0.50, "Should handle variations"
```

---

### 5. **platform_queries.jsonl** (6 records) - ✅ MEDIUM

**Purpose:** Test platform-specific searches

**Examples:**
- "Windows T1059.001 execution"
- "Linux privilege escalation"
- "macOS persistence"

**Why Useful:** Users often filter by platform during incident response.

**Reuse:**
```bash
cp _codex/threatassessor-master/tests/data/generated/platform_queries.jsonl \
   tests/data/generated/
```

---

### 6. **benign_admin_queries.jsonl** (12 records) - ✅ MEDIUM

**Purpose:** Validate system doesn't flag legitimate admin activities as threats

**Examples:**
- "scheduled backup"
- "software update"
- "user password reset"

**Why Useful:** Helps avoid **false positives** - distinguishes malicious from benign.

**Reuse:**
```bash
cp _codex/threatassessor-master/tests/data/generated/benign_admin_queries.jsonl \
   tests/data/generated/
```

**Test Usage:**
```python
def test_semantic_search_benign_queries():
    """Test benign admin queries have low confidence scores."""
    records = load_jsonl(Path("tests/data/generated/benign_admin_queries.jsonl"))
    
    # Benign queries should either return nothing or low-confidence results
    for record in records:
        results = search_techniques(record["query"], mitre, top_k=3)
        if results:
            assert results[0]["similarity_score"] < 0.5, \
                f"Benign query '{record['query']}' shouldn't match strongly"
```

---

### 7. **hard_negative_queries.jsonl** (3 records) - 🔶 LOW PRIORITY

**Purpose:** Test disambiguation ("T1059 but NOT T1053")

**Why Low Priority:** Edge case, only 3 records. Skip unless building production system.

---

### 8. **multi_step_chain_queries.jsonl** (1 record) - 🔶 LOW PRIORITY

**Purpose:** Test multi-stage attack chains

**Why Low Priority:** Only 1 record. Better tested via architecture analysis.

---

## Recommended Copy Strategy

### Option A: Copy Everything (Comprehensive)
```bash
cd /mnt/c/BACKUP/DEV-TEST

# Create structure
mkdir -p tests/data/fixtures tests/data/generated

# Copy fixtures (CRITICAL)
cp _codex/threatassessor-master/tests/data/fixtures/* tests/data/fixtures/

# Copy all generated datasets
cp _codex/threatassessor-master/tests/data/generated/*.jsonl tests/data/generated/

# Verify
ls tests/data/fixtures/  # Should show 2 files
ls tests/data/generated/  # Should show 8 .jsonl files
wc -l tests/data/generated/*.jsonl  # Should show 109 total
```

**Total Size:** ~30KB (negligible)  
**Time:** 1 minute  
**Benefit:** Complete test coverage

---

### Option B: Copy Critical Only (Minimal)
```bash
cd /mnt/c/BACKUP/DEV-TEST
mkdir -p tests/data/fixtures tests/data/generated

# Copy essential fixtures
cp _codex/threatassessor-master/tests/data/fixtures/mini_enterprise_attack.json \
   tests/data/fixtures/

# Copy critical datasets only
cp _codex/threatassessor-master/tests/data/generated/technique_canonical.jsonl \
   tests/data/generated/
cp _codex/threatassessor-master/tests/data/generated/technique_paraphrase.jsonl \
   tests/data/generated/
cp _codex/threatassessor-master/tests/data/generated/tactic_queries.jsonl \
   tests/data/generated/
```

**Records:** 63 (out of 109)  
**Coverage:** 58% of test data, 90% of critical tests  
**Recommendation:** Start here, add more later if needed

---

## Test Data Usage in Tests

### Example: Comprehensive Accuracy Test

```python
# tests/test_semantic_search.py
import pytest
from pathlib import Path
from chatbot.modules.mitre import MitreHelper
from chatbot.modules.mitre_embeddings import search_techniques
from tests.eval_utils import load_jsonl, evaluate_records


@pytest.mark.online
@pytest.mark.slow
def test_semantic_search_full_evaluation():
    """Comprehensive semantic search evaluation across all datasets."""
    mitre = MitreHelper(use_local=True)
    
    datasets = [
        ("technique_canonical.jsonl", {"top1": 0.70, "top3": 0.85}),
        ("technique_paraphrase.jsonl", {"top1": 0.40, "top3": 0.60}),
        ("tactic_queries.jsonl", {"tactic_match": 0.70}),
        ("robustness_mutations.jsonl", {"top3": 0.50}),
    ]
    
    results = {}
    for dataset_name, thresholds in datasets:
        path = Path(f"tests/data/generated/{dataset_name}")
        if not path.exists():
            continue
        
        records = load_jsonl(path)
        metrics = evaluate_records(
            records,
            lambda q: search_techniques(q, mitre, top_k=5)
        )
        
        results[dataset_name] = metrics
        
        # Check thresholds
        if "top1" in thresholds:
            assert metrics["top1_accuracy"] >= thresholds["top1"], \
                f"{dataset_name}: top-1 accuracy too low"
        if "top3" in thresholds:
            assert metrics["top3_accuracy"] >= thresholds["top3"], \
                f"{dataset_name}: top-3 accuracy too low"
        if "tactic_match" in thresholds:
            assert metrics["tactic_match_rate"] >= thresholds["tactic_match"], \
                f"{dataset_name}: tactic match rate too low"
    
    # Print summary
    print("\n=== Semantic Search Evaluation Results ===")
    for name, metrics in results.items():
        print(f"\n{name}:")
        print(f"  Top-1: {metrics.get('top1_accuracy', 0):.2%}")
        print(f"  Top-3: {metrics.get('top3_accuracy', 0):.2%}")
        print(f"  Tactic: {metrics.get('tactic_match_rate', 0):.2%}")
```

---

## Integration with STATUS_AND_PLAN.md

**Update Phase 2 - Step 2.1:**

```markdown
#### Step 2.1: Port Test Infrastructure (30 min)

```bash
cd /mnt/c/BACKUP/DEV-TEST

# Create test structure
mkdir -p tests/data/fixtures tests/data/generated

# Port shared fixtures and utilities
cp _codex/threatassessor-master/tests/conftest.py tests/
cp _codex/threatassessor-master/tests/eval_utils.py tests/

# Port test data (109 test records)
cp _codex/threatassessor-master/tests/data/fixtures/* tests/data/fixtures/
cp _codex/threatassessor-master/tests/data/generated/*.jsonl tests/data/generated/

# Verify
ls tests/data/fixtures/  # Should show mini_enterprise_attack.json, sample_architecture_input.txt
ls tests/data/generated/  # Should show 8 .jsonl files
wc -l tests/data/generated/*.jsonl  # Should show 109 total test records
```

**Checklist:**
- [ ] `conftest.py` copied
- [ ] `eval_utils.py` copied
- [ ] Mini MITRE fixture available (5.9KB)
- [ ] Sample architecture input available (446B)
- [ ] **109 test queries** copied (8 datasets)
- [ ] Can run: `pytest tests/ --collect-only`
```

---

## Benefits of Reusing Test Data

### 1. **Immediate Validation** (Critical)
- **48 technique queries** (24 canonical + 24 paraphrase) = Core validation
- Can measure **actual accuracy** instead of guessing
- Baseline: "Is semantic search working at all?"

### 2. **Real-World Coverage** (High Value)
- **Paraphrase queries** = How users actually search
- **Tactic queries** = Common IR workflow
- **Benign queries** = False positive prevention

### 3. **Regression Detection** (Long-term)
- Measure before/after changes
- Track: "Did I break semantic search?"
- CI/CD integration: Run on every commit

### 4. **Performance Benchmarking** (Bonus)
- Track accuracy over time
- Compare models/approaches
- Measure: "Is new embedding model better?"

---

## Quick Commands

**Copy all test data:**
```bash
cd /mnt/c/BACKUP/DEV-TEST
mkdir -p tests/data/{fixtures,generated}
cp _codex/threatassessor-master/tests/data/fixtures/* tests/data/fixtures/
cp _codex/threatassessor-master/tests/data/generated/*.jsonl tests/data/generated/
```

**Check what you got:**
```bash
ls tests/data/fixtures/
ls tests/data/generated/
wc -l tests/data/generated/*.jsonl
```

**Use in tests:**
```bash
# Test with canonical queries (easiest)
pytest tests/test_semantic_search.py -v -k canonical

# Test with paraphrases (real-world)
pytest tests/test_semantic_search.py -v -k paraphrase

# Full evaluation (all 109 records)
pytest tests/test_semantic_search.py::test_semantic_search_full_evaluation -v
```

---

## Summary

**Available Test Data:**
- ✅ 2 fixture files (mini MITRE, sample architecture)
- ✅ 109 test queries across 8 datasets
- ✅ Total size: ~30KB (negligible)

**Recommended Action:**
Copy everything (Option A) - it's tiny and gives complete coverage.

**Next Step:**
Update `STATUS_AND_PLAN.md` Phase 2 to include test data copying.

---

*Test data assessment complete - ready for reuse in main repo*
