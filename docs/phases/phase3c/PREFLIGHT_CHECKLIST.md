# Phase 3C Pre-Flight Checklist

**Date:** 2026-05-16  
**Purpose:** Verify all requirements before implementing LLM-centric Tester agent  
**Status:** 🔴 CRITICAL GAPS FOUND

---

## Critical Findings

### ❌ 1. Architect Agent NOT Using LLM
**Location:** `chatbot/modules/agent_framework.py:120`

```python
# Line 120: Tools are DISABLED
tool_schemas = None  # [tool.to_litellm_schema() for tool in self.tools] if self.tools else None

# Line 126: LLM called but tools disabled
response = self.llm_client.generate(
    prompt=prompt,
    system_message=self.system_prompt,
    model=self.model,
    # tools=tool_schemas,  # ← COMMENTED OUT!
    temperature=0.3,
    max_tokens=4000
)
```

**Impact:** ❌ Architect agent calls LLM but can't use tools (violates balanced approach)

**Fix Required:** Enable tools in `agent_framework.py`

---

### ❌ 2. No Confidence Threshold Validation
**Location:** `chatbot/modules/agent_framework.py:165-177`

```python
# CritiqueScore created but no validation
score = CritiqueScore(
    role=self.role,
    score=current_score,  # ← No check if >= 85%
    ...
)

logger.info(f"{self.role}: Critique complete - Score: {score.score}/{score.max_score} ({score.rating})")
# ← Agent continues even if score < 85%!
```

**Impact:** ❌ Agent outputs can be below 85% confidence with no warning/blocking

**Fix Required:** Add confidence validation before returning

---

### ❌ 3. Tool Calling Untested
**Test:** `python3 -m chatbot.modules.agent_validation`

**Result:**
```
ModuleNotFoundError: No module named 'litellm'
```

**Impact:** ❌ Can't verify tool calling works with OpenRouter/Bedrock

**Fix Required:** Install dependencies + test tool calling

---

### ⚠️ 4. No Agent Transaction Tracing
**Current State:** Logging exists but no structured trace

**Impact:** ⚠️ If agent produces bad output, hard to debug:
- Which LLM was called?
- What tools were used?
- What was the reasoning?
- Where did it fail?

**Fix Required:** Implement `AgentValidator` and `PipelineValidator`

---

## Detailed Analysis

### Issue 1: Architect Agent NOT Using LLM for Tools

#### Current Flow
```
User → Architect Agent
        ↓
      Format prompt with ground truth
        ↓
      LLM.generate(prompt, tools=None)  ← Tools disabled!
        ↓
      Parse JSON response
        ↓
      Return CritiqueScore
```

#### Problems
1. **Tools defined but not used:** Architect has `search_control_context` and `check_architecture_type` tools but they're disabled
2. **No tool execution logic:** Even if enabled, tool results aren't fed back to LLM
3. **Blind to Phase 3C intent:** Should use LLM + tools, currently LLM-only

#### Code Evidence
```python
# chatbot/modules/architect_critic.py:557-593
tools = [
    AgentTool(
        name="search_control_context",
        description="Search for control best practices...",
        function=search_control_context,
        parameters={...}
    ),
    AgentTool(
        name="check_architecture_type",
        description="Identify architecture type...",
        function=check_architecture_type,
        parameters={...}
    )
]

agent = CriticAgent(
    role="Security Architect",
    rubric=ARCHITECT_RUBRIC,
    system_prompt=ARCHITECT_SYSTEM_PROMPT,
    tools=tools,  # ← Defined
    model=model
)

# BUT in agent_framework.py:120
tool_schemas = None  # ← DISABLED for MVP1!
```

#### Why This Happened
**From `agent_framework.py:118-119`:**
```python
# MVP1: Disable tools for now - LLM prefers to ask for tools rather than directly answer
# Full tool execution in MVP2+
```

**Translation:** Tools were disabled because LLM was asking for tools instead of answering directly. This is a **prompt engineering issue**, not a tool problem.

---

### Issue 2: No 85% Confidence Validation

#### Current Behavior
```python
# Agent can return ANY score (0-100)
score = CritiqueScore(
    role="Security Architect",
    score=42,  # ← Way below 85%!
    rating="POOR",
    ...
)

# No validation!
return score
```

