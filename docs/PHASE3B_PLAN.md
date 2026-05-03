# Phase 3B Implementation Plan: DDIR + Resilience Enhancement

**Status:** Planned - Ready for Implementation  
**Start Date:** TBD  
**Estimated Duration:** ~13 hours (6 phases)  
**Version:** 1.0  
**Last Updated:** 2026-05-03

---

## Executive Summary

**Goal:** Enhance threat modeling with defense-in-depth (DDIR) and resilience by design (DDIRR) to achieve 100% validation pass rate and 89% average confidence.

**Current State:**
- Validation pass rate: 0/2 (found real issues)
- Average confidence: 81%
- Issues: T1190 misapplied, perimeter-only defense, no resilience assessment

**Target State:**
- Validation pass rate: 6/6 (100%)
- Average confidence: 89%
- Breadth (RAPIDS) + Depth (DDIR) + Resilience (DDIRR) all satisfied

---

## Core Philosophy

### Three-Pillar Approach

```
┌─────────────────────────────────────────────────────────┐
│ PILLAR 1: Threat Model (WHAT to defend against)        │
├─────────────────────────────────────────────────────────┤
│ • MITRE ATT&CK: Technique traceability & validation     │
│ • RAPIDS: Risk-driven threat prioritization            │
│ • Result: Identifies threats (breadth of coverage)      │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│ PILLAR 2: DDIR Defense (HOW to defend at each layer)   │
├─────────────────────────────────────────────────────────┤
│ • DETER (Prevent): WAF, MFA, Encryption                 │
│ • DETECT: Logging, IDS, Monitoring                      │
│ • ISOLATE: Network Segmentation, Circuit Breaker        │
│ • RESPOND: Backup, Incident Response, Failover          │
│ • Result: Depth at each hop, assume breach mindset      │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│ PILLAR 3: Resilience (WHY architecture must be robust) │
├─────────────────────────────────────────────────────────┤
│ • DDIRR: DDIR + Resilience by design                    │
│ • SPOF detection & mitigation                           │
│ • Internal DoS protection (not just perimeter)          │
│ • Result: Availability throughout, no cascading failure │
└─────────────────────────────────────────────────────────┘
```

**Integration Formula:**
```
MITRE + RAPIDS → Threat Model
DDIR → Breadth & Depth (security)
DDIRR → Resilience (availability)

Result: Secure AND Resilient Architecture
```

---

## Key Design Decisions

### 1. Context-Aware Technique Mapping

**Problem:** T1190 (Exploit Public-Facing Application) assigned to all internet-facing systems, regardless of vulnerability state.

**Solution:** Exploitability thresholds based on controls present

```python
# Deterministic CVE assumption
has_patching + has_vuln_scanning → threshold = 50 (zero-day risk only)
has_waf → threshold = 60 (some CVE mitigation)
Neither → threshold = 70 (assume known CVEs present)

# T1190 only if BOTH:
1. Internet-facing entry (not "Users")
2. app_vuln_risk ≥ threshold
```

**User/Insider Entries:**
```python
Entry = "Users", "Admin", "Employee" → T1566 (Phishing) + T1078 (Valid Accounts)
NOT T1190 (they don't exploit apps, they use credentials)
```

---

### 2. Layer Categorization by Node Descriptor

**Principle:** Categorize by what the node represents, not position in path

```python
LAYER_KEYWORDS = {
    "identity": ["user", "admin", "auth", "sso", "mfa", "login"],
    "network": ["gateway", "router", "firewall", "load balancer", "proxy", "cdn"],
    "device": ["workstation", "server", "iot", "mobile", "endpoint"],
    "application": ["web", "api", "service", "app", "orchestrator", "worker", "llm"],
    "data": ["database", "storage", "file", "s3", "blob", "vector", "cache"]
}
```

**Example:**
```
Path: Users → WebUI → AgentOrchestrator → LLM → VectorDB → Database

Layers:
- Users: identity
- WebUI: application
- AgentOrchestrator: application
- LLM: application (AI-specific)
- VectorDB: data
- Database: data
```

---

### 3. DDIR Budget Allocation

**33/33/17/17 Split:**
```
Max 10-12 controls:
- DETER (Prevent): 33% (3-4 controls)
- DETECT: 33% (3-4 controls)
- ISOLATE: 17% (2 controls)
- RESPOND: 17% (2 controls)
```

**Rationale:** Assume breach mindset requires detect/isolate/respond, not just prevent.

**Adjustment:** For insider threats, shift to 25/35/20/20 (more detect/isolate/respond).

---

### 4. Insider Threat Treatment

**Principle:** Insiders bypass perimeter → Focus on depth

