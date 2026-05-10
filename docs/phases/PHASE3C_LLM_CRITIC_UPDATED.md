# Phase 3C: LLM as Multi-Role Critic (Updated)

**Status:** Ready to Start - Phase 3B+ Complete (99.5% baseline)  
**Prerequisites:** ✅ Phase 3B+ complete (99.5% confidence, 100% technique coverage, 0 orphans)  
**Estimated Duration:** 4-6 hours  
**Purpose:** Quantitative LLM critique with scoring rubrics and revised diagrams

---

## Context Update (Phase 3B+ Complete)

**Baseline Changed:**
- ~~Phase 3C doc assumed 89% confidence baseline~~
- **Actual:** 99.5% confidence baseline (Phase 3B+ complete)
- **Implication:** LLM critique now focuses on edge cases, not fundamental gaps

**What Phase 3B+ Achieved:**
- ✅ 6-check validation framework (completeness)
- ✅ Per-node TTP mapping (precision)
- ✅ Exhaustive mitigation mapping (100% MITRE coverage)
- ✅ Path-based control placement (95% visual clarity)
- ✅ Orphan detection (0 orphans)
- ✅ 22/22 architectures validated

**What LLM Adds:**
- 🔍 Blind spot detection (edge cases deterministic rules miss)
- 🎯 Architecture-specific nuances (AI/IoT/Financial context)
- 🚨 Red team perspective (attacker mindset)
- 📊 Quantitative scoring (not just binary pass/fail)
- 🔄 Revised diagrams (after-llm.mmd with LLM suggestions)

---

## Core Concept: Three-Hat LLM Critique

```
┌─────────────────────────────────────────────────────────────┐
│ Phase 3B+ Output (99.5% Confidence Baseline)                │
├─────────────────────────────────────────────────────────────┤
│ • 6-check validation: PASS                                  │
│ • Technique coverage: 100%                                  │
│ • Orphan nodes: 0                                           │
│ • Control placement: 95% visual clarity                     │
│ • Residual risk: BEFORE → AFTER calculated                  │
└─────────────────────────────────────────────────────────────┘
                            ↓
        ┌───────────────────┴───────────────────┐
        │                                       │
        ▼                                       ▼
┌────────────────────┐              ┌────────────────────┐
│ HAT 1: ARCHITECT   │              │ HAT 2: TESTER      │
├────────────────────┤              ├────────────────────┤
│ Reviews design     │              │ Tests assumptions  │
│ Checks assumptions │              │ Validates coverage │
│ Architecture fit   │              │ Edge cases         │
│                    │              │                    │
│ Score: 0-100       │              │ Score: 0-100       │
└────────────────────┘              └────────────────────┘
        │                                       │
        └───────────────────┬───────────────────┘
                            ↓
                  ┌────────────────────┐
                  │ HAT 3: RED TEAMER  │
                  ├────────────────────┤
                  │ Attacker mindset   │
                  │ Bypass strategies  │
                  │ Weakest path       │
                  │                    │
                  │ Score: 0-100       │
                  └────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ LLM Critique Report                                         │
├─────────────────────────────────────────────────────────────┤
│ • Architect Score: 92/100 (EXCELLENT)                       │
│ • Tester Score: 88/100 (GOOD)                               │
│ • Red Team Score: 15/100 (HIGH SECURITY - hard to breach)   │
│ • Composite Confidence: 99.5% → 99.8% (+0.3%)               │
│ • Gaps Found: 3 (2 MEDIUM, 1 LOW)                           │
│ • Improvements: 5 actionable items                          │
│ • Revised Diagram: after-llm.mmd (with improvements)        │
└─────────────────────────────────────────────────────────────┘
```

---

## Hat 1: Security Architect Rubric

**Role:** Design reviewer checking if recommendations fit architecture context

### Scoring Rubric (0-100)

**A. Threat Model Completeness (40 points)**
- [ ] All entry points identified (10 pts)
- [ ] All data flows mapped (10 pts)
- [ ] Architecture-specific threats considered (10 pts)
- [ ] Trust boundaries clearly defined (10 pts)

**B. Control Appropriateness (30 points)**
- [ ] Controls match architecture complexity (10 pts)
- [ ] Controls aligned with data sensitivity (10 pts)
- [ ] Controls feasible for architecture type (10 pts)

**C. Defense-in-Depth (20 points)**
- [ ] Multiple control layers per path (10 pts)
- [ ] No single points of failure unmitigated (10 pts)

**D. Context Awareness (10 points)**
- [ ] Industry-specific considerations (5 pts)
- [ ] Regulatory requirements addressed (5 pts)

**Scoring:**
- 90-100: EXCELLENT - Architecture-aware recommendations
- 80-89: GOOD - Minor context improvements possible
- 70-79: FAIR - Some architectural mismatches
- <70: POOR - Significant architectural gaps

### LLM Prompt Template

