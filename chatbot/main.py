"""
main.py - Simple extensible chatbot

This script provides a basic chatbot loop and is designed for future extension with RAG, MCP, and agentic modules.
"""

from chatbot.modules.agent import AgentManager

def main():
    agent = AgentManager()
    user_input = input("Describe your scenario: ")
    result = agent.handle_input(user_input)
    print(result["prompt"])
    for detail in result["details"]:
        print(f"\nTechnique {detail['technique_id']} Summary:")
        print(detail["summary"] or "No summary available.")
        print("Mitigation Advice:")
        if detail["mitigations"]:
            if isinstance(detail["mitigations"], list):
                for m in detail["mitigations"]:
                    print(f"- {m}")
            else:
                print(detail["mitigations"])
        else:
            print("No mitigation advice available.")

if __name__ == "__main__":
    main()
