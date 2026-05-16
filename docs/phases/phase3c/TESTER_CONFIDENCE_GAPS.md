# Tester Agent Confidence Gap Analysis

**Date:** 2026-05-16  
**Current Confidence:** 95%  
**Target Confidence:** 98-99%  
**Gap:** **Technical validation** of security effectiveness (not just structural checks)

---

## The Real Question

**User's Critical Insight:**
> "The aim of testing agent is to parse the output from architect whether the path improvements are indeed testable via the TTP and against the mitigating effectiveness. The matching are correct wearing security testing hat."

**Translation:** Tester must validate:
1. ✅ Are recommended improvements **technically testable** via MITRE techniques?
2. ✅ Do the controls **actually mitigate** the techniques as claimed?
3. ✅ Are the **mappings correct** (Control→Technique, Technique→Mitigation)?
4. ✅ Can we **prove** the improvement via security testing?

**Current Problem:** The 95% confidence assumes **structural validation** (arithmetic, formatting) but not **technical validation** (security effectiveness).

---

## Current State: What We Have (95%)

### ✅ Structural Validation (Well-Covered)

| Check | Confidence | What We Validate |
|-------|------------|------------------|
| Arithmetic | 100% | Score breakdown adds up |
| Roadmap format | 95% | Has priority, action, verification_method |
| Gap cross-validation | 90% | Gaps exist in ground truth |
| Coverage counts | 100% | RAPIDS 6/6, control count matches |

**Problem:** None of this checks if the **security logic is correct**!

### ❌ Technical Validation (Missing)

| Check | Confidence | What's Missing | Impact |
|-------|------------|----------------|--------|
| Technique→Mitigation mapping | **40%** | No MITRE validation | **HIGH** - Could recommend wrong controls |
| Control effectiveness | **50%** | No mitigation scoring | **HIGH** - Could claim false reduction |
| Attack path realism | **60%** | No technique sequence validation | **MEDIUM** - Could have impossible paths |
| Verification testability | **70%** | Can't parse/execute checks | **MEDIUM** - Can't prove improvements |

**Overall Technical Confidence: ~55%** ❌

---

## Gap Analysis: Why Only 95%?

### Gap 1: No MITRE Technique→Mitigation Validation

**Problem:**
Architect says: "Control X (M1026) mitigates T1059"

**What Tester SHOULD check:**
```python
# Is M1026 actually listed in T1059's mitigations?
technique = mitre_data["techniques"]["T1059"]
valid_mitigations = technique.get("mitigations", [])

if "M1026" not in valid_mitigations:
    gaps.append({
        "severity": "CRITICAL",
        "description": "Architect claims M1026 mitigates T1059 but MITRE doesn't list this mapping",
        "impact": "Recommended control may be ineffective"
    })
```

**Current State:** ❌ Not implemented - no access to MITRE data in Tester

**Data Needed:**
- `chatbot/data/enterprise-attack.json` (44MB) - already in repo
- Technique → Mitigation lookup function

**Confidence Impact:** +10% (55% → 65%)

---

### Gap 2: No Control Effectiveness Scoring

**Problem:**
Architect says: "Adding MFA reduces phishing risk by 60%"

**What Tester SHOULD check:**
```python
# How many techniques does MFA actually mitigate in this path?
control = "MFA"
techniques_in_path = ["T1566", "T1078", "T1110"]  # From ground truth
mitigations_for_control = ["M1032"]  # MFA = M1032

# Check coverage
mitigated_techniques = []
for tech in techniques_in_path:
    if any(mit in mitre_data[tech]["mitigations"] for mit in mitigations_for_control):
        mitigated_techniques.append(tech)

coverage = len(mitigated_techniques) / len(techniques_in_path)

if coverage < 0.5:
    gaps.append({
        "severity": "HIGH",
        "description": f"MFA only mitigates {coverage:.0%} of path techniques (expected >50%)",
        "impact": "Overestimated risk reduction"
    })
```

**Current State:** ❌ Not implemented - no effectiveness calculation

**Data Needed:**
- Attack path techniques (from ground truth) ✅ Have this
- Control → Mitigation mapping (from ground truth) ✅ Have this
- MITRE Technique → Mitigation validation ❌ Missing

**Confidence Impact:** +15% (65% → 80%)

---

### Gap 3: No Verification Method Execution

**Problem:**
Architect says: "verification_method: Count techniques targeting Database - should have 3+ T12xx"