```
You are a Senior Security Architect reviewing a threat assessment.

ARCHITECTURE CONTEXT:
- Type: {architecture_type}
- Components: {component_list}
- Entry Points: {entry_points}
- Data Sensitivity: {sensitivity_level}
- Industry: {industry}

DETERMINISTIC ASSESSMENT (99.5% confidence):
- RAPIDS Threats: {rapids_summary}
- MITRE Techniques: {technique_count} mapped
- Controls Recommended: {control_count}
- Residual Risk: {before_risk} → {after_risk}
- Validation: 6/6 checks PASS

TASK: Score this assessment using the Architect Rubric (0-100)

For each rubric category:
1. Score (0-10 per item)
2. Reasoning (why this score?)
3. Gap identified (if score <10)
4. Improvement suggestion (specific, actionable)

OUTPUT FORMAT:
```json
{
  "architect_score": 92,
  "breakdown": {
    "threat_completeness": {"score": 38, "max": 40, "gaps": [...]},
    "control_appropriateness": {"score": 28, "max": 30, "gaps": [...]},
    "defense_in_depth": {"score": 18, "max": 20, "gaps": [...]},
    "context_awareness": {"score": 8, "max": 10, "gaps": [...]}
  },
  "gaps": [
    {
      "category": "Architecture-Specific Threats",
      "severity": "MEDIUM",
      "description": "AI model poisoning not considered for LLM component",
      "recommendation": "Add input validation and model versioning controls",
      "affected_components": ["AgentOrchestrator", "LLM"],
      "estimated_impact": "+2% risk reduction"
    }
  ]
}
```
```

---

## Hat 2: Security Tester Rubric

**Role:** Validation engineer testing assumptions and coverage

### Scoring Rubric (0-100)

**A. Technique Coverage (40 points)**
- [ ] All RAPIDS threats have MITRE techniques (10 pts)
- [ ] Techniques appropriate for attack paths (15 pts)
- [ ] Edge cases considered (10 pts)
- [ ] No false positives (techniques not relevant) (5 pts)

**B. Control Effectiveness (30 points)**
- [ ] Controls actually mitigate stated techniques (15 pts)
- [ ] No control redundancy (wasteful duplication) (10 pts)
- [ ] Controls address root cause (not just symptoms) (5 pts)

**C. Attack Path Validity (20 points)**
- [ ] Paths are realistic (attacker could execute) (10 pts)
- [ ] Paths cover all entry points (10 pts)

**D. Assumptions Validation (10 points)**
- [ ] Stated controls actually present (5 pts)
- [ ] Control placement correct (5 pts)

**Scoring:**
- 90-100: EXCELLENT - Validated thoroughly
- 80-89: GOOD - Minor assumptions to test
- 70-79: FAIR - Some questionable mappings
- <70: POOR - Significant validation failures

### LLM Prompt Template

```
You are a Security Testing Engineer validating a threat assessment.

TESTING SCOPE:
Attack Paths: {path_count}
Techniques Mapped: {technique_count}
Controls Recommended: {control_count}
Controls Present: {present_count}

SAMPLE ATTACK PATH:
Path: {path_example}
Techniques: {technique_list}
Controls: {control_list}

TASK: Validate assumptions using the Tester Rubric (0-100)

For each attack path (sample 3-5):
1. Is this path realistic? (Can attacker execute?)
2. Are techniques correctly mapped? (Check MITRE definitions)
3. Do controls actually mitigate techniques? (Not just correlation)
4. Are there edge cases missed? (Variants of this attack)

OUTPUT FORMAT:
```json
{
  "tester_score": 88,
  "breakdown": {
    "technique_coverage": {"score": 36, "max": 40, "issues": [...]},
    "control_effectiveness": {"score": 28, "max": 30, "issues": [...]},
    "attack_path_validity": {"score": 18, "max": 20, "issues": [...]},
    "assumptions": {"score": 6, "max": 10, "issues": [...]}
  },
  "validation_failures": [
    {
      "path_id": "AP-15",
      "issue": "T1190 assumes public-facing web, but component is internal-only",
      "severity": "MEDIUM",
      "recommendation": "Replace T1190 with T1078 (Valid Accounts via VPN)",
      "confidence_impact": "-1%"
    }
  ],
  "edge_cases": [
    {
      "scenario": "Attacker compromises VPN credentials AND MFA device",
      "currently_modeled": false,
      "severity": "LOW",
      "recommendation": "Add T1556 (Modify Authentication Process) to VPN path"
    }
  ]
}
```
```

---

## Hat 3: Red Teamer Rubric

**Role:** Adversary trying to find weakest path through defenses

### Scoring Rubric (0-100)

**INVERTED SCORING:** Higher score = Easier to breach (BAD for defense)

**A. Weakest Path Identification (40 points)**
- Easiest entry point found (10 pts if easy)
- Least defended hop found (10 pts if found)
- Bypass opportunities (10 pts if many)
- Social engineering vectors (10 pts if viable)

**B. Control Bypass Strategies (30 points)**
- Can bypass prevention controls (15 pts if yes)
- Can evade detection (10 pts if yes)
- Can maintain persistence (5 pts if yes)

