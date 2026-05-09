---
skill: housekeep-docs
description: Proactively organize, cleanup, and secure documentation - moves files, redacts secrets, consolidates duplicates
---

# Documentation Housekeeping Skill (Proactive)

**IMPORTANT:** This skill actively reorganizes files, not just reporting issues.

**Trigger words:** cleanup, housekeep, organize docs, clean documentation, pre-commit check

---

## What This Skill Does

Performs 9-point proactive housekeeping with automatic fixes:

1. **Root Organization** - Move extra files to proper locations
2. **Docs Subfolder Structure** - Organize docs/ with clear subfolders
3. **Archive Old Files** - Move obsolete docs to archive/
4. **Consolidate Duplicates** - Merge or remove duplicate content
5. **Redact Sensitive Data** - Auto-redact API keys, passwords
6. **Remove Dead Files** - Delete unused/superseded files
7. **Update Tracking** - Add "Last Updated" metadata
8. **Size Management** - Split oversized docs
9. **Cross-Reference Fix** - Update broken links

---

## Documentation Structure (Target State)

```
Root/                                   3 files only
├── README.md                          Quick start
├── CLAUDE.md                          System instructions
└── STATUS_AND_PLAN.md                 Current status

docs/                                   Organized by category
├── README.md                          Documentation map
├── core/                              Core system docs
│   ├── V1_FEATURES.md
│   ├── CONFIDENCE_METHODOLOGY.md
│   ├── PREVENTION_VS_MITIGATION.md
│   └── REFERENCE_ARCHITECTURES.md
├── operations/                        Day-to-day operations
│   ├── OPERATIONS.md
│   ├── TROUBLESHOOTING.md
│   └── MAINTENANCE.md
├── development/                       Development guides
│   ├── ARCHITECTURE.md
│   ├── TESTING_STRATEGY.md
│   └── CONTRIBUTION_GUIDE.md
├── phases/                            Implementation phases
│   ├── PHASE3B_IMPROVEMENTS.md
│   ├── PHASE3B_DIAGRAM_PLACEMENT.md
│   ├── PHASE3C_OVERVIEW.md
│   └── ROADMAP_TO_95_CONFIDENCE.md
└── specs/                             Specifications
    └── MVP_SPECIFICATION.md

tests/                                  Test docs only
├── README.md
└── data/
    └── architectures/README.md

archive/                                Historical only
├── session-notes/                     Session summaries
├── obsolete-features/                 Removed features
└── implementation-notes/              Implementation history
```

---

## Step 1: Root Directory Cleanup (PROACTIVE)

### Check
```bash
cd /mnt/c/BACKUP/DEV-TEST
echo "=== ROOT CLEANUP ==="
ls -1 *.md 2>/dev/null
EXTRA=$(ls *.md 2>/dev/null | grep -v "README.md\|CLAUDE.md\|STATUS_AND_PLAN.md")
```

### Action: Move Extra Files Automatically
```bash
if [ -n "$EXTRA" ]; then
    echo "Moving extra files from root..."
    for file in $EXTRA; do
        case $file in
            *HOUSEKEEPING*|*SUMMARY*)
                echo "  → archive/session-notes/$file"
                mv "$file" "archive/session-notes/"
                ;;
            *TESTING*|*TEST*)
                echo "  → docs/development/$file"
                mkdir -p docs/development
                mv "$file" "docs/development/"
                ;;
            *PHASE*|*ROADMAP*)
                echo "  → docs/phases/$file"
                mkdir -p docs/phases
                mv "$file" "docs/phases/"
                ;;
            *)
                echo "  → archive/session-notes/$file (unknown category)"
                mv "$file" "archive/session-notes/"
                ;;
        esac
    done
    echo "✅ Root cleaned: 3 files remain"
fi
```

---

## Step 2: Organize docs/ Subdirectories (PROACTIVE)

### Create Standard Structure
```bash
echo "=== ORGANIZING docs/ STRUCTURE ==="
mkdir -p docs/{core,operations,development,phases,specs}
```

