---
skill: update-mitre-data
description: Download latest MITRE ATT&CK enterprise-attack.json from official GitHub repository and validate
---

# Update MITRE Data Skill

This skill downloads the latest MITRE ATT&CK enterprise attack dataset from the official MITRE CTI GitHub repository, validates it, backs up the old version, and reminds to regenerate the embedding cache.

## Usage

When user asks to:
- "update MITRE data"
- "download latest ATT&CK"
- "get new MITRE techniques"
- "refresh enterprise-attack"
- "check for MITRE updates"

## What This Does

1. ✅ Downloads latest enterprise-attack.json from MITRE GitHub
2. ✅ Validates JSON structure and size
3. ✅ Backs up old file (with timestamp)
4. ✅ Replaces with new version
5. ✅ Shows summary of changes (file size, technique count)
6. ⚠️  Reminds to regenerate embedding cache

## Implementation

```bash
#!/bin/bash
set -e

REPO_ROOT="/mnt/c/BACKUP/DEV-TEST"
DATA_DIR="$REPO_ROOT/chatbot/data"
MITRE_FILE="enterprise-attack.json"
MITRE_URL="https://raw.githubusercontent.com/mitre/cti/refs/heads/master/enterprise-attack/enterprise-attack.json"
BACKUP_DIR="$DATA_DIR/backups"

cd "$REPO_ROOT"

echo "=================================================="
echo "   MITRE ATT&CK Data Update"
echo "=================================================="
echo

# Create backup directory if needed
mkdir -p "$BACKUP_DIR"

# Check if current file exists
if [ -f "$DATA_DIR/$MITRE_FILE" ]; then
    echo "📦 Backing up current file..."
    BACKUP_NAME="$MITRE_FILE.$(date +%Y%m%d_%H%M%S).bak"
    cp "$DATA_DIR/$MITRE_FILE" "$BACKUP_DIR/$BACKUP_NAME"
    
    # Get old stats
    OLD_SIZE=$(stat -c%s "$DATA_DIR/$MITRE_FILE" 2>/dev/null || stat -f%z "$DATA_DIR/$MITRE_FILE" 2>/dev/null)
    OLD_SIZE_MB=$(echo "scale=2; $OLD_SIZE / 1024 / 1024" | bc)
    
    echo "   ✅ Backed up to: $BACKUP_DIR/$BACKUP_NAME"
    echo "   Old file size: ${OLD_SIZE_MB}MB"
    echo
else
    echo "⚠️  No existing file found (first time setup)"
    echo
fi

# Download latest version
echo "📥 Downloading latest MITRE ATT&CK data..."
echo "   Source: $MITRE_URL"
echo

TMP_FILE=$(mktemp)
if wget -q --show-progress -O "$TMP_FILE" "$MITRE_URL"; then
    echo
    echo "   ✅ Download complete"
else
    echo
    echo "   ❌ Download failed"
    rm -f "$TMP_FILE"
    exit 1
fi

# Validate download
echo
echo "🔍 Validating downloaded file..."

NEW_SIZE=$(stat -c%s "$TMP_FILE" 2>/dev/null || stat -f%z "$TMP_FILE" 2>/dev/null)
NEW_SIZE_MB=$(echo "scale=2; $NEW_SIZE / 1024 / 1024" | bc)

# Check file size is reasonable (should be > 10MB)
if [ "$NEW_SIZE" -lt 10485760 ]; then
    echo "   ❌ File too small (${NEW_SIZE_MB}MB) - likely incomplete download"
    rm -f "$TMP_FILE"
    exit 1
fi

# Validate JSON structure
if ! python3 -c "import json; json.load(open('$TMP_FILE'))" 2>/dev/null; then
    echo "   ❌ Invalid JSON structure"
    rm -f "$TMP_FILE"
    exit 1
fi

echo "   ✅ File size: ${NEW_SIZE_MB}MB"
echo "   ✅ Valid JSON structure"

# Count techniques
TECHNIQUE_COUNT=$(python3 -c "import json; data=json.load(open('$TMP_FILE')); print(len([o for o in data['objects'] if o.get('type')=='attack-pattern']))")
echo "   ✅ Techniques found: $TECHNIQUE_COUNT"

# Move to final location
mv "$TMP_FILE" "$DATA_DIR/$MITRE_FILE"
echo
echo "✅ MITRE ATT&CK data updated successfully!"
echo

# Show changes if we had an old file
if [ -n "$OLD_SIZE" ]; then
    SIZE_DIFF=$(echo "scale=2; $NEW_SIZE_MB - $OLD_SIZE_MB" | bc)
    if (( $(echo "$SIZE_DIFF > 0" | bc -l) )); then
        echo "📊 Changes: +${SIZE_DIFF}MB (data increased)"
    elif (( $(echo "$SIZE_DIFF < 0" | bc -l) )); then
        SIZE_DIFF_ABS=$(echo "$SIZE_DIFF * -1" | bc)
        echo "📊 Changes: -${SIZE_DIFF_ABS}MB (data decreased)"
    else
        echo "📊 Changes: No size change"
    fi
fi

echo
echo "=================================================="
echo "   ⚠️  IMPORTANT: Next Steps"
echo "=================================================="
echo
echo "The MITRE data has been updated, but the embedding"
echo "cache is now out of sync. You MUST regenerate it:"
echo
echo "   python -m chatbot.modules.mitre_embeddings"
echo
echo "Or use the skill:"
echo
echo "   /build-embeddings-cache"
echo
echo "This will take 10-15 minutes (one-time)."
echo
echo "=================================================="
echo
echo "Backup location: $BACKUP_DIR/"
echo "Latest: $BACKUP_DIR/$BACKUP_NAME"
echo "=================================================="
```