**C. Lateral Movement (20 points)**
- Multiple paths to target (10 pts if multiple)
- Unmonitored connections (10 pts if exist)

**D. Exfiltration Feasibility (10 points)**
- Data exfiltration paths available (5 pts if yes)
- Exfiltration detection gaps (5 pts if exist)

**Scoring Interpretation:**
- 0-20: EXCELLENT DEFENSE - Very hard to breach
- 21-40: GOOD DEFENSE - Significant effort required
- 41-60: FAIR DEFENSE - Moderate skill can breach
- 61-80: POOR DEFENSE - Easy to breach
- 81-100: CRITICAL - Trivial to breach

### LLM Prompt Template

```
You are a Red Team Penetration Tester trying to breach this architecture.

CONSTRAINTS:
- You have internet access to entry points
- You have social engineering capability (phishing)
- Your skill level: Intermediate (not APT, but competent)
- Your goal: Reach {target_component} (usually database/sensitive data)

ARCHITECTURE:
Entry Points: {entry_points}
Controls Present: {present_controls}
Controls Recommended (NOT IMPLEMENTED): {recommended_controls}

ATTACK PATHS (deterministic analysis):
{attack_paths_summary}

TASK: Find the WEAKEST path to breach using Red Team Rubric (0-100)

Think like an attacker:
1. Which entry point is easiest to compromise?
2. Which hop has weakest controls?
3. Can you bypass controls? (social engineering, zero-days, misconfig)
4. Can you move laterally undetected?
5. Can you exfiltrate data without triggering alerts?

OUTPUT FORMAT:
```json
{
  "red_team_score": 15,
  "interpretation": "EXCELLENT DEFENSE - Very hard to breach",
  "breakdown": {
    "weakest_path": {"score": 5, "max": 40, "details": "..."},
    "bypass_strategies": {"score": 4, "max": 30, "details": "..."},
    "lateral_movement": {"score": 4, "max": 20, "details": "..."},
    "exfiltration": {"score": 2, "max": 10, "details": "..."}
  },
  "attack_narrative": {
    "chosen_path": "Internet → WAF → WebApp → Database",
    "step_1": "Phishing for credentials (bypasses MFA via social engineering)",
    "step_2": "Valid account access through WAF (looks legitimate)",
    "step_3": "SQL injection in WebApp (if input validation weak)",
    "step_4": "Data exfiltration via DNS tunneling (if DLP not configured)",
    "likelihood": "LOW (requires multiple bypasses)",
    "effort": "HIGH (days to weeks)",
    "detection_probability": "HIGH (logging + SIEM would catch)"
  },
  "weaknesses_found": [
    {
      "component": "WebApp",
      "weakness": "Input validation recommended but not present",
      "exploit": "SQL injection or command injection",
      "severity": "MEDIUM",
      "recommendation": "Prioritize input validation implementation"
    }
  ],
  "bypasses": [
    {
      "control": "MFA",
      "bypass_method": "Social engineering (phish MFA token)",
      "difficulty": "HARD",
      "recommendation": "Add user training and phishing simulation"
    }
  ]
}
```
```

---

## Composite Scoring & Confidence Adjustment

### Formula

```python
def calculate_llm_confidence_boost(architect_score, tester_score, red_team_score):
    """
    Calculate confidence adjustment from LLM critique.
    
    Architect: Higher = better (design quality)
    Tester: Higher = better (validation quality)
    Red Team: LOWER = better (harder to breach)
    """
    # Normalize red team score (invert because lower is better)
    red_team_defense_score = 100 - red_team_score
    
    # Weighted average
    composite = (
        architect_score * 0.30 +
        tester_score * 0.30 +
        red_team_defense_score * 0.40  # Red team weighted highest
    )
    
    # Confidence adjustment
    if composite >= 95:
        adjustment = +0.5  # Excellent across all dimensions
    elif composite >= 90:
        adjustment = +0.3  # Good across all dimensions
    elif composite >= 85:
        adjustment = +0.1  # Fair across all dimensions
    elif composite >= 80:
        adjustment = 0.0   # No boost (some issues)
    else:
        adjustment = -0.5  # Significant gaps found
    
    return adjustment, composite

# Example:
architect = 92  # Good design
tester = 88     # Good validation
red_team = 15   # Hard to breach (85 defense score)

boost, composite = calculate_llm_confidence_boost(92, 88, 15)
# composite = 92*0.3 + 88*0.3 + 85*0.4 = 88.0
# boost = +0.1

new_confidence = 99.5 + boost = 99.6%
```

---

## Output: LLM Critique Report

### Report Structure

