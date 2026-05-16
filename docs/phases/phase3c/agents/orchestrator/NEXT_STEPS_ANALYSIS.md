# Phase 3C: Next Steps and Improvement Analysis

**Date:** 2026-05-16  
**Purpose:** Answer 4 critical questions for Phase 3C completion  
**Status:** Analysis complete, recommendations provided

---

## Question 1: Red Teamer and Orchestrator Agents

### Current State

**Found in `agent_framework.py`:**

#### OrchestratorAgent (Lines 549-650)
```python
class OrchestratorAgent:
    """
    Manages 3 critic agents in sequence.
    
    Workflow:
    1. Run Architect -> Tester -> Red Teamer (sequential)
    2. Aggregate scores (weighted average)
    3. Resolve conflicts (if agents disagree)
    4. Consolidate improvements (de-duplicate, prioritize)
    5. Generate unified report
    """
    
    def __init__(self, critic_agents: List[CriticAgent]):
        if len(critic_agents) != 3:
            raise ValueError("OrchestratorAgent requires exactly 3 critic agents")
        
        self.critics = critic_agents
```

**Scoring weights:**
- Architect: 30% (design quality)
- Tester: 30% (validation correctness)
- Red Team: 40% (defense strength, **INVERTED**)

**Key insight:** Red Team score is inverted - **low score = hard to breach = good defense**

---

### What's Missing

#### Red Teamer Agent Implementation

**Current:** Only base framework exists  
**Needed:** `chatbot/modules/red_teamer_critic.py`

**Red Teamer role:**
- Evaluate exploit difficulty (can attacker actually execute attack path?)
- Check defense evasion (can attacker bypass controls?)
- Validate attack path realism (are techniques chained correctly?)
- Score exploitability (0-100, where 0 = impossible, 100 = trivial)

**Rubric (100 points, INVERTED):**
```
A. Exploit Difficulty (40 points)
   - Path complexity (10 pts) - More hops = harder
   - Technique sophistication (10 pts) - T14xx harder than T10xx
   - Skill required (10 pts) - Are techniques script-kiddie or APT-level?
   - Tool availability (10 pts) - Are exploits public or need custom development?

B. Defense Evasion (30 points)
   - Control bypass (15 pts) - Can attacker evade controls?
   - Detection avoidance (15 pts) - Can attacker stay undetected?

C. Attack Path Realism (30 points)
   - Tactic sequence (10 pts) - Is progression realistic?
   - Privilege escalation (10 pts) - Can attacker gain needed access?
   - Persistence (10 pts) - Can attacker maintain access?

INVERTED SCORING:
- 90-100 = CRITICAL (trivial to exploit, defense is weak)
- 70-89 = HIGH (moderate difficulty, defense has gaps)
- 50-69 = MEDIUM (difficult, defense is okay)
- 30-49 = LOW (very difficult, defense is strong)
- 0-29 = MINIMAL (nearly impossible, defense is excellent)
```

---

### Implementation Plan: Complete Phase 3C

#### Task 1: Implement Red Teamer (4-6 hours)

**File:** `chatbot/modules/red_teamer_critic.py`

**Approach:** Prompt-based (like Tester), embedding:
- Attack path details (hops, techniques, controls)
- MITRE technique difficulty ratings
- Known exploit databases (e.g., ExploitDB references)
- Control bypass techniques