### Move Files to Proper Locations
```bash
# Core system documentation
for file in V1_FEATURES CONFIDENCE_METHODOLOGY PREVENTION_VS_MITIGATION REFERENCE_ARCHITECTURES; do
    if [ -f "docs/${file}.md" ]; then
        mv "docs/${file}.md" "docs/core/"
        echo "  ✓ Moved ${file}.md to core/"
    fi
done

# Operations
for file in OPERATIONS TROUBLESHOOTING MAINTENANCE; do
    if [ -f "docs/${file}.md" ]; then
        mv "docs/${file}.md" "docs/operations/"
        echo "  ✓ Moved ${file}.md to operations/"
    fi
done

# Development
for file in ARCHITECTURE TESTING_STRATEGY CONTRIBUTION_GUIDE; do
    if [ -f "docs/${file}.md" ]; then
        mv "docs/${file}.md" "docs/development/"
        echo "  ✓ Moved ${file}.md to development/"
    fi
done

# Phases
for file in docs/PHASE*.md docs/ROADMAP*.md; do
    if [ -f "$file" ]; then
        mv "$file" "docs/phases/"
        echo "  ✓ Moved $(basename $file) to phases/"
    fi
done

# Implementation notes → archive
if [ -d "docs/implementation" ]; then
    echo "  ⚠️  Moving docs/implementation/ to archive/"
    mv docs/implementation archive/implementation-notes-$(date +%Y%m%d)
fi
```

---

## Step 3: Archive Obsolete Files (PROACTIVE)

### Identify Obsolete Files
```bash
echo "=== ARCHIVING OBSOLETE FILES ==="

# Files with "OBSOLETE" or "DEPRECATED" in name or content
find docs/ -name "*.md" -type f | while read file; do
    if grep -q "OBSOLETE\|DEPRECATED\|Superseded" "$file" 2>/dev/null; then
        echo "  → archive/obsolete-features/$(basename $file)"
        mkdir -p archive/obsolete-features
        mv "$file" "archive/obsolete-features/"
    fi
done

# Old backtest/implementation results (keep latest only)
find docs/ -name "*BACKTEST*" -o -name "*IMPLEMENTATION_STATUS*" | while read file; do
    if [ -f "$file" ]; then
        DATE=$(stat -c %y "$file" | cut -d' ' -f1)
        DAYS_OLD=$(( ($(date +%s) - $(date -d "$DATE" +%s)) / 86400 ))
        if [ $DAYS_OLD -gt 30 ]; then
            echo "  → archive/obsolete-features/$(basename $file) (${DAYS_OLD} days old)"
            mkdir -p archive/obsolete-features
            mv "$file" "archive/obsolete-features/"
        fi
    fi
done
```

### Files to Always Archive
```bash
# These are always historical after phase completion
ALWAYS_ARCHIVE=(
    "BACKTEST_RESULTS.md"
    "DYNAMIC_CONTROL_LIMITS.md"
    "ORPHAN_NODE_DETECTION.md"
    "DIAGRAM_PLACEMENT_IMPROVEMENTS.md"
)

for file in "${ALWAYS_ARCHIVE[@]}"; do
    if [ -f "docs/$file" ]; then
        echo "  → archive/session-notes/$file"
        mv "docs/$file" "archive/session-notes/"
    fi
done
```

---

## Step 4: Consolidate Duplicates (PROACTIVE)

### Find Duplicate Content
```bash
echo "=== CONSOLIDATING DUPLICATES ==="

# Example: Multiple QUICK_START files
QUICK_STARTS=($(find docs/ -name "*QUICK*START*.md" 2>/dev/null))
if [ ${#QUICK_STARTS[@]} -gt 1 ]; then
    echo "  Found ${#QUICK_STARTS[@]} QUICK_START variants:"
    for file in "${QUICK_STARTS[@]}"; do
        echo "    - $file"
    done
    
    # Keep most comprehensive, archive others
    LARGEST=$(ls -S "${QUICK_STARTS[@]}" | head -1)
    echo "  ✓ Keeping: $LARGEST (largest)"
    
    for file in "${QUICK_STARTS[@]}"; do
        if [ "$file" != "$LARGEST" ]; then
            echo "  → archive/session-notes/$(basename $file)"
            mv "$file" "archive/session-notes/"
        fi
    done
fi

# Example: Multiple README files (keep strategic ones)
# Root README: keep
# docs/README: keep (documentation map)
# tests/README: keep (test guide)
# All others → archive
find docs/ -mindepth 2 -name "README.md" | grep -v "docs/README.md\|tests/README.md" | while read file; do
    echo "  → archive/obsolete-features/README_$(dirname $file | tr '/' '_').md"
    mv "$file" "archive/obsolete-features/README_$(dirname $file | tr '/' '_').md"
done
```

