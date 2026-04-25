# Maintenance Guide

## Regular Maintenance Tasks

### Updating MITRE ATT&CK Data

**Frequency:** Quarterly (when MITRE releases updates)

**Quick Method:**
```bash
/update-mitre-data
```

This skill will:
1. ✅ Download latest enterprise-attack.json from MITRE GitHub
2. ✅ Validate file size and JSON structure
3. ✅ Backup current file with timestamp
4. ✅ Replace with new version
5. ✅ Show summary of changes
6. ⚠️  Remind to regenerate embedding cache

**After update, you MUST regenerate the embedding cache:**
```bash
/build-embeddings-cache
```

**Manual Update Process:**
```bash
# 1. Download latest version
cd /mnt/c/BACKUP/DEV-TEST
wget -O chatbot/data/enterprise-attack.json.new \
  https://raw.githubusercontent.com/mitre/cti/refs/heads/master/enterprise-attack/enterprise-attack.json

# 2. Validate
python3 -c "import json; data=json.load(open('chatbot/data/enterprise-attack.json.new')); \
  print(f'✅ Valid: {len([o for o in data[\"objects\"] if o.get(\"type\")==\"attack-pattern\"])} techniques')"

# 3. Backup old file
mkdir -p chatbot/data/backups
cp chatbot/data/enterprise-attack.json \
  chatbot/data/backups/enterprise-attack.json.$(date +%Y%m%d_%H%M%S).bak

# 4. Replace
mv chatbot/data/enterprise-attack.json.new chatbot/data/enterprise-attack.json

# 5. Regenerate cache (REQUIRED)
/build-embeddings-cache
```

**Check for Updates:**
- MITRE announcements: https://attack.mitre.org/resources/updates/
- GitHub commits: https://github.com/mitre/cti/commits/master/enterprise-attack
- Typical schedule: March, June, September, December

### Managing Backups

**Location:** `chatbot/data/backups/`

**Format:** `enterprise-attack.json.YYYYMMDD_HHMMSS.bak`

**Cleanup old backups:**
```bash
# List all backups (newest first)
ls -lt chatbot/data/backups/

# Keep only last 5 backups
cd chatbot/data/backups/
ls -t enterprise-attack.json.*.bak | tail -n +6 | xargs rm -f
```

**Restore from backup:**
```bash
# Find backup
ls -lt chatbot/data/backups/

# Restore (replace TIMESTAMP with actual timestamp)
cp chatbot/data/backups/enterprise-attack.json.TIMESTAMP.bak \
   chatbot/data/enterprise-attack.json

# Verify
python3 -c "from chatbot.modules.mitre import MitreHelper; \
  m = MitreHelper(use_local=True); \
  print(f'✅ Restored: {len(m.get_techniques())} techniques')"
```

### Regenerating Embedding Cache

**When to regenerate:**
- ✅ After MITRE data update (REQUIRED)
- ✅ After changing embedding model
- ✅ If cache becomes corrupted
- ✅ If search results seem inaccurate

**Command:**
```bash
/build-embeddings-cache
```

**Time:** 10-15 minutes (rate limited to 20 req/min)

**What it does:**
1. Loads all MITRE techniques
2. Generates embeddings in batches of 3
3. Respects rate limits (automatic pacing)
4. Saves to `chatbot/data/technique_embeddings.json`

**Progress monitoring:**
```bash
# Watch progress in real-time
/build-embeddings-cache

# You'll see:
# - Batch progress (e.g., "Processing batch 50/274")
# - Rate limit stats (e.g., "18/20 requests used")
# - Estimated time remaining
```

### Testing After Updates

**Quick validation:**
```bash
# Run integration tests
/validate-integration
```

**Full test suite:**
```bash
python test_openrouter.py
```

**Test search functionality:**
```bash
python3 -c "
from chatbot.modules.mitre import MitreHelper
m = MitreHelper(use_local=True)
techs = m.get_techniques()
print(f'✅ Loaded {len(techs)} techniques')
print(f'✅ First 3: {[t.get(\"name\") for t in techs[:3]]}')
"
```

## Monitoring and Health Checks

### Check MITRE Data Status

```bash
# File size and modification date
ls -lh chatbot/data/enterprise-attack.json

# Technique count
python3 -c "from chatbot.modules.mitre import MitreHelper; \
  m = MitreHelper(use_local=True); \
  print(f'Techniques: {len(m.get_techniques())}'); \
  print(f'Tactics: {len(m.get_tactics())}'); \
  print(f'Mitigations: {len(m.get_mitigations())}')"
```

### Check Embedding Cache Status

```bash
# Check if cache exists
ls -lh chatbot/data/technique_embeddings.json

# Validate cache
python3 -c "import json; \
  cache = json.load(open('chatbot/data/technique_embeddings.json')); \
  print(f'Cached techniques: {len(cache)}'); \
  sample = list(cache.items())[0]; \
  print(f'Embedding dimensions: {len(sample[1])}')"
```

