# Phase 3D Scripts - MoE Architecture

**Phase:** 3D (Mixture of Experts)  
**Date:** 2025-05-17  
**Status:** Week 1 Complete

---

## Available Scripts

### Test Scripts

#### `test_moe_foundation.py`
Tests MoE foundation (Week 1).

**Usage:**
```bash
source .venv/bin/activate
python3 scripts/phase3d/test_moe_foundation.py
```

**Tests:**
1. Fail-Fast Validation
2. Sequential Enforcement
3. Confidence Adjustments
4. Consensus Synthesis

**Expected:** 4/4 tests passing

---

## Quick Commands

### Run Full MoE Pipeline
```bash
source .venv/bin/activate
python3 -c "
from chatbot.modules.agents import run_moe_pipeline
result = run_moe_pipeline('report_samples/example_architecture')
print(f'Confidence: {result.final_confidence:.1f}%')
"
```

### Test on Specific Architecture
```bash
source .venv/bin/activate
python3 -c "
from chatbot.modules.agents import run_moe_pipeline
result = run_moe_pipeline('report/YOUR_ARCHITECTURE')
print(f'Final: {result.final_confidence:.1f}%')
print(f'Critical: {len(result.critical_recommendations)}')
print(f'High: {len(result.high_recommendations)}')
"
```

### Check Generated Files
```bash
ls -1 report/YOUR_ARCHITECTURE/ | grep -E "^\d|^(before|after|ground)"
# Should show 15 files
```

---

## Integration with Other Scripts

### Agent Testing (Phase 3C)
- `scripts/agent_testing/run_full_critique.py` - Legacy composite scoring
- Use `run_moe_pipeline()` instead for Phase 3D

### Generation
- `scripts/generation/generate_ground_truth.py` - Still used (Layer 1)
- MoE orchestrator auto-calls this

### Validation
- `scripts/validation/check_orphans.py` - Still valid
- Run before MoE pipeline

---

## Troubleshooting

### Missing Files
```bash
# Check which files are missing
python3 -c "
from pathlib import Path
report_dir = Path('report/YOUR_ARCHITECTURE')
expected = ['ground_truth.json', '04_architect_critique.json', 
            '05_tester_critique.json', '06_red_team_critique.json',
            '07_moe_orchestrator.json', '08_improvement_summary.md',
            'before.mmd', 'after.mmd', '08a_quick_wins.mmd',
            '08b_recommended_target.mmd', '08c_maximum_security.mmd']
for f in expected:
    exists = '✅' if (report_dir / f).exists() else '❌'
    print(f'{exists} {f}')
"
```

### Test Failures
```bash
# Run with verbose logging
python3 scripts/phase3d/test_moe_foundation.py 2>&1 | tee test_output.log
```

---

**Status:** Week 1 ✅ Complete  
**Next:** Week 2 scripts (expert refactoring)  
**Author:** ThreatAssessor Development Team
