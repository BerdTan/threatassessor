# ThreatAssessor MoE UI Design - Complete Visualization Plan

## Executive Summary

This document describes how the UI will visualize the **Mixture of Experts (MoE)** validation workflow, showing outputs from:
- **Team 1**: Deterministic Engine (99.5% confidence)
- **Team 2**: Architect Critic (confidence adjustment)
- **Team 3**: Tester Critic (confidence adjustment)
- **Team 4**: Red Team Critic (confidence adjustment)

---

## Current State: Deterministic Engine Only

### UI Layout (Team 1)
```
┌─────────────────────────────────────────────────────────────────┐
│ Header: ThreatAssessor - Deterministic Engine                  │
│ [Pattern Badges] [Theme] [New Analysis]                        │
├──────────┬──────────────────────────────────────────┬──────────┤
│ Sidebar  │ Center Pane: Analysis Results            │ Right    │
│          │                                          │ Pane     │
│ 📊 Overview    Tab Content:                         │ (Detail) │
│ 🎯 Attacks    - Overview: Threat chart + Diagram    │          │
│ 🛡️ Controls   - Attacks: Attack paths list          │          │
│ 🔒 Hardening  - Controls: Recommendations            │          │
│ 📋 MITRE      - Hardening: Before/After viz         │          │
│ 📄 Reports    - MITRE: Technique matrix             │          │
│ 💾 Data       - Reports: Generated files            │          │
│               - Raw Data: JSON artifacts            │          │
├──────────┴──────────────────────────────────────────┴──────────┤
│ Footer: [Progress: 100%] [Status: Complete] [GitHub] [Docs]    │
└─────────────────────────────────────────────────────────────────┘

Confidence: 99.5% (Deterministic only)
```

---

## Proposed State: MoE Validation Added

### New UI Layout (Teams 1-4)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Header: ThreatAssessor - MoE Validation Engine                              │
│ [Confidence: 99.5% → 93.8%] [Pattern Badges] [Theme] [New Analysis]        │
├──────────┬──────────────────────────────────────────────────┬───────────────┤
│ Session  │ Center Pane: Analysis + Validation               │ Expert Detail │
│ History  │                                                  │ (Right Pane)  │
│          │ ┌─────────────────────────────────────────────┐ │               │
│ 📁 Sessions   │ Phase Selector (Horizontal Pills)        │ │               │
│ ──────────    │ [Team 1: Base] [Team 2: Arch] [Team 3:  │ │               │
│ ● web_app.mmd │  Tester] [Team 4: Red Team] [Summary]   │ │               │
│   99.5%→93.8% │ └─────────────────────────────────────────┘ │               │
│   2m ago      │                                             │               │
│               │ Tab Navigation (Vertical):                   │               │
│ ○ api_gw.mmd  │ ┌────────────────────────────────────────┐ │               │
│   (no MoE)    │ │ 📊 Overview                            │ │               │
│               │ │ 🎯 Attack Paths                        │ │               │
│ [+ New]       │ │ 🛡️ Controls                            │ │               │
│               │ │ 🔒 Hardening                           │ │               │
│               │ │ 🧑‍🏫 Validation (NEW)                   │ │               │
│               │ │ 📋 MITRE                               │ │               │
│               │ │ 📄 Reports                             │ │               │
│               │ │ 💾 Raw Data                            │ │               │
│               │ └────────────────────────────────────────┘ │               │
│               │                                             │               │
│               │ Content Area (Changes per Phase):           │               │
│               │ [Phase-specific content here]               │               │
├──────────┴──────────────────────────────────────────────────┴───────────────┤
│ Footer: [Progress] [Status: Team 2 validating...] [Confidence: 95.2%]      │
│         [GitHub] [Docs]                                                     │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Phase Selector: Horizontal Pills (NEW)

**Location**: Top of center pane, below header  
**Purpose**: Switch between deterministic base and each expert's validation

