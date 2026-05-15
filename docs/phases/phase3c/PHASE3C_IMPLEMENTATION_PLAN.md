# Phase 3C: Implementation Plan (Sequential A-Team)

**Status:** 🚀 **READY TO START** - MVP1 Complete (Architect), 13h Remaining  
**Date:** 2026-05-15  
**Approach:** Sequential (Architect → Tester → Red Team)  
**Artifacts:** 10 total (5 critical + 5 important)

---

## Executive Summary

### Current State
- ✅ **MVP1 Complete:** Architect agent working (370 lines, tested on 3 architectures)
- ✅ **MVP2 Spec Ready:** Tester agent spec documented (PHASE3C_MVP2_TESTER_SPEC.md)
- ✅ **Framework Ready:** agent_framework.py (502 lines, reusable)
- ⏳ **Remaining:** 13 hours to complete MVP2-MVP7

### Approach Decision
**Sequential (not Parallel)** - see [PHASE3C_APPROACH_ANALYSIS.md](PHASE3C_APPROACH_ANALYSIS.md)

**Rationale:**
1. **Context Accumulation:** Tester validates Architect's roadmap → Red Team attacks using both findings
2. **70% Code Reuse:** MVP1 Architect + framework already done
3. **Simpler Debugging:** Linear execution, easy to trace
4. **Narrative Quality:** Report reads naturally (design → test → attack)

**Trade-off:** 6-9 min execution vs 3-4 min parallel (acceptable for MVP)

### Artifacts Structure
**10 Artifacts Total** - see [PHASE3C_ARTIFACT_STRUCTURE.md](PHASE3C_ARTIFACT_STRUCTURE.md)

**Tier 1: Critical (80% confidence)** - from ground_truth.json
1. Attack Paths (per-node techniques)
2. Control Recommendations (hop analysis)
3. Residual Risk (BEFORE/AFTER)
4. Validation Results (6 checks)
5. RAPIDS Assessment (6 categories)

**Tier 2: Important (22% confidence)** - from report files
6. before.mmd (original architecture visual)
7. after.mmd (architecture + controls visual)
8. 02_technical_report.md (detailed analysis)
9. 01_executive_summary.md (business summary)
10. 03_action_plan.md (implementation roadmap)

### Success Criteria
- ✅ All 10 artifacts extracted and used by agents
- ✅ Tester validates Architect's improvement_roadmap
- ✅ Red Team uses Architect + Tester findings
- ✅ Final confidence: 99.5% ± 30% (69.5% to 100%)
- ✅ Execution time: 6-9 minutes (acceptable)
- ✅ Cross-references in reports ("Tester confirmed Architect Priority 1")

---

## Architecture Overview

### Sequential Flow

```
┌─────────────────────────────────────────────┐
│ INPUT: Report Directory                     │
│ - ground_truth.json                         │
│ - before.mmd, after.mmd                     │
│ - 01_executive_summary.md                   │
│ - 02_technical_report.md                    │
│ - 03_action_plan.md                         │
└─────────────────┬───────────────────────────┘
                  │
                  ↓
┌─────────────────────────────────────────────┐
│ PHASE 1: Artifact Extractor (2h)            │
│ - Parse 10 artifacts                        │
│ - Build indexes (node→paths, control→paths) │
│ - Validate completeness                     │
└─────────────────┬───────────────────────────┘
                  │
                  ↓
┌─────────────────────────────────────────────┐
│ PHASE 2: Enhanced Architect (2.5h)          │
│ - Critique all 10 artifacts                 │
│ - Generate improvement_roadmap              │
│ - Output: 04_architect_critique.json        │
└─────────────────┬───────────────────────────┘
                  │
                  ↓ (improvement_roadmap)
┌─────────────────────────────────────────────┐
│ PHASE 3: Tester Agent (2h)                  │
│ - Validate using Architect roadmap          │
│ - Execute verification_method checks        │
│ - Output: 05_tester_critique.json           │
└─────────────────┬───────────────────────────┘
                  │
                  ↓ (validation_results)
┌─────────────────────────────────────────────┐
│ PHASE 4: Red Team Agent (3h)                │
│ - Attack using Architect + Tester findings  │
│ - Test control bypasses                     │
│ - Output: 06_red_team_critique.json         │
└─────────────────┬───────────────────────────┘
                  │
                  ↓
┌─────────────────────────────────────────────┐
│ PHASE 5: Sequential Orchestrator (1h)       │
│ - Aggregate scores                          │
│ - Calculate final confidence                │
│ - Generate validation report                │
└─────────────────┬───────────────────────────┘
                  │
                  ↓
┌─────────────────────────────────────────────┐
│ OUTPUT: Enhanced Reports                    │
│ - Final confidence: 99.5% ± agents          │
│ - Validation report with cross-references   │
│ - Agent critique JSONs                      │
└─────────────────────────────────────────────┘
```

