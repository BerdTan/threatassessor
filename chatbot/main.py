"""
main.py - Simple extensible chatbot

This script provides a basic chatbot loop and is designed for future extension with RAG, MCP, and agentic modules.
"""

from core import Chatbot

def main():
    bot = Chatbot()
    print("Welcome to the DEV-TEST Chatbot! Type 'exit' to quit.")
    while True:
        user_input = input("You: ")
        if user_input.lower() == "exit":
            print("Goodbye!")
            break
        response = bot.respond(user_input)
        print(f"Bot: {response}")

if __name__ == "__main__":
    main()
