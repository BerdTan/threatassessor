"""
Base Agent for MITRE Threat Modeling System

Provides abstract base class for all agents (critics, analysts, orchestrators).

Design Philosophy:
- Unified interface: All agents implement execute()
- Pluggable: Orchestrator discovers agents dynamically
- Testable: Mock execute() for unit tests
- Extensible: Easy to add new agent types

VERSION: 1.0 - Initial implementation for agent refactoring
"""

import json
import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional

from agentic.llm_client import LLMClient

logger = logging.getLogger(__name__)


class AgentResult:
    """Base result class for agent outputs."""

    def __init__(self, agent_name: str, data: Dict):
        self.agent_name = agent_name
        self.data = data

    def to_dict(self) -> Dict:
        """Convert result to dictionary."""
        return {
            "agent": self.agent_name,
            **self.data
        }


class BaseAgent(ABC):
    """
    Abstract base class for all agents.

    All agents (CriticAgent, AnalystAgent, OrchestratorAgent) inherit from this.

    Provides:
    - Unified interface: execute()
    - Shared LLM client
    - Common parsing/validation methods
    - Capability discovery
    """

    def __init__(self, role: str, model: Optional[str] = None):
        """
        Initialize agent.

        Args:
            role: Agent role (e.g., "Architect", "Tester", "Red Teamer")
            model: Optional model override (uses .env if None)
        """
        self.role = role
        self.model = model
        self.llm_client = LLMClient()

        logger.info(f"Initialized {role} agent (model={model or 'default'})")

    @abstractmethod
    def execute(self, context: Dict) -> AgentResult:
        """
        Execute agent's primary task.

        Args:
            context: Task context (ground truth, previous results, etc.)

        Returns:
            AgentResult with agent's output
        """
        pass

    @abstractmethod
    def get_capabilities(self) -> List[str]:
        """
        Return agent capabilities for dynamic discovery.

        Examples:
        - ["critique", "score", "identify_gaps"] for CriticAgent
        - ["analyze", "generate_threats"] for AnalystAgent
        - ["orchestrate", "aggregate"] for OrchestratorAgent

        Returns:
            List of capability strings
        """
        pass

    def _parse_llm_response(self, response: Any) -> Dict:
        """
        Parse LLM response into structured data.

        Handles:
        - Markdown code blocks (```json...```)
        - Raw JSON
        - Text responses

        Args:
            response: LLM response (LiteLLM response object or dict)

        Returns:
            Parsed dictionary (empty dict if parsing fails)
        """
        try:
            # Extract content from response
            if hasattr(response, 'content'):
                content = response.content
                logger.debug(f"{self.role}: Extracted content from response.content (length: {len(content)})")
            elif isinstance(response, dict):
                content = response.get('content', str(response))
                logger.debug(f"{self.role}: Extracted content from dict (length: {len(content)})")
            else:
                content = str(response)
                logger.debug(f"{self.role}: Converted response to string (length: {len(content)})")

            # Find JSON block (markdown first, then raw)
            if '```json' in content:
                # Markdown code block: ```json { ... } ```
                json_str = content.split('```json')[1].split('```')[0].strip()
                logger.debug(f"{self.role}: Found ```json block (length: {len(json_str)})")
            elif '```' in content and '{' in content:
                # Generic code block: ``` { ... } ```
                parts = content.split('```')
                for part in parts:
                    if '{' in part and '}' in part:
                        json_str = part.strip()
                        logger.debug(f"{self.role}: Found generic ``` block (length: {len(json_str)})")
                        break
                else:
                    raise ValueError("No JSON in code blocks")
            elif '{' in content and '}' in content:
                # Raw JSON (no code block)
                start = content.index('{')
                end = content.rindex('}') + 1
                json_str = content[start:end]
                logger.debug(f"{self.role}: Found raw JSON (length: {len(json_str)})")
            else:
                logger.warning(f"{self.role}: No JSON found in response")
                return {}

            # Parse JSON
            parsed = json.loads(json_str)
            logger.info(f"{self.role}: Successfully parsed JSON with keys: {list(parsed.keys())}")
            return parsed

        except Exception as e:
            logger.error(f"{self.role}: Failed to parse LLM response: {e}")
            if hasattr(response, 'content'):
                logger.debug(f"{self.role}: Response preview: {response.content[:500]}")
            return {}

    def _validate_dict_fields(self, data: Dict, required_fields: List[str]) -> bool:
        """
        Validate dictionary contains required fields.

        Args:
            data: Dictionary to validate
            required_fields: List of required field names

        Returns:
            True if all fields present, False otherwise
        """
        missing = [field for field in required_fields if field not in data]
        if missing:
            logger.warning(f"{self.role}: Missing required fields: {missing}")
            return False
        return True

    def _validate_score_range(self, score: int, min_val: int = 0, max_val: int = 100) -> bool:
        """
        Validate score is within valid range.

        Args:
            score: Score to validate
            min_val: Minimum valid score (default: 0)
            max_val: Maximum valid score (default: 100)

        Returns:
            True if score in range, False otherwise
        """
        if not (min_val <= score <= max_val):
            logger.warning(f"{self.role}: Invalid score: {score} (expected {min_val}-{max_val})")
            return False
        return True


# For backward compatibility, re-export from agent_framework if needed
__all__ = ['BaseAgent', 'AgentResult']