#### What Should Happen
```python
# Option A: Block low confidence
if score.score < 85:
    raise ValueError(f"Agent confidence {score.score}% below threshold 85%")

# Option B: Warn and continue
if score.score < 85:
    logger.warning(f"{self.role}: Low confidence {score.score}% (threshold 85%)")
    score.warnings.append(f"Below confidence threshold ({score.score}% < 85%)")

return score
```

#### Why This Matters
**From your requirement #2:**
> "check the output from agent has minimally 85% confidence and above before passing over to next agent"

**Current state:** Architect could output 42% confidence, Tester validates it, pipeline continues → unreliable assessment

---

### Issue 3: Tool Calling Untested

#### Missing Dependencies
```bash
$ python3 -m chatbot.modules.agent_validation
ModuleNotFoundError: No module named 'litellm'
```

#### Required Packages
```bash
pip install litellm
pip install anthropic  # For Bedrock/Claude
pip install openai     # For OpenRouter compatibility
```

#### Why Test Tool Calling First?
**From your requirement #3:**
> "how do we know the function calling by llm is workable and the llm that we are using should be tested out before we go deep into coding"

**Risk:** Spend 8 hours coding LLM-centric Tester, discover OpenRouter free tier doesn't support tool calling → wasted effort

#### OpenRouter Tool Calling Support
| Model | Tool Calling? | Notes |
|-------|---------------|-------|
| nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free | ❓ Unknown | Currently configured model |
| anthropic/claude-sonnet-4 | ✅ Yes | Paid tier, $15/M tokens |
| google/gemma-4-31b-it:free | ⚠️ Limited | May not support tool calling |
| meta-llama/llama-3.3-70b-instruct:free | ❓ Unknown | Often rate-limited |

**Critical:** Must test tool calling BEFORE implementing Tester agent!

---

### Issue 4: No Transaction Tracing

#### Current Debugging Experience
```
❌ Agent produced bad output
   ↓
   Check logs: "INFO: Architect: Critique complete - Score: 42/100 (POOR)"
   ↓
   Why 42%? Which LLM? What tools? What reasoning?
   ↓
   NO VISIBILITY! 🤷
```

#### Desired Tracing
```json
{
  "agent_name": "Architect",
  "duration_seconds": 12.5,
  "llm_provider": "openrouter",
  "llm_model": "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
  "llm_calls": 1,
  "tool_calls": [
    {
      "tool": "check_architecture_type",
      "parameters": {"components": ["WebServer", "Database"]},
      "result_summary": "web_app"
    }
  ],
  "output_score": 42,
  "validation": {
    "used_llm": true,
    "used_tools": true,
    "meets_confidence": false  // ← 42% < 85%
  },
  "errors": [
    "Confidence 42.0% below threshold 85%"
  ]
}
```

**From your requirement #4:**
> "trace of agent transaction should help tracking each stage and blindspot missed in event it went passing wrong msg, output and generate unreliable assessment"

---

## Action Plan

### Phase 0: Pre-Flight Fixes (BEFORE coding Tester) - 3 hours

#### Task 1: Install Dependencies (15 min)
```bash
source .venv/bin/activate
pip install litellm anthropic openai
pip freeze > requirements.txt
```

#### Task 2: Test Tool Calling (30 min)
```bash
# Test with OpenRouter
python3 -m chatbot.modules.agent_validation

# If fails, test with Bedrock (paid tier, should work)
# Update .env: LLM_PROVIDER=bedrock
python3 -m chatbot.modules.agent_validation
```

**Decision Point:**
- ✅ Tool calling works → Continue to Task 3
- ❌ Tool calling fails → Switch to Bedrock OR rethink tool approach

#### Task 3: Enable Tools in Agent Framework (1 hour)
**File:** `chatbot/modules/agent_framework.py`

**Changes:**
```python
# Line 120: Enable tools
tool_schemas = [tool.to_litellm_schema() for tool in self.tools] if self.tools else None

# Line 130: Pass tools to LLM
response = self.llm_client.generate(
    prompt=prompt,
    system_message=self.system_prompt,
    model=self.model,
    tools=tool_schemas,  # ← ENABLE
    temperature=0.3,
    max_tokens=4000
)

# Line 141-147: Implement tool execution
if hasattr(response, 'tool_calls') and response.tool_calls:
    logger.info(f"{self.role}: Executing {len(response.tool_calls)} tool calls")
    tool_results = self._execute_tools(response.tool_calls)
    
    # Re-prompt with tool results
    response = self._continue_with_tool_results(tool_results)
```

