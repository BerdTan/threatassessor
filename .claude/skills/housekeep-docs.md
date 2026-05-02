---
skill: housekeep-docs
description: Perform comprehensive documentation housekeeping - cleanup, deduplication, security checks, and organization validation
---

# Documentation Housekeeping Skill

This skill performs the complete documentation housekeeping regime established in `.github/COMMIT_RULES.md`.

**Trigger words:** cleanup, housekeep, organize docs, clean documentation, pre-commit check

---

## What This Skill Does

Performs 7-point pre-commit validation checklist:

1. **Documentation Organization** - Root should have exactly 3 .md files
2. **No Duplicates** - Find duplicate filenames and content
3. **No Sensitive Data** - Check for API keys, passwords, personal info
4. **Proper File Location** - Verify files in correct directories
5. **Update Tracking** - Check "Last Updated" dates present
6. **File Size Check** - Flag oversized docs (>50KB)
7. **Cross-Reference Check** - Verify links not broken

---

## Usage

When user asks to:
- "clean up documentation"
- "housekeep the docs"
- "organize markdown files"
- "prepare for commit"
- "run pre-commit checks"
- "validate documentation structure"

---

## Implementation Steps

### Step 1: Root Directory Check (2 min)

**Expected:** Only 3 files (README.md, CLAUDE.md, STATUS_AND_PLAN.md)

```bash
cd /mnt/c/BACKUP/DEV-TEST
echo "=== ROOT MARKDOWN FILES ==="
ls -1 *.md 2>/dev/null
COUNT=$(ls *.md 2>/dev/null | wc -l)
echo "Count: $COUNT (expected: 3)"

if [ "$COUNT" -ne 3 ]; then
    echo "⚠️  WARNING: Root has $COUNT markdown files (expected 3)"
    echo "Extra files should be moved to:"
    echo "  - docs/ (permanent reference)"
    echo "  - tests/ (test documentation)"
    echo "  - archive/session-notes/ (working notes)"
    ls *.md | grep -v "README.md\|CLAUDE.md\|STATUS_AND_PLAN.md"
fi
```

**Action if fails:** Move extra files to appropriate subdirectories.

---

### Step 2: Duplicate Detection (3 min)

**Check A: Duplicate filenames**

```bash
echo "=== CHECKING FOR DUPLICATE FILENAMES ==="
find . -name "*.md" -type f | grep -v ".venv\|node_modules\|\.git" | \
    awk -F'/' '{print $NF}' | sort | uniq -c | grep -v "^\s*1 "

# Expected: No output (all unique)
```

**Check B: Similar content (manual review)**

```bash
echo "=== CHECKING FOR SIMILAR FILENAMES ==="
find . -name "*.md" -type f | grep -v ".venv\|archive" | sort
echo ""
echo "Review for patterns like:"
echo "  - TESTING.md vs TESTING_GUIDE.md"
echo "  - README.md in multiple directories"
echo "  - Summary vs Status vs Plan documents"
```

**Action if duplicates found:**
1. Compare content of duplicates
2. Keep the most comprehensive/up-to-date version
3. Move older version to `archive/session-notes/` with date suffix
4. Update cross-references

---

### Step 3: Sensitive Data Check (2 min)

**Check A: Real API keys**

```bash
echo "=== CHECKING FOR REAL API KEYS ==="
grep -r "sk-or-v1-[a-zA-Z0-9]" --include="*.md" . 2>/dev/null | \
    grep -v "xxxxx\|example\|placeholder" | \
    grep -v ".venv\|archive"

# Expected: No matches
```

**Check B: Passwords and secrets**

```bash
echo "=== CHECKING FOR PASSWORDS/SECRETS ==="
grep -ri "password\s*=" --include="*.md" . 2>/dev/null | grep -v ".venv\|archive"
grep -ri "secret\s*=" --include="*.md" . 2>/dev/null | grep -v ".venv\|archive"

# Expected: No matches or only in documentation examples
```

**Check C: Personal information**

```bash
echo "=== CHECKING FOR EMAIL ADDRESSES ==="
grep -rE "[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}" \
    --include="*.md" . 2>/dev/null | \
    grep -v "example.com\|noreply@\|.venv\|archive"

# Expected: Only public/example addresses
```

