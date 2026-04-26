"""
security.py - Input/output validation module
"""


import re
from chatbot.modules import llm

# Dangerous patterns and their risk scores
DANGEROUS_INPUTS = [
    (r"rm -rf", 10),
    (r"drop table", 8),
    (r"shutdown", 7),
    # Add more patterns
]

DANGEROUS_OUTPUTS = [
    (r"disable firewall", 9),
    (r"share password", 10),
    (r"ignore security", 8),
    # Add more patterns
]

RISK_THRESHOLD = 7  # Example threshold

def score_input(user_input):
    score = 0
    for pattern, risk in DANGEROUS_INPUTS:
        if re.search(pattern, user_input, re.IGNORECASE):
            score = max(score, risk)
    return score

def score_output(bot_output):
    score = 0
    for pattern, risk in DANGEROUS_OUTPUTS:
        if re.search(pattern, bot_output, re.IGNORECASE):
            score = max(score, risk)
    return score

def process(user_input, history, persona, model=None):
    # Block empty input
    if not user_input.strip():
        return "[Security] Input cannot be empty."
    score = score_input(user_input)
    score += llm.assess_risk(user_input, model)
    if score >= RISK_THRESHOLD:
        return f"[Security] High-risk input detected (score: {score}). Blocked."
    return None

def check_output(bot_output, model=None):
    score = score_output(bot_output)
    score += llm.assess_risk(bot_output, model)
    if score >= RISK_THRESHOLD:
        return f"[Security] High-risk output detected (score: {score}). Blocked."
    return None
