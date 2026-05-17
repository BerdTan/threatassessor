# Phase 3B+ → 3C+: Priority & Orchestration Roadmap

**Date:** 2026-05-17  
**Overall Timeline:** 15-21 hours across 3 phases  
**Status:** Phase 1 ✅ Complete, Phase 2 📋 Next, Phase 3 🔮 Optional

---

## Overview: Three-Phase Approach

```
Phase 1 (3B++): Color Coding → Phase 2 (3C+): Orchestrator → Phase 3 (Optional): MoE Refactor
     1 hour                         6-8 hours                      8-12 hours
    ✅ DONE                        📋 NEXT                        🔮 FUTURE
```

**Goal:** Transform deterministic threat analysis into LLM-validated, consensus-driven prioritization with visual roadmaps

---

## Phase 1: Priority Color Coding (3B++) ✅ COMPLETE

**Date:** 2026-05-17  
**Effort:** 1 hour  
**Status:** ✅ Production Ready  

### What We Built
- Priority-based color coding for `after.mmd` diagrams
- Visual legend (🔴 critical, 🟡 high, 🔵 medium, 🟢 baseline)
- Deterministic priority from existing `ground_truth.json`

### Results
- Zero confidence impact (99.5% → 99.5%)
- Immediate visual value for CISOs
- Tested across 3 architectures (AI + traditional)
- Color distribution: 29 critical, 6 high, 2 medium (typical AI architecture)

### Files
- `chatbot/modules/threat_report.py` (+35 lines)
- `docs/phases/phase3b_plus/PRIORITY_COLOR_CODING.md`

**Commit:** `0115008` - "feat: Add priority-based color coding to after.mmd diagrams"

**See:** [PRIORITY_COLOR_CODING.md](PRIORITY_COLOR_CODING.md) for details

---

## Phase 2: Orchestrator Consensus (3C+) 📋 NEXT SPRINT

**Estimated Effort:** 6-8 hours  
**Timeline:** Split across 5 commits  
**Goal:** LLM-validated priorities with stepped implementation roadmaps

### Architecture: Three-Agent Consensus

```
┌─────────────────────────────────────────────────────────────┐
│                  Deterministic Analysis                      │
│           (ground_truth.json with priorities)                │
└────────────────────────┬────────────────────────────────────┘
                         │
          ┌──────────────┼──────────────┐
          │              │              │
    ┌─────▼─────┐  ┌─────▼─────┐  ┌────▼────────┐
    │ Architect │  │   Tester  │  │  Red Teamer │
    │  Critic   │  │  Critic   │  │   Critic    │
    └─────┬─────┘  └─────┬─────┘  └─────┬───────┘
          │              │               │
          └──────────────┼───────────────┘
                         │
                ┌────────▼────────┐
                │  Orchestrator   │
                │   (Consensus)   │
                └────────┬────────┘
                         │
         ┌───────────────┼───────────────┐
         │               │               │
    ┌────▼────┐    ┌────▼────┐    ┌────▼────┐
    │ Quick   │    │Recommend│    │ Maximum │
    │ Wins    │    │ Target  │    │Security │
    │ (1-2w)  │    │(1-3mo)⭐│    │ (6+mo)  │
    └─────────┘    └─────────┘    └─────────┘
```

### Task Breakdown

#### Task 1: Save Red Team Critique Separately (1h)
**Goal:** Make Red Team findings accessible without parsing orchestrator report

**Changes:**
- Modify `chatbot/modules/orchestrator.py`
- Add `_save_red_team_critique()` method
- Output: `report/{arch}/06_red_team_critique.json`

**File structure:**
```json
{
  "agent": "Red Teamer",
  "score": 40,
  "rating": "LOW = hard to exploit = GOOD defense",
  "exploit_mitigation_roadmap": [...],
  "strengths": [...],
  "gaps": [...]
}
```

**Acceptance:**
- ✅ File generated alongside orchestrator report
- ✅ Contains complete Red Team assessment
- ✅ Includes exploit difficulty scoring

---

#### Task 2: Human-Readable Improvement Summary (2h)
**Goal:** Generate markdown report for business/technical stakeholders

**New file:** `report/{arch}/08_improvement_summary.md`

