# Phase 2A Testing Guide - Manual Steps

**Estimated Time:** 15-20 minutes (plus 10-15 min for cache generation if needed)  
**Date:** 2026-04-26

---

## Option 1: Automated Testing (Recommended)

Run the automated test script:

```bash
bash run_phase2_tests.sh
```

This script will guide you through all steps automatically.

---

## Option 2: Manual Testing (Step-by-Step)

Follow these steps if you prefer manual control:

---

### Step 1: Activate Virtual Environment (5 seconds)

```bash
cd /mnt/c/BACKUP/DEV-TEST
source .venv/bin/activate
```

**Expected Output:**
```
(.venv) bread@hostname:~$
```

**✓ Success:** You see `(.venv)` prefix in your terminal prompt

---

### Step 2: Install Dependencies (30-60 seconds)

```bash
pip install numpy scikit-learn requests python-dotenv openai
```

**Expected Output:**
```
Successfully installed numpy-1.24.x scikit-learn-1.3.x ...
```

**✓ Success:** All packages install without errors

**Troubleshooting:**
- If "permission denied": Make sure virtual environment is activated (Step 1)
- If "command not found": Use `python3 -m pip install ...` instead

---

### Step 3: Verify API Key (5 seconds)

```bash
cat .env | grep OPENROUTER_API_KEY
```

**Expected Output:**
```
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxxxxxxxxxxxxxx
```

**✓ Success:** You see your API key (should be ~73 characters)

**Troubleshooting:**
- If file not found: Create `.env` file with `echo "OPENROUTER_API_KEY=your_key" > .env`
- If key missing: Add it to `.env` file

---

### Step 4: Test Module Imports (10 seconds)

```bash
python3 -c "
from chatbot.modules.mitre import MitreHelper
from chatbot.modules.embeddings import get_embedding
from chatbot.modules.mitre_embeddings import search_techniques
from chatbot.modules.llm_mitre_analyzer import analyze_scenario
from chatbot.modules.agent import AgentManager
print('✓ All modules imported successfully')
"
```

**Expected Output:**
```
✓ All modules imported successfully
```

**✓ Success:** No import errors

**Troubleshooting:**
- If `ModuleNotFoundError`: Check Step 2 completed successfully
- If syntax error: Make sure you copied the entire command (including quotes)

---

### Step 5: Verify MITRE Data (10 seconds)

```bash
python3 -c "
from chatbot.modules.mitre import MitreHelper
mitre = MitreHelper(use_local=True)
print(f'✓ Loaded {len(mitre.get_techniques())} MITRE techniques')
"
```

**Expected Output:**
```
✓ Loaded 823 MITRE techniques
```

**✓ Success:** Shows ~823 techniques loaded

**Troubleshooting:**
- If file not found: Run `/update-mitre-data` skill first
- If number is different: MITRE data may be newer version (OK)

---

### Step 6: Check Embedding Cache Status (5 seconds)

```bash
ls -lh chatbot/data/technique_embeddings.json 2>&1
```

**Case A - Cache EXISTS:**
```
-rw-r--r-- 1 user user 13M Apr 26 12:00 technique_embeddings.json
```
✓ Skip to Step 8 (cache already built)

**Case B - Cache MISSING:**
```
No such file or directory
```
⚠️ Continue to Step 7 (build cache)

---

### Step 7: Generate Embedding Cache (10-15 minutes, one-time only)

**⚠️ IMPORTANT:** This takes 10-15 minutes due to rate limiting. Only needed once!

```bash
python3 << 'EOF'
from chatbot.modules.mitre import MitreHelper
from chatbot.modules.mitre_embeddings import build_technique_embeddings, save_embeddings_json

print("Starting cache generation...")
print("This will take 10-15 minutes due to rate limiting (20 req/min)")
print("")

mitre = MitreHelper(use_local=True)
cache = build_technique_embeddings(mitre)
save_embeddings_json(cache, 'chatbot/data/technique_embeddings.json')

print("\n✓ Cache generation complete!")
EOF
```

**What You'll See:**
```
Starting cache generation...
This will take 10-15 minutes due to rate limiting (20 req/min)

   ✓ 10/823 techniques embedded (10 success, 0 failed)
   ✓ 20/823 techniques embedded (20 success, 0 failed)
   ⏱️  Rate limit: waiting 61.0s (max 20 req/60s)
   ✓ 30/823 techniques embedded (30 success, 0 failed)
   ...
   ✓ 823/823 techniques embedded (823 success, 0 failed)

✓ Cache saved to chatbot/data/technique_embeddings.json (13.2 MB)
```

**✓ Success:** Cache file created, ~13MB size

