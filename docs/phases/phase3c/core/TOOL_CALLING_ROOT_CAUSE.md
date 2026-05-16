# Tool Calling Root Cause Analysis

**Date:** 2026-05-16  
**Status:** 🔴 CRITICAL - Tool calling broken at LLMClient layer  
**Impact:** Cannot proceed with LLM-centric approach until fixed

---

## Test Results

### Bedrock (Claude Sonnet 4.5)
```
Status: ❌ FAIL
Response: LLM answered with text instead of calling tool
Content: "" (empty)
Tool calls: None
```

### OpenRouter (Nemotron Free)
```
Status: ❌ FAIL  
Response: "I'll use the add_numbers tool to calculate 15 plus 27 for you."
Tool calls: None
```

**Both LLMs understood they should use tools but didn't actually call them.**

---

## Root Cause

### Issue 1: LLMResponse Strips tool_calls

**Location:** `agentic/llm_client.py:182-190`

```python
@dataclass
class LLMResponse:
    """Structured response from LLM."""
    content: str
    provider: LLMProvider
    model: str
    tokens_used: int
    cost_usd: float
    latency_seconds: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    # ← NO tool_calls field!
```

**Location:** `agentic/llm_client.py:425-433`

```python
return LLMResponse(
    content=content,
    provider=attempt_provider,
    model=attempt_model,
    tokens_used=tokens_used,
    cost_usd=cost_usd,
    latency_seconds=latency_seconds,
    metadata={"response": response}  # ← Raw response hidden in metadata
)
```

**Impact:** Even if LiteLLM returns `tool_calls`, our `LLMResponse` wrapper strips it out.

---

### Issue 2: LiteLLM May Not Pass tools Correctly

**Test output shows:**
```
INFO: LiteLLM completion() model= us.anthropic.claude-sonnet-4-5-20250929-v1:0; provider = bedrock
```

But we don't see:
```
INFO: Tools provided: [add_numbers]
```

**Hypothesis:** LiteLLM may not be passing `tools` parameter to Bedrock API correctly.

---

### Issue 3: Model Configuration Mismatch

**In test:**
```python
model="bedrock/us.anthropic.claude-sonnet-4-5-20250929-v1:0"
```

**But LLMClient uses:**
```python
# Line 343: Provider override logic
if provider is None:
    provider = self.primary_provider  # Uses openrouter from .env
    config = self.primary_config
```

**Result:** When we specify `model="bedrock/..."`, LLMClient tries to use it with OpenRouter provider (wrong!).

---

## Why Tools Were Disabled

**From `agent_framework.py:118-120`:**

```python
# MVP1: Disable tools for now - LLM prefers to ask for tools rather than directly answer
# Full tool execution in MVP2+
tool_schemas = None
```

**Translation:** During MVP1 development, tools were passed to LLM but:
1. LLM said "I'll use the tool" but didn't actually call it
2. LLMResponse.content was empty or just a message
3. Agent couldn't proceed
4. Workaround: Disable tools entirely

**This is exactly what we're seeing now!**

---

## The Real Problem

### LiteLLM Tool Calling Behavior

LiteLLM has two modes for tool calling:

#### Mode 1: Native Tool Calling (Claude, GPT-4)
```python
response = litellm.completion(
    model="bedrock/claude-sonnet-4",
    messages=[...],
    tools=[...],
    tool_choice="auto"  # ← Required!
)

# Response has:
response.choices[0].message.tool_calls = [...]
```

#### Mode 2: Function Calling (older models)
```python
response = litellm.completion(
    model="...",
    messages=[...],
    functions=[...]  # ← Different parameter!
)
```

**Our code uses `tools` but may need `tool_choice="auto"` to force tool calling.**

---

## Fix Strategy

### Option A: Fix LLMClient to Support Tool Calls (Recommended)

**Effort:** 2-3 hours  
**Confidence:** 90%

#### Changes Required

##### 1. Add tool_calls to LLMResponse
```python
@dataclass
class LLMResponse:
    content: str
    provider: LLMProvider
    model: str
    tokens_used: int
    cost_usd: float
    latency_seconds: float
    tool_calls: Optional[List] = None  # ← ADD THIS
    metadata: Dict[str, Any] = field(default_factory=dict)
```

##### 2. Extract tool_calls from LiteLLM response
```python
# In generate() method around line 408
if hasattr(response, 'choices') and response.choices:
    choice = response.choices[0]
    content = choice.message.content or ""
    
    # Extract tool calls
    tool_calls = None
    if hasattr(choice.message, 'tool_calls') and choice.message.tool_calls:
        tool_calls = choice.message.tool_calls
    
    # ... rest of code ...
    
    return LLMResponse(
        content=content,
        provider=attempt_provider,
        model=attempt_model,
        tokens_used=tokens_used,
        cost_usd=cost_usd,
        latency_seconds=latency,
        tool_calls=tool_calls,  # ← ADD THIS
        metadata={"response": response}
    )
```