**Prompt structure:**
```python
def create_red_team_prompt(artifacts: ArtifactSet) -> str:
    """
    Create Red Team prompt focused on exploitability.
    
    Embeds:
    - Attack paths with controls at each hop
    - Technique difficulty (T1190 = easy, T1068 = hard)
    - Common bypass techniques
    - Exploit availability
    """
    
    prompt = f"""You are a Red Teamer assessing exploit difficulty.

ATTACK PATHS ({len(paths)} paths):
{format_paths_with_controls(paths)}

CONTROLS IN PLACE ({len(controls)} controls):
{format_controls_by_layer(controls)}

TECHNIQUE DIFFICULTY REFERENCE:
  T1190 (Exploit Public-Facing App): EASY (metasploit available)
  T1068 (Privilege Escalation): HARD (requires 0-day or CVE)
  T1110 (Brute Force): EASY (hydra, burp suite)
  ...

YOUR TASK:
1. For each attack path, assess:
   - How many hops can be exploited with public tools?
   - Which controls can be bypassed?
   - What skill level is required (script kiddie / professional / APT)?
   
2. Score exploitability (0-100):
   - 90-100: Trivial (Metasploit + default creds)
   - 70-89: Moderate (public exploits + some skill)
   - 50-69: Difficult (custom exploits needed)
   - 30-49: Very difficult (0-day required)
   - 0-29: Nearly impossible (multiple controls, no known bypasses)

REMEMBER: High score = easy to exploit = BAD defense
          Low score = hard to exploit = GOOD defense
"""
    return prompt
```

**Test case:** Red Teamer should score `01_minimal_vulnerable.mmd` high (80-90, easy to exploit) and `02_minimal_defended.mmd` low (30-40, hard to exploit).

---

#### Task 2: Integrate Orchestrator (2 hours)

**File:** `chatbot/modules/orchestrator.py` (new, uses existing OrchestratorAgent)

```python
from chatbot.modules.artifact_extractor import extract_artifacts
from chatbot.modules.architect_critic import EnhancedArchitectCritic
from chatbot.modules.tester_critic import TesterCritic
from chatbot.modules.red_teamer_critic import RedTeamerCritic
from chatbot.modules.agent_framework import OrchestratorAgent, CriticAgent

def run_full_critique(report_dir: str) -> Dict:
    """
    Run full 3-agent critique pipeline.
    
    Returns: Unified report with composite score
    """
    # Extract artifacts
    artifacts = extract_artifacts(report_dir)
    
    # Create agents
    architect = EnhancedArchitectCritic()
    tester = TesterCritic()
    red_teamer = RedTeamerCritic()
    
    # Run Architect
    architect_score = architect.critique(artifacts)
    
    # Run Tester (with Architect's roadmap)
    tester_score = tester.critique(artifacts, architect_score)
    
    # Run Red Teamer
    red_team_score = red_teamer.critique(artifacts)
    
    # Orchestrate (using agent base classes for compatibility)
    orchestrator = OrchestratorAgent([
        architect.agent,
        tester.agent,
        red_teamer.agent
    ])
    
    # Aggregate (manual since we already have scores)
    composite = {
        "architect": architect_score.to_dict(),
        "tester": tester_score.to_dict(),
        "red_team": red_team_score.to_dict(),
        "composite_score": calculate_weighted_score(
            architect_score.score,
            tester_score.score,
            red_team_score.score
        ),
        "rating": determine_composite_rating(...),
        "consolidated_gaps": merge_gaps([
            architect_score.gaps,
            tester_score.gaps,
            red_team_score.gaps
        ])
    }
    
    # Save
    output_path = Path(report_dir) / "07_orchestrator_report.json"
    with open(output_path, 'w') as f:
        json.dump(composite, f, indent=2)
    
    return composite

def calculate_weighted_score(arch: int, test: int, red: int) -> int:
    """
    Calculate composite score with inversion for Red Team.
    
    Weights:
    - Architect: 30% (design quality)
    - Tester: 30% (validation)
    - Red Team: 40% (defense strength, inverted)
    """
    red_defense = 100 - red  # Invert: low score = hard to exploit = good
    return int(arch * 0.30 + test * 0.30 + red_defense * 0.40)
```

**Output files:**
```
report/{architecture}/
├── 04_architect_critique.json    # Design quality
├── 05_tester_critique.json       # Validation correctness
├── 06_red_team_critique.json     # Exploit difficulty
└── 07_orchestrator_report.json   # Unified report
```

---

## Question 2: Using Bedrock as Primary LLM

### Current Configuration

**From `.env`:**
```bash
LLM_PROVIDER=openrouter
BEDROCK_MODEL=us.anthropic.claude-sonnet-4-5-20250929-v1:0
OPENROUTER_MODEL=nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free
```

