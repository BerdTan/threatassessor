"""
agent.py - Persona/task manager for routing user input to appropriate modules

NOTE: The keyword extraction logic in AgentManager is currently simplistic and only splits on spaces, filtering by word length and basic stopwords. For production use, this should be replaced with a robust NLP-based keyword extraction (e.g., using spaCy, NLTK, or custom logic) to avoid irrelevant keywords and ensure accurate threat mapping and LLM advice.
"""
from chatbot.modules import llm
from chatbot.modules.mitre import MitreHelper
from chatbot.modules.mitre_template import build_threat_prompt

class AgentManager:
    def __init__(self):
        self.mitre = MitreHelper(use_local=True)
        # Initialize other modules (kb, mcp, etc.) here

    def handle_input(self, user_input):
        # Example: extract keywords (replace with your logic)
        keywords = self.extract_keywords(user_input)
        # Route to appropriate module/persona
        result = self.threat_assessment(user_input, keywords)
        return result

    def extract_keywords(self, user_input):
        # TODO: Replace with robust NLP-based keyword extraction for production use
        stopwords = {"i", "am", "doing", "the", "and", "for", "with", "to", "a", "of"}
        return [word.lower() for word in user_input.split() if word.lower() not in stopwords and len(word) > 3]

    def threat_assessment(self, user_input, keywords):
        prompt = build_threat_prompt(user_input, keywords, self.mitre)
        import re
        technique_ids = re.findall(r'\(ID: ([^)]+)\)', prompt)
        details = []
        for ext_id in technique_ids:
            summary = self.mitre.get_technique_summary(ext_id)
            mitigations = self.mitre.get_mitigation_advice(ext_id)
            details.append({
                "technique_id": ext_id,
                "summary": summary,
                "mitigations": mitigations
            })
        return {
            "prompt": prompt,
            "details": details
        }

def process(user_input, history, persona, model=None):
    # Future: Agentic reasoning, then call LLM for action/response
    # response = llm.generate_response(user_input, history, persona, model)
    return None
