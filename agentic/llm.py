"""
Flexible LLM client using LiteLLM for multi-provider routing.

Supports OpenRouter as primary provider with ability to add more providers later.
Current configuration: OpenRouter with free tier models.
"""

import logging
from typing import Optional, Dict, Any, List
import litellm
from agentic.helper import get_openrouter_api_key

logger = logging.getLogger(__name__)

# Default model configuration
# Using nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free
# All other free models are rate-limited (Google, Venice providers)
# Works ~33% of time but only available option
DEFAULT_LLM_MODEL = "openrouter/nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free"


def generate_response(
    prompt: str,
    model: str = DEFAULT_LLM_MODEL,
    temperature: float = 0.7,
    max_tokens: int = 1000,
    **kwargs
) -> str:
    """
    Generate LLM response using LiteLLM routing.

    Args:
        prompt: Input prompt for the LLM
        model: Model identifier (default: openrouter/google/gemma-4-26b-a4b-it:free)
        temperature: Sampling temperature (0.0-1.0, default: 0.7)
        max_tokens: Maximum tokens to generate (default: 1000)
        **kwargs: Additional arguments passed to LiteLLM

    Returns:
        Generated text response

    Raises:
        RuntimeError: If LLM call fails
        ValueError: If API key is not configured

    Example:
        >>> response = generate_response("Explain MITRE ATT&CK T1059.001")
        >>> print(response)
        "PowerShell is a command and scripting interpreter..."
    """
    api_key = get_openrouter_api_key()
    if not api_key:
        raise ValueError(
            "OPENROUTER_API_KEY not found in environment. "
            "Please add to .env file: OPENROUTER_API_KEY=your_key_here"
        )

    try:
        # Configure LiteLLM for OpenRouter
        litellm.api_key = api_key

        # Add OpenRouter-specific headers if using openrouter/ prefix
        extra_headers = {}
        if model.startswith("openrouter/"):
            extra_headers = {
                "HTTP-Referer": "http://localhost:8000",
                "X-Title": "MITRE-Chatbot"
            }

        # Call LLM via LiteLLM
        response = litellm.completion(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens,
            extra_headers=extra_headers,
            **kwargs
        )

        # Extract generated text
        generated_text = response.choices[0].message.content

        # Handle None response
        if generated_text is None:
            logger.warning(f"LLM returned None content for model {model}")
            raise RuntimeError("LLM returned empty response (None content)")

        logger.debug(f"Generated {len(generated_text)} chars using {model}")
        return generated_text

    except Exception as e:
        error_msg = f"LLM generation failed: {str(e)}"
        logger.error(error_msg)
        raise RuntimeError(error_msg)


def generate_response_with_system(
    prompt: str,
    system_message: str,
    model: str = DEFAULT_LLM_MODEL,
    temperature: float = 0.7,
    max_tokens: int = 1000,
    **kwargs
) -> str:
    """
    Generate LLM response with custom system message.

    Args:
        prompt: User prompt
        system_message: System prompt to guide LLM behavior
        model: Model identifier (default: openrouter/google/gemma-4-26b-a4b-it:free)
        temperature: Sampling temperature (0.0-1.0, default: 0.7)
        max_tokens: Maximum tokens to generate (default: 1000)
        **kwargs: Additional arguments passed to LiteLLM

    Returns:
        Generated text response

    Raises:
        RuntimeError: If LLM call fails
        ValueError: If API key is not configured

    Example:
        >>> system = "You are a cybersecurity expert specializing in MITRE ATT&CK."
        >>> response = generate_response_with_system("Explain T1059.001", system)
    """
    api_key = get_openrouter_api_key()
    if not api_key:
        raise ValueError(
            "OPENROUTER_API_KEY not found in environment. "
            "Please add to .env file: OPENROUTER_API_KEY=your_key_here"
        )

    try:
        # Configure LiteLLM for OpenRouter
        litellm.api_key = api_key

        # Add OpenRouter-specific headers if using openrouter/ prefix
        extra_headers = {}
        if model.startswith("openrouter/"):
            extra_headers = {
                "HTTP-Referer": "http://localhost:8000",
                "X-Title": "MITRE-Chatbot"
            }

        # Call LLM with system message
        response = litellm.completion(
            model=model,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt}
            ],
            temperature=temperature,
            max_tokens=max_tokens,
            extra_headers=extra_headers,
            **kwargs
        )

        # Extract generated text
        generated_text = response.choices[0].message.content

        # Handle None response
        if generated_text is None:
            logger.warning(f"LLM returned None content for model {model}")
            raise RuntimeError("LLM returned empty response (None content)")

        logger.debug(f"Generated {len(generated_text)} chars using {model}")
        return generated_text

    except Exception as e:
        error_msg = f"LLM generation failed: {str(e)}"
        logger.error(error_msg)
        raise RuntimeError(error_msg)


def get_available_models() -> List[str]:
    """
    Get list of available LLM models.

    Returns:
        List of model identifiers that can be used with generate_response()

    Note:
        Currently returns hardcoded list. Can be extended to query provider APIs.
    """
    return [
        "openrouter/google/gemma-4-26b-a4b-it:free",  # Default
        # Add more models as needed
    ]
