# Phase 3B Pre-Implementation Confidence Check

**Date:** 2026-05-03  
**Purpose:** 95% Confidence Check Before Coding (per CLAUDE.md guidelines)  
**Status:** Ready for Review

---

## Test Targets

### Confirmed Test Architectures (3 Total)

1. **00_safeentry.mmd** (IoT physical access control)
   - 15 nodes, entry: MobileApp
   - Controls: 0 present (vulnerable baseline)
   - Expected: High insider + IoT-specific threats

2. **02_minimal_defended.mmd** (Web app with controls)
   - 6 nodes, entry: Internet
   - Controls: 6 present (WAF, MFA, etc.)
   - Current issue: T1190 at WAF (should be at Internet)

3. **21_agentic_ai_system.mmd** (AI application)
   - 25 nodes, entry: Users
   - Controls: 2 present (Network Seg, Audit Log)
   - Current issue: T1190 at "Users" (should be T1566)

**Note:** SafeEntry was previously excluded from Phase 3A validation but should be included for Phase 3B testing.

---

## Phase 3B-1: Context-Aware Technique Mapping

### What Needs to Change

**File:** `chatbot/modules/ground_truth_generator.py`

**Function 1: calculate_exploitability_threshold() - NEW**

```python
def calculate_exploitability_threshold(present_controls: Set[str]) -> int:
    """
    Determine app vuln threshold for T1190 based on defensive posture.
    
    Conservative assumption: If not actively defended, assume CVE present.
    
    Returns:
        int: Risk threshold (50-70). T1190 applies if app_vuln_risk >= threshold.
    """
    has_waf = "waf" in present_controls
    has_patching = "patching" in present_controls
    has_vuln_scanning = "vulnerability scanning" in present_controls
    
    if has_patching and has_vuln_scanning:
        return 50  # Well-maintained (zero-day risk only)
    elif has_waf:
        return 60  # WAF mitigates some known CVEs
    else:
        return 70  # Assume known CVEs present (conservative)
```

**Confidence:** ✅ 95%+ (logic is clear, discussed extensively)

---

**Function 2: map_path_to_techniques() - UPDATE**

Current location: ~line 450 in ground_truth_generator.py

```python
def map_path_to_techniques(
    path: List[str],
    nodes: Dict[str, Dict],
    present_controls: Set[str],
    rapids: Dict
) -> List[str]:
    """Map attack path to MITRE techniques based on entry/target/context."""
    
    techniques = []
    entry_label = nodes[path[0]].get("label", "").lower()
    target_label = nodes[path[-1]].get("label", "").lower() if len(path) > 1 else ""
    
    # NEW: User/Insider entries → Phishing + Valid Accounts
    if any(kw in entry_label for kw in ["user", "admin", "employee", "client", "mobile"]):
        techniques.append("T1566")  # Phishing
        techniques.append("T1078")  # Valid Accounts
    
    # NEW: Internet entries → Only if exploitable
    elif any(kw in entry_label for kw in ["internet", "public", "external"]):
        threshold = calculate_exploitability_threshold(present_controls)
        app_vuln_risk = rapids.get("application_vulns", {}).get("risk", 0)
        
        if app_vuln_risk >= threshold:
            techniques.append("T1190")  # Exploit Public-Facing Application
    
    # Existing logic for other techniques...
    # (Keep existing checks for T1213, T1059, etc.)
    
    return techniques
```

**Confidence Check:**
- ✅ Logic is correct (discussed and validated)
- ⚠️ Need to READ current implementation first (95% confidence rule)
- ⚠️ Need to verify RAPIDS key names match ("application_vulns")
- ⚠️ Need to test with all 3 architectures

**Confidence:** 🟡 85% (need to read current code first)

---

### Expected Results

**00_safeentry.mmd:**
- Entry: "MobileApp" → Should map to T1078 (Valid Accounts), possibly T1566
- No T1190 (not internet-facing)
- Validation: Should PASS technique mapping

**02_minimal_defended.mmd:**
- Entry: "Internet" → Check app_vuln_risk vs threshold
- Has WAF → threshold = 60
- If app_vuln_risk ≥ 60 → T1190 ✓
- Validation: Should PASS technique mapping

