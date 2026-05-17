# Phase 3B++: Priority Refinement with Attack Path Coverage

**Date:** 2026-05-17  
**Context:** Enhanced priority logic considering attack path coverage and hygiene classification  
**Impact:** More accurate critical/high/medium prioritization for better resource allocation  

---

## Problem Statement

**Original priority logic** (from `layered_defense.py`):
```python
priority = "critical" if (is_critical_hop and category == "prevention") else "high"
```

**Issues identified:**
1. ❌ **patching** (3/3 paths, prevention) → HIGH (should be CRITICAL?)
2. ❌ **backup** (3/3 paths, respond) → HIGH (covers all paths!)
3. ❌ **logging** (3/3 paths, detect) → HIGH (covers all paths!)
4. ✅ **least privilege** (3/3 paths, isolate) → CRITICAL (correct)

**User insight:** *"Controls that break attack paths deserve higher priority"*

---

## Solution: Multi-Factor Priority Logic

### Enhanced Priority Criteria

**CRITICAL** if:
1. Direct prevention at entry/target hop (existing logic), OR
2. Direct prevention covering >= 66% of attack paths, OR
3. Any control covering 100% of attack paths (even detection/response)

**HIGH** if:
1. Hygiene controls (patching, scanning) **even if covering all paths**, OR
2. Detection/Response covering >= 50% of paths, OR
3. Direct prevention covering < 66% of paths

**MEDIUM** if:
- Low path coverage (< 50%), OR
- Non-essential controls

---

## Key Distinction: Hygiene vs Direct Controls

### Direct Preventive Controls
**Block attacks in real-time**

Examples:
- MFA, WAF, Input Validation, Rate Limiting, Firewall
- **Effect:** Actively blocks attack attempts at runtime
- **Priority:** CRITICAL if at entry/target or covering >=66% paths

**Rationale:** These controls stop attacks immediately when they occur.

---

### Hygiene Controls
**Reduce vulnerability surface**

Examples:
- Patching, Vulnerability Scanning, Code Signing, SBOM, Container Scanning
- **Effect:** Reduces likelihood by removing vulnerabilities
- **Priority:** HIGH (important but not immediately effective)

**Rationale:** These don't block attacks in real-time - they reduce the chance of vulnerabilities existing. Important baseline, but patching doesn't stop an exploit attempt the way WAF does.

---

### Detection/Response Controls
**Identify or recover from attacks**

Examples:
- Logging, SIEM, IDS, Backup, EDR, Audit Log
- **Effect:** Detect attacks in progress or recover after breach
- **Priority:** CRITICAL if covering 100% of paths, otherwise HIGH

**Rationale:** Detection covering all paths is critical for visibility. Response controls (backup) covering all paths are critical for recovery.

---

## Implementation

### Function: `refine_control_priorities()`

**Location:** `chatbot/modules/ground_truth_generator.py` (line ~940)

**Logic:**
```python
def refine_control_priorities(
    control_recommendations: List[Dict],
    attack_paths: List[Dict]
) -> List[Dict]:
    """
    Refine priorities based on:
    1. Attack path coverage (% of paths affected)
    2. Hygiene classification (reduces likelihood, doesn't block)
    3. DIR category (prevention > detection > response)
    """
    
    HYGIENE_CONTROLS = {
        "patching", "vulnerability scanning", "code signing",
        "sbom", "container scanning", "secrets management",
        "user training", # Also hygiene - reduces likelihood, doesn't block
        ...
    }
    
    for rec in control_recommendations:
        path_coverage = len(rec["attack_paths"]) / total_paths
        is_hygiene = rec["control"] in HYGIENE_CONTROLS
        
        if is_hygiene:
            priority = "high"  # Always HIGH, never CRITICAL
        elif rec["dir_category"] == "prevention":
            if path_coverage >= 0.66:
                priority = "critical"  # Covers most paths
            else:
                priority = "high"
        elif path_coverage >= 1.0:
            priority = "critical"  # Covers ALL paths (even detect/respond)
        elif path_coverage >= 0.5:
            priority = "high"  # Covers half of paths
        else:
            priority = "medium"  # Low coverage
```

---

## Test Results: 02_minimal_defended

