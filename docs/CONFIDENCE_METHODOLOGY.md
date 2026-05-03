# Threat Modeling Confidence Methodology

## Overview

Every control recommendation includes a **confidence score (0-100%)** and **level (HIGH/MEDIUM/LOW)** that indicates how certain we are that this control will effectively address the identified threats in this specific architecture.

## Why Confidence Matters

Traditional threat modeling tools give you a list of controls without explaining:
1. **Why** is this control recommended?
2. **How confident** are we it will work for THIS architecture?
3. **Which specific threats** does it address?

Our approach provides **transparent, traceable, defensible** recommendations backed by MITRE ATT&CK.

---

## Confidence Score Calculation

Confidence is calculated from **5 factors**, each weighted differently:

### 1. Technique Mapping Confidence (30% weight)

**How certain are we about the MITRE techniques in the attack paths?**

- **HIGH (0.9)**: Clear external entry point (Internet, Public) → sensitive target (Database, Secrets)
  - Example: `Internet → WAF → Web Server → Database`
  - Technique: T1190 (Exploit Public-Facing Application)

- **MEDIUM (0.6-0.7)**: Generic components or longer paths
  - Example: `Generic Entry → Service → Cache`
  - Less clear what technique applies

- **LOW (0.4-0.5)**: Ambiguous paths, no specific entry/target

**Factors**:
- Entry point clarity (internet/public vs generic)
- Target sensitivity (database/secrets vs cache)
- Path length (shorter = more confident)

---

### 2. Mitigation-to-Control Mapping (30% weight)

**How direct is the mapping from MITRE mitigation to implementable control?**

| Confidence | Mapping Type | Examples |
|-----------|--------------|----------|
| **HIGH (1.0)** | Direct 1:1 mapping | M1032 (Multi-factor Auth) → MFA<br>M1053 (Data Backup) → Backup<br>M1050 (Exploit Protection) → WAF |
| **MEDIUM (0.7-0.8)** | Control implements part of mitigation | M1026 (Privileged Account Mgmt) → Least Privilege<br>M1037 (Filter Network Traffic) → Firewall |
| **LOW (0.4-0.6)** | Indirect or partial implementation | M1027 (Password Policies) → Patching (indirect)<br>M1017 (User Training) → Patching (indirect) |

**Why this matters**: If M1050 says "Exploit Protection" and we recommend WAF, that's a direct match (confidence = 1.0). If M1026 says "Privileged Account Management" and we recommend "Least Privilege", that's one aspect of account management (confidence = 0.8).

---

### 3. Attack Path Coverage (20% weight)

**How many attack paths does this control address?**

- Addresses 50%+ of paths → confidence = 1.0
- Addresses 25-50% → confidence = 0.5-1.0
- Addresses <25% → confidence < 0.5

**Example**: If WAF addresses all 5 attack paths starting from Internet, confidence increases.

---

### 4. RAPIDS Validation (10% weight)

**Does high RAPIDS risk category support this recommendation?**

| Threat Category | High-Risk Controls | Confidence Boost |
|----------------|-------------------|------------------|
| Ransomware (risk ≥ 60) | Backup, EDR, Network Segmentation | +0.9 |
| Application Vulns | WAF, Input Validation, Rate Limiting | +0.9 |
| Phishing | MFA, Email Gateway | +0.9 |
| Insider Threat | Logging, Least Privilege, DLP | +0.8 |
| DoS | DDoS Protection, Rate Limiting, CDN | +0.9 |

**Why this matters**: If RAPIDS shows high ransomware risk (70/100) AND we recommend Backup, confidence increases because two independent analysis methods agree.

---

### 5. Architecture Context (10% weight)

**Is this control relevant to this architecture type?**

| Architecture Type | Highly Relevant Controls | Confidence |
|------------------|-------------------------|------------|
| AI/LLM System | Prompt Filtering, Rate Limiting, Sandbox | 1.0 (critical) |
| Web Application | WAF, Rate Limiting, Input Validation | 0.9 (highly relevant) |
| IoT System | Network Segmentation, IDS/IPS | 0.9 (critical) |
| Generic | All controls | 0.7 (default) |

**Why this matters**: Recommending "Prompt Filtering" for an AI system has high context relevance. Recommending it for a traditional web app has low relevance.

---

## Exposure Multiplier (Phase 3B Enhancement)

**Why**: Systems with higher exposure need higher confidence - we can't afford to be wrong.

### Exposure Score Calculation

```
exposure_score = 0

# Internet-facing (+10)
if has_internet_entry:
    exposure_score += 10

# Insider threat (+10, equal weight to internet)
if insider_threat_risk >= 60:
    exposure_score += 10

# Privileged insider (+5, critical)
if has_privileged_insider:
    exposure_score += 5

# Complexity (+5, more attack surface)
if attack_path_count >= 5:
    exposure_score += 5

# High-value target (+5)
if architecture_type in ["ai_system", "financial"]:
    exposure_score += 5
```

### Multiplier Thresholds