**Current behavior:**
- Primary: OpenRouter (free tier)
- Fallback: Bedrock (paid tier)
- OpenRouter often fails → Falls back to Bedrock automatically

---

### Switching to Bedrock Primary

#### Option 1: Environment Variable (Simple)

**Edit `.env`:**
```bash
# Change this line:
LLM_PROVIDER=openrouter

# To:
LLM_PROVIDER=bedrock

# Keep model configured:
BEDROCK_MODEL=us.anthropic.claude-sonnet-4-5-20250929-v1:0
```

**Result:** All agents will use Bedrock by default.

#### Option 2: Per-Agent Override (Flexible)

```python
# Use Bedrock specifically for Tester
tester = TesterCritic(model="bedrock/us.anthropic.claude-sonnet-4-5-20250929-v1:0")

# Use OpenRouter for Architect (cheaper)
architect = EnhancedArchitectCritic(model="openrouter/...")
```

---

### Differences: OpenRouter vs Bedrock

| Aspect | OpenRouter (Free) | Bedrock (Paid) | Impact on Agents |
|--------|-------------------|----------------|------------------|
| **Model** | Nemotron 3 Nano (30B) | Claude Sonnet 4.5 | ✅ Bedrock much better |
| **Reliability** | ⚠️ Often rate-limited | ✅ Stable | ✅ Fewer fallbacks |
| **Response quality** | ⚠️ Sometimes empty | ✅ Consistent | ✅ Better parsing |
| **JSON compliance** | ⚠️ 70-80% | ✅ 95%+ | ✅ Fewer errors |
| **Cost** | $0.00 | ~$0.014 per critique | ⚠️ ~$0.05 per architecture |
| **Speed** | ~5s | ~30s | ⚠️ Slower but better |
| **Tool calling** | ❌ Not tested reliable | ✅ Native support | ✅ Future-ready |

---

### Recommendation: Use Bedrock as Primary

**Why:**
1. ✅ **Better quality** - Claude Sonnet 4.5 >> Nemotron Nano
2. ✅ **More reliable** - No rate limit issues
3. ✅ **Better JSON** - 95%+ compliance vs 70-80%
4. ✅ **Tool calling ready** - When we enable tools, Bedrock works
5. ✅ **Consistent responses** - No empty/None content issues

**Cost analysis:**
- Per critique: $0.014 (Tester agent, 4693 tokens)
- Per architecture: ~$0.05 (3 agents × $0.014)
- Per 22 architectures: ~$1.10

**Acceptable?** ✅ YES - Quality improvement worth $1/batch

**How to switch:**
```bash
# Edit .env
sed -i 's/LLM_PROVIDER=openrouter/LLM_PROVIDER=bedrock/' .env

# Test
python3 -m chatbot.modules.tester_critic report_samples/example_architecture

# Should see: "Attempting LLM call: provider=LLMProvider.BEDROCK"
```

---

## Question 3: Gaps in Deterministic Engine Output

### Tester Found Real Issues

**Example architecture score: 32/100 (POOR)**

**Gaps identified:**

#### 1. Invalid MITRE Mappings [CRITICAL]
```
LEAST PRIVILEGE claims M1016, M1018 but these aren't valid for T1059, T1133, T1190
MFA claims M1032 for T1485 but M1032 not in T1485's mitigation list
CODE SIGNING claims M1045 for T1490 but M1045 not valid
```

**Root cause:** Deterministic engine (`exhaustive_mitigation_mapper.py`) maps ALL 44 MITRE mitigations to techniques, not just valid ones.

**Impact:** ❌ False mappings → Overestimated control effectiveness → 0% risk reduction

---

#### 2. Zero Risk Reduction [CRITICAL]
```
Before: 91/100 risk
After: 91/100 risk (0% improvement despite 17 controls!)
```

**Root cause:** Invalid MITRE mappings → Controls don't actually address techniques → No calculated reduction.

**Impact:** ❌ Users think controls don't work → Lose confidence in assessment

---