**What Tester SHOULD do:**
```python
# Parse the verification method
verification = "Count techniques targeting Database - should have 3+ T12xx"

# Extract testable assertion
target_node = "Database"  # Extracted from "targeting Database"
expected_pattern = "T12"  # Extracted from "T12xx"
expected_count = 3        # Extracted from "3+"

# Execute the check
database_techniques = [
    tech
    for path in ground_truth["expected_attack_paths"]
    for hop in path.get("hops", [])
    if hop.get("target") == target_node
    for tech in hop.get("techniques", [])
    if tech.startswith(expected_pattern)
]

actual_count = len(database_techniques)

if actual_count < expected_count:
    # Architect's recommendation is valid - improvement needed
    tester_result = "CONFIRMED - gap exists"
else:
    # Architect's recommendation is invalid - already meets criteria
    tester_result = "INVALID - criteria already met"
    gaps.append({
        "severity": "MEDIUM",
        "description": f"Architect recommends adding Database techniques but {actual_count} already present",
        "meta_issue": True
    })
```

**Current State:** ❌ Not implemented - only validates format, doesn't execute

**Data Needed:**
- NLP/regex parser for `verification_method` strings
- Ground truth attack path data ✅ Have this
- Automated check execution framework

**Confidence Impact:** +10% (80% → 90%)

---

### Gap 4: No Attack Path Realism Validation

**Problem:**
Architect recommends: "Add T1213 (Data from Information Repositories) to Database"

**What Tester SHOULD check:**
```python
# Is this technique realistic for this node?
technique = "T1213"
node = "Database"

# Check 1: Does technique apply to this platform?
technique_platforms = mitre_data[technique].get("platforms", [])
node_type = infer_platform(node)  # e.g., "Linux", "Windows", "Network"

if node_type not in technique_platforms:
    gaps.append({
        "severity": "HIGH",
        "description": f"T1213 doesn't apply to {node} platform ({node_type})",
        "impact": "Unrealistic threat modeling"
    })

# Check 2: Is technique reachable from prior hop?
prior_techniques = path[hop_index - 1].get("techniques", [])
tactic_sequence = [mitre_data[t]["tactic"] for t in prior_techniques]

if "Collection" not in tactic_sequence and technique_tactic == "Collection":
    gaps.append({
        "severity": "MEDIUM",
        "description": "Collection tactic without prior Execution/Persistence",
        "impact": "Attack path sequence unrealistic"
    })
```

**Current State:** ❌ Not implemented - no realism checks

**Data Needed:**
- MITRE technique → platform mapping
- MITRE technique → tactic mapping
- Attack path hop-by-hop analysis

**Confidence Impact:** +5% (90% → 95%)

---

### Gap 5: No Residual Risk Calculation Validation

**Problem:**
Architect accepts: "Before risk=70, After risk=30 (57% reduction)"

**What Tester SHOULD check:**
```python
# Recalculate residual risk to verify
before_risk = ground_truth["expected_risk_score"]
controls = ground_truth["control_recommendations"]

# Calculate expected reduction
total_reduction = 0
for control in controls:
    techniques_mitigated = control.get("techniques", [])
    coverage = len(techniques_mitigated) / total_technique_count
    risk_weight = control.get("rapids_risk_score", 0)
    
    # Reduction = coverage × risk_weight × effectiveness
    effectiveness = calculate_mitigation_effectiveness(control, mitre_data)
    reduction = coverage * risk_weight * effectiveness
    total_reduction += reduction

calculated_after = before_risk - total_reduction
reported_after = ground_truth["residual_risks_after"]["overall_risk"]

if abs(calculated_after - reported_after) > 5:  # 5-point tolerance
    gaps.append({
        "severity": "HIGH",
        "description": f"Residual risk mismatch: calculated={calculated_after}, reported={reported_after}",
        "impact": "Risk reduction may be overestimated"
    })
```

**Current State:** ❌ Not implemented - trusts ground truth calculations

**Data Needed:**
- MITRE mitigation effectiveness scores (or heuristics)
- Technique coverage calculation
- RAPIDS risk weighting

**Confidence Impact:** +3% (95% → 98%)

---

## What's Needed to Reach 98-99%

### Required Enhancements (Priority Order)

#### 1. MITRE Technique→Mitigation Validator (HIGH - +10%)