### Visual Design
```
┌──────────────────────────────────────────────────────────────────┐
│ Analysis Phase:                                                  │
│ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐   │
│ │ Team 1  │ │ Team 2  │ │ Team 3  │ │ Team 4  │ │ Summary │   │
│ │ Base    │ │ Architect│ │ Tester  │ │ Red Team│ │ Final   │   │
│ │ 99.5%   │ │ -5.0%   │ │ -3.2%   │ │ -2.5%   │ │ 93.8%   │   │
│ │ ✅ Done  │ │ ✅ Done  │ │ ✅ Done  │ │ ✅ Done  │ │ View    │   │
│ └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘   │
└──────────────────────────────────────────────────────────────────┘

States:
- ⏳ Pending (gray, disabled)
- 🔄 Running (blue, animated spinner)
- ✅ Done (green, clickable)
- ⚠️ Issues Found (orange, clickable)
- ❌ Failed (red, clickable)
```

**Interaction**:
- Click any phase to view that expert's analysis
- Greyed out if not yet run
- Shows confidence delta (e.g., "-5.0%" for Architect)

---

## NEW Tab: 🧑‍🏫 Validation

**Purpose**: Show MoE expert critiques and confidence adjustments

### Content Layout

```
┌────────────────────────────────────────────────────────────────┐
│ 🧑‍🏫 Validation: Expert Critique Summary                        │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│ Confidence Progression:                                        │
│ ┌──────────────────────────────────────────────────────────┐ │
│ │ 99.5% ──→ 94.5% ──→ 91.3% ──→ 88.8% ──→ 93.8% (Final)   │ │
│ │ Base     Architect  Tester    Red Team   + Synthesis     │ │
│ └──────────────────────────────────────────────────────────┘ │
│                                                                │
│ ┌──────────────────────────────────────────────────────────┐ │
│ │ Expert             Confidence  Issues      Status        │ │
│ │                    Adjustment  Found                     │ │
│ ├──────────────────────────────────────────────────────────┤ │
│ │ 🏛️ Architect       -5.0%       2 gaps     ✅ Passed     │ │
│ │ 🧪 Tester          -3.2%       5 issues   ✅ Passed     │ │
│ │ 🎯 Red Team        -2.5%       3 concerns ✅ Passed     │ │
│ │ 🔄 Synthesis       +5.0%       Harmonized ✅ Complete   │ │
│ └──────────────────────────────────────────────────────────┘ │
│                                                                │
│ Expert Critiques (Click to expand):                           │
│ ┌──────────────────────────────────────────────────────────┐ │
│ │ ▶ 🏛️ Architect: Threat Model Completeness              │ │
│ └──────────────────────────────────────────────────────────┘ │
│ ┌──────────────────────────────────────────────────────────┐ │
│ │ ▶ 🧪 Tester: MITRE Mapping Accuracy                     │ │
│ └──────────────────────────────────────────────────────────┘ │
│ ┌──────────────────────────────────────────────────────────┐ │
│ │ ▶ 🎯 Red Team: Control Effectiveness                    │ │
│ └──────────────────────────────────────────────────────────┘ │
│                                                                │
│ [View Full Validation Report →]                               │
└────────────────────────────────────────────────────────────────┘
```

**Expandable Sections**: Click any expert to see detailed critique in right pane

---

## Team 2: Architect Critic Output

**Phase Pill**: "Team 2 - Architect"  
**Confidence**: Base 99.5% → After -5.0% = 94.5%

### Right Pane Detail View (When Selected)