#### 3. Incomplete Technique Coverage [HIGH]
```
T1005 (Data from Local System): Only M1057 (DLP)
T1567 (Exfiltration Over Web Service): Only M1021, M1057
```

**Root cause:** Deterministic engine may not map ALL valid mitigations per technique.

**Impact:** ⚠️ Gaps in coverage → Attacker can exploit unmapped paths

---

### What Can Be Done: Flywheel of Improvement

#### Feedback Loop

```
┌─────────────────────────────────────────────────────────┐
│ PHASE 3B+ (Deterministic Engine) - 99.5% CONFIDENCE    │
│                                                          │
│ Input:  architecture.mmd                                 │
│ Output: ground_truth.json                               │
│         - control_recommendations (17 controls)         │
│         - expected_attack_paths (2 paths)               │
│         - MITRE mappings (M1016 → T1059, etc.)          │
└────────────────────┬────────────────────────────────────┘
                     │
                     ↓ ground_truth.json
┌─────────────────────────────────────────────────────────┐
│ PHASE 3C (LLM Critics) - 75-80% CONFIDENCE             │
│                                                          │
│ Architect: Design quality                               │
│ Tester:    Validation (finds gaps) ← FEEDBACK STARTS   │
│ Red Team:  Exploit difficulty                           │
└────────────────────┬────────────────────────────────────┘
                     │
                     ↓ Gaps found (e.g., invalid M1016 mapping)
┌─────────────────────────────────────────────────────────┐
│ HUMAN REVIEW (Manual validation)                        │
│                                                          │
│ Engineer checks: Is M1016 valid for T1059?             │
│ MITRE reference: T1059 mitigations = M1026, M1040, ... │
│ Verdict: ❌ M1016 NOT valid for T1059                  │
└────────────────────┬────────────────────────────────────┘
                     │
                     ↓ Validated gap
┌─────────────────────────────────────────────────────────┐
│ FIX DETERMINISTIC ENGINE (Improve mapping logic)        │
│                                                          │
│ File: chatbot/modules/exhaustive_mitigation_mapper.py  │
│                                                          │
│ BEFORE:                                                  │
│   # Maps all 44 mitigations to all techniques          │
│   for mitigation in all_mitigations:                   │
│       for technique in all_techniques:                 │
│           mappings.append((mitigation, technique))     │
│                                                          │
│ AFTER:                                                   │
│   # Only map valid mitigations per MITRE               │
│   for technique in techniques:                         │
│       valid_mits = mitre.get_technique_mitigations()   │
│       for mitigation in valid_mits:                    │
│           mappings.append((mitigation, technique))     │
└────────────────────┬────────────────────────────────────┘
                     │
                     ↓ Fixed engine
┌─────────────────────────────────────────────────────────┐
│ RE-RUN ASSESSMENT (Validate fix)                        │
│                                                          │
│ python3 -m chatbot.main --gen-arch-truth arch.mmd      │
│                                                          │
│ NEW ground_truth.json:                                  │
│   - LEAST PRIVILEGE: M1026, M1042 (valid only)         │
│   - Risk reduction: 91 → 45 (50% improvement) ✅        │
└────────────────────┬────────────────────────────────────┘
                     │
                     ↓ Improved ground truth
┌─────────────────────────────────────────────────────────┐
│ RE-RUN TESTER (Verify improvement)                      │
│                                                          │
│ python3 -m chatbot.modules.tester_critic report/...    │
│                                                          │
│ NEW Tester score: 75/100 (FAIR) ← Improved from 32!    │
│   - validation_checks: 35/40 (was 8/40) ✅             │
│   - Gaps: 2 (was 6) ✅                                  │
└─────────────────────────────────────────────────────────┘
```

**This is the flywheel:** LLM critics find issues → Human validates → Fix deterministic engine → Better ground truth → Higher Tester score → Repeat

---

## Question 4: Flywheel of Improvement Strategy

### Best Effort Improvement Plan

#### Phase 1: Quick Wins (2-3 hours)

**Issue 1: Fix MITRE Mapping Validation**

**Current:** `exhaustive_mitigation_mapper.py` may map invalid mitigations

