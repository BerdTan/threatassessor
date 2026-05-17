# ThreatAssessor Agent Architecture (MoE)

**Version:** 1.0 (Phase 3D)  
**Date:** 2025-05-17  
**Architecture:** Mixture of Experts (MoE) with Sequential Validation

---

## Overview

ThreatAssessor uses a **Mixture of Experts (MoE)** architecture where specialized agents collaborate to generate and validate threat assessments:

```
┌────────────────────────────────────────────────────────────────┐
│                   LAYER 1: ANALYST AGENT                        │
│                   (Source of Truth - 99.5%)                     │
├────────────────────────────────────────────────────────────────┤
│  ThreatAnalyst (Deterministic)                                  │
│  ├─ Pattern: MITRE + RAPIDS (6 categories, 703 techniques)     │
│  ├─ Pattern: ATLAS + ARC (AI/ML - 170 techniques, 88 controls) │
│  └─> Output: ground_truth.json (99.5% confidence)              │
└────────────────────────────────────────────────────────────────┘
                              ↓
┌────────────────────────────────────────────────────────────────┐
│                   LAYER 2: CRITIC AGENTS                        │
│              (Sequential Validation - LLM-based)                │
├────────────────────────────────────────────────────────────────┤
│  2A: Architect Critic                                           │
│      ├─ Validates: Threat model completeness                   │
│      ├─ Validates: Control appropriateness                     │
│      ├─ Validates: Defense-in-depth coverage                   │
│      └─> Output: 04_architect_critique.json (-0% to -10%)      │
│                              ↓                                  │
│  2B: Tester Critic (requires 04_)                              │
│      ├─ Validates: MITRE mappings correct                      │
│      ├─ Validates: Architect's recommendations valid           │
│      ├─ Validates: Internal consistency                        │
│      └─> Output: 05_tester_critique.json (-0% to -5%)          │
│                              ↓                                  │
│  2C: Red Team Critic (requires 05_)                            │
│      ├─ Validates: Controls would stop real attacks            │
│      ├─ Validates: Bypass scenarios identified                 │
│      ├─ Validates: Tester's assessment correct                 │
│      └─> Output: 06_red_team_critique.json (-0% to -10%)       │
└────────────────────────────────────────────────────────────────┘
                              ↓
┌────────────────────────────────────────────────────────────────┐
│                   LAYER 3: ORCHESTRATOR AGENT                   │
│                   (Consensus & Coherence)                       │
├────────────────────────────────────────────────────────────────┤
│  MoEOrchestrator                                                │
│  ├─ Calculates: Final confidence (base ± adjustments)          │
│  ├─ Synthesizes: Consensus recommendations                     │
│  │   • Critical: All 3 experts agree                           │
│  │   • High: 2 experts agree                                   │
│  │   • Review: 1 expert only (may be false positive)           │
│  └─> Output: 07_moe_orchestrator.json                          │
│      └─> 00_executive_dashboard.md (unified report)            │
└────────────────────────────────────────────────────────────────┘
```

---

## Agent Types

### 1. Analyst Agents (`analysts/`)

**Purpose:** Generate threat assessments from architecture diagrams

**Current Implementation:**
- **ThreatAnalyst** - Deterministic engine (99.5% confidence)
  - RAPIDS threat assessment (6 categories)
  - MITRE ATT&CK technique mapping (703 techniques)
  - Per-node control recommendations
  - Residual risk calculation (BEFORE/AFTER)
  - Pattern-based: MITRE+RAPIDS (core) + ATLAS+ARC (AI/ML)

**Pattern System:**
- **PatternRegistry** - Manages threat patterns for different architectures
- **ATLAS + ARC Pattern** - AI/ML threats (170 techniques, 88 controls)
- Future: Cloud patterns (AWS/Azure/GCP), ICS patterns (OT/SCADA)

**Example:**
```python
from chatbot.modules.agents import ThreatAnalyst

analyst = ThreatAnalyst()
result = analyst.execute({
    "architecture_path": "architecture.mmd"
})

print(f"Confidence: {result.confidence:.1%}")
print(f"Patterns: {result.pattern_sources}")
# Output: ["RAPIDS", "AI/ML (ARC)"]
```

---

### 2. Critic Agents (`critics/`)

**Purpose:** Validate analysis quality (LLM-based validation)

**Current Implementations:**

#### **Architect Critic**
- **Validates:** Threat model completeness, control design, defense-in-depth
- **Rubric:** 100 points (80 Tier 1 + 20 Tier 2)
- **Adjustment:** -0% to -10% confidence
- **Output:** `04_architect_critique.json`

#### **Tester Critic**
- **Validates:** MITRE mappings, internal consistency, Architect's recommendations
- **Rubric:** 100 points (40 validation + 30 coverage + 20 consistency + 10 roadmap)
- **Adjustment:** -0% to -5% confidence
- **Output:** `05_tester_critique.json`

#### **Red Team Critic**
- **Validates:** Control effectiveness, bypass scenarios, exploit difficulty
- **Rubric:** 100 points INVERTED (low score = hard to exploit = good)
- **Adjustment:** -0% to -10% confidence
- **Output:** `06_red_team_critique.json`

