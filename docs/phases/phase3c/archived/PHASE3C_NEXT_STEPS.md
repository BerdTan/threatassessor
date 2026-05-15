# Phase 3C: Next Steps & Confidence Enhancement

**Date:** 2026-05-15  
**Current Status:** MVP1 Complete (Architect Critic)  
**Next:** MVP2+ (Tester + Security Tester + Orchestrator)  
**Your Questions:** Input validation, multi-agent rigor, security tester depth

---

## Current State (MVP1 Complete)

### What We Have
✅ **Agent Framework** (`agent_framework.py`, 502 lines)
- CriticAgent base class (reusable)
- CritiqueScore with improvement_roadmap
- JSON parsing with normalization
- Tool support (disabled MVP1, ready for MVP2+)

✅ **Architect Critic** (`architect_critic.py`, 370 lines)
- 100-point rubric (40+30+20+10)
- Improvement roadmap with verification_method
- Tested on 3 architectures (23/100 flawed, 78/100 good)
- Catches contradictions, priority mismatches, technique gaps

✅ **Test Infrastructure**
- `tests/data/agent_test_cases/test_flawed_assessment.json` (3 planted errors)
- `scripts/agent_testing/test_architect.sh`
- All 3 flaws caught by Architect

### What We're Missing (Your Concerns)
❌ **Input Validation** - No pre-LLM checks on deterministic data completeness
❌ **Tester Agent** - Validates assessment quality using Architect roadmap
❌ **Security Tester Agent** - Red team adversarial validation
❌ **Orchestrator** - Sequences agents, aggregates scores, resolves conflicts
❌ **Architecture Improvement** - No after-llm.mmd generation
❌ **Multi-Agent Confidence** - No aggregation of all agent scores

---

## Your Questions & Solutions

### Q1: How to ensure deterministic assessment is TRULY sent to LLM?

**Current Gap:** No validation that `ground_truth.json` is complete before passing to agents.

**Solution: Pre-Agent Input Validation Module**

