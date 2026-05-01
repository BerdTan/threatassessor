# Documentation Update Plan

**Date:** 2026-05-01  
**Reason:** Phase 2A completed, testing setup complete, need to sync all docs

---

## Documentation Status Analysis

### ✅ Already Updated (Current)
1. **ARCHITECTURE.md** - Just updated with Phase 2A status
2. **ARCHITECTURE_EXTENDED.md** - Synced from threatassessor (architecture analysis features)
3. **testing/** - All new, current (created today)
4. **RATE_LIMITING.md** - Current (documents implemented feature)

### ⚠️ Needs Major Update (Outdated Status)
1. **ROADMAP.md**
   - Says: "Planning Complete, Ready for Implementation"
   - Reality: Phase 2A complete, testing setup done
   - Last updated: 2026-04-25
   - **Action:** Update status, move completed items to "Done"

2. **QUICKSTART_PHASE2.md**
   - Probably has outdated instructions
   - May reference unimplemented features
   - **Action:** Review and update or deprecate

3. **INDEX.md**
   - Needs entry for `testing/` directory
   - May have outdated descriptions
   - **Action:** Add testing docs section

### 🔶 Might Need Minor Updates
4. **OPERATIONS.md**
   - Check if embedding cache instructions current
   - Check if rate limiting mentioned
   - **Action:** Quick review

5. **MAINTENANCE.md**
   - Check if procedures match current implementation
   - **Action:** Quick review

6. **MVP_SPECIFICATION.md**
   - May be historical/planning doc
   - **Action:** Check if still relevant or archive

7. **PROJECT_STRUCTURE.md**
   - Check if reflects current structure
   - **Action:** Quick review

### ✅ Likely Current (Reference Material)
8. **README.md** - Usually high-level, stable
9. **REFERENCES.md** - External links, stable
10. **QUICK_START.md** - Basic setup, probably stable
11. **QUICK_START_RATE_LIMITING.md** - Specific feature, probably current

---

## Recommended Update Priority

### Priority 1: Critical (Do Now - 15 min)

#### 1. Update ROADMAP.md
**Current Says:** "Planning Complete, Ready for Implementation"  
**Should Say:** "Phase 2A Complete, Testing Setup Done"

**Changes:**
```markdown
## Current Status

**Phase:** Phase 2A Complete, Testing Infrastructure Setup  
**Last Updated:** 2026-05-01  
**Status:** Production-ready semantic search + LLM analysis  
**Next Steps:** Create validation tests (Phase 2.2)

**Completed:**
1. ✅ Phase 1: Foundation & Configuration (2026-04-26)
   - OpenRouter API integration
   - Rate limiting implementation
   - Environment management

2. ✅ Phase 2A: Semantic Search + LLM Analysis (2026-04-26)
   - Embedding cache generation (45MB, 823 techniques)
   - Semantic search with cosine similarity
   - LLM refinement and ranking
   - Attack path generation
   - Contextual mitigation advice

3. ✅ Testing Infrastructure (2026-05-01)
   - 109 test queries ported from threatassessor
   - Production data fixtures strategy
   - Test evaluation utilities
   - Pytest markers and auto-skip logic

**In Progress:**
- Phase 2.2: Validation Testing (create semantic search accuracy tests)

**Backlog:**
- Architecture Analysis (threatassessor integration)
- Confidence scoring for attack paths
- Mermaid diagram output generation
```

#### 2. Update INDEX.md
**Add testing section:**
```markdown
### [testing/](testing/)
Testing strategy, test data, and validation documentation.

**Contains:**
- DATA_STRATEGY.md - Use production data for tests (89MB reused)
- TESTING_STRATEGY.md - Comprehensive testing approach
- TEST_DATA_ASSESSMENT.md - 109 test queries analysis
- README_TEST_DATA.md - Quick reference

**Read this when:**
- Setting up test infrastructure
- Creating new tests
- Validating semantic search accuracy
- Understanding test data strategy
```

---

### Priority 2: Review & Update If Needed (Do Soon - 30 min)

#### 3. Review QUICKSTART_PHASE2.md
**Check for:**
- Does it reference Phase 2A features?
- Are instructions still valid?
- Should it be merged into main docs or deprecated?

**Recommendation:** If specific to Phase 2A implementation, consider archiving or updating status.

#### 4. Review OPERATIONS.md
**Check sections:**
- Embedding cache generation procedure
- Rate limiting documentation references
- MITRE data update workflow

**Quick check:**
```bash
grep -n "embedding\|cache\|rate limit" docs/OPERATIONS.md
```

#### 5. Review MAINTENANCE.md
**Check:**
- Embedding cache regeneration instructions
- Backup procedures for 89MB production data
- Health check procedures

---

### Priority 3: Optional (Do Later - 15 min)

#### 6. Review PROJECT_STRUCTURE.md
**Check if includes:**
- `tests/` directory structure
- `docs/testing/` directory
- Updated module counts

#### 7. Check MVP_SPECIFICATION.md
**Determine:**
- Is this historical/planning doc?
- Should it be archived?
- Or updated to reflect current MVP?

---

## Quick Update Script

**For Priority 1 updates (15 min):**

```bash
cd /mnt/c/BACKUP/DEV-TEST/docs

# 1. Update ROADMAP.md
# Edit manually or use this template:
cat > ROADMAP_UPDATES.txt << 'EOF'
[Copy updated status from above]
EOF

# 2. Update INDEX.md
# Add testing/ section after MAINTENANCE.md

# 3. Verify changes
git diff ROADMAP.md INDEX.md
```

---

## Alternative: Create DOCS_STATUS.md

Instead of updating many docs, create a single status file:

**Create:** `docs/DOCS_STATUS.md`

```markdown
# Documentation Status

**Last Updated:** 2026-05-01

## Current Status Summary

**Implementation:** Phase 2A Complete ✅  
**Testing:** Infrastructure setup complete ✅  
**Next:** Create validation tests

For detailed status, see:
- Implementation: `/STATUS_AND_PLAN.md` (root)
- Architecture: `docs/ARCHITECTURE.md`
- Testing: `docs/testing/README.md`

## Phase Completion

- ✅ Phase 1: Foundation (2026-04-26)
- ✅ Phase 2A: Semantic Search + LLM (2026-04-26)
- 🔄 Phase 2.2: Testing & Validation (in progress)
- 📋 Phase 3+: Architecture Analysis (backlog)

## Documentation Maintenance

**Always Current:**
- `ARCHITECTURE.md` - Updated 2026-05-01
- `testing/` - All new, 2026-05-01
- `STATUS_AND_PLAN.md` (root) - Single source of truth

**May Be Outdated:**
- `ROADMAP.md` - Last updated 2026-04-25
- `QUICKSTART_PHASE2.md` - Check before using
- Other docs: Review date stamps

**When in doubt:** Check `STATUS_AND_PLAN.md` in root directory.
```

---

## Recommendation

### Option A: Minimal Updates (15 min)
1. Update `ROADMAP.md` status section
2. Add testing section to `INDEX.md`
3. Create `DOCS_STATUS.md` as single source

**Benefit:** Quick, establishes single source of truth

### Option B: Comprehensive Review (1 hour)
1. Update all Priority 1 docs
2. Review all Priority 2 docs
3. Update or archive Priority 3 docs

**Benefit:** All docs current, but time-consuming

### Option C: Accept Drift (0 min)
1. Rely on `STATUS_AND_PLAN.md` as single source
2. Update docs only when actively using them
3. Add warning to old docs

**Benefit:** Zero time, but confusing for others

---

## My Recommendation: Option A (15 min)

**Why:**
- `STATUS_AND_PLAN.md` is already your single source of truth
- Just update key navigation docs (ROADMAP, INDEX)
- Create DOCS_STATUS.md to direct people to current info
- Other docs can be updated as needed

**Commands:**
```bash
cd /mnt/c/BACKUP/DEV-TEST/docs

# Create status file
cat > DOCS_STATUS.md << 'EOF'
[Use template above]
EOF

# Update ROADMAP.md status section (manual edit)
# Update INDEX.md with testing section (manual edit)

# Commit
git add ROADMAP.md INDEX.md DOCS_STATUS.md
git commit -m "docs: Update status (Phase 2A complete, testing setup done)"
```

---

## Quick Check Commands

**Find outdated status references:**
```bash
grep -rn "Planning Complete\|Ready for Implementation\|TO IMPLEMENT" docs/
```

**Find references to old phases:**
```bash
grep -rn "Phase 1.*NEW\|Phase 2.*planning" docs/
```

**Check last update dates:**
```bash
for f in docs/*.md; do 
  echo -n "$f: "
  head -5 "$f" | grep -o "202[0-9]-[0-9][0-9]-[0-9][0-9]" | head -1
done
```

---

*Focus on ROADMAP.md and INDEX.md, let STATUS_AND_PLAN.md be the single source of truth*
