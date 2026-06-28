# Agent Types Reference

**Date:** 2026-05-17  
**Purpose:** Guide for when to use each agent type

---

## Agent Hierarchy

```
BaseAgent (abstract)
├── AnalystAgent - Generates threat assessments
├── CriticAgent - Evaluates assessment quality
└── Orchestrator - Coordinates multi-agent workflows
```

---

## 1. AnalystAgent - "What threats exist?"

**Purpose:** Generate threat assessments from architecture diagrams

**Implementations:**
- `ThreatAnalyst` - Deterministic analysis (99.5% confidence)
- `HybridThreatAnalyst` (future) - Deterministic + LLM enhancement

**When to use:**
- Analyzing new architecture diagrams
- Re-analyzing after architecture changes
- Generating ground truth for critic agents

**Input:** Architecture diagram (.mmd file)  
**Output:** `AnalysisResult` with threats, techniques, controls, risk scores

**Example:**
```python
from chatbot.modules.threat_analyst import ThreatAnalyst

analyst = ThreatAnalyst()
assessment = analyst.execute({
    "architecture_path": "tests/data/architectures/02_minimal_defended.mmd"
})

print(f"Threats: {len(assessment.threats)}")
print(f"Techniques: {len(assessment.techniques)}")
print(f"Controls recommended: {len(assessment.control_recommendations)}")
print(f"Confidence: {assessment.confidence:.1%}")
```

**Capabilities:**
- `generate_assessment` - Create threat assessment
- `identify_threats` - RAPIDS threat categorization
- `map_techniques` - MITRE technique mapping
- `recommend_controls` - Security control recommendations
- `calculate_risk` - Residual risk (before/after)

---

## 2. CriticAgent - "Is the analysis good?"

**Purpose:** Evaluate quality of threat assessments

**Implementations:**
- `ArchitectCritic` - Design quality assessment (82/100 avg)
- `TesterCritic` - Validation quality (88/100 avg)
- `RedTeamerCritic` - Exploit difficulty (inverted scoring)

**When to use:**
- Quality assurance on threat assessments
- Getting second opinion on analysis
- Finding gaps in coverage

**Input:** Artifacts (ground truth, reports, diagrams)  
**Output:** `CritiqueScore` with score, gaps, strengths, roadmap

**Example:**
```python
from chatbot.modules.architect_critic import EnhancedArchitectCritic
from chatbot.modules.artifact_extractor import extract_artifacts

architect = EnhancedArchitectCritic()
artifacts = extract_artifacts("report/02_minimal_defended")

critique = architect.critique(artifacts)

print(f"Score: {critique.score}/100 ({critique.rating})")
print(f"Gaps: {len(critique.gaps)}")
print(f"Strengths: {len(critique.strengths)}")
```

**Capabilities:**
- `critique` - Evaluate assessment quality
- `score` - Quantitative scoring (0-100)
- `identify_gaps` - Find missing coverage
- `recommend_improvements` - How to increase score

**Scoring:**
- **Architect:** Design quality (threat completeness, control appropriateness, defense-in-depth)
- **Tester:** Validation quality (MITRE correctness, coverage metrics, consistency)
- **Red Team:** Exploit difficulty (INVERTED - low score = hard to exploit = good)

---

## 3. Orchestrator - "Coordinate the workflow"

**Purpose:** Manage multi-agent analysis workflows

**Implementation:**
- `Orchestrator` - Sequential 3-agent workflow (Architect → Tester → Red Team)

**When to use:**
- Running full LLM critique pipeline
- Aggregating scores from multiple critics
- Generating unified improvement roadmaps

**Input:** Report directory (with ground truth + artifacts)  
**Output:** `OrchestratorResult` with composite scores, confidence, unified roadmap

**Example:**
```python
from chatbot.modules.orchestrator import Orchestrator

orchestrator = Orchestrator()  # Creates default 3 agents

result = orchestrator.orchestrate(
    report_dir="report/02_minimal_defended",
    deterministic_confidence=99.5
)

print(f"Composite: {result.composite_score}/100 ({result.composite_rating})")
print(f"Final confidence: {result.final_confidence:.1f}%")
print(f"Agent agreement: {result.agent_agreement}")
```

