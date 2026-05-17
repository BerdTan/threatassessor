# MoE (Mixture of Experts) Architecture Design

**Date:** 2026-05-17  
**Status:** 🎯 APPROVED - Ready for Implementation  
**Version:** 1.0  
**System:** ThreatAssessor (formerly MITRE Chatbot)

---

## Executive Summary

Refactor Phase 3C+ orchestrator into clean MoE architecture with:
- **Sequential expert chain** (Deterministic → Architect → Tester → Red Team)
- **Fail-fast validation** (missing prerequisite = abort)
- **Consensus orchestration** (coherent CISO-ready output)
- **Frontend-agnostic API** (robust analysis, any UI)

---

## Current Problems

1. **Parallel recommendations** - Deterministic (99.5%) vs LLM agents (85%) create conflicting advice
2. **Non-deterministic scoring** - Same architecture scores 52-63/100 (11 point variance)
3. **Missing dependencies** - Orchestrator proceeds even if architect/tester files missing
4. **Poor coherence** - 4 reports use different scoring systems, no clear next steps
5. **Self-referential validation** - Agents critique the analysis, not the architecture

---

## MoE Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    ThreatAssessor Engine                     │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  LAYER 1: Deterministic Expert (Source of Truth)            │
│  ───────────────────────────────────────────────────────    │
│  Input:  architecture.mmd                                    │
│  Output: ground_truth.json (99.5% confidence)                │
│                                                               │
│  ✓ Attack path analysis (RAPIDS framework)                  │
│  ✓ Per-node technique mapping (MITRE ATT&CK)                │
│  ✓ AI/ML threat detection (ARC + ATLAS)                     │
│  ✓ Control recommendations (Prevention + DIR)               │
│  ✓ Residual risk calculation (BEFORE/AFTER)                 │
│  ✓ 6-check validation (completeness)                        │
│                                                               │
│  Files: ground_truth.json                                    │
└─────────────────────────────────────────────────────────────┘
                            ↓
         ┌──────────────────────────────────┐
         │   Sequential Expert Chain         │
         │   (LLM-based validation)          │
         └──────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  LAYER 2A: Architect Expert (Design Quality Validator)      │