### Check API Rate Limit Status

```bash
# During operations, check rate limit stats
python3 -c "from chatbot.modules.rate_limiter import get_rate_limit_stats; \
  stats = get_rate_limit_stats(); \
  print(f'Recent requests: {stats[\"recent_requests\"]}/{stats[\"max_requests\"]}'); \
  print(f'Remaining: {stats[\"remaining\"]}')"
```

## Troubleshooting Maintenance Issues

### Update Failed - Download Error

**Symptom:** wget fails or download incomplete

**Solutions:**
1. Check internet connectivity
2. Verify MITRE GitHub is accessible: `curl -I https://github.com/mitre/cti`
3. Try alternative URL: `https://github.com/mitre/cti/raw/master/enterprise-attack/enterprise-attack.json`
4. Download manually via browser, then copy to `chatbot/data/`

### Update Failed - Validation Error

**Symptom:** "File too small" or "Invalid JSON"

**Solutions:**
1. Check downloaded file size: `ls -lh chatbot/data/enterprise-attack.json.new`
2. Validate JSON manually: `python3 -m json.tool chatbot/data/enterprise-attack.json.new > /dev/null`
3. Compare with backup: `diff chatbot/data/enterprise-attack.json chatbot/data/enterprise-attack.json.new`
4. Re-download if corrupted

### Cache Regeneration Stuck

**Symptom:** Process hangs or takes too long (>20 minutes)

**Solutions:**
1. Check rate limit isn't being hit too hard
2. Verify OpenRouter API key is valid
3. Check OpenRouter service status
4. Kill and restart with verbose logging:
   ```bash
   python3 -c "import logging; logging.basicConfig(level=logging.INFO); \
     from chatbot.modules.mitre_embeddings import build_technique_embeddings, save_embeddings_json; \
     # ... rest of command"
   ```

### Search Results Degraded After Update

**Symptom:** Poor or irrelevant results after MITRE update

**Solutions:**
1. Verify embedding cache was regenerated
2. Check cache matches current MITRE data:
   ```bash
   # Technique count should match
   python3 -c "from chatbot.modules.mitre import MitreHelper; import json; \
     m = MitreHelper(use_local=True); \
     cache = json.load(open('chatbot/data/technique_embeddings.json')); \
     print(f'MITRE: {len(m.get_techniques())} vs Cache: {len(cache)}')"
   ```
3. Regenerate cache if counts don't match
4. Test with known queries from docs/TESTING.md

### Disk Space Issues

**Symptom:** "No space left" during updates

**Check usage:**
```bash
df -h chatbot/data/
du -h chatbot/data/
```

**Cleanup:**
```bash
# Remove old backups (keep last 3)
cd chatbot/data/backups/
ls -t enterprise-attack.json.*.bak | tail -n +4 | xargs rm -f

# Remove old embedding cache backups if any
ls -t technique_embeddings.json.*.bak 2>/dev/null | tail -n +4 | xargs rm -f

# Check space again
df -h chatbot/data/
```

## Scheduled Maintenance

**Quarterly (aligned with MITRE releases):**
- ✅ Update MITRE data (`/update-mitre-data`)
- ✅ Regenerate embedding cache (`/build-embeddings-cache`)
- ✅ Run test suite (`/validate-integration`)
- ✅ Review backup storage

**Monthly:**
- ✅ Run integration tests
- ✅ Check rate limit behavior
- ✅ Review logs for errors

**After updates:**
- ✅ Test with standard queries
- ✅ Verify performance unchanged
- ✅ Document any issues

## Version Tracking

**Track MITRE versions in git commits:**
```bash
# After updating MITRE data
git add chatbot/data/enterprise-attack.json
git commit -m "Update MITRE ATT&CK data to v14.1 (2024-10-15)

- Technique count: 823 → 837
- New techniques: T1XXX, T1YYY
- Updated techniques: T1ZZZ
- Source: https://github.com/mitre/cti/commit/abc123"
```

**Document in changelog:**
```markdown
## [2024-10-15] MITRE Update v14.1
- Updated enterprise-attack.json to latest version
- Regenerated embedding cache (837 techniques)
- All tests passing
- Breaking changes: None
```

## Emergency Rollback

**If critical issues after update:**

```bash
# 1. Restore MITRE data from backup
cp chatbot/data/backups/enterprise-attack.json.TIMESTAMP.bak \
   chatbot/data/enterprise-attack.json

# 2. Restore embedding cache backup (if you made one)
cp chatbot/data/backups/technique_embeddings.json.TIMESTAMP.bak \
   chatbot/data/technique_embeddings.json

# 3. Verify system works
/validate-integration

# 4. Document rollback reason
git commit -m "Rollback MITRE update due to [reason]"
```

---

*Last Updated: 2026-04-25*  
*Maintenance Cycle: Quarterly (aligned with MITRE releases)*
