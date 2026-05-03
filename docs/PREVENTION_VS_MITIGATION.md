# Prevention vs Mitigation: Critical Distinction

**Date:** 2026-05-03  
**Context:** Phase 3B Planning Clarification

---

## Core Concept

**Prevention** and **Mitigation** are fundamentally different defensive strategies:

### Prevention (Critical Controls)
**Goal:** STOP the attack path from advancing to the next hop

- If prevention succeeds → Attack path ENDS ✋
- These are "gates" that must be bypassed to continue
- Examples: WAF blocks exploit, MFA stops credential theft, Firewall blocks connection

### Mitigation (DDIR - Assume Breach)
**Goal:** Manage the attack when prevention FAILS

- If prevention fails → Attack continues, but we have defenses
- DETECT: Know attack is happening
- ISOLATE: Contain the breach
- RESPOND: Recover from impact
- Examples: Logging (detect), Network Segmentation (isolate), Backup (respond)

---

## Framework per Hop

```
┌─────────────────────────────────────────────────────┐
│ Hop: Internet → WAF → WebServer                     │
├─────────────────────────────────────────────────────┤
│                                                      │
│ PREVENTION (Critical Control)                       │
│ └─ WAF blocks OWASP Top 10 exploits                 │
│    ├─ Success: Attack STOPS here ✋                  │
│    └─ Failure: Attack proceeds to WebServer         │
│                                                      │
│ MITIGATION (Assume WAF Bypassed)                    │
│ ├─ DETECT: WAF logs all attempts, SIEM alerts       │
│ ├─ ISOLATE: Rate limiting contains flood            │
│ └─ RESPOND: Auto-block IP, update WAF rules         │
│                                                      │
└─────────────────────────────────────────────────────┘
```

**Key Point:** Prevention is PRIMARY. Mitigation is BACKUP (assume prevention failed).

---

## Examples by Architecture Layer

### Identity Layer (Users → Auth Service)

**PREVENTION:**
- MFA (multi-factor authentication)
  - Success: Stolen password alone is insufficient ✋
  - Failure: Attacker has password + MFA device

**MITIGATION (Assume MFA Bypassed):**
- DETECT: Login monitoring, behavioral analysis (unusual location/time)
- ISOLATE: Account lockout after suspicious activity, session timeout
- RESPOND: Force password reset, investigate compromise

---

### Network Layer (Internet → Firewall → Internal Network)

**PREVENTION:**
- Firewall rules (block unauthorized ports/protocols)
  - Success: Connection rejected ✋
  - Failure: Attacker finds allowed port/protocol

**MITIGATION (Assume Firewall Bypassed):**
- DETECT: IDS monitors traffic for malicious patterns
- ISOLATE: Network segmentation limits lateral movement
- RESPOND: Isolate compromised segment, kill connections

---

### Application Layer (WebUI → API → Backend Service)

**PREVENTION:**
- Input validation (reject malicious payloads)
  - Success: SQL injection blocked ✋
  - Failure: Attacker finds bypass (e.g., encoding trick)

**MITIGATION (Assume Injection Succeeded):**
- DETECT: Application logging, error monitoring, anomaly detection
- ISOLATE: Least privilege (DB user has limited permissions), parameterized queries
- RESPOND: Rollback transaction, patch vulnerability, incident response

---

### Data Layer (Application → Database)

**PREVENTION:**
- Database firewall (block unauthorized queries)
  - Success: DROP TABLE rejected ✋
  - Failure: Attacker crafts query that passes firewall

**MITIGATION (Assume Firewall Bypassed):**
- DETECT: Audit logging, DLP monitors data exports
- ISOLATE: Least privilege, column-level encryption
- RESPOND: Backup restore, forensic analysis

---

## Why BOTH Are Needed (Defense-in-Depth)

### Scenario: Ransomware Attack

**Prevention Controls:**
1. Email Gateway (blocks phishing email) ✋
2. EDR (blocks ransomware execution) ✋
3. Network Segmentation (blocks lateral movement) ✋

**What if ALL prevention fails?**