---

## Step 5: Redact Sensitive Data (PROACTIVE)

### Auto-Redact API Keys
```bash
echo "=== REDACTING SENSITIVE DATA ==="

# Find and redact API keys in markdown files
find docs/ -name "*.md" -type f | while read file; do
    # OpenRouter keys
    if grep -q "sk-or-v1-[a-zA-Z0-9]\{10,\}" "$file" 2>/dev/null; then
        if ! grep -q "xxxxx" "$file"; then
            echo "  ⚠️  Found API key in $file - redacting..."
            sed -i 's/sk-or-v1-[a-zA-Z0-9]\{10,\}/sk-or-v1-xxxxx/g' "$file"
            echo "  ✓ Redacted"
        fi
    fi
    
    # AWS/Bedrock keys
    if grep -q "[A-Z0-9]\{20,\}" "$file" 2>/dev/null; then
        if grep -q "AWS.*KEY\|BEDROCK.*KEY" "$file"; then
            echo "  ⚠️  Found potential AWS key in $file - manual review needed"
        fi
    fi
    
    # Passwords in config examples
    if grep -q "PASSWORD=.*[^_here]$" "$file" 2>/dev/null; then
        echo "  ⚠️  Found password in $file - sanitizing..."
        sed -i 's/PASSWORD=.*/PASSWORD=your_secure_password_here/g' "$file"
        echo "  ✓ Sanitized"
    fi
done
```

---

## Step 6: Remove Dead Files (PROACTIVE)

### Remove Empty or Stub Files
```bash
echo "=== REMOVING DEAD FILES ==="

# Files with less than 10 lines (likely stubs)
find docs/ -name "*.md" -type f | while read file; do
    LINES=$(wc -l < "$file")
    if [ $LINES -lt 10 ]; then
        echo "  ⚠️  $file is only $LINES lines - moving to archive"
        mv "$file" "archive/obsolete-features/"
    fi
done

# Files that are just "TODO" or "TBD"
find docs/ -name "*.md" -type f -exec grep -l "^TODO\|^TBD\|Coming soon" {} \; | while read file; do
    if [ $(wc -l < "$file") -lt 20 ]; then
        echo "  → archive/obsolete-features/$(basename $file) (stub file)"
        mv "$file" "archive/obsolete-features/"
    fi
done
```

### Remove Superseded Files
```bash
# Known superseded files
SUPERSEDED=(
    "chatbot/modules/diagram_completeness_validator.py"
    "docs/OLD_*.md"
    "docs/*_DEPRECATED.md"
)

for pattern in "${SUPERSEDED[@]}"; do
    for file in $pattern; do
        if [ -f "$file" ]; then
            echo "  🗑️  Removing superseded: $file"
            rm "$file"
        fi
    done
done
```

---

## Step 7: Update Tracking (PROACTIVE)

### Add Missing Metadata
```bash
echo "=== ADDING UPDATE TRACKING ==="

find docs/core docs/operations docs/development docs/phases -name "*.md" -type f | while read file; do
    if ! grep -q "Last Updated\|Date:" "$file"; then
        echo "  Adding metadata to $file..."
        
        # Get file modification date
        MOD_DATE=$(stat -c %y "$file" | cut -d' ' -f1)
        
        # Add frontmatter if missing
        if ! head -1 "$file" | grep -q "^---"; then
            TITLE=$(basename "$file" .md | tr '_' ' ')
            cat > "${file}.tmp" << EOF
---
**Title:** $TITLE
**Last Updated:** $MOD_DATE
**Status:** Current
---

EOF
            cat "$file" >> "${file}.tmp"
            mv "${file}.tmp" "$file"
            echo "  ✓ Added metadata"
        fi
    fi
done
```