```python
# Detection
is_privileged_insider = any(kw in entry_label for kw in ["admin", "privileged", "root"])

if is_privileged_insider and insider_risk >= 60:
    priority = "CRITICAL"  # Highest risk
    
# Control focus
Controls: Logging (detect), Least Privilege (isolate), DLP (detect), 
          Audit Log (respond), Behavioral Analysis (detect)

# NOT: WAF, Firewall (they're already inside)
```

---

### 5. Resilience by Design (DDIRR)

**Problem:** DoS/availability threats exist at EVERY layer, not just perimeter

**Solution:** Resilience controls throughout architecture

```python
RESILIENCE_CONTROLS = {
    "prevent": [
        "rate limiting",        # Internal API rate limits
        "resource quotas",      # CPU/memory limits
        "connection pooling",   # Limit DB connections
        "load balancer"         # Distribute load
    ],
    "detect": [
        "health checks",        # Liveness/readiness probes
        "resource monitoring",  # CPU/memory/disk alerts
        "latency monitoring",   # Performance degradation
        "error rate alerting"   # Spike in failures
    ],
    "isolate": [
        "circuit breaker",      # Stop calling failing service
        "bulkhead pattern",     # Isolate thread pools
        "timeout policies",     # Prevent hanging requests
        "queue management"      # Backpressure control
    ],
    "respond": [
        "auto-scaling",         # Scale on demand
        "failover",            # Switch to backup
        "restart policies",    # Auto-restart on failure
        "retry with backoff"   # Intelligent retry
    ]
}
```

**AI Systems Special Case:**
- LLM API rate limiting (quota exhaustion is expensive $$$)
- Circuit breaker for LLM calls (prevent cascading failures)
- Queue management (handle burst traffic)

---

### 6. SPOF Detection (Automated)

**Graph Topology Analysis:**

```python
def identify_single_points_of_failure(nodes, edges):
    """
    SPOF indicators:
    1. Bottleneck: in-degree ≤ 1 AND out-degree ≥ 2
    2. Bridge: Removing node disconnects critical assets
    3. No redundancy: Single instance, no failover
    """
    
    spof = []
    
    for node_id in nodes:
        in_degree = count_incoming_edges(node_id, edges)
        out_degree = count_outgoing_edges(node_id, edges)
        
        # Bottleneck pattern
        if in_degree <= 1 and out_degree >= 2:
            spof.append(node_id)
        
        # Bridge pattern
        if is_bridge_node(node_id, nodes, edges):
            spof.append(node_id)
    
    return spof
```

**Mitigation:**
- Load Balancer in front of SPOF node
- At least 2 instances
- Health checks + auto-scaling
- Failover configuration

---

### 7. Control Prioritization (Triple-Objective)

**Breadth AND Depth AND Resilience (not either/or)**

```python
def prioritize_breadth_and_depth_and_resilience(
    rapids_recs,      # Breadth: RAPIDS threats
    layered_recs,     # Depth: DDIR per hop
    resilience_recs,  # Resilience: SPOF + internal DoS
    max_controls=12
):
    """
    Mandatory:
    1. Top 3 RAPIDS threats covered (≥2/3)
    2. All 4 DDIR categories represented
    3. SPOFs mitigated (if present)
    
    Prefer: Controls that serve multiple objectives
    Example: Logging serves insider threat (RAPIDS) + detect (DDIR)
    """
```

**Equal Weighting:** Security controls = Resilience controls (both critical)

---

### 8. Specific Placement Guidance

**Principle:** No generic terms, specify WHERE and HOW

```
❌ Generic: "Implement network segmentation"
✅ Specific: "Network segmentation between WebUI and AgentOrchestrator via VLAN"

❌ Generic: "Add logging"
✅ Specific: "Logging at LLM inference endpoint, capture prompts and outputs"

❌ Generic: "Install load balancer"
✅ Specific: "Load Balancer in front of AgentOrchestrator, distribute across 2+ instances"
```

---

### 9. Assume Breach Mindset

**For each hop, document:** "What if this layer is breached?"

```markdown
## Assume Breach Analysis

**Scenario 1:** WebUI Compromised (SQL injection)
- ✓ Network Segmentation isolates WebUI ↔ Orchestrator
- ✓ IDS detects lateral movement attempt
- ✓ Circuit Breaker prevents cascading to LLM
- ✓ Logging captures attack for forensics

**Scenario 2:** Privileged Insider Exfiltrates Data
- ✓ Least Privilege limits database access
- ✓ DLP detects large data export
- ✓ Audit Log records privileged actions
- ✓ Behavioral Analysis flags anomalous patterns
```

