#!/usr/bin/env python3
"""
Red Teamer Confidence Check - Phase 1

Tests if LLM can assess exploit difficulty correctly with inverted scoring.
"""

import json
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from chatbot.modules.artifact_extractor import extract_artifacts
from agentic.llm_client import LLMClient


def load_ground_truth(report_dir: str) -> dict:
    """Load ground_truth.json from report directory."""
    gt_path = Path(report_dir) / "ground_truth.json"
    with open(gt_path) as f:
        return json.load(f)


def create_red_team_prompt_v1(artifacts, ground_truth: dict) -> str:
    """
    Minimal Red Team prompt for confidence check.

    Focus: Can LLM assess exploit difficulty with inverted scoring?
    """

    paths = artifacts.tier1_critical['artifact_1_attack_paths']['paths']

    # Get DEPLOYED controls from ground truth
    controls_present = ground_truth.get('controls_present', [])

    # Create set of deployed control names (lowercase)
    deployed_controls = set(c.lower() for c in controls_present)

    prompt = f"""You are a Red Team assessor evaluating exploit difficulty from an attacker's perspective.

IMPORTANT: This uses INVERTED scoring:
- LOW score (0-40) = Hard to exploit = GOOD defense ✅
- HIGH score (60-100) = Easy to exploit = BAD defense ❌

DEPLOYED CONTROLS (what's actually protecting this architecture):
{', '.join(controls_present) if controls_present else 'NONE - Architecture is completely vulnerable!'}

ATTACK PATHS ({len(paths)} paths):
"""

    for i, path in enumerate(paths, 1):
        prompt += f"\nPath #{i}: {' → '.join(path['path'])}\n"
        prompt += f"  Techniques: {', '.join(path.get('techniques', [])[:5])}\n"

    prompt += """

TASK: Assess overall exploit difficulty (0-100 scale)

Consider:
1. Path complexity: More hops = harder to exploit
2. Controls present: WAF, MFA, EDR block common attacks
3. Public tool availability: Can Metasploit/Burp Suite work?
4. Skill required: Script kiddie / Professional / APT?

SCORING GUIDE (INVERTED):
- 0-20: Nearly impossible (multiple strong controls, no known bypasses)
- 21-40: Very difficult (strong controls like MFA+EDR, requires APT-level skills)
- 41-60: Difficult (moderate controls like basic firewall, requires professional skills)
- 61-80: Moderate (weak/few controls, public tools work with some skill)
- 81-100: Trivial (NO controls or bypassed controls, script kiddie level)

EXAMPLES:

Example 1: Architecture with NO controls
Deployed controls: NONE
Path: Internet → Web Server → Database
Analysis: No firewall, no authentication, direct database access
Score: 85/100 (CRITICAL - Trivial to exploit with Metasploit)
Rating: CRITICAL = Easy to exploit = BAD defense

Example 2: Architecture with STRONG controls
Deployed controls: WAF, MFA, EDR, Encryption
Path: Internet → WAF → ALB → MFA → Web Server (EDR) → Database (Encrypted)
Analysis: WAF blocks exploits, MFA blocks auth bypass, EDR detects malware
Score: 25/100 (LOW - Very difficult, requires APT-level skills)
Rating: LOW = Hard to exploit = GOOD defense

YOUR ANALYSIS:
Assess overall exploit difficulty based ONLY on deployed controls listed above.
DO NOT assume controls that aren't listed. If no controls are deployed, score should be HIGH (70-90).

Output JSON:

{
  "overall_difficulty": <int 0-100>,
  "rating": "<MINIMAL/LOW/MEDIUM/HIGH/CRITICAL> = <easy/hard> to exploit = <GOOD/BAD> defense",
  "reasoning": "<1-2 sentences explaining the score>",
  "path_assessments": [
    {
      "path_id": 1,
      "difficulty": <int 0-100>,
      "key_controls": ["control1", "control2"],
      "bypass_difficulty": "<EASY/MODERATE/HARD/VERY_HARD>"
    }
  ]
}

REMEMBER: Low score = hard to exploit = GOOD defense (we want this!)
"""

    return prompt