**Structure:**
```markdown
# Architecture Improvement Plan: {architecture_name}

## Executive Summary
Your architecture scored **{composite}/100**
- Design Quality (Architect): {arch_score}/100
- MITRE Validation (Tester): {test_score}/100
- Exploit Difficulty (Red Team): {red_score}/100

## Improvement Paths

### Option 1: Quick Wins (1-2 weeks)
Target: {current} → {target} composite
Changes: 5-7 critical controls
ROI: High

### Option 2: Recommended Target ⭐ (1-3 months)
Target: {current} → {target} composite
Changes: Critical + High priority
ROI: Excellent

### Option 3: Maximum Security (6+ months)
Target: {current} → {target} composite
Changes: All recommendations
ROI: Diminishing returns

## Consensus Recommendations
Items all 3 agents agree on...
```

**Implementation:**
- New module: `chatbot/modules/improvement_summary_generator.py`
- Reads: `07_orchestrator_report.json`, `ground_truth.json`
- Template-based generation with dynamic data

---

#### Task 3: Stepped Improvement MMDs (3h)
**Goal:** Generate 3 visual architecture diagrams showing progression

**New files:**
- `08a_quick_wins.mmd` - CRITICAL only (red controls)
- `08b_recommended_target.mmd` - CRITICAL + HIGH (red + yellow) ⭐ RECOMMENDED
- `08c_maximum_security.mmd` - All controls (red + yellow + blue + green)

**Approach:**
1. Parse original MMD (nodes, edges, structure)
2. Apply roadmap filters (critical / critical+high / all)
3. Generate improved MMD with color-coded controls

**Example transformation:**
```mermaid
# Quick Wins (08a) - CRITICAL only
Internet --> WebServer --> Database
DLP[DLP]:::critical --> Database
MFA[MFA]:::critical --> WebServer

# Recommended (08b) - CRITICAL + HIGH
+ IDS[IDS/IPS]:::high --> WebServer
+ Segmentation[Network Segmentation]:::high --> Database

# Maximum (08c) - All controls
+ SIEM[SIEM]:::medium --> WebServer
+ Deception[Deception Tech]:::medium --> Internet
```

**Implementation:**
- New module: `chatbot/modules/mmd_improvement_generator.py`
- Reuse MMD parsing from existing code
- Apply control recommendations based on priority
- Generate 3 versions in one pass

---

#### Task 4: Integrate into Orchestrator (1h)
**Goal:** Auto-generate all new files when orchestrator runs

**Changes to `orchestrator.py`:**
```python
def orchestrate(self, report_dir: str, ...) -> OrchestratorResult:
    # ... existing orchestration ...
    
    # Save orchestrator result
    self.save_result(result, output_path)
    
    # NEW: Save Red Team critique separately
    self._save_red_team_critique(result, report_dir)
    
    # NEW: Generate improvement summary
    from chatbot.modules.improvement_summary_generator import generate_summary
    generate_summary(report_dir, result)
    
    # NEW: Generate stepped improvement MMDs
    from chatbot.modules.mmd_improvement_generator import generate_improvement_mmds
    generate_improvement_mmds(report_dir, result)
    
    return result
```

**Acceptance:**
- ✅ All new files generated automatically
- ✅ No additional user commands required
- ✅ Backward compatible (existing files unchanged)

---

#### Task 5: Update Demo Scripts (0.5h)
**Goal:** Show new outputs in demos

**Changes:**
1. `demo_orchestrator.sh` - show all 5 new files
2. `demo_llm_critique.sh` - reference improvement summary
3. `demo_step_by_step.sh` - add improvement generation step

---

### Output Files (Phase 2)

**Total per architecture:** 15 files (~240 KB)

```
report/{architecture_name}/
├── 01_executive_summary.md       ✅ Existing
├── 02_technical_report.md        ✅ Existing
├── 03_action_plan.md             ✅ Existing
├── 04_architect_critique.json    ✅ Existing
├── 05_tester_critique.json       ✅ Existing
├── 06_red_team_critique.json     🆕 Task 1
├── 07_orchestrator_report.json   ✅ Existing
├── 08_improvement_summary.md     🆕 Task 2
├── 08a_quick_wins.mmd            🆕 Task 3
├── 08b_recommended_target.mmd    🆕 Task 3 ⭐ RECOMMENDED
├── 08c_maximum_security.mmd      🆕 Task 3
├── before.mmd                    ✅ Existing
├── after.mmd                     ✅ Existing (with Phase 1 colors)
└── ground_truth.json             ✅ Existing
```