**Troubleshooting:**
- If rate limit errors persist: Wait 60 seconds and retry
- If "API key invalid": Check `.env` file has correct key
- Safe to interrupt (Ctrl+C) and resume - cache saves incrementally

---

### Step 8: Run Quick Semantic Search Test (5 seconds)

```bash
python3 << 'EOF'
from chatbot.modules.mitre import MitreHelper
from chatbot.modules.mitre_embeddings import search_techniques

mitre = MitreHelper(use_local=True)
query = "PowerShell script execution"

print(f"Query: '{query}'")
results = search_techniques(query, mitre, top_k=3, min_score=0.5)

print(f"\nTop {len(results)} matches:")
for i, r in enumerate(results, 1):
    print(f"  {i}. {r['external_id']} - {r['name']} (score: {r['similarity_score']:.3f})")
EOF
```

**Expected Output:**
```
Query: 'PowerShell script execution'

Top 3 matches:
  1. T1059.001 - PowerShell (score: 0.856)
  2. T1059.003 - Windows Command Shell (score: 0.723)
  3. T1059 - Command and Scripting Interpreter (score: 0.698)
```

**✓ Success:** Returns relevant techniques with scores >0.5

---

### Step 9: Test LLM Analysis (15 seconds)

```bash
python3 << 'EOF'
from chatbot.modules.mitre import MitreHelper
from chatbot.modules.mitre_embeddings import search_techniques
from chatbot.modules.llm_mitre_analyzer import analyze_scenario

mitre = MitreHelper(use_local=True)
query = "Attacker used PowerShell for malicious execution"

print(f"Query: '{query}'")
print("Running LLM analysis (may take 10-15s)...\n")

matched = search_techniques(query, mitre, top_k=5, min_score=0.3)
analysis = analyze_scenario(query, matched, top_k=3)

print("✓ LLM Analysis Complete\n")
print(f"Refined techniques: {len(analysis['refined_techniques'])}")
print(f"Attack path stages: {len(analysis['attack_path'].get('attack_path', []))}")
print(f"Priority mitigations: {len(analysis['mitigations'].get('priority_mitigations', []))}")

if analysis['refined_techniques']:
    top = analysis['refined_techniques'][0]
    print(f"\nTop technique: {top['external_id']} - {top['name']}")
    print(f"Confidence: {top.get('confidence', 'N/A')}")
EOF
```

**Expected Output:**
```
Query: 'Attacker used PowerShell for malicious execution'
Running LLM analysis (may take 10-15s)...

✓ LLM Analysis Complete

Refined techniques: 3
Attack path stages: 1
Priority mitigations: 5

Top technique: T1059.001 - PowerShell
Confidence: high
```

**✓ Success:** LLM returns refined results with confidence scores

**Troubleshooting:**
- If rate limit errors: Wait 60s and retry
- If empty results: Check API key is valid
- If timeout: Network may be slow, increase timeout in code

---

### Step 10: Test Agent Integration (15 seconds)

```bash
python3 << 'EOF'
from chatbot.modules.agent import AgentManager

agent = AgentManager(use_semantic_search=True)
query = "Attacker used PowerShell to create scheduled tasks"

print(f"Query: '{query}'")
print("Processing...\n")

result = agent.handle_input(query, top_k=3)

print(f"Mode: {result['mode']}")
print(f"Matched techniques: {len(result.get('techniques', []))}")
print(f"Refined techniques: {len(result.get('refined_techniques', []))}")

if result.get('refined_techniques'):
    print("\nTop 3 Techniques:")
    for i, t in enumerate(result['refined_techniques'][:3], 1):
        print(f"  {i}. {t['external_id']} - {t['name']} (score: {t['similarity_score']:.3f})")
EOF
```

**Expected Output:**
```
Query: 'Attacker used PowerShell to create scheduled tasks'
Processing...

Mode: semantic
Matched techniques: 10
Refined techniques: 3

Top 3 Techniques:
  1. T1059.001 - PowerShell (score: 0.856)
  2. T1053.005 - Scheduled Task (score: 0.789)
  3. T1059 - Command and Scripting Interpreter (score: 0.723)
```

**✓ Success:** Agent uses semantic mode and returns refined results

---

### Step 11: Run Comprehensive Test Suite (2-3 minutes)

```bash
python3 test_phase2_semantic_search.py
```

**Expected Output:**
```
========================================================================
Phase 2A: Semantic Search Implementation Test
========================================================================

Test 1: Environment Check
----------------------------------------
✅ PASSED: API key found (73 characters)

Test 2: MITRE Data Loading
----------------------------------------
✅ PASSED: Loaded 823 MITRE techniques

...

========================================================================
TEST SUMMARY
========================================================================

✅ Phase 2A Implementation Complete

Key Components:
  - Embedding cache: ✅ Working
  - Semantic search: ✅ Working
  - LLM analysis: ✅ Working
  - Agent integration: ✅ Working
```