```python
# chatbot/modules/agent_input_validator.py (NEW)

class AgentInputValidator:
    """
    Validates that ground_truth.json has ALL required data before LLM critique.
    
    Raises: ValueError if data incomplete (fail fast)
    """
    
    REQUIRED_FIELDS = {
        "architecture": str,
        "attack_paths": list,
        "control_recommendations": list,
        "residual_risk": dict,
        "validation": dict,
        "confidence": dict
    }
    
    @staticmethod
    def validate_attack_paths(paths: List[Dict]) -> Dict[str, bool]:
        """
        Check attack paths have:
        - entry, target, path, techniques (basic)
        - per_node_techniques (Phase 3B+)
        - risk_score (residual risk)
        """
        checks = {
            "paths_present": len(paths) > 0,
            "basic_fields_complete": all([
                "entry" in p and "target" in p and "path" in p and "techniques" in p
                for p in paths
            ]),
            "per_node_techniques_mapped": all([
                "per_node_techniques" in p for p in paths
            ]),
            "risk_scores_calculated": all([
                "risk_score" in p for p in paths
            ])
        }
        return checks
    
    @staticmethod
    def validate_controls(controls: List[Dict]) -> Dict[str, bool]:
        """
        Check controls have:
        - Basic: control, priority, rationale
        - Phase 3B: dir_category, placement, _layered_defense
        - Phase 3B+: techniques, mitigations, attack_paths
        """
        checks = {
            "controls_present": len(controls) >= 10,  # Minimum threshold
            "basic_fields_complete": all([
                "control" in c and "priority" in c and "rationale" in c
                for c in controls
            ]),
            "dir_category_present": all([
                "dir_category" in c for c in controls
            ]),
            "placement_specified": all([
                "placement" in c for c in controls
            ]),
            "hop_analysis_present": all([
                "_layered_defense" in c and 
                len(c["_layered_defense"].get("hop_analysis", [])) > 0
                for c in controls
            ]),
            "technique_mapping_present": all([
                "techniques" in c and len(c["techniques"]) > 0
                for c in controls
            ]),
            "mitigation_mapping_present": all([
                "mitigations" in c for c in controls
            ]),
            "attack_path_coverage": all([
                "attack_paths" in c for c in controls
            ])
        }
        return checks
    
    @staticmethod
    def validate_residual_risk(residual: Dict) -> Dict[str, bool]:
        """
        Check residual risk has:
        - BEFORE/AFTER scores
        - Per-threat breakdown
        - Thresholds
        """
        checks = {
            "before_score_present": "current_risk" in residual,
            "after_score_present": "projected_risk" in residual,
            "reduction_calculated": "risk_reduction_percent" in residual,
            "thresholds_defined": "risk_thresholds" in residual,
            "per_threat_breakdown": "per_threat_risk" in residual
        }
        return checks
    
    @staticmethod
    def validate_validation_results(validation: Dict) -> Dict[str, bool]:
        """
        Check validation results have:
        - 6/6 checks run
        - Pass/fail results
        - Confidence score
        """
        checks = {
            "checks_run": validation.get("checks_total", 0) == 6,
            "results_present": "checks_passed" in validation,
            "confidence_calculated": "confidence" in validation
        }
        return checks
    
    @staticmethod
    def validate_ground_truth(ground_truth: Dict) -> Tuple[bool, Dict, List[str]]:
        """
        Full validation of ground_truth.json before passing to agents.
        
        Returns:
            (is_valid, validation_results, error_messages)
        
        Raises:
            ValueError if critical data missing
        """
        validation_results = {}
        errors = []
        
        # Check top-level fields
        for field, expected_type in AgentInputValidator.REQUIRED_FIELDS.items():
            if field not in ground_truth:
                errors.append(f"Missing required field: {field}")
            elif not isinstance(ground_truth[field], expected_type):
                errors.append(f"Field '{field}' has wrong type: expected {expected_type.__name__}")
        
        if errors:
            return False, {}, errors
        
        # Detailed checks
        validation_results["attack_paths"] = AgentInputValidator.validate_attack_paths(
            ground_truth["attack_paths"]
        )
        validation_results["controls"] = AgentInputValidator.validate_controls(
            ground_truth["control_recommendations"]
        )
        validation_results["residual_risk"] = AgentInputValidator.validate_residual_risk(
            ground_truth["residual_risk"]
        )
        validation_results["validation"] = AgentInputValidator.validate_validation_results(
            ground_truth["validation"]
        )
        
        # Collect failures
        for category, checks in validation_results.items():
            for check_name, passed in checks.items():
                if not passed:
                    errors.append(f"{category}.{check_name} FAILED")
        
        is_valid = len(errors) == 0
        
        return is_valid, validation_results, errors


# Usage in agent_framework.py
def run_architect_critique(ground_truth: Dict) -> CritiqueScore:
    """Run Architect agent with input validation."""
    
    # VALIDATE INPUT FIRST
    is_valid, validation_results, errors = AgentInputValidator.validate_ground_truth(ground_truth)
    
    if not is_valid:
        raise ValueError(
            f"Ground truth validation FAILED - cannot pass to LLM:\n" +
            "\n".join(f"  ❌ {err}" for err in errors) +
            "\n\nFix deterministic engine before running agents."
        )
    
    # Log what we're passing
    logger.info("✅ Ground truth validation PASSED - ready for LLM critique")
    logger.info(f"  - Attack paths: {len(ground_truth['attack_paths'])}")
    logger.info(f"  - Controls: {len(ground_truth['control_recommendations'])}")
    logger.info(f"  - Validation checks: {ground_truth['validation']['checks_passed']}/6")
    
    # NOW run agent
    agent = ArchitectCritic()
    return agent.critique(ground_truth)
```

**Confidence Impact:** +10% (ensures data completeness before LLM)

---

### Q2: How to validate LLM covers THOROUGH critic on threat model?

**Current Gap:** Architect rubric is 100 points, but doesn't deeply validate:
- Every node in each path analyzed
- Mitigation effectiveness proven
- Residual risk realistic
- Architecture improvements generate valid .mmd

**Solution: Enhance Architect + Add Dedicated Agents**

#### Enhancement 1: Architect Per-Node Analysis

