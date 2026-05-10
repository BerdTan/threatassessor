# Phase 3C: Agent Framework Comparison

**Date:** 2026-05-10  
**Context:** Evaluating agent frameworks for Phase 3C LLM Critic implementation  
**Decision Required:** Custom framework vs open-source framework

---

## Requirement Summary

**What We Need:**
- 4 agents: Architect, Tester, Red Teamer, Orchestrator
- Tool use: Agents need to search MITRE, validate techniques, check coverage
- Structured output: JSON with rubric scores
- Sequential execution: Architect → Tester → Red Teamer (managed by Orchestrator)
- Conflict resolution: Orchestrator aggregates scores, resolves disagreements
- LiteLLM integration: Must work with existing `agentic/llm_client.py`

**Constraints:**
- Must be production-stable (not experimental)
- Low learning curve (<4 hours to implement MVP1)
- Minimal dependencies (prefer lightweight)
- Works with OpenRouter, Bedrock, Anthropic (via LiteLLM)

---

## Framework Options

### 1. **Custom Framework** (Proposed in Phase 3C doc)

**Pros:**
- ✅ Tailored to exact needs (no bloat)
- ✅ Full control (no framework updates breaking code)
- ✅ Already designed (300 lines, clear structure)
- ✅ No new dependencies
- ✅ Integrates seamlessly with LiteLLM
- ✅ Learning curve: 0 hours (we design it)

**Cons:**
- ❌ Build from scratch (~2-3 hours for framework)
- ❌ Test thoroughly (need unit tests for framework)
- ❌ Maintain ourselves (bug fixes, enhancements)

**Code Estimate:** ~300 lines total
```python
# chatbot/modules/agent_framework.py (~150 lines)
class CriticAgent:
    def __init__(self, role, rubric, prompt, tools): ...
    def critique(self, ground_truth): ...
    
class OrchestratorAgent:
    def __init__(self, critics): ...
    def run_critique(self, ground_truth): ...
```

**Dependencies:** None (uses existing LiteLLM)

---

### 2. **LangGraph** (LangChain ecosystem)

**Description:** Graph-based workflow for agents with cycles, branching, state management

**Pros:**
- ✅ Production-stable (used by many companies)
- ✅ Graph-based workflow (natural fit for Orchestrator → Critics)
- ✅ State management (pass context between agents)
- ✅ Tool integration built-in
- ✅ Good documentation