**21_agentic_ai_system.mmd:**
- Entry: "Users" → Should map to T1566 + T1078 (NOT T1190)
- Validation: Should PASS technique mapping (was FAIL before)

**Overall:** 2/3 → 3/3 validation pass rate

---

## Residual Risk Assessment (NEW REQUIREMENT)

### What is Residual Risk?

**Residual Risk = Risk remaining AFTER all recommended controls are implemented**

No silver bullet. Even with all controls, there's always risk:
- Zero-day exploits (no patch available)
- Insider threats (authorized access abused)
- Advanced Persistent Threats (APT with significant resources)
- Human error (misconfiguration, social engineering)
- Supply chain compromise (trusted vendor compromised)

---

### Residual Risk Categories

#### 1. Inherent Limitations
**Risk:** Controls can't prevent 100% of attacks

Examples:
- **Zero-day exploits:** WAF blocks known CVEs, but not zero-days
- **APT techniques:** Advanced attackers can bypass standard controls
- **Social engineering:** MFA stops stolen passwords, but not user coercion

**Acceptance Criteria:** Document known limitations, monitor threat landscape

---

#### 2. Implementation Gaps
**Risk:** Controls implemented but not optimally configured

Examples:
- **Logging without correlation:** Logs exist but no SIEM to correlate
- **Network segmentation gaps:** Some flows bypass segmentation
- **Backup without testing:** Backups exist but never tested restore

**Acceptance Criteria:** Regular audits, penetration testing, incident drills

---

#### 3. Emerging Threats
**Risk:** New attack vectors not yet covered by controls

Examples:
- **AI-specific:** Prompt injection, model poisoning (no mature controls yet)
- **Supply chain:** New dependencies added without vetting
- **Cloud misconfig:** New cloud services deployed without security review

**Acceptance Criteria:** Continuous monitoring, threat intelligence, security champions

---

#### 4. Resource Constraints
**Risk:** Can't implement all recommended controls due to budget/time

Examples:
- **Budget:** Can only implement 6 of 10 recommended controls
- **Skills:** No expertise to operate SIEM effectively
- **Performance:** Encryption at rest impacts database performance

**Acceptance Criteria:** Risk-based prioritization, plan to add controls over time

---

### Residual Risk Scoring

**Formula:**
```
Residual Risk Score = (Initial RAPIDS Risk) * (1 - Control Effectiveness)

Control Effectiveness (Starting Conservative Values):
- Prevention controls: 70-90% effective (can be bypassed)
- Detection controls: 60-80% effective (may miss sophisticated attacks)
- Isolation controls: 50-70% effective (can be circumvented)
- Response controls: 40-60% effective (damage may already be done)
```

**IMPORTANT PRINCIPLES (User Guidance):**

1. **More Controls ≠ More Secure**
   - 20 weak controls < 5 well-designed controls
   - Focus on control QUALITY and VERIFICATION, not quantity
   - Example: 10 logging tools without correlation < 1 SIEM with proper tuning

2. **Controls Should NOT Be Static**
   - Architecture evolves → Controls must evolve
   - New threats emerge → Controls must adapt
   - Technology changes → Controls must be re-evaluated
   - Example: WAF rules from 2020 may not catch 2026 attacks

3. **Zero Trust Mindset**
   - Design matters: Assume controls will fail
   - Verification matters: Test controls regularly (pentesting, red team)
   - Layering matters: Defense-in-depth with overlapping controls
   - Example: Don't just deploy MFA, verify it can't be bypassed

4. **Architecture-Specific Effectiveness**
   - WAF 70% effective for web apps, but only 40% for API-first architectures
   - Encryption 90% effective for data at rest, but only if keys are secured
   - Network segmentation 65% effective if enforced, 20% if misconfigured

**Future Enhancement:**
- Phase 3C: LLM judges control effectiveness per architecture
- Phase 4: Control verification testing framework
- Ongoing: Update effectiveness based on pentesting results

**Example (21_agentic_ai_system):**

Initial RAPIDS:
- DoS Risk: 85/100
- Application Vulns: 80/100
- Insider Threat: 70/100

Recommended Controls:
- Rate Limiting (PREVENTION, 80% effective against DoS)
- WAF (PREVENTION, 70% effective against app vulns)
- Logging (DETECTION, 60% effective against insider)

