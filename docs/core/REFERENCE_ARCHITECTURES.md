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

## Current Status (2026-05-03) - Pre-Phase 3B

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

**Action Items (Phase 3B):**
1. ✓ WAF should not be treated as entry point for T1190
2. ✓ Entry should be "Internet" → WAF → ...
3. ✓ Update path detection to identify true external entries
4. ✓ Add DDIR assessment per hop (not just perimeter)
5. ✓ Check for SPOFs (none expected in this simple architecture)
6. ✓ Add resilience controls if needed

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
  • Perimeter-only defense (no depth)
  • Potential SPOF: AgentOrchestrator (needs verification)

Confidence Adjustments:
  • Least Privilege: 76% → 85% (MEDIUM → HIGH) ✓
  • WAF: 80% → 88% (HIGH) ✓
  • Rate Limiting: 74% → 82% (MEDIUM → HIGH) ✓
```

**Action Items (Phase 3B):**
1. ✓ "Users" entry → T1566 (Phishing) + T1078 (Valid Accounts), NOT T1190
2. ✓ T1190 only if truly internet-facing (e.g., public API endpoint)
3. ✓ RAPIDS should differentiate external vs internal threats
4. ✓ Add DDIR assessment for each hop (Users → WebUI → Orchestrator → LLM → VectorDB → DB)
5. ✓ Detect SPOF (likely: AgentOrchestrator as bottleneck)
6. ✓ Add resilience controls (circuit breaker, LLM rate limiting, auto-scaling)
7. ✓ AI-specific: Map prompt injection to closest MITRE + custom indicator

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

## Phase 3B Improvement Roadmap

### Phase 3B-1: Context-Aware Technique Mapping (HIGH PRIORITY)

**Problem**: T1190 (Exploit Public-Facing Application) incorrectly assigned to non-internet entries

**Fix**:
```python
# In map_path_to_techniques(), update logic:
def calculate_exploitability_threshold(present_controls):
    """Conservative: Assume CVE present unless defended."""
    if "patching" in present_controls and "vulnerability scanning" in present_controls:
        return 50  # Well-maintained (zero-day only)
    elif "waf" in present_controls:
        return 60  # WAF mitigates some CVEs
    else:
        return 70  # Assume known CVEs present

entry_label = nodes[path[0]].get("label", "").lower()

# Users/clients → phishing + credential theft
if any(kw in entry_label for kw in ["user", "client", "employee", "admin"]):
    techniques.append("T1566")  # Phishing
    techniques.append("T1078")  # Valid Accounts

# Internet → only if exploitable
elif any(kw in entry_label for kw in ["internet", "public", "external"]):
    threshold = calculate_exploitability_threshold(present_controls)
    app_vuln_risk = rapids.get("application_vulns", {}).get("risk", 0)
    
    if app_vuln_risk >= threshold:
        techniques.append("T1190")  # Exploitable
```

**Expected Impact**: Validation PASS rate: 0/2 → 2/2 (technique mapping)

---

### Phase 3B-2: Hop-Based Layered Defense + Resilience

**Problem**: Perimeter-only defense, no DDIR depth, no resilience assessment

**Fix**: New file `chatbot/modules/layered_defense.py`

```python
# Categorize each hop by descriptor (not position)
def categorize_hop_layer(node_label):
    # Returns: identity/network/device/application/data

# Assess DDIR (security) per hop
def assess_hop_ddir_coverage(hop, layer, present_controls):
    # Returns: {"prevent": bool, "detect": bool, "isolate": bool, "respond": bool}

# Assess resilience (availability) per hop
def assess_hop_resilience(hop, layer, present_controls):
    # Returns: {"prevent": bool, "detect": bool, "isolate": bool, "respond": bool}

# Detect SPOFs from graph topology
def identify_single_points_of_failure(nodes, edges):
    # Bottleneck: in-degree ≤ 1 AND out-degree ≥ 2
    # Bridge: Removing node disconnects critical assets

# Generate controls per hop
def generate_layered_defense(attack_paths, nodes, edges, present_controls, rapids):
    # Returns: DDIR + resilience recommendations per hop