│  ───────────────────────────────────────────────────────    │
│  Input:  ground_truth.json (deterministic analysis)          │
│  Role:   Validate threat model completeness & control design │
│  Output: 04_architect_critique.json                          │
│                                                               │
│  Questions:                                                   │
│  ✓ Are all attack paths covered?                            │
│  ✓ Are controls appropriate for threats?                    │
│  ✓ Is defense-in-depth adequate?                            │
│  ✓ Does RAPIDS prioritization make sense?                   │
│  ✓ Are critical nodes properly protected?                   │
│                                                               │
│  Output Format:                                              │
│  {                                                            │
│    "validation_status": "PASS/FAIL",                         │
│    "confidence_adjustment": -5,  // -5% for minor gaps      │
│    "gaps": [                                                 │
│      {                                                        │
│        "type": "missing_control",                            │
│        "severity": "HIGH",                                   │
│        "description": "No rate limiting on API Gateway",     │
│        "recommendation": "Add M1033 (rate limiting)"         │
│      }                                                        │
│    ],                                                         │
│    "strengths": ["Good DIR coverage", "RAPIDS complete"]     │
│  }                                                            │
│                                                               │
│  FAIL CONDITION: If ground_truth.json not found → ABORT     │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  LAYER 2B: Tester Expert (MITRE Validator)                  │
│  ───────────────────────────────────────────────────────    │
│  Input:  ground_truth.json + 04_architect_critique.json      │
│  Role:   Validate MITRE mappings & Architect's advice        │
│  Output: 05_tester_critique.json                             │
│                                                               │
│  Questions:                                                   │
│  ✓ Are technique IDs correct? (T1234 exists?)               │
│  ✓ Are mitigation IDs correct? (M5678 exists?)              │
│  ✓ Do mitigations actually address techniques?              │
│  ✓ Are ATLAS mappings valid? (AML.T#### exists?)            │
│  ✓ Did Architect catch real issues?                         │
│  ✓ Are Architect's recommendations valid?                   │
│                                                               │
│  Output Format:                                              │
│  {                                                            │
│    "validation_status": "PASS/FAIL",                         │
│    "confidence_adjustment": -2,  // -2% for minor errors    │
│    "mitre_errors": [                                         │
│      {                                                        │
│        "type": "invalid_technique",                          │
│        "found": "T9999",                                     │
│        "correction": "T1059 (Command and Scripting)"         │
│      }                                                        │
│    ],                                                         │
│    "architect_validation": {                                 │
│      "gaps_confirmed": 3,  // Real architecture issues      │
│      "gaps_invalid": 1     // Analysis critiques (ignore)   │
│    }                                                          │
│  }                                                            │
│                                                               │
│  FAIL CONDITION: If 04_architect_critique.json missing → ABORT │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  LAYER 2C: Red Team Expert (Exploit Validator)              │
│  ───────────────────────────────────────────────────────    │
│  Input:  ground_truth.json + 04_ + 05_                       │
│  Role:   Validate control effectiveness & Tester's assessment│
│  Output: 06_red_team_critique.json                           │
│                                                               │
│  Questions:                                                   │
│  ✓ Would recommended controls actually stop attacks?        │
│  ✓ Are there bypass techniques?                             │
│  ✓ Is exploit difficulty realistic?                         │
│  ✓ Did Tester catch all MITRE errors?                       │
│  ✓ Are there false control claims?                          │
│                                                               │
│  Output Format:                                              │
│  {                                                            │
│    "validation_status": "PASS/FAIL",                         │
│    "confidence_adjustment": -3,  // -3% for bypass risks    │
│    "bypass_scenarios": [                                     │
│      {                                                        │
│        "control": "WAF",                                     │
│        "bypass": "SSRF to internal services",                │
│        "additional_control": "Network segmentation"          │
│      }                                                        │
│    ],                                                         │
│    "tester_validation": {                                    │
│      "errors_confirmed": 2,                                  │
│      "false_positives": 0                                    │
│    },                                                         │
│    "exploit_difficulty": 45  // 0-100, LOW=easy, HIGH=hard  │
│  }                                                            │
│                                                               │
│  FAIL CONDITION: If 05_tester_critique.json missing → ABORT │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  LAYER 3: Orchestrator (Consensus & Coherence)              │
│  ───────────────────────────────────────────────────────    │
│  Input:  ground_truth.json + 04_ + 05_ + 06_                 │
│  Role:   Calculate final confidence & generate unified report│
│  Output: 00_executive_dashboard.md (CISO-ready)              │
│                                                               │
│  Confidence Calculation:                                     │
│  Base: 99.5% (deterministic)                                │
│  - Architect adjustment: -5%                                │
│  - Tester adjustment: -2%                                   │
│  - Red Team adjustment: -3%                                 │
│  = Final: 89.5%                                             │
│                                                               │
│  Consensus Logic:                                            │
│  ✓ Confirmed gaps (all 3 agree) → CRITICAL priority        │
│  ✓ Majority gaps (2 agree) → HIGH priority                 │
│  ✓ Single-agent gaps → REVIEW (may be false positive)      │
│                                                               │
│  Report Structure:                                           │
│  00_executive_dashboard.md:                                  │
│    - Single composite score (89.5%)                         │
│    - Risk transformation (BEFORE/AFTER)                     │
│    - 3 improvement options (Quick/Recommended/Maximum)      │
│    - Clear "Next Steps" with decision tree                  │
│    - Budget & timeline guidance                             │
│    - Consensus recommendations only (no conflicts)          │
│                                                               │
│  FAIL CONDITION: If any 04/05/06 missing → ABORT           │
└─────────────────────────────────────────────────────────────┘
```

---

## Key Principles

### 1. Sequential Dependencies (FAIL FAST)

Each expert requires previous outputs:

```python
def run_moe_pipeline(architecture_path: str) -> Report:
    # Layer 1: Deterministic (required)
    gt_path = run_deterministic(architecture_path)
    if not gt_path.exists():
        raise MissingPrerequisiteError("ground_truth.json not found")
    
    # Layer 2A: Architect (required)
    arch_path = run_architect(gt_path)
    if not arch_path.exists():
        raise MissingPrerequisiteError("04_architect_critique.json not found")
    
    # Layer 2B: Tester (required)
    test_path = run_tester(gt_path, arch_path)
    if not test_path.exists():
        raise MissingPrerequisiteError("05_tester_critique.json not found")
    
    # Layer 2C: Red Team (required)
    red_path = run_red_team(gt_path, test_path)
    if not red_path.exists():
        raise MissingPrerequisiteError("06_red_team_critique.json not found")
    
    # Layer 3: Orchestrator (synthesizes all)
    report = run_orchestrator(gt_path, arch_path, test_path, red_path)
    return report
```

### 2. Deterministic as Source of Truth

- Deterministic engine produces **recommendations** (what to do)
- LLM experts produce **validation** (confidence adjustments)
- Orchestrator produces **presentation** (CISO-ready report)

**No parallel recommendations!** LLM experts validate only.

### 3. Confidence Adjustments (Not Parallel Scores)

```
Base confidence: 99.5% (deterministic)

Architect validation:
✓ PASS → +0%
⚠️ MINOR GAPS → -2 to -5%
❌ MAJOR GAPS → -10 to -20%

Tester validation:
✓ PASS → +0%
⚠️ MINOR ERRORS → -1 to -3%
❌ MAJOR ERRORS → -5 to -10%

Red Team validation:
✓ PASS → +0%
⚠️ BYPASS RISKS → -3 to -8%
❌ CONTROLS INEFFECTIVE → -10 to -25%

Final confidence: 99.5% + adjustments (capped at 100%, floored at 50%)
```

### 4. Consensus Recommendations Only

Orchestrator outputs **unified** recommendations:

```json
{
  "consensus_recommendations": [
    {
      "priority": "CRITICAL",
      "control": "Rate Limiting",
      "source": "Deterministic + Architect + Tester + Red Team",
      "confidence": 95,
      "actionable": "Add M1033 (rate limiting) to API Gateway",
      "impact": "Reduces DoS risk from 85/100 to 30/100",
      "effort": "< 1 day",
      "cost": "$2K"
    }
  ],
  "review_recommendations": [
    {
      "priority": "LOW",
      "control": "Load Balancer",
      "source": "Deterministic only",
      "confidence": 70,
      "note": "No attack path evidence, pure RAPIDS recommendation"
    }
  ]
}
```

### 5. Frontend-Agnostic API

Output structure supports any frontend:

```
API Endpoint: /api/v1/assess
Input: architecture.mmd
Output:
{
  "status": "success",
  "confidence": 89.5,
  "risk": {
    "current": 76,
    "target": 15,
    "reduction": 80
  },
  "recommendations": {
    "critical": [...],
    "high": [...],
    "medium": [...]
  },
  "improvement_options": [
    {"name": "quick", "timeline": "1-2 weeks", "cost": "$10-50K"},
    {"name": "recommended", "timeline": "1-3 months", "cost": "$75-200K"},
    {"name": "maximum", "timeline": "6+ months", "cost": "$300-600K"}
  ],
  "artifacts": {
    "executive_summary": "00_executive_dashboard.md",
    "technical_report": "02_technical_report.md",
    "diagrams": ["before.mmd", "after.mmd", "08a_quick_wins.mmd", ...]
  }
}
```

---

## File Structure (After MoE)

```
report/architecture_name/
├── ground_truth.json           # Deterministic analysis (Layer 1)
├── 04_architect_critique.json  # Architect validation (Layer 2A)
├── 05_tester_critique.json     # Tester validation (Layer 2B)
├── 06_red_team_critique.json   # Red Team validation (Layer 2C)
├── 07_orchestrator_report.json # Consensus synthesis (Layer 3)
│
├── 00_executive_dashboard.md   # CISO report (unified, coherent)
├── 02_technical_report.md      # Engineer report (detailed)
├── 03_action_plan.md           # Implementation guide
├── 08_improvement_summary.md   # Improvement options
│
├── before.mmd                  # Current architecture
├── after.mmd                   # With all controls
├── 08a_quick_wins.mmd          # Critical controls only
├── 08b_recommended_target.mmd  # Critical + High
└── 08c_maximum_security.mmd    # All controls
```

**Key Changes:**
- Remove 01_executive_summary.md (replaced by 00_executive_dashboard.md)
- 00_ is NEW, generated by orchestrator, provides unified view
- All other files remain but reference 00_ as primary

---

## Implementation Plan

### Phase 1: Foundation (Week 1) - 8 hours

**Goal:** Fail-fast validation & sequential enforcement

1. **Create `MoEOrchestrator` class** (2h)
   - Replace `Orchestrator` with MoE-aware version
   - Enforce sequential dependencies
   - Fail fast if prerequisites missing

2. **Update expert contracts** (2h)
   - Architect returns `validation_status` + `confidence_adjustment`
   - Tester validates Architect advice
   - Red Team validates Tester assessment

3. **Implement prerequisite checks** (2h)
   - Check ground_truth.json before Architect
   - Check 04_ before Tester
   - Check 05_ before Red Team
   - Check 04/05/06 before Orchestrator

4. **Add error handling** (2h)
   ```python
   class MissingPrerequisiteError(Exception):
       """Raised when required input file is missing."""
       pass
   ```

### Phase 2: Expert Refactoring (Week 2) - 12 hours

**Goal:** Experts validate deterministic output, not parallel recommendations

5. **Refactor Architect** (4h)
   - Input: ground_truth.json
   - Output: validation report (not new recommendations)
   - Focus: "Is threat model complete?"
   - Return confidence adjustment (-0 to -20%)

6. **Refactor Tester** (4h)
   - Input: ground_truth.json + 04_architect_critique.json
   - Output: MITRE validation + Architect validation
   - Focus: "Are mappings correct? Are Architect gaps real?"
   - Return confidence adjustment (-0 to -10%)

7. **Refactor Red Team** (4h)
   - Input: ground_truth.json + 04_ + 05_
   - Output: Control effectiveness + Tester validation
   - Focus: "Would controls work? Are Tester errors real?"
   - Return confidence adjustment (-0 to -25%)

### Phase 3: Unified Orchestration (Week 3) - 10 hours

**Goal:** Generate coherent CISO-ready output

8. **Create 00_executive_dashboard.md generator** (6h)
   - Single composite confidence score
   - Risk transformation (BEFORE/AFTER)
   - 3 improvement options (Quick/Recommended/Maximum)
   - Clear "Next Steps" decision tree
   - Consensus recommendations only

9. **Update 08_improvement_summary.md** (2h)
   - Reference 00_executive_dashboard.md
   - Show confidence-weighted recommendations
   - Remove cryptic dict strings

10. **Add cross-references** (2h)
    - 00_ → 02_ (technical details)
    - 00_ → 03_ (action plan)
    - 00_ → 08_ (improvement options)

### Phase 4: Branding & Polish (Week 4) - 6 hours

**Goal:** Rebrand and prepare for frontend integration

11. **Rebrand to ThreatAssessor** (2h)
    - Update all "MITRE Chatbot" → "ThreatAssessor"
    - Update README.md, CLAUDE.md
    - Update report footers

12. **Create API specification** (2h)
    - Document JSON schema for frontend
    - Add examples for each endpoint
    - Version as v1.3

13. **Test on 10 architectures** (2h)
    - Validate all 15 files generated
    - Verify fail-fast works
    - Check report coherence

---

## Success Metrics

| Metric | Current | Target | How to Measure |
|--------|---------|--------|----------------|
| **Confidence variance** | ±11 points | ±2 points | Run same arch 5x, check std dev |
| **Report coherence** | 2 scoring systems | 1 scoring system | Manual review of 00_ |
| **Missing files** | 13/15 sometimes | 15/15 always | Automated check |
| **CISO clarity** | Confused | Clear next steps | User feedback |
| **API readiness** | No | Yes | Frontend team can integrate |

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| **LLM validation too subjective** | High variance | Use structured prompts, limit to yes/no questions |
| **Fail-fast too strict** | Breaks existing workflows | Add `--skip-validation` flag for testing |
| **Breaking changes** | Frontend breaks | Version as v1.3, maintain v1.2 compatibility |
| **Refactoring scope creep** | Delays | Stick to 4-week timeline, defer UX polish |

---

## Decision Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-05-17 | Use MoE architecture | Separate deterministic (truth) from LLM (validation) |
| 2026-05-17 | Enforce sequential dependencies | Quality depends on prior analysis |
| 2026-05-17 | Fail fast on missing prerequisites | Don't proceed with bad data |
| 2026-05-17 | Focus on robustness over UX | Frontend-agnostic, any UI can use |
| 2026-05-17 | Rebrand to ThreatAssessor | Evolved beyond MITRE scope |

---

## Next Steps

1. **Review this design** - Get approval on MoE approach
2. **Start Phase 1** - Implement fail-fast validation (Week 1)
3. **Iterate on experts** - Refactor one at a time (Week 2)
4. **Generate unified reports** - 00_executive_dashboard.md (Week 3)
5. **Rebrand & release** - ThreatAssessor v1.3 (Week 4)

---

**Total Effort:** 36 hours (4 weeks × 1-2 hours/day)  
**Status:** 🎯 APPROVED - Ready to implement  
**Owner:** Development team  
**Target Release:** ThreatAssessor v1.3 (4 weeks)

---

**Generated by:** ThreatAssessor Development Team  
**Date:** 2026-05-17  
**Version:** 1.0