```python
# Add to architect_critic.py

ARCHITECT_SYSTEM_PROMPT_ENHANCED = """
...existing prompt...

## CRITICAL: Per-Node Analysis Required

For EACH node in EACH attack path, validate:

1. **Techniques Mapped** (per_node_techniques field)
   - Entry node: Initial Access techniques (T1190, T1133, T1566)
   - Intermediate nodes: Privilege Escalation (T1068), Lateral Movement (T1021)
   - Target nodes: Impact (T1485, T1490), Exfiltration (T1041, T1048)

2. **Controls Applied** (_layered_defense.hop_analysis)
   - Check if hop has prevention/detect/isolate/respond
   - Validate control is EFFECTIVE for that node type
   - Example: WAF at WebServer hop (good), WAF at Database hop (wrong layer)

3. **SPOF Detection** (is_spof field in hop_analysis)
   - If hop is SPOF and has no resilience controls → HIGH severity gap
   - Example: Single firewall with no failover

## Scoring: Per-Node Coverage (NEW - 10 points)
- 10 pts: ALL nodes analyzed, techniques appropriate, controls match layer
- 7 pts: Most nodes analyzed, minor gaps
- 4 pts: Some nodes skipped, control placement issues
- 0 pts: Generic path analysis, no per-node detail

YOUR RESPONSE MUST INCLUDE:

### Per-Node Analysis Table

| Path | Node | Techniques | Controls | Gaps |
|------|------|------------|----------|------|
| #1 | WebServer | T1190, T1059 | WAF, rate limiting | ✓ Appropriate |
| #1 | Database | T1213, T1005 | least privilege | ⚠️ Missing backup (ransomware) |
| ... | ... | ... | ... | ... |

If ANY node is missing from this table → deduct 5 points (incomplete analysis).
"""
```

**Confidence Impact:** +5% (ensures every node validated)

#### Enhancement 2: Defense Effectiveness Agent (NEW)

**Purpose:** Validate that controls ACTUALLY mitigate the techniques they claim.

```python
# chatbot/modules/defense_effectiveness_critic.py (NEW)

DEFENSE_RUBRIC = {
    "mitigation_correctness": 40,  # Controls match techniques
    "placement_effectiveness": 30,  # Right layer/hop
    "defense_in_depth": 20,        # Layered (PREVENT→DETECT→ISOLATE→RESPOND)
    "resilience": 10               # SPOFs addressed
}

DEFENSE_SYSTEM_PROMPT = """
You are a defense architect validating control effectiveness.

## YOUR ROLE
For EACH control, prove it ACTUALLY mitigates the techniques claimed.

## INPUT: Control Recommendations
{control_recommendations_detailed}

## VALIDATION METHOD

### For EACH control:

1. **Mitigation Correctness Check**
   - Control: rate limiting
   - Techniques claimed: T1190 (Exploit Public-Facing Application)
   - Mitigations mapped: M1050 (Exploit Protection)
   - 
   - QUESTION: Does rate limiting actually prevent T1190?
   - ANSWER: ⚠️ PARTIAL - Prevents brute force but NOT exploit payloads
   - RECOMMENDATION: Add WAF (M1050 requires payload inspection, not just rate limiting)

2. **Placement Effectiveness Check**
   - Control: least privilege
   - Placement: At Database hop
   - Techniques: T1059 (Command and Scripting Interpreter)
   - 
   - QUESTION: Is Database hop the RIGHT place for least privilege?
   - ANSWER: ✗ TOO LATE - T1059 happens at WebServer, least privilege should be there too
   - RECOMMENDATION: Apply least privilege at WebServer hop (limit what WebServer can execute)

3. **Defense-in-Depth Check**
   - Path: Internet → WebServer → Database
   - Controls: rate limiting (PREVENT), logging (DETECT)
   - 
   - QUESTION: Are all 4 DIR categories covered?
   - ANSWER: ✗ MISSING ISOLATE and RESPOND
   - RECOMMENDATION: Add network segmentation (ISOLATE), add incident response playbook (RESPOND)

4. **Resilience Check**
   - Hop: WebServer → Database
   - SPOF: Yes (single firewall)
   - Resilience controls: None
   - 
   - QUESTION: Is SPOF mitigated?
   - ANSWER: ✗ NO - Single point of failure with no failover
   - RECOMMENDATION: Add redundant firewall or alternative control (network segmentation)

## SCORING (100 points)

### Mitigation Correctness (40 points)
- 40 pts: All controls correctly mitigate techniques
- 30 pts: 1-2 partial matches (e.g., rate limiting for T1190)
- 20 pts: 3-5 mismatches
- 0 pts: Controls don't match techniques

### Placement Effectiveness (30 points)
- 30 pts: All controls at optimal hops
- 20 pts: 1-2 suboptimal placements
- 10 pts: 3-5 wrong layers
- 0 pts: Random placement

### Defense-in-Depth (20 points)
- 20 pts: All paths have PREVENT/DETECT/ISOLATE/RESPOND
- 15 pts: All paths have 3/4 categories
- 10 pts: All paths have 2/4 categories
- 0 pts: Paths missing multiple categories

### Resilience (10 points)
- 10 pts: All SPOFs have resilience controls
- 7 pts: Most SPOFs covered
- 3 pts: Some SPOFs uncovered
- 0 pts: No resilience controls

## OUTPUT REQUIRED

### Control Effectiveness Issues (List)
```json
[
  {
    "control": "rate limiting",
    "issue": "PARTIAL mitigation - prevents brute force but not exploit payloads",
    "severity": "MEDIUM",
    "technique": "T1190",
    "recommendation": "Add WAF for payload inspection",
    "points_deducted": 5
  }
]
```

### Placement Improvements (List)
```json
[
  {
    "control": "least privilege",
    "current_placement": "At Database hop",
    "better_placement": "At WebServer hop (also)",
    "rationale": "T1059 happens at WebServer, need to limit execution there",
    "risk_reduction": "15%"
  }
]
```

### Defense-in-Depth Gaps (Per Path)
```json
{
  "path_1": {
    "present": ["PREVENT", "DETECT"],
    "missing": ["ISOLATE", "RESPOND"],
    "recommendations": ["network segmentation (ISOLATE)", "incident response (RESPOND)"]
  }
}
```

### Architecture Improvements (for after-llm.mmd)
```json
[
  {
    "type": "add_node",
    "node_id": "APIGateway",
    "node_label": "API Gateway",
    "layer": "network",
    "insert_between": ["Internet", "WebServer"],
    "controls_to_apply": ["MFA", "rate limiting", "WAF"],
    "risk_reduction": "20%",
    "rationale": "Centralizes authentication and input validation"
  }
]
```

## YOUR RESPONSE
[Provide scoring + detailed findings in JSON format above]
"""
```