**Example:**
```python
from chatbot.modules.agents import EnhancedArchitectCritic
from chatbot.modules.artifact_extractor import extract_artifacts

critic = EnhancedArchitectCritic()
artifacts = extract_artifacts("report/architecture_name")
critique = critic.critique(artifacts)

print(f"Score: {critique.score}/100")
print(f"Adjustment: {critique.confidence_adjustment*100:.1f}%")
```

---

### 3. Orchestrator Agents (`orchestrators/`)

**Purpose:** Coordinate agents and synthesize consensus

**Current Implementation:**

#### **MoEOrchestrator** (Phase 3D - Current)
- **Sequential validation:** Layer 1 → 2A → 2B → 2C → 3
- **Fail-fast:** Missing prerequisite = abort immediately
- **Confidence formula:** Base × (1 + arch_adj) × (1 + test_adj) × (1 + red_adj)
- **Consensus:** Critical (3 agree) > High (2 agree) > Review (1 only)
- **Output:** `07_moe_orchestrator.json`

#### **LegacyOrchestrator** (Phase 3C - Deprecated)
- Parallel agent execution
- Composite scoring (conflicts with deterministic)
- Non-deterministic output (±11 point variance)
- Kept for backward compatibility only

**Example:**
```python
from chatbot.modules.agents import run_moe_pipeline

result = run_moe_pipeline("report/architecture_name")

print(f"Final confidence: {result.final_confidence:.1f}%")
print(f"  Base: {result.base_confidence:.1f}%")
print(f"  Architect: {result.architect_adjustment*100:+.1f}%")
print(f"  Tester: {result.tester_adjustment*100:+.1f}%")
print(f"  Red Team: {result.red_team_adjustment*100:+.1f}%")

print(f"\nConsensus:")
print(f"  Critical: {len(result.critical_recommendations)}")
print(f"  High: {len(result.high_recommendations)}")
print(f"  Review: {len(result.review_recommendations)}")
```

---

## Key Principles

### 1. Sequential Dependencies (Fail-Fast)

Each layer requires previous outputs or **aborts immediately**:

```python
# Layer 1: Deterministic (required)
if not ground_truth.json.exists():
    raise MissingPrerequisiteError("ground_truth.json not found")

# Layer 2A: Architect (required)
if not 04_architect_critique.json.exists():
    raise MissingPrerequisiteError("04_architect_critique.json not found")

# Layer 2B: Tester (required)
if not 05_tester_critique.json.exists():
    raise MissingPrerequisiteError("05_tester_critique.json not found")

# Layer 2C: Red Team (required)
if not 06_red_team_critique.json.exists():
    raise MissingPrerequisiteError("06_red_team_critique.json not found")
```

**Philosophy:** Quality over quantity - don't proceed with bad data.

---

### 2. Deterministic as Source of Truth

```
Deterministic (ThreatAnalyst)  → Recommendations (what to do)
LLM Experts (Critics)          → Validation (how confident we are)
Orchestrator                   → Presentation (how to communicate)
```

**No parallel recommendations!** Critics validate only, they don't create new controls.

---

### 3. Confidence Adjustments (Not Parallel Scores)

```
Base confidence: 99.5% (deterministic)

Architect validation:
✓ PASS         → +0%
⚠️ MINOR GAPS  → -2% to -5%
❌ MAJOR GAPS  → -10%

Tester validation:
✓ PASS         → +0%
⚠️ MINOR GAPS  → -1% to -3%
❌ MAJOR GAPS  → -5%

Red Team validation:
✓ PASS         → +0%
⚠️ BYPASS RISKS → -3% to -6%
❌ INEFFECTIVE → -10%

Final = 99.5% × (1-0.05) × (1-0.03) × (1-0.06) = 86.1%
```

Capped at 100%, floored at 50%.

---

### 4. Consensus Recommendations Only

Orchestrator outputs **unified** recommendations:

```json
{
  "critical_recommendations": [
    {
      "description": "Missing WAF",
      "source": "Architect + Tester + Red Team",
      "confidence": 99,
      "priority": "CRITICAL"
    }
  ],
  "high_recommendations": [
    {
      "description": "Weak MFA",
      "source": "Tester + Red Team",
      "confidence": 66,
      "priority": "HIGH"
    }
  ],
  "review_recommendations": [
    {
      "description": "Add load balancer",
      "source": "Architect only",
      "confidence": 33,
      "priority": "REVIEW"
    }
  ]
}
```

---

## Usage

### Full Pipeline

```python
from chatbot.modules.agents import run_moe_pipeline

result = run_moe_pipeline(
    report_dir="report/architecture_name",
    base_confidence=99.5
)
```

### Individual Agents