### Before Refinement
```
🔴 CRITICAL: 3 controls
🟡 HIGH: 9 controls
🔵 MEDIUM: 5 controls
```

### After Refinement
```
🔴 CRITICAL: 8 controls (+5)
🟡 HIGH: 8 controls (-1)
🔵 MEDIUM: 1 control (-4)
```

---

### Priority Changes (11 controls adjusted)

#### Hygiene Controls → HIGH ✅
```
🧹 vulnerability scanning: CRITICAL → HIGH (hygiene, 3 paths)
🧹 patching: HIGH → HIGH (hygiene, 3 paths) 
🧹 code signing: HIGH → HIGH (hygiene, 3 paths)
🧹 container scanning: MEDIUM → HIGH (hygiene, 0 paths)
🧹 secrets management: MEDIUM → HIGH (hygiene, 0 paths)
🧹 sbom: MEDIUM → HIGH (hygiene, 0 paths)
```

**Reason:** These are important baseline controls but don't actively block attacks in real-time.

---

#### Direct Controls → CRITICAL ✅
```
🛡️ backup: HIGH → CRITICAL (respond, 3/3 paths = 100%)
🛡️ logging: HIGH → CRITICAL (detect, 3/3 paths = 100%)
🛡️ audit log: HIGH → CRITICAL (detect, 3/3 paths = 100%)
🛡️ behavioral analysis: HIGH → CRITICAL (detect, 3/3 paths = 100%)
🛡️ input validation: HIGH → CRITICAL (prevention, 2/3 paths = 66%)
🛡️ api gateway: HIGH → CRITICAL (prevention, 2/3 paths = 66%)
```

**Reason:** These controls either cover all paths (100%) or meet the prevention threshold (66%).

---

#### Unchanged ✅
```
🛡️ least privilege: CRITICAL (isolate, 3 paths) - already correct
🛡️ rate limiting: CRITICAL (prevention, 2 paths) - already correct
```

---

## Metadata: Priority Refinement Transparency

Each control now includes `priority_refinement` metadata:

```json
{
  "control": "patching",
  "priority": "high",
  "priority_refinement": {
    "original": "high",
    "refined": "high",
    "reason": "hygiene control (reduces vulnerability surface)",
    "path_coverage": 1.0,
    "is_hygiene": true
  }
}
```

**Benefits:**
- Transparency: See why each priority was assigned
- Auditability: Track priority changes
- Debugging: Understand refinement logic

---

## Why Hygiene Controls Stay HIGH

**Question:** *"Why isn't patching CRITICAL if it covers all 3 paths?"*

**Answer:** **Effectiveness timing** - hygiene controls reduce **likelihood**, direct controls block **attempts**.

### Scenario: SQL Injection Attack

**With patching (hygiene):**
1. Vulnerability exists for 30 days before patch released
2. Attacker discovers vulnerability on day 15
3. Patch applied on day 35 (5 days after release)
4. **Window of exposure:** 20 days
5. **Effect:** Reduces likelihood, but doesn't stop attempts during window

**With input validation (direct prevention):**
1. Vulnerability may exist in underlying code
2. Attacker tries SQL injection
3. **Input validation blocks the attempt immediately**
4. **Window of exposure:** 0 seconds
5. **Effect:** Active blocking at runtime

**Both are important:**
- Patching = **reduces attack surface** (HIGH priority)
- Input Validation = **blocks active attacks** (CRITICAL priority)

---

## Confidence Impact

**Before refinement:** 99.5% (deterministic)  
**After refinement:** 99.5% (unchanged - only priority labels adjusted)

**Why no change:**
- Priority refinement is deterministic logic
- Based on existing validated data (attack_paths, dir_category)
- No new threat analysis, just better prioritization
- All existing validation still passes

---

## Business Value

### For CISOs

**Before refinement:**
- "We have 3 critical controls to implement"
- May miss important detection/response controls covering all paths

**After refinement:**
- "We have 8 critical controls to implement"
- Includes backup, logging, detection covering all attack paths
- More comprehensive security posture

**Resource allocation:**
1. **Week 1-2:** Implement 8 critical controls (entry/target + high coverage)
2. **Month 1-3:** Implement 8 high controls (hygiene + moderate coverage)
3. **Month 3-6:** Implement 1 medium control (low coverage)

