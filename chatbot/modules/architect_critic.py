"""
Architect Critic Agent for Phase 3C

Role: Security Architect reviewing threat assessment design quality

Rubric (100 points):
- Threat Model Completeness (40 points)
- Control Appropriateness (30 points)
- Defense-in-Depth (20 points)
- Context Awareness (10 points)
"""

import logging
from typing import Dict, List, Optional

from chatbot.modules.agent_framework import CriticAgent, AgentTool

logger = logging.getLogger(__name__)


# ============================================================================
# ARCHITECT TOOLS
# ============================================================================

def search_control_context(control_name: str, architecture_type: str) -> str:
    """
    Search for control best practices in given architecture context.

    Args:
        control_name: Control to research (e.g., "WAF", "MFA")
        architecture_type: Architecture type (e.g., "web_app", "ai_system")

    Returns: Context-specific guidance
    """
    # MVP1: Simple lookup (can be enhanced with actual search later)
    context_map = {
        "web_app": {
            "waf": "Critical for web applications - blocks OWASP Top 10 attacks at perimeter",
            "mfa": "Highly relevant - mitigates credential theft from phishing",
            "rate limiting": "Essential for API protection and DoS prevention"
        },
        "ai_system": {
            "prompt filtering": "Critical for AI - prevents prompt injection and jailbreaks",
            "rate limiting": "Essential for AI - prevents model abuse and cost overruns",
            "sandbox": "Important for AI - isolates model execution"
        },
        "iot": {
            "network segmentation": "Critical for IoT - prevents lateral movement",
            "firmware validation": "Essential for IoT - prevents device compromise",
            "certificate management": "Important for IoT - ensures device identity"
        }
    }

    arch_controls = context_map.get(architecture_type, {})
    guidance = arch_controls.get(control_name.lower(), "General security control - verify applicability to architecture")

    return guidance


def check_architecture_type(components: List[str]) -> str:
    """
    Identify architecture type from components.

    Args:
        components: List of component names

    Returns: Architecture type (web_app, ai_system, iot, generic)
    """
    components_lower = [c.lower() for c in components]

    # AI/LLM indicators
    if any(kw in ' '.join(components_lower) for kw in ['llm', 'agent', 'model', 'embedding', 'vectordb']):
        return "ai_system"

    # IoT indicators
    if any(kw in ' '.join(components_lower) for kw in ['sensor', 'device', 'gateway', 'mqtt', 'firmware']):
        return "iot"

    # Web app indicators (default if has internet + database)
    if any(kw in ' '.join(components_lower) for kw in ['web', 'api', 'http', 'rest']):
        return "web_app"

    return "generic"


# ============================================================================
# ARCHITECT RUBRIC
# ============================================================================

ARCHITECT_RUBRIC = {
    "threat_completeness": {
        "max": 40,
        "criteria": {
            "entry_points": {"points": 10, "description": "All entry points identified"},
            "data_flows": {"points": 10, "description": "All data flows mapped"},
            "arch_specific_threats": {"points": 10, "description": "Architecture-specific threats considered"},
            "trust_boundaries": {"points": 10, "description": "Trust boundaries clearly defined"}
        }
    },
    "control_appropriateness": {
        "max": 30,
        "criteria": {
            "complexity_match": {"points": 10, "description": "Controls match architecture complexity"},
            "sensitivity_alignment": {"points": 10, "description": "Controls aligned with data sensitivity"},
            "feasibility": {"points": 10, "description": "Controls feasible for architecture type"}
        }
    },
    "defense_in_depth": {
        "max": 20,
        "criteria": {
            "multiple_layers": {"points": 10, "description": "Multiple control layers per path"},
            "no_spof": {"points": 10, "description": "No single points of failure unmitigated"}
        }
    },
    "context_awareness": {
        "max": 10,
        "criteria": {
            "industry_specific": {"points": 5, "description": "Industry-specific considerations"},
            "regulatory": {"points": 5, "description": "Regulatory requirements addressed"}
        }
    }
}


# ============================================================================
# ARCHITECT SYSTEM PROMPT
# ============================================================================

