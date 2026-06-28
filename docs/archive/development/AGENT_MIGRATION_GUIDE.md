# Agent Module Migration Guide

**Version:** 1.0  
**Date:** 2025-05-17  
**Phase:** 3D (MoE Architecture Organization)

---

## Overview

The ThreatAssessor agent system has been reorganized into a clean MoE (Mixture of Experts) structure:

**Old Structure:**
```
chatbot/modules/
├── architect_critic.py
├── tester_critic.py
├── red_teamer_critic.py
├── orchestrator.py
├── threat_analyst.py
├── pattern_registry.py
└── patterns/
    └── ai_pattern.py
```

**New Structure:**
```
chatbot/modules/agents/
├── critics/          # CriticAgents
│   ├── architect_critic.py
│   ├── tester_critic.py
│   └── red_teamer_critic.py
├── analysts/         # AnalystAgents
│   ├── threat_analyst.py
│   ├── pattern_registry.py
│   └── patterns/
│       └── atlas_arc_pattern.py
└── orchestrators/    # OrchestratorAgents
    ├── moe_orchestrator.py
    └── legacy_orchestrator.py
```

---

## Import Migration

### Old Imports (Still Work)

```python
# Old - still supported for backward compatibility
from chatbot.modules.architect_critic import EnhancedArchitectCritic
from chatbot.modules.tester_critic import TesterCritic
from chatbot.modules.red_teamer_critic import RedTeamerCritic
from chatbot.modules.orchestrator import Orchestrator
from chatbot.modules.threat_analyst import ThreatAnalyst
from chatbot.modules.pattern_registry import PatternRegistry
from chatbot.modules.patterns.ai_pattern import AIPattern
```

### New Imports (Recommended)

```python
# New - cleaner, organized by agent type
from chatbot.modules.agents import (
    # Critics
    EnhancedArchitectCritic,
    TesterCritic,
    RedTeamerCritic,
    
    # Analysts
    ThreatAnalyst,
    PatternRegistry,
    
    # Orchestrators
    MoEOrchestrator,
    run_moe_pipeline,
    
    # Exceptions
    MissingPrerequisiteError,
    
    # Result types
    MoEResult,
    ValidationResult,
)
```

### Specific Submodule Imports

```python
# Import from specific submodules if needed
from chatbot.modules.agents.critics import EnhancedArchitectCritic
from chatbot.modules.agents.analysts import ThreatAnalyst
from chatbot.modules.agents.orchestrators import MoEOrchestrator

# Pattern-specific imports
from chatbot.modules.agents.analysts.patterns import AIPattern
```

---

## Code Migration Examples

### Example 1: Full Pipeline

**Old (Phase 3C):**
```python
from chatbot.modules.orchestrator import orchestrate_full_critique

result = orchestrate_full_critique("report/architecture_name")
```

**New (Phase 3D):**
```python
from chatbot.modules.agents import run_moe_pipeline

result = run_moe_pipeline("report/architecture_name")

# Access results
print(f"Confidence: {result.final_confidence:.1f}%")
print(f"Critical: {len(result.critical_recommendations)}")
print(f"High: {len(result.high_recommendations)}")
```

---

### Example 2: Individual Agents

**Old:**
```python
from chatbot.modules.architect_critic import EnhancedArchitectCritic
from chatbot.modules.artifact_extractor import extract_artifacts

critic = EnhancedArchitectCritic()
artifacts = extract_artifacts("report/architecture")
critique = critic.critique(artifacts)
```

**New:**
```python
from chatbot.modules.agents import EnhancedArchitectCritic
from chatbot.modules.artifact_extractor import extract_artifacts

critic = EnhancedArchitectCritic()
artifacts = extract_artifacts("report/architecture")
critique = critic.critique(artifacts)
```

*(Same code, just cleaner import)*

---

### Example 3: Threat Analysis

**Old:**
```python
from chatbot.modules.threat_analyst import ThreatAnalyst

analyst = ThreatAnalyst()
result = analyst.execute({"architecture_path": "arch.mmd"})
```

**New:**
```python
from chatbot.modules.agents import ThreatAnalyst

analyst = ThreatAnalyst()
result = analyst.execute({"architecture_path": "arch.mmd"})
```

*(Same code, just cleaner import)*

---

### Example 4: Custom Orchestration

**Old (Phase 3C):**
```python
from chatbot.modules.orchestrator import Orchestrator
from chatbot.modules.architect_critic import EnhancedArchitectCritic
from chatbot.modules.tester_critic import TesterCritic
from chatbot.modules.red_teamer_critic import RedTeamerCritic

# Create custom agents
architect = EnhancedArchitectCritic()
tester = TesterCritic()
red_team = RedTeamerCritic()

# Old orchestrator (composite scoring)
orchestrator = Orchestrator(agents=[architect, tester, red_team])
result = orchestrator.orchestrate("report/arch")

# Issue: Non-deterministic scoring, conflicting recommendations
print(f"Composite: {result.composite_score}/100")  # ±11 variance
```

**New (Phase 3D):**
```python
from chatbot.modules.agents import MoEOrchestrator

# MoE orchestrator (sequential validation)
orchestrator = MoEOrchestrator()
result = orchestrator.run_pipeline("report/arch")

# Deterministic confidence adjustments
print(f"Confidence: {result.final_confidence:.1f}%")  # Base ± adjustments
print(f"  Base: {result.base_confidence:.1f}%")
print(f"  Architect: {result.architect_adjustment*100:+.1f}%")
print(f"  Tester: {result.tester_adjustment*100:+.1f}%")
print(f"  Red Team: {result.red_team_adjustment*100:+.1f}%")
```

