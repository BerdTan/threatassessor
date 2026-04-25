# Copilot Instructions for DEV-TEST Chatbot & Agentic Project

## Project Overview

This repository is a modular, extensible chatbot and agentic system for threat assessment, knowledgebase, and LLM-powered advice. It is organized into two main domains:

- `chatbot/`: Core chatbot logic, MITRE integration, and modular components.
- `agentic/`: Advanced agentic features (RAG, MCP, agent manager, Google ADK integration, Neo4j tools).

## Key Architectural Patterns

- **Separation of Concerns:** Chatbot logic and agentic/LLM/graph/ADK logic are separated into `chatbot/` and `agentic/`.
- **Agentic Orchestration:** Use `agentic/agent_manager.py` and `adk-basic.py` as the foundation for multi-agent workflows, leveraging Google ADK.
- **MITRE Integration:** Use `chatbot/modules/mitre.py` and `chatbot/modules/mitre_template.py` for mapping user input to MITRE ATT&CK techniques and generating threat prompts.
- **Neo4j Integration:** Use `agentic/neo4j_for_adk.py` for ADK-friendly graph database access. Reference this in agentic tools, not in chatbot modules.

## Developer Workflows

- **Install dependencies:**  
  `pip install -r requirements.txt`
- **Run the chatbot:**  
  `python chatbot/main.py`
- **Develop agentic features:**  
  Reference and extend `agentic/adk-basic.py` for Google ADK, LLM, and Neo4j workflows.
- **Testing:**  
  Use `pytest` for unit/integration tests (add tests in `tests/` or alongside modules).

## Project-Specific Conventions

- **Prompt Building:** Use `build_threat_prompt` from `chatbot/modules/mitre_template.py` for all MITRE-based threat prompt logic.
- **Agentic Imports:** All new agentic logic (RAG, MCP, LLM, agent manager) should be placed in `agentic/` and imported from there.
- **No Duplicates:** Do not duplicate agentic modules in `chatbot/`; always reference the canonical version in `agentic/`.
- **Google ADK:** Use `agentic/adk-basic.py` as the reference for ADK setup, agent creation, and tool integration. Document new agentic patterns in this file or in the README.

## Integration Points

- **LLM:** Use `agentic/llm.py` for LLM logic in agentic workflows.
- **Neo4j:** Use `agentic/neo4j_for_adk.py` for all graph database access in agentic modules.
- **MITRE:** Use `chatbot/modules/mitre.py` and `mitre_template.py` for MITRE ATT&CK logic.

## Example Patterns

- To build a threat prompt:
  ```python
  from chatbot.modules.mitre_template import build_threat_prompt
  ```
- To use Neo4j in an agentic tool:
  ```python
  from agentic.neo4j_for_adk import graphdb
  result = graphdb.send_query("MATCH (n) RETURN n LIMIT 1")
  ```
- To create a new agent with ADK:
  ```python
  from google.adk.agents import Agent
  from agentic.agent_manager import AgentManager
  ```

## External Dependencies

- Google ADK (`google-adk`)
- Neo4j Python driver (`neo4j`)
- LiteLLM (`litellm`)
- (Optional) spaCy, NLTK for NLP

## See Also

- `README.md` for project structure, setup, and TODOs.
- `agentic/adk-basic.py` for ADK and agentic workflow examples.
