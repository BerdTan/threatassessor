# Phase 3C: LLM as Judge/Critic (Sequential A-Team)

**Start Date:** May 10, 2026 (MVP1)  
**Current Date:** May 15, 2026  
**Status:** 🚀 **IN PROGRESS** (MVP1 Complete, 13h Remaining)  
**Parent:** [../README.md](../README.md)

---

## Quick Start

**📍 Start Here:** [PHASE3C_IMPLEMENTATION_PLAN.md](PHASE3C_IMPLEMENTATION_PLAN.md)

**Current Status:** MVP1 Architect agent complete (4h), ready for Phase 1: Artifact Extractor (2h)

---

## What Phase 3C Will Achieve

### Goal
Use LLM agents to **critique** the deterministic engine (Phase 3B+ baseline), identify blind spots, and suggest architecture improvements.

### Approach
**Sequential A-Team:** Architect → Tester → Red Team (not parallel)

**Why Sequential?** See [PHASE3C_APPROACH_ANALYSIS.md](PHASE3C_APPROACH_ANALYSIS.md)
- Context accumulation (Tester validates Architect's roadmap)
- 70% code reuse (MVP1 Architect + framework done)
- Simpler debugging (linear execution)
- Narrative quality (design → test → attack)

### Artifacts Used
**10 Total:** 5 critical (ground_truth.json) + 5 important (report files)

See [PHASE3C_ARTIFACT_STRUCTURE.md](PHASE3C_ARTIFACT_STRUCTURE.md) for full spec.

---

## Phase 3C Documents (Active)

### Navigation & Planning

#### PHASE3C_MASTER_INDEX.md (12K)
**Purpose:** Documentation navigation hub

Quick reference for "what to read when" - use this to find the right document.

---

#### PHASE3C_IMPLEMENTATION_PLAN.md (27K) ⭐
**Purpose:** Single source of truth - MASTER PLAN

**Key Content:**
- Executive summary (sequential, 10 artifacts, 13h remaining)
- Architecture overview (flow diagram)
- 7 implementation phases with detailed tasks
- Code structure and timeline
- Success criteria and risk mitigation

**Start reading here for implementation guidance.**

---

### Reference Specifications

#### PHASE3C_ARTIFACT_STRUCTURE.md (22K)
**Purpose:** Define all 10 artifacts agents will use

**Tier 1: Critical (80% confidence)**
1. Attack Paths (expected_attack_paths)
2. Control Recommendations (control_recommendations)
3. Residual Risk (residual_risks)
4. Validation Results (validation_report)
5. RAPIDS Assessment (rapids_assessment)

**Tier 2: Important (22% confidence)**
6. before.mmd (original architecture)
7. after.mmd (architecture + controls)
8. 02_technical_report.md
9. 01_executive_summary.md
10. 03_action_plan.md

**Use When:** Implementing artifact extractor, agent prompts

---

#### PHASE3C_APPROACH_ANALYSIS.md (28K)
**Purpose:** Sequential vs Parallel comparison + decision

**Key Content:**
- Decision matrix (Sequential vs Parallel vs Hybrid)
- **Recommendation: Sequential (Option A)**
- Rationale: Context accumulation, 70% code done, simpler debugging
- 5-artifact structure from ground_truth.json (now 10 with Tier 2)
- Implementation timeline

**Use When:** Understanding why sequential approach was chosen

---

### MVP1 - Architect Agent (COMPLETE)

#### PHASE3C_MVP1_SUMMARY.md (10K)
**Purpose:** MVP1 completion summary (what was built)

**Achievements:**
- Architect agent built (370 lines, tested on 3 architectures)
- Agent framework created (502 lines, reusable)
- Test data: test_flawed_assessment.json (3 planted errors)
- Scores: Good=78/100, Flawed=23/100 ✅
- improvement_roadmap with verification_method for Tester

**Use When:** Understanding what MVP1 delivered

---

#### PHASE3C_MVP1_CHECKLIST.md (9K)
**Purpose:** MVP1 completion checklist (all items checked)

All 9/9 success criteria met.

---

#### PHASE3C_MVP1_CONFIDENCE_ANALYSIS.md (8K)
**Purpose:** Answers 5 critical questions about MVP1 reliability

**Questions Answered:**
1. What input is sent to LLM? → Deterministic findings verified
2. How to validate score accuracy? → Evidence-based scoring
3. Useful for Tester? → Yes, verification_method field
4. Overshoot >100 illogical? → Fixed with normalization
5. MITRE quality vs quantity? → Quality emphasized

**Use When:** Understanding MVP1 validation and design decisions

---

### MVP2 - Tester Agent (READY TO BUILD)

#### PHASE3C_MVP2_TESTER_SPEC.md (8K)
**Purpose:** Tester agent specification (next to implement)

**Key Content:**
- Tester rubric (40+30+20+10 = 100 points)
- Primary focus: Artifact 4 (validation_report)
- Uses Architect's improvement_roadmap
- Executes verification_method checks
- Cross-references Architect findings

**Use When:** Implementing Tester agent (Phase 3 of plan)

---

## Archived Documents (Design Explorations)

### archived/ subfolder (5 files, 180K)

Design documents that led to current decisions. See [archived/README.md](archived/README.md).

**Quick Reference:**
- **PHASE3C_OVERVIEW.md** - Original vision (pre-MVP1)
- **PHASE3C_LLM_CRITIC_UPDATED.md** - Early design exploration
- **PHASE3C_AGENT_FRAMEWORK_COMPARISON.md** - Framework decision
- **PHASE3C_TEAM_ARCHITECTURE.md** - Parallel design (not chosen)
- **PHASE3C_NEXT_STEPS.md** - Early enhancement plan

**When to reference:** See archived/README.md for guidance

---

## Progress Tracker

| Phase | Component | Hours | Status | Notes |
|-------|-----------|-------|--------|-------|
| 0 | MVP1: Architect | 4 | ✅ COMPLETE | Tested on 3 architectures |
| 1 | Artifact Extractor | 2 | 🚀 NEXT | Extract 10 artifacts |
| 2 | Enhanced Architect | 2.5 | Pending | Use all 10 artifacts |
| 3 | Tester Agent | 2 | Pending | Spec ready (MVP2) |
| 4 | Red Team Agent | 3 | Pending | Adversarial testing |
| 5 | Sequential Orchestrator | 1 | Pending | Chain agents |
| 6 | CLI Integration | 1 | Pending | --gen-arch-truth-team |
| 7 | Testing & Validation | 1.5 | Pending | Test on 3 archs |
| **Total** | **17 hours** | **25%** | **(4 done + 13 remaining)** |

---

## File Structure

```
phase3c/
├── README.md (this file)                       - Phase overview
├── PHASE3C_MASTER_INDEX.md                     - Navigation hub
├── PHASE3C_IMPLEMENTATION_PLAN.md              - ⭐ MASTER PLAN
├── PHASE3C_ARTIFACT_STRUCTURE.md               - 10 artifacts
├── PHASE3C_APPROACH_ANALYSIS.md                - Why sequential
├── PHASE3C_MVP1_SUMMARY.md                     - Architect complete
├── PHASE3C_MVP1_CHECKLIST.md                   - Completion
├── PHASE3C_MVP1_CONFIDENCE_ANALYSIS.md         - Validation
├── PHASE3C_MVP2_TESTER_SPEC.md                 - Tester spec
│
└── archived/                                   - Design explorations
    ├── README.md                               - Archive guide
    └── 5 archived documents                    - Reference only
```

---

## Quick Reference

### I want to start implementing...
**Read:** [PHASE3C_IMPLEMENTATION_PLAN.md](PHASE3C_IMPLEMENTATION_PLAN.md)

### I want to understand the 10 artifacts...
**Read:** [PHASE3C_ARTIFACT_STRUCTURE.md](PHASE3C_ARTIFACT_STRUCTURE.md)

### I want to know why sequential...
**Read:** [PHASE3C_APPROACH_ANALYSIS.md](PHASE3C_APPROACH_ANALYSIS.md)

### I want to see what MVP1 did...
**Read:** [PHASE3C_MVP1_SUMMARY.md](PHASE3C_MVP1_SUMMARY.md)

### I want to build the Tester agent...
**Read:** [PHASE3C_MVP2_TESTER_SPEC.md](PHASE3C_MVP2_TESTER_SPEC.md)

### I want historical context...
**Read:** [archived/README.md](archived/README.md)

---

## Next Steps

**Current:** Phase 1 - Artifact Extractor (2h)
1. Create `chatbot/modules/artifact_extractor.py`
2. Extract 10 artifacts from report directory
3. Build indexes for efficient agent queries
4. Test on 02_minimal_defended

**Then:** Phase 2 - Enhanced Architect (2.5h)
**Then:** Phase 3 - Tester Agent (2h)

---

**Phase Started:** May 10, 2026  
**Phase Status:** In Progress (25% complete)  
**Documents:** 8 active + 5 archived  
**Next Milestone:** Artifact Extractor (Phase 1)
