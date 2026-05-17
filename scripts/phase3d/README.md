# Phase 3D Scripts - MoE Architecture

**Phase:** 3D (Mixture of Experts)  
**Date:** 2026-05-17  
**Status:** ✅ Week 1-3 Complete

---

## Active Scripts

**None** - Foundation testing complete. Use production modules directly.

### Archived Scripts

**Location:** `archive/phase3d_test_data/`

- `test_moe_foundation.py` - Week 1 foundation validation (archived, no longer needed)

---

## Production Usage

### Run Full MoE Pipeline
```bash
# Generate deterministic analysis
python3 -m chatbot.main --gen-arch-truth architecture.mmd

# Run MoE validation
python3 -m chatbot.modules.agents report/architecture_name

# Generate executive dashboard
python3 -m chatbot.modules.executive_dashboard_generator report/architecture_name

# View primary report
cat report/architecture_name/00_executive_dashboard.md
```

### Programmatic Usage
```python
from chatbot.modules.agents import run_moe_pipeline

# Run MoE validation
result = run_moe_pipeline('report/architecture_name')

print(f'Confidence: {result.final_confidence:.1f}%')
print(f'Status: {result.validation_status}')
print(f'Critical: {len(result.consensus.critical)}')
```

### Check Generated Files
```bash
ls -1 report/architecture_name/ | wc -l
# Should show 16 files (00-08 + diagrams + ground_truth)
```

---

## Week 4 Scripts (Planned)

### batch_test_moe.py (TODO - Task 13)

**Purpose:** Validate MoE pipeline across 10 architectures

**Tests:**
- All architectures generate successfully
- Coherence across 16 files
- Confidence scores 84-95%
- No risk extraction failures

**Expected Output:**
```
✅ 10/10 architectures passed
- Average confidence: 91.2%
- Coherence issues: 0
```

---

**Status:** Week 1-3 ✅ Complete  
**Next:** Week 4 (Branding + Batch Testing + API docs)  
**Last Updated:** 2026-05-17
