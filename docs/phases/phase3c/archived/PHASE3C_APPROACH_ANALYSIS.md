# Phase 3C: Sequential vs Parallel Agent Approach - Analysis

**Date:** 2026-05-15  
**Purpose:** Determine optimal agent execution pattern (sequential vs parallel)  
**Reference:** @/report/02_minimal_defended (sample for 5-artifact structure)

---

## Part 1: The 5 Deterministic Artifacts (Ground Truth Structure)

### Actual Structure from `ground_truth.json`

Based on `/report/02_minimal_defended/ground_truth.json`:

```python
# Top-level keys in ground_truth.json
{
    # ARTIFACT 1: Attack Paths
    "expected_attack_paths": [
        {
            "entry": "Internet",
            "target": "Database with Encryption",
            "path": [...],  # List of node objects
            "techniques": ["T1190", "T1059", ...],
            "per_node_techniques": {  # Phase 3B+ feature
                "Internet": [],
                "WAF": ["T1190"],
                "ALB": [],
                "MFA": ["T1133"],
                "WebServer": ["T1059", "T1068"],
                "Database": ["T1213", "T1005"]
            },
            "risk_score": 45,
            "severity": "HIGH"
        }
    ],
    
    # ARTIFACT 2: Control Recommendations
    "control_recommendations": [
        {
            "control": "least privilege",
            "priority": "critical",
            "score": 18.0,
            "rapids_threats": ["ransomware", "insider_threat"],
            "rapids_risk_score": 120,
            "mitigations": ["M1016", "M1018", "M1026", "M1042"],
            "techniques": ["T1059", "T1133", "T1190", "T1213", "T1485", "T1490"],
            "attack_paths": [0, 1, 2],  # Path IDs this control addresses
            "rationale": "RAPIDS: Ransomware, Insider Threat | Confirmed by attack path(s) #1, #2, #3",
            "detailed_rationale": [...],
            "dir_category": "isolate",
            "layer": "data",
            "placement": "At Database with Encryption hop",
            "control_type": "MITIGATION:ISOLATE",
            "confidence": {
                "score": 0.7731666666666667,
                "level": "MEDIUM",
                "breakdown": {...}
            },
            "_layered_defense": {  # Phase 3B+ feature
                "hop_analysis": [
                    {
                        "path_id": 0,
                        "hop_id": 0,
                        "source_id": "WebServer",
                        "target_id": "Database",
                        "source_label": "Web Server with EDR",
                        "target_label": "Database with Encryption",
                        "layer": "data",
                        "security_coverage": {
                            "prevention": true,
                            "detect": false,
                            "isolate": false,
                            "respond": false
                        },
                        "resilience_coverage": {...},
                        "is_critical": true,
                        "is_spof": false
                    }
                ]
            }
        }
    ],
    
    # ARTIFACT 3: Residual Risk
    "residual_risks": {
        "current_total_risk": 178,
        "projected_total_risk": 62,
        "risk_reduction": 116,
        "risk_reduction_percent": 65,
        "current_risk_level": "HIGH",
        "projected_risk_level": "MEDIUM",
        "per_threat": {
            "ransomware": {
                "current": 70,
                "projected": 20,
                "reduction": 50,
                "reduction_percent": 71
            },
            "ddos": {...},
            "phishing": {...},
            "supply_chain": {...},
            "insider_threat": {...},
            "data_breach": {...}
        },
        "thresholds": {
            "critical": 80,
            "high": 60,
            "medium": 40,
            "low": 20
        }
    },
    
    # ARTIFACT 4: Validation Results
    "validation_report": {
        "overall_valid": true,
        "validations": [
            {
                "check": "path_completeness",
                "passed": true,
                "details": "All 3 attack paths have ≥1 control"
            },
            {
                "check": "orphan_nodes",
                "passed": true,
                "details": "All nodes reachable from entry points"
            },
            {
                "check": "mitigation_exhaustiveness",
                "passed": true,
                "details": "Controls cover 100% of MITRE mitigations"
            },
            {
                "check": "diagram_completeness",
                "passed": true,
                "details": "All controls visualized"
            },
            {
                "check": "control_budget",
                "passed": true,
                "details": "DDIR balance: 35/29/24/12 (within ±5%)"
            },
            {
                "check": "hop_coverage",
                "passed": true,
                "details": "Each hop has ≥1 prevention control"
            }
        ],
        "confidence_adjustments": {
            "base": 0.995,
            "validation_bonus": 0.005,
            "final": 1.0
        },
        "issues_found": []
    },
    
    # ARTIFACT 5: RAPIDS Assessment
    "rapids_assessment": {
        "ransomware": {
            "risk": 70,
            "priority": "high",
            "rationale": "Database is high-value target, encryption present but backup missing",
            "controls_present": ["encryption", "edr"],
            "controls_missing": ["backup", "least privilege"],
            "residual_risk": 20
        },
        "ddos": {
            "risk": 40,
            "priority": "medium",
            "rationale": "Load balancer provides some protection but rate limiting missing",
            "controls_present": ["load balancer"],
            "controls_missing": ["rate limiting", "ddos protection"],
            "residual_risk": 15
        },
        "phishing": {...},
        "supply_chain": {...},
        "insider_threat": {...},
        "data_breach": {...},
        "zero_day": {...}  # Sometimes present
    },
    
    # Metadata
    "architecture": "02_minimal_defended.mmd",
    "description": "Web App architecture",
    "controls_present": ["edr", "encryption", "firewall", "load balancer", "mfa", "waf"],
    "controls_missing": ["least privilege", "vulnerability scanning", ...],
    "expected_risk_score": 178,
    "expected_defensibility": 35,
    "metadata": {
        "timestamp": "2026-05-10T22:17:00",
        "deterministic_version": "3B+",
        "confidence": 0.995
    }
}
```

