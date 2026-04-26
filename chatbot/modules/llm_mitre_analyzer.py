"""
LLM-enhanced MITRE technique analysis and attack path construction.

This module uses LLM (via OpenRouter) to:
1. Refine and rank semantic search results
2. Construct logical attack paths from matched techniques
3. Generate contextual mitigation advice
4. Explain relevance of techniques to user scenarios

Rate limited to 20 req/min via OpenRouter free tier.
"""

import json
import logging
from typing import List, Dict, Optional, Tuple
from chatbot.modules.rate_limiter import rate_limited
from agentic.llm import generate_response_with_system

logger = logging.getLogger(__name__)


# System prompts for different analysis tasks
SYSTEM_PROMPT_REFINE = """You are a cybersecurity expert specializing in MITRE ATT&CK framework.
Your task is to analyze matched techniques and explain their relevance to the user's scenario.
Be concise, specific, and focus on practical security implications."""

SYSTEM_PROMPT_ATTACK_PATH = """You are a threat intelligence analyst specializing in attack chain analysis.
Your task is to construct logical attack paths showing how an attacker might progress through techniques.
Focus on realistic progression based on MITRE ATT&CK tactics (Initial Access → Execution → Persistence → etc).
Be specific about the sequence and explain why each step enables the next."""

SYSTEM_PROMPT_MITIGATION = """You are a security architect specializing in defense strategies.
Your task is to provide practical, prioritized mitigation advice based on matched MITRE techniques.
Focus on actionable recommendations that address root causes, not just symptoms.
Consider detection, prevention, and response strategies."""


@rate_limited(max_retries=3, base_delay=2.0)
def refine_technique_matches(
    user_query: str,
    matched_techniques: List[Dict],
    top_k: int = 5
) -> List[Dict]:
    """
    Use LLM to refine and rank matched techniques based on relevance.

    Args:
        user_query: Original user query/scenario
        matched_techniques: List of techniques from semantic search with scores
        top_k: Number of most relevant techniques to return

    Returns:
        List of refined technique dicts with LLM-generated relevance explanations:
        [
            {
                "external_id": "T1059.001",
                "name": "PowerShell",
                "similarity_score": 0.856,
                "relevance_explanation": "PowerShell is directly relevant because...",
                "confidence": "high",  # high/medium/low
                ...original fields...
            },
            ...
        ]

    Note:
        - Rate limited to 20 req/min
        - Returns original results if LLM fails (graceful degradation)
    """
    if not matched_techniques:
        logger.warning("No techniques provided for refinement")
        return []

    # Build prompt with matched techniques
    techniques_summary = "\n".join([
        f"- {t['external_id']} ({t['name']}): Similarity score {t['similarity_score']:.3f}"
        for t in matched_techniques[:10]  # Limit to top 10 for token efficiency
    ])

    prompt = f"""User Scenario:
"{user_query}"

Matched MITRE Techniques (from semantic search):
{techniques_summary}

Task:
1. Analyze which techniques are most relevant to this scenario
2. Rank the top {top_k} techniques by relevance
3. For each, provide a brief explanation (1-2 sentences) of WHY it's relevant
4. Rate confidence level: high/medium/low

Return JSON format:
{{
  "refined_techniques": [
    {{
      "external_id": "T1059.001",
      "relevance_explanation": "Brief explanation here...",
      "confidence": "high"
    }},
    ...
  ]
}}
"""

    try:
        logger.info(f"Refining {len(matched_techniques)} techniques with LLM...")

        response = generate_response_with_system(
            prompt=prompt,
            system_message=SYSTEM_PROMPT_REFINE,
            temperature=0.3,  # Lower temperature for more focused analysis
            max_tokens=1500
        )

        # Parse JSON response
        # Handle markdown code blocks if present
        response_clean = response.strip()
        if response_clean.startswith("```json"):
            response_clean = response_clean.split("```json")[1].split("```")[0].strip()
        elif response_clean.startswith("```"):
            response_clean = response_clean.split("```")[1].split("```")[0].strip()

        refined_data = json.loads(response_clean)
        refined_list = refined_data.get("refined_techniques", [])

        # Merge LLM analysis with original technique data
        result = []
        for refined in refined_list:
            ext_id = refined.get("external_id")

            # Find matching technique in original results
            original = next(
                (t for t in matched_techniques if t["external_id"] == ext_id),
                None
            )

            if original:
                # Merge LLM insights with original data
                enriched = original.copy()
                enriched["relevance_explanation"] = refined.get("relevance_explanation", "")
                enriched["confidence"] = refined.get("confidence", "medium")
                result.append(enriched)

        logger.info(f"Refined to {len(result)} most relevant techniques")
        return result[:top_k]

    except Exception as e:
        logger.error(f"LLM refinement failed: {str(e)}")
        logger.warning("Falling back to semantic search ranking only")
        # Graceful fallback: return original results
        return matched_techniques[:top_k]


