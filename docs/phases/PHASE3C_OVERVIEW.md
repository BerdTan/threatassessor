# Phase 3C: LLM as Judge/Critic (Future)

**Status:** Planned - After Phase 3B Complete  
**Prerequisites:** Phase 3B (DDIR + Resilience) must be complete with deterministic baseline  
**Estimated Duration:** 3-4 hours  
**Purpose:** Use LLM to identify gaps beyond deterministic assessment

---

## Philosophy

**Phase 3A + 3B = Deterministic Foundation**
- Parser-based analysis (no LLM required)
- Rule-based technique mapping
- Graph topology analysis (SPOF detection)
- RAPIDS risk scoring (formula-based)
- DDIR coverage assessment (checklist-based)

**Phase 3C = LLM Enhancement (Gap Detection)**
- LLM as critic/judge of deterministic assessment
- Identifies blind spots in rules
- Architecture-specific nuances
- Industry-specific threats
- Novel attack vectors not in MITRE ATT&CK

---

## Core Concept: LLM as Critic

```
┌─────────────────────────────────────────────────────┐
│ Phase 3B Output (Deterministic)                     │
├─────────────────────────────────────────────────────┤
│ • Threat model: RAPIDS + MITRE techniques           │
│ • Controls: Breadth + Depth + Resilience            │
│ • Validation: 6/6 checks passed                     │
│ • Confidence: 89% average                           │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│ LLM Critique (Phase 3C)                             │
├─────────────────────────────────────────────────────┤
│ Questions to LLM:                                   │
│ 1. What threats did we miss?                        │
│ 2. Are the controls sufficient for this context?    │
│ 3. Architecture-specific risks not captured?        │
│ 4. Industry-specific threats relevant?              │
│ 5. Emerging threats not in MITRE?                   │
│ 6. Are there cascading failure scenarios?           │
│ 7. Supply chain risks specific to components?       │
│ 8. Regulatory/compliance gaps?                      │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│ Enhanced Assessment (Deterministic + LLM)           │
├─────────────────────────────────────────────────────┤
│ • Original assessment maintained (deterministic)    │
│ • LLM findings added as "Additional Considerations" │
│ • Flagged for human review (not auto-applied)       │
│ • Confidence adjusted if LLM confirms gaps          │
└─────────────────────────────────────────────────────┘
```

---

## What LLM Adds

### 1. Threat Model Gaps

**LLM Prompt:**
```
You are a senior security architect reviewing a threat model.

Architecture: {description}
Entry Points: {list}
Components: {list}
Controls Present: {list}

Our deterministic analysis identified these threats:
{RAPIDS threats + MITRE techniques}

Critical Question: What threats did we miss?

Consider:
- Architecture-specific risks (e.g., AI model poisoning, IoT device compromise)
- Industry-specific threats (e.g., financial: insider trading, healthcare: HIPAA violations)
- Supply chain risks (e.g., compromised dependencies, malicious libraries)
- Emerging threats not yet in MITRE ATT&CK
- Cascading failures we didn't model

Format your response as:
1. Threat category
2. Why it's relevant to THIS architecture
3. Severity (CRITICAL/HIGH/MEDIUM/LOW)
4. Recommended controls
```

**Example Output:**
```
ADDITIONAL THREAT: AI Model Poisoning
Relevance: LLM component (AgentOrchestrator → LLM) is trained on external data
Severity: HIGH
Rationale: Attacker could poison training data to bias model outputs
Recommended Controls: Input data validation, model versioning, A/B testing, anomaly detection
```

---

### 2. Control Sufficiency Gaps

**LLM Prompt:**
```
Our deterministic analysis recommended these controls:
{list of controls with rationale}

We achieved:
- DDIR balance: 33/33/17/17 (prevent/detect/isolate/respond)
- Breadth: Top 3 RAPIDS threats covered
- Depth: Controls at each hop
- Resilience: SPOFs mitigated

Critical Question: Are these controls SUFFICIENT for this architecture?

Consider:
- Defense-in-depth: Are there gaps between layers?
- Assume breach: If control X fails, is there a backup?
- Implementation quality: Is "logging" enough, or do we need "centralized SIEM"?
- Context-specific: Are controls appropriate for THIS architecture type?
- Completeness: Are there obvious gaps a pentester would exploit?

Format your response as:
1. Gap identified
2. Why current controls insufficient
3. Recommended enhancement
4. Priority
```

**Example Output:**
```
GAP: Logging without Centralization
Current: "Logging" recommended at 3 hops
Issue: Logs at each hop but no correlation across hops (attacker can cover tracks hop-by-hop)
Enhancement: Centralized SIEM with correlation rules
Priority: HIGH (assume breach requires cross-hop visibility)
```

---

### 3. Architecture-Specific Nuances

