"""
main.py - LLM-Enhanced MITRE Attack Path Analyzer (CLI)

This script provides a CLI interface for semantic threat assessment.
Supports both semantic search (with LLM analysis) and keyword fallback modes.
"""

import logging
from chatbot.modules.agent import AgentManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def print_semantic_results(result: dict):
    """Display semantic search results in readable format."""
    print("\n" + "="*80)
    print("THREAT ASSESSMENT RESULTS (Semantic Mode)")
    print("="*80)

    # Display matched techniques
    refined = result.get("refined_techniques", [])
    if refined:
        print("\n📊 MATCHED TECHNIQUES:\n")
        for i, tech in enumerate(refined, 1):
            print(f"{i}. {tech['external_id']} - {tech['name']}")
            print(f"   Similarity: {tech.get('similarity_score', 0):.3f} | Confidence: {tech.get('confidence', 'N/A')}")
            print(f"   Relevance: {tech.get('relevance_explanation', 'N/A')}")
            print(f"   Tactics: {', '.join(tech.get('tactics', []))}")
            print()

    # Display attack path
    attack_path = result.get("attack_path", {})
    if attack_path:
        print("\n🎯 ATTACK PATH ANALYSIS:\n")
        print(attack_path.get("attack_narrative", "No narrative available."))
        print()

        stages = attack_path.get("attack_path", [])
        if stages:
            print("Attack Progression:")
            for i, stage in enumerate(stages, 1):
                print(f"\n  Stage {i}: {stage.get('stage', 'Unknown')}")
                print(f"  Techniques: {', '.join(stage.get('techniques', []))}")
                print(f"  {stage.get('description', 'No description.')}")

    # Display mitigations
    mitigations = result.get("mitigations", {})
    if mitigations:
        print("\n\n🛡️  MITIGATION RECOMMENDATIONS:\n")

        # Priority mitigations
        priority = mitigations.get("priority_mitigations", [])
        if priority:
            print("Priority Actions:")
            for i, m in enumerate(priority[:5], 1):  # Top 5
                print(f"\n  {i}. [{m.get('priority', 'N/A').upper()}] {m.get('recommendation', 'N/A')}")
                print(f"     Addresses: {', '.join(m.get('addresses_techniques', []))}")
                print(f"     Rationale: {m.get('rationale', 'N/A')}")

        # Quick wins
        quick_wins = mitigations.get("quick_wins", [])
        if quick_wins:
            print("\n\nQuick Wins (Easy to Implement):")
            for i, win in enumerate(quick_wins, 1):
                print(f"  {i}. {win}")

    print("\n" + "="*80 + "\n")


def print_keyword_results(result: dict):
    """Display keyword search results in readable format (legacy)."""
    print("\n" + "="*80)
    print("THREAT ASSESSMENT RESULTS (Keyword Mode - Fallback)")
    print("="*80 + "\n")

    print(result.get("prompt", "No prompt available."))

    for detail in result.get("details", []):
        print(f"\n{'─'*80}")
        print(f"Technique {detail['technique_id']} Summary:")
        print(detail.get("summary") or "No summary available.")
        print("\nMitigation Advice:")
        mitigations = detail.get("mitigations")
        if mitigations:
            if isinstance(mitigations, list):
                for m in mitigations:
                    print(f"- {m}")
            else:
                print(mitigations)
        else:
            print("No mitigation advice available.")

    print("\n" + "="*80 + "\n")


def main():
    """Main CLI entry point."""
    print("\n" + "="*80)
    print("LLM-Enhanced MITRE Attack Path Analyzer")
    print("="*80)
    print("\nThis tool uses semantic search and LLM analysis to map threats")
    print("to MITRE ATT&CK techniques and provide mitigation advice.\n")

    # Initialize agent with semantic search enabled
    try:
        agent = AgentManager(use_semantic_search=True)
    except Exception as e:
        logger.error(f"Failed to initialize with semantic search: {e}")
        print("⚠️  Semantic search unavailable, using keyword fallback mode")
        agent = AgentManager(use_semantic_search=False)

    # Get user input
    print("Describe your threat scenario (e.g., 'Attacker used PowerShell to create scheduled tasks'):")
    user_input = input("> ").strip()

    if not user_input:
        print("Error: Please provide a scenario description.")
        return

    print("\n🔄 Analyzing scenario...")
    print("   This may take 10-15 seconds (semantic search + LLM analysis)\n")

    # Process input
    try:
        result = agent.handle_input(user_input, top_k=5)

        # Display results based on mode
        mode = result.get("mode", "unknown")
        if mode == "semantic":
            print_semantic_results(result)
        elif mode == "keyword":
            print_keyword_results(result)
        else:
            print(f"Error: Unknown mode '{mode}'")
            print(result)

    except Exception as e:
        logger.error(f"Error processing input: {e}")
        print(f"\n❌ Error: {str(e)}")
        print("Please check logs for details.")


if __name__ == "__main__":
    main()
