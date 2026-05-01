# Test Data Quick Reference

**Total Test Records:** 109 queries + 2 fixture files  
**Total Size:** ~30KB (negligible)  
**Source:** threatassessor-master (validated test suite)

---

## Quick Copy (1 minute)

```bash
cd /mnt/c/BACKUP/DEV-TEST
mkdir -p tests/data/fixtures tests/data/generated

# Copy everything (recommended)
cp _codex/threatassessor-master/tests/data/fixtures/* tests/data/fixtures/
cp _codex/threatassessor-master/tests/data/generated/*.jsonl tests/data/generated/

# Verify
wc -l tests/data/generated/*.jsonl  # Should show 109 total
```

---

## What You Get

### Fixtures (2 files)
- `mini_enterprise_attack.json` (5.9KB) - Lightweight MITRE dataset for offline tests
- `sample_architecture_input.txt` (446B) - Example Mermaid diagram + risk notes

### Test Queries (109 records in 8 datasets)

| Dataset | Count | Purpose | Priority |
|---------|-------|---------|----------|
| technique_canonical.jsonl | 24 | Exact names/IDs/descriptions | ⭐ CRITICAL |
| technique_paraphrase.jsonl | 24 | Real-world phrasings | ⭐ CRITICAL |
| tactic_queries.jsonl | 15 | Tactic-level searches | ⭐ HIGH |
| robustness_mutations.jsonl | 24 | Case/whitespace variations | 🔶 MEDIUM |
| platform_queries.jsonl | 6 | Platform-specific queries | 🔶 MEDIUM |
| benign_admin_queries.jsonl | 12 | False positive tests | 🔶 MEDIUM |
| hard_negative_queries.jsonl | 3 | Disambiguation | 🔷 LOW |
| multi_step_chain_queries.jsonl | 1 | Attack chains | 🔷 LOW |

---

## Sample Test Query

```json
{
  "query": "attacker used Remote Desktop Protocol",
  "expected_ids": ["T1021.001"],
  "allowed_ids": ["T1021"],
  "expected_tactics": ["lateral-movement"],
  "platforms": ["Windows"],
  "test_type": "paraphrase",
  "difficulty": "medium"
}
```

---

## Usage in Tests

```python
from pathlib import Path
from tests.eval_utils import load_jsonl, evaluate_records

# Load canonical queries (easiest - should have 70%+ accuracy)
records = load_jsonl(Path("tests/data/generated/technique_canonical.jsonl"))

# Evaluate semantic search
metrics = evaluate_records(records, search_fn)

print(f"Top-1 Accuracy: {metrics['top1_accuracy']:.2%}")
print(f"Top-3 Accuracy: {metrics['top3_accuracy']:.2%}")
```

---

## Expected Accuracy Baselines

| Dataset | Top-1 Target | Top-3 Target | Notes |
|---------|--------------|--------------|-------|
| Canonical | ≥ 70% | ≥ 85% | Should be easy |
| Paraphrase | ≥ 40% | ≥ 60% | Real-world usage |
| Tactic | N/A | N/A | Use tactic_match_rate ≥ 70% |
| Robustness | N/A | ≥ 50% | Should handle variations |

---

## Files Created

After running the copy command:
```
tests/
├── data/
│   ├── fixtures/
│   │   ├── mini_enterprise_attack.json
│   │   └── sample_architecture_input.txt
│   └── generated/
│       ├── technique_canonical.jsonl (24)
│       ├── technique_paraphrase.jsonl (24)
│       ├── tactic_queries.jsonl (15)
│       ├── robustness_mutations.jsonl (24)
│       ├── platform_queries.jsonl (6)
│       ├── benign_admin_queries.jsonl (12)
│       ├── hard_negative_queries.jsonl (3)
│       └── multi_step_chain_queries.jsonl (1)
```

---

## Next Steps

1. Copy test data (above command)
2. Port test infrastructure (`conftest.py`, `eval_utils.py`)
3. Create `test_semantic_search.py` with accuracy tests
4. Run: `pytest tests/test_semantic_search.py -v`

See `TEST_DATA_ASSESSMENT.md` for complete analysis.

---

*109 validated test queries ready to validate your semantic search!*