Residual Risk:
- DoS: 85 * (1 - 0.80) = 17/100 (LOW, acceptable)
- Application Vulns: 80 * (1 - 0.70) = 24/100 (LOW-MEDIUM, acceptable)
- Insider Threat: 70 * (1 - 0.60) = 28/100 (MEDIUM, acceptable with monitoring)

**Overall Residual Risk: ~23/100 (LOW-MEDIUM, acceptable)**

---

### Residual Risk Report Section (NEW)

**Format:**
```markdown
## Residual Risk Assessment

Even with all recommended controls implemented, residual risk remains:

### Quantitative Assessment

| Threat Category | Initial Risk | Control Effectiveness | Residual Risk | Status |
|----------------|--------------|----------------------|---------------|--------|
| DoS | 85/100 | 80% (Rate Limiting) | 17/100 | ⚠️ MONITOR |
| Application Vulns | 80/100 | 70% (WAF) | 24/100 | ❌ MITIGATE |
| Insider Threat | 70/100 | 60% (Logging) | 28/100 | ❌ MITIGATE |
| Ransomware | 60/100 | 85% (Backup) | 9/100 | ✅ ACCEPT |

**Overall Residual Risk: 19.5/100 (MEDIUM, REQUIRES ACTION)**

**Updated Thresholds (Per User):**
- **< 10:** ✅ ACCEPT
- **10-20:** ⚠️ MONITOR (quarterly review)
- **> 20:** ❌ MITIGATE (need additional controls)

### Qualitative Assessment

**Inherent Limitations:**
- ⚠️ Zero-day exploits may bypass WAF (no patch available)
- ⚠️ Advanced APT techniques may evade detection
- ⚠️ Insider with admin privileges can bypass many controls

**Recommended Risk Acceptance:**
1. **Accept:** Low residual risks (< 20/100) with monitoring
2. **Monitor:** Medium residual risks (20-40/100) with quarterly reviews
3. **Mitigate:** High residual risks (> 40/100) require additional controls

**Continuous Improvement:**
- Quarterly threat landscape review
- Annual penetration testing
- Incident response drills (bi-annual)
- Security awareness training (quarterly)
- Vulnerability scanning (continuous)

### Risk Ownership

**Recommended Risk Owners:**
- DoS Risk (17/100): Infrastructure Team
- Application Vulns (24/100): Development Team + AppSec
- Insider Threat (28/100): Security Operations + HR
- Overall Residual Risk: CISO / Security Leadership

**Acceptance Signature Required:** (Business Owner / CISO)
- [ ] I acknowledge the residual risks documented above
- [ ] I accept these risks are within organizational risk appetite
- [ ] I commit to quarterly reviews and continuous improvement

Date: ___________  Signature: ___________
```

---

## Implementation Confidence Check

### Phase 3B-1: Context-Aware Technique Mapping

**Before Starting:**
- [ ] Read current `ground_truth_generator.py` implementation
- [ ] Verify `map_path_to_techniques()` location and structure
- [ ] Check RAPIDS key names match ("application_vulns")
- [ ] Confirm present_controls format (Set[str] with lowercase)
- [ ] Review test architectures (safeentry, minimal_defended, agentic_ai)

**Confidence After Reading:**
- Target: 95%+ before writing code
- If < 95%: Ask clarifying questions
- If ≥ 95%: Proceed with implementation

**Testing Plan:**
1. Regenerate all 3 test architectures
2. Check technique mapping in ground_truth.json
3. Verify validation results (3/3 pass expected)
4. Review reports for correctness

---

### Residual Risk Assessment

**Before Starting:**
- [ ] Define control effectiveness percentages (research-based)
- [ ] Create residual risk calculation function
- [ ] Integrate into report generation
- [ ] Add acceptance signature section to reports

**Confidence:**
- Logic: ✅ 95% (formula is straightforward)
- Effectiveness values: 🟡 70% (need industry benchmarks)
- Integration: ✅ 90% (know where to add in threat_report.py)

**Research Needed:**
- Industry-standard control effectiveness rates
- NIST, CIS, or other framework references
- Typical residual risk acceptance thresholds

---

## Questions Before Implementation

### 1. Test Architectures ✅ CONFIRMED
**Question:** SafeEntry was excluded in Phase 3A. Should we include it now for Phase 3B testing?

