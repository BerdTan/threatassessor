"""
mitre_template.py - Scaffold for building structured prompts for threat assessment using MITRE data
"""

# Example function to build a prompt from user input and extracted keywords

def build_threat_prompt(user_input, keywords, mitre_helper):
    """
    Build a structured prompt for LLM or local MITRE mapping.
    Args:
        user_input (str): The user's layman scenario description.
        keywords (list): List of extracted keywords/assets/threats.
        mitre_helper (MitreHelper): Instance for local MITRE lookup.
    Returns:
        str: Structured prompt for LLM or local mapping.
    """
    mapped_techniques = []
    for kw in keywords:
        for tech in mitre_helper.get_techniques():
            name = tech.get('name', '').lower()
            desc = tech.get('description', '').lower()
            ext_refs = tech.get('external_references', [])
            ext_id = next((ref.get('external_id', '') for ref in ext_refs if 'external_id' in ref), '')
            if kw.lower() in name or kw.lower() in desc or kw.lower() == ext_id.lower():
                mapped_techniques.append(f"{tech.get('name', 'N/A')} (ID: {ext_id})")
                break
    prompt = (
        f"Threat Assessment Scenario:\n"
        f"User Description: {user_input}\n"
        f"Extracted Keywords: {', '.join(keywords)}\n"
        f"Mapped MITRE Techniques: {', '.join(mapped_techniques) if mapped_techniques else 'None found'}\n"
        f"\nFor each mapped technique, provide a summary and recommended mitigations."
    )
    return prompt

# Example usage:
if __name__ == "__main__":
    from chatbot.modules.mitre import MitreHelper
    mitre = MitreHelper(use_local=True)
    user_input = "We allow desktop access for IT support."
    keywords = ["desktop", "RDP"]
    prompt = build_threat_prompt(user_input, keywords, mitre)
    print(prompt)

    # Extract mapped technique IDs from the prompt output
    import re
    matches = re.findall(r'\(ID: ([^)]+)\)', prompt)
    technique_ids = [m[1] for m in re.finditer(r'\(ID: ([^)]+)\)', prompt)]

    for ext_id in technique_ids:
        summary = mitre.get_technique_summary(ext_id)
        mitigations = mitre.get_mitigation_advice(ext_id)
        print(f"\nTechnique {ext_id} Summary:")
        print(summary if summary else "No summary available.")
        print(f"Mitigation Advice:")
        if mitigations:
            if isinstance(mitigations, list):
                for m in mitigations:
                    print(f"- {m}")
            else:
                print(mitigations)
        else:
            print("No mitigation advice available.")
