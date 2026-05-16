# Phase 3C: Core Implementation Documentation

This folder contains core implementation and architectural documents.

---

## Key Documents

### [HYBRID_MITRE_APPROACH.md](HYBRID_MITRE_APPROACH.md) ⭐
**The Key Innovation**

Solves the defense-in-depth vs strict validation conflict.

**Problem:** Either strict MITRE (misses layered defense) or exhaustive (false confidence)

**Solution:** Separate concerns
```json
{
  "mitigations": ["M1016", "M1026"],     // Defense-in-depth (what's implemented)
  "technique_coverage": {                // Strict validation (what's claimed)
    "T1059": ["M1026"],                 // Only valid for T1059
    "T1190": ["M1016", "M1026"]         // M1016 valid for T1190
  }
}
```

**Impact:** +30 points (32 → 62)

---

### [CONFIDENCE_IMPROVEMENTS.md](CONFIDENCE_IMPROVEMENTS.md)
**The Bug Fixes**

Fixed 3 critical issues:
1. ✅ Residual risk: 0→0 to 36→6.7 (81.4% reduction)
2. ✅ Empty controls: Added coverage_note for supply chain
3. ✅ T1005/T1567: Documented as MITRE limitation

**Impact:** +10 points (62 → 72)

---

### [ISOLATION_GUARANTEE.md](ISOLATION_GUARANTEE.md)
**The Safety Proof**

Proves agent system doesn't break deterministic engine (Phase 3B+).

**Verification:**
- Ground truth SHA256 hash identical before/after
- No code coupling (agents never import ground_truth_generator)
- Separate file namespaces (agents write 04_*, 05_*, 06_*)

**Confidence:** 99.5% that agents are isolated

---

### [BALANCED_LLM_APPROACH.md](BALANCED_LLM_APPROACH.md)
**The Strategy Analysis**

Why prompt-based approach vs tool calling.

**Decision:** Prompt-based for MVP
- Tool calling broken in LLMClient
- Embed MITRE data in prompts instead
- Confidence: 75-80% (acceptable for MVP)

**Future:** Fix tool calling for 85-90%

---

### [TOOL_CALLING_ROOT_CAUSE.md](TOOL_CALLING_ROOT_CAUSE.md)
**The Technical Deep-Dive**

Why tool calling doesn't work.

**Root Cause:** LLMResponse class strips tool_calls field

**Workaround:** Embed data in prompts (prompt-based approach)

**Fix Plan:** Add tool_calls field to LLMResponse (2-3 hours)

---

## Usage

These documents explain **HOW** and **WHY** Phase 3C works.

- **Hybrid Approach:** Read first (key innovation)
- **Confidence Improvements:** Bug fixes and validation
- **Isolation Guarantee:** Safety proof
- **LLM Strategy:** Design decisions
- **Tool Calling:** Technical details

Refer to these when:
- Understanding design decisions
- Debugging agent issues
- Planning future improvements
- Explaining to others
