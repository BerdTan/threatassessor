# Agent Test Cases

**Purpose:** Test data for Phase 3C agent framework validation

**Location:** `tests/data/agent_test_cases/`

---

## Structure

```
tests/data/
├── architectures/           # Real architecture .mmd files for threat analysis
│   ├── 01_minimal_vulnerable.mmd
│   ├── 02_minimal_defended.mmd
│   └── ...
├── agent_test_cases/        # Synthetic test data for agent validation (YOU ARE HERE)
│   ├── test_flawed_assessment.json
│   └── README.md
├── generated/               # Auto-generated test outputs
└── ground_truth/            # Pre-generated ground truth files
```

---

## Test Cases

### 1. test_flawed_assessment.json

**Purpose:** Validate that critic agents catch quality issues

**Type:** Deliberately flawed threat assessment (synthetic, not from real architecture)

**Planted Flaws (3 total):**

1. **Logic Contradiction (Ransomware)**
   - `rapids_assessment.ransomware.rationale`: "Low risk - we have backups"
   - `controls_missing`: ["backup", "edr", "logging", ...]
   - **Expected:** Architect/Tester catches contradiction

2. **Risk-Priority Mismatch (DoS)**
   - `rapids_assessment.dos.risk`: 80/100 (HIGH)
   - `control_recommendations[0].priority`: "low" (for rate limiting)
   - **Expected:** Architect/Tester catches priority misalignment

3. **Coverage Gap (Application Vulnerabilities)**
   - `rapids_assessment.application_vulns.risk`: 90/100 (VERY HIGH)
   - `expected_attack_paths`: Only 1 technique (T1190)
   - **Expected:** Architect/Tester catches insufficient technique coverage

**Validation Results:**

| Agent | Score | Key Findings |
|-------|-------|--------------|
| **Architect** | 23/100 (POOR) | Caught all 3 flaws + design gaps |
| **Tester** | TBD (MVP2) | Should catch flaws + validation failures |
| **Red Teamer** | TBD (MVP3) | Should note easy attack surface |

**Usage:**

```bash
# Set up test data
mkdir -p report/test_flawed_assessment
cp tests/data/agent_test_cases/test_flawed_assessment.json \
   report/test_flawed_assessment/ground_truth.json

# Run Architect critique
python3 -m chatbot.modules.architect_critic test_flawed_assessment

# Expected output:
# Score: 20-30/100 (POOR)
# Gaps: Should mention backup contradiction, DoS priority, coverage gap
```

---

## Creating New Test Cases

### Guidelines

1. **Naming Convention:** `test_<issue_type>_<description>.json`
   - Examples: `test_missing_controls.json`, `test_inconsistent_rapids.json`

2. **Required Fields:**
   - `architecture`: Descriptive name (e.g., "test_flawed_assessment.mmd")
   - `description`: What the test validates
   - `metadata.purpose`: "Test case for [agent] validation"
   - `_test_expectations`: Document what each agent should catch

3. **Include Test Expectations:**
   ```json
   "_test_expectations": {
     "architect_should_catch": [
       "Control priority mismatch",
       "Missing database security"
     ],
     "tester_should_catch": [
       "Ransomware rationale contradiction",
       "Validation checks failed (3/6)"
     ],
     "red_teamer_should_catch": [
       "Only 1 attack path - too easy to defend"
     ]
   }
   ```

4. **Validation Reports:**
   - Include `validation_report` with deliberate failures
   - Mark which checks should fail: `"passed": false`

### Example Template

```json
{
  "architecture": "test_example.mmd",
  "description": "Test case description",
  "metadata": {
    "architecture_type": "web_app",
    "purpose": "Test case for agent validation",
    "created_date": "2026-05-10"
  },
  "controls_present": [...],
  "controls_missing": [...],
  "control_recommendations": [...],
  "rapids_assessment": {...},
  "expected_attack_paths": [...],
  "validation_report": {
    "overall_valid": false,
    "validations": [
      {"check": "...", "passed": false, "issue": "..."}
    ]
  },
  "_test_expectations": {
    "architect_should_catch": [...],
    "tester_should_catch": [...],
    "red_teamer_should_catch": [...]
  }
}
```

---

## Test Case Ideas (TODO)

1. **test_missing_prevention_dir.json**
   - All controls are Prevention (0% Detection/Isolation/Response)
   - Tests: Defense-in-depth validation

2. **test_high_risk_no_controls.json**
   - RAPIDS scores all 80-90/100
   - Only 2-3 controls recommended
   - Tests: Control adequacy validation

3. **test_generic_techniques.json**
   - All techniques are generic (T1059, T1055)
   - No architecture-specific techniques
   - Tests: MITRE quality validation

4. **test_inconsistent_residual_risk.json**
   - Before risk: 80/100
   - After risk: 85/100 (WORSE after controls!)
   - Tests: Logic validation

5. **test_duplicate_controls.json**
   - Same control recommended 3 times with different priorities
   - Tests: De-duplication validation

---

## Difference from Real Architectures

| tests/data/architectures/ | tests/data/agent_test_cases/ |
|---------------------------|------------------------------|
| Real .mmd files | Synthetic JSON test data |
| Used for threat analysis | Used for agent validation |
| Generated by ground_truth_generator.py | Hand-crafted with deliberate flaws |
| Complete, valid assessments | Deliberately flawed assessments |
| 22 files (01-22) | Growing set of edge cases |

**Both are important:**
- `architectures/`: Regression testing for threat analysis engine
- `agent_test_cases/`: Unit testing for critic agents

---

## Maintenance

- **Add test cases** as new agent issues discovered
- **Update expectations** when agent rubrics change
- **Document failures** when agents miss expected findings
- **Keep in sync** with agent framework changes

**Last Updated:** 2026-05-10 (MVP1 complete)
