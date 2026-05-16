# Phase 3C MVP2: Tester Agent Specification

**Date:** 2026-05-10  
**Status:** Specification (MVP1 Complete)  
**Purpose:** Design Tester agent to validate assessment quality using Architect's roadmap

---

## Role: Quality Assurance Tester

**Focus:** Internal consistency, validation checks, coverage metrics

**NOT:** Design quality (Architect), exploit difficulty (Red Teamer)

---

## Input from Architect Agent

```json
{
  "role": "Security Architect",
  "score": 78,
  "rating": "FAIR",
  "improvement_roadmap": [
    {
      "action": "Add database-specific threat analysis",
      "category": "threat_completeness",
      "points_gained": 6,
      "effort": "MEDIUM",
      "priority": 1,
      "verification_method": "Check if assessment includes database layer in threat model",
      "expected_outcome": "Database threats explicitly modeled"
    }
  ]
}
```

**Key insight:** `verification_method` tells Tester EXACTLY what to check!

---

## Tester Rubric (100 points)

### A. Validation Checks (40 points)
- Ground truth validation passed (10 pts)
- Control-threat mapping valid (10 pts)
- Risk score consistency (10 pts)
- Technique coverage adequate (10 pts)

**Verification:**
```python
# Check validation_report in ground truth
validation = ground_truth.get("validation_report", {})
passed = sum(1 for v in validation.get("validations", []) if v.get("passed"))
score = (passed / 6) * 40  # 6 validation checks
```

### B. Coverage Metrics (30 points)
- RAPIDS completeness (6/6 categories) (10 pts)
- Technique-to-risk ratio appropriate (10 pts)
- Control-to-threat coverage sufficient (10 pts)

**Verification:**
```python
# Example: High risk should have multiple techniques
if rapids_risk >= 80 and technique_count < 5:
    gaps.append("High risk (80+) has <5 techniques")
```

### C. Internal Consistency (20 points)
- Rationale matches control inventory (10 pts)
- Priority matches risk scores (10 pts)

**Verification:**
```python
# Architect roadmap Priority 5 verification method:
# "Verify ransomware rationale aligns with actual controls"

ransomware_rationale = ground_truth["rapids_assessment"]["ransomware"]["rationale"]
controls_missing = ground_truth["controls_missing"]

if "backup" in ransomware_rationale.lower() and "backup" in controls_missing:
    gaps.append({
        "severity": "HIGH",
        "description": "Ransomware rationale claims backup exists but backup in controls_missing",
        "verification_source": "Architect roadmap Priority 5"
    })
```

### D. Architect Roadmap Validation (10 points)
- Roadmap addresses actual gaps (5 pts)
- Points allocation realistic (5 pts)

**Verification:**
```python
# Check if roadmap improvements are implementable
total_points = sum(item["points_gained"] for item in roadmap)
if total_points + architect_score > 110:
    gaps.append("Roadmap overpromises (total >110)")
```

---

## How Tester Uses Architect Roadmap

### Example 1: Quantitative Check

**Architect says:**
```json
{
  "priority": 1,
  "verification_method": "Count MITRE techniques - should increase from 1 to 8+"
}
```

**Tester executes:**
```python
technique_count = sum(len(path.get("techniques", [])) for path in ground_truth["expected_attack_paths"])

if technique_count < 8:
    gaps.append({
        "category": "coverage_metrics",
        "severity": "HIGH",
        "description": f"Only {technique_count} techniques (Architect expects 8+)",
        "architect_roadmap_ref": "Priority 1"
    })
```

### Example 2: Consistency Check

**Architect says:**
```json
{
  "priority": 2,
  "verification_method": "Verify control priorities aligned to RAPIDS scores"
}
```

**Tester executes:**
```python
for control in ground_truth["control_recommendations"]:
    control_priority = control.get("priority", "low")
    rapids_threats = control.get("rapids_threats", [])
    
    # Check if HIGH risk threats have LOW priority controls
    for threat in rapids_threats:
        risk = ground_truth["rapids_assessment"][threat]["risk"]
        if risk >= 80 and control_priority == "low":
            gaps.append({
                "category": "internal_consistency",
                "severity": "HIGH",
                "description": f"Control {control['control']} priority=low but {threat} risk={risk}",
                "architect_roadmap_ref": "Priority 2"
            })
```