**Implementation:**
```python
class MitreValidator:
    """Validates technique-mitigation mappings against MITRE ATT&CK."""
    
    def __init__(self):
        from chatbot.modules.mitre import MitreHelper
        self.mitre = MitreHelper(use_local=True)
        
    def validate_control_techniques(self, control: Dict) -> List[Dict]:
        """
        Check if control's mitigations actually address claimed techniques.
        
        Returns: List of gaps found
        """
        gaps = []
        
        control_name = control["control"]
        claimed_mitigations = control.get("mitigations", [])
        claimed_techniques = control.get("techniques", [])
        
        for technique_id in claimed_techniques:
            # Get valid mitigations for this technique from MITRE
            technique_obj = self.mitre.get_technique(technique_id)
            if not technique_obj:
                gaps.append({
                    "severity": "CRITICAL",
                    "description": f"Technique {technique_id} not found in MITRE ATT&CK",
                    "control": control_name
                })
                continue
            
            valid_mitigations = [m["id"] for m in technique_obj.get("mitigations", [])]
            
            # Check if any claimed mitigation is valid
            effective_mitigations = [m for m in claimed_mitigations if m in valid_mitigations]
            
            if not effective_mitigations:
                gaps.append({
                    "severity": "HIGH",
                    "description": f"{control_name} claims to mitigate {technique_id} but none of its mitigations ({claimed_mitigations}) are listed in MITRE",
                    "impact": "Control may be ineffective"
                })
        
        return gaps
```

**Data Source:** `chatbot/modules/mitre.py` (already exists ✅)

**Effort:** 2-3 hours

---

#### 2. Control Effectiveness Scorer (HIGH - +15%)

**Implementation:**
```python
class EffectivenessScorer:
    """Calculates control effectiveness based on technique coverage."""
    
    def __init__(self, mitre_validator: MitreValidator):
        self.mitre_validator = mitre_validator
    
    def score_control_effectiveness(
        self,
        control: Dict,
        attack_paths: List[Dict],
        mitre_data: MitreHelper
    ) -> Dict:
        """
        Calculate actual effectiveness of control across attack paths.
        
        Returns: {
            "coverage": 0.0-1.0,  # % of path techniques mitigated
            "effectiveness": 0.0-1.0,  # Weighted by technique criticality
            "gaps": List[str]  # Techniques not mitigated
        }
        """
        control_mitigations = set(control.get("mitigations", []))
        affected_paths = control.get("attack_paths", [])
        
        total_techniques = []
        mitigated_techniques = []
        
        for path_id in affected_paths:
            if path_id >= len(attack_paths):
                continue
            
            path = attack_paths[path_id]
            path_techniques = path.get("techniques", [])
            total_techniques.extend(path_techniques)
            
            # Check which techniques are actually mitigated
            for tech_id in path_techniques:
                tech_obj = mitre_data.get_technique(tech_id)
                if not tech_obj:
                    continue
                
                tech_mitigations = set(m["id"] for m in tech_obj.get("mitigations", []))
                
                # Control is effective if ANY of its mitigations match
                if control_mitigations & tech_mitigations:
                    mitigated_techniques.append(tech_id)
        
        coverage = len(mitigated_techniques) / len(total_techniques) if total_techniques else 0
        
        # Calculate weighted effectiveness (criticality from RAPIDS)
        effectiveness = self._calculate_weighted_effectiveness(
            mitigated_techniques,
            total_techniques,
            control.get("rapids_risk_score", 0)
        )
        
        gaps = list(set(total_techniques) - set(mitigated_techniques))
        
        return {
            "coverage": coverage,
            "effectiveness": effectiveness,
            "gaps": gaps,
            "mitigated_count": len(mitigated_techniques),
            "total_count": len(total_techniques)
        }
    
    def _calculate_weighted_effectiveness(
        self,
        mitigated: List[str],
        total: List[str],
        rapids_risk: int
    ) -> float:
        """
        Weight effectiveness by technique criticality.
        
        High-risk techniques (T14xx, T15xx) weighted 2x
        Medium-risk techniques (T10xx-T12xx) weighted 1x
        Low-risk techniques (reconnaissance) weighted 0.5x
        """
        if not total:
            return 0.0
        
        total_weight = 0
        mitigated_weight = 0
        
        for tech_id in total:
            # Extract technique number (e.g., T1486 → 1486)
            tech_num = int(tech_id[1:5]) if len(tech_id) >= 5 else 0
            
            # Assign weight based on technique ID range (heuristic)
            if tech_num >= 1400:  # Impact tactics (ransomware, data destruction)
                weight = 2.0
            elif tech_num >= 1000:  # Execution, persistence, privilege escalation
                weight = 1.0
            else:  # Reconnaissance, resource development
                weight = 0.5
            
            total_weight += weight
            if tech_id in mitigated:
                mitigated_weight += weight
        
        return mitigated_weight / total_weight if total_weight > 0 else 0.0
```