---

## Step 8: Size Management (PROACTIVE)

### Split Oversized Documents
```bash
echo "=== CHECKING FILE SIZES ==="

# Warn about files >50KB
find docs/ -name "*.md" -size +50k | while read file; do
    SIZE=$(du -h "$file" | cut -f1)
    echo "  ⚠️  Large file: $file ($SIZE)"
    echo "      Consider splitting into multiple focused documents"
    echo "      Or moving detailed content to archive/"
done

# Auto-split if >100KB (implement splitting logic as needed)
find docs/ -name "*.md" -size +100k | while read file; do
    SIZE=$(du -h "$file" | cut -f1)
    echo "  ❌ Oversized: $file ($SIZE)"
    echo "      MUST be split or archived before commit"
done
```

---

## Step 9: Cross-Reference Fix (PROACTIVE)

### Update Broken Links
```bash
echo "=== FIXING CROSS-REFERENCES ==="

# Common moves that break links
declare -A MOVED_FILES=(
    ["docs/PHASE3B_IMPROVEMENTS.md"]="docs/phases/PHASE3B_IMPROVEMENTS.md"
    ["docs/OPERATIONS.md"]="docs/operations/OPERATIONS.md"
    ["docs/V1_FEATURES.md"]="docs/core/V1_FEATURES.md"
)

# Update references in all markdown files
for old_path in "${!MOVED_FILES[@]}"; do
    new_path="${MOVED_FILES[$old_path]}"
    
    # Find files that reference the old path
    grep -rl "$old_path" --include="*.md" . 2>/dev/null | while read file; do
        echo "  Updating links in $file..."
        sed -i "s|$old_path|$new_path|g" "$file"
    done
done

# Update relative path references
find docs/ -name "*.md" -type f -exec grep -l "\.\./docs/" {} \; | while read file; do
    echo "  Fixing relative paths in $file..."
    # If file is now in docs/subdir/, update ../docs/ to ../
    SUBDIR=$(dirname "$file" | grep -o "docs/[^/]*")
    if [ -n "$SUBDIR" ]; then
        sed -i 's|\.\./docs/|../|g' "$file"
    fi
done
```

---

## Final Report & Commit Preparation

### Generate Summary
```bash
echo ""
echo "=== HOUSEKEEPING SUMMARY ==="
echo ""
echo "Root files: $(ls *.md 2>/dev/null | wc -l) (expected: 3)"
echo "docs/ structure:"
echo "  core/: $(find docs/core -name "*.md" 2>/dev/null | wc -l) files"
echo "  operations/: $(find docs/operations -name "*.md" 2>/dev/null | wc -l) files"
echo "  development/: $(find docs/development -name "*.md" 2>/dev/null | wc -l) files"
echo "  phases/: $(find docs/phases -name "*.md" 2>/dev/null | wc -l) files"
echo "  specs/: $(find docs/specs -name "*.md" 2>/dev/null | wc -l) files"
echo ""
echo "Archived: $(find archive/ -name "*.md" -type f | wc -l) files"
echo "Total active docs: $(find . -name "*.md" | grep -v ".venv\|archive\|report" | wc -l)"
echo ""

# Check if ready for commit
ISSUES=0

if [ $(ls *.md 2>/dev/null | wc -l) -ne 3 ]; then
    echo "❌ Root directory has extra files"
    ISSUES=$((ISSUES+1))
fi

if grep -r "sk-or-v1-[a-zA-Z0-9]\{10,\}" --include="*.md" docs/ 2>/dev/null | grep -v "xxxxx"; then
    echo "❌ Found unredacted API keys"
    ISSUES=$((ISSUES+1))
fi

if [ $ISSUES -eq 0 ]; then
    echo "✅ Status: READY FOR COMMIT"
    echo ""
    echo "Next: Review changes with 'git status' and commit"
else
    echo "⚠️  Status: $ISSUES ISSUES FOUND - review above"
fi
```