**Confidence Impact:** +5% (validates control effectiveness)

---

### Q3: How to ensure Security Tester gives DEEPER critic on improvements?

**Current Gap:** No Security Tester agent yet (MVP1 only has Architect).

**Solution: Security Tester Agent with Adversarial Validation**

```python
# chatbot/modules/security_tester_critic.py (NEW)

SECURITY_TESTER_RUBRIC = {
    "exploit_feasibility": 40,     # Can attacker succeed?
    "control_bypass_difficulty": 30,  # How hard to bypass controls?
    "architecture_improvement_validation": 20,  # Does after-llm.mmd work?
    "residual_risk_realism": 10    # Is AFTER score achievable?
}

SECURITY_TESTER_SYSTEM_PROMPT = """
You are a red team pentester with MODERATE skill (NOT APT-level).

## YOUR ROLE
Find the WEAKEST attack path and attempt to BYPASS controls.

## ASSUMPTIONS
- You have: Internet access, moderate skill (Metasploit, Burp Suite), some insider knowledge (phishing)
- You DON'T have: Zero-days, APT resources, physical access

## INPUT
- Original architecture: {architecture_original}
- Improved architecture: {architecture_improved} (after Defense Agent)
- Controls: {control_recommendations}
- Residual risk: BEFORE {before_score} → AFTER {after_score}

## RED TEAM TASKS

### Task 1: Exploit Path Selection (Score impact: 40 points)

Choose the path with HIGHEST success likelihood:

**Analysis Template:**
```
PATH OPTIONS:
1. Internet → WebServer → Database
   - Controls: rate limiting (PREVENT), WAF (PREVENT), logging (DETECT)
   - Difficulty: MEDIUM (WAF can be bypassed)
   - Success likelihood: 40%

2. Phishing → Employee → Internal Network → Database
   - Controls: MFA (PREVENT), edr (DETECT), least privilege (ISOLATE)
   - Difficulty: HIGH (MFA blocks, EDR detects)
   - Success likelihood: 20%

CHOSEN: Path #1 (higher success likelihood)
```

**Scoring:**
- 40 pts: Correct choice (weakest path identified)
- 20 pts: Suboptimal choice (harder path chosen)
- 0 pts: No path analysis

### Task 2: Control Bypass Scenarios (Score impact: 30 points)

For EACH control in chosen path, attempt bypass:

**Bypass Template:**
```json
[
  {
    "control": "rate limiting",
    "technique_blocked": "T1190",
    "bypass_method": "Use distributed botnet (1,000 IPs) to stay under per-IP limit",
    "bypass_difficulty": "EASY",
    "bypass_likelihood": "80%",
    "effectiveness_after_bypass": "20% (down from 80%)",
    "recommendation": "Add behavior analysis (detect patterns across IPs)"
  },
  {
    "control": "WAF",
    "technique_blocked": "T1190",
    "bypass_method": "Obfuscate payload (base64, unicode) to evade signature detection",
    "bypass_difficulty": "MEDIUM",
    "bypass_likelihood": "50%",
    "effectiveness_after_bypass": "50% (down from 90%)",
    "recommendation": "Use ML-based WAF (not just signatures)"
  }
]
```

**Scoring:**
- 30 pts: Realistic bypasses, correct difficulty assessment
- 20 pts: Some bypasses unrealistic (e.g., requires zero-day)
- 0 pts: No bypass analysis

### Task 3: Architecture Improvement Validation (Score impact: 20 points)

Test if `after-llm.mmd` ACTUALLY reduces risk:

**Validation Template:**
```
IMPROVEMENT: Added API Gateway between Internet and WebServer