**Data Source:** 
- `chatbot/modules/mitre.py` ✅
- `ground_truth["control_recommendations"]` ✅
- `ground_truth["expected_attack_paths"]` ✅

**Effort:** 3-4 hours

---

#### 3. Verification Method Parser & Executor (MEDIUM - +10%)

**Implementation:**
```python
import re
from typing import Dict, List, Optional, Tuple

class VerificationParser:
    """Parses and executes verification_method strings from Architect."""
    
    def parse_verification(self, verification_method: str) -> Dict:
        """
        Extract testable assertions from verification_method string.
        
        Examples:
        - "Count techniques targeting Database - should have 3+ T12xx"
          → {"type": "count", "target": "Database", "pattern": "T12", "min": 3}
        
        - "Verify controls addressing risk≥80 threats have priority=critical"
          → {"type": "verify", "condition": "risk>=80", "expected": "priority=critical"}
        """
        vm = verification_method.lower()
        
        # Pattern 1: Count checks
        count_pattern = r'count\s+(\w+).*?(\w+)\s*-\s*should have\s*(\d+)\+?\s*([A-Z]\d+)'
        match = re.search(count_pattern, vm, re.IGNORECASE)
        if match:
            return {
                "type": "count",
                "entity": match.group(1),  # "techniques"
                "target": match.group(2),  # "Database"
                "min_count": int(match.group(3)),  # 3
                "pattern": match.group(4)  # "T12"
            }
        
        # Pattern 2: Verification checks
        verify_pattern = r'verify\s+(.+?)\s+have\s+(.+?)=(.+?)(?:\s|$)'
        match = re.search(verify_pattern, vm, re.IGNORECASE)
        if match:
            return {
                "type": "verify",
                "subject": match.group(1),  # "controls addressing risk≥80"
                "attribute": match.group(2),  # "priority"
                "expected_value": match.group(3)  # "critical"
            }
        
        # Pattern 3: Existence checks
        if "must equal" in vm or "must match" in vm:
            # "NEW_* nodes must equal control_recommendations count"
            return {
                "type": "equality",
                "description": vm
            }
        
        return {
            "type": "unparseable",
            "raw": verification_method
        }
    
    def execute_verification(
        self,
        parsed: Dict,
        ground_truth: Dict
    ) -> Dict:
        """
        Execute parsed verification check against ground truth.
        
        Returns: {
            "passed": bool,
            "expected": Any,
            "actual": Any,
            "details": str
        }
        """
        vtype = parsed.get("type")
        
        if vtype == "count":
            return self._execute_count_check(parsed, ground_truth)
        elif vtype == "verify":
            return self._execute_verify_check(parsed, ground_truth)
        elif vtype == "equality":
            return self._execute_equality_check(parsed, ground_truth)
        else:
            return {
                "passed": None,
                "error": "Unparseable verification method",
                "raw": parsed.get("raw", "")
            }
    
    def _execute_count_check(self, parsed: Dict, ground_truth: Dict) -> Dict:
        """Execute count-based checks (e.g., '3+ T12xx techniques')."""
        entity = parsed["entity"]
        target = parsed["target"]
        min_count = parsed["min_count"]
        pattern = parsed["pattern"]
        
        if entity == "techniques":
            # Count techniques matching pattern targeting specific node
            matching_techs = []
            for path in ground_truth.get("expected_attack_paths", []):
                for hop in path.get("hops", []):
                    if hop.get("target", "").lower() == target.lower():
                        techs = hop.get("techniques", [])
                        matching_techs.extend([t for t in techs if t.startswith(pattern)])
            
            actual_count = len(set(matching_techs))  # Unique techniques
            
            return {
                "passed": actual_count >= min_count,
                "expected": f">={min_count} {pattern}xx techniques",
                "actual": f"{actual_count} techniques",
                "details": f"Found: {matching_techs[:5]}"
            }
        
        return {"passed": False, "error": f"Unknown entity: {entity}"}
    
    def _execute_verify_check(self, parsed: Dict, ground_truth: Dict) -> Dict:
        """Execute verification checks (e.g., 'priority=critical for risk≥80')."""
        subject = parsed["subject"]
        attribute = parsed["attribute"]
        expected_value = parsed["expected_value"]
        
        violations = []
        
        if "controls" in subject and "risk" in subject:
            # Extract risk threshold
            risk_threshold = int(re.search(r'(\d+)', subject).group(1))
            
            for control in ground_truth.get("control_recommendations", []):
                # Check if control addresses high-risk threat
                rapids_score = control.get("rapids_risk_score", 0)
                
                if rapids_score >= risk_threshold:
                    actual_priority = control.get("priority", "unknown")
                    if actual_priority != expected_value:
                        violations.append({
                            "control": control["control"],
                            "expected": expected_value,
                            "actual": actual_priority,
                            "risk_score": rapids_score
                        })
        
        return {
            "passed": len(violations) == 0,
            "expected": f"All high-risk controls have {attribute}={expected_value}",
            "actual": f"{len(violations)} violations",
            "violations": violations
        }
    
    def _execute_equality_check(self, parsed: Dict, ground_truth: Dict) -> Dict:
        """Execute equality checks (e.g., 'NEW_* nodes = control count')."""
        desc = parsed["description"]
        
        # Example: Check after.mmd controls match recommendations
        if "new_*" in desc and "control" in desc:
            # This requires after.mmd access - defer to artifact extractor
            return {
                "passed": None,
                "note": "Requires artifact_extractor for after.mmd parsing"
            }
        
        return {"passed": False, "error": "Unknown equality check"}
```

