"""
LLM-enhanced MITRE technique analysis and attack path construction.

This module uses LLM (via OpenRouter) to:
1. Refine and rank semantic search results
2. Construct logical attack paths from matched techniques
3. Generate contextual mitigation advice
4. Explain relevance of techniques to user scenarios

Rate limited to 20 req/min via OpenRouter free tier.

Note: Uses structured text format instead of JSON for better LLM reliability.
"""

import json
import logging
import re
from typing import List, Dict, Optional, Tuple
from chatbot.modules.rate_limiter import rate_limited
from agentic.llm import generate_response_with_system

logger = logging.getLogger(__name__)


# ============================================================================
# Text Parsing Functions (for structured LLM output)
# ============================================================================

def parse_structured_techniques(response: str) -> List[Dict]:
    """
    Parse structured text response into technique dicts.

    Expected format:
        TECHNIQUE: T1059.001
        RELEVANCE: Explanation here...
        CONFIDENCE: HIGH

        TECHNIQUE: T1053.005
        RELEVANCE: Another explanation...
        CONFIDENCE: MEDIUM

    Returns:
        [
            {
                "external_id": "T1059.001",
                "relevance_explanation": "Explanation here...",
                "confidence": "high"
            },
            ...
        ]
    """
    techniques = []

    # Split by blank lines to get individual technique blocks
    blocks = re.split(r'\n\s*\n', response.strip())

    for block in blocks:
        if not block.strip():
            continue

        # Extract fields using regex (case-insensitive)
        tech_match = re.search(r'TECHNIQUE[:\s]+([T]\d+(?:\.\d+)?)', block, re.IGNORECASE)
        rel_match = re.search(r'RELEVANCE[:\s]+(.+?)(?=\nCONFIDENCE:|$)', block, re.IGNORECASE | re.DOTALL)
        conf_match = re.search(r'CONFIDENCE[:\s]+(HIGH|MEDIUM|LOW)', block, re.IGNORECASE)

        if tech_match and rel_match:
            techniques.append({
                "external_id": tech_match.group(1).strip(),
                "relevance_explanation": rel_match.group(1).strip(),
                "confidence": conf_match.group(1).lower() if conf_match else "medium"
            })

    return techniques


def parse_structured_attack_path(response: str) -> Dict:
    """
    Parse structured attack path response.

    Expected format:
        NARRATIVE:
        The attacker likely started by...

        STAGE 1: Initial Access
        TECHNIQUES: T1566, T1566.001
        DESCRIPTION: Attacker sends phishing emails...

        STAGE 2: Execution
        TECHNIQUES: T1059.001
        DESCRIPTION: PowerShell executes payload...

    Returns:
        {
            "attack_narrative": "...",
            "attack_path": [
                {
                    "stage": "Initial Access",
                    "techniques": ["T1566", "T1566.001"],
                    "description": "..."
                },
                ...
            ]
        }
    """
    result = {
        "attack_narrative": "",
        "attack_path": []
    }

    # Extract narrative
    narrative_match = re.search(r'NARRATIVE[:\s]+(.+?)(?=\nSTAGE|\Z)', response, re.IGNORECASE | re.DOTALL)
    if narrative_match:
        result["attack_narrative"] = narrative_match.group(1).strip()

    # Extract stages
    stage_pattern = r'STAGE\s+\d+[:\s]+([^\n]+)\s+TECHNIQUES[:\s]+([^\n]+)\s+DESCRIPTION[:\s]+(.+?)(?=\nSTAGE|\Z)'
    for match in re.finditer(stage_pattern, response, re.IGNORECASE | re.DOTALL):
        stage_name = match.group(1).strip()
        techniques_str = match.group(2).strip()
        description = match.group(3).strip()

        # Parse technique IDs
        technique_ids = re.findall(r'T\d+(?:\.\d+)?', techniques_str)

        result["attack_path"].append({
            "stage": stage_name,
            "techniques": technique_ids,
            "description": description
        })

    return result


def parse_structured_mitigations(response: str) -> Dict:
    """
    Parse structured mitigation response.

    Expected format:
        MITIGATION 1:
        PRIORITY: CRITICAL
        RECOMMENDATION: Deploy email security...
        ADDRESSES: T1566, T1566.001
        RATIONALE: Prevents malicious emails...

        QUICK WINS:
        - Enable anti-phishing policies
        - Deploy MFA

    Returns:
        {
            "priority_mitigations": [
                {
                    "priority": "critical",
                    "recommendation": "...",
                    "addresses_techniques": ["T1566", ...],
                    "rationale": "..."
                },
                ...
            ],
            "quick_wins": ["...", ...]
        }
    """
    result = {
        "priority_mitigations": [],
        "quick_wins": []
    }

    # Extract individual mitigations
    mitigation_pattern = r'MITIGATION\s+\d+[:\s]*\s+PRIORITY[:\s]+([^\n]+)\s+RECOMMENDATION[:\s]+(.+?)ADDRESSES[:\s]+([^\n]+)\s+RATIONALE[:\s]+(.+?)(?=\nMITIGATION|\nQUICK WINS:|\Z)'

    for match in re.finditer(mitigation_pattern, response, re.IGNORECASE | re.DOTALL):
        priority = match.group(1).strip()
        recommendation = match.group(2).strip()
        addresses_str = match.group(3).strip()
        rationale = match.group(4).strip()

        # Parse technique IDs
        technique_ids = re.findall(r'T\d+(?:\.\d+)?', addresses_str)

        result["priority_mitigations"].append({
            "priority": priority.lower(),
            "recommendation": recommendation,
            "addresses_techniques": technique_ids,
            "rationale": rationale
        })

    # Extract quick wins
    quick_wins_match = re.search(r'QUICK WINS[:\s]*\n((?:[-•]\s*.+\n?)+)', response, re.IGNORECASE)
    if quick_wins_match:
        quick_wins_text = quick_wins_match.group(1)
        # Extract each bullet point
        result["quick_wins"] = [
            line.strip().lstrip('-•').strip()
            for line in quick_wins_text.split('\n')
            if line.strip() and (line.strip().startswith('-') or line.strip().startswith('•'))
        ]

    return result


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
2. Select the top {top_k} most relevant techniques
3. For each technique, explain WHY it's relevant (1-2 sentences)
4. Rate confidence level: HIGH/MEDIUM/LOW