### Artifact Summary

| Artifact | Key in JSON | Size (02_minimal_defended) | Key Fields for Agents |
|----------|-------------|----------------------------|------------------------|
| 1. Attack Paths | `expected_attack_paths` | 3 paths | `per_node_techniques`, `techniques`, `risk_score`, `path` |
| 2. Controls | `control_recommendations` | 17 controls | `_layered_defense`, `techniques`, `attack_paths`, `mitigations`, `confidence` |
| 3. Residual Risk | `residual_risks` | 1 object | `per_threat`, `current_total_risk`, `projected_total_risk`, `thresholds` |
| 4. Validation | `validation_report` | 1 object | `validations` (6 checks), `overall_valid`, `issues_found` |
| 5. RAPIDS | `rapids_assessment` | 6-7 categories | `risk`, `priority`, `controls_present`, `controls_missing`, `residual_risk` |

---

## Part 2: Sequential vs Parallel - Trade-off Analysis

### Option A: Sequential (Existing Code Pattern)

```
┌─────────────┐
│  Architect  │ (2-3 min) Critiques all 5 artifacts
└──────┬──────┘
       │ improvement_roadmap
       ↓
┌─────────────┐
│   Tester    │ (1-2 min) Validates using Architect roadmap
└──────┬──────┘
       │ validation_results
       ↓
┌─────────────┐
│  Red Team   │ (2-3 min) Tests using Architect + Tester findings
└──────┬──────┘
       │ bypass_scenarios
       ↓
┌─────────────┐
│ Orchestrator│ (30s) Aggregates results
└─────────────┘

Total Time: 6-9 minutes
```

**Pros:**
1. ✅ **Context Accumulation**: Each agent builds on previous findings
2. ✅ **Cross-Referencing**: Tester can verify Architect's roadmap directly
3. ✅ **Progressive Refinement**: Red Team attacks the improved model (Architect suggestions)
4. ✅ **Simpler Debugging**: Linear execution, easier to trace issues
5. ✅ **Code Reuse**: MVP1 Architect already implemented, MVP2 Tester spec ready
6. ✅ **Memory Efficiency**: Only one LLM call active at a time
7. ✅ **Narrative Flow**: Report reads naturally (design → test → attack)

**Cons:**
1. ❌ **Slower**: 6-9 minutes vs 2-3 minutes (3x slower)
2. ❌ **Cascade Errors**: If Architect misses something, Tester/Red Team won't catch it
3. ❌ **No Independent Validation**: Agents can't provide "second opinion" on same artifact

**Best For:**
- Depth over speed
- Small batch processing (1-5 architectures)
- Detailed investigation of specific architectures
- Development/testing phase

---

### Option B: Parallel (Proposed Team Architecture)