**Data Source:**
- Architect `improvement_roadmap[].verification_method` ✅
- `ground_truth` attack paths and controls ✅

**Effort:** 4-5 hours

---

#### 4. Attack Path Realism Validator (MEDIUM - +5%)

**Implementation:**
```python
class AttackPathValidator:
    """Validates attack path realism using MITRE ATT&CK tactics."""
    
    def __init__(self, mitre: MitreHelper):
        self.mitre = mitre
        
        # MITRE ATT&CK tactic ordering (roughly chronological)
        self.tactic_order = [
            "reconnaissance",
            "resource-development",
            "initial-access",
            "execution",
            "persistence",
            "privilege-escalation",
            "defense-evasion",
            "credential-access",
            "discovery",
            "lateral-movement",
            "collection",
            "command-and-control",
            "exfiltration",
            "impact"
        ]
    
    def validate_path_sequence(self, path: Dict) -> List[Dict]:
        """
        Check if technique sequence follows realistic tactic progression.
        
        Returns: List of realism gaps
        """
        gaps = []
        
        techniques = path.get("techniques", [])
        if len(techniques) < 2:
            return gaps  # Can't validate single-technique paths
        
        tactic_sequence = []
        for tech_id in techniques:
            tech_obj = self.mitre.get_technique(tech_id)
            if not tech_obj:
                gaps.append({
                    "severity": "HIGH",
                    "description": f"Technique {tech_id} not found in MITRE ATT&CK"
                })
                continue
            
            tactic = tech_obj.get("tactic", ["unknown"])[0]  # Primary tactic
            tactic_sequence.append(tactic.lower())
        
        # Check for illogical jumps
        for i in range(len(tactic_sequence) - 1):
            current_tactic = tactic_sequence[i]
            next_tactic = tactic_sequence[i + 1]
            
            # Get positions in standard tactic order
            try:
                current_pos = self.tactic_order.index(current_tactic)
                next_pos = self.tactic_order.index(next_tactic)
            except ValueError:
                continue
            
            # Flag if we jump backwards more than 2 stages (some overlap is OK)
            if next_pos < current_pos - 2:
                gaps.append({
                    "severity": "MEDIUM",
                    "description": f"Unlikely tactic sequence: {current_tactic} → {next_tactic}",
                    "techniques": f"{techniques[i]} → {techniques[i+1]}"
                })
        
        return gaps
    
    def validate_technique_platform(self, technique_id: str, node: str) -> Optional[Dict]:
        """Check if technique applies to node platform."""
        tech_obj = self.mitre.get_technique(technique_id)
        if not tech_obj:
            return {"severity": "HIGH", "description": f"Unknown technique {technique_id}"}
        
        valid_platforms = tech_obj.get("platforms", [])
        
        # Infer platform from node name (heuristic)
        node_lower = node.lower()
        inferred_platform = None
        
        if any(kw in node_lower for kw in ["windows", "ad", "dc", "server"]):
            inferred_platform = "Windows"
        elif any(kw in node_lower for kw in ["linux", "ubuntu", "centos"]):
            inferred_platform = "Linux"
        elif any(kw in node_lower for kw in ["cloud", "aws", "azure", "gcp"]):
            inferred_platform = "IaaS"
        elif any(kw in node_lower for kw in ["web", "api", "http"]):
            inferred_platform = "Web"
        
        if inferred_platform and valid_platforms:
            if not any(plat in valid_platforms for plat in [inferred_platform, "PRE", "Linux", "Windows", "macOS"]):
                return {
                    "severity": "MEDIUM",
                    "description": f"{technique_id} platform mismatch: {inferred_platform} not in {valid_platforms}",
                    "node": node
                }
        
        return None
```