```markdown
# LLM Critique Report

**Architecture:** {name}
**Baseline Confidence:** 99.5% (Phase 3B+)
**LLM Critique Date:** {date}

---

## Composite Scores

| Role | Score | Rating | Interpretation |
|------|-------|--------|----------------|
| Security Architect | 92/100 | EXCELLENT | Design well-suited to architecture |
| Security Tester | 88/100 | GOOD | Minor validation gaps |
| Red Team | 15/100 | EXCELLENT DEFENSE | Very hard to breach |
| **Composite** | **88.0/100** | **EXCELLENT** | Strong across all dimensions |

**Confidence Adjustment:** 99.5% → 99.6% (+0.1%)

---

## Security Architect Findings

### Gaps Identified (2)

#### 1. AI Model Poisoning (MEDIUM)
- **Component:** AgentOrchestrator → LLM
- **Issue:** Training data source not validated
- **Recommendation:** Add input data validation control, model versioning
- **Estimated Impact:** +2% risk reduction
- **Implementation:** 2-3 days

#### 2. Regulatory Compliance (LOW)
- **Component:** Database → PII Storage
- **Issue:** GDPR data retention policy not documented
- **Recommendation:** Document data lifecycle management
- **Estimated Impact:** +1% compliance posture
- **Implementation:** 1 day (documentation)

### Strengths Confirmed (5)
1. ✅ Defense-in-depth: Multiple control layers per path
2. ✅ Entry point coverage: All entry points have MFA
3. ✅ SPOF mitigation: No single points of failure
4. ✅ Layered defense: Prevention + Detect + Isolate + Respond
5. ✅ Context-aware: Controls appropriate for web architecture

---

## Security Tester Findings

### Validation Failures (1)

#### 1. Technique Mapping Edge Case (MEDIUM)
- **Path:** VPN → AdminPortal → Database
- **Issue:** T1190 (Exploit Public-Facing Application) assumes public-facing, but VPN is access-controlled
- **Correction:** Should be T1078 (Valid Accounts) for VPN compromise
- **Confidence Impact:** -0.5% (minor misclassification)
- **Fix:** Update per-node TTP mapping rules for VPN components

### Edge Cases Identified (1)

#### 1. Simultaneous MFA + Credential Compromise (LOW)
- **Scenario:** Attacker compromises both VPN credentials AND MFA device
- **Currently Modeled:** No (assumes MFA prevents compromise)
- **Recommendation:** Add T1556 (Modify Authentication Process) to VPN path
- **Likelihood:** LOW (requires physical access or sophisticated social engineering)
- **Implementation:** Add to ground truth as low-priority path

### Validations Passed (12)
- ✅ All 22 attack paths realistic
- ✅ Controls actually mitigate stated techniques
- ✅ No false positive techniques
- ✅ Controls address root causes
- ✅ (... 8 more confirmations)

---

## Red Team Findings

### Weakest Path Analysis

**Chosen Attack Vector:** Phishing → VPN Compromise → Lateral Movement
```
Internet
  ↓ [Phishing email with malicious link]
VPN Credentials Stolen
  ↓ [Bypass MFA via social engineering]
VPN → MFA (bypassed) → AdminPortal
  ↓ [Escalate privileges]
AdminPortal → Database
  ↓ [Exfiltrate data]
