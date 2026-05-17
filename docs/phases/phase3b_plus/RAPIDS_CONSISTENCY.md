# RAPIDS Control Consistency in Diagrams

**Date:** 2026-05-17  
**Context:** Phase 3B++ enhancement  
**Issue:** RAPIDS-only controls showed just name, no threat pattern/DIR context  

---

## Problem

**Before this fix:**

**MITRE controls** (with M####/T#### mappings):
```
MFA<br/>MITRE: M1032<br/>Prevents: T1078<br/>Paths: #1, #2
```

**RAPIDS-only controls** (no MITRE mapping):
```
SBOM  ← Just the name!
```

**User confusion:**
- What threat does SBOM address?
- Is it prevention or detection?
- Why does it have no MITRE context?

---

## Root Cause

RAPIDS-only controls (Supply Chain, Phishing, DoS, Ransomware) don't map to specific MITRE ATT&CK techniques:

```json
{
  "control": "sbom",
  "rapids_threats": ["supply_chain"],
  "dir_category": "prevention",
  "mitigations": [],  // ← Empty! No MITRE mapping
  "techniques": []    // ← Empty! No T#### techniques
}
```

Our code only showed MITRE info **if** mitigations/techniques existed:
```python
if mitigations:
    control_label += f"<br/>MITRE: {', '.join(mitigations)}"
# If no mitigations → control_label stays as just "SBOM"
```

---

## Solution: Show RAPIDS Framework Consistently

**New format for RAPIDS-only controls:**
```
SBOM<br/>RAPIDS: Supply Chain<br/>Prevention
User Training<br/>RAPIDS: Phishing, Ransomware<br/>Prevention
DDoS Protection<br/>RAPIDS: Dos<br/>Prevention
Container Scanning<br/>RAPIDS: Supply Chain<br/>Detect
```

**Pattern consistency:**
```
Framework: Category<br/>DIR Action
```

---

## Implementation

### Code Changes (threat_report.py)

**Extract RAPIDS threats:**
```python
rapids_threats = rec.get("rapids_threats", [])  # ['supply_chain']
```

**Show RAPIDS info if no MITRE mapping:**
```python
if mitigations:
    # MITRE control path
    control_label += f"<br/>MITRE: {', '.join(mitigations)}"
    control_label += f"<br/>{action_verb}: {', '.join(techniques)}"
elif rapids_threats and not mitigations:
    # RAPIDS-only control path
    rapids_categories = [t.replace('_', ' ').title() for t in rapids_threats[:2]]
    control_label += f"<br/>RAPIDS: {', '.join(rapids_categories)}"
    control_label += f"<br/>{dir_category.title()}"  # Prevention, Detect, etc.
```

**Logic:**
1. If `mitigations` exist → Show MITRE path (M####, T####)
2. If `rapids_threats` exist but no `mitigations` → Show RAPIDS path (category, DIR)
3. Both show consistent 2-line format after control name

---

## Examples by Control Type

### MITRE ATT&CK Controls
```
MFA<br/>MITRE: M1032<br/>Prevents: T1078, T1213<br/>Paths: #1, #2
Rate Limiting<br/>MITRE: M1033<br/>Prevents: T1059<br/>Paths: #1, #2, #3
DLP<br/>MITRE: M1057<br/>Contains: T1005, T1567
```

**Pattern:** `MITRE: M####<br/>Action: T####`

---

### RAPIDS Supply Chain Controls
```
SBOM<br/>RAPIDS: Supply Chain<br/>Prevention
Secrets Management<br/>RAPIDS: Supply Chain<br/>Prevention
Container Scanning<br/>RAPIDS: Supply Chain<br/>Detect
```

**Pattern:** `RAPIDS: Category<br/>DIR Action`

---

### RAPIDS Phishing/Ransomware Controls
```
User Training<br/>RAPIDS: Phishing, Ransomware<br/>Prevention
```

**Pattern:** Multiple RAPIDS categories shown (up to 2)

---

### RAPIDS DoS Controls
```
DDoS Protection<br/>RAPIDS: Dos<br/>Prevention
```

**Pattern:** Single RAPIDS category

---

## Test Results

### Architecture: 02_minimal_defended

**RAPIDS controls now consistent:**
- SBOM: `SBOM<br/>RAPIDS: Supply Chain<br/>Prevention` ✅
- Secrets Management: `Secrets Management<br/>RAPIDS: Supply Chain<br/>Prevention` ✅
- Container Scanning: `Container Scanning<br/>RAPIDS: Supply Chain<br/>Detect` ✅

**MITRE controls unchanged:**
- DLP: `DLP<br/>MITRE: M1057<br/>Contains: T1005, T1567` ✅
- MFA: `MFA<br/>MITRE: M1032<br/>Prevents: T1078, T1213` ✅

---

### Architecture: 22_generic_name_with_ai_nodes

**RAPIDS controls now consistent:**
- User Training: `User Training<br/>RAPIDS: Phishing, Ransomware<br/>Prevention` ✅
- DDoS Protection: `DDoS Protection<br/>RAPIDS: Dos<br/>Prevention` ✅

**MITRE controls unchanged:**
- Rate Limiting: `Rate Limiting<br/>MITRE: M1033<br/>Prevents: T1059` ✅

---

## Why No Attack Paths for RAPIDS Controls?

RAPIDS controls don't show `Paths: #1, #2` because:

1. **Attack paths are MITRE-specific**
   - Based on MITRE ATT&CK technique sequences
   - Example: `Internet → T1190 (Exploit) → T1059 (Command Execution)`

2. **RAPIDS controls are preventive/detective layers**
   - Don't break specific MITRE paths
   - Apply broadly across architecture
   - Example: SBOM prevents unknown dependencies, not specific T#### technique

3. **Data structure:**
   ```json
   {
     "control": "sbom",
     "attack_paths": [],  // ← Empty for RAPIDS-only
     "rapids_threats": ["supply_chain"]
   }
   ```

**Visual placement:** RAPIDS controls still connect to architecture nodes, just without path numbers.

---

## RAPIDS Threat Categories

| Category | Examples | DIR Category |
|----------|----------|--------------|
| **Supply Chain** | SBOM, Secrets Management, Container Scanning | Prevention/Detect |
| **Phishing** | User Training, Email Filtering | Prevention |
| **Ransomware** | Backup, User Training | Prevention/Response |
| **DoS** | DDoS Protection, Rate Limiting | Prevention |
| **Application Vulns** | WAF, Input Validation | Prevention |
| **Data Breach** | DLP, Encryption | Prevention/Detect |

---

## DIR Framework Actions

| DIR Category | Display | Meaning |
|--------------|---------|---------|
| `prevention` | Prevention | Stops attack from happening |
| `detect` | Detect | Identifies attack in progress |
| `isolate` | Isolate | Contains damage/spread |
| `respond` | Respond | Recovers after breach |

**RAPIDS controls use DIR category** instead of technique-specific verbs (Prevents/Detects/Contains/Recovers).

---

## Backward Compatibility

✅ **All existing functionality preserved:**
- MITRE controls show M####/T#### as before
- RAPIDS controls now show threat category + DIR
- No breaking changes to file formats
- No schema changes to ground_truth.json

✅ **Color coding still works:**
- RAPIDS controls get priority-based colors (red/yellow/blue/green)
- Based on `rapids_risk_score` and `priority` field

---

## Updated Legend

**Old legend:**
```mermaid
%% Format: Control Name<br/>MITRE: M####<br/>Addresses: T####
```

**New legend:**
```mermaid
%% Format: MITRE controls show M####/T####, RAPIDS controls show threat category
```

More accurate - acknowledges both MITRE and RAPIDS patterns.

---

## Code Diff Summary

**Lines changed:** ~15 lines in `threat_report.py`

**Key additions:**
1. Extract `rapids_threats` from recommendation
2. Add `elif rapids_threats and not mitigations:` branch
3. Format RAPIDS categories (replace underscores, title case)
4. Show DIR category as action

**Risk:** Zero - only affects label formatting, no logic changes

---

## Benefits

### For Users
1. **Consistent visual format** - all controls show framework + context
2. **Clear threat mapping** - know what each control addresses
3. **DIR visibility** - see prevention vs detection at a glance

### Example User Story
**Before:**
- User: "What does SBOM do? Why is it recommended?"
- Had to check ground_truth.json or docs

**After:**
- Diagram shows: `SBOM<br/>RAPIDS: Supply Chain<br/>Prevention`
- User: "Ah, it prevents supply chain attacks"

---

## Future Enhancements (Phase 3C+)

**Phase 3C+ orchestrator will add:**
- AI/ML controls: `ATLAS: T0051<br/>ARC: Safety<br/>Prevention`
- Custom patterns: `Finance: PCI-DSS<br/>Compliance<br/>Detect`

**Format remains consistent:**
```
Framework: Category<br/>Action/DIR
```

This establishes the pattern for all future threat frameworks.

---

## Files Modified

- `chatbot/modules/threat_report.py` (+15 lines)
  - Extract `rapids_threats` field
  - Add RAPIDS-only control branch
  - Format RAPIDS categories consistently

- `docs/phases/phase3b_plus/RAPIDS_CONSISTENCY.md` (this file)

---

## Validation Checklist

✅ RAPIDS controls show threat category  
✅ RAPIDS controls show DIR action  
✅ MITRE controls unchanged (M####/T####)  
✅ Color coding still works  
✅ Legend updated  
✅ Tested on 2 architectures  
✅ Backward compatible  

---

**Status:** ✅ Complete  
**Phase:** 3B++ (Visual Consistency)  
**Related:** PRIORITY_COLOR_CODING.md  
**Date:** 2026-05-17