BEFORE (original):
- Attack: T1190 directly to WebServer
- Success likelihood: 70% (rate limiting only)
- Risk score: 62/100

AFTER (improved):
- Attack: Must bypass API Gateway (MFA + WAF + rate limiting)
- Bypass difficulty:
  - MFA: HIGH (requires stolen credentials)
  - WAF: MEDIUM (payload obfuscation)
  - rate limiting: EASY (botnet)
- Success likelihood: 30% (3 layers to bypass)
- Risk score: 18/100 (claimed)

VALIDATION:
✓ IMPROVEMENT VALID - Adds 2 controls (MFA, WAF) at entry
✓ RISK REDUCTION REALISTIC - 70% → 30% achievable
✓ ARCHITECTURE PARSEABLE - API Gateway is valid node type

RECOMMENDATION: ACCEPT improvement
```

**Scoring:**
- 20 pts: Improvement validated, risk reduction realistic
- 10 pts: Improvement valid but risk reduction overstated
- 0 pts: Improvement ineffective or unparseable

### Task 4: Residual Risk Realism Check (Score impact: 10 points)

Can you achieve the AFTER score in a real attack?

**Realism Template:**
```
AFTER SCORE CLAIMED: 18/100

RED TEAM ATTACK SCENARIO:
1. Reconnaissance: Nmap scan, identify WebServer version
2. Initial Access: T1190 exploit (CVE-2023-XXXX) with obfuscated payload
3. Bypass Controls:
   - rate limiting: Botnet (1,000 IPs) → BYPASSED
   - WAF: Base64 obfuscation → 50% chance BYPASSED
   - logging: Delete logs after compromise → EVADED (no centralized SIEM)
4. Lateral Movement: T1021 (SMB to Database)
5. Impact: T1005 (Data exfiltration)

SUCCESS LIKELIHOOD: 35% (realistic with moderate skill)
ACHIEVED RISK SCORE: 25/100 (not 18/100)

REASON FOR DIFFERENCE:
- WAF bypass easier than expected (signature-based, not ML)
- Logging evasion possible (no centralized SIEM)

RECOMMENDATION: Adjust AFTER score to 25/100 OR add centralized SIEM
```

**Scoring:**
- 10 pts: Realistic attack scenario, accurate risk adjustment
- 5 pts: Some assumptions unrealistic (e.g., requires insider)
- 0 pts: No validation

## OUTPUT REQUIRED

Provide:
1. **Chosen Attack Path** (weakest path with rationale)
2. **Control Bypass Scenarios** (per control, with likelihood)
3. **Architecture Improvement Validation** (does after-llm.mmd work?)
4. **Residual Risk Adjustment** (realistic AFTER score)

## CONFIDENCE ADJUSTMENT

Based on your findings:
- If controls hold up (success <30%): +0.10 (high confidence)
- If 1-2 bypasses found (success 30-50%): +0.05 (acceptable)
- If 3-5 bypasses (success 50-70%): 0.00 (needs work)
- If 6+ bypasses (success >70%): -0.10 (significant gaps)

## YOUR RESPONSE
[Provide structured red team report in JSON format above]
"""
```

**Confidence Impact:** +10% (adversarial validation catches false positives)

---

### Q4: How to aggregate multi-agent confidence?

**Current Gap:** No orchestrator to sequence agents and combine scores.

**Solution: Orchestrator Agent**