**Mitigation Controls (Assume Breach):**
- DETECT: EDR catches encryption activity, SIEM correlates events
- ISOLATE: Network segmentation slows spread, immutable backups safe from encryption
- RESPOND: Restore from backup, isolate infected hosts, incident response

**Result:** Even if ransomware encrypts some systems, organization recovers with minimal data loss.

---

## Terminology Clarification

### Old Framework (Confusing)
```
DDIR:
- DETER (Prevent)  ← Conflates prevention with deterrence
- DETECT
- ISOLATE
- RESPOND
```

**Problem:** "DETER" and "PREVENT" are different:
- PREVENT = Attack stops
- DETER = Attack continues but is harder

### New Framework (Clear)
```
Per Hop:

1. PREVENTION (Critical Control)
   └─ Blocks attack path advancement
   
2. MITIGATION (Assume Prevention Failed)
   ├─ DETECT: Visibility into breach
   ├─ ISOLATE: Contain damage
   └─ RESPOND: Recover from impact
```

**Note:** "DETER" is now part of prevention OR making mitigation harder (e.g., encryption deters data theft even if stolen).

---

## Phase 3B Implementation Impact

### Control Recommendations Format (Updated)

**Old Format:**
```
Recommendation: WAF
DDIR Category: DETER (Prevent)
```

**New Format:**
```
Recommendation: WAF (PREVENTION)
Purpose: Block OWASP Top 10 exploits at perimeter
If Bypassed (Mitigation):
├─ DETECT: WAF logging → SIEM
├─ ISOLATE: Rate limiting, IP blocking
└─ RESPOND: Update WAF rules, patch application
```

---

### Report Structure (Updated)

**Old:**
```markdown
## Control Recommendations

1. WAF (DDIR: PREVENT, RAPIDS: App Vulns)
2. Logging (DDIR: DETECT, RAPIDS: Insider)
3. Network Segmentation (DDIR: ISOLATE, RAPIDS: Ransomware)
```

**New:**
```markdown
## Defense Strategy: Prevention + Mitigation

### Hop 0→1: Internet → WebUI

**PREVENTION (Critical Control):**
- WAF (blocks OWASP Top 10)
  - If successful: Attack stops here ✋
  - RAPIDS: Application Vulns (80/100)
  - MITRE: M1050 (Exploit Protection) → T1190

**MITIGATION (Assume WAF Bypassed):**
- DETECT: WAF Logging + SIEM (correlation)
- ISOLATE: Rate Limiting (flood control), IP Blocking
- RESPOND: Auto-update WAF rules, alert SecOps

### Hop 1→2: WebUI → Database

**PREVENTION (Critical Control):**
- Input Validation (rejects SQL injection)
  - If successful: Attack stops here ✋
  - RAPIDS: Application Vulns (80/100)
  - MITRE: M1027 (Input Validation) → T1190

**MITIGATION (Assume Injection Succeeded):**
- DETECT: Database Audit Logs, DLP
- ISOLATE: Least Privilege (read-only), Database Firewall
- RESPOND: Rollback, Patch, Incident Response
```

---

## Prioritization Impact

### Old Approach (Conflated)
```
Budget: 10 controls
- 33% DETER (Prevent)
- 33% DETECT
- 17% ISOLATE
- 17% RESPOND
```

**Problem:** Doesn't distinguish critical prevention from mitigation.

### New Approach (Clear)
```
Budget: 10 controls

PREVENTION (40% - Critical)
└─ 4 controls that block attack paths
   Examples: WAF, MFA, Firewall, Input Validation

MITIGATION (60% - Assume Breach)
├─ DETECT (30%): 3 controls (Logging, SIEM, IDS)
├─ ISOLATE (20%): 2 controls (Network Seg, Least Privilege)
└─ RESPOND (10%): 1 control (Backup)
```

**Rationale:**
- Prevention is MOST critical (stop attack)
- But assume prevention fails → Need strong detection + isolation
- Response is backup plan (recover if all else fails)

---

## Validation Impact

### New Validation Check (Phase 3B-4)

**Validation: Prevention + Mitigation Coverage**

