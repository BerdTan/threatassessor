
# DEV-TEST Chatbot Project

This project is a modular, extensible chatbot harness designed for easy integration of advanced features such as RAG (Retrieval Augmented Generation), MCP (Model Context Protocol), agentic capabilities, security, knowledgebase, and LLM-powered intelligence.

## Summary of Progress

- Set up a modular Python chatbot scaffold in `chatbot/`.
- Implemented a core chatbot class with dynamic module loading and persona support.
- Added modules for:
  - Security (input/output validation, risk scoring, threshold-based blocking)
  - Knowledgebase (best-practice advice checks)
  - Logging (audit trail)
  - RAG, MCP, Agentic features (stubs)
- Centralized all LLM logic in `modules/llm.py` for easy future integration and maintenance.
- Refactored all modules to use the centralized LLM interface.

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

1. **LLM Integration**
   - Implement real LLM calls in `modules/llm.py` (OpenAI, local models, etc.)
   - Add model selection/configuration options
2. **Security Enhancements**
   - Expand dangerous pattern lists and risk scoring
   - Integrate LLM-based risk assessment
   - Add user override/blocking options
3. **Knowledgebase Expansion**
   - Add more best-practice patterns and semantic checks
   - Integrate LLM for advice validation
4. **RAG, MCP, Agentic Features**
   - Implement retrieval, context protocol, and agentic logic in respective modules
   - Connect these modules to LLM for advanced reasoning
5. **Logging and Audit**
   - Expand logging for all actions and decisions
   - Add log management and export options
6. **Testing and Documentation**
   - Write unit and integration tests for all modules
   - Update documentation as new features are added

## Contributing
Please document new modules and update this README with setup and usage instructions. Suggest improvements and help expand the chatbot’s capabilities!