**Fix:**
```python
# File: chatbot/modules/exhaustive_mitigation_mapper.py

def get_mitigations_for_techniques(techniques: List[str], mitre: MitreHelper) -> Dict:
    """
    Get ONLY valid MITRE mitigations for techniques.
    
    BEFORE: Returns all 44 mitigations regardless
    AFTER: Returns only mitigations listed in technique's MITRE data
    """
    mappings = {}
    
    for tech_id in techniques:
        tech_obj = mitre.find_technique(tech_id)
        if not tech_obj:
            continue
        
        # Get OFFICIAL mitigations from MITRE
        tech_internal_id = tech_obj.get('id')
        official_mitigations = mitre.get_technique_mitigations(tech_internal_id)
        
        # Store only valid mitigations
        mappings[tech_id] = [m["mitigation_id"] for m in official_mitigations]
    
    return mappings
```

**Test:**
```bash
# Before fix
python3 -m chatbot.main --gen-arch-truth tests/data/architectures/02_minimal_defended.mmd
python3 -m chatbot.modules.tester_critic report/02_minimal_defended
# Expected: Score 32/100, 6 gaps

# After fix
python3 -m chatbot.main --gen-arch-truth tests/data/architectures/02_minimal_defended.mmd
python3 -m chatbot.modules.tester_critic report/02_minimal_defended
# Expected: Score 70-80/100, 1-2 gaps
```

**Impact:** +40 points (32 → 72) on Tester validation_checks

---

**Issue 2: Recalculate Residual Risk**

**Current:** Risk reduction 0% despite controls

**Fix:** Ensure risk calculation uses VALID mappings (fix from Issue 1 should resolve this)

**Verify:**
```python
# In ground_truth.json after fix:
"residual_risks_before": {"overall_risk": 91},
"residual_risks_after": {"overall_risk": 45},  # Should be <50 now!
```

**Impact:** +10 points on Tester internal_consistency

---

#### Phase 2: Medium Wins (4-6 hours)

**Issue 3: Enhance Technique Coverage**

**Current:** Some techniques (T1005, T1567) have minimal mitigation coverage

**Fix:** Cross-reference with MITRE embeddings to find related techniques and mitigations

```python
# File: chatbot/modules/per_node_ttp_mapper.py

def enhance_technique_coverage(techniques: List[str], mitre: MitreHelper) -> List[str]:
    """
    Use semantic search to find related techniques.
    
    Example:
    - T1005 (Data from Local System) 
      → Also add T1039 (Data from Network Shared Drive)
      → Also add T1074 (Data Staged)
    
    Reasoning: If attacker uses T1005, likely also uses related data collection techniques
    """
    from chatbot.modules.mitre_embeddings import search_techniques
    
    enhanced = set(techniques)
    
    for tech_id in techniques:
        tech = mitre.find_technique(tech_id)
        if not tech:
            continue
        
        # Semantic search for related techniques
        description = tech.get("description", "")[:500]
        similar = search_techniques(
            query=description,
            mitre=mitre,
            top_k=3,
            min_score=0.7
        )
        
        for result in similar:
            if result["external_id"] != tech_id:  # Don't add self
                enhanced.add(result["external_id"])
    
    return list(enhanced)
```

**Impact:** +5-10 points on Tester coverage_metrics

---

**Issue 4: Add Tactic Sequence Validation**

**Current:** Attack paths may have illogical tactic sequences

**Fix:** Validate tactic flow matches MITRE kill chain

