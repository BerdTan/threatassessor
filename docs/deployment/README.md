# Deployment Documentation

---
**Last Updated:** 2026-05-02  
**Status:** Current
---

## Quick Links

- **[QUICK_START.md](QUICK_START.md)** - Deploy in 30 minutes
- **[CHECKLIST.md](CHECKLIST.md)** - Complete deployment guide

---

## Deployment Modes

### Development / Testing
```bash
cd /mnt/c/BACKUP/DEV-TEST
source .venv/bin/activate
python3 -m chatbot.main
```

### Production
See [CHECKLIST.md](CHECKLIST.md) for:
- Pre-deployment validation
- Monitoring setup
- Health checks
- Rollback procedures

---

## Pre-Deployment Requirements

### System Validation

**Always run self-test first:**
```bash
python3 -m chatbot.main --self-test

# Expected:
# ✅ 9/9 tests passed
# ✅ System ready for use
# Confidence: 79% (production-ready)
```

### Required Files

✅ `chatbot/data/enterprise-attack.json` (44MB)  
✅ `chatbot/data/technique_embeddings.json` (45MB)  
✅ `.env` with `OPENROUTER_API_KEY`

### System Requirements

- Python 3.8+
- 200MB disk space
- Internet connection (for embedding API)
- Virtual environment configured

---

## Deployment Options

### Option 1: Quick Start (30 minutes)

**Best for:** Development, internal use, demos

**Steps:**
1. Run self-test
2. Setup basic logging
3. Deploy

**Guide:** [QUICK_START.md](QUICK_START.md)

### Option 2: Full Deployment (1 hour)

**Best for:** Production, external users, monitoring

**Steps:**
1. Complete pre-deployment checklist
2. Setup monitoring infrastructure
3. Configure logging
4. Health checks
5. Deploy with monitoring

**Guide:** [CHECKLIST.md](CHECKLIST.md)

---

## Monitoring

### Production Logging

```bash
# Create logs directory
mkdir -p logs

# Logs automatically created:
logs/queries_YYYYMMDD.log
```

### Health Checks

```bash
# Daily self-test
python3 -m chatbot.main --self-test-quiet

# Exit code 0 = healthy
# Exit code 1 = unhealthy
```

### Weekly Analysis

```bash
# Run analysis script
./analyze_logs.sh

# Shows:
# - Total queries
# - Fallback activation rate
# - Top techniques found
```

---

## Configuration

### Environment Variables

```bash
# Required
OPENROUTER_API_KEY=sk-or-v1-xxxxx

# Optional
LOG_LEVEL=INFO  # DEBUG, INFO, WARNING, ERROR
```

### CLI Options

```bash
# Output formats
python3 -m chatbot.main --format executive
python3 -m chatbot.main --format action-plan
python3 -m chatbot.main --format technical

# Validation
python3 -m chatbot.main --self-test

# Non-interactive
python3 -m chatbot.main --query "threat scenario"
```

---

## Troubleshooting

### Deployment Fails: Missing Data

```bash
# Check files
ls -lh chatbot/data/*.json

# Regenerate if needed
python3 -c "from chatbot.modules.mitre_embeddings import build_technique_embeddings, save_embeddings_json; from chatbot.modules.mitre import MitreHelper; mitre = MitreHelper(use_local=True); cache = build_technique_embeddings(mitre); save_embeddings_json(cache)"
```

### Self-Test Fails

See [../SELF_TEST.md](../SELF_TEST.md) for troubleshooting guide

### System Performance

**Slow queries (>10s):**
- Check: Internet connection
- Check: API rate limiting (20 req/min)
- Expected: 2-60s response time (free tier)

---

## Rollback

### If Issues Occur

```bash
# 1. Stop system
# (No background processes in CLI mode)

# 2. Revert to previous version
git revert HEAD
git push origin master

# 3. Redeploy
python3 -m chatbot.main --self-test
python3 -m chatbot.main
```

---

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Deploy MITRE Chatbot

on:
  push:
    branches: [master]

jobs:
  test-and-deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      
      - name: Setup Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.8'
      
      - name: Install dependencies
        run: |
          python -m venv .venv
          source .venv/bin/activate
          pip install -r requirements.txt
      
      - name: Run self-test
        run: |
          source .venv/bin/activate
          python3 -m chatbot.main --self-test-quiet
      
      - name: Deploy (if tests pass)
        if: success()
        run: |
          echo "Deployment steps here"
```

---

## Security Considerations

### API Keys

- ✅ Store in `.env` (never commit)
- ✅ Use environment variables
- ✅ Rotate keys periodically

### Data Files

- ✅ MITRE data is public (safe to commit)
- ❌ Don't commit embedding cache (45MB, regenerate)
- ❌ Don't commit logs (may contain queries)

### User Queries

- ⚠️ Logs may contain sensitive threat scenarios
- ⚠️ Review logs before sharing
- ✅ Anonymize if needed

---

## Performance Tuning

### Expected Performance

- Semantic search: ~2-3 seconds
- With LLM: ~60 seconds (when available)
- Fallback: <1 second

### Optimization

**Not needed for CLI:**
- Single-user, interactive use
- Free tier sufficient

**Future (Web UI):**
- Consider caching
- Implement request queuing
- Use paid tier LLM

---

## Support

### Documentation

- [../../STATUS_AND_PLAN.md](../../STATUS_AND_PLAN.md) - Project status
- [../OPERATIONS.md](../OPERATIONS.md) - Operations guide
- [../SELF_TEST.md](../SELF_TEST.md) - Self-test feature
- [../../CLAUDE.md](../../CLAUDE.md) - Developer guidelines

### Issues

Report issues: GitHub Issues (if public repo)

---

**Deployment Status:** ✅ Ready  
**Confidence:** 79% (production-ready)  
**Validated:** 84.9% accuracy (146 queries)