**Action if sensitive data found:**
1. Replace real API keys with `sk-or-v1-xxxxx`
2. Replace real emails with `user@example.com`
3. Remove passwords/secrets completely
4. Check if file should be in .gitignore

---

### Step 4: File Location Validation (3 min)

**Check directory structure:**

```bash
echo "=== VALIDATING FILE LOCATIONS ==="
echo ""
echo "Root (should be 3 files):"
ls -1 *.md 2>/dev/null | wc -l

echo ""
echo "docs/ (permanent reference):"
ls docs/*.md 2>/dev/null | wc -l

echo ""
echo "tests/ (test documentation):"
ls tests/*.md 2>/dev/null | wc -l

echo ""
echo "archive/ (historical):"
find archive/ -name "*.md" 2>/dev/null | wc -l
```

**Expected structure:**

```
Root/                              3 files (README, CLAUDE, STATUS_AND_PLAN)
docs/                              ~15 files (permanent reference)
├── deployment/                    3 files
└── testing/                       3 files
tests/                             3-5 files (README + analysis docs)
└── results/phase2.2/              3 files
archive/                           40+ files (historical)
└── session-notes/                 session summaries
```

**Check for misplaced files:**

```bash
echo "=== CHECKING FOR MISPLACED FILES ==="
echo ""
echo "Session notes in docs/ (should be in archive/):"
ls docs/*.md 2>/dev/null | grep -i "session\|summary\|complete\|notes"

echo ""
echo "Implementation notes in docs/ (should be in archive/):"
ls docs/*.md 2>/dev/null | grep -i "implementation"

echo ""
echo "Test results in root (should be in tests/results/):"
ls *.md 2>/dev/null | grep -i "test\|result\|validation"
```

**Action if misplaced:**
- Session notes → `archive/session-notes/`
- Test results → `tests/results/phaseX.Y/`
- Implementation notes → `archive/session-notes/`

---

### Step 5: Update Tracking (2 min)

**Check for "Last Updated" dates:**

```bash
echo "=== CHECKING UPDATE DATES ==="
echo ""
echo "Files in docs/ without 'Last Updated' date:"
for file in docs/*.md docs/*/*.md; do
    if [ -f "$file" ] && ! grep -q "Last Updated" "$file"; then
        echo "  Missing: $file"
    fi
done

echo ""
echo "Files in tests/ without 'Last Updated' date (excluding scripts):"
for file in tests/*.md; do
    if [ -f "$file" ] && ! grep -q "Last Updated\|Status:" "$file"; then
        echo "  Missing: $file"
    fi
done
```

**Action if missing:**
1. Add frontmatter to each doc:
```markdown
---
**Last Updated:** YYYY-MM-DD  
**Status:** Current | Archived | Superseded
---
```

2. Update STATUS_AND_PLAN.md documentation log:
```markdown
## Documentation Updates

- YYYY-MM-DD: Brief description of changes
```

---

### Step 6: File Size Check (1 min)

**Check for oversized documents:**

```bash
echo "=== CHECKING FILE SIZES ==="
echo ""
echo "Large markdown files (>50KB):"
find docs/ tests/ -name "*.md" -size +50k -exec ls -lh {} \; 2>/dev/null

echo ""
echo "Total active docs size (excluding archive/):"
find . -name "*.md" -type f | \
    grep -v ".venv\|node_modules\|archive" | \
    xargs du -ch 2>/dev/null | tail -1
```

**Expected:** 
- Individual files: <50KB each
- Total active docs: <1MB (excluding archive/)

**Action if oversized:**
- Consider splitting large docs into multiple focused docs
- Move very detailed/historical content to archive/
- Extract code examples into separate files

---

### Step 7: Cross-Reference Check (3 min)

**Extract all markdown links:**

```bash
echo "=== CHECKING CROSS-REFERENCES ==="
echo ""
echo "Markdown links in key docs:"
grep -h "\[.*\](.*\.md)" README.md CLAUDE.md STATUS_AND_PLAN.md \
    docs/README.md tests/README.md 2>/dev/null | \
    grep -o "([^)]*\.md)" | sort -u
```