```
┌────────────────────────────────────────────────────────────────┐
│ 🏛️ Architect Critic: Threat Model Completeness                │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│ Confidence Adjustment: -5.0%                                   │
│ Rationale: Minor threat model gaps identified                 │
│                                                                │
│ ┌──────────────────────────────────────────────────────────┐ │
│ │ Issues Found (2):                                        │ │
│ │                                                          │ │
│ │ ⚠️ Issue #1: Missing Data Flow Validation               │ │
│ │ Severity: MEDIUM                                         │ │
│ │ Location: WebApp → Database edge                         │ │
│ │ Description: Data flow lacks input validation control.  │ │
│ │              Could allow injection attacks.              │ │
│ │ Recommendation: Add input validation control at edge.   │ │
│ │                                                          │ │
│ │ ⚠️ Issue #2: Incomplete Trust Boundary                   │ │
│ │ Severity: LOW                                            │ │
│ │ Location: External → DMZ zone                            │ │
│ │ Description: Trust boundary not explicitly defined.      │ │
│ │ Recommendation: Add explicit trust boundary annotation. │ │
│ └──────────────────────────────────────────────────────────┘ │
│                                                                │
│ Validation Checks (6):                                         │
│ ✅ Component identification                                    │
│ ✅ Trust boundaries defined                                    │
│ ⚠️ Data flows complete (2 gaps)                               │
│ ✅ Attack surface mapped                                       │
│ ✅ Threat categories covered                                   │
│ ✅ Control coverage adequate                                   │
│                                                                │
│ Expert Commentary:                                             │
│ "The base threat model is comprehensive with good coverage    │
│ of RAPIDS categories. Minor gaps in data flow validation      │
│ reduce confidence slightly. Recommend adding input validation │
│ controls at identified edges."                                 │
│                                                                │
│ [View Full Architect Report →]                                │
└────────────────────────────────────────────────────────────────┘
```

---

## Team 3: Tester Critic Output

**Phase Pill**: "Team 3 - Tester"  
**Confidence**: After Architect 94.5% → After -3.2% = 91.3%

### Right Pane Detail View

```
┌────────────────────────────────────────────────────────────────┐
│ 🧪 Tester Critic: MITRE Mapping Accuracy                       │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│ Confidence Adjustment: -3.2%                                   │
│ Rationale: MITRE technique coverage has minor gaps             │
│                                                                │
│ ┌──────────────────────────────────────────────────────────┐ │
│ │ Issues Found (5):                                        │ │
│ │                                                          │ │
│ │ ⚠️ Missing Technique: T1133 (External Remote Services)  │ │
│ │ Location: Internet → WebApp edge                         │ │
│ │ Expected: Should be mapped based on architecture         │ │
│ │ Impact: Coverage gap of 7%                               │ │
│ │                                                          │ │
│ │ ⚠️ Over-mapped Technique: T1543 (Service Creation)      │ │
│ │ Location: WebApp node                                    │ │
│ │ Rationale: Architecture doesn't show service creation   │ │
│ │ Recommendation: Remove or justify mapping               │ │
│ │                                                          │ │
│ │ [+3 more issues]                                         │ │
│ └──────────────────────────────────────────────────────────┘ │
│                                                                │
│ MITRE Coverage Analysis:                                       │
│ ┌──────────────────────────────────────────────────────────┐ │
│ │ Total Techniques Identified: 47                          │ │
│ │ Correct Mappings: 44 (93.6%)                             │ │
│ │ Missing: 3 (6.4%)                                        │ │
│ │ Over-mapped: 2 (4.3%)                                    │ │
│ │                                                          │ │
│ │ Tactic Coverage:                                         │ │
│ │ ✅ Initial Access: 100%                                  │ │
│ │ ✅ Execution: 95%                                        │ │
│ │ ⚠️ Persistence: 85% (1 missing)                          │ │
│ │ ✅ Privilege Escalation: 100%                            │ │
│ │ ... (14 tactics total)                                   │ │
│ └──────────────────────────────────────────────────────────┘ │
│                                                                │
│ Expert Commentary:                                             │
│ "MITRE mapping quality is good overall. Minor discrepancies   │
│ in technique coverage suggest the deterministic engine may    │
│ need refinement for edge-case detection. Recommended          │
│ improvements documented."                                      │
│                                                                │
│ [View Detailed Coverage Report →]                             │
└────────────────────────────────────────────────────────────────┘
```

---

## Team 4: Red Team Critic Output

**Phase Pill**: "Team 4 - Red Team"  
**Confidence**: After Tester 91.3% → After -2.5% = 88.8%

### Right Pane Detail View