**Cons:**
- ❌ Heavy dependency (requires LangChain ecosystem)
- ❌ Learning curve (2-3 hours to understand graph concepts)
- ❌ LangChain-centric (may conflict with LiteLLM)
- ❌ Overkill for sequential workflow (we don't need cycles)

**Code Estimate:** ~400-500 lines (framework overhead + our logic)

**Dependencies:** `langgraph`, `langchain`, `langchain-core` (~5MB)

**Example:**
```python
from langgraph.graph import StateGraph

graph = StateGraph()
graph.add_node("architect", architect_agent)
graph.add_node("tester", tester_agent)
graph.add_node("red_teamer", red_teamer_agent)
graph.add_edge("architect", "tester")
graph.add_edge("tester", "red_teamer")
```

**Verdict:** ⚠️ Powerful but heavy. Overkill for our sequential workflow.

---

### 3. **CrewAI** (Agent collaboration framework)

**Description:** Multi-agent collaboration with roles, tasks, and delegation

**Pros:**
- ✅ Built for multi-agent workflows (natural fit)
- ✅ Role-based agents (Architect, Tester, Red Teamer)
- ✅ Task delegation (Orchestrator assigns tasks)
- ✅ Simple API
- ✅ Good documentation

**Cons:**
- ❌ Opinionated (enforces CrewAI patterns)
- ❌ Async-first (may complicate sequential execution)
- ❌ LangChain dependency (again, conflicts with LiteLLM)
- ❌ Learning curve (1-2 hours to understand Crew/Agent/Task model)

**Code Estimate:** ~350-400 lines

**Dependencies:** `crewai`, `langchain`, `pydantic` (~8MB)

**Example:**
```python
from crewai import Agent, Task, Crew

architect = Agent(role="Security Architect", tools=[...])
tester = Agent(role="Security Tester", tools=[...])
red_teamer = Agent(role="Red Teamer", tools=[...])

crew = Crew(agents=[architect, tester, red_teamer])
result = crew.kickoff(inputs={"ground_truth": ...})
```

**Verdict:** ⚠️ Good fit conceptually, but LangChain dependency is concern.

---

### 4. **AutoGen** (Microsoft)

**Description:** Conversational agents that chat to solve tasks

**Pros:**
- ✅ Microsoft-backed (stable)
- ✅ Multi-agent conversation (agents debate findings)
- ✅ Code execution (can run Python tools)
- ✅ Good for collaborative tasks

**Cons:**
- ❌ Conversation-based (not ideal for structured rubric scoring)
- ❌ Non-deterministic (agents chat until consensus, hard to control)
- ❌ Complex setup (need to configure conversation patterns)
- ❌ Learning curve (2-3 hours to understand conversation model)

**Code Estimate:** ~500+ lines (complex conversation orchestration)

**Dependencies:** `pyautogen`, `openai` (~10MB)

**Verdict:** ❌ Not a good fit. Too conversational, not structured enough.

---

### 5. **Phidata** (Lightweight agent framework)

**Description:** Simple agent framework with tools and memory

**Pros:**
- ✅ Lightweight (~2MB)
- ✅ Simple API (easy to learn)
- ✅ Tool integration built-in
- ✅ Works with multiple LLM providers
- ✅ No heavy dependencies

**Cons:**
- ⚠️ Relatively new (less battle-tested)
- ⚠️ Smaller community (fewer examples)
- ❌ No built-in orchestration (need to build ourselves)

**Code Estimate:** ~250-300 lines

**Dependencies:** `phidata` (~2MB)

**Example:**
```python
from phi.agent import Agent
from phi.tools import Tool

architect = Agent(
    role="Security Architect",
    tools=[search_mitre, check_controls]
)
result = architect.run(task="Review this architecture...")
```

**Verdict:** ✅ Promising. Lightweight, but still need orchestration logic.

---

### 6. **Strands AI** / **MAF** / **ADK**

**Research Status:** Could not find well-documented Python frameworks with these names.
- "Strands AI" - Not found in major repositories
- "MAF" - Too generic (Multiple Agent Framework?)
- "ADK" - Unclear which framework (Amazon Agent Development Kit?)

**Verdict:** ❌ Insufficient information to evaluate.

---

## Recommendation Matrix

| Framework | Setup Time | Code Lines | Deps | Fit Score | Verdict |
|-----------|-----------|-----------|------|-----------|---------|
| **Custom** | 2-3h | ~300 | None | 95% | ✅ **Recommended** |
| **Phidata** | 1-2h | ~250-300 | 2MB | 85% | ✅ Alternative |
| **LangGraph** | 2-3h | ~400-500 | 5MB | 70% | ⚠️ Overkill |
| **CrewAI** | 1-2h | ~350-400 | 8MB | 75% | ⚠️ LangChain dependency |
| **AutoGen** | 3-4h | ~500+ | 10MB | 50% | ❌ Not structured enough |

---

## Decision Recommendation

### **Option A: Custom Framework** (Recommended)

**Why:**
1. **Exact fit:** Designed for our exact needs (4 agents, rubric scoring, sequential)
2. **No dependencies:** Uses existing LiteLLM (no new packages)
3. **Full control:** No framework updates breaking code
4. **Simple:** 300 lines, clear structure
5. **Fast to build:** MVP1 includes framework (~2-3 hours total)

**Trade-off:** Build and maintain ourselves (~150 lines of framework code)

**When to reconsider:** If we need >10 agents or complex workflows in the future

---

### **Option B: Phidata** (Alternative if framework complexity grows)

**Why:**
1. **Lightweight:** Only 2MB dependency
2. **Simple API:** Easy to learn (<1 hour)
3. **Tool integration:** Built-in tool support
4. **Multi-provider:** Works with LiteLLM

**Trade-off:** Still need to build orchestration logic ourselves

**When to use:** If custom framework gets >500 lines or we need more agent features

---

## Implementation Plan (Custom Framework)

### MVP1: Framework + Architect (2-3 hours)

**Step 1: Core Framework (1 hour)**
```python
# chatbot/modules/agent_framework.py (~150 lines)

from dataclasses import dataclass
from typing import Dict, List, Callable

@dataclass
class AgentTool:
    name: str
    description: str
    function: Callable

class CriticAgent:
    """Reusable agent for critique roles"""
    def __init__(self, role: str, rubric: Dict, prompt: str, tools: List[AgentTool]):
        self.role = role
        self.rubric = rubric
        self.prompt = prompt
        self.tools = tools
        self.llm_client = LLMClient()  # Existing LiteLLM client
        
    def critique(self, ground_truth: Dict) -> Dict:
        """Execute agent critique with tool use"""
        # 1. Format prompt with ground truth data
        # 2. LLM generates response with tool calls
        # 3. Execute tools
        # 4. Return structured output (rubric scores + gaps)
        pass
        
    def _format_prompt(self, ground_truth: Dict) -> str:
        """Insert ground truth into agent prompt template"""
        pass
        
    def _validate_output(self, response: Dict) -> bool:
        """Ensure response matches rubric schema"""
        pass

class OrchestratorAgent:
    """Manages 3 critic agents"""
    def __init__(self, critics: List[CriticAgent]):
        self.critics = critics
        self.llm_client = LLMClient()
        
    def run_critique(self, ground_truth: Dict) -> Dict:
        """Sequential execution: Architect → Tester → Red Teamer"""
        # 1. Run each critic agent
        # 2. Aggregate scores
        # 3. Resolve conflicts
        # 4. Consolidate improvements
        # 5. Return unified report
        pass
```

**Step 2: Architect Agent Config (30 min)**
```python
# chatbot/modules/architect_critic.py

from agent_framework import CriticAgent, AgentTool

def search_control_context(control_name: str) -> str:
    """Search for control best practices"""
    pass

def check_architecture_type(components: List[str]) -> str:
    """Identify architecture type (web, AI, IoT)"""
    pass

architect_rubric = {
    "threat_completeness": {"max": 40, "criteria": [...]},
    "control_appropriateness": {"max": 30, "criteria": [...]},
    "defense_in_depth": {"max": 20, "criteria": [...]},
    "context_awareness": {"max": 10, "criteria": [...]}
}

architect_prompt = """
You are a Senior Security Architect reviewing a threat assessment.

RAPIDS: Ransomware, Application vulnerabilities, Phishing, Insider threat, DoS, Supply chain
...
[Full explicit prompt from Phase 3C doc]
"""

architect_agent = CriticAgent(
    role="Security Architect",
    rubric=architect_rubric,
    prompt=architect_prompt,
    tools=[
        AgentTool("search_control_context", "Search for control best practices", search_control_context),
        AgentTool("check_architecture_type", "Identify architecture type", check_architecture_type)
    ]
)
```

**Step 3: Test on 2 Architectures (30 min)**
```bash
python3 -m chatbot.modules.architect_critic --test 10_complex_enterprise
python3 -m chatbot.modules.architect_critic --test 21_agentic_ai_system
```

**Validation:**
- [ ] Agent completes without errors
- [ ] Output matches rubric schema (JSON validation)
- [ ] Scores are 0-100 range
- [ ] Gaps are actionable (not vague like "improve security")

---

## Framework Integration with Existing Code

**Existing LLM Client:**
```python
# agentic/llm_client.py (already exists)
from litellm import completion

class LLMClient:
    def generate(self, prompt, tools=None, ...):
        response = completion(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            tools=tools,  # Tool definitions for LLM
            ...
        )
        return response
```

**Agent Framework Uses LLMClient:**
```python
# chatbot/modules/agent_framework.py (new)
from agentic.llm_client import LLMClient

class CriticAgent:
    def __init__(self, ...):
        self.llm_client = LLMClient()  # Reuse existing client
        
    def critique(self, ground_truth):
        # Convert agent tools to LiteLLM tool format
        tool_defs = [self._tool_to_schema(t) for t in self.tools]
        
        # Call LLM with tools
        response = self.llm_client.generate(
            prompt=self._format_prompt(ground_truth),
            tools=tool_defs
        )
        
        # Execute tool calls
        if response.tool_calls:
            for tool_call in response.tool_calls:
                result = self._execute_tool(tool_call)
                # Add tool result to context, re-prompt LLM
        
        return response
```

**No Conflicts:** Custom framework wraps existing LLMClient, no new dependencies.

---

## Conclusion

**Decision: Use Custom Framework**

**Rationale:**
1. ✅ Fastest to implement (2-3 hours for MVP1 including framework)
2. ✅ No new dependencies (uses existing LiteLLM)
3. ✅ Exact fit for requirements (sequential agents, rubric scoring)
4. ✅ Full control (no framework updates breaking code)
5. ✅ Lightweight (300 lines total)

**If complexity grows (>500 lines or >10 agents):** Re-evaluate Phidata as lightweight alternative.

**Framework avoided:** LangGraph (overkill), CrewAI (LangChain dependency), AutoGen (too conversational).

---

**Document Status:** Decision ready for Phase 3C MVP1 implementation  
**Next Step:** Build `chatbot/modules/agent_framework.py` (~150 lines)  
**Estimated Time:** 1 hour (framework base) + 1-2 hours (Architect agent config + testing)
