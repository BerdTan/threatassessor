# Commit Rules - Documentation Organization

---
**Purpose:** Maintain clean, organized, secure repository  
**Applies To:** All commits, especially documentation  
**Status:** Active
---

## Before Every Commit: Checklist

### 1. Documentation Organization ✅

**Root directory (keep minimal):**
```bash
# Should only contain:
- README.md          ✅ Main entry point
- CLAUDE.md          ✅ Developer guidelines  
- STATUS_AND_PLAN.md ✅ Living status document

# Everything else goes in subdirectories
```

**Check:**
```bash
ls *.md | wc -l
# Expected: 3 (README, CLAUDE, STATUS_AND_PLAN)
# If more: Move to appropriate subdirectory
```

---

### 2. No Duplicates ✅

**Check for duplicate files:**
```bash
# Find files with same name
find . -name "*.md" -type f | grep -v ".venv" | grep -v "node_modules" | sort | uniq -c | grep -v "^\s*1 "

# Expected: No output (all unique)
# If duplicates: Keep one, delete others
```

**Check for duplicate content:**
```bash
# Manual review of similar filenames:
# - TESTING.md vs TESTING_GUIDE.md
# - README.md in multiple directories
# - Summary vs Status vs Plan documents
```

---

### 3. No Sensitive Data ✅

**Check for API keys:**
```bash
# Check for real keys
grep -r "sk-or-v1-[a-zA-Z0-9]" --include="*.md" . | grep -v "xxxxx"

# Expected: No matches
# If found: Replace with placeholder (sk-or-v1-xxxxx)
```

**Check for passwords:**
```bash
grep -ri "password\s*=" --include="*.md" .
grep -ri "secret\s*=" --include="*.md" .

# Expected: No matches or only in documentation examples
```

**Check for personal info:**
```bash
# Email addresses
grep -E "[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}" --include="*.md" -r .

# Expected: Only public/example addresses
# Remove: Personal emails, internal addresses
```

---

### 4. Proper File Location ✅

**Documentation structure:**
```
Root/
├── README.md, CLAUDE.md, STATUS_AND_PLAN.md only
│
docs/
├── ARCHITECTURE.md, OPERATIONS.md, SELF_TEST.md, etc.
├── deployment/          # Deployment guides
├── specs/               # Requirements, specifications
├── testing/             # Testing methodology
└── archive/             # Historical documents

tests/
├── README.md            # Test suite overview
├── test_*.py            # Test code
├── results/             # Test results by phase
│   └── phase2.2/
└── [analysis docs]      # TEST_DATA_ASSESSMENT.md, FALLBACK_ANALYSIS.md

archive/
├── session-notes/       # Session summaries, working docs
└── test-results/        # Historical test results
```

**Verify location:**
```bash
# Check: No session notes in docs/
ls docs/*.md | grep -i "session\|summary\|complete"
# Expected: No matches

# Check: No implementation notes in docs/
ls docs/*.md | grep -i "implementation"
# Expected: No matches (should be in archive/)
```

---

### 5. Update Tracking ✅

**Add to each document:**
```markdown
---
**Last Updated:** YYYY-MM-DD
**Status:** Current | Archived | Superseded
**Superseded By:** [link if applicable]
---
```

**Update STATUS_AND_PLAN.md:**
```markdown
## Documentation Updates

- YYYY-MM-DD: Brief description of changes
```

**Check:**
```bash
# Verify all docs in docs/ have update dates
for file in docs/*.md; do
    if ! grep -q "Last Updated" "$file"; then
        echo "Missing date: $file"
    fi
done
```

---

### 6. File Size Check ✅

**Check for oversized docs:**
```bash
# Find large markdown files (>50KB)
find docs/ tests/ -name "*.md" -size +50k -exec ls -lh {} \;

# If found: Consider splitting or moving to archive
```

**Total size:**
```bash
# Calculate total markdown size
find . -name "*.md" -type f | grep -v ".venv" | xargs du -ch | tail -1

# Target: <1MB for active docs (excluding archive/)
```

---

### 7. Cross-Reference Check ✅

**Verify links:**
```bash
# Check for broken links (manual review)
grep -h "\[.*\](.*\.md)" docs/*.md tests/README.md README.md

# Verify paths exist
# Update if files moved
```

**Common patterns:**
```bash
# Relative links from docs/
../README.md
../STATUS_AND_PLAN.md
../CLAUDE.md

# Relative links from tests/
../docs/testing/
../README.md

# Relative links from root
docs/ARCHITECTURE.md
tests/README.md
```

---

## Commit Message Format

### Structure

```
type: Brief description

## Context
Why this change was made

## Changes
- File moved: from → to
- File deleted: reason
- File created: purpose

## Impact
- Documentation: cleaner/updated
- Tests: [if applicable]
- Breaking changes: [if any]

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>
```

### Types

- `docs:` - Documentation changes
- `test:` - Test code/data changes
- `feat:` - New feature
- `fix:` - Bug fix
- `refactor:` - Code restructuring
- `chore:` - Maintenance (dependencies, etc.)

---

## Pre-Commit Script (Optional)

Create `.git/hooks/pre-commit`:

```bash
#!/bin/bash

echo "Running pre-commit checks..."

# 1. Check for sensitive data
if grep -r "sk-or-v1-[a-zA-Z0-9]" --include="*.md" . | grep -v "xxxxx"; then
    echo "❌ ERROR: Real API key found in markdown files"
    exit 1
fi

# 2. Check root directory
ROOT_MDS=$(ls *.md 2>/dev/null | grep -v "README.md\|CLAUDE.md\|STATUS_AND_PLAN.md" | wc -l)
if [ "$ROOT_MDS" -gt 0 ]; then
    echo "⚠️  WARNING: Extra markdown files in root directory"
    ls *.md | grep -v "README.md\|CLAUDE.md\|STATUS_AND_PLAN.md"
    echo "Consider moving to docs/ or tests/"
fi

# 3. Check for large files
LARGE_FILES=$(find docs/ tests/ -name "*.md" -size +100k 2>/dev/null)
if [ -n "$LARGE_FILES" ]; then
    echo "⚠️  WARNING: Large markdown files found:"
    echo "$LARGE_FILES"
fi

echo "✅ Pre-commit checks complete"
exit 0
```

Make executable:
```bash
chmod +x .git/hooks/pre-commit
```

---

## Post-Commit Actions

### 1. Update STATUS_AND_PLAN.md

Add entry to documentation updates section:
```markdown
## Documentation Updates

- 2026-05-02: Reorganized docs, moved session notes to archive
- [previous entries]
```

### 2. Verify GitHub

After push, verify on GitHub:
- [ ] Files in correct locations
- [ ] No sensitive data visible
- [ ] Links work in web UI
- [ ] README renders correctly

---

## Special Cases

### Working Documents (Session Notes)

**During development:**
- Can create in root for easy access
- Named: `WORKING_*.md` or `SESSION_*.md`

**Before commit:**
- Move to `archive/session-notes/`
- Rename to include date: `phase2.2-summary-2026-05-02.md`

### Test Results

**Temporary results:**
- Keep in `tests/` during active testing
- Named: `TEMP_*.md` or `DEBUG_*.md`

**Before commit:**
- Consolidate into `tests/results/phaseX.Y/summary.md`
- Delete temporary files
- Keep only permanent reference docs

### Implementation Notes

**During feature development:**
- Document in root: `FEATURE_NAME_IMPLEMENTATION.md`

**After feature complete:**
- Move to `archive/session-notes/`
- Extract permanent docs to appropriate location

---

## Common Mistakes to Avoid

### ❌ Don't

1. **Commit working docs to root**
   ```
   ❌ FINAL_SUMMARY.md
   ❌ IMPLEMENTATION_NOTES.md
   ❌ SESSION_COMPLETE.md
   ```

2. **Leave duplicates**
   ```
   ❌ tests/TESTING.md + tests/TESTING_GUIDE.md
   ❌ TEST_DATA_ASSESSMENT.md in two locations
   ```

3. **Commit sensitive data**
   ```
   ❌ Real API keys (sk-or-v1-abc123...)
   ❌ Personal emails
   ❌ Internal URLs
   ```

4. **Create unclear structure**
   ```
   ❌ docs/implementation/session-notes/
   ❌ tests/docs/guides/
   ```

### ✅ Do

1. **Use clear hierarchy**
   ```
   ✅ docs/deployment/CHECKLIST.md
   ✅ docs/testing/STRATEGY.md
   ✅ tests/results/phase2.2/summary.md
   ```

2. **Consolidate duplicates**
   ```
   ✅ Merge TESTING.md + TESTING_GUIDE.md → tests/README.md
   ✅ One TEST_DATA_ASSESSMENT.md in tests/
   ```

3. **Use placeholders**
   ```
   ✅ sk-or-v1-xxxxx
   ✅ user@example.com
   ✅ https://example.com
   ```

4. **Archive working docs**
   ```
   ✅ archive/session-notes/phase2.2-summary.md
   ✅ archive/session-notes/self-test-implementation.md
   ```

---

## Quick Reference

### Before Commit Checklist

```bash
# 1. Root directory clean?
ls *.md | wc -l  # Expected: 3

# 2. No duplicates?
find . -name "*.md" | sort | uniq -c | grep -v "^\s*1 "

# 3. No secrets?
grep -r "sk-or-v1-[a-zA-Z0-9]" --include="*.md" . | grep -v "xxxxx"

# 4. Files in right place?
# Manual review of ls docs/ tests/

# 5. Update dates added?
grep -L "Last Updated" docs/*.md

# 6. STATUS_AND_PLAN.md updated?
tail -20 STATUS_AND_PLAN.md  # Check for new entry
```

### Target Structure

```
Root: 3 markdown files (README, CLAUDE, STATUS_AND_PLAN)
docs/: ~15 permanent reference documents
tests/: ~10 files (README + test code + 2-3 analysis docs)
archive/: Historical documents (excluded from main navigation)

Total active: ~30 files
Total with archive: ~70 files
```

---

## Enforcement

### Pull Request Review

Before merging:
- [ ] Run all checklist items above
- [ ] Verify file organization
- [ ] Check for sensitive data
- [ ] Confirm links work
- [ ] Review commit message

### Continuous

- Monthly: Review and archive old docs
- Quarterly: Consolidate duplicate content
- Per release: Update all "Last Updated" dates

---

**Commit Rules Version:** 1.0  
**Last Updated:** 2026-05-02  
**Status:** Active  
**Review Schedule:** Monthly