---

### 10. Validation Framework

**6 Validation Checks (Target: 6/6 = 100%)**

1. **Technique Mapping:** T1190 contextual, T1566 for users
2. **RAPIDS Breadth:** Top 3 threats have controls (≥2/3)
3. **DDIR Depth:** All 4 categories represented
4. **Hop Coverage:** Critical hops have ≥3 DDIR
5. **SPOF Mitigation:** All SPOFs have resilience controls
6. **Resilience Coverage:** High DoS risk → internal resilience controls

---

## Implementation Phases

### Phase 3B-1: Context-Aware Technique Mapping (2h)

**Goal:** Fix validation failures (0/2 → 2/2)

**Tasks:**
1. Add `calculate_exploitability_threshold()` function
   - Input: present_controls
   - Output: threshold (50/60/70)
   - Logic: Conservative CVE assumption

2. Update `map_path_to_techniques()` function
   - User/Admin/Employee entry → T1566 + T1078
   - Internet entry + app_vuln_risk ≥ threshold → T1190
   - Otherwise → No T1190

3. Test with reference architectures
   - 02_minimal_defended: Internet + unpatched → T1190 ✓
   - 21_agentic_ai_system: Users → T1566/T1078 ✓

**Files Modified:**
- `chatbot/modules/ground_truth_generator.py`

**Expected Outcome:**
- Validation pass rate: 2/2 technique mapping ✓
- Confidence: +2% (better technique accuracy)

---

### Phase 3B-2: Hop-Based Layered Defense + Resilience (5h)

**Goal:** Add depth (DDIR) and resilience (DDIRR) per hop

**Tasks:**

1. Create `chatbot/modules/layered_defense.py` (~400 lines)

2. Implement layer categorization
   ```python
   def categorize_hop_layer(node_label: str) -> str:
       # Returns: identity/network/device/application/data
   ```

3. Implement DDIR assessment
   ```python
   def assess_hop_ddir_coverage(hop, layer, present_controls) -> Dict:
       # Returns: {"prevent": bool, "detect": bool, "isolate": bool, "respond": bool}
   ```

4. Implement resilience assessment
   ```python
   def assess_hop_resilience(hop, layer, present_controls) -> Dict:
       # Returns: {"prevent": bool, "detect": bool, "isolate": bool, "respond": bool}
   ```

5. Implement SPOF detection
   ```python
   def identify_single_points_of_failure(nodes, edges) -> List[str]:
       # Returns: List of SPOF node IDs
   ```

6. Implement hop recommendations
   ```python
   def generate_hop_recommendations(hop, ddir_gaps, resilience_gaps, is_insider) -> List[Dict]:
       # Returns: Controls for this hop
   ```

7. Implement main function
   ```python
   def generate_layered_defense(attack_paths, nodes, edges, present_controls, rapids) -> List[Dict]:
       # Returns: All depth + resilience recommendations
   ```

**Files Created:**
- `chatbot/modules/layered_defense.py` (NEW)

**Expected Outcome:**
- Each hop assessed for security DDIR
- Each hop assessed for resilience DDIR
- SPOFs identified with mitigation recommendations

---

### Phase 3B-3: Breadth + Depth + Resilience Merge (2.5h)

**Goal:** Balance all three objectives

**Tasks:**

1. Create resilience recommendation generator
   ```python
   def generate_resilience_recommendations(attack_paths, nodes, edges, present_controls, rapids):
       # Identify SPOFs
       # Generate SPOF mitigation controls
       # Generate internal DoS controls
       # Generate AI-specific resilience (if applicable)
   ```

2. Create triple-objective prioritization
   ```python
   def prioritize_breadth_and_depth_and_resilience(rapids_recs, layered_recs, resilience_recs, max_controls=12):
       # STEP 1: Ensure breadth (top 3 RAPIDS)
       # STEP 2: Ensure depth (all 4 DDIR)
       # STEP 3: Ensure resilience (SPOFs mitigated)
       # STEP 4: Find overlaps (controls serving multiple objectives)
       # STEP 5: Fill remaining budget
   ```

3. Update main function integration
   ```python
   def generate_rapids_driven_controls(...):
       rapids_recs = generate_rapids_recommendations(...)  # Existing
       layered_recs = generate_layered_defense(...)        # Phase 3B-2
       resilience_recs = generate_resilience_recommendations(...)  # New
       
       merged = prioritize_breadth_and_depth_and_resilience(...)
       final = add_confidence_to_recommendations(...)
       return final
   ```

**Files Modified:**
- `chatbot/modules/rapids_driven_controls.py`

