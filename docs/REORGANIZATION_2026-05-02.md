# Documentation Reorganization Plan

**Date:** 2026-05-02  
**Current:** 71 markdown files, 611 KB  
**Goal:** Clean, organized, no duplicates, intuitive structure

---

## Current Issues

### Problems Identified

1. **Too many files in root** (8 docs in root directory)
   - DEPLOYMENT_CHECKLIST.md
   - DEPLOY_NOW.md
   - FINAL_SUMMARY.md
   - SELF_TEST_FEATURE.md
   - STATUS_AND_PLAN.md
   - CLAUDE.md ✅ (should stay)
   - README.md ✅ (should stay)

2. **Duplicate content in tests/** (11 docs, 115 KB)
   - Many are session working docs, not permanent references
   - TEST_DATA_ASSESSMENT.md duplicated in docs/testing/

3. **Unclear separation** between:
   - Session summaries (temporary)
   - Reference documentation (permanent)
   - Implementation notes (historical)

4. **No clear update tracking** - Hard to know what's current

---

## Proposed Structure

### Target Organization

```
/mnt/c/BACKUP/DEV-TEST/
│
├── README.md                    # Main entry point ✅
├── CLAUDE.md                    # Developer guidelines ✅
├── STATUS_AND_PLAN.md          # Current status (living document) ✅
│
├── docs/                        # Permanent reference docs
│   ├── README.md               # Documentation index ✅
│   ├── ARCHITECTURE.md         # System design ✅
│   ├── OPERATIONS.md           # Ops/troubleshooting ✅
│   ├── OUTPUT_FORMATS.md       # Format guide ✅
│   ├── SELF_TEST.md            # Self-test feature ✅
│   │
│   ├── deployment/             # NEW: Deployment guides
│   │   ├── CHECKLIST.md       # Full deployment checklist
│   │   └── QUICK_START.md     # Fast deployment
│   │
│   ├── specs/                  # Requirements/specs ✅
│   │   └── MVP_SPECIFICATION.md
│   │
│   ├── testing/                # Testing documentation
│   │   ├── README.md          # Testing overview ✅
│   │   ├── STRATEGY.md        # Testing strategy
│   │   └── RESULTS.md         # Latest test results (Phase 2.2)
│   │
│   └── archive/                # Historical docs ✅
│       └── [old docs]
│
├── tests/                      # Test code + results
│   ├── README.md              # NEW: Test suite overview
│   ├── conftest.py            ✅
│   ├── test_*.py              ✅
│   │
│   └── results/               # NEW: Test result summaries
│       └── phase2.2/
│           ├── summary.md     # Consolidated results
│           └── analysis.md    # Analysis docs
│
├── archive/                    # Session notes ✅
│   ├── session-notes/
│   └── test-results/
│
└── .archive/                   # Auto-archived ✅
    └── [date folders]
```

---

## Reorganization Actions

### Phase 1: Move Root Documents (Session Working Docs)

**Move to appropriate locations:**

| Current Location | New Location | Reason |
|-----------------|--------------|--------|
| DEPLOYMENT_CHECKLIST.md | docs/deployment/CHECKLIST.md | Deployment guide |
| DEPLOY_NOW.md | docs/deployment/QUICK_START.md | Quick deploy guide |
| FINAL_SUMMARY.md | archive/session-notes/phase2.2-summary.md | Session summary |
| SELF_TEST_FEATURE.md | archive/session-notes/self-test-implementation.md | Implementation notes |

**Keep in root:**
- README.md ✅
- CLAUDE.md ✅
- STATUS_AND_PLAN.md ✅

---

### Phase 2: Consolidate Test Documentation

**Currently in tests/** (11 files):
```
tests/EASY_KILL_TESTS.md           → archive (session planning)
tests/FALLBACK_ANALYSIS.md         → docs/testing/FALLBACK_ANALYSIS.md (reference)
tests/ITERATIVE_TEST_STRATEGY.md   → archive (session planning)
tests/SIZE_ESTIMATES.md            → archive (session planning)
tests/STAGE1_RESULTS.md            → tests/results/phase2.2/stage1.md
tests/STAGE1_SUMMARY.md            → MERGE into tests/results/phase2.2/summary.md
tests/TESTING.md                   → DELETE (duplicate)
tests/TESTING_GUIDE.md             → MERGE into tests/README.md
tests/TEST_DATA_ASSESSMENT.md      → KEEP (delete duplicate in docs/testing/)
tests/TEST_INTEGRATION.md          → archive (historical)
tests/TIER1_TEST_RESULTS.md        → tests/results/phase2.2/tier1.md
```

**Create consolidated:**
- `tests/README.md` - Overview of test suite
- `tests/results/phase2.2/summary.md` - Phase 2.2 complete results
- `tests/results/phase2.2/analysis.md` - Detailed analysis

---

### Phase 3: Consolidate Documentation

**Currently in docs/testing/** (5 files):
```
docs/testing/DATA_STRATEGY.md           → KEEP
docs/testing/README.md                  → KEEP
docs/testing/README_TEST_DATA.md        → MERGE into README.md
docs/testing/TESTING_STRATEGY.md        → KEEP
docs/testing/TEST_DATA_ASSESSMENT.md    → DELETE (duplicate of tests/)
```

**Currently in docs/implementation/** (5 files):
```
docs/implementation/CLEANUP_SUMMARY.md           → archive/session-notes/
docs/implementation/CONFIDENCE_VALIDATION.md     → archive/session-notes/
docs/implementation/FORMATS_IMPLEMENTATION.md    → archive/session-notes/
docs/implementation/IMPLEMENTATION_SUMMARY.md    → archive/session-notes/
docs/implementation/SESSION_COMPLETE.md          → archive/session-notes/
```

After moving, **DELETE docs/implementation/** (all are session notes)

---

### Phase 4: Create New Structure

**New directories:**
```bash
mkdir -p docs/deployment
mkdir -p tests/results/phase2.2
```

**New files to create:**
```
docs/deployment/README.md          # Deployment overview
tests/README.md                    # Test suite guide
tests/results/phase2.2/summary.md  # Consolidated Phase 2.2 results
```

---

## File-by-File Actions

### Root Directory (8 → 3 files)

```bash
# Keep
README.md                 # Main entry ✅
CLAUDE.md                 # Dev guidelines ✅
STATUS_AND_PLAN.md       # Living document ✅

# Move
mv DEPLOYMENT_CHECKLIST.md docs/deployment/CHECKLIST.md
mv DEPLOY_NOW.md docs/deployment/QUICK_START.md
mv FINAL_SUMMARY.md archive/session-notes/phase2.2-final-summary.md
mv SELF_TEST_FEATURE.md archive/session-notes/self-test-feature.md
```

### Tests Directory (11 → 5 files + results/)

```bash
# Keep (permanent reference)
tests/TEST_DATA_ASSESSMENT.md      # Coverage analysis ✅
tests/FALLBACK_ANALYSIS.md         # Fallback quality analysis ✅

# Move to results
mv tests/STAGE1_RESULTS.md tests/results/phase2.2/stage1-results.md
mv tests/TIER1_TEST_RESULTS.md tests/results/phase2.2/tier1-results.md

# Archive (session planning docs)
mv tests/EASY_KILL_TESTS.md archive/session-notes/easy-kill-tests-planning.md
mv tests/ITERATIVE_TEST_STRATEGY.md archive/session-notes/iterative-test-strategy.md
mv tests/SIZE_ESTIMATES.md archive/session-notes/size-estimates.md
mv tests/STAGE1_SUMMARY.md archive/session-notes/stage1-summary.md
mv tests/TEST_INTEGRATION.md archive/session-notes/test-integration.md

# Delete (duplicates)
rm tests/TESTING.md  # Duplicate content
```

**Create consolidated summary:**
```bash
# New: tests/results/phase2.2/summary.md
# Combines: STAGE1_SUMMARY, TIER1_RESULTS, FINAL_SUMMARY
```

### Docs Directory

```bash
# Move implementation notes to archive
mv docs/implementation/*.md archive/session-notes/
rmdir docs/implementation

# Delete duplicate
rm docs/testing/TEST_DATA_ASSESSMENT.md  # Duplicate of tests/

# Merge README_TEST_DATA into README
cat docs/testing/README_TEST_DATA.md >> docs/testing/README.md
rm docs/testing/README_TEST_DATA.md

# Create new deployment docs
mkdir -p docs/deployment
# (files moved from root)
```

---

## New File Contents

### 1. tests/README.md

```markdown
# Test Suite Documentation

**Status:** Phase 2.2 Complete (84.9% accuracy validated)

## Quick Start

\`\`\`bash
# Run all tests
pytest tests/ -v

# Run specific test
pytest tests/test_semantic_search.py -v

# Run self-test (quick validation)
python3 -m chatbot.main --self-test
\`\`\`

## Test Coverage

- **146 test queries** across all 14 MITRE tactics
- **84.9% overall accuracy** (top-3)
- **100% robustness** (mutations, special chars)
- **Test files:** See conftest.py, test_*.py

## Test Results

Latest: [Phase 2.2 Results](results/phase2.2/summary.md)

## Reference Documents

- [Test Data Assessment](TEST_DATA_ASSESSMENT.md) - Coverage analysis
- [Fallback Analysis](FALLBACK_ANALYSIS.md) - Keyword fallback quality
- [Testing Strategy](../docs/testing/TESTING_STRATEGY.md) - Overall approach

## See Also

- [docs/testing/](../docs/testing/) - Testing documentation
- [docs/SELF_TEST.md](../docs/SELF_TEST.md) - Self-test feature
```

### 2. tests/results/phase2.2/summary.md

```markdown
# Phase 2.2 Test Results Summary

**Date:** 2026-05-02  
**Status:** ✅ Complete  
**Confidence:** 79% (production-ready)

## Overall Results

| Metric | Result |
|--------|--------|
| Overall accuracy | **84.9%** (146 queries) |
| Tactic coverage | **14/14** (100%) |
| Min per-tactic | **75%** (lateral-movement) |
| Stage 1 smoke | **100%** (8/8) |
| Robustness | **100%** (24/24) |

## Detailed Results

- [Stage 1 Results](stage1-results.md)
- [Tier 1 Results](tier1-results.md)

## Analysis

See [tests/TEST_DATA_ASSESSMENT.md](../../TEST_DATA_ASSESSMENT.md) for coverage analysis.
See [tests/FALLBACK_ANALYSIS.md](../../FALLBACK_ANALYSIS.md) for fallback quality.

## Next Steps

- Deploy to production
- Monitor with Stage 4 (production feedback)
- Expand coverage based on usage patterns
```

### 3. docs/deployment/README.md

```markdown
# Deployment Documentation

## Quick Links

- [Quick Start](QUICK_START.md) - Deploy in 30 minutes
- [Full Checklist](CHECKLIST.md) - Complete deployment guide

## Deployment Modes

### Development
\`\`\`bash
source .venv/bin/activate
python3 -m chatbot.main
\`\`\`

### Production
See [CHECKLIST.md](CHECKLIST.md) for:
- Pre-deployment validation
- Monitoring setup
- Health checks

## Pre-Deployment

**Always run self-test first:**
\`\`\`bash
python3 -m chatbot.main --self-test
\`\`\`

## See Also

- [STATUS_AND_PLAN.md](../../STATUS_AND_PLAN.md) - Current status
- [docs/OPERATIONS.md](../OPERATIONS.md) - Ops guide
```

---

## Duplicate Detection

### Confirmed Duplicates to Remove

1. **tests/TEST_DATA_ASSESSMENT.md** vs **docs/testing/TEST_DATA_ASSESSMENT.md**
   - Keep: tests/ (source of truth)
   - Delete: docs/testing/ (copy)

2. **tests/TESTING.md** vs **tests/TESTING_GUIDE.md**
   - Merge content into tests/README.md
   - Delete both originals

3. **docs/testing/README_TEST_DATA.md** vs **docs/testing/README.md**
   - Merge README_TEST_DATA into README
   - Delete README_TEST_DATA

---

## Update Tracking System

### Add to Each Document

```markdown
---
**Last Updated:** 2026-05-02
**Status:** Current | Archived | Superseded
**Superseded By:** [link if applicable]
---
```

### Status Definitions

- **Current:** Active reference, kept up-to-date
- **Archived:** Historical record, not updated
- **Superseded:** Replaced by newer document

### Update Log (Add to STATUS_AND_PLAN.md)

```markdown
## Documentation Updates

- 2026-05-02: Phase 2.2 validation complete, docs reorganized
- 2026-05-01: Phase 2A complete, docs consolidated
```

---

## Commit Rules (For Future)

### Before Every Commit

1. **Check for duplicates**
   ```bash
   # Find similar filenames
   find . -name "*.md" -type f | sort | uniq -d
   ```

2. **Organize by purpose**
   - Root: Only README, CLAUDE, STATUS_AND_PLAN
   - docs/: Permanent reference
   - tests/: Test code + current results
   - archive/: Historical/session notes

3. **Check for sensitive data**
   ```bash
   # Check for API keys
   grep -r "sk-or-v1" . --include="*.md"
   grep -r "OPENROUTER_API_KEY" . --include="*.md"
   grep -r "password" . --include="*.md"
   ```

4. **Update STATUS_AND_PLAN.md**
   - Add entry to documentation updates
   - Update "Last Updated" date

5. **Verify file sizes**
   ```bash
   # Check for large docs (>50KB)
   find docs/ -name "*.md" -size +50k
   ```

---

## .gitignore Updates

```gitignore
# Documentation (ensure these are excluded)
_codex/
.archive/
archive/

# Sensitive files (double-check)
.env
*.key
*.pem
*secret*
*password*

# Large data files
chatbot/data/*.json
```

---

## Implementation Steps

### Step 1: Create New Structure (5 min)
```bash
mkdir -p docs/deployment
mkdir -p tests/results/phase2.2
```

### Step 2: Move Files (10 min)
```bash
# Execute moves from "File-by-File Actions" above
```

### Step 3: Create New Files (10 min)
```bash
# Create tests/README.md
# Create tests/results/phase2.2/summary.md
# Create docs/deployment/README.md
```

### Step 4: Update References (5 min)
```bash
# Update links in README.md, STATUS_AND_PLAN.md
# Update internal cross-references
```

### Step 5: Verify (5 min)
```bash
# Check for broken links
# Verify no sensitive data
# Test that docs are accessible
```

### Total Time: ~35 minutes

---

## Post-Reorganization Structure

### Final Count

```
Root: 3 files (README, CLAUDE, STATUS_AND_PLAN)
docs/: ~15 files (organized by purpose)
tests/: ~10 files (code + 2 reference docs)
archive/: ~40 files (historical)

Total committed: ~30 active files (vs 71 current)
Reduction: 58% fewer files in active areas
```

### Benefits

✅ **Intuitive:** Easy to find what you need  
✅ **Clean:** No duplicates, clear purpose  
✅ **Maintainable:** Clear rules for future additions  
✅ **Traceable:** Update tracking in place  
✅ **Secure:** No sensitive data in public docs

---

## Validation Checklist

Before final commit:

- [ ] No duplicates (check with: `find . -name "*.md" | sort | uniq -c | grep -v " 1 "`)
- [ ] No sensitive data (check with grep patterns above)
- [ ] All docs have update dates
- [ ] STATUS_AND_PLAN.md updated
- [ ] README.md links work
- [ ] Tests/docs directories clean
- [ ] Archive directories excluded from git

---

**Ready to Execute:** Yes, proceed with reorganization

**Estimated Time:** 35 minutes

**Risk:** Low (all moves, no deletions until verified)
