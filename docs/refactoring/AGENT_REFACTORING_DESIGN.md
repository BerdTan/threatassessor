# Agent Architecture Refactoring Design

**Date:** 2026-05-17  
**Status:** ✅ APPROVED - Option D (Incremental)  
**Goal:** Unified agent architecture for scalability (swarms, new agents, new patterns)  
**Confidence:** 95% (validated against Phase 3C framework comparison)

---

## Background: Why Custom Framework?

**Phase 3C Decision (May 10, 2026):** Built custom agent framework after evaluating:
- LangGraph (heavy, 5MB deps)
- CrewAI (LangChain conflicts)
- AutoGen (too conversational)
- Phidata (lightweight alternative)

**Result:** Custom framework = 300 lines, zero deps, exact fit for rubric-based critique.

**See:** `docs/phases/phase3c/archived/PHASE3C_AGENT_FRAMEWORK_COMPARISON.md`

---

## Problem Statement

### Current State (Phase 3C+)

**Agents:**
- ✅ Architect: Uses `CriticAgent` base class
- ✅ Tester: Uses `CriticAgent` base class  
- ❌ Red Teamer: Standalone class (doesn't inherit from `CriticAgent`)
- ❌ Orchestrator: Hardcoded integration with 3 agents

**Issues:**
1. **Inconsistent inheritance:** RedTeamer reinvents wheel (custom prompt, LLM client, parsing)
2. **Hard to add agents:** Need to modify Orchestrator for each new agent
3. **No swarm support:** Can't dynamically compose agent teams
4. **Deterministic engine coupling:** Adding new MITRE patterns requires modifying multiple modules

---

## Design Goals

1. **Unified base class:** All agents inherit from common `BaseAgent`
2. **Pluggable agents:** Orchestrator discovers agents dynamically
3. **Swarm support:** Compose arbitrary agent teams (3, 4, 5+ agents)
4. **Extensible deterministic engine:** Plugin architecture for new MITRE patterns
5. **Backward compatible:** Existing agents/tests still work

---

## Proposed Architecture

### 1. Agent Hierarchy

```
BaseAgent (abstract)
├── CriticAgent (evaluates assessments)
│   ├── ArchitectCritic
│   ├── TesterCritic
│   └── RedTeamerCritic (REFACTOR to inherit)
├── AnalystAgent (new, generates assessments)
│   └── ThreatAnalyst (future, deterministic → LLM hybrid)
└── OrchestratorAgent (coordinates agents)
```

**BaseAgent (new abstract class):**
```python
class BaseAgent(ABC):
    """Abstract base for all agents."""
    
    def __init__(self, role: str, model: str = None):
        self.role = role
        self.model = model
        self.llm_client = LLMClient()
    
    @abstractmethod
    def execute(self, context: Dict) -> AgentResult:
        """Execute agent's primary task."""
        pass
    
    @abstractmethod
    def get_capabilities(self) -> List[str]:
        """Return what this agent can do (for dynamic discovery)."""
        pass
    
    def _parse_llm_response(self, response: Any) -> Dict:
        """Shared JSON parsing logic."""
        # Move from CriticAgent to BaseAgent
        pass
```

**CriticAgent (refactor to inherit from BaseAgent):**
```python
class CriticAgent(BaseAgent):
    """Agents that critique existing assessments."""
    
    def __init__(self, role: str, rubric: Dict, system_prompt: str, ...):
        super().__init__(role, model)
        self.rubric = rubric
        self.system_prompt = system_prompt
    
    def execute(self, context: Dict) -> CritiqueScore:
        """Implement BaseAgent.execute() for critique workflow."""
        return self.critique(context["ground_truth"])
    
    def get_capabilities(self) -> List[str]:
        return ["critique", "score", "identify_gaps"]
    
    def critique(self, ground_truth: Dict) -> CritiqueScore:
        # Existing logic
        pass
```

---

### 2. RedTeamer Refactoring

**Before (red_teamer_critic.py, 300+ lines):**
```python
class RedTeamerCritic:
    def __init__(self, model: str = None):
        self.role = "Red Teamer"
        self.model = model
        self.llm_client = LLMClient()  # Duplicate
        # Custom prompt, parsing, validation
```

**After (inherits from CriticAgent):**
```python
class RedTeamerCritic(CriticAgent):
    def __init__(self, model: str = None):
        super().__init__(
            role="Red Teamer",
            rubric=self._create_rubric(),
            system_prompt=self._create_system_prompt(),
            model=model
        )
    
    def critique(self, ground_truth: Dict) -> CritiqueScore:
        # Call parent critique() for LLM interaction
        raw_critique = super().critique(ground_truth)
        
        # Apply Red Team specific post-processing
        validated = self._post_process_validation(raw_critique, ground_truth)
        
        return validated
    
    def _post_process_validation(self, critique: CritiqueScore, gt: Dict) -> CritiqueScore:
        """4-check validation (existing logic)."""
        # Check 1: Control existence
        # Check 2: Difficulty reasonableness
        # Check 3: Tester gap integration
        # Check 4: Inverted scoring
        pass
```

**Benefits:**
- ✅ Removes 150+ lines of duplicate code (LLM client, parsing, validation)
- ✅ Consistent with Architect/Tester
- ✅ Keeps unique post-processing logic
- ✅ Easier to test (mock parent methods)

---

### 3. Orchestrator: Dynamic Agent Discovery

**Before (orchestrator.py):**
```python
class Orchestrator:
    def __init__(self, model: str = None):
        # Hardcoded 3 agents
        self.architect = EnhancedArchitectCritic(model=model)
        self.tester = TesterCritic(model=model)
        self.red_team = RedTeamerCritic(model=model)
    
    def orchestrate(self, report_dir: str) -> OrchestratorResult:
        # Run in fixed order
        arch_critique = self.architect.critique(ground_truth)
        test_critique = self.tester.critique(ground_truth, arch_critique)
        red_critique = self.red_team.critique(ground_truth, test_critique)
        # ...
```

**After (pluggable agents):**
```python
class Orchestrator(BaseAgent):
    def __init__(self, agents: List[BaseAgent], workflow: str = "sequential"):
        super().__init__(role="Orchestrator")
        self.agents = agents
        self.workflow = workflow  # "sequential", "parallel", "swarm"
    
    def execute(self, context: Dict) -> OrchestratorResult:
        if self.workflow == "sequential":
            return self._run_sequential(context)
        elif self.workflow == "parallel":
            return self._run_parallel(context)
        elif self.workflow == "swarm":
            return self._run_swarm(context)
    
    def _run_sequential(self, context: Dict) -> OrchestratorResult:
        """Existing Phase 3C+ workflow: Architect → Tester → Red Team."""
        results = []
        for agent in self.agents:
            # Pass previous results in context
            context["previous_results"] = results
            result = agent.execute(context)
            results.append(result)
        
        return self._aggregate_results(results)
    
    def _run_parallel(self, context: Dict) -> OrchestratorResult:
        """Run all agents in parallel (for independent critiques)."""
        # Future: Use threading/async
        pass
    
    def _run_swarm(self, context: Dict) -> OrchestratorResult:
        """Multi-round deliberation (agents can respond to each other)."""
        # Future: Phase 4
        pass
```

**Usage:**
```python
# Phase 3C+ (current, 3 agents)
orchestrator = Orchestrator(
    agents=[
        ArchitectCritic(),
        TesterCritic(),
        RedTeamerCritic()
    ],
    workflow="sequential"
)

# Phase 4 (future, 4+ agents with swarm)
orchestrator = Orchestrator(
    agents=[
        ArchitectCritic(),
        TesterCritic(),
        RedTeamerCritic(),
        ComplianceCritic(),  # New agent
        CloudSecurityCritic()  # New agent
    ],
    workflow="swarm"
)
```

---

### 4. Deterministic Engine: Plugin Architecture

**Problem:** Adding new MITRE patterns (e.g., Cloud, ICS, Mobile) requires modifying:
- `per_node_ttp_mapper.py`
- `exhaustive_mitigation_mapper.py`
- `threat_report.py`
- `completeness_validator.py`

**Solution: Pattern Registry**

```python
# chatbot/modules/pattern_registry.py (new)

class ThreatPattern(ABC):
    """Abstract base for threat patterns."""
    
    @abstractmethod
    def get_name(self) -> str:
        """Pattern name (e.g., 'RAPIDS', 'Cloud', 'ICS')."""
        pass
    
    @abstractmethod
    def assess_threat(self, node: str, context: Dict) -> Dict:
        """Assess threat for given node."""
        pass
    
    @abstractmethod
    def recommend_controls(self, threats: List[Dict]) -> List[Dict]:
        """Recommend controls for identified threats."""
        pass
    
    @abstractmethod
    def validate(self, ground_truth: Dict) -> ValidationResult:
        """Validate assessment completeness."""
        pass


class PatternRegistry:
    """Manages threat pattern plugins."""
    
    def __init__(self):
        self.patterns: Dict[str, ThreatPattern] = {}
    
    def register(self, pattern: ThreatPattern):
        """Register new threat pattern."""
        self.patterns[pattern.get_name()] = pattern
    
    def assess_all(self, node: str, context: Dict) -> Dict[str, Dict]:
        """Run all registered patterns."""
        results = {}
        for name, pattern in self.patterns.items():
            results[name] = pattern.assess_threat(node, context)
        return results


# Built-in patterns

class RAPIDSPattern(ThreatPattern):
    """Existing RAPIDS implementation."""
    
    def get_name(self) -> str:
        return "RAPIDS"
    
    def assess_threat(self, node: str, context: Dict) -> Dict:
        # Existing RAPIDS logic from ground_truth_generator.py
        pass


class CloudPattern(ThreatPattern):
    """Cloud-specific threats (S3 misconfig, IAM, etc.)."""
    
    def get_name(self) -> str:
        return "Cloud"
    
    def assess_threat(self, node: str, context: Dict) -> Dict:
        # New: Cloud-specific logic
        pass


class ICSPattern(ThreatPattern):
    """ICS/SCADA threats."""
    
    def get_name(self) -> str:
        return "ICS"
    
    def assess_threat(self, node: str, context: Dict) -> Dict:
        # New: ICS-specific logic
        pass
```

**Usage in ground_truth_generator.py:**
```python
# Initialize registry
registry = PatternRegistry()
registry.register(RAPIDSPattern())
registry.register(CloudPattern())  # Optional, auto-detected
registry.register(ICSPattern())    # Optional, auto-detected

# Assess with all patterns
for node in nodes:
    threat_assessment = registry.assess_all(node, context)
    # threat_assessment = {
    #     "RAPIDS": {...},
    #     "Cloud": {...},   # Only if Cloud pattern registered
    #     "ICS": {...}      # Only if ICS pattern registered
    # }
```

**Benefits:**
- ✅ Add new patterns without modifying core engine
- ✅ Optional patterns (load only if needed)
- ✅ Easy to test (mock individual patterns)
- ✅ Backward compatible (RAPIDS still default)

---

## Implementation Plan

### Phase 1: Foundation (4h)

**Task 1.1: Create BaseAgent (1h)**
- New file: `chatbot/modules/base_agent.py`
- Abstract class with `execute()`, `get_capabilities()`
- Move shared methods from CriticAgent (parsing, validation)

**Task 1.2: Refactor CriticAgent (1h)**
- Inherit from BaseAgent
- Keep critique-specific logic
- Update Architect/Tester to use new signature

**Task 1.3: Refactor RedTeamerCritic (1.5h)**
- Inherit from CriticAgent
- Remove duplicate code (LLM client, parsing)
- Keep post-processing logic
- Update tests

**Task 1.4: Update Orchestrator (0.5h)**
- Accept `List[BaseAgent]` instead of hardcoded agents
- Keep sequential workflow (for now)
- Backward compatible initialization

---

### Phase 2: Pattern Registry (3h)

**Task 2.1: Create PatternRegistry (1h)**
- New file: `chatbot/modules/pattern_registry.py`
- Abstract `ThreatPattern` class
- Registry with `register()`, `assess_all()`

**Task 2.2: Extract RAPIDS pattern (1.5h)**
- New file: `chatbot/modules/patterns/rapids_pattern.py`
- Move RAPIDS logic from `ground_truth_generator.py`
- Implement `ThreatPattern` interface

**Task 2.3: Integrate into engine (0.5h)**
- Update `ground_truth_generator.py` to use registry
- Backward compatible (RAPIDS auto-registered)

---

### Phase 3: Testing & Documentation (2h)

**Task 3.1: Update tests (1h)**
- Test BaseAgent hierarchy
- Test RedTeamer refactored inheritance
- Test backward compatibility

**Task 3.2: Documentation (1h)**
- Update ARCHITECTURE.md
- Document plugin pattern
- Add examples for new agents

---

## Success Criteria

**Functional:**
- ✅ All existing tests pass
- ✅ RedTeamer uses CriticAgent base
- ✅ Can add new agent without modifying Orchestrator
- ✅ Can add new pattern without modifying core engine
- ✅ Backward compatible (existing code works)

**Code Quality:**
- ✅ Reduced duplication (150+ lines removed)
- ✅ Clear inheritance hierarchy
- ✅ Easy to extend (new agent in <100 lines)
- ✅ Well-documented (docstrings + examples)

**Performance:**
- ✅ No performance degradation
- ✅ Same output as Phase 3C+ baseline

---

## Future Extensions (Out of Scope)

**Phase 4 (Swarm Intelligence, 8-10h):**
- Multi-round deliberation (agents respond to each other)
- Voting/consensus mechanism
- Dynamic agent composition based on architecture type

**Phase 5 (Cloud/ICS Patterns, 6-8h):**
- CloudPattern: S3, IAM, Lambda, API Gateway threats
- ICSPattern: SCADA, PLC, Modbus threats
- MobilePattern: iOS/Android app threats

**Phase 6 (LLM-Deterministic Hybrid, 10-12h):**
- ThreatAnalyst agent (generates assessments using LLM)
- Hybrid mode: Deterministic base + LLM enhancement
- Confidence blending (99.5% deterministic + 85% LLM)

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Breaking existing agents | Medium | High | Extensive tests, backward compatibility checks |
| Performance degradation | Low | Medium | Benchmark before/after |
| Over-engineering | Medium | Low | Start with minimal viable refactoring |
| RedTeamer behavior changes | Medium | High | Validate output identical to Phase 3C+ baseline |

---

## Migration Path

**Step 1: Baseline validation**
```bash
# Run before refactoring
python3 scripts/agent_testing/run_full_critique.py report/02_minimal_defended
# Save output for comparison
```

**Step 2: Implement Phase 1 (BaseAgent + CriticAgent refactor)**
```bash
# Test after each task
python3 -m pytest tests/test_agents.py -v
```

**Step 3: Refactor RedTeamer**
```bash
# Compare output to baseline
python3 scripts/agent_testing/run_full_critique.py report/02_minimal_defended
diff report/02_minimal_defended/06_red_team_critique.json baseline/
```

**Step 4: Implement Phase 2 (PatternRegistry)**
```bash
# Validate deterministic output unchanged
python3 -m chatbot.main --gen-arch-truth tests/data/architectures/02_minimal_defended.mmd
diff report/02_minimal_defended/ground_truth.json baseline/
```

---

## Decision Required

**Options:**

**A. Full refactoring (7-9h total)**
- Implement all 3 phases
- Future-proof for swarms + new patterns
- Risk: Larger change surface

**B. Agent refactoring only (4h)**
- Phase 1 only (BaseAgent + RedTeamer)
- Defer pattern registry to later
- Risk: Half-solution, need another refactor later

**C. Pattern registry only (3h)**
- Phase 2 only (keep agent architecture as-is)
- Defer agent unification to later
- Risk: RedTeamer still inconsistent

**D. Incremental (Phase 1 now, Phase 2 after Task 3)**
- Do agent refactoring first
- Validate with Task 3 (MMD generation)
- Add pattern registry in Phase 4
- Risk: Two separate refactorings

**Recommendation: Option D (Incremental)**
- Lower risk (smaller changes)
- Validate with immediate task (Task 3)
- Natural breakpoint between agent + pattern concerns

---

**Status:** ✅ APPROVED - Option D  
**Author:** Phase 3C+ Team  
**Date:** 2026-05-17  
**Approved By:** User (2026-05-17)  
**Next:** Implement Phase 1 (BaseAgent + RedTeamer refactor, 4h)
