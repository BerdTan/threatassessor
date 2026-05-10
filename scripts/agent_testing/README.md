# Agent Testing Scripts

**Purpose:** Test scripts for Phase 3C agent framework validation

**Location:** `scripts/agent_testing/`

---

## Available Scripts

### test_architect.sh

**Purpose:** Test Architect critic agent on flawed assessment

**Usage:**
```bash
./scripts/agent_testing/test_architect.sh
```

**What it does:**
1. Sets up test data from `tests/data/agent_test_cases/test_flawed_assessment.json`
2. Runs Architect agent: `python3 -m chatbot.modules.architect_critic test_flawed_assessment`
3. Saves results to: `report/test_flawed_assessment/04_architect_critique.json`

**Expected Results:**
- Score: 20-35/100 (POOR)
- Gap: Ransomware rationale contradiction (backup)
- Gap: DoS priority mismatch (risk=80, priority=low)
- Gap: App Vulns coverage gap (risk=90, 1 technique)

---

## Future Scripts (MVP2-5)

### test_tester.sh (MVP2)
Test Tester agent on flawed assessment
- Should catch all validation failures
- Should reference Architect roadmap findings

### test_red_teamer.sh (MVP3)
Test Red Teamer agent on easy-to-breach assessment
- Should identify exploitable weaknesses
- Should rate attack difficulty

### test_orchestrator.sh (MVP4)
Test Orchestrator managing all 3 agents
- Should aggregate scores (30/30/40 weights)
- Should consolidate improvements
- Should calculate confidence boost

### test_all_agents.sh (MVP5)
Run full agent suite on multiple test cases
- Good assessment (should score high)
- Flawed assessment (should score low)
- Edge cases (various failure modes)

---

## Related Documentation

- **Test Data:** `tests/data/agent_test_cases/README.md`
- **Agent Framework:** `chatbot/modules/agent_framework.py`
- **Architect Agent:** `chatbot/modules/architect_critic.py`
- **MVP1 Summary:** `docs/phases/PHASE3C_MVP1_SUMMARY.md`

---

**Last Updated:** 2026-05-10 (MVP1)