**LLM Prompt:**
```
Architecture Type: {ai_system / web_app / iot / financial / etc.}
Components: {list with descriptions}

Our deterministic rules applied generic security controls.

Critical Question: What architecture-specific risks are we missing?

For AI systems, consider:
- Prompt injection (direct and indirect)
- Model inversion attacks
- Training data poisoning
- Model theft (extraction via API)
- Output bias/toxicity

For IoT systems, consider:
- Physical access to devices
- Firmware vulnerabilities
- Device sprawl (inventory management)
- Limited compute (can't run heavy security)

For Financial systems, consider:
- Insider trading
- Transaction manipulation
- Regulatory compliance (PCI-DSS, SOX)
- High-value target (APT interest)

Format as above.
```

---

### 4. Industry/Regulatory Context

**LLM Prompt:**
```
Architecture: {description}
Industry: {if known, otherwise "generic"}

Our assessment focused on technical threats.

Critical Question: What industry-specific or regulatory requirements are missing?

Consider:
- GDPR (EU data protection)
- HIPAA (healthcare data)
- PCI-DSS (payment card data)
- SOX (financial reporting)
- NIST frameworks
- Industry-specific standards (e.g., IEC 62443 for industrial control systems)

Format your response as:
1. Regulation/Standard
2. Requirement not addressed by current controls
3. Recommended control or process
4. Compliance risk if not addressed
```

---

## Implementation Approach

### Option 1: Critique Mode (Recommended)

```python
def llm_critique_assessment(ground_truth: Dict, architecture_description: str) -> Dict:
    """
    LLM reviews deterministic assessment and identifies gaps.
    
    Returns: {
        "threat_gaps": [...],
        "control_gaps": [...],
        "architecture_specific": [...],
        "industry_considerations": [...]
    }
    """
    prompt = build_critique_prompt(ground_truth, architecture_description)
    llm_response = call_llm(prompt)
    parsed_gaps = parse_llm_critique(llm_response)
    
    return parsed_gaps
```