```
        ┌─────────────┐
        │ Orchestrator│ (30s) Parses artifacts, initializes memory
        └──────┬──────┘
               ├────────────┬────────────┐
               ↓            ↓            ↓
        ┌──────────┐  ┌──────────┐  ┌──────────┐
        │Architect │  │  Tester  │  │ Red Team │ (2-3 min parallel)
        └──────────┘  └──────────┘  └──────────┘
               │            │            │
               └────────────┴────────────┘
                           ↓
                   ┌──────────────┐
                   │Shared Memory │
                   │(concurrent)  │
                   └──────┬───────┘
                          ↓
                   ┌─────────────┐
                   │ Orchestrator│ (30s) Consolidates findings
                   └─────────────┘

Total Time: 3-4 minutes
```

**Pros:**
1. ✅ **Faster**: 3-4 minutes vs 6-9 minutes (2-3x speedup)
2. ✅ **Independent Validation**: Multiple agents find same issue = higher confidence
3. ✅ **Diverse Perspectives**: Each agent approaches artifacts differently
4. ✅ **Scalable**: Can add more agents without increasing time
5. ✅ **Redundancy**: If one agent fails, others still provide value

**Cons:**
1. ❌ **No Context Accumulation**: Tester can't directly verify Architect roadmap
2. ❌ **Duplication Risk**: Agents may find same issues (need de-duplication)
3. ❌ **Complex Coordination**: Shared memory, thread-safety, race conditions
4. ❌ **Higher Resource Usage**: 3 LLM calls simultaneously (more $$)
5. ❌ **More Code**: Need artifact parser, shared memory, complex orchestrator
6. ❌ **Harder Debugging**: Concurrent execution, non-deterministic order

**Best For:**
- Speed over depth
- Batch processing (10+ architectures)
- Production pipeline
- When LLM API cost is not a constraint

---

### Option C: Hybrid (Sequential with Parallel Sub-Tasks)

```
┌─────────────┐
│  Architect  │ (2-3 min) Critiques all 5 artifacts
└──────┬──────┘
       │ improvement_roadmap
       ├─────────────┬─────────────┐
       ↓             ↓             ↓
┌──────────┐  ┌──────────┐  ┌──────────┐
│ Tester   │  │ Red Team │  │ Defense  │ (2-3 min parallel)
│(validate)│  │ (attack) │  │ (improve)│
└──────────┘  └──────────┘  └──────────┘
       │             │             │
       └─────────────┴─────────────┘
                     ↓
              ┌─────────────┐
              │ Orchestrator│ (30s) Consolidates
              └─────────────┘

Total Time: 4-6 minutes
```

**Pros:**
1. ✅ **Balanced**: Faster than sequential, simpler than full parallel
2. ✅ **Context for Stage 2**: Architect findings inform stage 2 agents
3. ✅ **Diverse Stage 2**: Multiple perspectives on Architect's work
4. ✅ **Moderate Complexity**: Only stage 2 needs shared memory

**Cons:**
1. ❌ **Still 4-6 minutes**: Not as fast as full parallel
2. ❌ **Partial Context**: Stage 2 agents can't influence each other
3. ❌ **Moderate Complexity**: More complex than pure sequential

---

## Part 3: Recommendation & Decision Framework

### Decision Matrix

| Criteria | Sequential (A) | Parallel (B) | Hybrid (C) |
|----------|----------------|--------------|------------|
| **Implementation Time** | 8-10h (70% done) | 14-16h (20% done) | 12-14h (50% done) |
| **Execution Speed** | 6-9 min | 3-4 min | 4-6 min |
| **Code Complexity** | Low | High | Medium |
| **Debugging Ease** | High | Low | Medium |
| **Context Depth** | High | Low | Medium |
| **Independent Validation** | Low | High | Medium |
| **Resource Usage (LLM)** | 3 calls | 3 calls (parallel) | 4 calls |
| **Scalability** | Poor | Excellent | Good |
| **Code Reuse** | High (MVP1) | Low (rewrite) | Medium |

### Recommendation: **Sequential (Option A)** for MVP

**Reasons:**

1. **70% Complete**: MVP1 (Architect) done, MVP2 (Tester) spec ready
   - Parallel requires rewriting existing code
   - Sequential leverages existing `agent_framework.py` and `architect_critic.py`

2. **Context is Critical**: 
   - Tester NEEDS Architect's `improvement_roadmap` (verification_method field)
   - Red Team NEEDS to test the improved architecture (after applying Architect suggestions)
   - Sequential provides this naturally

