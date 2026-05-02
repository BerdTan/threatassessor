#!/bin/bash
# Automated documentation housekeeping
# Usage: .github/scripts/housekeep.sh [--quick]
# Version: 1.0
# Source: .github/COMMIT_RULES.md

cd "$(git rev-parse --show-toplevel)" || exit 1

QUICK_MODE=${1:-""}
PASS=0
FAIL=0

echo "========================================"
echo "Documentation Housekeeping"
echo "========================================"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Helper functions
check_pass() {
    echo -e "${GREEN}✅ PASS${NC}: $1"
    ((PASS++))
}

check_fail() {
    echo -e "${RED}❌ FAIL${NC}: $1"
    ((FAIL++))
}

check_warn() {
    echo -e "${YELLOW}⚠️  WARN${NC}: $1"
}

# ========================================
# CHECK 1: Root Directory Organization
# ========================================
echo "CHECK 1: Root directory organization"
ROOT_COUNT=$(ls *.md 2>/dev/null | wc -l)

if [ "$ROOT_COUNT" -eq 3 ]; then
    check_pass "Root has exactly 3 markdown files"
else
    check_fail "Root has $ROOT_COUNT files (expected 3)"
    echo "  Expected: README.md, CLAUDE.md, STATUS_AND_PLAN.md"
    echo "  Found:"
    ls -1 *.md 2>/dev/null | sed 's/^/    /'
    echo "  Extra files should be moved to docs/, tests/, or archive/"
fi
echo ""

# ========================================
# CHECK 2: Duplicate Detection
# ========================================
echo "CHECK 2: Duplicate detection"
DUPLICATES=$(find . -name "*.md" -type f | \
    grep -v ".venv\|node_modules\|\.git\|_codex\|\.archive\|\.pytest_cache" | \
    awk -F'/' '{print $NF}' | sort | uniq -c | grep -v "^\s*1 " | wc -l || echo "0")

# Filter out expected duplicates (README.md in multiple dirs is normal)
REAL_DUPLICATES=$(find . -name "*.md" -type f | \
    grep -v ".venv\|node_modules\|\.git\|_codex\|\.archive\|\.pytest_cache\|/archive/" | \
    awk -F'/' '{print $NF}' | sort | uniq -c | grep -v "^\s*1 " | \
    grep -v "README.md" | wc -l || echo "0")

if [ "$REAL_DUPLICATES" -eq 0 ]; then
    check_pass "No duplicate filenames found"
else
    check_fail "Found $REAL_DUPLICATES duplicate filename(s)"
    echo "  Duplicates:"
    find . -name "*.md" -type f | \
        grep -v ".venv\|node_modules\|\.git\|_codex\|\.archive\|\.pytest_cache\|/archive/" | \
        awk -F'/' '{print $NF}' | sort | uniq -c | grep -v "^\s*1 " | \
        grep -v "README.md" | sed 's/^/    /'
fi
echo ""

# ========================================
# CHECK 3: Sensitive Data
# ========================================
echo "CHECK 3: Sensitive data check"

# Real API keys
API_KEYS=$(grep -r "sk-or-v1-[a-zA-Z0-9]" --include="*.md" . 2>/dev/null | \
    grep -v "xxxxx\|example\|placeholder\|abc123\|.venv\|archive\|_codex\|COMMIT_RULES" | wc -l || echo "0")

if [ "$API_KEYS" -eq 0 ]; then
    check_pass "No real API keys found"
else
    check_fail "Found $API_KEYS real API key(s)"
    echo "  Replace with placeholder: sk-or-v1-xxxxx"
fi

# Passwords
PASSWORDS=$(grep -ri "password\s*=" --include="*.md" . 2>/dev/null | \
    grep -v ".venv\|archive\|example" | wc -l || echo "0")

if [ "$PASSWORDS" -eq 0 ]; then
    check_pass "No passwords found"
else
    check_warn "Found $PASSWORDS password reference(s) - review manually"
