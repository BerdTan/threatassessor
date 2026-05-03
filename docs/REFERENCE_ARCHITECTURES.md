# Reference Architecture Test Suite

## Overview

Two architectures serve as **validation benchmarks** for the threat modeling engine:
1. **02_minimal_defended.mmd** - Web application with existing controls
2. **21_agentic_ai_system.mmd** - AI/LLM application

These are used to:
- ✅ Validate MITRE technique mapping accuracy
- ✅ Test RAPIDS assessment calibration
- ✅ Verify control recommendation relevance
- ✅ Measure confidence scoring effectiveness
- ✅ Identify areas for improvement

---

## Current Status (2026-05-03)

### 02_minimal_defended.mmd (Web App with Controls)

**Architecture**: 6 nodes, 5 edges  
**Entry Points**: Internet, WAF, WebServer  
**Controls Present**: 6 (EDR, Encryption, Firewall, Load Balancer, MFA, WAF)

**Validation Results**:
```
✗ FAIL (1 issue)
Issues:
  • Path #3: T1190 marked but entry is "WAF" (control, not entry)

Confidence Adjustments:
  • Application Whitelisting: +8.0% ✓
  • Patching: +5.5% ✓
  • Rate Limiting: +5.5% ✓
```

**Action Items**:
1. WAF should not be treated as entry point for T1190
2. Entry should be "Internet" → WAF → ...
3. Update path detection to identify true external entries

---

### 21_agentic_ai_system.mmd (AI Application)

**Architecture**: 25 nodes, 24 edges  
**Entry Points**: Users, WebUI, AgentOrchestrator  
**Controls Present**: 2 (Network Segmentation, Audit Log)

**Validation Results**:
```
✗ FAIL (6 issues)
Issues:
  • Paths #1-5: T1190 marked but entry is "Users" not "Internet"
  • RAPIDS: No public entry but HIGH app vuln risk (may be overestimated)

Confidence Adjustments:
  • Least Privilege: 76% → 85% (MEDIUM → HIGH) ✓
  • WAF: 80% → 88% (HIGH) ✓
  • Rate Limiting: 74% → 82% (MEDIUM → HIGH) ✓
```

**Action Items**:
1. For AI systems, users access via WebUI - should be T1078 or internal threats
2. T1190 only if truly internet-facing (e.g., public API endpoint)
3. RAPIDS should lower app vuln risk if no public entry (unless internal threats)
4. Consider AI-specific techniques (prompt injection = different technique?)

---

## How to Use This Test Suite

### 1. Run Tests

```bash
# Generate reports for both reference architectures
for arch in 02_minimal_defended 21_agentic_ai_system; do
    python3 -m chatbot.main --gen-arch-truth tests/data/architectures/${arch}.mmd
done
```

### 2. Review Validation Results

Check logs for:
- ✓ Validation PASS/FAIL
- ✓ Issues found (technique mismatches, RAPIDS misalignments)
- ✓ Confidence adjustments (+/- %)

### 3. Compare Reports

```bash
# View technical reports
cat report/02_minimal_defended/02_technical_report.md  
cat report/21_agentic_ai_system/02_technical_report.md
```

### 4. Measure Accuracy

| Metric | Current | Target |
|--------|---------|--------|
| Validation PASS Rate | 0/2 (0%) | 2/2 (100%) |
| Average Confidence (before validation) | 74-78% | 75-85% |
| Average Confidence (after validation) | 78-84% | 80-90% |
| Technique Mapping Accuracy | ~85% | 95%+ |

---

## Improvement Roadmap

### Phase 1: Fix Entry Point Detection (HIGH PRIORITY)

**Problem**: T1190 (Exploit Public-Facing Application) incorrectly assigned to non-internet entries

**Fix**:
```python
# In map_path_to_techniques(), update logic:
entry_label = nodes[path[0]].get("label", "").lower()

# STRICT check for T1190
if any(kw in entry_label for kw in ["internet", "public", "external network"]):
    techniques.append("T1190")

# Users/clients → phishing or valid accounts
elif any(kw in entry_label for kw in ["user", "client", "employee"]):
    techniques.append("T1566")  # Phishing
    techniques.append("T1078")  # Valid Accounts (if auth present)
```

