# Phase 3C: Balanced LLM-Centric Approach

**Date:** 2026-05-16  
**Problem:** Current approach (75%) over-relies on deterministic code, underutilizes LLM reasoning  
**Solution:** Use LLM as primary judge, MITRE validator as tool  
**Target Confidence:** 85-90% (vs 75% now, 93% fully deterministic)

---

## The Core Issue

### Current Approach (Phase 2 Complete)
```
Tester Agent = Hard-coded MITRE validation + Some LLM scoring
                ↓
              75% confidence
```

**Problems:**
1. ❌ Over-engineered deterministic logic (460 lines of validation code)
2. ❌ LLM only scores, doesn't reason about security
3. ❌ Can't catch nuanced issues (e.g., "MFA without rate limiting is weak")
4. ❌ Not aligned with "LLM as Judge" philosophy
5. ❌ 75% too low for security testing

### Phase 3C Original Intent
```
"LLM as Judge/Critic" - Let the LLM reason about security quality
```

**The right balance:**
- LLM should be the **brain** (reasoning, judgment, context)
- Tools should be **eyes** (MITRE data, embeddings, verification)

---

## Balanced Approach: LLM-Centric with Tools

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ TESTER AGENT (LLM as Judge)                                 │
│                                                              │
│  System Prompt:                                              │
│  "You are a Security Tester validating threat assessments.  │
│   Use MITRE tools to verify technical claims.               │
│   Reason about security effectiveness contextually."         │
│                                                              │
│  Available Tools:                                            │
│  1. validate_mitre_mapping(control, techniques)              │
│  2. score_control_effectiveness(control, attack_paths)       │
│  3. search_similar_techniques(description)                   │
│  4. execute_verification(verification_method, ground_truth)  │
│                                                              │
│  LLM decides:                                                │
│  - WHEN to call tools (not always needed)                    │
│  - HOW to interpret results (context-aware)                  │
│  - WHAT qualitative issues exist (beyond tool checks)        │
└─────────────────────────────────────────────────────────────┘
```

### Key Insight

**Instead of:**
```python
# Deterministic (Phase 2 approach)
def validate_control(control):
    validator = MitreValidator()
    results = validator.validate_control_techniques(control)
    if results:
        return "INVALID"
    return "VALID"
```

**Do this:**
```python
# LLM-centric (Phase 3C approach)
tester_agent.critique(ground_truth, architect_critique)

# LLM decides: "I'll validate MFA's MITRE mappings"
# LLM calls tool: validate_mitre_mapping("MFA", ["T1078", "T1110"])
# Tool returns: {"valid": true, "coverage": 0.6}
# LLM reasons: "MFA is valid but 60% coverage is insufficient for critical path"
# LLM outputs: "HIGH severity: MFA coverage too low for critical authentication path"
```

---

## What Changes

### 1. MITRE Validator Becomes a Tool (Not Core Logic)

**Before (Phase 2):**
```python
class TesterCritic:
    def __init__(self):
        self.validator = MitreValidator()  # Hard-coded dependency
        
    def critique(self, ground_truth):
        # Deterministic validation
        validation = self.validator.validate_all_controls(controls)
        if validation["invalid_controls"] > 0:
            score -= 5  # Fixed penalty
```

**After (Balanced):**
```python
# Tool definition
validate_mitre_tool = AgentTool(
    name="validate_mitre_mapping",
    description="Validate if control's mitigations actually address claimed techniques per MITRE ATT&CK",
    function=lambda control_name, techniques: {
        "valid": check_mitre_validity(control_name, techniques),
        "coverage": calculate_coverage(control_name, techniques),
        "gaps": find_unmitigated_techniques(control_name, techniques)
    },
    parameters={
        "type": "object",
        "properties": {
            "control_name": {"type": "string"},
            "techniques": {"type": "array", "items": {"type": "string"}}
        }
    }
)

tester_agent = CriticAgent(
    role="Security Tester",
    system_prompt=TESTER_SYSTEM_PROMPT,
    tools=[validate_mitre_tool, score_effectiveness_tool, ...]  # LLM decides when to use
)
```

**Why better:**
- LLM decides WHICH controls need validation (not blindly validate all 17)
- LLM interprets results contextually (60% coverage = bad for MFA, OK for logging)
- LLM can catch issues tools can't (e.g., "No rate limiting before MFA = brute force risk")

---

### 2. Add LLM Reasoning for Verification Execution

**The Hard Way (Phase 3 original plan):**
```python
class VerificationParser:
    """460 lines of regex patterns to parse verification_method strings"""
    
    def parse_verification(self, vm):
        # Regex hell for: "Count techniques targeting Database - should have 3+ T12xx"
        if match := re.search(r'count\s+(\w+).*?(\d+)\+?\s*([A-Z]\d+)', vm):
            return {"type": "count", "min": int(match.group(2)), ...}
        # 50 more patterns...