**Integration:**
- Run AFTER deterministic assessment complete
- Add LLM findings as separate report section: "LLM-Identified Considerations"
- Flag for human review (don't auto-apply)
- Update confidence IF LLM confirms deterministic findings align

---

### Option 2: Iterative Refinement

```python
def iterative_llm_refinement(ground_truth: Dict, max_iterations: int = 2) -> Dict:
    """
    LLM suggests improvements, deterministic rules apply, repeat.
    
    Iteration 1:
    1. Deterministic assessment
    2. LLM critique
    3. Apply validated LLM suggestions (human-approved)
    4. Re-run deterministic assessment
    
    Iteration 2:
    1. LLM reviews updated assessment
    2. Suggests further improvements
    3. Apply if valid
    
    Stop when: No more significant gaps OR max iterations reached
    """
```

---

### Option 3: Red Team Mode

```python
def llm_red_team(ground_truth: Dict) -> List[Dict]:
    """
    LLM acts as attacker, tries to find weakest path through defenses.
    
    Prompt:
    "You are a red team pentester. Given these controls:
    {list of recommended controls}
    
    Your goal: Identify the attack path with highest chance of success.
    Assume:
    - You have internet access to the system
    - You have some insider knowledge (social engineering possible)
    - You have moderate skill (not APT-level)
    
    Which path would you take and why?"
    
    Returns: Attack scenarios that BYPASS current controls
    """
```

---

## CLI Integration

### New Command

```bash
# Deterministic only (Phase 3B)
python3 -m chatbot.main --gen-arch-truth architecture.mmd

# Deterministic + LLM critique (Phase 3C)
python3 -m chatbot.main --gen-arch-truth-llm architecture.mmd

# Or explicit critique mode
python3 -m chatbot.main --critique-threat-model ground_truth.json
```

---

## Report Integration

### Deterministic Section (Unchanged)
```markdown
## Threat Model
- RAPIDS threats
- MITRE techniques
- Attack paths

## Control Recommendations
1. Control X (DDIR: PREVENT, RAPIDS: DoS)
2. Control Y (DDIR: DETECT, RAPIDS: Insider)
...
```

### LLM Critique Section (New)
```markdown
## LLM-Identified Considerations

⚠️ **Note:** These are LLM-generated insights for human review. 
They complement the deterministic assessment but require validation.

### Additional Threats
1. **AI Model Poisoning** (HIGH)
   - Relevance: LLM trained on external data
   - Risk: Attacker poisons training data
   - Recommended: Input validation, model versioning

2. **Firmware Vulnerability** (MEDIUM)
   - Relevance: IoT devices in architecture
   - Risk: Outdated firmware on edge devices
   - Recommended: Automated firmware updates, device inventory

### Control Sufficiency Gaps
1. **Logging → SIEM** (HIGH)
   - Current: Logging at 3 hops (isolated)
   - Gap: No cross-hop correlation
   - Enhancement: Centralized SIEM with correlation

### Architecture-Specific Risks
1. **Prompt Injection** (HIGH)
   - Context: Public-facing LLM API
   - Attack: Malicious prompts bypass filters
   - Recommended: Input sanitization, output validation, rate limiting per user

### Regulatory Considerations
1. **GDPR Data Protection**
   - Requirement: Data minimization, right to deletion
   - Gap: No documented data retention policy
   - Recommended: Data lifecycle management, deletion workflows
```

---

## Validation

### How to Validate LLM Critique

1. **Threat Gaps:**
   - Check if threat is real for this architecture type
   - Verify with industry data (e.g., OWASP Top 10 for LLM)
   - Confirm not already covered by RAPIDS/MITRE

2. **Control Gaps:**
   - Check if gap is genuine (not already addressed)
   - Verify enhancement is practical
   - Assess priority (does it align with risk?)

3. **Architecture-Specific:**
   - Validate against architecture documentation
   - Check industry best practices (e.g., NIST AI guidelines)
   - Confirm relevance to THIS architecture

4. **Regulatory:**
   - Check if regulation applies to this industry
   - Verify requirement accuracy
   - Assess if current controls partially satisfy

### Red Flags (Ignore LLM if)
- Recommends controls already present
- Suggests threats not relevant to architecture
- Hallucinates regulations that don't exist
- Proposes impractical controls

---

## Success Criteria

### LLM Critique Quality
- [ ] Identifies ≥1 genuine gap not caught by deterministic
- [ ] No more than 20% false positives (irrelevant suggestions)
- [ ] Suggestions are actionable (not vague)
- [ ] Aligns with industry best practices

### Integration Quality
- [ ] LLM findings clearly separated from deterministic
- [ ] Marked for human review (not auto-applied)
- [ ] Format is consistent and parseable
- [ ] Doesn't break existing reports

### Performance
- [ ] LLM critique adds ≤30s to total assessment time
- [ ] Graceful degradation if LLM unavailable (skip critique)
- [ ] Can run in offline mode (deterministic only)

---

## Risks & Mitigation

### Risk 1: LLM Hallucination
**Impact:** Recommends non-existent threats or controls  
**Mitigation:** 
- Clearly label as "LLM-generated" 
- Require human validation
- Cross-check against MITRE/OWASP databases

### Risk 2: Generic Advice
**Impact:** LLM gives boilerplate advice not specific to architecture  
**Mitigation:**
- Provide detailed architecture context in prompt
- Ask for "why THIS architecture" in response
- Filter out suggestions that don't reference specific components

### Risk 3: Overconfidence
**Impact:** Security team trusts LLM critique without validation  
**Mitigation:**
- Prominent disclaimer in reports
- Track false positive rate
- Document validation process

### Risk 4: Cost (API Usage)
**Impact:** LLM critique adds API cost per assessment  
**Mitigation:**
- Make LLM critique optional (--gen-arch-truth-llm flag)
- Cache results per architecture hash
- Use cheaper model for critique vs analysis

---

## Future Enhancements (Beyond Phase 3C)

### 1. LLM as Validator
Instead of just critique, LLM validates deterministic findings:
```
"Our rules say this is T1190. Do you agree? Why or why not?"
```

### 2. LLM Attack Narratives
Generate realistic attack scenarios for each path:
```
"Convert attack path #1 (Internet → WebUI → DB) into a realistic APT scenario with:
- Reconnaissance phase
- Initial compromise method
- Lateral movement steps
- Data exfiltration technique"
```

### 3. LLM Control Prioritization
Help prioritize when budget is limited:
```
"We can only implement 5 of these 10 controls. Given the architecture and threat landscape, which 5 should we prioritize and why?"
```

### 4. LLM Compliance Mapper
Map controls to multiple frameworks:
```
"Map these controls to: NIST CSF, CIS Controls, ISO 27001, PCI-DSS"
```

---

## Dependencies

**Phase 3C depends on:**
- ✅ Phase 3A complete (RAPIDS-driven deterministic)
- ✅ Phase 3B complete (DDIR + Resilience)
- ✅ Validation framework working (6/6 checks)
- ✅ Deterministic baseline is solid (89% confidence)

**Phase 3C enables:**
- More comprehensive threat coverage
- Architecture-specific insights
- Industry-specific considerations
- Regulatory alignment
- Higher overall confidence (90%+)

---

## Estimated Timeline

| Task | Duration |
|------|----------|
| Design LLM critique prompts | 1h |
| Implement critique function | 1h |
| Parse and validate LLM output | 0.5h |
| Integrate into reports | 0.5h |
| Test with 2 reference architectures | 0.5h |
| Document findings | 0.5h |
| **Total** | **4 hours** |

---

## Next Steps (After Phase 3B)

1. Complete Phase 3B (deterministic DDIR + Resilience)
2. Validate deterministic baseline (6/6 checks, 89% confidence)
3. Start Phase 3C:
   - Design critique prompts
   - Implement --gen-arch-truth-llm mode
   - Test and refine
4. Document results and move to Phase 4 (Web UI)

---

**Document Version:** 1.0  
**Date:** 2026-05-03  
**Status:** Planned for after Phase 3B  
**Purpose:** Capture LLM enhancement vision before break
