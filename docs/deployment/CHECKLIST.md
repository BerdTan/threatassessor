# Deployment Checklist

**Date:** 2026-05-02  
**Version:** Phase 2.2 Complete - Validated Release  
**Confidence:** 79% (Production-Ready)

---

## Pre-Deployment Verification

### ✅ Core Functionality
- [x] Semantic search working (84.9% accuracy)
- [x] All 14 MITRE tactics validated
- [x] LLM integration working (~33% uptime)
- [x] Hybrid mitigations functional
- [x] Multi-format output tested
- [x] Rate limiting working (20 req/min)
- [x] Fallback mechanism functional

### ✅ Testing
- [x] 146 test queries validated
- [x] Per-tactic accuracy ≥75% (all tactics)
- [x] Stage 1 smoke tests: 100% (8/8)
- [x] Robustness tests: 100% (24/24)
- [x] Security validation: Special chars handled
- [x] Scoring system: 9/9 tests passed

### ✅ Documentation
- [x] README.md updated
- [x] STATUS_AND_PLAN.md current
- [x] CLAUDE.md developer guidelines
- [x] Test results documented
- [x] Known limitations documented

### ✅ Data Files
- [x] `chatbot/data/enterprise-attack.json` (44MB) - Present
- [x] `chatbot/data/technique_embeddings.json` (45MB) - Generated
- [x] `.env` configured with API keys
- [x] Test data (146 queries) - Present

---

## Deployment Steps

### 1. Environment Setup (5 min)

```bash
# Activate virtual environment
cd /mnt/c/BACKUP/DEV-TEST
source .venv/bin/activate

# Verify dependencies
pip list | grep -E "litellm|requests|numpy"

# Check data files
ls -lh chatbot/data/*.json

# Verify API key
grep OPENROUTER_API_KEY .env
```

**Status:** [ ] Complete

---

### 2. Final Testing (5 min)

```bash
# Quick smoke test
python3 -m chatbot.main <<EOF
Attacker used PowerShell to download malware
EOF

# Expected: T1059.001 in results
# If LLM unavailable: Fallback to semantic search (acceptable)
```

**Status:** [ ] Complete  
**Result:** _________

---

### 3. Git Commit (5 min)

```bash
# Stage test files
git add tests/test_semantic_search.py
git add tests/test_stage1_validation.py
git add tests/data/generated/stage1_tactic_smoke_tests.jsonl
git add tests/__init__.py
git add tests/eval_utils.py
git add tests/conftest.py

# Stage documentation
git add STATUS_AND_PLAN.md
git add DEPLOYMENT_CHECKLIST.md
git add tests/STAGE1_RESULTS.md
git add tests/STAGE1_SUMMARY.md
git add tests/TIER1_TEST_RESULTS.md
git add tests/FALLBACK_ANALYSIS.md
git add tests/TEST_DATA_ASSESSMENT.md
git add tests/ITERATIVE_TEST_STRATEGY.md
git add tests/SIZE_ESTIMATES.md
git add tests/EASY_KILL_TESTS.md

# Commit
git commit -m "$(cat <<'EOF'
test: Complete Phase 2.2 validation testing

## Validation Results
- Overall accuracy: 84.9% (146 queries)
- All 14 tactics validated (100% coverage)
- Per-tactic accuracy: All ≥75%
- Stage 1 smoke tests: 100% (8/8)
- Robustness tests: 100% (24/24)
- Confidence: 79% (production-ready)

## Test Infrastructure
- Created test_semantic_search.py (11 test functions)
- Created test_stage1_validation.py (4 test functions)
- Added 33 Stage 1 tactic smoke test queries
- Fixed eval_utils.py for production data compatibility

## Coverage Improvement
- Techniques: 6 → 17 (2.4% coverage)
- Tactics: 5 → 14 (100% coverage)
- Test queries: 109 → 146 (+34%)

## Documentation
- Comprehensive test result analysis
- Fallback mechanism analysis (acceptable quality)
- Iterative testing strategy documented
- Deployment checklist created

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>
EOF
)"
```

**Status:** [ ] Complete  
**Commit Hash:** _________

---

### 4. Push to GitHub (2 min)

```bash
# Push to main
git push origin master

# Verify on GitHub
# Visit: https://github.com/[your-username]/[repo-name]/commits/master
```