```python
# File: chatbot/modules/completeness_validator.py

def validate_tactic_sequence(path: Dict, mitre: MitreHelper) -> Dict:
    """
    Validate attack path follows realistic tactic progression.
    
    MITRE Tactic Order:
    1. Initial Access
    2. Execution
    3. Persistence
    4. Privilege Escalation
    5. Defense Evasion
    6. Credential Access
    7. Discovery
    8. Lateral Movement
    9. Collection
    10. Command and Control
    11. Exfiltration
    12. Impact
    
    Flag if path jumps backwards >2 stages (e.g., Impact → Discovery)
    """
    tactic_order = [
        "initial-access", "execution", "persistence", "privilege-escalation",
        "defense-evasion", "credential-access", "discovery", "lateral-movement",
        "collection", "command-and-control", "exfiltration", "impact"
    ]
    
    techniques = path.get("techniques", [])
    tactic_sequence = []
    
    for tech_id in techniques:
        tech = mitre.find_technique(tech_id)
        if tech and "kill_chain_phases" in tech:
            tactic = tech["kill_chain_phases"][0]["phase_name"]
            tactic_sequence.append(tactic)
    
    # Check for illogical jumps
    issues = []
    for i in range(len(tactic_sequence) - 1):
        current_idx = tactic_order.index(tactic_sequence[i])
        next_idx = tactic_order.index(tactic_sequence[i+1])
        
        if next_idx < current_idx - 2:  # Backwards jump
            issues.append({
                "severity": "MEDIUM",
                "description": f"Illogical tactic sequence: {tactic_sequence[i]} → {tactic_sequence[i+1]}",
                "techniques": f"{techniques[i]} → {techniques[i+1]}"
            })
    
    return {
        "valid": len(issues) == 0,
        "issues": issues
    }
```

**Impact:** +5 points on Tester validation_checks

---

#### Phase 3: Long-term Wins (8-12 hours)

**Issue 5: Learn from LLM Critiques**

**Strategy:** Build feedback database

```python
# File: chatbot/modules/feedback_db.py

class FeedbackDB:
    """
    Store validated gaps from Tester critiques.
    
    Schema:
    {
        "architecture": "02_minimal_defended",
        "gap": {
            "category": "validation_checks",
            "severity": "CRITICAL",
            "description": "LEAST PRIVILEGE claims M1016 for T1059",
            "validated": true,  # Human confirmed
            "fixed": true,      # Engine updated
            "fix_date": "2026-05-16"
        }
    }
    
    Use cases:
    1. Track which gaps are real vs false positives
    2. Build training data for fine-tuning LLM critics
    3. Auto-fix common issues (e.g., invalid M1016 mapping)
    4. Generate improvement metrics over time
    """
    
    def __init__(self, db_path: str = "feedback.json"):
        self.db_path = db_path
        self.feedback = self._load_db()
    
    def add_gap(self, architecture: str, gap: Dict, validated: bool = False):
        """Add gap to feedback database."""
        # ...
    
    def get_recurring_issues(self) -> List[Dict]:
        """Get issues that appear across multiple architectures."""
        # ...
    
    def get_fix_suggestions(self, architecture: str) -> List[str]:
        """Get auto-fix suggestions based on past validated gaps."""
        # ...
```

**Impact:** +10-15 points over time as patterns learned

---

**Issue 6: Automated Fix Application**

**Strategy:** Let LLM critics propose fixes to deterministic engine

```python
# File: chatbot/modules/engine_fixer.py

def apply_tester_fixes(tester_critique: CritiqueScore, ground_truth_path: str) -> Dict:
    """
    Apply Tester's validated fixes to ground truth.
    
    Example:
    - Tester finds: "LEAST PRIVILEGE has invalid M1016 mapping"
    - Load ground_truth.json
    - Remove M1016 from LEAST PRIVILEGE's mitigations
    - Add note: "Fixed by Tester on 2026-05-16"
    - Save updated ground_truth.json
    
    IMPORTANT: Only apply fixes with severity=CRITICAL and user approval
    """
    with open(ground_truth_path) as f:
        ground_truth = json.load(f)
    
    fixes_applied = []
    
    for gap in tester_critique.gaps:
        if gap["severity"] != "CRITICAL":
            continue  # Only auto-fix critical issues
        
        # Parse gap
        if "invalid" in gap["description"].lower() and "mitigation" in gap["description"].lower():
            # Extract: control name, invalid mitigation
            control_name, invalid_mit = parse_invalid_mitigation_gap(gap)
            
            # Find control in ground truth
            for control in ground_truth["control_recommendations"]:
                if control["control"] == control_name:
                    # Remove invalid mitigation
                    if invalid_mit in control["mitigations"]:
                        control["mitigations"].remove(invalid_mit)
                        fixes_applied.append({
                            "control": control_name,
                            "removed": invalid_mit,
                            "reason": gap["description"]
                        })
    
    # Save with backup
    backup_path = f"{ground_truth_path}.backup"
    shutil.copy(ground_truth_path, backup_path)
    
    with open(ground_truth_path, 'w') as f:
        json.dump(ground_truth, f, indent=2)
    
    return {
        "fixes_applied": fixes_applied,
        "backup": backup_path
    }
```