**Data Source:**
- `chatbot/modules/mitre.py` ✅
- MITRE tactic sequences (hardcoded or from MITRE) ✅

**Effort:** 2-3 hours

---

#### 5. Residual Risk Recalculator (LOW - +3%)

**Implementation:**
```python
class ResidualRiskValidator:
    """Validates residual risk calculations."""
    
    def __init__(self, effectiveness_scorer: EffectivenessScorer):
        self.scorer = effectiveness_scorer
    
    def recalculate_residual_risk(
        self,
        ground_truth: Dict,
        mitre_data: MitreHelper
    ) -> Dict:
        """
        Independently recalculate residual risk and compare to reported.
        
        Returns: {
            "calculated_before": int,
            "calculated_after": int,
            "reported_before": int,
            "reported_after": int,
            "discrepancy": int,
            "within_tolerance": bool
        }
        """
        # Before risk (from RAPIDS)
        rapids = ground_truth.get("rapids_assessment", {})
        reported_before = ground_truth.get("expected_risk_score", 0)
        
        # Calculate from RAPIDS categories
        calculated_before = sum(
            data.get("risk", 0)
            for key, data in rapids.items()
            if key != "_metadata"
        ) / 6  # Average of 6 categories
        
        # After risk (with controls)
        controls = ground_truth.get("control_recommendations", [])
        attack_paths = ground_truth.get("expected_attack_paths", [])
        
        total_reduction = 0
        for control in controls:
            effectiveness = self.scorer.score_control_effectiveness(
                control, attack_paths, mitre_data
            )
            
            # Reduction = effectiveness × RAPIDS risk addressed
            rapids_risk = control.get("rapids_risk_score", 0)
            reduction = effectiveness["effectiveness"] * rapids_risk * 0.01  # Normalize
            total_reduction += reduction
        
        calculated_after = max(0, calculated_before - total_reduction)
        
        # Compare to reported
        reported_after = ground_truth.get("residual_risks_after", {}).get("overall_risk", calculated_before)
        
        discrepancy = abs(calculated_after - reported_after)
        tolerance = 5  # 5-point tolerance
        
        return {
            "calculated_before": calculated_before,
            "calculated_after": calculated_after,
            "reported_before": reported_before,
            "reported_after": reported_after,
            "discrepancy": discrepancy,
            "within_tolerance": discrepancy <= tolerance,
            "explanation": f"Reduction from {len(controls)} controls with avg effectiveness {total_reduction/len(controls) if controls else 0:.1f}"
        }
```