**Expected Outcome:**
- 10-12 controls that satisfy breadth + depth + resilience
- Controls with multiple objectives prioritized

---

### Phase 3B-4: Enhanced Validation (2.5h)

**Goal:** Validate all three dimensions

**Tasks:**

1. Create breadth & depth validation
   ```python
   def validate_breadth_and_depth(control_recs, attack_paths, rapids, nodes):
       # Check: Top 3 RAPIDS threats covered (≥2/3)
       # Check: All 4 DDIR categories represented
       # Check: Critical hops have ≥3 DDIR
       # Check: Insider paths are depth-focused
   ```

2. Create resilience validation
   ```python
   def validate_resilience_by_design(control_recs, attack_paths, nodes, edges, rapids):
       # Check: SPOFs mitigated
       # Check: Microservices have circuit breakers
       # Check: AI systems have LLM rate limiting
       # Check: High DoS risk → internal resilience controls
   ```

3. Update main validation runner
   ```python
   def run_self_validation(ground_truth, nodes, architecture_type):
       # Validation 1-2: Technique mapping (existing)
       # Validation 3-4: Breadth & depth (NEW)
       # Validation 5-6: Resilience (NEW)
   ```

**Files Modified:**
- `chatbot/modules/self_validation.py`

**Expected Outcome:**
- 6 validation checks (target: 6/6 = 100%)
- Issues identified for each failed check

---

### Phase 3B-5: Exposure + Insider Confidence (1.5h)

**Goal:** Scale confidence to exposure level

**Tasks:**

1. Create exposure multiplier calculator
   ```python
   def calculate_exposure_multiplier(architecture_type, rapids, attack_paths, nodes):
       exposure_score = 0
       
       # Internet-facing: +10
       # Insider threat (risk ≥ 60): +10
       # Privileged insider: +5
       # Complexity (≥5 paths): +5
       # High-value target (AI, financial): +5
       
       # Return multiplier (0.95 to 1.15)
   ```

2. Update confidence calculation
   ```python
   def add_confidence_to_recommendations(...):
       base_confidence = calculate_confidence(...)  # Existing 5 factors
       exposure_multiplier = calculate_exposure_multiplier(...)
       final_confidence = base_confidence * exposure_multiplier
   ```

**Files Modified:**
- `chatbot/modules/confidence_scoring.py`

**Expected Outcome:**
- High-exposure systems: 90%+ confidence
- Medium-exposure: 85-89% confidence
- Average: 89% confidence

---

### Phase 3B-6: Enhanced Reporting (1.5h)

**Goal:** Communicate breadth, depth, and resilience clearly

**Tasks:**

1. Add "Defense-in-Depth Analysis" section
   ```markdown
   | Hop | Node | Layer | Security DDIR | Resilience DDIR | SPOF? |
   ```

2. Add "SPOF Mitigation" section
   ```markdown
   **Critical:** AgentOrchestrator
   - Risk: Single point of failure
   - Impact: Entire AI pipeline fails
   - Recommendation: Load Balancer + 2 instances + health checks
   - Placement: Between WebUI and AgentOrchestrator
   ```

3. Add "Assume Breach Analysis" section
   ```markdown
   **Scenario 1:** WebUI Compromised
   - ✓ Control X isolates...
   - ✓ Control Y detects...
   ```

4. Update control recommendations to show specific placement

**Files Modified:**
- `chatbot/modules/threat_report.py`

**Expected Outcome:**
- Reports show hop-by-hop DDIR
- SPOF mitigation plans documented
- Assume breach scenarios clear
- Specific placement guidance (not generic)

---

## Success Criteria

### Technical Validation
- [ ] T1190 only when exploitable (internet + app_vuln_risk ≥ threshold)
- [ ] T1566/T1078 for user/insider entries
- [ ] Each hop has ≥1 security DDIR category
- [ ] Each hop with high DoS risk has ≥1 resilience DDIR
- [ ] Critical hops (entry, target) have ≥3 DDIR total
- [ ] SPOFs identified and mitigated
- [ ] DDIR balance: ≤50% preventive-only
- [ ] Insider paths are depth-focused
- [ ] AI systems have LLM API rate limiting
- [ ] Microservices (≥3 services) have circuit breakers

### Metrics
- [ ] Validation pass rate: 6/6 (100%)
  - 2/2 technique mapping
  - 2/2 breadth & depth
  - 2/2 resilience
- [ ] Average confidence: 89% (exceeds 85% target)
- [ ] High-exposure systems: 90%+ confidence
- [ ] DDIR balance: ~33/33/17/17
- [ ] SPOF mitigation rate: 100%