**Add method:**
```python
def _execute_tools(self, tool_calls) -> List[Dict]:
    """Execute tool calls and return results."""
    results = []
    for tool_call in tool_calls:
        tool_name = tool_call.function.name
        tool_args = json.loads(tool_call.function.arguments)
        
        # Find tool
        tool = next((t for t in self.tools if t.name == tool_name), None)
        if not tool:
            logger.warning(f"Tool {tool_name} not found")
            continue
        
        # Execute
        try:
            result = tool.function(**tool_args)
            results.append({
                "tool": tool_name,
                "args": tool_args,
                "result": result
            })
        except Exception as e:
            logger.error(f"Tool {tool_name} failed: {e}")
            results.append({
                "tool": tool_name,
                "args": tool_args,
                "error": str(e)
            })
    
    return results
```

#### Task 4: Add Confidence Validation (30 min)
**File:** `chatbot/modules/agent_framework.py`

**Add after line 174:**
```python
# Validate confidence threshold
MIN_CONFIDENCE = 85.0

if score.score < MIN_CONFIDENCE:
    logger.warning(
        f"{self.role}: Low confidence {score.score}% (threshold {MIN_CONFIDENCE}%)"
    )
    
    # Add warning to gaps
    score.gaps.insert(0, {
        "severity": "CRITICAL",
        "category": "meta",
        "description": f"Agent confidence {score.score}% below threshold {MIN_CONFIDENCE}%",
        "recommendation": "Review and improve assessment quality"
    })
```

#### Task 5: Integrate Tracing (1 hour)
**File:** `chatbot/modules/agent_framework.py`

**Add to CriticAgent.__init__:**
```python
from chatbot.modules.agent_validation import AgentValidator

self.validator = AgentValidator(min_confidence=85.0)
```

**Wrap critique method:**
```python
def critique(self, ground_truth: Dict) -> CritiqueScore:
    """Execute critique workflow with validation."""
    
    # Start trace
    trace = self.validator.start_trace(self.role, "ground_truth")
    
    try:
        # ... existing code ...
        
        # Record LLM call
        self.validator.record_llm_call(
            trace,
            provider=self.llm_client.provider,
            model=self.model or "default"
        )
        
        # Record tool calls
        if tool_results:
            for result in tool_results:
                self.validator.record_tool_call(
                    trace,
                    tool_name=result["tool"],
                    parameters=result["args"],
                    result=result.get("result")
                )
        
        # ... rest of existing code ...
        
        # End trace
        self.validator.end_trace(trace, score)
        
        return score
        
    except Exception as e:
        trace.errors.append(str(e))
        raise
```

---

### Phase 1: Verify Architect Works (BEFORE building Tester) - 1 hour

#### Test Script
```python
# test_architect_with_tools.py

import json
from pathlib import Path
from chatbot.modules.artifact_extractor import extract_artifacts
from chatbot.modules.architect_critic import EnhancedArchitectCritic

# Extract artifacts
artifacts = extract_artifacts("report_samples/example_architecture")

# Create Architect (tools enabled)
architect = EnhancedArchitectCritic()

# Run critique
print("Running Architect with tools enabled...")
score = architect.critique(artifacts)

# Check validation
trace = architect.agent.validator.traces[-1]

print(f"\n{'='*70}")
print("ARCHITECT VALIDATION")
print(f"{'='*70}\n")

print(f"Score: {score.score}/100 ({score.rating})")
print(f"Used LLM: {'✅' if trace.used_llm else '❌'}")
print(f"Used Tools: {'✅' if trace.used_tools else '❌'}")
print(f"Meets Confidence: {'✅' if trace.meets_confidence else '❌'}")
print(f"Valid: {'✅' if trace.is_valid else '❌'}")

if trace.errors:
    print(f"\n❌ Errors:")
    for error in trace.errors:
        print(f"  - {error}")

if trace.tool_calls:
    print(f"\n🔧 Tool Calls:")
    for tc in trace.tool_calls:
        print(f"  - {tc['tool']}({tc['parameters']}) → {tc['result_summary']}")

# Save trace
trace_path = "report_samples/example_architecture/architect_trace.json"
with open(trace_path, 'w') as f:
    json.dump(trace.to_dict(), f, indent=2)

print(f"\n📄 Trace saved to: {trace_path}")
```