@rate_limited(max_retries=3, base_delay=2.0)
def generate_attack_path(
    user_query: str,
    matched_techniques: List[Dict]
) -> Dict:
    """
    Construct logical attack path from matched techniques.

    Args:
        user_query: Original user query/scenario
        matched_techniques: List of matched techniques (with tactics)

    Returns:
        Dict with attack path analysis:
        {
            "attack_path": [
                {
                    "stage": "Initial Access",
                    "techniques": ["T1566.001"],
                    "description": "Attacker begins with phishing..."
                },
                {
                    "stage": "Execution",
                    "techniques": ["T1059.001"],
                    "description": "PowerShell executes malicious payload..."
                },
                ...
            ],
            "attack_narrative": "Full narrative explanation...",
            "kill_chain_phases": ["reconnaissance", "weaponization", ...]
        }

    Note:
        - Rate limited to 20 req/min
        - Returns simplified structure if LLM fails
    """
    if not matched_techniques:
        logger.warning("No techniques provided for attack path construction")
        return {
            "attack_path": [],
            "attack_narrative": "No techniques available for analysis.",
            "kill_chain_phases": []
        }

    # Build prompt with technique details
    techniques_detail = []
    for t in matched_techniques[:10]:  # Limit for token efficiency
        tactics = ", ".join(t.get("tactics", []))
        techniques_detail.append(
            f"- {t['external_id']} ({t['name']})\n"
            f"  Tactics: {tactics}\n"
            f"  Description: {t.get('description', '')[:200]}..."
        )

    techniques_text = "\n".join(techniques_detail)

    prompt = f"""User Scenario:
"{user_query}"

Matched MITRE ATT&CK Techniques:
{techniques_text}

Task:
Construct a logical attack path showing how an attacker might progress through these techniques.

1. Group techniques by MITRE tactic stages (Initial Access, Execution, Persistence, etc.)
2. Order stages in a realistic attack progression
3. For each stage, explain what the attacker is doing and why
4. Create a narrative that ties everything together

Return JSON format:
{{
  "attack_path": [
    {{
      "stage": "Initial Access",
      "techniques": ["T1566.001"],
      "description": "Brief explanation of what happens in this stage..."
    }},
    ...
  ],
  "attack_narrative": "A cohesive narrative explaining the full attack chain...",
  "kill_chain_phases": ["reconnaissance", "weaponization", "delivery", ...]
}}
"""

    try:
        logger.info("Generating attack path with LLM...")

        response = generate_response_with_system(
            prompt=prompt,
            system_message=SYSTEM_PROMPT_ATTACK_PATH,
            temperature=0.4,
            max_tokens=2000
        )

        # Parse JSON response
        response_clean = response.strip()
        if response_clean.startswith("```json"):
            response_clean = response_clean.split("```json")[1].split("```")[0].strip()
        elif response_clean.startswith("```"):
            response_clean = response_clean.split("```")[1].split("```")[0].strip()

        attack_data = json.loads(response_clean)

        logger.info(f"Generated attack path with {len(attack_data.get('attack_path', []))} stages")
        return attack_data

    except Exception as e:
        logger.error(f"Attack path generation failed: {str(e)}")
        logger.warning("Falling back to simple tactic grouping")

        # Fallback: simple tactic-based grouping
        tactic_groups = {}
        for t in matched_techniques:
            for tactic in t.get("tactics", []):
                if tactic not in tactic_groups:
                    tactic_groups[tactic] = []
                tactic_groups[tactic].append(t["external_id"])

        fallback_path = [
            {
                "stage": tactic.replace("-", " ").title(),
                "techniques": tech_ids,
                "description": f"Attacker uses {len(tech_ids)} technique(s) for {tactic}"
            }
            for tactic, tech_ids in tactic_groups.items()
        ]

        return {
            "attack_path": fallback_path,
            "attack_narrative": "Attack path analysis unavailable. See individual tactics above.",
            "kill_chain_phases": list(tactic_groups.keys())
        }