Database → Exfiltration
```

**Attack Narrative:**
1. **Initial Access:** Phishing email targeting admins (T1566.002)
   - Likelihood: MEDIUM (user training present but not perfect)
   - Detection: Email gateway + user training would likely catch
   
2. **MFA Bypass:** Social engineering for MFA token (T1621)
   - Likelihood: LOW (requires real-time phishing)
   - Detection: Behavioral analysis would flag unusual MFA patterns
   
3. **Lateral Movement:** Valid account access (T1078)
   - Likelihood: HIGH (if steps 1-2 succeed)
   - Detection: Logging + audit logs would record access
   
4. **Exfiltration:** Data exfiltration via encrypted channel (T1041)
   - Likelihood: MEDIUM (DLP recommended but not present)
   - Detection: DLP + behavioral analysis would catch

**Overall Assessment:**
- **Effort Required:** HIGH (multiple social engineering steps)
- **Skill Level:** ADVANCED (coordinated campaign)
- **Time to Breach:** 2-4 weeks (reconnaissance + execution)
- **Detection Probability:** 85% (multiple detection opportunities)
- **Conclusion:** Defense is STRONG. Attacker would need advanced persistent threat (APT) capabilities.

### Weaknesses Found (2)

#### 1. User Training Gap (MEDIUM)
- **Control:** User training recommended but not present
- **Exploit:** Increases phishing success rate 20% → 40%
- **Recommendation:** Implement phishing simulation + quarterly training
- **Priority:** HIGH (foundational defense)

#### 2. DLP Not Implemented (MEDIUM)
- **Control:** DLP recommended but not present
- **Exploit:** Data exfiltration harder to detect
- **Recommendation:** Prioritize DLP implementation for database access
- **Priority:** MEDIUM (important but not critical given other layers)

### Bypass Strategies Evaluated (3)

#### 1. MFA Bypass via Social Engineering
- **Control:** MFA (present)
- **Bypass Method:** Real-time phishing attack (MFA fatigue)
- **Difficulty:** HARD (requires sophisticated operation)
- **Recommendation:** Add MFA fatigue detection (limit push notifications)

#### 2. WAF Bypass via Obfuscation
- **Control:** WAF (present)
- **Bypass Method:** Request obfuscation, encoding tricks
- **Difficulty:** MEDIUM (known WAF bypass techniques exist)
- **Recommendation:** WAF rule tuning + regular updates

#### 3. Logging Evasion via Low-and-Slow
- **Control:** Logging + SIEM (recommended)
- **Bypass Method:** Slow exfiltration over weeks
- **Difficulty:** MEDIUM (requires patience)
- **Recommendation:** Behavioral analysis + data volume baselines

---

## Actionable Improvements (5)

### Priority: HIGH

**1. Implement User Training (fills gap identified by Red Team)**
- **Control:** User Training + Phishing Simulation
- **Rationale:** Reduces phishing success rate from 40% → 10%
- **Implementation:** 2 weeks (setup + first campaign)
- **Cost:** Low ($5K for platform + internal time)
- **Risk Reduction:** -5% residual risk

**2. Fix VPN Technique Mapping (validation failure)**
- **Control:** Update ground truth rules
- **Rationale:** T1190 → T1078 for VPN components
- **Implementation:** 1 hour (code fix + revalidate)
- **Cost:** Minimal (engineering time)
- **Confidence Impact:** +0.5%

### Priority: MEDIUM

**3. Add AI Model Validation Controls (architect gap)**
- **Control:** Input Data Validation + Model Versioning
- **Rationale:** Prevents model poisoning attacks
- **Implementation:** 3 days (development + testing)
- **Cost:** Medium ($10K development)
- **Risk Reduction:** -2% residual risk

**4. Implement DLP (red team weakness)**
- **Control:** Data Loss Prevention
- **Rationale:** Detects data exfiltration attempts
- **Implementation:** 2 weeks (deployment + tuning)
- **Cost:** Medium ($15K license + implementation)
- **Risk Reduction:** -3% residual risk

### Priority: LOW

**5. Document GDPR Compliance (architect gap)**
- **Control:** Data Lifecycle Management Documentation
- **Rationale:** Regulatory compliance requirement
- **Implementation:** 1 day (documentation)
- **Cost:** Minimal (compliance time)
- **Risk Reduction:** +1% compliance posture (not technical risk)

---

## Revised Architecture (after-llm.mmd)

**Changes from after.mmd:**
1. ✅ Add USER_TRAINING control at Internet entry
2. ✅ Add DLP control at Database
3. ✅ Add MODEL_VALIDATION control at LLM component
4. ✅ Update MFA with "MFA Fatigue Detection" note
5. ✅ Update technique labels (T1190 → T1078 for VPN)

**Risk Impact:**
- BEFORE (Phase 3B+): 9.5/100 residual risk
- AFTER (LLM improvements): 7.0/100 residual risk (-26% reduction)

**See:** after-llm.mmd for visual diagram with improvements

---

## Summary

### Baseline (Phase 3B+)
- Confidence: 99.5%
- Residual Risk: 9.5/100 (ACCEPT threshold)
- Technique Coverage: 100%
- Validation: 6/6 checks PASS

### LLM Critique Results
- Architect Score: 92/100 (EXCELLENT)
- Tester Score: 88/100 (GOOD)
- Red Team Score: 15/100 (EXCELLENT DEFENSE)
- Gaps Found: 5 (2 HIGH, 2 MEDIUM, 1 LOW)
- Improvements: 5 actionable items

### After LLM Improvements
- Confidence: 99.6% (+0.1%)
- Residual Risk: 7.0/100 (ACCEPT threshold, -26% reduction)
- New Controls: 3 (User Training, DLP, Model Validation)
- Validation: Still 6/6 checks PASS (improvements don't break validation)

### Recommendation
**APPROVE LLM-SUGGESTED IMPROVEMENTS** - All 5 improvements are:
- ✅ Actionable (specific, not vague)
- ✅ Cost-justified (risk reduction > implementation cost)
- ✅ Architecture-appropriate (fit the context)
- ✅ Validated (cross-checked against industry best practices)

---

## Implementation Plan

### Phase 3C Implementation Workflow

```
Step 1: Validation Framework (2-3 hours)
├── Create blind spot test suite (5-10 architectures)
│   ├── Business logic gaps
│   ├── Cascading failures
│   ├── Compliance gaps
│   ├── Supply chain attack surfaces
│   └── Insider threat scenarios
├── Human expert validation (baseline)
├── Historical incident reconstruction
└── Edge case catalog

Step 2: LLM Critique Module (2-3 hours)
├── Implement llm_critique.py
│   ├── Hat 1: Architect critique
│   ├── Hat 2: Tester critique
│   └── Hat 3: Red team critique
├── Composite scoring calculation
├── Report generation (04_llm_critique.md)
└── Revised diagram generation (after-llm.mmd)

Step 3: Integration (1 hour)
├── Add to ground_truth_generator.py
│   ├── --llm-critique flag (optional, defaults OFF)
│   ├── Run after Phase 3B+ validation
│   └── Append to existing reports
├── Add to demo_architecture.sh
└── Update documentation