### Example 3: Logic Check (Catches Planted Flaw!)

**Architect says:**
```json
{
  "priority": 5,
  "verification_method": "Verify ransomware rationale aligns with actual controls"
}
```

**Tester executes:**
```python
ransomware = ground_truth["rapids_assessment"]["ransomware"]
rationale = ransomware["rationale"].lower()

# Check for mentioned controls
mentioned_controls = []
if "backup" in rationale:
    mentioned_controls.append("backup")
if "edr" in rationale:
    mentioned_controls.append("edr")

controls_present = ground_truth["controls_present"]
controls_missing = ground_truth["controls_missing"]

# Verify each mentioned control exists
for control in mentioned_controls:
    if control in controls_missing:
        gaps.append({
            "category": "internal_consistency",
            "severity": "HIGH",
            "description": f"Ransomware rationale mentions '{control}' but it's in controls_missing",
            "architect_roadmap_ref": "Priority 5",
            "planted_flaw": True  # ← This catches our test case!
        })
```

---

## Test Case: test_flawed_assessment.json

**Expected Tester Findings:**

| Check | Expected Result | Reference |
|-------|----------------|-----------|
| Validation checks | 3/6 failed → 20/40 points | Rubric A |
| Technique coverage | 1 technique for risk=90 → 3/10 points | Rubric B + Architect Priority 1 |
| Control priority | DoS=80 but priority=low → 0/10 points | Rubric C + Architect Priority 2 |
| Backup contradiction | Rationale vs controls_missing → HIGH gap | Rubric C + Architect Priority 5 |
| Roadmap validation | +80 points realistic → 5/5 points | Rubric D |

**Expected Tester Score:** 35-45/100 (lower than Architect's 23/100)

**Why lower?** Tester focuses on internal validation failures, not design quality

---

## Tester System Prompt (Draft)

```
You are a Quality Assurance Tester reviewing a deterministic threat assessment.

IMPORTANT: You are NOT evaluating design quality (that's Architect's job).
You are checking INTERNAL CONSISTENCY and VALIDATION.

YOUR CHECKS:
1. Validation report status (ground_truth.validation_report)
2. Coverage metrics (techniques per high-risk threat)
3. Logic consistency (rationale matches control inventory)
4. Priority alignment (HIGH risk = HIGH priority controls)

YOU WILL RECEIVE:
- Ground truth assessment (raw data)
- Architect critique (includes improvement_roadmap)

USE ARCHITECT'S ROADMAP:
- Each roadmap item has verification_method
- Execute those checks to validate Architect's gaps
- If you find the same issue, reference "Architect Priority N"
- If you find NEW issues, mark as "Tester-only finding"

OUTPUT: Same JSON format as Architect but different rubric
```

---

## Implementation Checklist

- [ ] Create `chatbot/modules/tester_critic.py`
- [ ] Define TESTER_RUBRIC (40+30+20+10)
- [ ] Write TESTER_SYSTEM_PROMPT
- [ ] Implement verification checks:
  - [ ] Parse validation_report
  - [ ] Count techniques per risk level
  - [ ] Check rationale vs controls consistency
  - [ ] Validate control priorities
  - [ ] Execute Architect roadmap verifications
- [ ] Test on:
  - [ ] 02_minimal_defended (good assessment)
  - [ ] test_flawed_assessment (should catch all 3 planted flaws)
- [ ] Verify Tester finds issues Architect missed
- [ ] Verify Tester references Architect roadmap

---

## Success Criteria

1. **Tester catches planted flaws:** All 3 contradictions detected
2. **References Architect:** Uses "Architect Priority N" in gap descriptions
3. **Orthogonal scoring:** Tester score ≠ Architect score (different dimensions)
4. **Verifiable gaps:** Each gap has quantitative check (e.g., "found 1 technique, expected 8")
5. **Roadmap validation:** Checks if Architect's improvement estimates are realistic

---

**Next Step:** Implement MVP2 using this specification

**Estimated Time:** 2-3 hours (reuse agent_framework.py, just config + rubric)
