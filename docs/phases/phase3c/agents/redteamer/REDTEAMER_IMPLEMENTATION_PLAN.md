# Red Teamer Agent: Implementation Plan

**Date:** 2026-05-16  
**Purpose:** Assess exploit difficulty and defense strength  
**Estimated Time:** 4-6 hours  
**Status:** Planning phase

---

## Overview

The Red Teamer agent evaluates architecture defensibility from an attacker's perspective. Unlike Architect (design quality) and Tester (MITRE validation), Red Teamer answers: **"How hard would it be to actually breach this system?"**

**Key Insight:** Red Team score is **INVERTED** - Low score = Hard to exploit = Good defense

---

## Confidence Level Check-In (Before Implementation)

Before building the agent, we'll validate the approach with a **confidence check**:

### Step 1: Manual Red Team Assessment (30 mins)

**Architecture:** `02_minimal_defended.mmd`

**Manual Analysis:**
```
Attack Path #1: Internet → WAF → ALB → Web Server → Database

Hop 1: Internet → WAF
  Technique: T1190 (Exploit Public-Facing App)
  Difficulty: MODERATE (30/100)
    - WAF in place (blocks common exploits)
    - Requires bypass technique or 0-day
    - Public tools: ModSecurity evasion, SQLmap with tamper scripts
    - Skill required: Professional pentester

Hop 2: WAF → ALB → Web Server
  Technique: T1078 (Valid Accounts) via MFA
  Difficulty: HARD (20/100)
    - MFA blocks credential stuffing
    - Requires phishing or SIM swap
    - Public tools: EvilGinx2, modlishka
    - Skill required: Advanced social engineering

Hop 3: Web Server → Database
  Technique: T1552 (Unsecured Credentials)
  Difficulty: MODERATE (40/100)
    - EDR may detect credential access
    - Database encryption requires key access
    - Public tools: Mimikatz, LaZagne
    - Skill required: Professional

Overall Path Difficulty: (30 + 20 + 40) / 3 = 30/100
Rating: LOW = Very difficult to exploit = GOOD DEFENSE
```

**Expected Red Team Score: 30/100** (inverted = 70/100 defense strength)

---

### Step 2: Prompt-Based Prototype (1-2 hours)

Create minimal prompt to test LLM's ability to assess exploit difficulty:

```python
def create_red_team_prompt_v1(artifacts: ArtifactSet) -> str:
    """
    Minimal Red Team prompt for confidence check.
    """
    
    paths = artifacts.attack_paths
    controls = artifacts.control_recommendations
    
    prompt = f"""You are a Red Team assessor evaluating exploit difficulty.

ATTACK PATHS ({len(paths)} paths):
"""
    
    for i, path in enumerate(paths, 1):
        prompt += f"\nPath #{i}: {' → '.join(path['path'])}\n"
        prompt += f"  Techniques: {', '.join(path['techniques'])}\n"
        
        # Show controls at each hop
        for hop_idx, hop in enumerate(path['path'][:-1]):
            prompt += f"  Hop {hop_idx+1} ({hop} → {path['path'][hop_idx+1]}):\n"
            hop_controls = [c['control'] for c in controls if hop in c.get('placement', [])]
            if hop_controls:
                prompt += f"    Controls: {', '.join(hop_controls)}\n"
            else:
                prompt += f"    Controls: None (vulnerable!)\n"
    
    prompt += f"""

TASK: Assess exploit difficulty (0-100 scale)

For each attack path:
1. Evaluate each hop:
   - Can attacker exploit with public tools (Metasploit, Burp Suite)?
   - What skill level required (script kiddie / professional / APT)?
   - Are controls bypassable?

2. Score difficulty per hop (0-100):
   - 0-20: Nearly impossible (multiple controls, no known bypass)
   - 21-40: Very difficult (strong controls, requires custom exploits)
   - 41-60: Difficult (moderate controls, public tools with skill)
   - 61-80: Moderate (weak controls, public tools work)
   - 81-100: Trivial (no controls, script kiddie level)

3. Average across hops for path difficulty

REMEMBER: Low score = hard to exploit = GOOD defense

OUTPUT FORMAT:
{{
  "paths": [
    {{
      "path_id": 1,
      "hops": [
        {{
          "hop": "Internet → WAF",
          "technique": "T1190",
          "difficulty": 30,
          "reasoning": "WAF blocks common exploits, requires bypass"
        }}
      ],
      "average_difficulty": 30
    }}
  ],
  "overall_difficulty": 30,
  "rating": "LOW = Very difficult = GOOD defense"
}}
"""
    
    return prompt
```