For each attack path:
- [ ] Each hop has ≥1 PREVENTION control (critical)
- [ ] Each hop has ≥2 MITIGATION controls (DETECT + ISOLATE minimum)
- [ ] Final hop (target) has RESPOND control (backup/recovery)

**Example:**
```
Path: Internet → WAF → WebServer → Database

Hop 0→1: 
- ✓ PREVENTION: WAF
- ✓ MITIGATION: Logging (DETECT), Rate Limiting (ISOLATE)

Hop 1→2:
- ✓ PREVENTION: Input Validation
- ✓ MITIGATION: Audit Log (DETECT), Least Privilege (ISOLATE)

Hop 2 (Target):
- ✓ PREVENTION: Database Firewall
- ✓ MITIGATION: DLP (DETECT), Encryption (ISOLATE), Backup (RESPOND)
```

---

## AI System Example (21_agentic_ai_system)

### Path: Users → WebUI → AgentOrchestrator → LLM → VectorDB → Database

**Hop 0→1: Users → WebUI**

PREVENTION:
- MFA (stops credential theft) ✋
- RAPIDS: Phishing (60/100), MITRE: T1566 → M1032 (MFA)

MITIGATION (Assume Credentials Stolen):
- DETECT: Login monitoring, behavioral analysis
- ISOLATE: Session timeout, account lockout
- RESPOND: Force password reset, investigate

---

**Hop 1→2: WebUI → AgentOrchestrator**

PREVENTION:
- Input Validation (rejects malicious payloads) ✋
- RAPIDS: Application Vulns (80/100), MITRE: T1190 → M1027

MITIGATION (Assume Validation Bypassed):
- DETECT: Application logging, error monitoring
- ISOLATE: Network Segmentation (WebUI ↔ Orchestrator), Rate Limiting
- RESPOND: Circuit breaker, auto-rollback

---

**Hop 2→3: AgentOrchestrator → LLM**

PREVENTION:
- Rate Limiting (prevents API quota exhaustion) ✋
- RAPIDS: DoS (85/100), Resilience: API quota protection

MITIGATION (Assume Rate Limit Bypassed):
- DETECT: API monitoring, latency alerts
- ISOLATE: Circuit breaker (stop calls if failing), Queue management
- RESPOND: Fallback to cached responses, scale out

---

**Hop 3→4: LLM → VectorDB**

PREVENTION:
- Access Control (only authorized services) ✋
- RAPIDS: Insider (70/100), MITRE: T1078 → M1026

MITIGATION (Assume Access Control Bypassed):
- DETECT: Query logging, anomaly detection
- ISOLATE: Least Privilege, Connection Pooling (limit connections)
- RESPOND: Kill suspicious connections, incident response

---

**Hop 4→5: VectorDB → Database (Target)**

PREVENTION:
- Database Firewall (blocks unauthorized queries) ✋
- RAPIDS: Application Vulns (80/100), MITRE: T1190 → M1033

MITIGATION (Assume Firewall Bypassed):
- DETECT: Audit logging, DLP (detect large exports)
- ISOLATE: Encryption at rest, Least Privilege
- RESPOND: Backup restore, forensic analysis

---

## Summary: Key Principles

1. **Prevention First:** Critical controls that STOP attack paths
2. **Mitigation Always:** Assume prevention fails, have backups
3. **Both Required:** Defense-in-depth = Prevention + Mitigation
4. **Clear Labels:** Don't conflate "DETER" with "PREVENT"
5. **Prioritization:** 40% Prevention (critical), 60% Mitigation (assume breach)
6. **Validation:** Every hop needs both prevention AND mitigation
7. **Reporting:** Show "If prevention fails → mitigation plan"

---

**Impact on Phase 3B:**
- Update terminology throughout
- Separate prevention from mitigation in reports
- Adjust control allocation (40/30/20/10 vs 33/33/17/17)
- Add prevention coverage to validation checks
- Show mitigation plan for each prevention control

---

**Document Version:** 1.0  
**Date:** 2026-05-03  
**Status:** Clarification for Phase 3B Implementation