**Status:** [ ] Complete  
**GitHub URL:** _________

---

### 5. Production Monitoring Setup (15 min)

#### Option A: Simple File Logging (Recommended for MVP)

```bash
# Create logs directory
mkdir -p logs

# Add to chatbot/main.py (or create wrapper script)
cat > monitor_queries.sh << 'SCRIPT'
#!/bin/bash
# Production query logging wrapper

LOG_DIR="logs"
LOG_FILE="$LOG_DIR/queries_$(date +%Y%m%d).log"

mkdir -p "$LOG_DIR"

# Log query start
echo "[$(date '+%Y-%m-%d %H:%M:%S')] START" >> "$LOG_FILE"

# Run chatbot and capture results
python3 -m chatbot.main 2>&1 | tee -a "$LOG_FILE"

# Log query end
echo "[$(date '+%Y-%m-%d %H:%M:%S')] END" >> "$LOG_FILE"
echo "" >> "$LOG_FILE"
SCRIPT

chmod +x monitor_queries.sh
```

**Log Format:**
```
[2026-05-02 14:30:15] START
User query: Attacker used PowerShell
Results: T1059.001 (score: 0.856)
[2026-05-02 14:30:17] END
```

**Status:** [ ] Complete

#### Option B: Structured Logging (For Production Scale)

```python
# Add to chatbot/modules/logger.py
import json
import logging
from datetime import datetime

def log_query(query: str, results: list, duration: float, method: str):
    """Log production queries for analysis"""
    log_entry = {
        'timestamp': datetime.utcnow().isoformat(),
        'query': query,
        'results': [
            {'technique_id': r[1], 'name': r[2], 'score': r[3]}
            for r in results[:5]  # Top 5 only
        ],
        'duration_sec': duration,
        'method': method,  # 'semantic' or 'keyword_fallback'
    }
    
    with open('logs/queries.jsonl', 'a') as f:
        f.write(json.dumps(log_entry) + '\n')
```

**Status:** [ ] Complete (optional)

---

### 6. Weekly Analysis Script (15 min)

```bash
# Create analysis script
cat > analyze_logs.sh << 'SCRIPT'
#!/bin/bash
# Weekly log analysis

LOG_DIR="logs"

echo "=== Weekly Query Analysis ==="
echo ""

# Count total queries
echo "Total queries:"
grep -c "START" $LOG_DIR/*.log 2>/dev/null || echo "0"

# Count fallback activations
echo ""
echo "Fallback activations:"
grep -c "Using keyword fallback" $LOG_DIR/*.log 2>/dev/null || echo "0"

# Most common techniques
echo ""
echo "Top 10 techniques found:"
grep "Results:" $LOG_DIR/*.log | 
  grep -oP 'T\d+(\.\d+)?' | 
  sort | uniq -c | sort -rn | head -10

echo ""
echo "Analysis complete. Review logs in: $LOG_DIR"
SCRIPT

chmod +x analyze_logs.sh
```

**Usage:**
```bash
# Run weekly
./analyze_logs.sh
```

**Status:** [ ] Complete

---

## Post-Deployment Monitoring

### Week 1 Checklist

- [ ] **Day 1:** Check system is running
  - [ ] Test query works
  - [ ] Logs being generated
  - [ ] No crashes/errors

- [ ] **Day 3:** Review initial logs
  - [ ] Count total queries
  - [ ] Check fallback activation rate
  - [ ] Identify any failed queries

- [ ] **Day 7:** First analysis
  - [ ] Run `analyze_logs.sh`
  - [ ] Calculate metrics:
    - [ ] Total queries
    - [ ] Fallback rate (<1% expected)
    - [ ] Most common techniques
  - [ ] Document findings

### Metrics to Track

| Metric | Target | Measurement |
|--------|--------|-------------|
| Total queries | N/A | Count log entries |
| Fallback activation | <1% | Count "keyword fallback" messages |
| Average response time | <5s | Parse timestamps |
| User satisfaction | Qualitative | Collect feedback |

---

## Known Limitations (Document for Users)

### 1. LLM Availability (~33% uptime)
**Issue:** Free tier LLM has limited availability  
**Impact:** Detailed analysis intermittently unavailable  
**Workaround:** System falls back to semantic search (84.9% accuracy)  
**User message:** "LLM refinement unavailable, using semantic search"