Format your response EXACTLY like this example:

TECHNIQUE: T1059.001
RELEVANCE: PowerShell is directly relevant because attackers commonly use it for remote code execution and lateral movement in Windows environments.
CONFIDENCE: HIGH

TECHNIQUE: T1053.005
RELEVANCE: Scheduled tasks provide persistence by ensuring malicious code runs automatically after system reboot.
CONFIDENCE: HIGH

Continue for all {top_k} techniques. Use exactly this format with blank lines between techniques.
"""

    try:
        logger.info(f"Refining {len(matched_techniques)} techniques with LLM...")

        response = generate_response_with_system(
            prompt=prompt,
            system_message=SYSTEM_PROMPT_REFINE,
            temperature=0.3,  # Lower temperature for more focused analysis
            max_tokens=1500
        )

        # Check if response is None or empty
        if not response or not response.strip():
            raise ValueError("LLM returned empty response")

        # Parse structured text response
        refined_list = parse_structured_techniques(response)

        if not refined_list:
            logger.warning("No techniques extracted from LLM response")
            raise ValueError("Failed to parse any techniques from response")

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

1. Write a narrative explaining the full attack chain (2-3 sentences)
2. Break down the attack into stages based on MITRE tactics
3. For each stage, list techniques and explain what's happening

Format your response EXACTLY like this:

NARRATIVE:
The attacker likely began by sending phishing emails to gain initial access. Once a user opened the malicious attachment, PowerShell scripts were executed to establish persistence through scheduled tasks.

STAGE 1: Initial Access
TECHNIQUES: T1566, T1566.001
DESCRIPTION: Attacker sends spearphishing emails with malicious attachments to gain initial foothold in the target environment.

STAGE 2: Execution
TECHNIQUES: T1059.001, T1204.002
DESCRIPTION: User opens attachment, triggering PowerShell script execution that downloads and runs additional malware.

STAGE 3: Persistence
TECHNIQUES: T1053.005
DESCRIPTION: Attacker creates scheduled tasks to maintain access across system reboots.

Use exactly this format with blank lines between sections.
"""

    try:
        logger.info("Generating attack path with LLM...")

        response = generate_response_with_system(
            prompt=prompt,
            system_message=SYSTEM_PROMPT_ATTACK_PATH,
            temperature=0.4,
            max_tokens=2000
        )

        # Check if response is None or empty
        if not response or not response.strip():
            raise ValueError("LLM returned empty response")

        # Parse structured text response
        attack_data = parse_structured_attack_path(response)

        if not attack_data.get("attack_path"):
            logger.warning("No attack path stages extracted from LLM response")
            raise ValueError("Failed to parse attack path from response")

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

1. List 5 prioritized mitigations (CRITICAL/HIGH/MEDIUM priority)
2. For each, explain what to do and why it matters
3. Specify which techniques each mitigation addresses
4. Add quick wins (easy to implement actions)

Format your response EXACTLY like this:

MITIGATION 1:
PRIORITY: CRITICAL
RECOMMENDATION: Deploy advanced email security gateway with attachment sandboxing and URL scanning
ADDRESSES: T1566, T1566.001, T1566.002
RATIONALE: Prevents malicious emails from reaching users, blocking the most common initial access vector

MITIGATION 2:
PRIORITY: HIGH
RECOMMENDATION: Enforce multi-factor authentication (MFA) for all privileged accounts
ADDRESSES: T1078, T1078.001
RATIONALE: Even if credentials are compromised, MFA prevents unauthorized access

MITIGATION 3:
PRIORITY: HIGH
RECOMMENDATION: Enable PowerShell logging and implement constrained language mode
ADDRESSES: T1059.001, T1059.003
RATIONALE: Provides visibility into PowerShell usage and limits script execution capabilities

QUICK WINS:
- Enable built-in anti-phishing policies in email gateway
- Deploy MFA for all accounts
- Block executable email attachments
- Disable PowerShell v2.0
- Enable Windows Defender Application Control

Use exactly this format. Continue for at least 5 mitigations.
"""

    try:
        logger.info("Generating mitigation advice with LLM...")

        response = generate_response_with_system(
            prompt=prompt,
            system_message=SYSTEM_PROMPT_MITIGATION,
            temperature=0.3,
            max_tokens=2500
        )

        # Check if response is None or empty
        if not response or not response.strip():
            raise ValueError("LLM returned empty response")

        # Parse structured text response
        mitigation_data = parse_structured_mitigations(response)

        if not mitigation_data.get("priority_mitigations"):
            logger.warning("No mitigations extracted from LLM response")
            raise ValueError("Failed to parse mitigations from response")

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