Step 4: Validation Testing (1 hour)
├── Run on blind spot test suite
├── Calculate validation metrics
│   ├── Detection rate (target: 70%+)
│   ├── False positive rate (target: <20%)
│   └── Unique value rate (target: 30%+)
└── Tune prompts/rubrics if needed
```

### Validation Strategy

**Approach Selected:** Human Expert + Historical Incidents + Edge Cases

**Rationale:**
- ❌ Multi-LLM: Adds cost/complexity, measures LLM consensus not accuracy
- ✅ Human Expert: Ground truth baseline (2-3 security professionals review 5 architectures)
- ✅ Historical Incidents: Retrospective validation (can LLM catch known breaches?)
- ✅ Edge Cases: Proactive gatekeeping (synthetic blind spots to test detection)

#### Validation Test Suite Structure

**Blind Spot Tests (5-10 architectures):**

```
tests/data/architectures/blind_spots/
├── bs01_business_logic_gap.mmd
│   └── Issue: E-commerce with no transaction replay protection
│
├── bs02_cascading_failure.mmd
│   └── Issue: Microservices with shared DB SPOF affecting 8 services
│
├── bs03_compliance_gap.mmd
│   └── Issue: Healthcare (HIPAA) with no encryption at rest
│
├── bs04_supply_chain.mmd
│   └── Issue: Heavy third-party APIs, no integrity validation
│
├── bs05_insider_threat.mmd
│   └── Issue: Admin everywhere, no audit trail
│
├── bs06_ai_model_poisoning.mmd (NEW)
│   └── Issue: LLM component with no input validation
│
├── bs07_api_abuse.mmd (NEW)
│   └── Issue: Public API with no rate limiting
│
└── bs08_credential_stuffing.mmd (NEW)
    └── Issue: Auth endpoint with no brute force protection
```

**Each test includes:**
- `.mmd` file (architecture diagram)
- `expected_gaps.json` (what LLM should find)
- `severity.json` (CRITICAL/HIGH/MEDIUM/LOW per gap)
- `human_expert_notes.txt` (baseline from security professionals)

#### Validation Metrics

```python
# After running LLM critique on blind spot test suite
validation_results = {
    "detection_rate": 0.75,        # 75% of seeded gaps caught
    "false_positive_rate": 0.15,   # 15% invalid findings
    "unique_value_rate": 0.40,     # 40% findings are LLM-unique
    "precision": 0.85,             # True positives / all positives
    "recall": 0.75,                # True positives / all actual gaps
    "f1_score": 0.80               # Harmonic mean
}

# Confidence boost eligibility
if detection_rate >= 0.70 and false_positive_rate <= 0.20:
    llm_critique_enabled = True
    confidence_boost_eligible = True
else:
    llm_critique_enabled = False
    requires_prompt_tuning = True
```

#### Historical Incident Validation

**Test cases from public breach reports:**

```
incidents/
├── target_2013.mmd
│   └── Vendor VPN compromise → lateral movement → POS compromise
│   └── Expected: Red team should identify vendor access as weakest path
│
├── equifax_2017.mmd
│   └── Unpatched Apache Struts → data exfiltration
│   └── Expected: Tester should flag missing patch management
│
└── solarwinds_2020.mmd
    └── Supply chain compromise via build system
    └── Expected: Architect should flag build pipeline security gap
```

**Success criteria:** LLM critique catches ≥60% of actual breach vectors in hindsight

---

## Integration into Existing System

### Command-Line Interface

```bash
# Standard analysis (Phase 3B+ only, 99.5% confidence)
python3 -m chatbot.main --gen-arch-truth architecture.mmd

# With LLM critique (Phase 3C, 99.5% → 99.6-99.8%)
python3 -m chatbot.main --gen-arch-truth --llm-critique architecture.mmd

# LLM critique only (re-run on existing report)
python3 -m chatbot.main --llm-critique-only architecture_name

# Validation mode (test on blind spot suite)
python3 -m chatbot.main --validate-llm-critique
```

### Report Structure (with LLM critique enabled)

```
report/architecture_name/
├── 01_executive_summary.md        # Business summary (unchanged)
├── 02_technical_report.md         # MITRE mapping (unchanged)
├── 03_action_plan.md              # 8-week roadmap (unchanged)
├── 04_llm_critique.md             # NEW: Three-role critique
├── ground_truth.json              # Enhanced with LLM findings
├── before.mmd                     # Original architecture
├── after.mmd                      # Phase 3B+ recommendations
└── after-llm.mmd                  # NEW: With LLM improvements
```

### ground_truth.json Enhancement

```json
{
  "architecture_name": "10_complex_enterprise",
  "phase_3b_plus": {
    "confidence": 0.995,
    "validation": "6/6 checks PASS",
    "residual_risk_before": 65.0,
    "residual_risk_after": 9.5
  },
  "llm_critique": {
    "enabled": true,
    "timestamp": "2026-05-09T14:30:00Z",
    "scores": {
      "architect": 92,
      "tester": 88,
      "red_team": 15,
      "composite": 88.0
    },
    "confidence_adjustment": 0.1,
    "final_confidence": 0.996,
    "gaps_found": [
      {
        "source": "architect",
        "severity": "MEDIUM",
        "category": "AI Model Poisoning",
        "description": "Training data source not validated",
        "recommendation": "Add input validation and model versioning",
        "affected_components": ["AgentOrchestrator", "LLM"],
        "estimated_impact": "+2% risk reduction"
      }
    ],
    "improvements_applied": 5,
    "residual_risk_after_llm": 7.0
  }
}
```

### User Experience

**Scenario 1: User runs standard analysis (no LLM)**
```bash
$ python3 -m chatbot.main --gen-arch-truth my_arch.mmd