```

**The LLM Way (Balanced):**
```python
# Tool: Execute verification check
execute_verification_tool = AgentTool(
    name="execute_verification",
    description="Execute a verification check from Architect's roadmap against ground truth",
    function=execute_verification_with_llm,  # LLM parses the string!
    parameters={
        "verification_method": {"type": "string"},  # "Count techniques targeting Database..."
        "ground_truth": {"type": "object"}
    }
)

def execute_verification_with_llm(verification_method: str, ground_truth: Dict) -> Dict:
    """Let LLM parse and execute the verification."""
    
    prompt = f"""Parse this verification method and extract the testable assertion:

"{verification_method}"

Extract:
1. What to check (e.g., "technique count", "control priority")
2. Target (e.g., "Database node", "high-risk controls")
3. Expected value (e.g., "3+", "priority=critical")
4. Pattern (e.g., "T12xx", "risk>=80")

Then execute the check against this ground truth data and return pass/fail.

Ground truth (relevant sections):
- Attack paths: {len(ground_truth['expected_attack_paths'])} paths
- Controls: {len(ground_truth['control_recommendations'])} controls
- RAPIDS: {list(ground_truth['rapids_assessment'].keys())}

Return JSON:
{{
  "parsed": {{"type": "...", "target": "...", "expected": "..."}},
  "actual_value": "...",
  "passed": true/false,
  "details": "..."
}}
"""
    
    # LLM parses AND executes (no regex needed!)
    result = llm_client.generate(prompt, response_format="json")
    return result
```

**Why better:**
- No regex parsing (LLM understands natural language)
- Handles variations ("3+" vs "at least 3" vs "minimum of three")
- Can reason about complex checks ("controls for high-risk threats should be critical priority")
- Self-documenting (LLM explains what it checked)

---

### 3. Semantic Gap Detection (LLM's Superpower)

**What deterministic code can't catch:**

```python
# Ground truth has:
controls = ["MFA", "WAF", "Firewall"]
rapids_assessment = {
    "phishing": {"risk": 90, "rationale": "No user training, high click rate"}
}

# Deterministic validator says: ✅ All controls have valid MITRE mappings
# LLM says: ❌ "High phishing risk (90) but no user training control - MFA alone insufficient"
```

**How LLM catches this:**
```
LLM System Prompt:
"Beyond MITRE validation, reason about:
1. Defense-in-depth: Are controls complementary or redundant?
2. RAPIDS alignment: Do high-risk threats have multiple controls?
3. Control ordering: Is there a weak link (e.g., MFA without rate limiting)?
4. Architecture fit: Are controls appropriate for this system type?"

LLM calls validate_mitre_mapping("MFA", ["T1078"]) → valid=true
LLM reads rapids_assessment["phishing"] → risk=90
LLM reasons: "MFA is valid but insufficient - phishing needs user training + email filtering"
LLM outputs: {
    "severity": "HIGH",
    "description": "Phishing risk=90 but only MFA control present. Need user training.",
    "recommendation": "Add M1017 (User Training) as complementary control",
    "llm_reasoning": "MFA stops credential reuse but doesn't prevent initial compromise"
}
```

---

## Proposed Tool Suite for Tester Agent

### Core Tools (4 essential)

#### 1. validate_mitre_mapping
```python
{
  "name": "validate_mitre_mapping",
  "description": "Check if control's MITRE mitigations actually address claimed techniques",
  "function": mitre_validator.validate_control_techniques,
  "use_when": "Validating Architect's control→technique claims"
}
```

#### 2. score_control_effectiveness  
```python
{
  "name": "score_control_effectiveness",
  "description": "Calculate technique coverage and weighted effectiveness for a control",
  "function": effectiveness_scorer.score_control_effectiveness,
  "use_when": "Checking if effectiveness claims are realistic"
}
```

#### 3. search_techniques_semantic
```python
{
  "name": "search_techniques_semantic",
  "description": "Find MITRE techniques matching a description using embeddings",
  "function": mitre_embeddings.search_techniques,
  "use_when": "Architect mentions threats without technique IDs"
}
```

#### 4. execute_verification_check
```python
{
  "name": "execute_verification_check",
  "description": "Parse and execute verification_method from Architect roadmap",
  "function": execute_verification_with_llm,  # LLM-assisted parsing
  "use_when": "Validating Architect's improvement roadmap items"
}
```

### Optional Tools (nice-to-have)

#### 5. compare_architectures
```python
{
  "name": "compare_architectures",
  "description": "Find similar architectures in test data for baseline comparison",
  "function": find_similar_architectures,
  "use_when": "Checking if assessment quality matches similar systems"
}
```

#### 6. explain_technique
```python
{
  "name": "explain_technique",
  "description": "Get detailed MITRE technique info (description, mitigations, examples)",
  "function": mitre.get_technique_summary,
  "use_when": "Need context on unfamiliar technique"
}
```

---

## Updated Tester System Prompt

```
You are a Security Tester validating threat assessment quality.