**Expected Impact**: Validation PASS rate: 0% → 50% (1/2)

---

### Phase 2: RAPIDS Calibration

**Problem**: AI system has HIGH app vuln risk without public entry

**Fix**:
```python
# In assess_rapids_risks(), adjust for entry point context
if architecture_type == "ai_system":
    has_public_entry = any(...)
    
    if not has_public_entry:
        # Internal AI system - lower external threat risk
        app_vuln_risk -= 20
        dos_risk -= 15
        # But increase insider/data poisoning risk
        insider_risk += 15
```

**Expected Impact**: RAPIDS alignment: 67% → 100%

---

### Phase 3: AI-Specific Techniques

**Problem**: Prompt injection not represented in MITRE ATT&CK techniques

**Solution**: Map to closest MITRE techniques + add custom indicators
```python
# For AI/LLM components, add:
if any(kw in path_str for kw in ["llm", "agent", "prompt", "model"]):
    techniques.append("T1059")  # Command Injection (closest match)
    techniques.append("T1190")  # If public-facing
    # Add custom indicator for reporting
    ai_specific_threats.append("Prompt Injection (no MITRE ID)")
```

**Expected Impact**: AI threat coverage: 70% → 90%

---

### Phase 4: Confidence Target: 85%+

**Current**: Most controls are 71-78% (MEDIUM)  
**Target**: 80-90% (HIGH) for direct mappings

**Actions**:
1. ✅ Validation increases confidence by 5-10% (implemented)
2. Add architecture context validation (+5%)
3. Cross-reference with CVE data for patching (+5%)
4. Industry benchmarks (e.g., NIST, CIS) alignment (+5%)

**Expected Impact**: Average confidence: 75% → 85%

---

## Success Criteria

### Validation PASS Checklist

Architecture passes validation when:
- [ ] All MITRE techniques justified by entry/target/path
- [ ] RAPIDS scores align with controls present/missing
- [ ] Control recommendations trace to techniques
- [ ] Confidence ≥ 80% for ≥50% of recommendations
- [ ] No critical validation issues

### Current Scores

| Architecture | Validation | Avg Confidence (Pre) | Avg Confidence (Post) |
|--------------|-----------|---------------------|----------------------|
| Minimal Defended | ✗ FAIL | 74% | 78% (+4%) |
| AI System | ✗ FAIL | 78% | 84% (+6%) |
| **AVERAGE** | **0/2 (0%)** | **76%** | **81% (+5%)** |

---

## Continuous Improvement Process

1. **Run tests weekly** on the 2 reference architectures
2. **Track metrics**: validation pass rate, confidence scores, technique accuracy
3. **Fix issues** found by self-validation
4. **Add new reference architectures** as patterns emerge (cloud, kubernetes, IoT, etc.)
5. **Update this document** with latest results

---

## Validation Log

### 2026-05-03 - Initial Self-Validation Implementation

**Findings**:
- ✗ 0/2 architectures pass validation
- ✓ Confidence increases by average 5% after validation
- ✗ Entry point detection needs improvement (T1190 misapplied)
- ✓ Control-technique mappings generally valid (80%+ alignment)
- ✗ RAPIDS needs calibration for non-public-facing systems

**Actions Taken**:
1. Implemented self-validation framework ✓
2. Added confidence adjustment based on validation ✓
3. Documented issues for Phase 1 fixes ✓

**Next**:
- Fix entry point detection logic (Priority 1)
- Retest and update metrics

---

## References

- [MITRE ATT&CK Enterprise Matrix](https://attack.mitre.org/matrices/enterprise/)
- [NIST Cybersecurity Framework](https://www.nist.gov/cyberframework)
- Phase 3A Validation: 86% accuracy on technique mapping

---

*Last Updated: 2026-05-03*  
*Status: Self-Validation v1.0 - 0/2 PASS, 81% avg confidence*