```python
# chatbot/modules/agent_orchestrator.py (NEW)

class AgentOrchestrator:
    """
    Sequences agents, aggregates scores, resolves conflicts.
    """
    
    def __init__(self):
        self.agents = {
            "architect": ArchitectCritic(),
            "defense": DefenseEffectivenessCritic(),
            "security_tester": SecurityTesterCritic()
        }
    
    def run_critique_pipeline(
        self,
        ground_truth: Dict,
        architecture_mmd: str
    ) -> Dict:
        """
        Run all agents in sequence, aggregate results.
        
        Returns: {
            "final_confidence": float,
            "agent_scores": {...},
            "aggregate_findings": {...},
            "after_llm_mmd": str
        }
        """
        
        # STEP 1: Validate input
        is_valid, validation_results, errors = AgentInputValidator.validate_ground_truth(ground_truth)
        
        if not is_valid:
            raise ValueError(f"Input validation failed:\n" + "\n".join(errors))
        
        logger.info("✅ Input validation passed - starting agent pipeline")
        
        # STEP 2: Run Architect (design quality)
        logger.info("Running Agent 1/3: Architect Critic...")
        architect_result = self.agents["architect"].critique(ground_truth)
        
        # STEP 3: Run Defense Effectiveness (control validation)
        logger.info("Running Agent 2/3: Defense Effectiveness Critic...")
        defense_result = self.agents["defense"].critique(
            ground_truth,
            architect_improvements=architect_result.improvement_roadmap
        )
        
        # STEP 4: Generate improved architecture
        logger.info("Generating improved architecture (after-llm.mmd)...")
        after_llm_mmd = self._generate_improved_architecture(
            architecture_mmd,
            defense_result.architecture_improvements
        )
        
        # STEP 5: Run Security Tester (adversarial validation)
        logger.info("Running Agent 3/3: Security Tester (Red Team)...")
        tester_result = self.agents["security_tester"].critique(
            ground_truth,
            architecture_original=architecture_mmd,
            architecture_improved=after_llm_mmd,
            architect_findings=architect_result,
            defense_findings=defense_result
        )
        
        # STEP 6: Aggregate confidence
        final_confidence = self._calculate_final_confidence(
            deterministic_baseline=ground_truth["validation"]["confidence"],
            architect_score=architect_result.score,
            defense_score=defense_result.score,
            tester_score=tester_result.score
        )
        
        # STEP 7: Resolve conflicts (if any)
        conflicts = self._detect_conflicts(architect_result, defense_result, tester_result)
        if conflicts:
            logger.warning(f"⚠️  {len(conflicts)} conflicts detected - resolving...")
            resolved = self._resolve_conflicts(conflicts)
        
        return {
            "final_confidence": final_confidence,
            "agent_scores": {
                "architect": architect_result.score,
                "defense": defense_result.score,
                "security_tester": tester_result.score
            },
            "aggregate_findings": {
                "architect": architect_result.findings,
                "defense": defense_result.findings,
                "security_tester": tester_result.findings,
                "conflicts_resolved": conflicts if conflicts else []
            },
            "after_llm_mmd": after_llm_mmd,
            "validation_report": self._generate_validation_report(
                architect_result, defense_result, tester_result
            )
        }
    
    def _calculate_final_confidence(
        self,
        deterministic_baseline: float,
        architect_score: int,
        defense_score: int,
        tester_score: int
    ) -> Dict:
        """
        Aggregate confidence from deterministic + 3 agents.
        
        Formula:
        - Architect adjustment: (score - 50) / 500 (max ±0.10)
        - Defense adjustment: (score - 50) / 500 (max ±0.10)
        - Tester adjustment: (score - 50) / 500 (max ±0.10)
        - Total adjustment: sum (max ±0.30)
        
        Final = baseline + total_adjustment (clamped to [0, 1])
        """
        
        architect_adjustment = (architect_score - 50) / 500
        defense_adjustment = (defense_score - 50) / 500
        tester_adjustment = (tester_score - 50) / 500
        
        total_adjustment = architect_adjustment + defense_adjustment + tester_adjustment
        
        final = deterministic_baseline + total_adjustment
        final = max(0.0, min(1.0, final))  # Clamp to [0, 1]
        
        # Determine level
        if final >= 0.95:
            level = "CRITICAL"
        elif final >= 0.85:
            level = "HIGH"
        elif final >= 0.70:
            level = "MEDIUM"
        else:
            level = "LOW"
        
        return {
            "final_confidence": final,
            "level": level,
            "baseline": deterministic_baseline,
            "adjustments": {
                "architect": architect_adjustment,
                "defense": defense_adjustment,
                "security_tester": tester_adjustment,
                "total": total_adjustment
            }
        }
    
    def _detect_conflicts(
        self,
        architect: CritiqueScore,
        defense: CritiqueScore,
        tester: CritiqueScore
    ) -> List[Dict]:
        """
        Detect conflicts between agents.
        
        Examples:
        - Architect says control is good, Tester bypasses it easily
        - Defense says placement is optimal, Architect says it's wrong layer
        - Tester says risk score is achievable, Defense says controls insufficient
        """
        conflicts = []
        
        # Example: Architect vs Tester conflict
        for arch_finding in architect.findings.get("control_gaps", []):
            control_name = arch_finding["control"]
            for tester_bypass in tester.findings.get("bypasses", []):
                if tester_bypass["control"] == control_name:
                    if tester_bypass["bypass_likelihood"] > 70:
                        conflicts.append({
                            "type": "control_effectiveness",
                            "agents": ["architect", "security_tester"],
                            "control": control_name,
                            "architect_assessment": "Appropriate control",
                            "tester_assessment": f"Easily bypassed ({tester_bypass['bypass_likelihood']}%)",
                            "severity": "HIGH"
                        })
        
        return conflicts
    
    def _resolve_conflicts(self, conflicts: List[Dict]) -> List[Dict]:
        """
        Resolve conflicts (prefer red team perspective).
        
        Rule: If Tester can bypass, Tester wins (real-world validation).
        """
        resolved = []
        for conflict in conflicts:
            if conflict["type"] == "control_effectiveness":
                resolution = {
                    "conflict": conflict,
                    "resolution": "Accept Security Tester assessment (adversarial validation is authoritative)",
                    "action": f"Downgrade confidence in {conflict['control']}",
                    "confidence_penalty": -0.05
                }
                resolved.append(resolution)
        
        return resolved
    
    def _generate_improved_architecture(
        self,
        original_mmd: str,
        improvements: List[Dict]
    ) -> str:
        """
        Generate after-llm.mmd with Defense Agent improvements.
        """
        from chatbot.parsers.mermaid_parser import MermaidParser
        
        parser = MermaidParser()
        nodes, edges, subgraphs = parser.parse_file(original_mmd)
        
        # Apply improvements
        for imp in improvements:
            if imp["type"] == "add_node":
                nodes.append({
                    "id": imp["node_id"],
                    "label": imp["node_label"],
                    "layer": imp["layer"]
                })
                
                # Add edges (insert between)
                if "insert_between" in imp:
                    source, target = imp["insert_between"]
                    # Remove old edge
                    edges = [e for e in edges if not (e["source"] == source and e["target"] == target)]
                    # Add new edges
                    edges.append({"source": source, "target": imp["node_id"]})
                    edges.append({"source": imp["node_id"], "target": target})
        
        # Generate Mermaid syntax
        mmd_lines = ["graph TB"]
        
        for node in nodes:
            mmd_lines.append(f"  {node['id']}[\"{node['label']}\"]")
        
        for edge in edges:
            label = edge.get("label", "")
            if label:
                mmd_lines.append(f"  {edge['source']} -->|{label}| {edge['target']}")
            else:
                mmd_lines.append(f"  {edge['source']} --> {edge['target']}")
        
        return "\n".join(mmd_lines)
    
    def _generate_validation_report(
        self,
        architect: CritiqueScore,
        defense: CritiqueScore,
        tester: CritiqueScore
    ) -> str:
        """
        Generate Pass/Fail validation report.
        """
        report = "# Agent Validation Report\n\n"
        
        # Architect
        report += f"## Agent 1: Architect Critic\n"
        report += f"**Score:** {architect.score}/100 ({architect.rating})\n"
        report += f"**Status:** {'✅ PASS' if architect.score >= 70 else '⚠️ NEEDS IMPROVEMENT'}\n\n"
        
        # Defense
        report += f"## Agent 2: Defense Effectiveness Critic\n"
        report += f"**Score:** {defense.score}/100 ({defense.rating})\n"
        report += f"**Status:** {'✅ PASS' if defense.score >= 70 else '⚠️ NEEDS IMPROVEMENT'}\n\n"
        
        # Tester
        report += f"## Agent 3: Security Tester (Red Team)\n"
        report += f"**Score:** {tester.score}/100 ({tester.rating})\n"
        report += f"**Status:** {'✅ PASS' if tester.score >= 70 else '⚠️ NEEDS IMPROVEMENT'}\n\n"
        
        return report
```

