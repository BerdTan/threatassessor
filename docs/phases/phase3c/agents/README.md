# Phase 3C: Agent-Specific Documentation

This folder contains documentation specific to individual critic agents.

---

## Agent Subdirectories

### architect/
Documentation for the Architect critic agent.
- Design quality assessment
- Threat modeling evaluation
- Defense-in-depth analysis

**Status:** ✅ Implemented (82/100 GOOD)

### tester/
Documentation for the Tester critic agent.
- MITRE validation
- Coverage analysis
- Consistency checks

**Status:** ✅ Implemented (88/100 GOOD)

**Key Doc:** [tester/TESTER_CONFIDENCE_GAPS.md](tester/TESTER_CONFIDENCE_GAPS.md)

### orchestrator/
Documentation for the Orchestrator and Red Teamer.
- Weighted scoring strategy
- Conflict resolution
- Red Teamer specifications

**Status:** ⏳ Planned (Phase 3C+)

**Key Doc:** [orchestrator/NEXT_STEPS_ANALYSIS.md](orchestrator/NEXT_STEPS_ANALYSIS.md)

---

## Cross-Agent Documentation

### [ARCHITECT_TO_TESTER_HANDOFF.md](ARCHITECT_TO_TESTER_HANDOFF.md)
How Architect and Tester communicate.
- Architect provides improvement roadmap
- Tester validates roadmap feasibility
- Handoff via architect_critique parameter

---

## Usage

Each agent subdirectory contains:
- Implementation notes
- Rubric details
- Testing strategies
- Performance analysis
- Known issues

Add agent-specific docs as they're created.
