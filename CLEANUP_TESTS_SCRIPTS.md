# Tests & Scripts Cleanup Plan

**Date:** 2026-05-17  
**Context:** Post Phase 3C+ cleanup  
**Status:** 📋 PLAN

---

## Current State Analysis

### tests/ Structure (7 directories, ~30 files)

```
tests/
├── README.md                           ✅ Keep
├── conftest.py                         ✅ Keep (pytest config)
├── eval_utils.py                       ✅ Keep (evaluation utilities)
├── __init__.py                         ✅ Keep
│
├── phase2/                             ❓ REVIEW (4 test files from Phase 2)
│   ├── test_phase2_semantic_search.py  ❌ Archive (Phase 2 obsolete)
│   ├── test_scoring.py                 ❓ Check if still relevant
│   ├── test_semantic_search.py         ❓ Check if still relevant
│   └── test_stage1_validation.py       ❌ Archive (Stage 1 obsolete)
│
├── unit/                               ✅ Keep (2 test files)
│   ├── test_control_detection.py       ✅ Keep
│   └── test_mitre.py                   ✅ Keep
│
├── phase3c/                            ✅ Keep (agent tests)
│   └── (agent test files)
│
├── data/                               ✅ Keep
│   ├── architectures/                  ✅ Keep (22 .mmd files)
│   └── agent_test_cases/              ✅ Keep
│
└── results/                            ✅ Keep (test results)
    └── test_results_llm_providers.json
```

---

### scripts/ Structure (5 directories, ~17 files)

```
scripts/
├── README.md                                    ✅ Keep
│
├── agent_testing/                               ✅ Keep (active)
│   ├── run_full_critique.py                    ✅ Keep
│   ├── run_full_pipeline.py                    ✅ Keep
│   ├── test_architect.sh                       ✅ Keep
│   ├── test_red_team_confidence.py             ✅ Keep
│   ├── test_red_team_contrast.py               ✅ Keep
│   └── test_red_teamer_full.py                 ✅ Keep
│
├── generation/                                  ✅ Keep
│   ├── batch_generate_ground_truth.sh          ✅ Keep
│   ├── demo_mitre_advice.py                    ❓ Check if used
│   └── generate_ground_truth.py                ✅ Keep
│
├── integration/                                 ✅ Keep
│   ├── backtest_all_architectures.py           ✅ Keep (used in validation)
│   ├── test_llm_providers.py                   ✅ Keep
│   ├── test_openrouter.py                      ✅ Keep
│   ├── validate_engine_accuracy.py             ✅ Keep
│   └── validate_parser_harness.py              ✅ Keep
│
├── validation/                                  ✅ Keep
│   ├── check_orphans.py                        ✅ Keep (actively used)
│   └── validate_llm_config.py                  ✅ Keep
│
└── personal/                                    ❌ ARCHIVE
    └── sync_repos.sh                            ❌ Archive (references _codex)
```

---

## Files to Archive

### tests/phase2/ (4 files) - Phase 2 is obsolete

**Archive all Phase 2 tests:**
```bash
mkdir -p archive/tests/phase2
mv tests/phase2/test_phase2_semantic_search.py archive/tests/phase2/
mv tests/phase2/test_stage1_validation.py archive/tests/phase2/
```

**Review these (may still be relevant):**
```bash
tests/phase2/test_scoring.py           # Check if scoring module still tested
tests/phase2/test_semantic_search.py   # Check if semantic search still used
```

**After review, if obsolete:**
```bash
mv tests/phase2/test_scoring.py archive/tests/phase2/
mv tests/phase2/test_semantic_search.py archive/tests/phase2/
rmdir tests/phase2/  # If empty
```

---

### scripts/personal/ (1 file) - Personal scripts

**Archive personal sync script:**
```bash
mkdir -p archive/scripts/personal
mv scripts/personal/sync_repos.sh archive/scripts/personal/
rmdir scripts/personal/  # If empty
```

**Reason:** References `_codex/threatassessor-master` which may not exist, personal maintenance script

---

### scripts/generation/demo_mitre_advice.py - Check if used

**Investigate:**
```bash
grep -r "demo_mitre_advice" . --exclude-dir=archive
# If no references found, archive it
mv scripts/generation/demo_mitre_advice.py archive/scripts/generation/
```

---

## Proposed Structure After Cleanup

### tests/ (clean)

```
tests/
├── README.md                     # Test documentation
├── conftest.py                   # Pytest configuration
├── eval_utils.py                 # Evaluation utilities
├── __init__.py
│
├── unit/                         # Unit tests (2 files)
│   ├── test_control_detection.py
│   └── test_mitre.py
│
├── phase3c/                      # Phase 3C agent tests
│   └── (agent test files)
│
├── data/                         # Test data
│   ├── architectures/            # 22 .mmd test files
│   └── agent_test_cases/         # Agent test cases
│
└── results/                      # Test results
    └── test_results_llm_providers.json
```

**Files removed:** ~4-6 files (phase2/ folder)

---

### scripts/ (clean)