def run_confidence_check(report_dir: str, expected_range: tuple) -> dict:
    """
    Run confidence check on a single architecture.

    Args:
        report_dir: Path to report directory
        expected_range: (min, max) expected difficulty score

    Returns:
        dict with score, confidence, and assessment
    """
    print(f"\n{'='*70}")
    print(f"Testing: {report_dir}")
    print(f"Expected difficulty: {expected_range[0]}-{expected_range[1]}")
    print(f"{'='*70}\n")

    # Load ground truth for controls_present
    ground_truth = load_ground_truth(report_dir)

    # Extract artifacts
    artifacts = extract_artifacts(report_dir)

    # Create prompt
    prompt = create_red_team_prompt_v1(artifacts, ground_truth)

    # Call LLM
    client = LLMClient()
    response = client.generate(
        prompt=prompt,
        system_message="You are a Red Team assessor evaluating exploit difficulty.",
        model=None,  # Use .env defaults
        temperature=0.3,
        max_tokens=2000
    )

    print(f"LLM Response:\n{response.content}\n")

    # Parse response
    try:
        # Try to extract JSON from response
        content = response.content.strip()
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        result = json.loads(content)
        score = result.get("overall_difficulty", -1)

        # Check if in expected range
        in_range = expected_range[0] <= score <= expected_range[1]

        assessment = {
            "score": score,
            "expected_range": expected_range,
            "in_range": in_range,
            "rating": result.get("rating", "UNKNOWN"),
            "reasoning": result.get("reasoning", ""),
            "confidence": "HIGH" if in_range else "LOW"
        }

        print(f"✅ Parsed score: {score}/100")
        print(f"   Expected: {expected_range[0]}-{expected_range[1]}")
        print(f"   In range: {'✅ YES' if in_range else '❌ NO'}")
        print(f"   Rating: {result.get('rating', 'UNKNOWN')}")
        print(f"   Reasoning: {result.get('reasoning', 'N/A')}")

        return assessment

    except Exception as e:
        print(f"❌ Failed to parse LLM response: {e}")
        return {
            "score": -1,
            "expected_range": expected_range,
            "in_range": False,
            "error": str(e),
            "confidence": "FAILED"
        }


def main():
    """
    Run confidence check on defended architecture.

    Success criteria:
    - Score should be 20-40 (VERY DIFFICULT = GOOD defense)
    - Rating should be LOW or MINIMAL
    - Reasoning should mention controls (WAF, MFA, EDR)
    """

    print("="*70)
    print("RED TEAMER CONFIDENCE CHECK - Phase 1")
    print("="*70)
    print("\nGoal: Verify LLM can assess exploit difficulty with inverted scoring")
    print("\nInverted scoring:")
    print("  • Low score (0-40) = Hard to exploit = GOOD defense ✅")
    print("  • High score (60-100) = Easy to exploit = BAD defense ❌")
    print()

    # Test defended architecture
    result = run_confidence_check(
        report_dir="report/02_minimal_defended",
        expected_range=(20, 40)  # VERY DIFFICULT = GOOD defense
    )

    print("\n" + "="*70)
    print("CONFIDENCE CHECK RESULT")
    print("="*70)

    if result["in_range"]:
        print("\n✅ PASS - LLM correctly assessed exploit difficulty!")
        print(f"   Score: {result['score']}/100 (LOW = Hard to exploit = GOOD defense)")
        print(f"   Confidence: HIGH")
        print("\n   ➡️  Proceed to Step 2: Vulnerable vs Defended contrast test")
        return 0
    else:
        print("\n⚠️  NEEDS ADJUSTMENT - Score outside expected range")
        print(f"   Score: {result['score']}/100")
        print(f"   Expected: {result['expected_range'][0]}-{result['expected_range'][1]}")
        print(f"   Confidence: LOW")
        print("\n   ➡️  Need to add more examples or adjust prompt")
        return 1


if __name__ == "__main__":
    sys.exit(main())