3. **Narrative Quality**:
   ```markdown
   ## Architect Critique
   Found 3 gaps, provided roadmap to fix...
   
   ## Tester Validation
   Verified Architect Priority 1: ✓ Technique count increased 1→8
   Verified Architect Priority 2: ✗ Control priorities still misaligned
   
   ## Red Team Attack
   Tested Architect's suggested improvements...
   Bypass scenarios found: 2/5 controls
   ```
   
   This reads better than parallel (no cross-references).

4. **Debugging**: 
   - Sequential: "Red Team failed → check Tester output → check Architect output"
   - Parallel: "All 3 failed → which one caused it?"

5. **MVP Philosophy**: 
   - Get working end-to-end first
   - Optimize later if needed
   - Sequential = proven pattern (existing code)

### When to Switch to Parallel (Later)

**Trigger Criteria:**
1. Processing >10 architectures in batch
2. LLM API speed improves (sub-30s per call)
3. Sequential proves too slow in production
4. Need independent validation (e.g., 3 agents vote on findings)

**Migration Path:**
- Keep sequential as "deep mode" (`--gen-arch-truth-team-deep`)
- Add parallel as "fast mode" (`--gen-arch-truth-team-fast`)
- Let users choose based on use case

---

## Part 4: Sequential Implementation Plan (Recommended)

### Phase 1: Artifact Parser (1.5h) - CRITICAL

```python
# chatbot/modules/artifact_extractor.py

class ArtifactExtractor:
    """
    Extracts 5 artifacts from ground_truth.json.
    Creates indexed views for efficient agent queries.
    """
    
    @staticmethod
    def extract(ground_truth: Dict) -> Dict:
        """
        Extract and validate 5 artifacts.
        
        Returns: {
            "artifact_1_attack_paths": {...},
            "artifact_2_controls": {...},
            "artifact_3_residual_risk": {...},
            "artifact_4_validation": {...},
            "artifact_5_rapids": {...}
        }
        """
        
        # Validate presence
        required = [
            "expected_attack_paths",
            "control_recommendations", 
            "residual_risks",
            "validation_report",
            "rapids_assessment"
        ]
        
        for key in required:
            if key not in ground_truth:
                raise ValueError(f"Missing artifact: {key}")
        
        # Extract with indexes
        return {
            "artifact_1_attack_paths": ArtifactExtractor._extract_attack_paths(ground_truth),
            "artifact_2_controls": ArtifactExtractor._extract_controls(ground_truth),
            "artifact_3_residual_risk": ground_truth["residual_risks"],
            "artifact_4_validation": ground_truth["validation_report"],
            "artifact_5_rapids": ground_truth["rapids_assessment"]
        }
    
    @staticmethod
    def _extract_attack_paths(gt: Dict) -> Dict:
        """Extract Artifact 1 with indexes."""
        paths = gt["expected_attack_paths"]
        
        # Build indexes
        node_to_paths = {}
        technique_to_paths = {}
        
        for i, path in enumerate(paths):
            # Index: node_id → path_ids
            for node in path.get("path", []):
                node_id = node.get("id") or node
                if node_id not in node_to_paths:
                    node_to_paths[node_id] = []
                node_to_paths[node_id].append(i)
            
            # Index: technique → path_ids
            for tech in path.get("techniques", []):
                if tech not in technique_to_paths:
                    technique_to_paths[tech] = []
                technique_to_paths[tech].append(i)
        
        return {
            "paths": paths,
            "count": len(paths),
            "node_to_paths": node_to_paths,
            "technique_to_paths": technique_to_paths
        }
    
    @staticmethod
    def _extract_controls(gt: Dict) -> Dict:
        """Extract Artifact 2 with indexes."""
        controls = gt["control_recommendations"]
        
        # Build indexes
        control_to_paths = {}
        control_to_techniques = {}
        
        for ctrl in controls:
            name = ctrl["control"]
            control_to_paths[name] = ctrl.get("attack_paths", [])
            control_to_techniques[name] = ctrl.get("techniques", [])
        
        return {
            "controls": controls,
            "count": len(controls),
            "control_to_paths": control_to_paths,
            "control_to_techniques": control_to_techniques
        }
```

### Phase 2: Enhanced Architect (2h)

