# Red Teamer: Post-Processing Validation Specification

**Date:** 2026-05-16  
**Purpose:** Safety net to catch hallucinations  
**Time:** 1 hour implementation  
**Similar to:** Tester's `_validate_gaps()` method

---

## What to Validate

### Check 1: Control Existence ✅
```python
def _validate_control_claims(self, score: CritiqueScore, ground_truth: dict) -> list:
    """
    Verify Red Team only mentions controls that actually exist.
    
    Example hallucination:
    - Claimed: ["waf", "mfa", "ids"]
    - Actual: ["waf", "mfa"]
    - Hallucinated: ["ids"] ← Not deployed!
    """
    
    controls_present = set(c.lower() for c in ground_truth.get("controls_present", []))
    
    false_positives = []
    
    # Check path assessments for claimed controls
    for path in score.breakdown.get("path_assessments", []):
        claimed = path.get("key_controls", [])
        for ctrl in claimed:
            if ctrl.lower() not in controls_present:
                false_positives.append({
                    "path_id": path["path_id"],
                    "claimed_control": ctrl,
                    "issue": f"Control '{ctrl}' not in deployed controls"
                })
    
    return false_positives
```

**Action:** Remove false control claims from path assessments

---

### Check 2: Difficulty Score Reasonableness ✅
```python
def _validate_difficulty_score(self, score: int, ground_truth: dict) -> dict:
    """
    Check if difficulty score makes sense given control count.
    
    Heuristic:
    - 0 controls: 80-90 (CRITICAL - easy to exploit)
    - 1-2 controls: 65-80 (HIGH)
    - 3-5 controls: 45-65 (MEDIUM)
    - 6-10 controls: 25-45 (LOW - hard to exploit)
    - 10+ controls: 10-25 (MINIMAL - very hard)
    """
    
    control_count = len(ground_truth.get("controls_present", []))
    
    # Calculate expected range
    if control_count == 0:
        expected_min, expected_max = 80, 90
    elif control_count <= 2:
        expected_min, expected_max = 65, 80
    elif control_count <= 5:
        expected_min, expected_max = 45, 65
    elif control_count <= 10:
        expected_min, expected_max = 25, 45
    else:
        expected_min, expected_max = 10, 25
    
    # Check if score is way off
    if score < expected_min - 20:
        return {
            "issue": "Score too optimistic (rated too hard to exploit)",
            "actual": score,
            "expected_range": (expected_min, expected_max),
            "suggested": expected_min,
            "severity": "MEDIUM"
        }
    elif score > expected_max + 20:
        return {
            "issue": "Score too pessimistic (rated too easy to exploit)",
            "actual": score,
            "expected_range": (expected_min, expected_max),
            "suggested": expected_max,
            "severity": "MEDIUM"
        }
    else:
        return {"valid": True}
```

**Action:** Adjust score toward expected range if >20 points off

---

### Check 3: Tester Gap Integration ✅
```python
def _adjust_for_tester_gaps(self, score: int, tester_critique: CritiqueScore) -> int:
    """
    Increase exploit difficulty if Tester found critical gaps.
    
    Logic:
    - Tester found invalid MITRE mappings
    - Control claims to mitigate T1059 but mapping is invalid
    - T1059 is actually NOT mitigated
    - Attacker can exploit T1059 freely
    - → Increase exploit score (easier to attack)
    
    Example:
    - Base score: 30/100 (hard to exploit)
    - Tester found 3 critical gaps
    - Adjusted: 30 + (3 × 5) = 45/100 (moderate)
    """
    
    if not tester_critique:
        return score
    
    critical_gaps = len([g for g in tester_critique.gaps 
                        if 'CRITICAL' in str(g) or 'invalid' in str(g).lower()])
    
    # Each critical gap makes exploit easier
    adjustment = critical_gaps * 5  # +5 points per gap
    
    adjusted_score = min(100, score + adjustment)
    
    if adjustment > 0:
        logger.info(f"Red Team: Adjusted score {score} → {adjusted_score} "
                   f"(+{adjustment} for {critical_gaps} critical gaps)")
    
    return adjusted_score
```

**Action:** Increase exploit difficulty by 5 points per critical gap

---