```python
from chatbot.modules.agents import (
    ThreatAnalyst,
    EnhancedArchitectCritic,
    TesterCritic,
    RedTeamerCritic,
    MoEOrchestrator
)

# Layer 1: Generate threat assessment
analyst = ThreatAnalyst()
analysis = analyst.execute({"architecture_path": "architecture.mmd"})

# Layer 2: Validate with critics
architect = EnhancedArchitectCritic()
tester = TesterCritic()
red_team = RedTeamerCritic()

architect_critique = architect.critique(artifacts)
tester_critique = tester.critique(artifacts, architect_critique)
red_team_critique = red_team.critique(artifacts, ground_truth, tester_critique)

# Layer 3: Synthesize consensus
orchestrator = MoEOrchestrator()
result = orchestrator.run_pipeline(report_dir)
```

---

## File Structure

```
chatbot/modules/agents/
├── __init__.py           # Main exports
├── README.md             # This file
│
├── critics/              # CriticAgents - Validate analysis quality
│   ├── __init__.py
│   ├── architect_critic.py
│   ├── tester_critic.py
│   └── red_teamer_critic.py
│
├── analysts/             # AnalystAgents - Generate threat assessments
│   ├── __init__.py
│   ├── threat_analyst.py
│   ├── pattern_registry.py
│   └── patterns/
│       ├── __init__.py
│       └── atlas_arc_pattern.py (AI/ML: ATLAS + ARC)
│
└── orchestrators/        # OrchestratorAgents - Coordinate & Consensus
    ├── __init__.py
    ├── moe_orchestrator.py (Phase 3D - current)
    └── legacy_orchestrator.py (Phase 3C - deprecated)
```

---

## Output Files (15 files per architecture)

```
report/architecture_name/
├── ground_truth.json           # Layer 1: Deterministic analysis
├── 04_architect_critique.json  # Layer 2A: Architect validation
├── 05_tester_critique.json     # Layer 2B: Tester validation
├── 06_red_team_critique.json   # Layer 2C: Red Team validation
├── 07_moe_orchestrator.json    # Layer 3: Consensus synthesis
│
├── 00_executive_dashboard.md   # Unified CISO report (Phase 3D)
├── 01_executive_summary.md     # Legacy (Phase 3C)
├── 02_technical_report.md      # Engineer report
├── 03_action_plan.md           # Implementation guide
├── 08_improvement_summary.md   # Improvement options
│
├── before.mmd                  # Current architecture
├── after.mmd                   # With all controls (color-coded)
├── 08a_quick_wins.mmd          # Critical controls only (1-2 weeks)
├── 08b_recommended_target.mmd  # Critical + High (1-3 months)
└── 08c_maximum_security.mmd    # All controls (6+ months)
```

---

## Testing

Run MoE foundation tests:

```bash
source .venv/bin/activate
python3 scripts/test_moe_foundation.py
```

Tests:
1. ✅ Fail-fast validation (missing prerequisite)
2. ✅ Sequential enforcement (Layer 1 → 2A → 2B → 2C → 3)
3. ✅ Confidence adjustments (formula validation)
4. ✅ Consensus synthesis (recommendation prioritization)

---

## Migration Notes

### From Old Structure to Agents Module

**Old locations:**
```python
# Old imports (still work via backward compatibility)
from chatbot.modules.architect_critic import EnhancedArchitectCritic
from chatbot.modules.tester_critic import TesterCritic
from chatbot.modules.red_teamer_critic import RedTeamerCritic
from chatbot.modules.orchestrator import Orchestrator
from chatbot.modules.threat_analyst import ThreatAnalyst
```

**New locations:**
```python
# New imports (recommended)
from chatbot.modules.agents import (
    EnhancedArchitectCritic,
    TesterCritic,
    RedTeamerCritic,
    MoEOrchestrator,
    ThreatAnalyst,
    run_moe_pipeline
)
```

**Backward compatibility:**
- Old files remain in `chatbot/modules/` for backward compatibility
- New code should use `chatbot.modules.agents` imports
- Gradual migration over Phase 3D

---

## Roadmap

### Phase 3D Week 1: Foundation ✅ COMPLETE
- [x] MoEOrchestrator with fail-fast validation
- [x] Sequential enforcement (Layer 1 → 2A → 2B → 2C → 3)
- [x] Confidence adjustment formula
- [x] Test suite (4/4 tests passing)

### Phase 3D Week 2: Expert Refactoring (In Progress)
- [ ] Refactor Architect → validation only (not new recommendations)
- [ ] Refactor Tester → validates Architect + MITRE
- [ ] Refactor Red Team → validates Tester + controls

### Phase 3D Week 3: Unified Orchestration
- [ ] Create `00_executive_dashboard.md` generator
- [ ] Update `08_improvement_summary.md` (remove cryptic dict strings)
- [ ] Add cross-references between reports

### Phase 3D Week 4: Branding & Polish
- [ ] Rebrand "MITRE Chatbot" → "ThreatAssessor"
- [ ] Create API specification (frontend-agnostic)
- [ ] Test on 10 architectures (validate 15/15 files)

---

**Status:** Phase 3D Week 1 ✅ Complete  
**Next:** Week 2 - Expert Refactoring (validation only, not parallel recommendations)  
**Target:** ThreatAssessor v1.3 release (4 weeks)