```python
# Enhance existing chatbot/modules/architect_critic.py

def _format_prompt(self, ground_truth: Dict) -> str:
    """
    Format prompt with ALL 5 artifacts clearly labeled.
    """
    
    # Extract artifacts (validation happens here)
    artifacts = ArtifactExtractor.extract(ground_truth)
    
    prompt = f"""
You are a security architect reviewing a threat assessment.

## ARTIFACT 1: ATTACK PATHS ({artifacts['artifact_1_attack_paths']['count']} paths)

{self._format_attack_paths(artifacts['artifact_1_attack_paths'])}

## ARTIFACT 2: CONTROL RECOMMENDATIONS ({artifacts['artifact_2_controls']['count']} controls)

{self._format_controls(artifacts['artifact_2_controls'])}

## ARTIFACT 3: RESIDUAL RISK

{self._format_residual_risk(artifacts['artifact_3_residual_risk'])}

## ARTIFACT 4: VALIDATION RESULTS

{self._format_validation(artifacts['artifact_4_validation'])}

## ARTIFACT 5: RAPIDS ASSESSMENT

{self._format_rapids(artifacts['artifact_5_rapids'])}

## YOUR TASK

Critique each artifact using the rubric:
1. Artifact 1 (40 pts): Attack path completeness
2. Artifact 2 (30 pts): Control appropriateness  
3. Artifact 3 (20 pts): Risk realism
4. Artifact 4 (10 pts): Validation thoroughness

Provide improvement_roadmap with verification_method for Tester agent.
"""
    
    return prompt
```

### Phase 3: Tester Agent (2h) - NEW

```python
# chatbot/modules/tester_critic.py

class TesterCritic(CriticAgent):
    """
    Validates assessment quality using Architect's roadmap.
    """
    
    def critique(self, ground_truth: Dict, architect_result: CritiqueScore) -> CritiqueScore:
        """
        Validate ground truth using Architect's improvement_roadmap.
        
        Architect provides verification_method for each roadmap item.
        Tester executes those checks.
        """
        
        # Extract artifacts
        artifacts = ArtifactExtractor.extract(ground_truth)
        
        # Execute Architect roadmap verifications
        verification_results = []
        
        for roadmap_item in architect_result.improvement_roadmap:
            verification_method = roadmap_item["verification_method"]
            
            # Execute verification (deterministic checks)
            result = self._execute_verification(
                verification_method,
                artifacts,
                roadmap_item
            )
            
            verification_results.append(result)
        
        # Format prompt with verification results
        prompt = self._format_tester_prompt(
            artifacts,
            architect_result,
            verification_results
        )
        
        # Call LLM
        llm_response = self.llm_client.generate(...)
        
        # Parse and return
        return self._parse_critique(llm_response)
    
    def _execute_verification(self, method: str, artifacts: Dict, roadmap_item: Dict) -> Dict:
        """
        Execute verification_method from Architect roadmap.
        
        Examples:
        - "Count MITRE techniques - should increase from 1 to 8+"
        - "Verify ransomware rationale aligns with actual controls"
        - "Check if control priorities aligned to RAPIDS scores"
        """
        
        # Parse method (simple keyword matching for MVP)
        if "count" in method.lower() and "technique" in method.lower():
            # Count techniques
            total = sum(len(p["techniques"]) for p in artifacts["artifact_1_attack_paths"]["paths"])
            expected = 8  # Parse from method
            
            return {
                "method": method,
                "status": "PASS" if total >= expected else "FAIL",
                "actual": total,
                "expected": expected,
                "architect_priority": roadmap_item["priority"]
            }
        
        # Add more verification patterns...
```

### Phase 4: Red Team Agent (3h) - NEW

```python
# chatbot/modules/red_team_critic.py

class RedTeamCritic(CriticAgent):
    """
    Adversarial testing of assessment from attacker perspective.
    """
    
    def critique(
        self, 
        ground_truth: Dict,
        architect_result: CritiqueScore,
        tester_result: CritiqueScore
    ) -> CritiqueScore:
        """
        Red team attack using:
        - Architect's identified gaps
        - Tester's validation failures
        - All 5 artifacts
        """
        
        # Extract artifacts
        artifacts = ArtifactExtractor.extract(ground_truth)
        
        # Select weakest path (using Architect + Tester insights)
        weakest_path = self._select_weakest_path(
            artifacts["artifact_1_attack_paths"],
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
```