```
┌────────────────────────────────────────────────────────────────┐
│ 🎯 Red Team Critic: Control Effectiveness Review               │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│ Confidence Adjustment: -2.5%                                   │
│ Rationale: Control placement has implementation concerns       │
│                                                                │
│ ┌──────────────────────────────────────────────────────────┐ │
│ │ Concerns Found (3):                                      │ │
│ │                                                          │ │
│ │ ⚠️ Concern #1: WAF Bypass Potential                      │ │
│ │ Control: Web Application Firewall                        │ │
│ │ Location: Internet → WebApp edge                         │ │
│ │ Issue: WAF alone may not stop all injection attacks     │ │
│ │ Attack Vector: HTTP smuggling, encoding bypass          │ │
│ │ Recommendation: Add input validation + output encoding  │ │
│ │ Risk: MEDIUM                                             │ │
│ │                                                          │ │
│ │ ⚠️ Concern #2: Lateral Movement Not Addressed            │ │
│ │ Control: Network Segmentation                            │ │
│ │ Location: DMZ → Internal zone                            │ │
│ │ Issue: Segmentation may be bypassed after initial       │ │
│ │        compromise                                        │ │
│ │ Recommendation: Add micro-segmentation + EDR            │ │
│ │ Risk: HIGH                                               │ │
│ │                                                          │ │
│ │ [+1 more concern]                                        │ │
│ └──────────────────────────────────────────────────────────┘ │
│                                                                │
│ Attack Path Resistance Analysis:                               │
│ ┌──────────────────────────────────────────────────────────┐ │
│ │ AP-1 (CRITICAL): Internet → WebApp → DB                 │ │
│ │ Defense Score: 54/100                                    │ │
│ │ Weakness: WAF alone insufficient                         │ │
│ │                                                          │ │
│ │ AP-2 (HIGH): Internet → API → Backend                   │ │
│ │ Defense Score: 67/100                                    │ │
│ │ Weakness: API gateway lacks rate limiting                │ │
│ │                                                          │ │
│ │ [+3 more paths]                                          │ │
│ └──────────────────────────────────────────────────────────┘ │
│                                                                │
│ Exploitability Assessment:                                     │
│ "Controls recommended by deterministic engine are sound       │
│ but may face real-world implementation challenges. Specific   │
│ bypass techniques identified. Defense-in-depth approach       │
│ recommended with layered controls."                            │
│                                                                │
│ [View Attack Scenarios →]                                     │
└────────────────────────────────────────────────────────────────┘
```

---

## Summary Phase: Final Consensus

**Phase Pill**: "Summary - Final"  
**Confidence**: 93.8% (after synthesis adds +5.0% for harmonization)

### Center Pane Content

```
┌────────────────────────────────────────────────────────────────┐
│ 📊 MoE Validation Summary                                      │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│ Final Confidence: 93.8% ✅                                     │
│ Status: PASSED (threshold: 90%)                                │
│                                                                │
│ Confidence Progression:                                        │
│ ┌──────────────────────────────────────────────────────────┐ │
│ │   99.5%                                                  │ │
│ │   │ Team 1: Deterministic Base                           │ │
│ │   ▼ -5.0%                                                │ │
│ │   94.5%                                                  │ │
│ │   │ Team 2: Architect (threat model gaps)               │ │
│ │   ▼ -3.2%                                                │ │
│ │   91.3%                                                  │ │
│ │   │ Team 3: Tester (MITRE coverage gaps)                │ │
│ │   ▼ -2.5%                                                │ │
│ │   88.8%                                                  │ │
│ │   │ Team 4: Red Team (control concerns)                 │ │
│ │   ▼ +5.0%                                                │ │
│ │   93.8% ✅                                               │ │
│ │   Synthesis: Harmonized findings                         │ │
│ └──────────────────────────────────────────────────────────┘ │
│                                                                │
│ Issue Summary:                                                 │
│ ┌──────────────────────────────────────────────────────────┐ │
│ │ Expert        Issues  Severity         Resolved          │ │
│ ├──────────────────────────────────────────────────────────┤ │
│ │ Architect     2       MEDIUM (1), LOW (1)   ✅ 2/2       │ │
│ │ Tester        5       LOW (5)               ✅ 5/5       │ │
│ │ Red Team      3       HIGH (1), MEDIUM (2)  ⚠️ 1/3       │ │
│ │ TOTAL         10      HIGH (1), MED (3), LOW (6)         │ │
│ └──────────────────────────────────────────────────────────┘ │
│                                                                │
│ Key Findings:                                                  │
│ ✅ Threat model coverage: Good (minor gaps addressed)         │
│ ✅ MITRE technique mapping: 93.6% accuracy                    │
│ ⚠️ Control effectiveness: 1 high-risk concern outstanding     │
│                                                                │
│ Recommendations:                                               │
│ 1. Add input validation at WebApp → DB edge (Architect)      │
│ 2. Review MITRE T1133 mapping for Internet edge (Tester)     │
│ 3. Implement defense-in-depth for AP-1 (Red Team) ⚠️         │
│                                                                │
│ Synthesis Report:                                              │
│ "MoE validation confirms deterministic engine produces high-  │
│ quality threat assessments. Identified improvements are       │
│ minor and don't affect overall architecture defensibility.    │
│ Final confidence of 93.8% indicates production-ready          │
│ assessment with documented enhancement opportunities."         │
│                                                                │
│ [Download Full MoE Report] [Export PDF] [View Comparison]    │
└────────────────────────────────────────────────────────────────┘
```