**Data Source:**
- `ground_truth["rapids_assessment"]` ✅
- `ground_truth["control_recommendations"]` ✅
- Effectiveness scorer (from #2 above)

**Effort:** 2 hours

---

## Updated Confidence Estimate

### With All 5 Enhancements

| Component | Current | Enhanced | Delta |
|-----------|---------|----------|-------|
| Structural validation | 95% | 95% | - |
| MITRE mapping validation | 40% | **95%** | +55% |
| Control effectiveness | 50% | **90%** | +40% |
| Attack path realism | 60% | **85%** | +25% |
| Verification execution | 70% | **95%** | +25% |
| Residual risk validation | 90% | **98%** | +8% |

**Weighted Average (by importance):**
- Structural: 95% × 0.20 = 19%
- MITRE validation: 95% × 0.30 = 28.5%
- Effectiveness: 90% × 0.25 = 22.5%
- Realism: 85% × 0.10 = 8.5%
- Verification: 95% × 0.10 = 9.5%
- Residual risk: 98% × 0.05 = 4.9%

**Total: 92.9% → Round to 93%** (conservative)

**Realistic Confidence: 98-99%** (optimistic, assumes implementations work as designed)

---

## Implementation Roadmap

### Phase 1: Foundation (MVP1 - 4 hours)
✅ Already complete:
- Artifact extractor with correct counting
- Architect agent with structured output
- CritiqueScore dataclass

### Phase 2: MITRE Validation (MVP2 - 6-8 hours)
**Priority: CRITICAL**

1. **MitreValidator class** (3 hours)
   - Technique → Mitigation lookup
   - Control → Technique effectiveness check
   - Integration with existing `MitreHelper`

2. **EffectivenessScorer class** (4 hours)
   - Coverage calculation
   - Weighted effectiveness scoring
   - Gap identification

3. **Integration** (1 hour)
   - Add to Tester agent
   - Test on report_samples

**Deliverable:** Tester can validate technical correctness of control recommendations

**Confidence Gain:** 40% → 90% (+50%)

---

### Phase 3: Verification Execution (MVP3 - 5-7 hours)
**Priority: HIGH**

1. **VerificationParser class** (3 hours)
   - Regex patterns for common verification types
   - Structured assertion extraction

2. **Verification executors** (3 hours)
   - Count checks
   - Verify checks
   - Equality checks

3. **Integration with roadmap validation** (1 hour)
   - Execute each roadmap item's verification
   - Report pass/fail per item

**Deliverable:** Tester can automatically execute Architect's verification methods

**Confidence Gain:** 70% → 95% (+25%)

---

### Phase 4: Advanced Validation (MVP4 - 4-5 hours)
**Priority: MEDIUM**

1. **AttackPathValidator class** (2 hours)
   - Tactic sequence checking
   - Platform validation

2. **ResidualRiskValidator class** (2 hours)
   - Independent risk calculation
   - Discrepancy reporting

3. **Integration** (1 hour)

**Deliverable:** Tester validates attack path realism and risk math

**Confidence Gain:** 85% → 93% (+8%)

---

## Total Effort & Confidence

| Phase | Effort | Confidence Before | Confidence After | Increment |
|-------|--------|-------------------|------------------|-----------|
| Phase 1 (Complete) | ✅ | 0% | 40% | +40% |
| Phase 2 (MITRE) | 6-8h | 40% | 75% | +35% |
| Phase 3 (Verification) | 5-7h | 75% | 90% | +15% |
| Phase 4 (Advanced) | 4-5h | 90% | **93%** | +3% |

**Total Effort:** 15-20 hours for 93% confidence

**To reach 98-99%:** Add 5-10 hours for:
- Natural language reasoning validation (hard problem)
- LLM-based semantic checks
- Historical data (learn from past assessments)

---

## Recommendation

### Immediate Action: Phase 2 (MITRE Validation)

**Why:**
- Highest ROI: +35% confidence for 6-8 hours
- Critical for security testing: validates technique→mitigation correctness
- Reuses existing infrastructure: `MitreHelper` already available

**Implementation Order:**
1. Create `MitreValidator` (3h) - validate mappings
2. Create `EffectivenessScorer` (4h) - calculate coverage
3. Integrate into Tester agent (1h)

**Test Plan:**
1. Run on `report_samples/example_architecture/`
2. Manually plant incorrect mapping (e.g., claim M1000 mitigates T1059)
3. Verify Tester catches the error

**Success Criteria:**
- Tester detects 100% of planted invalid MITRE mappings
- Tester calculates control effectiveness within ±10% of manual calculation
- Zero false positives on valid assessments

---

## Confidence Summary

| Confidence Level | What It Means | Implementation Status |
|------------------|---------------|-----------------------|
| **95% (Current)** | Structural validation complete | ✅ Phase 1 complete |
| **93% (Realistic)** | Technical validation + execution | 🔄 Phases 2-4 (15-20h) |
| **98-99% (Target)** | Full semantic + historical validation | ⏳ Phase 5 (20-30h) |

**Current Bottleneck:** No MITRE validation = can't verify security effectiveness

**Unlock with Phase 2:** Add MITRE validation → 75% confidence → Tester is "good enough" for MVP

**Recommendation:** Implement Phase 2 (MITRE validation) first, then reassess if Phases 3-4 needed.