### Philosophy
- [ ] MITRE + RAPIDS drive threat model
- [ ] DDIR drives breadth and depth
- [ ] DDIRR drives resilience
- [ ] Assume breach mindset throughout
- [ ] Breadth AND depth AND resilience (all three)
- [ ] Security AND resilience weighted equally
- [ ] Specific placement (not generic)
- [ ] Deterministic (no LLM dependency for core logic)

### Reporting
- [ ] Defense-in-depth table (hop-by-hop)
- [ ] SPOF identification + mitigation
- [ ] Assume breach scenarios
- [ ] Specific placement guidance
- [ ] Layer categorization by descriptor
- [ ] Resilience architecture assessment

---

## Files to Create/Modify

### New Files
1. `chatbot/modules/layered_defense.py` (~400 lines)
   - Hop categorization by descriptor
   - DDIR assessment (security)
   - Resilience assessment (availability)
   - SPOF detection (graph topology)
   - Hop-specific recommendations

### Modified Files
1. `chatbot/modules/ground_truth_generator.py`
   - `calculate_exploitability_threshold()` - NEW
   - `map_path_to_techniques()` - UPDATE
   - `assess_rapids_risks()` - UPDATE (add internal DoS assessment)

2. `chatbot/modules/rapids_driven_controls.py`
   - `generate_resilience_recommendations()` - NEW
   - `prioritize_breadth_and_depth_and_resilience()` - NEW
   - `generate_rapids_driven_controls()` - UPDATE

3. `chatbot/modules/self_validation.py`
   - `validate_breadth_and_depth()` - NEW
   - `validate_resilience_by_design()` - NEW
   - `run_self_validation()` - UPDATE

4. `chatbot/modules/confidence_scoring.py`
   - `calculate_exposure_multiplier()` - NEW
   - `add_confidence_to_recommendations()` - UPDATE

5. `chatbot/modules/threat_report.py`
   - Add "Defense-in-Depth Analysis" section
   - Add "SPOF Mitigation" section
   - Add "Assume Breach Analysis" section
   - Update control placement to be specific

### Documentation Updates
1. `docs/CONFIDENCE_METHODOLOGY.md`
   - Add exposure multiplier explanation
   - Add resilience confidence factors

2. `docs/REFERENCE_ARCHITECTURES.md`
   - Update validation framework (6 checks)
   - Add SPOF detection results
   - Update target metrics

3. `STATUS_AND_PLAN.md`
   - Update Phase 3B details
   - Add completion criteria

---

## Expected Results

### 02_minimal_defended

**Before:**
- Validation: 0/2 pass
- Confidence: 78%
- Issues: T1190 at WAF (control, not entry)

**After:**
- Validation: 6/6 pass
- Confidence: 87-89%
- Controls: Patching, WAF, Logging, Network Seg, Backup, IDS, Load Balancer (7)

---

### 21_agentic_ai_system

**Before:**
- Validation: 0/2 pass
- Confidence: 84%
- Issues: T1190 at "Users", perimeter-only defense, no SPOF mitigation

**After:**
- Validation: 6/6 pass
- Confidence: 91-93%
- Controls: Logging, Least Privilege, Rate Limiting (LLM), Network Seg, Circuit Breaker, DLP, Load Balancer (Orchestrator), Backup, Health Checks, MFA (10)
- SPOF: AgentOrchestrator identified and mitigated

---

## Risk & Mitigation

### Risk 1: Implementation Complexity
**Impact:** 13 hours may be underestimated  
**Mitigation:** Phase 3B-2 (layered defense) is most complex. Budget +2 hours buffer.

### Risk 2: SPOF Detection False Positives
**Impact:** May identify non-critical nodes as SPOFs  
**Mitigation:** Validate SPOF detection on reference architectures first, tune thresholds.

### Risk 3: Control Budget Explosion
**Impact:** 10-12 controls may not fit all objectives  
**Mitigation:** Prioritize by risk score, ensure mandatory objectives met first.

---

## Pre-Implementation Checklist

Before starting Phase 3B-1:
- [ ] Read this plan (docs/PHASE3B_PLAN.md)
- [ ] Read docs/REFERENCE_ARCHITECTURES.md (current validation issues)
- [ ] Read docs/CONFIDENCE_METHODOLOGY.md (current scoring approach)
- [ ] Review chatbot/modules/rapids_driven_controls.py (current implementation)
- [ ] Review chatbot/modules/self_validation.py (current validation)
- [ ] Understand the three pillars: MITRE+RAPIDS | DDIR | DDIRR

---

**Plan Version:** 1.0  
**Author:** Claude Sonnet 4.5 + User Collaboration  
**Date:** 2026-05-03  
**Status:** Ready for Implementation
