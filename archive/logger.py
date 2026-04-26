"""
logger.py - Logging and audit module
"""
import datetime

def log_event(event_type, data):
    with open("chatbot.log", "a") as f:
        f.write(f"{datetime.datetime.now()} [{event_type}] {data}\n")