**User Answer:** ✅ YES - All 3 architectures in report/ folder:
- 00_safeentry
- 02_minimal_defended  
- 21_agentic_ai_system

**Confidence Impact:** ✅ 85% → 95% (confirmed)

---

### 2. Control Effectiveness Values ✅ CONFIRMED (with caveats)
**Question:** What control effectiveness percentages should we use?

**User Answer:** ✅ YES, use conservative 60-90% as START, but:
- **CRITICAL:** Controls should NOT be static
- **IMPORTANT:** More controls ≠ More secure
- **PRINCIPLE:** Design and control verification matters (zero trust angle)
- **FUTURE:** Explore more effective controls based on architecture context

**Starting Values (Conservative):**
- Prevention: 70-90% effective
- Detection: 60-80% effective  
- Isolation: 50-70% effective
- Response: 40-60% effective

**Future Enhancement:** Architecture-specific effectiveness (e.g., WAF 70% for web, but only 40% for API-first architectures)

**Confidence Impact:** ✅ 70% → 95% (confirmed with evolution path)

---

### 3. Residual Risk Thresholds ✅ CONFIRMED (ADJUSTED)
**Question:** What residual risk levels are "acceptable"?

**User Answer:** ✅ ADJUSTED thresholds (more stringent):
- **< 10:** ✅ ACCEPT (low risk)
- **10-20:** ⚠️ MONITOR (medium risk, quarterly review)
- **> 20:** ❌ MITIGATE (high risk, need more controls)

**Rationale:** More conservative than initial proposal (was < 20 accept). Reflects zero-trust mindset - keep residual risk as low as possible.

**Confidence Impact:** ✅ 95% (confirmed, more stringent is better)

---

### 4. Report Location ✅ CONFIRMED
**Question:** Where should residual risk section appear in reports?

**User Answer:** ✅ YES, technical report + executive mention, but:
- **IMPORTANT:** Depth differs by audience
  - Executive: High-level summary (quantitative table + acceptance decision)
  - Technical: Detailed analysis (qualitative + mitigation recommendations)
  - Action Plan: Residual risk monitoring tasks

**Implementation:**
- Executive Summary: 1-2 paragraphs + table
- Technical Report: Full residual risk section (2-3 pages)
- Action Plan: Monitoring tasks for residual risks

**Confidence Impact:** ✅ 95% (confirmed with audience-specific depth)

---

## Confidence Summary (UPDATED with User Answers)

| Component | Before | After User Confirmation | Blocker? |
|-----------|--------|------------------------|----------|
| Technique Mapping Logic | ✅ 95% | ✅ 95% | No |
| Test Architecture Setup | 🟡 85% | ✅ 95% | **CLEARED** |
| Residual Risk Formula | ✅ 95% | ✅ 95% | No |
| Control Effectiveness | 🟡 70% | ✅ 95% | **CLEARED** |
| Residual Risk Thresholds | 🟡 85% | ✅ 95% | **CLEARED** |
| Report Integration | ✅ 90% | ✅ 95% | No |

**Overall Confidence: ✅ 95%+**

**All Blockers Cleared:**
1. ✅ SafeEntry confirmed in test set (report/00_safeentry)
2. ✅ Control effectiveness values confirmed (conservative 60-90%, evolve later)
3. ✅ Residual risk thresholds adjusted (< 10 accept, 10-20 monitor, > 20 mitigate)
4. ✅ Report structure confirmed (audience-specific depth)

**Recommendation:** ✅ READY TO START PHASE 3B-1 IMPLEMENTATION

---

## Pre-Implementation Checklist

**Before Phase 3B-1:**
- [ ] User confirms: SafeEntry included in test set?
- [ ] Read: chatbot/modules/ground_truth_generator.py (current implementation)
- [ ] Verify: RAPIDS key names, present_controls format
- [ ] Confirm: Residual risk effectiveness values (60-80% conservative range)
- [ ] Confirm: Residual risk thresholds (< 20 = acceptable, 20-40 = monitor, > 40 = mitigate)
- [ ] Review: All 3 test architecture .mmd files

**Confidence Target:** ≥ 95% before writing any code

---

**Document Version:** 1.0  
**Date:** 2026-05-03  
**Status:** Ready for User Review and Confidence Check