---

### For Technical Teams

**Before:**
- "Patching covers all 3 paths but is only HIGH?"
- Confusing prioritization

**After:**
- "Patching is hygiene (HIGH), Input Validation is prevention (CRITICAL)"
- Clear distinction: hygiene vs direct blocking
- Metadata explains reasoning: `"reason": "hygiene control (reduces vulnerability surface)"`

---

## Hygiene Controls List

Complete list of controls classified as hygiene:

```python
HYGIENE_CONTROLS = {
    # Vulnerability Management
    "patching",
    "vulnerability scanning",
    "penetration testing",
    "security audit",
    
    # Supply Chain Security
    "code signing",
    "sbom",
    "container scanning",
    "dependency scanning",
    
    # Secrets Management
    "secrets management",
    
    # Security Testing
    "static analysis",
    "dynamic analysis",
    
    # Training
    "security training",
    "user training",
    
    # Compliance
    "compliance checks"
}
```

**Rationale:** These reduce the likelihood of vulnerabilities but don't actively block attacks at runtime.

---

## Examples by Architecture Type

### Traditional Web App (02_minimal_defended)
- **8 CRITICAL:** backup, logging, audit log, behavioral analysis, input validation, api gateway, least privilege, rate limiting
- **8 HIGH:** patching, code signing, network segmentation, container scanning, secrets management, sbom, dlp, web filtering
- **1 MEDIUM:** (low coverage controls)

### AI/ML System (21_agentic_ai_system)
- **CRITICAL:** MFA, WAF, Input Validation, Rate Limiting + Detection covering all 5 paths
- **HIGH:** User Training (hygiene), Patching (hygiene), AI-specific controls
- **MEDIUM:** Low-coverage enhancements

### Complex Enterprise (10_complex_enterprise)
- **CRITICAL:** Multi-path prevention + Detection/Response at critical nodes
- **HIGH:** Hygiene baseline + Moderate coverage controls
- **MEDIUM:** Defense-in-depth enhancements

---

## Future Enhancements (Phase 3C+)

**Phase 3C+ Orchestrator will add:**
- LLM validation of hygiene classification
- Context-aware priority refinement (e.g., "High-security environment → elevate hygiene to CRITICAL")
- Industry-specific adjustments (healthcare, finance)

**Example LLM refinement:**
- Architect: "This system processes PCI data, patching should be CRITICAL"
- Orchestrator: **Override hygiene rule, elevate to CRITICAL**

---

## Files Modified

**Code:**
- `chatbot/modules/ground_truth_generator.py` (+130 lines)
  - New function: `refine_control_priorities()`
  - Called after confidence adjustments
  - Adds `priority_refinement` metadata

- `chatbot/modules/layered_defense.py` (+30 lines)
  - Added `HYGIENE_CONTROLS` constant
  - Documentation of hygiene vs direct controls

**Documentation:**
- `docs/phases/phase3b_plus/PRIORITY_REFINEMENT.md` (this file)

---

## Validation Checklist

✅ Hygiene controls stay HIGH even with 100% path coverage  
✅ Direct controls promoted to CRITICAL if covering >= 66% paths  
✅ Detection/Response promoted to CRITICAL if covering 100% paths  
✅ Priority refinement metadata added for transparency  
✅ Tested on 02_minimal_defended (11 adjustments)  
✅ Backward compatible (priority field already exists)  
✅ No confidence impact (99.5% unchanged)  

---

## Related Documentation

- [PRIORITY_COLOR_CODING.md](PRIORITY_COLOR_CODING.md) - Visual color scheme
- [RAPIDS_CONSISTENCY.md](RAPIDS_CONSISTENCY.md) - Framework consistency
- [README.md](README.md) - Phase 3B++ overview
- [../phase3d/ROADMAP.md](../phase3d/ROADMAP.md) - Next phase plan

---

**Status:** ✅ Complete  
**Phase:** 3B++ (Priority Refinement)  
**Confidence:** 99.5% (unchanged)  
**Next:** Phase 3C+ (LLM-validated priorities)  
**Date:** 2026-05-17