---

## Visualization: Confidence Waterfall Chart (NEW)

**Location**: Summary tab, top section  
**Purpose**: Show confidence progression visually

```
Confidence Waterfall:

100% ┤
     │ ┌────┐
     │ │99.5│
 95% ┤ │    │ ┌────┐
     │ │    │ │94.5│
     │ │    │ │    │ ┌────┐
 90% ┤ │    │ │    │ │91.3│ ┌────┐           ┌────┐
     │ │    │ │    │ │    │ │88.8│           │93.8│
     │ │    │ │    │ │    │ │    │           │    │
 85% ┤ │    │ │    │ │    │ │    │           │    │
     ├─┴────┴─┴────┴─┴────┴─┴────┴───────────┴────┴─
       Base  Architect Tester Red Team    Synthesis
             -5.0%    -3.2%   -2.5%        +5.0%

Legend:
█ Green: Passed (≥90%)
█ Yellow: Review (85-89%)
█ Red: Failed (<85%)
```

---

## Session History Sidebar (LEFT PANE - NEW)

**Purpose**: Show multiple analysis sessions, track MoE status

```
┌──────────────────────────────────┐
│ 📁 Analysis Sessions             │
├──────────────────────────────────┤
│                                  │
│ ● web_app.mmd                    │
│   ├─ Base: 99.5% ✅             │
│   ├─ Architect: -5.0% ✅        │
│   ├─ Tester: -3.2% ✅           │
│   ├─ Red Team: -2.5% ✅         │
│   └─ Final: 93.8% ✅            │
│   2 minutes ago                  │
│                                  │
│ ○ api_gateway.mmd                │
│   ├─ Base: 99.5% ✅             │
│   └─ (MoE not run)               │
│   1 hour ago                     │
│                                  │
│ ○ legacy_app.mmd                 │
│   ├─ Base: 99.5% ✅             │
│   ├─ Architect: -8.0% ⚠️        │
│   ├─ Tester: -5.5% ⚠️           │
│   ├─ Red Team: -6.0% ❌         │
│   └─ Final: 79.0% ❌ (FAILED)   │
│   Yesterday                      │
│                                  │
│ [+ New Analysis]                 │
└──────────────────────────────────┘

States:
● Active (blue dot)
○ Inactive (gray dot)
✅ Passed
⚠️ Warning
❌ Failed
```

---

## Footer Changes During MoE

**Current (Deterministic)**:
```
[Progress: 100%] [Status: Analysis complete] [GitHub] [Docs]
```

**During MoE Validation**:
```
[Team 2: 45%] [Status: Architect validating threat model...] [Conf: 94.5%→?]
```

**After MoE Complete**:
```
[Complete] [Status: MoE validation complete] [Confidence: 93.8%] [GitHub]
```

---

## API Endpoints for MoE (Future)