**Test:**
```bash
# Run on 02_minimal_defended
python3 -c "
from chatbot.modules.artifact_extractor import extract_artifacts
from chatbot.modules.llm_client import LLMClient

artifacts = extract_artifacts('report/02_minimal_defended')
prompt = create_red_team_prompt_v1(artifacts)
client = LLMClient()
response = client.chat([{'role': 'user', 'content': prompt}])
print(response.content)
"
```

**Expected Output:**
```json
{
  "overall_difficulty": 25-35,
  "rating": "LOW = Very difficult = GOOD defense"
}
```

**Confidence Check:**
- ✅ If score is 25-35: LLM can assess exploit difficulty correctly
- ⚠️ If score is 60-80: LLM being too pessimistic, needs examples
- ❌ If score is >80: LLM doesn't understand inverted scoring

---

### Step 3: Compare Vulnerable vs Defended (1 hour)

Test on contrasting architectures:

**01_minimal_vulnerable (No controls):**
- Expected: 80-90 (trivial to exploit)
- Path: Internet → Web Server → Database (no WAF, no MFA, no EDR)

**02_minimal_defended (With controls):**
- Expected: 25-35 (very difficult to exploit)
- Path: Internet → WAF → ALB → MFA → Web Server (EDR) → Database (Encrypted)

**Validation:**
```python
def validate_red_team_scoring():
    """
    Verify Red Team can distinguish vulnerable vs defended.
    """
    # Test vulnerable
    vuln_artifacts = extract_artifacts('report/01_minimal_vulnerable')
    vuln_score = prototype_red_team(vuln_artifacts)
    
    # Test defended
    def_artifacts = extract_artifacts('report/02_minimal_defended')
    def_score = prototype_red_team(def_artifacts)
    
    # Verify contrast
    assert vuln_score > def_score + 30, "Red Team should score vulnerable much higher"
    assert vuln_score >= 70, "Vulnerable should be EASY to exploit"
    assert def_score <= 40, "Defended should be HARD to exploit"
    
    print(f"✅ Vulnerable: {vuln_score}/100 (HIGH = easy to exploit)")
    print(f"✅ Defended: {def_score}/100 (LOW = hard to exploit)")
    print(f"✅ Contrast: {vuln_score - def_score} points (good discrimination)")
```

**Success Criteria:**
- Vulnerable scores 70+ (easy to exploit)
- Defended scores <40 (hard to exploit)
- Contrast >30 points (clear discrimination)

---

## Full Implementation (After Confidence Check)

Only proceed if confidence check passes (Step 1-3 successful).

### Rubric (100 points, INVERTED)

**A. Exploit Difficulty (40 points)**
- Path complexity (10 pts) - More hops = harder
- Technique sophistication (10 pts) - T14xx harder than T10xx
- Skill required (10 pts) - Script kiddie vs APT
- Tool availability (10 pts) - Public exploits vs custom

**B. Defense Evasion (30 points)**
- Control bypass (15 pts) - Can attacker evade controls?
- Detection avoidance (15 pts) - Can attacker stay undetected?

**C. Attack Path Realism (30 points)**
- Tactic sequence (10 pts) - Is progression realistic?
- Privilege escalation (10 pts) - Can attacker gain needed access?
- Persistence (10 pts) - Can attacker maintain access?

**INVERTED SCORING:**
- 90-100 = CRITICAL (trivial to exploit, defense is weak)
- 70-89 = HIGH (moderate difficulty, defense has gaps)
- 50-69 = MEDIUM (difficult, defense is okay)
- 30-49 = LOW (very difficult, defense is strong)
- 0-29 = MINIMAL (nearly impossible, defense is excellent)

---

### Output Schema