Your role: Verify that Architect's recommendations are:
1. Technically correct (valid MITRE mappings)
2. Contextually appropriate (fit the architecture)
3. Realistically effective (can actually mitigate the threats)
4. Complete (no critical gaps)

SCORING RUBRIC (100 points):

A. VALIDATION CHECKS (40 points)
   - Ground truth validation passed (10 pts)
   - MITRE mappings valid (10 pts) ← USE validate_mitre_mapping TOOL
   - Risk score consistency (10 pts)
   - Technique coverage adequate (10 pts) ← USE score_control_effectiveness TOOL

B. COVERAGE METRICS (30 points)
   - RAPIDS completeness (6/6 categories) (10 pts)
   - Technique-to-risk ratio appropriate (10 pts)
   - Control-to-threat coverage sufficient (10 pts) ← USE score_control_effectiveness TOOL

C. INTERNAL CONSISTENCY (20 points)
   - Control rationales match inventory (10 pts)
   - Priorities aligned to risk scores (10 pts)

D. ARCHITECT ROADMAP VALIDATION (10 points)
   - Roadmap items address real gaps (5 pts) ← USE execute_verification_check TOOL
   - Improvement claims are realistic (5 pts)

AVAILABLE TOOLS:
- validate_mitre_mapping: Check technique→mitigation validity
- score_control_effectiveness: Calculate actual coverage
- search_techniques_semantic: Find techniques by description
- execute_verification_check: Validate roadmap verification methods

CRITICAL INSTRUCTIONS:
1. Use tools SELECTIVELY (not every control needs validation)
2. Reason CONTEXTUALLY (60% coverage = bad for MFA, OK for logging)
3. Catch SEMANTIC GAPS (e.g., "High phishing risk but no user training")
4. Validate QUALITATIVELY (beyond what tools report)

OUTPUT FORMAT: JSON with score, breakdown, gaps, and improvement_roadmap