### Phase 5: Sequential Orchestrator (1h)

```python
# chatbot/modules/sequential_orchestrator.py

class SequentialOrchestrator:
    """
    Runs A-Team agents sequentially with context passing.
    """
    
    def run_critique(self, ground_truth: Dict) -> Dict:
        """
        Sequential: Architect → Tester → Red Team
        """
        
        logger.info("🚀 Starting Sequential A-Team Critique")
        
        # Stage 1: Architect (2-3 min)
        logger.info("  [1/3] Running Architect...")
        architect = ArchitectCritic(...)
        architect_result = architect.critique(ground_truth)
        logger.info(f"  ✅ Architect complete - Score: {architect_result.score}/100")
        
        # Stage 2: Tester (1-2 min) - uses Architect roadmap
        logger.info("  [2/3] Running Tester (validating Architect roadmap)...")
        tester = TesterCritic(...)
        tester_result = tester.critique(ground_truth, architect_result)
        logger.info(f"  ✅ Tester complete - Score: {tester_result.score}/100")
        
        # Stage 3: Red Team (2-3 min) - uses Architect + Tester findings
        logger.info("  [3/3] Running Red Team (attacking assessment)...")
        red_team = RedTeamCritic(...)
        red_team_result = red_team.critique(ground_truth, architect_result, tester_result)
        logger.info(f"  ✅ Red Team complete - Exploit Score: {red_team_result.score}/100")
        
        # Aggregate
        final_confidence = self._calculate_confidence(
            deterministic=ground_truth["validation_report"]["confidence_adjustments"]["final"],
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

---

## Part 5: Implementation Timeline

| Phase | Component | Hours | Dependencies |
|-------|-----------|-------|--------------|
| 1 | Artifact Extractor | 1.5 | None |
| 2 | Enhanced Architect (use 5 artifacts) | 2 | Phase 1 |
| 3 | Tester Agent (verify roadmap) | 2 | Phase 1, 2 |
| 4 | Red Team Agent (attack) | 3 | Phase 1, 2, 3 |
| 5 | Sequential Orchestrator | 1 | Phase 2, 3, 4 |
| 6 | CLI Integration | 1 | Phase 5 |
| 7 | Testing (3 architectures) | 1.5 | Phase 6 |
| **Total** | **12 hours** | | |

---

## Part 6: Success Criteria

### Artifact Utilization
- [ ] All 5 artifacts extracted and validated
- [ ] Architect critiques all 5 artifacts explicitly
- [ ] Tester validates Artifact 4 (validation_report)
- [ ] Red Team uses Artifact 1 (attack_paths) for path selection

### Sequential Context Flow
- [ ] Tester references Architect's improvement_roadmap
- [ ] Tester executes verification_method checks
- [ ] Red Team uses Architect + Tester gaps to select weakest path
- [ ] Report shows narrative flow (design → test → attack)

### Performance
- [ ] Total execution: 6-9 minutes (acceptable for MVP)
- [ ] Artifact extraction: <5 seconds
- [ ] Each agent: 1-3 minutes

### Quality
- [ ] No duplicate findings across agents
- [ ] Cross-references between agents (e.g., "Tester confirmed Architect Priority 1")
- [ ] Final confidence: 99.5% ± 30% (realistic range)

---

## Conclusion

**Recommendation: Sequential (Option A)**

**Rationale:**
1. 70% code already exists (Architect MVP1, Tester spec)
2. Context passing is critical for quality critique
3. Narrative flow superior for human consumption
4. Simpler debugging and development
5. Can optimize to parallel later if needed

**Next Steps:**
1. Implement Artifact Extractor (validate 5 artifacts from `ground_truth.json`)
2. Enhance Architect to use all 5 artifacts
3. Build Tester to validate using Architect roadmap
4. Build Red Team to attack using Architect + Tester findings
5. Test end-to-end on 3 architectures

**Future Optimization:**
- If sequential proves too slow in production
- Add parallel mode as optional fast path
- Keep sequential as "deep investigation" mode

---

**Document Version:** 1.0  
**Date:** 2026-05-15  
**Purpose:** Analyze sequential vs parallel, map 5 artifacts, recommend approach  
**Reference:** @/report/02_minimal_defended/ground_truth.json