@rate_limited(max_retries=3, base_delay=2.0)
def generate_mitigation_advice(
    user_query: str,
    matched_techniques: List[Dict],
    attack_path: Optional[Dict] = None
) -> Dict:
    """
    Generate contextual mitigation advice based on matched techniques and attack path.

    Args:
        user_query: Original user query/scenario
        matched_techniques: List of matched techniques
        attack_path: Optional attack path analysis from generate_attack_path()

    Returns:
        Dict with mitigation recommendations:
        {
            "priority_mitigations": [
                {
                    "priority": "critical",
                    "category": "prevention",
                    "recommendation": "Specific action to take...",
                    "addresses_techniques": ["T1059.001", "T1059.003"],
                    "rationale": "Why this is important..."
                },
                ...
            ],
            "defense_layers": {
                "prevention": ["Action 1", "Action 2", ...],
                "detection": ["Action 1", "Action 2", ...],
                "response": ["Action 1", "Action 2", ...]
            },
            "quick_wins": ["Easy high-impact actions..."],
            "long_term": ["Strategic improvements..."]
        }

    Note:
        - Rate limited to 20 req/min
        - Returns basic mitigations if LLM fails
    """
    if not matched_techniques:
        logger.warning("No techniques provided for mitigation advice")
        return {
            "priority_mitigations": [],
            "defense_layers": {"prevention": [], "detection": [], "response": []},
            "quick_wins": [],
            "long_term": []
        }

    # Build prompt
    techniques_text = "\n".join([
        f"- {t['external_id']} ({t['name']}): {t.get('description', '')[:150]}..."
        for t in matched_techniques[:10]
    ])

    attack_context = ""
    if attack_path:
        attack_context = f"\nAttack Path:\n{attack_path.get('attack_narrative', '')}\n"

    prompt = f"""User Scenario:
"{user_query}"

Matched MITRE Techniques:
{techniques_text}
{attack_context}

Task:
Provide practical, prioritized mitigation advice to defend against these techniques.

1. Identify critical mitigations (prevention, detection, response)
2. Prioritize by impact and feasibility
3. Specify which techniques each mitigation addresses
4. Separate quick wins (easy to implement) from long-term strategic improvements

Return JSON format:
{{
  "priority_mitigations": [
    {{
      "priority": "critical/high/medium",
      "category": "prevention/detection/response",
      "recommendation": "Specific action...",
      "addresses_techniques": ["T1059.001"],
      "rationale": "Why this matters..."
    }},
    ...
  ],
  "defense_layers": {{
    "prevention": ["Action 1", ...],
    "detection": ["Action 1", ...],
    "response": ["Action 1", ...]
  }},
  "quick_wins": ["Easy action 1", ...],
  "long_term": ["Strategic action 1", ...]
}}
"""

    try:
        logger.info("Generating mitigation advice with LLM...")

        response = generate_response_with_system(
            prompt=prompt,
            system_message=SYSTEM_PROMPT_MITIGATION,
            temperature=0.3,
            max_tokens=2500
        )

        # Parse JSON response
        response_clean = response.strip()
        if response_clean.startswith("```json"):
            response_clean = response_clean.split("```json")[1].split("```")[0].strip()
        elif response_clean.startswith("```"):
            response_clean = response_clean.split("```")[1].split("```")[0].strip()

        mitigation_data = json.loads(response_clean)

        logger.info(f"Generated {len(mitigation_data.get('priority_mitigations', []))} prioritized mitigations")
        return mitigation_data

    except Exception as e:
        logger.error(f"Mitigation advice generation failed: {str(e)}")
        logger.warning("Falling back to basic mitigation listing")

        # Fallback: extract mitigations from technique data
        all_mitigations = []
        for t in matched_techniques:
            # Note: This would work if technique dict includes mitigations
            # For now, provide generic advice
            all_mitigations.append(f"Review mitigations for {t['external_id']} ({t['name']})")

        return {
            "priority_mitigations": [
                {
                    "priority": "high",
                    "category": "general",
                    "recommendation": m,
                    "addresses_techniques": [matched_techniques[i]["external_id"]],
                    "rationale": "Standard MITRE ATT&CK mitigation"
                }
                for i, m in enumerate(all_mitigations[:5])
            ],
            "defense_layers": {
                "prevention": ["Review and implement standard preventive controls"],
                "detection": ["Configure monitoring for matched techniques"],
                "response": ["Develop incident response playbooks"]
            },
            "quick_wins": ["Enable logging and monitoring"],
            "long_term": ["Implement defense-in-depth strategy"]
        }