**Pluggable mode:**
```python
# Custom agents
custom_architect = CustomArchitectCritic()
custom_tester = CustomTesterCritic()
custom_red_team = CustomRedTeamerCritic()

orchestrator = Orchestrator(agents=[custom_architect, custom_tester, custom_red_team])
```

**Capabilities:**
- `orchestrate` - Run full workflow
- `coordinate_agents` - Sequential agent execution
- `aggregate_scores` - Weighted composite scoring
- `calculate_confidence` - Multi-layer confidence model
- `synthesize_roadmap` - Unified improvement recommendations

**Scoring formula:**
- Architect: 30%
- Tester: 30%
- Red Team (defense, inverted): 40%

---

## Workflow Patterns

### Pattern 1: Full Analysis (Deterministic + Critique)

```python
# Step 1: Generate threat assessment (AnalystAgent)
analyst = ThreatAnalyst()
assessment = analyst.execute({"architecture_path": arch_path})

# Step 2: Critique assessment quality (CriticAgents via Orchestrator)
orchestrator = Orchestrator()
critique = orchestrator.orchestrate(report_dir)

# Result: Deterministic assessment (99.5%) + LLM critique (85%)
```

### Pattern 2: Quick Threat Analysis Only

```python
# Just deterministic analysis, no critique
analyst = ThreatAnalyst()
assessment = analyst.execute({"architecture_path": arch_path})

# Use assessment.data for ground truth
ground_truth = assessment.data
```

### Pattern 3: Critique Existing Analysis

```python
# Assume ground truth already generated in report_dir
orchestrator = Orchestrator()
result = orchestrator.orchestrate(report_dir)

# Get unified recommendations
print(result.unified_roadmap)
print(result.recommended_target)
```

### Pattern 4: Custom Agent Workflow

```python
# Create custom agents
my_analyst = CustomThreatAnalyst()
my_architect = CustomArchitectCritic()
my_tester = CustomTesterCritic()

# Run custom workflow
assessment = my_analyst.execute(context)
architect_critique = my_architect.critique(assessment)
tester_critique = my_tester.critique(assessment, architect_critique)

# Aggregate manually or use orchestrator
```

---

## Future Enhancements

### Phase 2: Pattern Registry
```python
# Multi-pattern analysis
analyst = ThreatAnalyst()
analyst.set_pattern_registry(PatternRegistry([
    RAPIDSPattern(),
    CloudPattern(),
    ICSPattern(),
    MobilePattern()
]))

assessment = analyst.execute(context)
# assessment.pattern_sources = ["RAPIDS", "Cloud", "ICS", "Mobile"]
```

### Phase 6: Hybrid LLM + Deterministic
```python
# LLM-enhanced analysis
analyst = HybridThreatAnalyst()
assessment = analyst.execute(context)

# Blends:
# - Deterministic (99.5% confidence)
# - LLM insights (85% confidence)
# - Final: Weighted composite
```

---

## Summary: When to Use Which Agent

| Task | Agent Type | Implementation | Output |
|------|------------|----------------|--------|
| Analyze new architecture | AnalystAgent | ThreatAnalyst | Threat assessment |
| Evaluate analysis quality | CriticAgent | Architect/Tester/RedTeam | Quality scores |
| Run full workflow | Orchestrator | Orchestrator | Unified assessment |
| Custom multi-agent | BaseAgent | Your implementation | Custom result |

---

**See also:**
- `AGENT_REFACTORING_DESIGN.md` - Design rationale
- `AGENT_REFACTORING_SUMMARY.md` - Implementation details
- `chatbot/modules/base_agent.py` - Abstract base class
- `chatbot/modules/analyst_agent.py` - AnalystAgent abstract
- `chatbot/modules/agent_framework.py` - CriticAgent class