```

**Expected Impact**: 
- Each hop assessed for security + resilience
- SPOFs identified (e.g., AgentOrchestrator in AI system)
- Depth added (not just breadth)

---

### Phase 3B-3: Breadth + Depth + Resilience Merge

**Problem**: Need to balance RAPIDS threats (breadth), DDIR (depth), and SPOF mitigation (resilience)

**Fix**: Update `chatbot/modules/rapids_driven_controls.py`

```python
def prioritize_breadth_and_depth_and_resilience(rapids_recs, layered_recs, resilience_recs, max_controls=12):
    """
    Triple-objective optimization:
    - Top 3 RAPIDS threats covered (breadth)
    - All 4 DDIR categories represented (depth)
    - SPOFs mitigated (resilience)
    - Prefer controls serving multiple objectives
    """
```

**Expected Impact**:
- 10-12 controls satisfying all three objectives
- Example: Logging serves insider threat (RAPIDS) + detect (DDIR)
- Security AND resilience weighted equally

---

### Phase 3B-4: Enhanced Validation

**Problem**: Only 2 validation checks (technique mapping), need 6 total

**Fix**: Update `chatbot/modules/self_validation.py`

```python
# Validation 1-2: Technique mapping (existing)
# Validation 3-4: Breadth & depth (NEW)
def validate_breadth_and_depth(control_recs, attack_paths, rapids, nodes):
    # Check: Top 3 RAPIDS covered
    # Check: All 4 DDIR represented
    # Check: Critical hops have ≥3 DDIR

# Validation 5-6: Resilience (NEW)
def validate_resilience_by_design(control_recs, attack_paths, nodes, edges, rapids):
    # Check: SPOFs mitigated
    # Check: Microservices have circuit breakers
    # Check: AI systems have LLM rate limiting
```

**Expected Impact**: Validation: 2/2 → 6/6 (100%)

---

### Phase 3B-5: Exposure + Insider Confidence

**Problem**: Flat confidence, doesn't account for exposure level

**Fix**: Update `chatbot/modules/confidence_scoring.py`

```python
def calculate_exposure_multiplier(architecture_type, rapids, attack_paths, nodes):
    exposure_score = 0
    # Internet: +10, Insider: +10, Privileged: +5, Complexity: +5, High-value: +5
    # Return multiplier: 0.95 to 1.15
```

**Expected Impact**: 
- High-exposure (25+): 90%+ confidence required
- Average confidence: 81% → 89%

---

### Phase 3B-6: Enhanced Reporting

**Problem**: Reports lack DDIR details, SPOF identification, assume breach scenarios

**Fix**: Update `chatbot/modules/threat_report.py`

- Add "Defense-in-Depth Analysis" (hop-by-hop table)
- Add "SPOF Mitigation" section
- Add "Assume Breach Analysis" scenarios
- Show specific placement (not generic)

---

## Success Criteria (Phase 3B)

### Validation PASS Checklist (6 Checks)

Architecture passes validation when:
- [ ] Technique Mapping (2 checks):
  - [ ] T1190 only when internet + exploitable
  - [ ] T1566/T1078 for user/insider entries
- [ ] Breadth & Depth (2 checks):
  - [ ] Top 3 RAPIDS threats have controls (≥2/3)
  - [ ] All 4 DDIR categories represented
  - [ ] Critical hops have ≥3 DDIR
  - [ ] Insider paths are depth-focused
- [ ] Resilience (2 checks):
  - [ ] SPOFs identified and mitigated
  - [ ] Microservices (≥3 services) have circuit breakers
  - [ ] AI systems have LLM rate limiting
  - [ ] High DoS risk → internal resilience controls

### Current Scores (Pre-Phase 3B)

| Architecture | Validation | Avg Confidence (Pre) | Avg Confidence (Post) | Target |
|--------------|-----------|---------------------|----------------------|--------|
| Minimal Defended | ✗ 0/2 | 74% | 78% (+4%) | 6/6, 87-89% |
| AI System | ✗ 0/2 | 78% | 84% (+6%) | 6/6, 91-93% |
| **AVERAGE** | **0/2 (0%)** | **76%** | **81% (+5%)** | **6/6 (100%), 89%** |

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