✅ Phase 3B+ Analysis Complete
   Confidence: 99.5%
   Residual Risk: 65/100 → 9.5/100 (85% reduction)
   Reports: report/my_arch/ (3 files + 2 diagrams)

ℹ️  Optional: Run LLM critique for additional insights
   python3 -m chatbot.main --llm-critique-only my_arch
```

**Scenario 2: User runs with LLM critique**
```bash
$ python3 -m chatbot.main --gen-arch-truth --llm-critique my_arch.mmd

✅ Phase 3B+ Analysis Complete (99.5% confidence)
🔍 Running LLM Critique (3 roles)...
   Hat 1: Security Architect... 92/100 (EXCELLENT)
   Hat 2: Security Tester... 88/100 (GOOD)
   Hat 3: Red Teamer... 15/100 (HARD TO BREACH)
   
✅ LLM Critique Complete
   Composite: 88/100
   Confidence: 99.5% → 99.6% (+0.1%)
   Gaps Found: 5 (2 HIGH, 2 MEDIUM, 1 LOW)
   Improvements: 5 actionable items
   
   Reports: report/my_arch/ (4 files + 3 diagrams)
   New: 04_llm_critique.md, after-llm.mmd
```

---

## Code Structure

### New Module: chatbot/modules/llm_critique.py

```python
"""
LLM-based critique of threat assessments using three-role rubrics.
Validates Phase 3B+ outputs and identifies blind spots.
"""

from typing import Dict, List, Tuple
from dataclasses import dataclass

@dataclass
class CritiqueScore:
    role: str
    score: int
    max_score: int
    rating: str
    breakdown: Dict[str, Dict]
    gaps: List[Dict]

class LLMCritic:
    """
    Three-role LLM critique system.
    """
    
    def __init__(self, llm_provider):
        self.llm = llm_provider
        
    def critique_as_architect(self, ground_truth: Dict) -> CritiqueScore:
        """Hat 1: Security Architect perspective"""
        pass
        
    def critique_as_tester(self, ground_truth: Dict) -> CritiqueScore:
        """Hat 2: Security Tester perspective"""
        pass
        
    def critique_as_red_teamer(self, ground_truth: Dict) -> CritiqueScore:
        """Hat 3: Red Team perspective (inverted scoring)"""
        pass
        
    def calculate_composite(
        self, 
        architect: CritiqueScore,
        tester: CritiqueScore,
        red_team: CritiqueScore
    ) -> Tuple[float, float]:
        """
        Calculate composite score and confidence adjustment.
        Returns: (composite_score, confidence_adjustment)
        """
        pass
        
    def generate_revised_diagram(
        self,
        ground_truth: Dict,
        improvements: List[Dict]
    ) -> str:
        """Generate after-llm.mmd with LLM improvements"""
        pass

def run_llm_critique(ground_truth: Dict) -> Dict:
    """
    Main entry point for LLM critique.
    """
    critic = LLMCritic(llm_provider=get_llm_provider())
    
    # Run three critiques
    architect = critic.critique_as_architect(ground_truth)
    tester = critic.critique_as_tester(ground_truth)
    red_team = critic.critique_as_red_teamer(ground_truth)
    
    # Calculate composite
    composite, adjustment = critic.calculate_composite(architect, tester, red_team)
    
    # Generate improvements
    improvements = consolidate_improvements([architect, tester, red_team])
    
    # Generate revised diagram
    revised_diagram = critic.generate_revised_diagram(ground_truth, improvements)
    
    return {
        "scores": {
            "architect": architect.score,
            "tester": tester.score,
            "red_team": red_team.score,
            "composite": composite
        },
        "confidence_adjustment": adjustment,
        "gaps_found": improvements,
        "revised_diagram": revised_diagram
    }
```

### Integration Point: chatbot/modules/ground_truth_generator.py

```python
# Add after Phase 3B+ validation (line ~450)

def generate_ground_truth(architecture_path: str, llm_critique: bool = False):
    """Generate threat assessment with optional LLM critique"""
    
    # ... existing Phase 3B+ logic ...
    
    # Phase 3B+ complete
    ground_truth = {
        "confidence": 0.995,
        "validation": validation_results,
        # ... all existing fields ...
    }
    
    # Optional: LLM critique
    if llm_critique:
        logger.info("Running LLM critique (Phase 3C)...")
        critique_results = run_llm_critique(ground_truth)
        
        ground_truth["llm_critique"] = critique_results
        ground_truth["final_confidence"] = (
            ground_truth["confidence"] + 
            critique_results["confidence_adjustment"]
        )
        
        # Generate 04_llm_critique.md
        generate_llm_critique_report(
            architecture_name,
            critique_results
        )
        
        # Generate after-llm.mmd
        write_file(
            f"report/{architecture_name}/after-llm.mmd",
            critique_results["revised_diagram"]
        )
    
    return ground_truth
