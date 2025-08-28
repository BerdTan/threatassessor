import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from chatbot.modules.mitre import MitreHelper

DEBUG = False  # Set to True to print all technique IDs and first technique details
mitre = MitreHelper(use_local=True)

def list_tactic_names(mitre_helper):
    tactics = mitre_helper.get_tactics()
    print("Available Tactics:")
    for tactic in tactics:
        print(f"- {tactic.get('name', 'N/A')}")

if __name__ == "__main__":
    techniques = mitre.get_techniques()
    if DEBUG:
        print("Available Technique IDs:")
        print([t.get('external_references', [{}])[0].get('external_id', None) for t in techniques])
        if techniques:
            print("\nFirst technique object:")
            print(techniques[0])
        else:
            print("\nNo techniques loaded.")
        # Interactive: List tactics and prompt for details
        list_tactic_names(mitre)
        tactic_name = input("\nEnter a tactic name to view details (or press Enter to skip): ").strip()
        if tactic_name:
            tactic = mitre.get_tactic_by_name(tactic_name)
            if tactic:
                print(f"\nTactic: {tactic['name']} (ID: {tactic['id']})\nDescription: {tactic.get('description', 'No description available.')}")
            else:
                print("Tactic not found.")

        # Prompt user for technique ID
        tech_id = input("\nEnter a technique ID (e.g., T1059) to view summary and mitigations: ").strip()
        if tech_id:
            print("\nTechnique Summary:")
            print(mitre.get_technique_summary(tech_id))
            print("\nMitigation Advice:")
            print(mitre.get_mitigation_advice(tech_id))
    else:
        # Non-interactive: Example output for T1059 and Execution
        print("\nTechnique Summary:")
        print(mitre.get_technique_summary("T1059"))
        print("\nMitigation Advice:")
        print(mitre.get_mitigation_advice("T1059"))
        print("\nTactic Lookup:")
        tactic = mitre.get_tactic_by_name("Execution")
        if tactic:
            print(f"Tactic: {tactic['name']} (ID: {tactic['id']})\nDescription: {tactic.get('description', 'No description available.')}")
        else:
            print("Tactic not found.")