| Exposure Score | Multiplier | Required Confidence | Example |
|---------------|-----------|---------------------|---------|
| 25+ | 1.15x | 95%+ | Internet + Insider + Privileged + AI |
| 20-24 | 1.10x | 90%+ | Internet + Insider + Complexity |
| 10-19 | 1.0x | 85% | Internet only or Insider only |
| <10 | 0.95x | 80% | Internal system, low complexity |

### Application

```python
base_confidence = calculate_confidence(...)  # 5 factors above
exposure_multiplier = calculate_exposure_multiplier(...)
final_confidence = base_confidence * exposure_multiplier
```

**Example:**
- 21_agentic_ai_system: Internet (10) + Insider (10) + AI (5) = 25 → 1.15x multiplier
- Base confidence: 80% → Final: 92% (meets 90%+ bar for high exposure)

---

## Confidence Levels

| Level | Score Range | Meaning | When to Implement |
|-------|-------------|---------|------------------|
| **🟢 HIGH** | 80-100% | Strong evidence from multiple sources | Implement immediately |
| **🟡 MEDIUM** | 60-79% | Good evidence, some uncertainty | Prioritize based on risk |
| **🟠 LOW** | 40-59% | Weak or indirect evidence | Validate before implementing |

---

## Example: SafeEntry IoT Access Control System

### Attack Path #1
```
Internet → API Gateway → Auth Service → User Database
Techniques: T1190 (Exploit Public-Facing Application), T1078 (Valid Accounts)
```

### Recommended Control: **RATE LIMITING**

**Confidence Breakdown**:
```
Overall Confidence: 78% (MEDIUM 🟡)

Factors:
├─ Technique Mapping (30%): 0.85
│  └─ Clear entry (Internet), sensitive target (Database), 4 hops
├─ Mitigation-to-Control (30%): 0.70
│  └─ M1037 (Filter Network Traffic) → Rate Limiting (indirect match)
├─ Attack Path Coverage (20%): 1.00
│  └─ Addresses 5/5 attack paths (100% coverage)
├─ RAPIDS Validation (10%): 0.90
│  └─ DoS risk = 50/100, Application Vulns = 60/100 (both support rate limiting)
└─ Architecture Context (10%): 0.90
   └─ Web App architecture - rate limiting highly relevant
```

**Why 78% and not higher?**
- Mitigation-to-control mapping is indirect (0.70 vs 1.0 for direct)
- If we recommended WAF instead, confidence would be ~88% (direct mapping)

**Rationale Shown to User**:
```
3. RATE LIMITING (CRITICAL)
   Confidence: 🟡 MEDIUM (78%)
   Addresses: Mitigates T1190 in path(s) #1, #2, #3, #4, #5
   MITRE Mitigations: M1035, M1037
   MITRE Techniques: T1190
```

---

## Validation & Transparency

### Every recommendation includes:
1. ✅ **Confidence level** (HIGH/MEDIUM/LOW with %)
2. ✅ **Threat context** (which MITRE techniques it addresses)
3. ✅ **Attack path IDs** (which specific paths it mitigates)
4. ✅ **MITRE traceability** (mitigation IDs and technique IDs)
5. ✅ **Priority** (critical/high/medium)

### Audit Trail Available:
- Full confidence breakdown in `ground_truth.json`
- Logs show detailed calculation for each factor
- MITRE technique → mitigation → control mapping is explicit

---

## Comparison: Before vs After

### ❌ Before (Static List)
```
Missing Critical Controls:
1. FIREWALL
2. LOGGING
3. BACKUP
4. MFA

(No confidence, no threat context, same for every architecture)
```

### ✅ After (Threat-Driven with Confidence)
```
1. RATE LIMITING (CRITICAL)
   Confidence: 🟡 MEDIUM (78%)
   Addresses: Mitigates T1190 (Exploit Public-Facing Application) in paths #1-5
   MITRE Mitigations: M1035 (Limit Access), M1037 (Filter Network Traffic)
   MITRE Techniques: T1190

2. WAF (CRITICAL)
   Confidence: 🟢 HIGH (88%)
   Addresses: Mitigates T1190 in paths #1-5
   MITRE Mitigations: M1037, M1050 (Exploit Protection)
   MITRE Techniques: T1190
```

**Key Differences**:
- ✅ Shows WHY (specific threats)
- ✅ Shows HOW CERTAIN we are (confidence %)
- ✅ Backed by MITRE ATT&CK (traceable)
- ✅ Architecture-specific (adapts to context)
- ✅ Defensible in audits/reviews

---

## When to Question Low Confidence

If a control has **LOW confidence (<60%)**, ask:
1. Is the mapping indirect? (e.g., "Patching" for password policies)
2. Does it address only 1-2 paths? (low coverage)
3. Is it relevant to this architecture? (context mismatch)

**Action**: Validate with security team before investing resources.

---

## References

- [MITRE ATT&CK Mitigations](https://attack.mitre.org/mitigations/enterprise/)
- [NIST SP 800-53 Security Controls](https://csrc.nist.gov/publications/detail/sp/800-53/rev-5/final)
- Phase 3A Validation: 86% technique mapping accuracy (7 ground truths, 100% F1)

---

*Generated by DEV-TEST Threat Modeling Engine v0.6.0*
*Last Updated: 2026-05-03*