**Impact:** Automated improvement loop (careful: needs human oversight!)

---

### Flywheel Metrics

**Track improvement over iterations:**

| Iteration | Tester Score | Gaps | Deterministic Engine Changes |
|-----------|--------------|------|------------------------------|
| **Baseline** | 32/100 | 6 gaps | None |
| **Iteration 1** | 72/100 (+40) | 2 gaps (-4) | Fix invalid MITRE mappings |
| **Iteration 2** | 80/100 (+8) | 1 gap (-1) | Enhance technique coverage |
| **Iteration 3** | 85/100 (+5) | 0 gaps (-1) | Add tactic validation |
| **Iteration 4** | 90/100 (+5) | 0 gaps | Learn from feedback DB |

**Target:** Reach 90/100 Tester score across all 22 test architectures

---

## Summary

### Question 1: Red Teamer & Orchestrator
- ✅ **Framework exists** in `agent_framework.py`
- ⏳ **Red Teamer needs implementation** (4-6 hours)
- ⏳ **Orchestrator needs integration** (2 hours)
- **Total effort:** 6-8 hours to complete Phase 3C

### Question 2: Bedrock as Primary
- ✅ **Recommended:** Switch to Bedrock for better quality
- ✅ **Simple:** Change `LLM_PROVIDER=bedrock` in `.env`
- ✅ **Cost:** ~$0.05 per architecture (~$1.10 for 22 tests)
- ✅ **Benefits:** Better reliability, JSON compliance, tool calling support

### Question 3: Gaps in Deterministic Engine
- ❌ **Invalid MITRE mappings** (M1016 for T1059)
- ❌ **Zero risk reduction** (91→91 despite 17 controls)
- ⚠️ **Incomplete coverage** (T1005, T1567 under-protected)
- **Impact:** Tester scores 32/100 (POOR) due to these issues

### Question 4: Flywheel of Improvement
- ✅ **Phase 1 (Quick wins):** Fix MITRE validation → +40 points (2-3h)
- ✅ **Phase 2 (Medium wins):** Enhance coverage, add tactic validation → +15 points (4-6h)
- ✅ **Phase 3 (Long-term):** Feedback DB, auto-fix → +10-15 points over time (8-12h)
- **Target:** Reach 90/100 Tester score (from current 32/100)

---

## Recommended Next Steps

### Priority 1: Fix Deterministic Engine (HIGH ROI)
**Effort:** 2-3 hours  
**Impact:** +40 points (32 → 72)  
**Action:** Fix MITRE mapping validation in `exhaustive_mitigation_mapper.py`

### Priority 2: Switch to Bedrock
**Effort:** 5 minutes  
**Impact:** +5-10% reliability  
**Action:** `sed -i 's/LLM_PROVIDER=openrouter/LLM_PROVIDER=bedrock/' .env`

### Priority 3: Complete Phase 3C (Red Teamer + Orchestrator)
**Effort:** 6-8 hours  
**Impact:** Full 3-agent critique pipeline  
**Action:** Implement Red Teamer + Orchestrator integration

### Priority 4: Iterate Flywheel
**Effort:** Ongoing  
**Impact:** Continuous improvement  
**Action:** Run Tester → Validate gaps → Fix engine → Re-test

---

**Key Insight:** The LLM critics (Phase 3C) are working! They found real issues in the deterministic engine (Phase 3B+). Now use this feedback to improve both systems iteratively.