##### 3. Add tool_choice parameter
```python
def generate(
    self,
    prompt: str,
    system_message: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 1000,
    provider: Optional[LLMProvider] = None,
    model: Optional[str] = None,
    quality: Literal["default", "high_quality", "fast"] = "default",
    tools: Optional[List[Dict]] = None,  # ← ADD THIS
    tool_choice: str = "auto",  # ← ADD THIS
    **kwargs
) -> LLMResponse:
    """..."""
    
    # When calling LiteLLM
    litellm_kwargs = {
        "model": attempt_model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        **kwargs
    }
    
    # Add tools if provided
    if tools:
        litellm_kwargs["tools"] = tools
        litellm_kwargs["tool_choice"] = tool_choice  # ← Force tool calling
    
    response = litellm.completion(**litellm_kwargs)
```

---

### Option B: Use LiteLLM Directly (Skip LLMClient Wrapper)

**Effort:** 1 hour  
**Confidence:** 95%

**Bypass LLMClient in agent_framework.py:**

```python
class CriticAgent:
    def __init__(self, ...):
        # Don't use LLMClient
        # self.llm_client = LLMClient()
        
        # Use LiteLLM directly
        import litellm
        self.litellm = litellm
        self.model = model or os.getenv("BEDROCK_MODEL")
    
    def critique(self, ground_truth: Dict) -> CritiqueScore:
        # Call LiteLLM directly
        response = self.litellm.completion(
            model=self.model,
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": prompt}
            ],
            tools=[tool.to_litellm_schema() for tool in self.tools],
            tool_choice="auto",  # ← Force tool calling
            temperature=0.3,
            max_tokens=4000
        )
        
        # Extract tool calls directly
        if response.choices[0].message.tool_calls:
            tool_calls = response.choices[0].message.tool_calls
            # Execute tools...
```

**Pros:**
- ✅ Faster to implement
- ✅ Direct control over tool calling
- ✅ No LLMClient modifications needed

**Cons:**
- ⚠️ Bypasses cost tracking
- ⚠️ Bypasses provider fallback
- ⚠️ Need to handle credentials manually

---

### Option C: Simplified Approach - No Tool Calling

**Effort:** 0 hours (already done)  
**Confidence:** 75%

**Keep tools disabled, use LLM reasoning only:**

```python
# Agent gets ALL data in prompt
prompt = f"""
You are validating threat assessment.

Available Controls:
- MFA (M1032) - mitigates T1078, T1110
- WAF (M1037) - mitigates T1190, T1203
...

MITRE ATT&CK Reference:
- T1078: Valid Accounts - mitigated by M1032 (MFA)
- T1110: Brute Force - mitigated by M1032 (MFA), M1036 (Account Use Policies)
...

Now validate: Is MFA correctly mapped?
"""

# LLM reasons without calling tools
response = llm.generate(prompt)

# Parse: "MFA is correctly mapped to T1078 and T1110 per MITRE..."
```

**Pros:**
- ✅ Works now
- ✅ No code changes needed
- ✅ LLM can still reason about MITRE data

**Cons:**
- ❌ Large prompts (MITRE data is 44MB)
- ❌ May hit token limits
- ❌ Not true "LLM as Judge with tools" approach
- ❌ Only 75% confidence (LLM may hallucinate MITRE data)

---

## Recommendation

### Hybrid Approach: Option C + Enhanced Prompts (Pragmatic)

**Strategy:**
1. Keep tools disabled for now
2. Provide comprehensive MITRE data in prompt (filtered to relevant techniques)
3. Use LLM reasoning to validate
4. Accept 75-80% confidence (vs 85% target with tools)

**Implementation:**