---

### Confidence Impact (Phase 2)

**Current:** 99.5% deterministic (Phase 3B++)  
**After Phase 2:** 99.5% deterministic + **85% LLM consensus** (composite)

**How it works:**
- Deterministic engine still runs (99.5% confidence)
- LLM agents critique and validate (85% composite)
- Orchestrator synthesizes consensus
- **Final output:** Both deterministic data + LLM-validated priorities

**Risk assessment:**
- ✅ Isolated new modules (no changes to core engine)
- ✅ Follows existing `agent_framework.py` patterns
- ⚠️ Complexity: Synthesizing 3 agent opinions
- ⚠️ New file generation (5 new files)

**Messiness:** Medium - adds ~500 lines across 3 new modules

---

### Implementation Order (Phase 2)

**Why this order:**
1. Task 1 (Red Team) - Quick win, unblocks Task 4
2. Task 3 (MMDs) - Core value delivery (visual diagrams)
3. Task 2 (Summary) - Depends on Task 3 for context
4. Task 4 (Integration) - Ties everything together
5. Task 5 (Demos) - Final polish

**Commit strategy:**
```
Commit 1: Task 1 - Red Team critique
Commit 2: Task 3 - MMD generation module
Commit 3: Task 2 - Improvement summary
Commit 4: Task 4 - Orchestrator integration
Commit 5: Task 5 - Demo updates + documentation
```

---

## Phase 3: MoE Architecture Refactor (Optional) 🔮 FUTURE

**Estimated Effort:** 8-12 hours  
**Timeline:** After Phase 2 validated (2-3 weeks production use)  
**Goal:** Clean mixture-of-experts architecture for maintainability

### Proposed Architecture

```
chatbot/modules/agents/
├── __init__.py
├── analyst/
│   ├── __init__.py
│   ├── base_analyst.py       # Deterministic base class
│   ├── rapids_analyst.py     # RAPIDS threat assessment
│   ├── mitre_analyst.py      # MITRE technique mapping
│   ├── atlas_analyst.py      # AI/ML threats (ATLAS)
│   └── arc_analyst.py        # AI/ML controls (ARC)
├── critic/
│   ├── __init__.py
│   ├── base_critic.py        # LLM base class
│   ├── architect_critic.py   # Design quality (82/100)
│   ├── tester_critic.py      # MITRE validation (88/100)
│   └── red_team_critic.py    # Exploit analysis (40/100 = hard to exploit)
└── orchestrator/
    ├── __init__.py
    ├── orchestrator.py       # Main coordinator
    ├── workflow_coordinator.py
    ├── priority_agent.py     # User's idea: Specialist prioritization
    └── consensus_builder.py
```

### Benefits
1. **Clear separation of concerns** - each agent class has one job
2. **Extensible** - easy to add new patterns (Finance, Healthcare)
3. **Testable** - each agent can be tested independently
4. **Maintainable** - changes to RAPIDS don't affect critics

### PriorityAgent Design
```python
class PriorityAgent:
    """Specialist for assigning and refining priorities."""
    
    def assign_priorities(
        self,
        analyst_results: Dict,  # Deterministic priorities
        critic_consensus: Dict   # LLM-validated priorities
    ) -> Dict[str, str]:
        """
        Synthesize final priorities from both sources.
        
        Logic:
        1. Start with deterministic priority (analyst_results)
        2. Check critic consensus for overrides
        3. Apply business rules (e.g., "no remote access → downgrade MFA")
        4. Return final priority mapping
        """
        pass
```

### Implementation Tasks

1. **Create folder structure** (1h)
   - Move existing files to new locations
   - Update imports across codebase

2. **Extract base classes** (2h)
   - `base_analyst.py` - common deterministic logic
   - `base_critic.py` - common LLM logic