```
POST /api/v1/validate-moe
  Request: {
    "architecture_name": "web_app",
    "ground_truth_path": "report/web_app/ground_truth.json",
    "enable_fail_fast": false,
    "critics": ["architect", "tester", "red_teamer"]
  }
  
  Response: SSE stream with:
  - event: critic_start (team 2, 3, or 4 starting)
  - event: critic_progress (intermediate updates)
  - event: critic_complete (issues found, confidence delta)
  - event: synthesis_complete (final confidence)
  - event: moe_complete (full result)
```

---

## Implementation Phases

### Phase 1: UI Structure (Week 1)
- [ ] Add phase selector (horizontal pills)
- [ ] Add 🧑‍🏫 Validation tab
- [ ] Add session history sidebar
- [ ] Update footer for MoE progress

### Phase 2: Data Integration (Week 2)
- [ ] Wire up MoE API endpoints
- [ ] Parse critic outputs
- [ ] Display confidence progression
- [ ] Show issue details in right pane

### Phase 3: Visualizations (Week 3)
- [ ] Confidence waterfall chart
- [ ] Issue severity heatmap
- [ ] Expert comparison matrix
- [ ] Before/after comparison (enhanced)

### Phase 4: Polish (Week 4)
- [ ] Animations for confidence changes
- [ ] Export MoE reports
- [ ] Session comparison view
- [ ] Mobile responsive design

---

## Summary: Where MoE Outputs Appear

| Team | Output Location | UI Component |
|------|----------------|--------------|
| **Team 1** (Base) | All existing tabs | Current UI (no change) |
| **Team 2** (Architect) | 🧑‍🏫 Validation tab + Right pane | Expandable critique card |
| **Team 3** (Tester) | 🧑‍🏫 Validation tab + Right pane | MITRE coverage analysis |
| **Team 4** (Red Team) | 🧑‍🏫 Validation tab + Right pane | Attack resistance scores |
| **Synthesis** | Summary phase | Confidence waterfall + final report |

**Key Principle**: Keep deterministic results (Team 1) unchanged. MoE adds **NEW** validation tab showing expert critiques, confidence progression, and final harmonized assessment.

---

## Mockup: Complete UI With MoE

```
┌──────────────────────────────────────────────────────────────────────────┐
│ 🛡️ ThreatAssessor - MoE Validation Engine                                │
│ Confidence: 99.5% → 93.8% ✅ | [RAPIDS] [Theme 🌙] [🔄 New Analysis]    │
├────────────┬─────────────────────────────────────────────┬───────────────┤
│ 📁 Sessions│ Phase: [Base ✅][Architect ✅][Tester ✅]   │ 🏛️ Architect  │
│            │        [Red Team ✅][Summary]                │ Detail        │
│ ● web_app  │ ────────────────────────────────────────── │ ────────────  │
│  93.8% ✅  │ Tab: 🧑‍🏫 Validation                        │ Confidence:   │
│  2m ago    │ ┌──────────────────────────────────────┐   │ -5.0%         │
│            │ │ Confidence: 99.5%→94.5%→91.3%→88.8% │   │               │
│ ○ api_gw   │ │             ↓ +5.0% = 93.8% ✅       │   │ Issues (2):   │
│  99.5%     │ └──────────────────────────────────────┘   │ ⚠️ Data flow  │
│  1h ago    │ Expert Summary:                            │   validation  │
│            │ ┌──────────────────────────────────────┐   │ ⚠️ Trust      │
│ [+ New]    │ │ 🏛️ Architect  -5.0%  2 gaps  ✅     │   │   boundary    │
│            │ │ 🧪 Tester     -3.2%  5 issues ✅    │   │               │
│            │ │ 🎯 Red Team   -2.5%  3 concerns ✅  │   │ "Minor gaps   │
│            │ └──────────────────────────────────────┘   │  identified.  │
│            │ [Click expert to view details →]           │  Overall good │
│            │                                            │  coverage."   │
├────────────┴─────────────────────────────────────────────┴───────────────┤
│ [Complete] [Status: MoE validation complete] [93.8%] [GitHub] [Docs]    │
└──────────────────────────────────────────────────────────────────────────┘
```

---

**End of Design Document**

Built with ❤️ by BerdTan | © 2026 ThreatAssessor