### Update Documentation Map
```bash
echo "Updating docs/README.md with new structure..."
cat > docs/README.md << 'EOF'
# Documentation Map

**Last Updated:** $(date +%Y-%m-%d)

## Quick Links

- **[Quick Start](../README.md)** - Get started in 5 minutes
- **[System Instructions](../CLAUDE.md)** - How to work with this system
- **[Current Status](../STATUS_AND_PLAN.md)** - Project status and roadmap

---

## Core Documentation

**Essential reading for understanding the system:**

- **[V1 Features](core/V1_FEATURES.md)** - Complete feature set and capabilities
- **[Confidence Methodology](core/CONFIDENCE_METHODOLOGY.md)** - 6-factor confidence scoring
- **[Prevention + DIR Framework](core/PREVENTION_VS_MITIGATION.md)** - Defense-in-depth approach
- **[Reference Architectures](core/REFERENCE_ARCHITECTURES.md)** - Validation benchmarks

---

## Operations

**Day-to-day usage and maintenance:**

- **[Operations Guide](operations/OPERATIONS.md)** - Running the system
- **[Troubleshooting](operations/TROUBLESHOOTING.md)** - Common issues and fixes
- **[Maintenance](operations/MAINTENANCE.md)** - Updates and upkeep

---

## Development

**For contributors and developers:**

- **[Architecture](development/ARCHITECTURE.md)** - System architecture
- **[Testing Strategy](development/TESTING_STRATEGY.md)** - Test approach
- **[Contribution Guide](development/CONTRIBUTION_GUIDE.md)** - How to contribute

---

## Phases

**Implementation history and future plans:**

- **[Phase 3B Improvements](phases/PHASE3B_IMPROVEMENTS.md)** - Confidence to 99.1%
- **[Phase 3B+ Diagram Placement](phases/PHASE3B_DIAGRAM_PLACEMENT.md)** - Visual improvements
- **[Phase 3C Overview](phases/PHASE3C_OVERVIEW.md)** - LLM as Judge (next)
- **[Roadmap to 95% Confidence](phases/ROADMAP_TO_95_CONFIDENCE.md)** - Future improvements

---

## Specifications

**Detailed specs for features:**

- **[MVP Specification](specs/MVP_SPECIFICATION.md)** - Web UI specification

---

## File Organization Rules

```
docs/
├── core/              Essential system documentation (rarely changes)
├── operations/        Day-to-day operations (updates quarterly)
├── development/       Developer guides (updates as needed)
├── phases/            Implementation phases (append-only)
└── specs/             Feature specifications (version-controlled)
```

**Archive rules:**
- Session notes → `archive/session-notes/`
- Obsolete features → `archive/obsolete-features/`
- Implementation history → `archive/implementation-notes/`

---

**Total active docs:** $(find . -name "*.md" | grep -v ".venv\|archive\|report" | wc -l)  
**Archive size:** $(find archive/ -name "*.md" | wc -l) files
EOF
```

---

## Success Criteria (After Housekeeping)

**✅ Ready when:**
- Root has exactly 3 .md files
- docs/ organized into 5 subdirectories (core, operations, development, phases, specs)
- No sensitive data in any .md files
- No files >100KB (warning at >50KB)
- All active docs have "Last Updated" metadata
- docs/README.md reflects current structure
- Old/obsolete files moved to archive/
- Cross-references updated for moved files

---

## Usage Examples

### Full Housekeeping (Before Phase Commit)
```bash
# User says: "housekeep docs"
# Claude runs all 9 steps, moves files, redacts secrets, updates structure
# Reports final status and what was changed
```

### Quick Check (Daily)
```bash
# User says: "quick cleanup"
# Claude runs steps 1, 5, 9 only (root, secrets, links)
# Fast validation without major reorganization
```

---

## References

- **Root:** README.md, CLAUDE.md, STATUS_AND_PLAN.md
- **Archive policy:** Files >30 days old moved to archive/
- **Size limits:** 50KB warning, 100KB hard limit

---

**Skill Version:** 2.0 (Proactive)  
**Last Updated:** 2026-05-09  
**Changes:** Now actively moves/fixes files instead of just reporting