## Expected Output

```
==================================================
   MITRE ATT&CK Data Update
==================================================

📦 Backing up current file...
   ✅ Backed up to: chatbot/data/backups/enterprise-attack.json.20260425_123456.bak
   Old file size: 38.45MB

📥 Downloading latest MITRE ATT&CK data...
   Source: https://raw.githubusercontent.com/mitre/cti/...
   ✅ Download complete

🔍 Validating downloaded file...
   ✅ File size: 39.12MB
   ✅ Valid JSON structure
   ✅ Techniques found: 837

✅ MITRE ATT&CK data updated successfully!

📊 Changes: +0.67MB (data increased)

==================================================
   ⚠️  IMPORTANT: Next Steps
==================================================

The MITRE data has been updated, but the embedding
cache is now out of sync. You MUST regenerate it:

   python -m chatbot.modules.mitre_embeddings

Or use the skill:

   /build-embeddings-cache

This will take 10-15 minutes (one-time).

==================================================

Backup location: chatbot/data/backups/
Latest: chatbot/data/backups/enterprise-attack.json.20260425_123456.bak
==================================================
```

## Success Criteria

- ✅ File downloaded successfully
- ✅ File size > 10MB
- ✅ Valid JSON structure
- ✅ Contains attack-pattern objects (techniques)
- ✅ Old file backed up with timestamp
- ✅ New file in place at chatbot/data/enterprise-attack.json

## Failure Handling

**Download fails:**
- Check internet connectivity
- Verify MITRE GitHub is accessible
- Check URL is still valid

**Validation fails:**
- File too small → incomplete download, retry
- Invalid JSON → corrupted download, retry
- No techniques found → wrong file format

**If update fails:**
- Old file remains in place (not deleted)
- Backup is safe in backups/ directory
- Can restore manually if needed

## Post-Update Required Actions

### CRITICAL: Regenerate Embedding Cache
```bash
# Using skill (recommended)
/build-embeddings-cache

# Or directly
python -m chatbot.modules.mitre_embeddings
```

This is **required** because:
- Embedding cache is tied to specific technique descriptions
- New/changed techniques won't be searchable without regeneration
- Takes 10-15 minutes (one-time)

### Optional: Run Tests
```bash
# Verify MITRE data loads correctly
python -c "from chatbot.modules.mitre import MitreHelper; m = MitreHelper(use_local=True); print(f'Loaded {len(m.get_techniques())} techniques')"

# Run full integration tests
python test_openrouter.py
```

## Backup Management

Backups are stored in `chatbot/data/backups/` with timestamp format:
```
enterprise-attack.json.20260425_123456.bak
```

**Cleanup old backups (manual):**
```bash
# Keep only last 5 backups
cd chatbot/data/backups/
ls -t enterprise-attack.json.*.bak | tail -n +6 | xargs rm -f
```

## Update Frequency

MITRE ATT&CK releases updates quarterly:
- Check: https://attack.mitre.org/resources/updates/
- Typical schedule: Q1, Q2, Q3, Q4
- Use this skill when new version announced

## Rollback Procedure

If new version has issues:
```bash
# Restore from backup
cd chatbot/data
cp backups/enterprise-attack.json.YYYYMMDD_HHMMSS.bak enterprise-attack.json

# Verify restoration
python -c "from chatbot.modules.mitre import MitreHelper; m = MitreHelper(use_local=True); print('OK')"

# If embedding cache was already regenerated, you may need to regenerate again
# or restore the old cache if you backed it up
```

## Notes

- ✅ Always backs up old file before replacing
- ✅ Validates download before replacing
- ✅ Safe: old file only deleted after successful validation
- ⚠️  Remember to regenerate embedding cache after update
- 💡 Can check MITRE CTI GitHub for latest changes before running