---

## Breaking Changes

### ⚠️ Orchestrator API Change

**Old (Phase 3C):**
```python
from chatbot.modules.orchestrator import Orchestrator

orch = Orchestrator()
result = orch.orchestrate(report_dir)

# Returns OrchestratorResult with:
# - composite_score (30% + 30% + 40%)
# - parallel recommendations
# - conflicting scoring systems
```

**New (Phase 3D):**
```python
from chatbot.modules.agents import MoEOrchestrator

orch = MoEOrchestrator()
result = orch.run_pipeline(report_dir)

# Returns MoEResult with:
# - final_confidence (base ± adjustments)
# - consensus recommendations (critical/high/review)
# - single scoring system
```

**Migration Strategy:**
- For backward compatibility, use `legacy_orchestrator.py`
- For new code, use `moe_orchestrator.py`
- Gradual migration recommended (not forced)

---

### ⚠️ Pattern File Rename

**Old:**
```python
from chatbot.modules.patterns.ai_pattern import AIPattern
```

**New:**
```python
from chatbot.modules.agents.analysts.patterns.atlas_arc_pattern import AIPattern
# OR
from chatbot.modules.agents.analysts.patterns import AIPattern
```

**Reason:** Clarifies that AI pattern uses ATLAS (MITRE) + ARC (framework)

---

## File Location Changes

| Old Location | New Location | Status |
|--------------|--------------|--------|
| `chatbot/modules/architect_critic.py` | `chatbot/modules/agents/critics/architect_critic.py` | ✅ Copied |
| `chatbot/modules/tester_critic.py` | `chatbot/modules/agents/critics/tester_critic.py` | ✅ Copied |
| `chatbot/modules/red_teamer_critic.py` | `chatbot/modules/agents/critics/red_teamer_critic.py` | ✅ Copied |
| `chatbot/modules/threat_analyst.py` | `chatbot/modules/agents/analysts/threat_analyst.py` | ✅ Copied |
| `chatbot/modules/pattern_registry.py` | `chatbot/modules/agents/analysts/pattern_registry.py` | ✅ Copied |
| `chatbot/modules/patterns/ai_pattern.py` | `chatbot/modules/agents/analysts/patterns/atlas_arc_pattern.py` | ✅ Renamed |
| `chatbot/modules/moe_orchestrator.py` | `chatbot/modules/agents/orchestrators/moe_orchestrator.py` | ✅ Moved |
| `chatbot/modules/orchestrator.py` | `chatbot/modules/agents/orchestrators/legacy_orchestrator.py` | ✅ Renamed |

**Backward Compatibility:**
- Old files remain in `chatbot/modules/` for now
- Imports still work from old locations
- Will be deprecated in v1.4 (after Phase 3D complete)

---

## Testing Migration

### Old Test:
```python
from chatbot.modules.moe_orchestrator import run_moe_pipeline

result = run_moe_pipeline("report/arch")
```

### New Test:
```python
from chatbot.modules.agents import run_moe_pipeline

result = run_moe_pipeline("report/arch")
```

Run tests:
```bash
source .venv/bin/activate
python3 scripts/test_moe_foundation.py
```

---

## Migration Checklist

### For Existing Code:

- [ ] Update imports to use `chatbot.modules.agents`
- [ ] Replace `Orchestrator` with `MoEOrchestrator` (if using orchestrator)
- [ ] Update `ai_pattern` imports to `atlas_arc_pattern`
- [ ] Test with `python3 scripts/test_moe_foundation.py`
- [ ] Update documentation references

### For New Code:

- [x] Always use `from chatbot.modules.agents import ...`
- [x] Use `MoEOrchestrator` (not `Orchestrator`)
- [x] Use `run_moe_pipeline()` convenience function
- [x] Follow MoE patterns (sequential, fail-fast, validation-only)

---

## Deprecation Timeline

**Phase 3D (Current):**
- ✅ New structure created (`chatbot/modules/agents/`)
- ✅ Backward compatibility maintained (old imports work)
- ✅ Documentation updated with new imports
- ⚠️ Old orchestrator renamed to `legacy_orchestrator.py`

**v1.3 Release (End of Phase 3D):**
- New code should use new structure
- Old imports marked as deprecated (warnings added)
- Migration guide distributed

**v1.4 (Future):**
- Old files removed from `chatbot/modules/`
- Only `chatbot.modules.agents` supported
- Breaking change announced

---

## Benefits of New Structure

1. **Clear Separation:** Critics vs Analysts vs Orchestrators
2. **MoE Principles:** Sequential validation, fail-fast, consensus
3. **Scalability:** Easy to add new patterns (Cloud, ICS, Mobile)
4. **Discoverability:** `from chatbot.modules.agents import ...` shows all available agents
5. **Maintainability:** Related code grouped together

---

## Questions?

See:
- [Agent Architecture README](../chatbot/modules/agents/README.md)
- [MoE Design Document](../phases/phase3d/MOE_ARCHITECTURE_DESIGN.md)
- [Phase 3D Roadmap](../phases/phase3d/ROADMAP.md)

**Contact:** ThreatAssessor Development Team  
**Version:** 1.0 (Phase 3D Week 1)