def analyze_scenario(
    user_query: str,
    matched_techniques: List[Dict],
    top_k: int = 5
) -> Dict:
    """
    Complete LLM-enhanced analysis: refine matches, build attack path, generate mitigations.

    Args:
        user_query: User's threat scenario description
        matched_techniques: Techniques from semantic search
        top_k: Number of most relevant techniques to focus on

    Returns:
        Complete analysis dict:
        {
            "refined_techniques": [...],  # From refine_technique_matches()
            "attack_path": {...},          # From generate_attack_path()
            "mitigations": {...}           # From generate_mitigation_advice()
        }

    Note:
        - Makes 3 LLM calls (rate limited)
        - Total time: ~10-15 seconds
        - Graceful degradation on API failures
    """
    logger.info(f"Starting complete scenario analysis for query: '{user_query[:50]}...'")

    # Step 1: Refine technique matches
    refined_techniques = refine_technique_matches(user_query, matched_techniques, top_k)

    # Step 2: Generate attack path
    attack_path = generate_attack_path(user_query, refined_techniques)

    # Step 3: Generate mitigation advice
    mitigations = generate_mitigation_advice(user_query, refined_techniques, attack_path)

    result = {
        "refined_techniques": refined_techniques,
        "attack_path": attack_path,
        "mitigations": mitigations
    }

    logger.info("Complete scenario analysis finished")
    return result


if __name__ == "__main__":
    # Test LLM analyzer
    print("Testing LLM-enhanced MITRE analyzer...\n")

    # Sample matched techniques (mock data)
    mock_techniques = [
        {
            "external_id": "T1059.001",
            "name": "PowerShell",
            "similarity_score": 0.856,
            "description": "PowerShell is a powerful interactive command-line interface and scripting environment included in the Windows operating system.",
            "tactics": ["execution"],
            "platforms": ["Windows"]
        },
        {
            "external_id": "T1053.005",
            "name": "Scheduled Task",
            "similarity_score": 0.723,
            "description": "Adversaries may abuse the Windows Task Scheduler to perform task scheduling for initial or recurring execution of malicious code.",
            "tactics": ["execution", "persistence", "privilege-escalation"],
            "platforms": ["Windows"]
        }
    ]

    user_query = "Attacker used PowerShell to create scheduled tasks for persistence"

    print(f"Query: '{user_query}'\n")
    print("Running complete analysis...\n")

    try:
        result = analyze_scenario(user_query, mock_techniques, top_k=2)

        print("=== Refined Techniques ===")
        for t in result["refined_techniques"]:
            print(f"- {t['external_id']}: {t.get('relevance_explanation', 'N/A')}")

        print("\n=== Attack Path ===")
        print(result["attack_path"].get("attack_narrative", "N/A"))

        print("\n=== Top Mitigations ===")
        for m in result["mitigations"].get("priority_mitigations", [])[:3]:
            print(f"- [{m['priority']}] {m['recommendation']}")

        print("\n✅ LLM analyzer test complete")

    except Exception as e:
        print(f"❌ Test failed: {str(e)}")
        print("Note: Ensure OPENROUTER_API_KEY is set in .env")