Focus on: Are the security claims REALISTIC and TESTABLE?
```

---

## Confidence Analysis: LLM-Centric Approach

### Deterministic Approach (Current Path)
| Component | Confidence | Notes |
|-----------|------------|-------|
| MITRE validation (hard-coded) | 95% | ✅ Accurate but rigid |
| Effectiveness scoring (formula) | 85% | ⚠️ Heuristic weights |
| Verification parsing (regex) | 70% | ❌ Brittle, limited patterns |
| Semantic gaps | 30% | ❌ Can't catch "MFA without training" issues |
| **Overall** | **75%** | ❌ Too low for security testing |

### LLM-Centric Approach (Balanced)
| Component | Confidence | Notes |
|-----------|------------|-------|
| MITRE validation (LLM + tool) | 90% | ✅ LLM decides when/how to validate |
| Effectiveness scoring (LLM + tool) | 85% | ✅ LLM interprets context |
| Verification execution (LLM parsing) | 85% | ✅ Handles natural language |
| Semantic gaps (LLM reasoning) | 80% | ✅ Catches nuanced issues |
| **Overall** | **85%** | ✅ Good enough for security testing |

**Key Difference:** LLM reasoning bridges the gaps that deterministic code misses

---

## Implementation Plan: Balanced Approach

### Phase 2.5: Convert Validator to Tools (2 hours)
**Goal:** Make MITRE validator accessible to LLM as tools

**Tasks:**
1. Wrap `MitreValidator.validate_control_techniques` as AgentTool (30 min)
2. Wrap `EffectivenessScorer.score_control_effectiveness` as AgentTool (30 min)
3. Add `search_techniques_semantic` tool (embeddings) (30 min)
4. Test tool calling in isolation (30 min)

**Deliverable:** 3 working tools that Tester agent can call

---

### Phase 3: Enhanced Tester Agent (4 hours)
**Goal:** Build Tester agent with LLM reasoning + tools

**Tasks:**
1. Create `tester_critic.py` with enhanced system prompt (1 hour)
   - 100-point rubric
   - Tool usage guidelines
   - Semantic gap detection instructions

2. Implement `execute_verification_check` tool (1.5 hours)
   - LLM-assisted parsing of verification_method
   - Execute check against ground truth
   - Return pass/fail + details

3. Integration with artifact extractor (1 hour)
   - Load 10 artifacts
   - Pass to Tester agent
   - Handle tool calls

4. Testing (30 min)
   - Run on report_samples/example_architecture
   - Verify tool calls work
   - Check output quality

**Deliverable:** Working Tester agent with 85% confidence

---

### Phase 4: End-to-End Testing (2 hours)
**Goal:** Validate full Architect → Tester pipeline

**Tasks:**
1. Test on 3 architectures (1 hour)
   - 01_minimal_vulnerable (expect low scores)
   - 02_minimal_defended (expect medium scores)
   - 10_complex_enterprise (expect high scores)

2. Plant deliberate flaws (30 min)
   - Invalid MITRE mapping
   - Overestimated effectiveness
   - Missing verification method

3. Verify Tester catches flaws (30 min)

**Deliverable:** Confidence validation (target: 85%)

---

## Total Effort & Confidence

| Approach | Effort | Confidence | Trade-offs |
|----------|--------|------------|------------|
| **Deterministic (original)** | 15-20h | 93% | ❌ Over-engineered, brittle |
| **Current (Phase 2 only)** | 5h | 75% | ❌ Too low for security |
| **Balanced (LLM-centric)** | 8h | 85% | ✅ Good balance |

**Recommendation:** Balanced approach (8 hours total, 85% confidence)

---

## Why 85% is Sufficient

### What 85% Means
- ✅ Catches 85% of technical errors (invalid MITRE mappings, overestimates)
- ✅ Catches 80% of semantic gaps (missing complementary controls)
- ✅ Provides actionable feedback (not just "wrong", but "why wrong")
- ⏳ May miss 15% of edge cases (obscure technique interactions)

### Comparison to Alternatives
| Confidence | Approach | Practical Outcome |
|------------|----------|-------------------|
| **75%** | Deterministic rules only | ❌ Misses too many semantic issues |
| **85%** | LLM + tools (balanced) | ✅ Catches most issues, good ROI |
| **93%** | Full deterministic + LLM | ⚠️ Diminishing returns, over-engineered |
| **98%+** | + Historical data + semantic validation | ❌ Not achievable in reasonable time |

### Industry Context
```
Unit tests: 80-90% code coverage = production ready
Security tools: 85% detection rate = industry standard
LLM agents: 85% accuracy = high-performing
```

**Conclusion:** 85% is the "sweet spot" for security testing agents

---

## Key Benefits of LLM-Centric Approach

### 1. Flexibility
```
Deterministic: "Count techniques matching regex pattern"
LLM: "Understand intent, handle variations, reason about results"
```

### 2. Context-Awareness
```
Deterministic: "60% coverage → score = 6/10"
LLM: "60% MFA coverage on critical auth path → HIGH severity gap"
```

### 3. Semantic Understanding
```
Deterministic: ✅ "MFA control has valid MITRE mapping"
LLM: ❌ "MFA alone insufficient for 90-risk phishing threat"
```

### 4. Self-Explanation
```
Deterministic: "FAILED CHECK #7"
LLM: "Ransomware risk=70 but no backup control (M1053). This is critical because..."
```

### 5. Adaptability
```
Deterministic: Needs code changes for new check types
LLM: Learns from system prompt, adapts to new scenarios
```

---

## Migration Path

### Step 1: Keep Phase 2 Work (Don't Throw Away)
```python
# chatbot/modules/mitre_validator.py stays as-is
# Used internally by tools, not directly by Tester
```

**Why:** Tools need the logic, just wrapped differently

---

### Step 2: Create Tool Wrappers (2 hours)
```python
# chatbot/modules/tester_tools.py

from chatbot.modules.mitre_validator import MitreValidator, EffectivenessScorer
from chatbot.modules.agent_framework import AgentTool