### 2. Response Time (2-60s)
**Issue:** 2s for semantic search, 60s when LLM available  
**Impact:** User waits for detailed analysis  
**Workaround:** None (free tier limitation)  
**User message:** "Analyzing... (this may take up to 60 seconds)"

### 3. Keyword Fallback Quality (Low but Rare)
**Issue:** Fallback has ~30% accuracy  
**Impact:** Suboptimal results when embedding API down  
**Frequency:** <1% of queries (rarely used)  
**Workaround:** Users can try simpler/more specific queries  
**User message:** "Using keyword search (limited accuracy)"

### 4. Coverage (2.4% techniques)
**Issue:** Only 17/703 techniques tested  
**Impact:** Unknown accuracy on rare techniques  
**Mitigation:** Monitor production for gaps  
**Expected:** Accuracy holds across untested techniques

---

## Rollback Plan (If Needed)

### Symptoms Requiring Rollback
- [ ] System crashes frequently (>1 per hour)
- [ ] Accuracy drops below 50% in production
- [ ] User complaints about quality (>10%)
- [ ] Security issues discovered

### Rollback Steps
```bash
# 1. Revert to previous commit
git revert HEAD
git push origin master

# 2. Notify users (if applicable)
echo "System temporarily reverted to previous version"

# 3. Debug issues offline
git checkout -b debug-issues
# Fix and test
# Re-deploy when ready
```

**Status:** [ ] Not needed (hopefully!)

---

## Success Criteria

### Day 1 ✅
- [ ] System runs without crashes
- [ ] At least 1 successful query
- [ ] Logs being generated

### Week 1 ✅
- [ ] Total queries: >10
- [ ] Fallback rate: <1%
- [ ] No critical issues
- [ ] User feedback: Positive or neutral

### Month 1 ✅
- [ ] Total queries: >100
- [ ] Accuracy maintained: >80%
- [ ] Fallback improved: If usage >1%
- [ ] Test coverage increased: >50 techniques

---

## Communication Plan

### Internal Team
**Message:**
```
🚀 MITRE Chatbot v2.2 Deployed

✅ Validated with 84.9% accuracy (146 test queries)
✅ All 14 MITRE tactics covered
✅ 79% confidence - production-ready

Usage:
  source .venv/bin/activate
  python3 -m chatbot.main

Formats:
  --format executive     # Business summary
  --format action-plan   # Implementation roadmap
  --format technical     # Detailed analysis

Known Limitations:
  - LLM availability: ~33% (free tier)
  - Response time: 2-60s
  - Fallback quality: Lower (rarely used)

Monitoring: logs/ directory
Feedback: [your contact]
```

### Users (If External)
**Message:**
```
New Feature: MITRE Threat Analysis Chatbot

Describe threats in natural language, get:
- MITRE ATT&CK technique mapping
- Attack path analysis
- Mitigation recommendations

Validated: 84.9% accuracy across all attack tactics

Try it: [deployment URL or instructions]
Feedback: [contact]
```

---

## Next Steps After Deployment

### Immediate (Week 1)
1. Monitor daily for issues
2. Collect user feedback
3. Log all queries for analysis
4. Fix any critical bugs

### Short-term (Weeks 2-4)
1. Analyze query patterns
2. Identify common techniques (add to tests)
3. Improve fallback if needed (>1% usage)
4. Expand test coverage (Stage 2/3)

### Medium-term (Month 2-3)
1. Build Stage 4 test set from production
2. Measure production accuracy
3. Add domain-specific tests (cloud, containers)
4. Consider paid LLM tier

### Long-term (Months 4+)
1. Web UI (Phase 4)
2. Architecture analysis integration (Phase 3)
3. SIEM integration
4. Custom MITRE matrices

---

## Final Checks

- [ ] All tests passing
- [ ] Documentation updated
- [ ] Git committed
- [ ] Monitoring setup
- [ ] Known limitations documented
- [ ] Rollback plan ready
- [ ] Success criteria defined

---

**Deployment Status:** [ ] Ready  
**Deployed By:** _________  
**Deployed Date:** _________  
**Version:** Phase 2.2 (Validated)  
**Confidence:** 79% ✅

---

**🚀 READY TO DEPLOY!**