#### Success Criteria
- [ ] Architect uses LLM (llm_calls >= 1)
- [ ] Architect calls tools (tool_calls >= 1)
- [ ] Score >= 85% OR explicit warning if below
- [ ] Trace saved with full execution details
- [ ] No critical errors

---

### Phase 2: Build Tester Agent (AFTER Architect verified) - 4 hours

Only proceed if Phase 0 + Phase 1 passed!

---

## Risk Assessment

### High Risk (Must Fix)

| Issue | Impact | Probability | Mitigation |
|-------|--------|-------------|------------|
| OpenRouter doesn't support tool calling | 🔴 CRITICAL - Can't use LLM-centric approach | 60% | Test first, switch to Bedrock if needed |
| Tools enabled but LLM doesn't call them | 🔴 HIGH - Back to deterministic approach | 40% | Improve prompt engineering |
| Confidence below 85% not caught | 🔴 HIGH - Unreliable pipeline | 90% | Add validation (30 min fix) |

### Medium Risk (Should Fix)

| Issue | Impact | Probability | Mitigation |
|-------|--------|-------------|------------|
| No transaction tracing | 🟡 MEDIUM - Hard to debug | 100% | Implement tracing (1 hour) |
| Agent-to-agent handoff not validated | 🟡 MEDIUM - Bad output propagates | 70% | Add PipelineValidator |

### Low Risk (Nice to Fix)

| Issue | Impact | Probability | Mitigation |
|-------|--------|-------------|------------|
| LLM calls but doesn't use results | 🟢 LOW - Wasted tokens | 30% | Monitor + improve prompts |
| Tool results too verbose | 🟢 LOW - Token waste | 20% | Truncate in tracing |

---

## Recommendation

### STOP and Fix Pre-Flight Issues (3 hours)

**Before writing any Tester code:**

1. ✅ **Install dependencies** (15 min)
2. ✅ **Test tool calling** (30 min) - Verify OpenRouter/Bedrock supports tools
3. ✅ **Enable tools in Architect** (1 hour) - Remove MVP1 limitation
4. ✅ **Add confidence validation** (30 min) - Block/warn on <85%
5. ✅ **Add tracing** (1 hour) - Track LLM/tool calls

**Then validate:**

6. ✅ **Test Architect with tools** (1 hour) - Ensure it works before building Tester

**Total: 4 hours before Tester implementation**

---

### Why This Matters

**Your 4 requirements:**
1. ❌ "Architect uses LLM" - **YES but tools disabled**
2. ❌ "85% confidence" - **NO validation**
3. ❌ "Tool calling tested" - **UNTESTED (missing deps)**
4. ❌ "Transaction tracing" - **NOT IMPLEMENTED**

**Current state:** 0/4 requirements met

**After pre-flight fixes:** 4/4 requirements met

---

## Next Steps

**Option A: Fix Now (Recommended)**
- 4 hours pre-flight fixes
- 1 hour Architect validation
- 4 hours Tester implementation
- **Total: 9 hours to working MVP**

**Option B: Continue as-is (Risky)**
- 4 hours Tester implementation
- Discover tool calling doesn't work
- Discover Architect not using tools
- Discover no confidence validation
- **Total: 4 hours + unknown rework time**

**Recommendation:** Option A - fix foundations first

---

## Summary

**Status:** 🔴 NOT READY for Tester implementation

**Critical Gaps:**
1. Tools disabled in agent framework
2. No confidence validation
3. Tool calling untested
4. No transaction tracing

**Required Before Proceeding:** 3-4 hours pre-flight fixes

**Confidence After Fixes:** 
- Tool calling: 70% → 95% (tested)
- Agent validation: 0% → 90% (confidence checks)
- Debugging: 40% → 85% (tracing)
- **Overall: 60% → 90%** (ready for Tester)

**Next Action:** Run pre-flight checklist (Task 1: Install dependencies)