```json
{
  "score": 30,
  "rating": "LOW = Very difficult to exploit = GOOD defense",
  "breakdown": {
    "exploit_difficulty": 18,
    "defense_evasion": 8,
    "attack_path_realism": 4
  },
  "paths": [
    {
      "path_id": 1,
      "description": "Internet → WAF → Web Server → Database",
      "difficulty": 30,
      "hops": [
        {
          "hop": "Internet → WAF",
          "technique": "T1190",
          "difficulty": 30,
          "controls": ["WAF", "Rate Limiting"],
          "bypass_difficulty": "HIGH",
          "public_tools": ["SQLmap with tamper", "ModSecurity evasion"],
          "skill_required": "Professional"
        }
      ]
    }
  ],
  "gaps": [
    {
      "severity": "MEDIUM",
      "description": "No IDS/IPS on internal network - attacker can move laterally undetected"
    }
  ]
}
```

---

## Integration with Orchestrator

**Weighted scoring:**
```python
def calculate_composite(architect: int, tester: int, red_team: int) -> int:
    """
    Calculate final composite with Red Team inverted.
    
    Weights:
    - Architect: 30% (design quality)
    - Tester: 30% (validation)
    - Red Team: 40% (defense strength, INVERTED)
    """
    red_team_defense = 100 - red_team  # Invert: low exploit = strong defense
    return int(architect * 0.30 + tester * 0.30 + red_team_defense * 0.40)
```

**Example:**
- Architect: 82/100 (design quality)
- Tester: 88/100 (validation)
- Red Team: 30/100 (exploit difficulty = 70/100 defense strength)
- Composite: (82 × 0.30) + (88 × 0.30) + (70 × 0.40) = **79/100**

---

## Implementation Checklist

### Phase 1: Confidence Check (2 hours)
- [ ] Manual red team assessment (30 mins)
- [ ] Create prototype prompt (1 hour)
- [ ] Test on 02_minimal_defended (30 mins)
- [ ] Compare vulnerable vs defended (30 mins)
- [ ] **Decision point:** Proceed only if confidence >75%

### Phase 2: Full Implementation (2-4 hours)
- [ ] Implement full rubric (40+30+30 points)
- [ ] Add technique difficulty database
- [ ] Add control bypass techniques
- [ ] Implement hop-by-hop analysis
- [ ] Add few-shot examples (like Tester)

### Phase 3: Testing (1-2 hours)
- [ ] Test on 5 diverse architectures
- [ ] Verify inverted scoring works correctly
- [ ] Validate contrast (vulnerable vs defended)
- [ ] Check Orchestrator integration

### Phase 4: Documentation (1 hour)
- [ ] Create REDTEAMER_RUBRIC.md
- [ ] Add examples to README
- [ ] Update NEXT_STEPS_ANALYSIS.md with results

---

## Risk Mitigation

**Risk 1: LLM doesn't understand inverted scoring**
- Mitigation: Add explicit examples in prompt
- Fallback: Post-process to invert scores programmatically

**Risk 2: Too optimistic about defenses**
- Mitigation: Include known bypass techniques in prompt
- Fallback: Conservative scoring (assume controls can be bypassed)

**Risk 3: Inconsistent scoring across architectures**
- Mitigation: Use reference architectures for calibration
- Fallback: Normalize scores against baseline

---

## Success Criteria

**Minimum (Phase 1 - Confidence Check):**
- ✅ Red Team scores vulnerable >70 (easy to exploit)
- ✅ Red Team scores defended <40 (hard to exploit)
- ✅ Contrast >30 points (clear discrimination)

**Target (Phase 2 - Full Implementation):**
- ✅ Red Team composite with Architect + Tester ≥80/100
- ✅ Consistent scoring across 22 test architectures
- ✅ Actionable gaps identified (bypass techniques, detection gaps)

**Stretch (Phase 3 - Advanced):**
- ✅ Red Team + Orchestrator ≥85/100 composite
- ✅ Integration with feedback flywheel
- ✅ Automated exploit difficulty database

---

## Next Steps

**Immediate:**
1. Run confidence check (Step 1-3, 2 hours)
2. Review results and decide: proceed or revise?
3. If proceed: Implement full Red Teamer (4 hours)
4. Integrate with Orchestrator (2 hours)

**Total Time:** 8 hours (2 confidence + 4 implementation + 2 integration)

---

**Key Decision Point:** After confidence check, assess if Red Team scoring is reliable enough to proceed. Target: 75%+ confidence that LLM can correctly assess exploit difficulty with inverted scoring.