def create_tester_tools() -> List[AgentTool]:
    """Create tools for Tester agent."""
    
    # Initialize validators (one-time)
    validator = MitreValidator()
    scorer = EffectivenessScorer(validator)
    
    tools = [
        AgentTool(
            name="validate_mitre_mapping",
            description="Validate technique-mitigation mapping against MITRE ATT&CK",
            function=lambda control: validator.validate_control_techniques(control),
            parameters={...}
        ),
        
        AgentTool(
            name="score_control_effectiveness",
            description="Calculate control effectiveness across attack paths",
            function=lambda control, paths: scorer.score_control_effectiveness(control, paths),
            parameters={...}
        ),
        
        # ... 2 more tools
    ]
    
    return tools
```

---

### Step 3: Enhanced Tester Agent (4 hours)
```python
# chatbot/modules/tester_critic.py

from chatbot.modules.agent_framework import CriticAgent
from chatbot.modules.tester_tools import create_tester_tools

TESTER_SYSTEM_PROMPT = """
You are a Security Tester...
[Enhanced prompt from above]
"""

def create_tester_agent(model: Optional[str] = None) -> CriticAgent:
    """Create Tester critic with LLM reasoning + tools."""
    
    tools = create_tester_tools()
    
    agent = CriticAgent(
        role="Security Tester",
        rubric=TESTER_RUBRIC,
        system_prompt=TESTER_SYSTEM_PROMPT,
        tools=tools,
        model=model
    )
    
    return agent
```

---

### Step 4: Integration Test (2 hours)
```python
# Test full pipeline
from chatbot.modules.artifact_extractor import extract_artifacts
from chatbot.modules.architect_critic import EnhancedArchitectCritic
from chatbot.modules.tester_critic import create_tester_agent

# Extract artifacts
artifacts = extract_artifacts("report/02_minimal_defended")

# Architect critique
architect = EnhancedArchitectCritic()
architect_score = architect.critique(artifacts)

# Tester validation (uses LLM + tools)
tester = create_tester_agent()
tester_score = tester.critique(artifacts, architect_score)

print(f"Tester: {tester_score.score}/100")
for gap in tester_score.gaps:
    print(f"  [{gap['severity']}] {gap['description']}")
```

---

## Success Criteria

### Quantitative
- [ ] Tester detects 100% of planted invalid MITRE mappings
- [ ] Tester detects 80%+ of semantic gaps (e.g., missing complementary controls)
- [ ] Tester calls tools appropriately (<5 calls per critique, not 20+)
- [ ] Overall confidence: 85% (validated on 5+ test cases)

### Qualitative
- [ ] Tester explanations are clear and actionable
- [ ] Tester reasoning goes beyond tool outputs
- [ ] Tester catches issues Phase 2 validator misses
- [ ] Tester critique aligns with manual security review

---

## Comparison: All Three Approaches

| Aspect | Deterministic (Phase 2) | Full Engineering (Phase 3+4) | Balanced LLM (Proposed) |
|--------|------------------------|------------------------------|-------------------------|
| **Effort** | 5h ✅ | 15-20h ❌ | 8h ✅ |
| **Confidence** | 75% ❌ | 93% ✅ | 85% ✅ |
| **Flexibility** | Low (regex patterns) | Low (more patterns) | High (LLM reasoning) |
| **Maintainability** | Medium (460 lines) | Low (1500+ lines) | High (tools + prompt) |
| **Phase 3C Alignment** | Poor (not LLM-centric) | Poor (over-engineered) | Excellent (LLM as judge) |
| **Semantic Gap Detection** | 30% ❌ | 40% ⚠️ | 80% ✅ |
| **ROI** | Medium | Low | High ✅ |

**Winner:** Balanced LLM approach (8h, 85%, aligned with Phase 3C goals)

---

## Recommendation

**Proceed with Balanced LLM-Centric Approach:**

1. ✅ **Keep Phase 2 work** (mitre_validator.py) - Use as tool backend
2. 🔄 **Add tool wrappers** (2h) - Make validators accessible to LLM
3. 🆕 **Build enhanced Tester** (4h) - LLM reasoning + tools
4. ✅ **Test end-to-end** (2h) - Validate 85% confidence

**Total: 8 hours | Confidence: 85% | Aligned with Phase 3C philosophy**

**Why this is better:**
- Respects "LLM as Judge" philosophy (not over-engineering deterministic code)
- Achieves sufficient confidence (85% >> 75%)
- Reasonable effort (8h vs 15-20h)
- Leverages LLM strengths (semantic reasoning, context-awareness)
- Avoids LLM weaknesses (arithmetic, exact pattern matching) via tools

**Next Step:** Implement Phase 2.5 (tool wrappers) - ETA 2 hours