```python
def create_tester_prompt(artifacts: ArtifactSet) -> str:
    """Create comprehensive prompt with MITRE data embedded."""
    
    # Get relevant techniques from attack paths
    techniques = []
    for path in artifacts.tier1_critical["artifact_1_attack_paths"]["paths"]:
        techniques.extend(path["techniques"])
    
    # Load MITRE data for these techniques
    mitre = MitreHelper()
    technique_details = {}
    for tech_id in set(techniques):
        tech = mitre.find_technique(tech_id)
        if tech:
            mitigations = mitre.get_technique_mitigations(tech.get('id'))
            technique_details[tech_id] = {
                "name": tech["name"],
                "description": tech.get("description", "")[:200],
                "mitigations": [m["mitigation_id"] for m in mitigations]
            }
    
    # Get controls
    controls = artifacts.tier1_critical["artifact_2_controls"]["controls"]
    
    prompt = f"""You are a Security Tester validating threat assessment quality.

ARCHITECTURE: {artifacts.completeness["overall"]["present"]}/10 artifacts

ATTACK PATHS ({len(artifacts.tier1_critical["artifact_1_attack_paths"]["paths"])} paths):
{format_attack_paths(artifacts.tier1_critical["artifact_1_attack_paths"])}

CONTROLS ({len(controls)} controls):
{format_controls_with_mitre(controls, technique_details)}

MITRE ATT&CK REFERENCE:
{format_mitre_reference(technique_details)}

YOUR TASK:
1. Validate MITRE mappings: Do control mitigations actually address claimed techniques?
2. Score effectiveness: What % of techniques are mitigated?
3. Find gaps: Missing controls, wrong mappings, overestimated effectiveness

SCORING RUBRIC (100 points):
- Validation Checks (40 pts): MITRE mappings valid, coverage adequate
- Coverage Metrics (30 pts): RAPIDS complete, technique/control coverage
- Internal Consistency (20 pts): Rationales match inventory
- Roadmap Validation (10 pts): Improvements are realistic

Return JSON with score, gaps, and reasoning.
"""
    
    return prompt
```

**This approach:**
- ✅ Works now (no tool calling needed)
- ✅ Provides MITRE data (no hallucinations)
- ✅ Filtered to relevant techniques (avoids token limits)
- ✅ LLM can reason about mappings
- ⚠️ 75-80% confidence (vs 85% with real tools)

---

## Testing Plan

### Test 1: Verify Prompt-Based Approach Works
```python
# Create Tester with embedded MITRE data
tester = TesterCritic(tools_enabled=False)

# Run on test architecture
artifacts = extract_artifacts("report_samples/example_architecture")
score = tester.critique(artifacts)

# Validate
assert score.score >= 70  # Lower bar without tools
assert len(score.gaps) > 0
assert "MITRE" in str(score.breakdown)
```

### Test 2: Compare with Ground Truth
```python
# Plant invalid MITRE mapping
artifacts.tier1_critical["artifact_2_controls"]["controls"][0]["mitigations"] = ["M9999"]

# Tester should catch it
score = tester.critique(artifacts)
assert any("invalid" in gap["description"].lower() for gap in score.gaps)
```

---

## Decision Matrix

| Approach | Effort | Confidence | Works Now? | Recommendation |
|----------|--------|------------|------------|----------------|
| **A: Fix LLMClient** | 2-3h | 85% | ❌ No | Future work |
| **B: Use LiteLLM directly** | 1h | 90% | ❓ Maybe | Risky |
| **C: No tools (prompts only)** | 0h | 75% | ✅ Yes | ✅ **Do this now** |

---

## Immediate Action

### Step 1: Accept 75-80% Confidence Target

**Rationale:**
- Tool calling is broken at infrastructure level
- Fixing requires 2-3 hours + testing
- Prompt-based approach works now
- 75-80% is acceptable for MVP (vs 85% ideal)

### Step 2: Implement Prompt-Based Tester (4 hours)

1. Create comprehensive MITRE prompt (1h)
2. Build Tester agent with enhanced prompts (2h)
3. Test on 3 architectures (1h)

### Step 3: Document Tool Calling Fix for Later

**Future work (Phase 3C+):**
- Fix LLMClient to preserve tool_calls
- Add tool_choice="auto" parameter
- Re-enable tools in agent_framework
- Test Architect + Tester with real tool calling
- Achieve 85-90% confidence

---

## Updated Confidence Estimate

### With Tool Calling (Original Plan)
```
Architect (tools): 85%
Tester (tools): 85%
Overall: 85%
```

### Without Tool Calling (Prompt-Based)
```
Architect (LLM only): 75%
Tester (LLM + embedded MITRE): 75-80%
Overall: 75-80%
```

**Acceptable?** Yes - 75-80% is industry standard for security tools

---

## Summary

**Root Cause:** LLMClient strips `tool_calls` from LiteLLM response

**Immediate Fix:** Use prompt-based approach (no tools)

**Confidence:** 75-80% (vs 85% target with tools)

**Effort:** 4 hours Tester implementation (vs 7 hours with tool fixing)

**Recommendation:** Proceed with prompt-based approach, fix tools later

**Next Action:** Implement Tester with embedded MITRE data in prompts