3. **Refactor orchestrator** (3h)
   - Extract `WorkflowCoordinator`
   - Extract `PriorityAgent`
   - Extract `ConsensusBuilder`

4. **Update tests** (2h)
   - Test each agent independently
   - Test orchestrator integration

5. **Documentation** (2h)
   - Update ARCHITECTURE.md
   - Update CLAUDE.md
   - Add MoE pattern guide

**Total:** 10 hours

---

### When to Do Phase 3

**Wait until:**
- ✅ Phase 2 deployed to production
- ✅ 2-3 weeks of real-world usage
- ✅ Prioritization logic validated by users
- ✅ No major bugs in orchestrator

**Why wait:**
1. Validate the prioritization approach first
2. Let the design settle (avoid premature optimization)
3. Focus on value delivery (Phase 2) before refactoring

**When to proceed:**
- Users confirm priorities are accurate
- Team wants to add new agent types (Finance, Healthcare)
- Codebase maintainability becomes issue

---

## Success Criteria

### Phase 1 ✅ (Completed)
- ✅ Color-coded controls by priority
- ✅ Visual legend in after.mmd
- ✅ Zero confidence impact
- ✅ Tested on 3 architectures

### Phase 2 📋 (Next)
- ✅ 3-agent consensus working
- ✅ 15 files generated per architecture
- ✅ Stepped roadmaps (08a/08b/08c.mmd)
- ✅ Human-readable improvement summary
- ✅ Validated priorities from LLM critique

### Phase 3 🔮 (Optional)
- ✅ Clean MoE folder structure
- ✅ PriorityAgent as specialist
- ✅ Each agent testable independently
- ✅ Same output quality, better code

---

## Risk Assessment

| Phase | Risk Level | Mitigation |
|-------|------------|------------|
| Phase 1 | ✅ Zero | Only styling changes, no logic modification |
| Phase 2 | ⚠️ Low-Medium | Isolated modules, extensive testing on 22 architectures |
| Phase 3 | ⚠️ Medium | Wait for Phase 2 validation, incremental refactoring |

---

## Timeline Summary

```
Week 1 (Current):
├─ Phase 1 ✅ Complete (1h)
└─ Phase 2 Planning (this document)

Week 2-3:
├─ Task 1: Red Team critique (1h)
├─ Task 2: Improvement summary (2h)
├─ Task 3: Stepped MMDs (3h)
├─ Task 4: Integration (1h)
└─ Task 5: Demos (0.5h)
   Total: 7.5h → Phase 2 Complete

Week 4-6:
└─ Production validation (2-3 weeks)

Week 7+ (Optional):
└─ Phase 3: MoE refactor (8-12h)
```

---

## Documentation Updates

**After Phase 2:**
- [ ] Update STATUS_AND_PLAN.md (15 files section)
- [ ] Update CURRENT_OUTPUT.md (new files)
- [ ] Create HYBRID_IMPLEMENTATION.md (how it works)
- [ ] Update README.md (mention improvement diagrams)
- [ ] Add examples to report_samples/

**After Phase 3:**
- [ ] Update ARCHITECTURE.md (MoE pattern)
- [ ] Update CLAUDE.md (new folder structure)
- [ ] Create MOE_PATTERN_GUIDE.md
- [ ] Update all imports documentation

---

## References

**Phase 1:**
- [PRIORITY_COLOR_CODING.md](PRIORITY_COLOR_CODING.md) - Implementation details
- Commit: `0115008`

**Phase 2:**
- [../../phase3c/HYBRID_PLAN.md](../../phase3c/HYBRID_PLAN.md) - Original plan
- [../../phase3c/PHASE3C_OVERVIEW.md](../../phase3c/PHASE3C_OVERVIEW.md) - Context

**Phase 3:**
- [../../development/ARCHITECTURE.md](../../development/ARCHITECTURE.md) - Current architecture
- To be created: MOE_PATTERN_GUIDE.md

---

**Status:** Phase 1 ✅ Complete, Phase 2 📋 Ready to Start  
**Next Action:** Begin Task 1 (Red Team critique, 1h)  
**Author:** Phase 3B+/3C+ Team  
**Date:** 2026-05-17  
**Version:** 1.0