ARCHITECT_SYSTEM_PROMPT = """You are a Senior Security Architect reviewing a threat assessment.

IMPORTANT: This prompt uses explicit terminology to avoid ambiguity.

============================================================
DEFINITIONS (spell out all terms)
============================================================

RAPIDS: Six risk areas used for threat assessment
- R: Ransomware (risk of ransomware/data encryption attacks)
- A: Application vulnerabilities (web app, API, software flaws)
- P: Phishing (social engineering, credential theft)
- I: Insider threat (malicious or negligent insiders)
- D: Denial of Service (DoS, resource exhaustion)
- S: Supply chain risk (third-party, vendor, dependency risks)

Each RAPIDS category scored 0-100 (higher = more risk)

Residual Risk: Risk remaining AFTER controls are applied (0-100 scale)
- 0-10: ACCEPT (low risk, acceptable)
- 10-20: MONITOR (medium risk, watch closely)
- 20+: MITIGATE (high risk, action required)

MITRE Technique: Specific adversary behavior from MITRE ATT&CK framework
- Format: T#### or T####.### (e.g., T1190 = Exploit Public-Facing Application)
- Total: 703 techniques in MITRE ATT&CK v15

Prevention + DIR Framework: Defense-in-Depth strategy
- Prevention (40%): Stop attacks before they start (MFA, WAF, Input Validation)
- Detect (30%): Identify attacks in progress (Logging, SIEM, IDS)
- Isolate (20%): Contain breaches (Network Segmentation, Firewall)
- Respond (10%): Recover from incidents (Backup, Incident Response)

============================================================
SCORING RUBRIC (Security Architect)
============================================================

A. Threat Model Completeness (40 points)
   - All entry points identified (10 pts)
   - All data flows mapped (10 pts)
   - Architecture-specific threats considered (10 pts)
   - Trust boundaries clearly defined (10 pts)

B. Control Appropriateness (30 points)
   - Controls match architecture complexity (10 pts)
   - Controls aligned with data sensitivity (10 pts)
   - Controls feasible for architecture type (10 pts)

C. Defense-in-Depth (20 points)
   - Multiple control layers per path (10 pts)
   - No single points of failure unmitigated (10 pts)

D. Context Awareness (10 points)
   - Industry-specific considerations (5 pts)
   - Regulatory requirements addressed (5 pts)

SCORING BANDS:
- 90-100: EXCELLENT - Architecture-aware recommendations
- 80-89: GOOD - Minor context improvements possible
- 70-79: FAIR - Some architectural mismatches
- <70: POOR - Significant architectural gaps

============================================================
YOUR ROLE
============================================================

As a Security Architect, focus on:
1. Design quality - Do recommendations fit the architecture?
2. Completeness - Are all entry points and data flows considered?
3. Context - Are controls appropriate for this specific system?
4. Feasibility - Can these controls actually be implemented here?

THINK LIKE AN ARCHITECT:
- "Would I recommend this to a client?"
- "Does this address the actual risks in THIS architecture?"
- "Are we over-engineering or under-protecting?"
- "Will this design withstand a real attack?"

OUTPUT REQUIREMENTS:
- Provide scores for each rubric category
- Identify specific gaps (not vague statements)
- Recommend actionable improvements
- Cite affected components by name
- Estimate impact of improvements

Be critical but constructive. Your goal is to improve the assessment quality.
"""


# ============================================================================
# ARCHITECT AGENT FACTORY
# ============================================================================

def create_architect_agent(model: Optional[str] = None) -> CriticAgent:
    """
    Create configured Architect critic agent.

    Args:
        model: LLM model to use (via LiteLLM). If None, uses .env configuration.
               .env settings: LLM_PROVIDER, OPENROUTER_MODEL, BEDROCK_MODEL, etc.

    Returns: Configured CriticAgent
    """
    tools = [
        AgentTool(
            name="search_control_context",
            description="Search for control best practices in given architecture context",
            function=search_control_context,
            parameters={
                "type": "object",
                "properties": {
                    "control_name": {
                        "type": "string",
                        "description": "Control to research (e.g., WAF, MFA, Rate Limiting)"
                    },
                    "architecture_type": {
                        "type": "string",
                        "description": "Architecture type (web_app, ai_system, iot, generic)"
                    }
                },
                "required": ["control_name", "architecture_type"]
            }
        ),
        AgentTool(
            name="check_architecture_type",
            description="Identify architecture type from component names",
            function=check_architecture_type,
            parameters={
                "type": "object",
                "properties": {
                    "components": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of component names from architecture"
                    }
                },
                "required": ["components"]
            }
        )
    ]

    agent = CriticAgent(
        role="Security Architect",
        rubric=ARCHITECT_RUBRIC,
        system_prompt=ARCHITECT_SYSTEM_PROMPT,
        tools=tools,
        model=model
    )

    logger.info("Created Architect critic agent")
    return agent


# ============================================================================
# CLI TEST INTERFACE (for MVP1 testing)
# ============================================================================

if __name__ == "__main__":
    import sys
    import json
    from pathlib import Path

    # Simple CLI for testing
    if len(sys.argv) < 2:
        print("Usage: python -m chatbot.modules.architect_critic <architecture_name>")
        print("Example: python -m chatbot.modules.architect_critic 10_complex_enterprise")
        sys.exit(1)

    arch_name = sys.argv[1]
    ground_truth_path = Path(f"report/{arch_name}/ground_truth.json")

    if not ground_truth_path.exists():
        print(f"Error: Ground truth not found at {ground_truth_path}")
        print("Run: python3 -m chatbot.main --gen-arch-truth <architecture.mmd> first")
        sys.exit(1)

    # Load ground truth
    with open(ground_truth_path) as f:
        ground_truth = json.load(f)

    # Create agent and run critique
    print(f"\n{'='*70}")
    print(f"ARCHITECT CRITIQUE: {arch_name}")
    print(f"{'='*70}\n")

    agent = create_architect_agent()
    score = agent.critique(ground_truth)

    # Print results
    print(f"\n{'='*70}")
    print(f"RESULTS")
    print(f"{'='*70}\n")
    print(f"Score: {score.score}/{score.max_score} ({score.rating})")
    print(f"\nBreakdown:")
    for category, data in score.breakdown.items():
        print(f"  {category}: {data.get('score', 0)}/{data.get('max', 0)}")

    print(f"\nGaps Found: {len(score.gaps)}")
    for i, gap in enumerate(score.gaps, 1):
        print(f"\n{i}. [{gap.get('severity', 'UNKNOWN')}] {gap.get('category', 'Unknown')}")
        print(f"   {gap.get('description', 'No description')}")
        print(f"   Recommendation: {gap.get('recommendation', 'None')}")

    print(f"\nStrengths: {len(score.strengths)}")
    for i, strength in enumerate(score.strengths, 1):
        print(f"  {i}. {strength}")

    # Save results
    output_path = Path(f"report/{arch_name}/04_architect_critique.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(score.to_dict(), f, indent=2)

    print(f"\n{'='*70}")
    print(f"Saved to: {output_path}")
    print(f"{'='*70}\n")