**Manual verification required:**
1. Check if linked files exist
2. Verify relative paths are correct
3. Update links if files were moved

**Common link patterns:**

```bash
# From root/
docs/ARCHITECTURE.md
tests/README.md
.github/COMMIT_RULES.md

# From docs/
../README.md
../STATUS_AND_PLAN.md
../tests/README.md
deployment/CHECKLIST.md

# From tests/
../docs/testing/TESTING_STRATEGY.md
../README.md
results/phase2.2/summary.md
```

---

## Final Report

After all checks, generate summary:

```bash
echo ""
echo "=== HOUSEKEEPING SUMMARY ==="
echo ""
echo "✅ Documentation organization: [PASS/FAIL]"
echo "✅ Duplicate detection: [PASS/FAIL]"
echo "✅ Sensitive data check: [PASS/FAIL]"
echo "✅ File locations: [PASS/FAIL]"
echo "✅ Update tracking: [PASS/FAIL]"
echo "✅ File sizes: [PASS/FAIL]"
echo "✅ Cross-references: [PASS/FAIL]"
echo ""
echo "Status: [READY FOR COMMIT / NEEDS ATTENTION]"
```

---

## Quick Housekeeping (Fast Version - 2 min)

For quick checks before minor commits:

```bash
cd /mnt/c/BACKUP/DEV-TEST

# Quick 4-point check
echo "1. Root files:"
ls -1 *.md 2>/dev/null | wc -l  # Expected: 3

echo "2. No secrets:"
grep -r "sk-or-v1-[a-zA-Z0-9]" --include="*.md" . 2>/dev/null | \
    grep -v "xxxxx" | wc -l  # Expected: 0

echo "3. Recent updates:"
tail -20 STATUS_AND_PLAN.md | grep "Documentation Updates" -A 5

echo "4. Git status:"
git status --short
```

---

## Automated Housekeeping Script

Create `.github/scripts/housekeep.sh`:

```bash
#!/bin/bash
# Automated documentation housekeeping
# Usage: .github/scripts/housekeep.sh [--quick]

set -e
cd "$(git rev-parse --show-toplevel)"

# Source: .github/COMMIT_RULES.md
# Version: 1.0

QUICK_MODE=${1:-""}

if [ "$QUICK_MODE" = "--quick" ]; then
    echo "Running quick housekeeping checks..."
    # Run checks 1-3 only
else
    echo "Running full housekeeping regime..."
    # Run all 7 checks
fi

# Implementation of all 7 checks above
# Exit code 0 = pass, 1 = needs attention
```

---

## Post-Housekeeping Actions

### If All Checks Pass

```bash
# Update STATUS_AND_PLAN.md
echo "- $(date +%Y-%m-%d): Documentation housekeeping complete" >> STATUS_AND_PLAN.md

# Commit if changes made
git add -A
git commit -m "docs: Documentation housekeeping

- Validated organization (3 root files)
- No duplicates found
- No sensitive data
- All files properly located
- Update tracking current
- File sizes acceptable
- Cross-references validated

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

### If Checks Fail

1. Fix issues identified in each check
2. Re-run housekeeping skill
3. Repeat until all checks pass

---

## Success Criteria

**Ready for commit when:**
- ✅ Root has exactly 3 .md files
- ✅ No duplicate filenames or content
- ✅ No sensitive data in markdown files
- ✅ All files in correct locations (docs/, tests/, archive/)
- ✅ All docs have "Last Updated" dates
- ✅ No files >100KB (50KB warning threshold)
- ✅ Cross-references verified working
- ✅ STATUS_AND_PLAN.md updated with documentation changes

---

## References

- **[.github/COMMIT_RULES.md](../../.github/COMMIT_RULES.md)** - Complete commit rules
- **[docs/README.md](../../docs/README.md)** - Documentation structure
- **[STATUS_AND_PLAN.md](../../STATUS_AND_PLAN.md)** - Project status

---

**Skill Version:** 1.0  
**Last Updated:** 2026-05-02  
**Estimated Time:** 15-20 minutes (full) | 2 minutes (quick)