**Confidence Impact:** +5% (orchestration ensures consistency)

---

## Implementation Roadmap

### MVP2: Tester Agent (2-3 hours) - ALREADY SPECCED
✅ **Spec exists:** `docs/phases/PHASE3C_MVP2_TESTER_SPEC.md`

Tasks:
- [ ] Create `chatbot/modules/tester_critic.py` (validation agent)
- [ ] Implement TESTER_RUBRIC (40+30+20+10)
- [ ] Execute Architect roadmap verification_method checks
- [ ] Test on flawed assessment (should catch all 3 errors)

### MVP3: Input Validation (1 hour) - NEW
- [ ] Create `chatbot/modules/agent_input_validator.py`
- [ ] Implement pre-LLM assertions (fail fast if incomplete)
- [ ] Add validation logging (what's being passed to agents)
- [ ] Test on good + incomplete ground truth

### MVP4: Defense Effectiveness Agent (2-3 hours) - NEW
- [ ] Create `chatbot/modules/defense_effectiveness_critic.py`
- [ ] Implement per-control mitigation validation
- [ ] Add placement effectiveness checks
- [ ] Generate architecture improvements (for after-llm.mmd)
- [ ] Test on 2 architectures

### MVP5: Security Tester Agent (3-4 hours) - NEW
- [ ] Create `chatbot/modules/security_tester_critic.py`
- [ ] Implement red team path selection logic
- [ ] Add control bypass scenarios
- [ ] Validate after-llm.mmd (does it reduce risk?)
- [ ] Test on 2 architectures

### MVP6: Orchestrator (2-3 hours) - NEW
- [ ] Create `chatbot/modules/agent_orchestrator.py`
- [ ] Implement agent sequencing (Architect → Defense → Tester)
- [ ] Add conflict detection + resolution
- [ ] Generate after-llm.mmd from Defense improvements
- [ ] Calculate final confidence (deterministic + 3 agents)
- [ ] Test end-to-end on 3 architectures

### MVP7: CLI Integration (1 hour)
- [ ] Add `--gen-arch-truth-llm` flag
- [ ] Output after-llm.mmd in report directory
- [ ] Add validation_report.md
- [ ] Update threat_report.md with agent findings

---

## Total Estimated Time: 11-15 hours

| Phase | Hours | Status |
|-------|-------|--------|
| MVP1: Architect | 4 | ✅ COMPLETE |
| MVP2: Tester | 2-3 | Spec ready |
| MVP3: Input Validation | 1 | Design ready |
| MVP4: Defense Effectiveness | 2-3 | Design ready |
| MVP5: Security Tester | 3-4 | Design ready |
| MVP6: Orchestrator | 2-3 | Design ready |
| MVP7: CLI Integration | 1 | Design ready |
| **Total** | **15-20** | **20% complete** |

---

## Success Criteria (Final)

### Input Validation
- [ ] 100% of ground truth fields validated before LLM
- [ ] Assertion errors if data incomplete (fail fast)
- [ ] Zero false starts (LLM not called with bad data)

### Agent Quality
- [ ] Architect: 78/100 good, 23/100 flawed (already achieved)
- [ ] Defense: Catches control-technique mismatches
- [ ] Security Tester: Identifies 1+ bypass per architecture
- [ ] Orchestrator: Resolves conflicts, aggregates scores

### Confidence Accuracy
- [ ] Final confidence: 99.5% ± (up to 30% from 3 agents)
- [ ] Adjustments justified in breakdown
- [ ] after-llm.mmd parseable and reduces risk

### Performance
- [ ] All agents complete in ≤2 minutes (total)
- [ ] Graceful degradation if LLM unavailable
- [ ] Cached results reused if architecture unchanged

---

## Key Improvements Over Original PHASE3C_OVERVIEW.md

1. **Build on Existing Work** - Uses agent_framework.py and architect_critic.py (MVP1)
2. **Input Validation** - New module ensures data completeness before LLM
3. **Per-Node Analysis** - Enhanced Architect rubric validates every node
4. **Defense Effectiveness** - New agent validates control-technique mapping
5. **Adversarial Validation** - Security Tester red teams the entire assessment
6. **Orchestration** - Sequences agents, detects conflicts, aggregates confidence
7. **Architecture Improvement** - Generates after-llm.mmd (testable improvement)

---

## Next Steps

1. **Review this design** with stakeholders
2. **Complete MVP2** (Tester agent, spec already exists)
3. **Implement MVP3** (Input validation, highest ROI for confidence)
4. **Iterate** on Defense + Security Tester (MVP4-5)
5. **Integrate** with Orchestrator (MVP6)
6. **Test** end-to-end on 22 reference architectures

---

**Document Version:** 1.0  
**Date:** 2026-05-15  
**Purpose:** Enhancement plan building on MVP1, addressing user concerns about rigor  
**Supersedes:** None (complements existing Phase 3C docs)