fi

echo ""

# ========================================
# CHECK 4: File Locations (Quick Mode Skip)
# ========================================
if [ "$QUICK_MODE" != "--quick" ]; then
    echo "CHECK 4: File location validation"

    # Check for session notes in docs/
    SESSION_NOTES=$(ls docs/*.md 2>/dev/null | grep -i "session\|summary\|complete\|notes" | wc -l || echo "0")

    if [ "$SESSION_NOTES" -eq 0 ]; then
        check_pass "No session notes in docs/"
    else
        check_fail "Found $SESSION_NOTES session note(s) in docs/"
        echo "  Move to archive/session-notes/"
        ls docs/*.md 2>/dev/null | grep -i "session\|summary\|complete\|notes" | sed 's/^/    /'
    fi

    echo ""
fi

# ========================================
# CHECK 5: Update Tracking (Quick Mode Skip)
# ========================================
if [ "$QUICK_MODE" != "--quick" ]; then
    echo "CHECK 5: Update tracking"

    MISSING_DATES=0
    for file in docs/*.md docs/*/*.md; do
        if [ -f "$file" ] && ! grep -q "Last Updated" "$file"; then
            ((MISSING_DATES++))
        fi
    done

    if [ "$MISSING_DATES" -eq 0 ]; then
        check_pass "All docs have 'Last Updated' dates"
    else
        check_warn "$MISSING_DATES doc(s) missing 'Last Updated' date"
    fi

    echo ""
fi

# ========================================
# CHECK 6: File Size (Quick Mode Skip)
# ========================================
if [ "$QUICK_MODE" != "--quick" ]; then
    echo "CHECK 6: File size check"

    LARGE_FILES=$(find docs/ tests/ -name "*.md" -size +50k 2>/dev/null | wc -l || echo "0")

    if [ "$LARGE_FILES" -eq 0 ]; then
        check_pass "No oversized files (>50KB)"
    else
        check_warn "Found $LARGE_FILES file(s) >50KB"
        echo "  Large files:"
        find docs/ tests/ -name "*.md" -size +50k -exec ls -lh {} \; 2>/dev/null | \
            awk '{print "    " $9 " (" $5 ")"}'
        echo "  Consider splitting or moving to archive/"
    fi

    echo ""
fi

# ========================================
# CHECK 7: STATUS_AND_PLAN.md Updated
# ========================================
echo "CHECK 7: STATUS_AND_PLAN.md documentation log"

if grep -q "Documentation Updates" STATUS_AND_PLAN.md 2>/dev/null; then
    RECENT_UPDATE=$(grep -A 1 "Documentation Updates" STATUS_AND_PLAN.md | tail -1 | grep "$(date +%Y-%m)" || echo "")

    if [ -n "$RECENT_UPDATE" ]; then
        check_pass "STATUS_AND_PLAN.md has recent update entry"
    else
        check_warn "No documentation update logged this month"
        echo "  Add entry to STATUS_AND_PLAN.md:"
        echo "  - $(date +%Y-%m-%d): [description]"
    fi
else
    check_fail "STATUS_AND_PLAN.md missing 'Documentation Updates' section"
fi

echo ""

# ========================================
# SUMMARY
# ========================================
echo "========================================"
echo "SUMMARY"
echo "========================================"
echo ""
echo -e "Passed: ${GREEN}$PASS${NC}"
echo -e "Failed: ${RED}$FAIL${NC}"
echo ""

if [ "$FAIL" -eq 0 ]; then
    echo -e "${GREEN}✅ READY FOR COMMIT${NC}"
    echo ""
    echo "Next steps:"
    echo "  1. git add -A"
    echo "  2. git commit -m 'docs: [description]'"
    echo "  3. git push origin master"
    exit 0
else
    echo -e "${RED}❌ NEEDS ATTENTION${NC}"
    echo ""
    echo "Fix issues above and re-run housekeeping"
    exit 1
fi
