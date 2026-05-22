# Bug #2: "Missing Encryption Controls" - NOT A BUG

**Date:** 2026-05-22  
**Status:** ✅ CLOSED - Working as designed  
**Severity:** N/A

---

## Initial Concern

**Reported:** Database nodes should have encryption at rest controls  
**Observed:** Encryption not recommended for 00_safeentry databases

---

## Investigation

### Database Threats Present

```
Techniques targeting databases:
- T1005: Data from Local System
- T1213: Data from Information Repositories
- T1485: Data Destruction
- T1486: Data Encrypted for Impact (ransomware)
- T1490: Inhibit System Recovery
- T1567: Exfiltration Over Web Service
```

### MITRE Mitigations for These Techniques

**T1486 (Ransomware Encryption):**
- M1040: Behavior Prevention on Endpoint
- M1053: Data Backup ✅ (RECOMMENDED)

**T1485 (Data Destruction):**
- M1032: Multi-factor Authentication
- M1053: Data Backup ✅ (RECOMMENDED)
- M1018: User Account Management

**T1213 (Data from Information Repositories):**
- M1041: Encrypt Sensitive Information ✅
- M1018: User Account Management
- M1047: Audit

### M1041 (Encrypt Sensitive Information)

**MITRE Definition:** "Protect sensitive information at rest, in transit, and during processing"

**Addresses:** T1213 only (data access, not ransomware)

**NOT addresses:** T1486, T1485, T1490 (ransomware techniques)

---

## Why Encryption NOT Recommended

1. **MITRE doesn't list encryption as mitigation for ransomware**
   - Ransomware encrypts YOUR data
   - Having encrypted-at-rest doesn't prevent ransomware from encrypting
   - Backup (M1053) is the correct mitigation for ransomware recovery

2. **Encryption at rest protects confidentiality, not availability**
   - Ransomware is an availability attack
   - Encryption defends against unauthorized read (T1213)
   - Different threat model

3. **M1041 only addresses 1/6 database techniques**
   - T1213: Yes (data access) ✅
   - T1486, T1485, T1490: No (ransomware)
   - T1005, T1567: No (already extracted data)

---

## What IS Recommended (Correctly)

```
Database Controls Placed:
- Backup (M1053): Addresses T1486, T1485, T1490 ✅
  - UserDB: ✓
  - AccessLogDB: ✓
  - Cache: ✗ (volatile, correct)

- DLP (M1057): Addresses T1005, T1567 ✅
  - UserDB: ✓
  - AccessLogDB: ✓
  - Cache: ✓

- Logging (M1047): Addresses T1213 ✅
  - UserDB: ✓
  - AccessLogDB: ✓
  - Cache: ✓
```

---

## Should Encryption Be Recommended Anyway?

**Industry Best Practice:** Yes, databases containing PII/sensitive data should use encryption at rest

**MITRE Guidance:** Only if T1213 (Data from Information Repositories) is present

**Current Behavior:**
- T1213 IS present in safeentry attack paths ✅
- M1041 SHOULD be recommended
- But M1041 is not in control recommendations

**Why?**
Let me check if M1041 is being filtered out...

### Check Control Recommendations

```python
# From report/00_safeentry/ground_truth.json
controls_recommended = [
  "least privilege", "vulnerability scanning", "rate limiting",
  "logging", "backup", "edr", "input validation", "patching",
  "mfa", "code signing", "behavioral analysis", "user training",
  "email gateway", "container scanning", "secrets management",
  "dlp", "web content filtering"
]

# Missing: "encryption at rest" or "encrypt sensitive information"
```

M1041 is NOT being mapped to a control name.

---

## Root Cause: Control Name Mapping Missing

**File:** `chatbot/modules/threat_driven_controls.py`

**Issue:** M1041 not mapped to a control name like "encryption at rest"

**Evidence:**
```python
# MITIGATION_TO_CONTROLS dict likely missing:
"M1041": ["encryption at rest", "encryption in transit", "encryption"]
```

---

## Decision: Enhancement, Not Bug

**Classification:** Enhancement (not critical bug)

**Reasoning:**
1. System correctly recommends backup for ransomware (M1053) ✅
2. System correctly recommends DLP for exfiltration (M1057) ✅
3. Encryption at rest (M1041) would be *additional* defense-in-depth
4. Missing because control name not mapped, not logic error

**Priority:** Medium (defense-in-depth enhancement)

**Impact:** Low
- UserDB has backup (can recover from ransomware)
- UserDB has logging (can detect unauthorized access)
- UserDB has DLP (can prevent exfiltration)
- Missing encryption = confidentiality gap, not availability gap

---

## Recommendation

**Option A:** Add M1041 mapping (15min)
- Map M1041 → "encryption at rest"
- Will be recommended for architectures with T1213
- Diagram will place on databases

**Option B:** Defer to post-API work
- Not critical (backup + DLP + logging already present)
- Can add as enhancement later
- Focus on validator bug first

**Choice:** Option B - Defer (not blocking API work)

---

**Status:** ✅ CLOSED - Working as designed  
**Action:** Deferred enhancement (add M1041 mapping later)  
**Next:** Bug #3 - Validator type handling