**✓ Success:** All tests pass

---

### Step 12: Interactive CLI Test (Manual)

```bash
python3 chatbot/main.py
```

**What You'll See:**
```
========================================================================
LLM-Enhanced MITRE Attack Path Analyzer
========================================================================

This tool uses semantic search and LLM analysis to map threats
to MITRE ATT&CK techniques and provide mitigation advice.

Describe your threat scenario (e.g., 'Attacker used PowerShell to create scheduled tasks'):
> 
```

**Try These Example Queries:**

1. **PowerShell Execution**
   ```
   Attacker used PowerShell to execute malicious scripts
   ```
   
   **Expected:** T1059.001 ranked highly, execution tactics, PowerShell-specific mitigations

2. **Phishing Attack**
   ```
   Phishing email with malicious Excel macro that downloads and executes payload
   ```
   
   **Expected:** T1566 (Phishing), T1059 (Macro execution), multi-stage attack path

3. **Lateral Movement**
   ```
   Attacker used stolen credentials to access remote systems via RDP
   ```
   
   **Expected:** T1078 (Valid Accounts), T1021 (Remote Services), credential-focused mitigations

4. **Persistence Mechanism**
   ```
   Malware creates scheduled tasks and registry run keys for persistence
   ```
   
   **Expected:** T1053 (Scheduled Task), T1547 (Registry Run Keys), persistence tactics

**What to Look For:**

✓ **Relevance:** Techniques match the scenario  
✓ **Scores:** Similarity scores >0.5 for good matches  
✓ **Explanations:** LLM explains WHY each technique is relevant  
✓ **Attack Path:** Shows logical progression (Initial Access → Execution → Persistence)  
✓ **Mitigations:** Contextual and prioritized recommendations  

---

## Success Criteria Checklist

After completing all steps, verify:

- [ ] All module imports work (Step 4)
- [ ] MITRE data loads successfully (Step 5)
- [ ] Embedding cache exists and loads (Steps 6-7)
- [ ] Semantic search returns relevant results (Step 8)
- [ ] LLM analysis generates refinements (Step 9)
- [ ] Agent integration works in semantic mode (Step 10)
- [ ] Comprehensive test suite passes (Step 11)
- [ ] CLI produces readable, useful output (Step 12)

---

## Common Issues & Solutions

### Issue: "ModuleNotFoundError: No module named 'numpy'"
**Solution:** Run Step 2 again with virtual environment activated

### Issue: "OPENROUTER_API_KEY not found"
**Solution:** Check `.env` file exists and has correct key (Step 3)

### Issue: "Rate limit exceeded (429)"
**Solution:** Wait 60 seconds, this is normal for free tier (20 req/min)

### Issue: "Embedding cache generation too slow"
**Solution:** This is expected (10-15 min). Run once, then cache is reused forever

### Issue: "LLM returns empty results"
**Solution:** Check API key is valid, verify OpenRouter service status

### Issue: "Semantic search returns irrelevant techniques"
**Solution:** Lower min_score threshold (e.g., 0.3 instead of 0.5), or improve query wording

---

## Performance Benchmarks

Expected timings on typical system:

| Operation | Expected Time | Notes |
|-----------|---------------|-------|
| Module imports | <5s | One-time per session |
| MITRE data load | <5s | Cached after first load |
| Cache generation | 10-15 min | **One-time only** |
| Cache loading | <1s | Instant from disk |
| Semantic search | 1-2s | Single query |
| LLM analysis | 10-15s | Full refinement + paths + mitigations |
| Complete CLI query | 15-20s | End-to-end |

---

## Next Steps After Testing

Once all tests pass:

1. **Document any issues found** - Note edge cases or unexpected behavior
2. **Test with real-world scenarios** - Use actual threat intelligence reports
3. **Validate output quality** - Have security team review technique matches
4. **Approve Phase 3 start** - Ready to build Web API + Mermaid parser

---

## Quick Reference Commands

```bash
# Activate environment
source .venv/bin/activate

# Run comprehensive tests
python3 test_phase2_semantic_search.py

# Launch interactive CLI
python3 chatbot/main.py

# Rebuild cache (after MITRE data update)
python3 -c "
from chatbot.modules.mitre import MitreHelper
from chatbot.modules.mitre_embeddings import get_or_build_cache
mitre = MitreHelper(use_local=True)
cache = get_or_build_cache(mitre, force_rebuild=True)
"
```

---

**Testing Guide Version:** 1.0  
**Phase:** 2A (Semantic Search Implementation)  
**Status:** Ready for Testing ✅