### Confidence Calculation

```python
final_confidence = deterministic_baseline + tier2_bonus + agent_adjustments

Where:
- deterministic_baseline = 0.995 (99.5% from Phase 3B+)
- tier2_bonus = 0 to 0.22 (22% if all 5 Tier 2 files present)
- agent_adjustments = ±0.30 (±10% per agent)
  - Architect: (score - 50) / 500  (±0.10)
  - Tester:    (score - 50) / 500  (±0.10)
  - Red Team:  (50 - score) / 500  (±0.10, inverted - lower exploit = better)

Range: 69.5% to 100% (clamped)
```

---

## Implementation Phases (13 Hours)

### Phase 1: Artifact Extractor (2 hours)

**Goal:** Extract and validate all 10 artifacts from report directory.

**File:** `chatbot/modules/artifact_extractor.py` (NEW)

**Tasks:**
1. Parse Tier 1 artifacts from ground_truth.json (1h)
   - Extract 5 artifacts with validation
   - Build indexes (node_to_paths, technique_to_paths, control_to_techniques)
   - Fail fast if any Tier 1 artifact missing

2. Parse Tier 2 artifacts from report files (0.5h)
   - Read before.mmd, after.mmd
   - Read 3 markdown reports
   - Warn if any Tier 2 artifact missing (don't fail)

3. Create ArtifactSet dataclass (0.5h)
   - Structured representation with indexes
   - Helper methods for agent queries
   - Completeness tracking

**Key Functions:**
```python
class ArtifactExtractor:
    @staticmethod
    def extract_all(report_dir: str, ground_truth: Dict) -> Dict:
        """
        Extract 10 artifacts from report directory.
        
        Returns: {
            "tier1_critical": {...},  # 5 artifacts from JSON
            "tier2_important": {...}, # 5 artifacts from files
            "completeness": {...}
        }
        """
    
    @staticmethod
    def _extract_attack_paths(gt: Dict) -> Dict:
        """
        Extract Artifact 1 with indexes.
        
        Returns: {
            "paths": [...],
            "count": int,
            "node_to_paths": Dict[str, List[int]],
            "technique_to_paths": Dict[str, List[int]]
        }
        """
    
    @staticmethod
    def _extract_controls(gt: Dict) -> Dict:
        """
        Extract Artifact 2 with indexes.
        
        Returns: {
            "controls": [...],
            "count": int,
            "control_to_paths": Dict[str, List[int]],
            "control_to_techniques": Dict[str, List[str]]
        }
        """
```

**Testing:**
- Test on: 02_minimal_defended (all files present)
- Test on: incomplete report (missing after.mmd)
- Validate indexes are correct

**Success Criteria:**
- [ ] Extracts all 10 artifacts successfully
- [ ] Indexes are accurate (node_to_paths, etc.)
- [ ] Fails fast if Tier 1 missing
- [ ] Warns if Tier 2 missing (doesn't fail)

---

### Phase 2: Enhanced Architect (2.5 hours)

**Goal:** Enhance existing Architect to critique all 10 artifacts.

**File:** `chatbot/modules/architect_critic.py` (ENHANCE EXISTING)

**Tasks:**
1. Update prompt to include Tier 2 artifacts (1h)
   - Add before.mmd visual context
   - **CRITICAL:** Add after.mmd validation (check control completeness)
   - Add technical report cross-check
   - Add executive summary ROI validation
   - Add action plan phasing validation

2. Enhance rubric to 100 points (0.5h)
   - Tier 1: 80 points (Artifacts 1-5)
   - Tier 2: 20 points (Artifacts 6-10)
   - **Critical:** after.mmd completeness (10 pts)

3. Update _format_prompt method (0.5h)
   - Use ArtifactExtractor output
   - Format all 10 artifacts clearly
   - Add artifact labels in prompt

4. Add after.mmd validation logic (0.5h)
   - Parse after.mmd to count NEW_* nodes
   - Compare with control_recommendations count
   - Flag gaps as HIGH severity

**Key Changes:**
```python
def _format_prompt(self, artifacts: Dict) -> str:
    """
    Format prompt with ALL 10 artifacts.
    """
    tier1 = artifacts["tier1_critical"]
    tier2 = artifacts["tier2_important"]
    
    prompt = f"""
You are a security architect reviewing a threat assessment.

## TIER 1: CRITICAL ARTIFACTS (80% confidence weight)

### ARTIFACT 1: ATTACK PATHS ({tier1['artifact_1_attack_paths']['count']} paths)
{self._format_attack_paths(tier1['artifact_1_attack_paths'])}

### ARTIFACT 2: CONTROL RECOMMENDATIONS ({tier1['artifact_2_controls']['count']} controls)
{self._format_controls(tier1['artifact_2_controls'])}

[... artifacts 3-5 ...]

## TIER 2: IMPORTANT ARTIFACTS (22% confidence weight)

### ARTIFACT 6: ORIGINAL ARCHITECTURE (before.mmd)
{tier2['artifact_6_before_mmd']}

### ARTIFACT 7: IMPROVED ARCHITECTURE (after.mmd)
{tier2['artifact_7_after_mmd']}

**CRITICAL CHECK:** Validate after.mmd includes ALL controls from Artifact 2.

Expected controls: {tier1['artifact_2_controls']['count']}
Controls in after.mmd: [COUNT "NEW_*" nodes]

If mismatch → HIGH severity gap.

[... artifacts 8-10 ...]

## YOUR CRITIQUE
Score each artifact (100 points total):
- Artifacts 1-5 (Tier 1): 80 points
- Artifacts 6-10 (Tier 2): 20 points

Provide improvement_roadmap with verification_method for Tester.
"""
    
    return prompt
```

**Testing:**
- Test on: 02_minimal_defended (should score high)
- Test on: test_flawed_assessment (should catch gaps)
- Validate after.mmd completeness check works

**Success Criteria:**
- [ ] Critiques all 10 artifacts
- [ ] after.mmd completeness validated
- [ ] improvement_roadmap includes verification_method
- [ ] Score reflects Tier 1 (80%) + Tier 2 (20%) weighting

---

### Phase 3: Tester Agent (2 hours)

**Goal:** Build Tester agent that validates using Architect's roadmap.

**File:** `chatbot/modules/tester_critic.py` (NEW)

**Reference:** [PHASE3C_MVP2_TESTER_SPEC.md](PHASE3C_MVP2_TESTER_SPEC.md)

**Tasks:**
1. Create TesterCritic class (0.5h)
   - Inherit from CriticAgent
   - Define TESTER_RUBRIC (40+30+20+10)
   - Primary focus: Artifact 4 (validation_report)

2. Implement verification_method executor (1h)
   - Parse Architect roadmap items
   - Execute verification checks (deterministic)
   - Examples: "Count techniques", "Check priorities", "Validate rationale"

3. Format Tester prompt (0.5h)
   - Include Architect roadmap
   - Include verification results
   - Request cross-references

**Key Functions:**
```python
class TesterCritic(CriticAgent):
    def critique(self, artifacts: Dict, architect_result: CritiqueScore) -> CritiqueScore:
        """
        Validate assessment using Architect's roadmap.
        """
        # Execute verification methods
        verification_results = []
        for item in architect_result.improvement_roadmap:
            result = self._execute_verification(
                item["verification_method"],
                artifacts,
                item
            )
            verification_results.append(result)
        
        # Format prompt with results
        prompt = self._format_tester_prompt(
            artifacts,
            architect_result,
            verification_results
        )
        
        # Call LLM
        llm_response = self.llm_client.generate(...)
        return self._parse_critique(llm_response)
    
    def _execute_verification(self, method: str, artifacts: Dict, item: Dict) -> Dict:
        """
        Execute verification_method from Architect roadmap.
        
        Examples:
        - "Count techniques - should be 8+"
        - "Verify priorities align with RAPIDS"
        - "Check rationale consistency"
        """
        if "count" in method.lower() and "technique" in method.lower():
            # Count techniques
            total = sum(len(p["techniques"]) for p in artifacts["tier1_critical"]["artifact_1_attack_paths"]["paths"])
            expected = 8
            return {
                "method": method,
                "status": "PASS" if total >= expected else "FAIL",
                "actual": total,
                "expected": expected,
                "architect_priority": item["priority"]
            }
        
        # Add more patterns...
```

**Testing:**
- Test on: 02_minimal_defended + Architect result
- Validate verification_method execution
- Check cross-references to Architect

**Success Criteria:**
- [ ] Executes Architect roadmap verifications
- [ ] Cross-references Architect findings
- [ ] Score on good assessment: 70-85/100
- [ ] Score on flawed assessment: 30-45/100

---

### Phase 4: Red Team Agent (3 hours)

**Goal:** Build Red Team agent that attacks the assessment.

**File:** `chatbot/modules/red_team_critic.py` (NEW)

**Tasks:**
1. Create RedTeamCritic class (0.5h)
   - Inherit from CriticAgent
   - Define RED_TEAM_RUBRIC (40+30+20+10)
   - **Inverted scoring:** Lower = better defense

2. Implement path selection logic (1h)
   - Select weakest path from Artifact 1
   - Use Architect gaps to inform selection
   - Use Tester findings to prioritize

3. Implement control bypass testing (1h)
   - Test each control for bypass scenarios
   - Use Artifact 2 (control-technique mapping)
   - Generate realistic bypass methods

4. Format Red Team prompt (0.5h)
   - Include Architect + Tester findings
   - Request attack scenarios
   - Request bypass difficulty assessments

**Key Functions:**
```python
class RedTeamCritic(CriticAgent):
    def critique(
        self,
        artifacts: Dict,
        architect_result: CritiqueScore,
        tester_result: CritiqueScore
    ) -> CritiqueScore:
        """
        Red team attack using all findings.
        """
        # Select weakest path
        weakest_path = self._select_weakest_path(
            artifacts["tier1_critical"]["artifact_1_attack_paths"],
            architect_result.gaps,
            tester_result.gaps
        )
        
        # Format prompt
        prompt = self._format_red_team_prompt(
            artifacts,
            weakest_path,
            architect_gaps=architect_result.gaps,
            tester_gaps=tester_result.gaps
        )
        
        # Call LLM
        llm_response = self.llm_client.generate(...)
        return self._parse_critique(llm_response)
    
    def _select_weakest_path(
        self,
        attack_paths: Dict,
        architect_gaps: List[Dict],
        tester_gaps: List[Dict]
    ) -> Dict:
        """
        Select path with highest exploit likelihood.
        
        Prioritize:
        1. Paths flagged by both Architect and Tester
        2. Paths with highest risk_score
        3. Paths with fewest controls
        """
        # Score each path
        path_scores = []
        for path_id, path in enumerate(attack_paths["paths"]):
            score = self._calculate_exploit_score(
                path,
                architect_gaps,
                tester_gaps
            )
            path_scores.append((path_id, score))
        
        # Return highest score (most exploitable)
        weakest_id = max(path_scores, key=lambda x: x[1])[0]
        return attack_paths["paths"][weakest_id]
```

**Testing:**
- Test on: 02_minimal_defended + Architect + Tester results
- Validate path selection logic
- Check bypass scenarios are realistic

**Success Criteria:**
- [ ] Selects weakest path intelligently
- [ ] Control bypass scenarios realistic
- [ ] Score on good defense: 20-30/100 (low exploit = good)
- [ ] Score on weak defense: 60-80/100 (high exploit = bad)

---

### Phase 5: Sequential Orchestrator (1 hour)

**Goal:** Orchestrate sequential execution of 3 agents.

**File:** `chatbot/modules/sequential_orchestrator.py` (NEW)

**Tasks:**
1. Create SequentialOrchestrator class (0.5h)
   - Initialize 3 agents (Architect, Tester, Red Team)
   - Sequential execution with context passing

2. Implement run_critique method (0.5h)
   - Stage 1: Architect (pass artifacts)
   - Stage 2: Tester (pass artifacts + Architect result)
   - Stage 3: Red Team (pass artifacts + Architect + Tester results)
   - Aggregate results

**Key Functions:**
```python
class SequentialOrchestrator:
    def __init__(self):
        self.architect = ArchitectCritic(...)
        self.tester = TesterCritic(...)
        self.red_team = RedTeamCritic(...)
    
    def run_critique(self, report_dir: str, ground_truth: Dict) -> Dict:
        """
        Sequential: Architect → Tester → Red Team
        """
        logger.info("🚀 Starting Sequential A-Team Critique")
        
        # Extract artifacts
        artifacts = ArtifactExtractor.extract_all(report_dir, ground_truth)
        
        # Stage 1: Architect
        logger.info("  [1/3] Running Architect...")
        architect_result = self.architect.critique(artifacts)
        logger.info(f"  ✅ Architect complete - Score: {architect_result.score}/100")
        
        # Stage 2: Tester (uses Architect roadmap)
        logger.info("  [2/3] Running Tester (validating Architect roadmap)...")
        tester_result = self.tester.critique(artifacts, architect_result)
        logger.info(f"  ✅ Tester complete - Score: {tester_result.score}/100")
        
        # Stage 3: Red Team (uses both)
        logger.info("  [3/3] Running Red Team (attacking assessment)...")
        red_team_result = self.red_team.critique(artifacts, architect_result, tester_result)
        logger.info(f"  ✅ Red Team complete - Exploit Score: {red_team_result.score}/100")
        
        # Calculate final confidence
        final_confidence = self._calculate_confidence(
            deterministic=ground_truth["validation_report"]["confidence_adjustments"]["final"],
            tier2_present=artifacts["completeness"]["tier2"],
            architect=architect_result,
            tester=tester_result,
            red_team=red_team_result
        )
        
        logger.info(f"✅ A-Team Complete - Final Confidence: {final_confidence['final_confidence']:.1%}")
        
        return {
            "approach": "sequential",
            "final_confidence": final_confidence,
            "architect": architect_result.to_dict(),
            "tester": tester_result.to_dict(),
            "red_team": red_team_result.to_dict()
        }
```

**Testing:**
- Test end-to-end on 02_minimal_defended
- Validate context passing (Tester gets Architect roadmap)
- Check final confidence calculation

**Success Criteria:**
- [ ] Agents run sequentially (not parallel)
- [ ] Context passed between agents
- [ ] Final confidence calculated correctly
- [ ] Execution time: 6-9 minutes

---

### Phase 6: CLI Integration (1 hour)

**Goal:** Add CLI command to run A-Team critique.

**File:** `chatbot/main.py` (MODIFY)

**Tasks:**
1. Add --gen-arch-truth-team flag (0.5h)
2. Wire up SequentialOrchestrator (0.25h)
3. Save outputs to report directory (0.25h)

**CLI Usage:**
```bash
# Deterministic only (existing)
python3 -m chatbot.main --gen-arch-truth architecture.mmd

# Deterministic + A-Team critique (NEW)
python3 -m chatbot.main --gen-arch-truth-team architecture.mmd
```

**Output:**
```
report/architecture_name/
├── ground_truth.json               (deterministic)
├── before.mmd                      (deterministic)
├── after.mmd                       (deterministic)
├── 01_executive_summary.md         (deterministic)
├── 02_technical_report.md          (deterministic)
├── 03_action_plan.md               (deterministic)
├── 04_architect_critique.json      (Agent 1 - NEW)
├── 05_tester_critique.json         (Agent 2 - NEW)
├── 06_red_team_critique.json       (Agent 3 - NEW)
├── 07_final_confidence.json        (Aggregated - NEW)
└── 08_validation_report.md         (Pass/Fail - NEW)
```

**Success Criteria:**
- [ ] CLI flag works
- [ ] All agent outputs saved
- [ ] Final confidence JSON generated
- [ ] Validation report generated

---

### Phase 7: Testing & Validation (1.5 hours)

**Goal:** Test on 3 architectures, validate results.

**Tasks:**
1. Test on 02_minimal_defended (0.5h)
   - Should score high (good assessment)
   - Validate cross-references between agents
   - Check final confidence: 95-100%

2. Test on test_flawed_assessment (0.5h)
   - Should score low (flawed assessment)
   - Validate all 3 agents catch errors
   - Check final confidence: 70-85%

3. Test on 03_aws_3tier (0.5h)
   - Moderate complexity
   - Validate AWS-specific critiques
   - Check final confidence: 85-95%

**Validation Checklist:**
- [ ] All 10 artifacts extracted successfully
- [ ] Architect critiques all 10 artifacts
- [ ] Tester references Architect roadmap
- [ ] Red Team uses Architect + Tester findings
- [ ] Cross-references in reports
- [ ] Final confidence in expected range
- [ ] Execution time: 6-9 minutes

---

## Code Structure

```
chatbot/modules/
├── artifact_extractor.py           (NEW - Phase 1)
│   └── ArtifactExtractor class
│       ├── extract_all()
│       ├── _extract_attack_paths()
│       ├── _extract_controls()
│       └── _read_file()
│
├── architect_critic.py             (ENHANCE - Phase 2)
│   └── ArchitectCritic class
│       ├── critique()              (existing)
│       ├── _format_prompt()        (enhance - 10 artifacts)
│       └── _validate_after_mmd()   (NEW)
│
├── tester_critic.py                (NEW - Phase 3)
│   └── TesterCritic class
│       ├── critique()
│       ├── _execute_verification()
│       └── _format_tester_prompt()
│
├── red_team_critic.py              (NEW - Phase 4)
│   └── RedTeamCritic class
│       ├── critique()
│       ├── _select_weakest_path()
│       └── _format_red_team_prompt()
│
├── sequential_orchestrator.py      (NEW - Phase 5)
│   └── SequentialOrchestrator class
│       ├── run_critique()
│       └── _calculate_confidence()
│
└── agent_framework.py              (EXISTING - reuse)
    └── CriticAgent base class
```

---

## Timeline Summary

| Phase | Task | Hours | Status |
|-------|------|-------|--------|
| 0 | MVP1 (Architect) | 4 | ✅ COMPLETE |
| 1 | Artifact Extractor | 2 | 🚀 NEXT |
| 2 | Enhanced Architect | 2.5 | Pending |
| 3 | Tester Agent | 2 | Pending |
| 4 | Red Team Agent | 3 | Pending |
| 5 | Sequential Orchestrator | 1 | Pending |
| 6 | CLI Integration | 1 | Pending |
| 7 | Testing & Validation | 1.5 | Pending |
| **Total** | **17 hours** | **(4 done + 13 remaining)** |

---

## Success Criteria (Final)

### Artifact Utilization
- [ ] All 10 artifacts extracted (5 critical + 5 important)
- [ ] Architect critiques all 10 artifacts explicitly
- [ ] Tester validates Artifact 4 (validation_report) primarily
- [ ] Red Team uses Artifact 1 (attack_paths) for path selection
- [ ] after.mmd completeness validated by Architect

### Sequential Context Flow
- [ ] Tester receives Architect's improvement_roadmap
- [ ] Tester executes verification_method checks
- [ ] Red Team receives Architect + Tester findings
- [ ] Red Team selects weakest path using both inputs
- [ ] Report shows narrative flow (design → test → attack)

### Cross-Referencing
- [ ] Tester: "Verified Architect Priority 1: technique count increased"
- [ ] Red Team: "Attacking path flagged by Architect as weak"
- [ ] No duplicate findings (de-duplicated in report)

### Performance
- [ ] Total execution: 6-9 minutes (acceptable for MVP)
- [ ] Artifact extraction: <5 seconds
- [ ] Each agent: 1-3 minutes

### Confidence Accuracy
- [ ] Final confidence: 99.5% ± 30% (69.5% to 100%)
- [ ] Tier 2 bonus: +22% if all files present
- [ ] Agent adjustments justified in breakdown
- [ ] Good assessment: 95-100% confidence
- [ ] Flawed assessment: 70-85% confidence

---

## Risk Mitigation

### Risk 1: Artifact Extraction Fails
**Mitigation:** Fail fast with clear error message, show which artifact missing

### Risk 2: LLM Hallucination
**Mitigation:** 
- Architect validates after.mmd against ground_truth.json (deterministic check)
- Tester executes verification_method (deterministic checks)
- Cross-reference findings between agents

### Risk 3: Context Loss Between Agents
**Mitigation:**
- Pass full CritiqueScore objects (not just scores)
- Include improvement_roadmap, gaps, findings
- Log context passing for debugging

### Risk 4: Execution Too Slow
**Mitigation:**
- Accept 6-9 minutes for MVP
- Can optimize later (parallel mode as Option B)
- Cache LLM responses during development

---

## Next Steps

1. **Review this plan** (you are here)
2. **Start Phase 1:** Implement Artifact Extractor (2h)
3. **Iterate:** Complete Phases 2-7 sequentially
4. **Test:** Validate on 3 architectures
5. **Document:** Update CLAUDE.md with new CLI flag

---

## References

- [PHASE3C_MASTER_INDEX.md](PHASE3C_MASTER_INDEX.md) - Documentation index
- [PHASE3C_APPROACH_ANALYSIS.md](PHASE3C_APPROACH_ANALYSIS.md) - Sequential vs parallel decision
- [PHASE3C_ARTIFACT_STRUCTURE.md](PHASE3C_ARTIFACT_STRUCTURE.md) - 10-artifact specification
- [PHASE3C_MVP1_SUMMARY.md](PHASE3C_MVP1_SUMMARY.md) - MVP1 completion summary
- [PHASE3C_MVP2_TESTER_SPEC.md](PHASE3C_MVP2_TESTER_SPEC.md) - Tester implementation spec

---

**Document Version:** 1.0  
**Date:** 2026-05-15  
**Status:** Ready to Start (Phase 1)  
**Maintained by:** Claude Code  
**Next Review:** After Phase 1 complete