### Check 4: Inverted Score Validation ✅
```python
def _validate_inverted_scoring(self, score: CritiqueScore) -> CritiqueScore:
    """
    Ensure LLM understood inverted scoring.
    
    Common mistake: LLM forgets inversion
    - Rates strong defense as 90/100 (thinking high = good)
    - Should be 30/100 (low = good in inverted scale)
    
    Detection:
    - Rating says "GOOD defense" but score is >60
    - Rating says "BAD defense" but score is <40
    """
    
    rating = score.rating.lower()
    actual_score = score.score
    
    # Check for contradiction
    if ("good" in rating or "strong" in rating or "hard" in rating) and actual_score > 60:
        logger.warning(f"Red Team: Inverted scoring error detected - "
                      f"Rating says 'good defense' but score is {actual_score}/100")
        
        # Invert the score
        corrected_score = 100 - actual_score
        score.score = corrected_score
        
        logger.info(f"Red Team: Corrected score {actual_score} → {corrected_score} (inverted)")
    
    elif ("bad" in rating or "weak" in rating or "easy" in rating) and actual_score < 40:
        logger.warning(f"Red Team: Inverted scoring error detected - "
                      f"Rating says 'bad defense' but score is {actual_score}/100")
        
        # Invert the score
        corrected_score = 100 - actual_score
        score.score = corrected_score
        
        logger.info(f"Red Team: Corrected score {actual_score} → {corrected_score} (inverted)")
    
    return score
```

**Action:** Auto-correct if LLM forgot inverted scoring

---

## Implementation Structure

```python
class RedTeamerCritic:
    """
    Red Team critic with post-processing validation.
    """
    
    def critique(self, artifacts, ground_truth, tester_critique=None):
        """
        Main critique workflow with validation.
        """
        
        # 1. Generate initial critique (LLM call)
        raw_score = self._generate_critique(artifacts, ground_truth, tester_critique)
        
        # 2. POST-PROCESSING VALIDATION
        validated_score = self._validate_and_adjust(raw_score, ground_truth, tester_critique)
        
        return validated_score
    
    def _validate_and_adjust(self, score, ground_truth, tester_critique):
        """
        Apply all validation checks.
        """
        
        logger.info("Red Team: Starting post-processing validation...")
        
        # Check 1: Control existence
        false_controls = self._validate_control_claims(score, ground_truth)
        if false_controls:
            logger.warning(f"Red Team: Found {len(false_controls)} false control claims")
            score = self._remove_false_controls(score, false_controls)
        
        # Check 2: Difficulty reasonableness
        difficulty_check = self._validate_difficulty_score(score.score, ground_truth)
        if not difficulty_check.get("valid"):
            logger.warning(f"Red Team: {difficulty_check['issue']}")
            score.score = difficulty_check["suggested"]
        
        # Check 3: Tester gap integration
        if tester_critique:
            score.score = self._adjust_for_tester_gaps(score.score, tester_critique)
        
        # Check 4: Inverted scoring
        score = self._validate_inverted_scoring(score)
        
        logger.info(f"Red Team: Validation complete - Final score: {score.score}/100")
        
        return score
```

---

## Expected Impact

### Before Post-Processing (Potential Issues)
```
Score: 75/100
Issues:
- Claimed "IDS" control (not deployed)
- Score too high for 6 controls (expected 25-45)
- Forgot inverted scoring
```

### After Post-Processing (Fixed)
```
Score: 35/100
Fixes applied:
- Removed "IDS" claim (not in controls_present)
- Adjusted 75 → 35 (control count suggests 25-45)
- Validated inverted scoring (low = good)
```

**Confidence Increase:** 80% → 95% (post-processing safety net)

---

## Success Criteria

✅ **Zero false control claims** - Only mentions deployed controls  
✅ **Reasonable difficulty scores** - Within ±20 of expected range  
✅ **Tester gaps integrated** - Adjusts for invalid mappings  
✅ **Inverted scoring correct** - Low score = good defense

---

## Time Estimate

- Implementation: 1 hour
- Testing (during Orchestrator): 0.5 hour
- **Total: 1.5 hours**

---

## Comparison: With vs Without Few-Shot

| Approach | Time | Confidence | When Issues Found |
|----------|------|------------|-------------------|
| **Post-processing only** | 1h | 90-95% | Auto-fixes programmatically |
| Few-shot (3 examples) | 0.5h | 85-90% | LLM learns patterns |
| Few-shot (5 examples) | 1h | 90-95% | LLM learns edge cases |
| Post-processing + Few-shot | 1.5-2h | 95-98% | Double protection |

**Recommendation:** Post-processing only (1h) is sufficient

---

**Status:** Ready to implement  
**Risk:** Low (simpler than Tester, post-processing proven effective)  
**Confidence:** 90% this alone will prevent hallucinations
