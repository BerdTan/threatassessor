"""
knowledgebase.py - Reference for best practices and risky patterns
"""
from chatbot.modules import llm

def check_advice(advice, model=None):
    good_patterns = ["update regularly", "use strong passwords"]
    for pattern in good_patterns:
        if pattern in advice:
            return None
    # LLM-based semantic check (future)
    # risk = llm.assess_risk(advice, model)
    # if risk > 0:
    #     return "[Knowledgebase] Advice may not follow best practices (LLM check)."
    return "[Knowledgebase] Advice may not follow best practices."
