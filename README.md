
# DEV-TEST Chatbot Project

This project is a modular, extensible chatbot harness designed for easy integration of advanced features such as RAG (Retrieval Augmented Generation), MCP (Model Context Protocol), agentic capabilities, security, knowledgebase, and LLM-powered intelligence.


## Progress (as of August 28, 2025)

- Project scaffolded and modularized
- MITRE ATT&CK integration via local enterprise-attack.json
- Centralized LLM logic
- Security, knowledgebase, logging, and audit modules
- Automated tests for MITRE helper functions (technique/tactic/mitigation lookup)
- Demo script (`demo_mitre_advice.py`) supports both non-interactive and interactive modes:
   - Non-interactive: Prints summary, mitigation, and tactic for T1059/Execution
   - Interactive (set `DEBUG = True`): Lists tactics, prompts for user input
- All code lint- and syntax-error free
- Integration advice and best practices applied

## Project Structure
- `chatbot/` — Main chatbot code and modules
  - `core.py` — Core chatbot logic
  - `modules/` — Extensible modules (security, knowledgebase, logger, rag, mcp, agent, llm)
- `requirements.txt` — Python dependencies
- `README.md` — Project documentation and setup instructions
- `.gitignore` — Files and folders to ignore in version control

## Getting Started
1. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
2. Run the chatbot:
   ```
   python chatbot/main.py
   ```


## To-Do List / Next Steps

1. **MITRE ATT&CK Integration**
   - Integrate `mitreattack-python` to access MITRE ATT&CK techniques, tactics, and mitigations.
   - Use MITRE data to enrich the knowledgebase and threat grammar.
2. **Graph-Based Threat Modeling**
   - Design and implement a graph data model (e.g., with `networkx`) for threats, mitigations, and assumptions.
   - Enable visualization and export of threat models as graphs.
3. **Threat Grammar Expansion**
   - Extract and expand threat grammar from threat-composer and MITRE ATT&CK.
   - Use LLMs to help users write and refine threat statements.
4. **LLM Integration**
   - Implement real LLM calls in `modules/llm.py` (OpenAI, local models, etc.)
   - Add model selection/configuration options.
   - Use LLMs for advisory, grammar validation, and brainstorming.
5. **Security Enhancements**
   - Expand dangerous pattern lists and risk scoring.
   - Integrate LLM-based risk assessment.
   - Add user override/blocking options.
6. **Knowledgebase Expansion**
   - Add more best-practice patterns and semantic checks.
   - Integrate LLM for advice validation.
7. **RAG, MCP, Agentic Features**
   - Implement retrieval, context protocol, and agentic logic in respective modules.
   - Connect these modules to LLM for advanced reasoning.
8. **Logging and Audit**
   - Expand logging for all actions and decisions.
   - Add log management and export options.
9. **Testing and Documentation**
   - Write unit and integration tests for all modules.
   - Update documentation as new features are added.

## Contributing
Please document new modules and update this README with setup and usage instructions. Suggest improvements and help expand the chatbot’s capabilities!