```
scripts/
├── README.md
│
├── agent_testing/                # Agent testing scripts (6 files)
│   └── (all current scripts)
│
├── generation/                   # Ground truth generation (2-3 files)
│   ├── batch_generate_ground_truth.sh
│   └── generate_ground_truth.py
│   └── (possibly demo_mitre_advice.py if still used)
│
├── integration/                  # Integration tests (5 files)
│   └── (all current scripts)
│
└── validation/                   # Validation scripts (2 files)
    ├── check_orphans.py
    └── validate_llm_config.py
```

**Files removed:** 1-2 files (personal/ folder + possibly demo script)

---

## Investigation Required

### 1. Check if Phase 2 scoring tests are still relevant

```bash
# Check if scoring module exists and is tested elsewhere
ls chatbot/modules/scoring.py
grep -r "test_scoring\|from.*scoring import" tests/phase3c/
```

**If scoring is still used but not tested in phase3c:**
- Move `test_scoring.py` to `tests/unit/` instead of archiving
- Update imports if needed

**If scoring is obsolete:**
- Archive to `archive/tests/phase2/`

---

### 2. Check if semantic search tests are still relevant

```bash
# Check if semantic search/embeddings are still used
ls chatbot/modules/*embed* chatbot/modules/*semantic*
grep -r "semantic_search\|build_technique_embeddings" chatbot/modules/
```

**If semantic search is still core functionality:**
- Move `test_semantic_search.py` to `tests/unit/` or `tests/integration/`
- Update to test current implementation

**If semantic search is obsolete or replaced:**
- Archive to `archive/tests/phase2/`

---

### 3. Check if demo_mitre_advice.py is used

```bash
# Check for references
grep -r "demo_mitre_advice" . --exclude-dir=archive --exclude-dir=.git
cat scripts/generation/demo_mitre_advice.py | head -20  # Check header
```

**If it's a demo/example:**
- Keep if it demonstrates current functionality
- Archive if it demos obsolete features

**If never used:**
- Archive to `archive/scripts/generation/`

---

## Execution Plan

### Step 1: Investigate (15 minutes)

```bash
# Check scoring
echo "=== Checking scoring module ==="
ls -la chatbot/modules/scoring.py 2>/dev/null || echo "Not found"
python3 -m pytest tests/phase2/test_scoring.py -v 2>&1 | head -20

# Check semantic search
echo "=== Checking semantic search ==="
ls -la chatbot/modules/*embed* chatbot/modules/*semantic* 2>/dev/null || echo "Not found"
python3 -m pytest tests/phase2/test_semantic_search.py -v 2>&1 | head -20

# Check demo script
echo "=== Checking demo_mitre_advice ==="
head -30 scripts/generation/demo_mitre_advice.py
```

---

### Step 2: Archive Phase 2 tests (if obsolete)

```bash
mkdir -p archive/tests/phase2

# Definitely obsolete
mv tests/phase2/test_phase2_semantic_search.py archive/tests/phase2/
mv tests/phase2/test_stage1_validation.py archive/tests/phase2/

# After investigation, if also obsolete:
mv tests/phase2/test_scoring.py archive/tests/phase2/
mv tests/phase2/test_semantic_search.py archive/tests/phase2/

# Remove empty directory
rmdir tests/phase2/ 2>/dev/null || echo "Directory not empty or already removed"
```

---

### Step 3: Archive personal scripts

```bash
mkdir -p archive/scripts/personal
mv scripts/personal/sync_repos.sh archive/scripts/personal/
rmdir scripts/personal/ 2>/dev/null || echo "Directory not empty"
```

---

### Step 4: Archive demo script (if not used)

```bash
# Only if investigation shows it's obsolete
mkdir -p archive/scripts/generation
mv scripts/generation/demo_mitre_advice.py archive/scripts/generation/
```

---

### Step 5: Update READMEs

**tests/README.md:**
- Remove references to phase2/ tests
- Add note about phase3c/ tests
- Update test count

**scripts/README.md:**
- Remove references to personal/ if archived
- Update script count

---

### Step 6: Git commit

```bash
git add -A
git commit -m "tests/scripts: Archive obsolete Phase 2 tests and personal scripts

Archived:
- tests/phase2/ (4 files) - Phase 2 obsolete, now at v1.3/Phase 3C+
- scripts/personal/ (1 file) - Personal sync script referencing non-existent _codex/

Reason: Phase 2 tests no longer relevant after Phase 3C+ completion
Current testing: unit/ and phase3c/ tests cover v1.3 functionality

Tests remain: unit/, phase3c/, data/, results/
Scripts remain: agent_testing/, generation/, integration/, validation/

Co-Buddy: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Validation Checklist

After cleanup:
- ✅ All current tests still runnable (unit/, phase3c/)
- ✅ All active scripts still functional
- ✅ No broken references to archived files
- ✅ READMEs updated
- ✅ Clean directory structure (no obsolete phase2/)

---

## Summary

**Scope:** Archive 5-7 obsolete files  
**Impact:** Low (only obsolete Phase 2 tests and personal scripts)  
**Benefit:** Cleaner test/script structure, easier to navigate  
**Time:** 30 minutes (including investigation)

---

**Status:** 📋 READY FOR INVESTIGATION  
**Date:** 2026-05-17