```

---

## Testing & Validation Checklist

### Pre-Implementation Validation

- [ ] Create blind spot test suite (5-10 architectures)
- [ ] Document expected gaps per test case
- [ ] Get human expert baseline (2-3 security professionals review 5 cases)
- [ ] Reconstruct 3 historical incidents (Target, Equifax, SolarWinds)
- [ ] Document edge case catalog

### Post-Implementation Validation

- [ ] Run LLM critique on blind spot suite
- [ ] Calculate detection rate (target: ≥70%)
- [ ] Calculate false positive rate (target: ≤20%)
- [ ] Calculate unique value rate (target: ≥30%)
- [ ] Validate against human expert baseline (precision/recall)
- [ ] Test on historical incidents (retrospective detection)
- [ ] Run on all 22 test architectures (no regressions)

### Quality Gates

**Gate 1: Detection Rate**
- Requirement: ≥70% of seeded blind spots caught
- If fail: Tune prompts, add few-shot examples, retry

**Gate 2: False Positive Rate**
- Requirement: ≤20% invalid findings
- If fail: Adjust rubric thresholds, add validation checks

**Gate 3: Unique Value**
- Requirement: ≥30% findings are LLM-unique (not duplicates)
- If fail: Review if LLM adds value vs complexity

**Gate 4: Confidence Justification**
- Requirement: Confidence adjustment justified by quantitative metrics
- If fail: Adjust composite scoring formula

---

## Success Criteria

### Quantitative

| Metric | Target | Measurement |
|--------|--------|-------------|
| Detection Rate | ≥70% | Blind spot suite |
| False Positive Rate | ≤20% | Expert review |
| Unique Value Rate | ≥30% | Gap analysis |
| Confidence Boost | +0.1-0.5% | Composite formula |
| Execution Time | <60s | Per architecture |

### Qualitative

- [ ] LLM findings are **actionable** (specific, not vague)
- [ ] LLM findings are **novel** (not already in Phase 3B+ output)
- [ ] LLM findings are **context-aware** (architecture-specific)
- [ ] Reports are **readable** (business + technical audiences)
- [ ] System remains **deterministic-first** (LLM is augmentation, not replacement)

---

## Rollout Strategy

### Phase 3C.1: Validation Framework (Week 1)
- Create blind spot test suite
- Human expert baseline
- Historical incident reconstruction
- Success: Validation suite ready

### Phase 3C.2: Core Implementation (Week 1-2)
- Implement llm_critique.py
- Three rubrics + composite scoring
- Report generation
- Success: Module complete, unit tests pass

### Phase 3C.3: Integration (Week 2)
- Add to ground_truth_generator.py
- CLI flags (--llm-critique)
- Documentation updates
- Success: End-to-end workflow works

### Phase 3C.4: Validation Testing (Week 2)
- Run on blind spot suite
- Calculate metrics
- Tune prompts/rubrics if needed
- Success: All quality gates pass

### Phase 3C.5: Production Rollout (Week 3)
- Document validation results
- Update STATUS_AND_PLAN.md
- Commit Phase 3C
- Success: Available for production use

---

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| LLM doesn't find gaps | MEDIUM | MEDIUM | Validation suite proves value first |
| Too many false positives | MEDIUM | HIGH | Human expert review in validation |
| LLM cost too high | LOW | MEDIUM | Optional flag, users opt-in |
| Execution time too long | LOW | LOW | Async execution, progress indicators |
| LLM availability issues | HIGH | LOW | Graceful degradation, Phase 3B+ still works |

---

## Future Enhancements (Phase 4+)

- **Multi-LLM Consensus** (Phase 4): Run with 2-3 LLMs, compare results
- **Interactive Critique** (Phase 4): Web UI for reviewing/approving suggestions
- **Learning from History** (Phase 5): Train on past critiques to improve
- **Custom Rubrics** (Phase 5): Industry-specific rubrics (healthcare, finance, etc.)

---

**Document Version:** 3.0 (Added implementation plan & validation strategy)  
**Date:** 2026-05-09  
**Status:** Ready for implementation (plan complete, coding deferred)  
**Changes from v2.0:** 
- Added validation strategy (human expert + historical incidents + edge cases)
- Added implementation workflow (4-step, 4-6 hours total)
- Added integration details (CLI, reports, ground_truth.json)
- Added code structure (llm_critique.py module)
- Added testing checklist & quality gates
- Added rollout strategy (5 phases over 2-3 weeks)
- Added risks & mitigations
- Clarified: LLM critique is OPTIONAL, deterministic system remains primary
