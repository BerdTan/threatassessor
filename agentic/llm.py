"""
DEPRECATED: Use agentic.llm_client instead.

This module is maintained for backward compatibility only.
All new code should use:
    from agentic.llm_client import LLMClient, generate_response_with_system

Migration guide: docs/MIGRATION_LLM_CLIENT.md

This file redirects all calls to agentic.llm_client with deprecation warnings.
"""

import warnings
from agentic.llm_client import (
    generate_response as _generate_response,
    generate_response_with_system as _generate_response_with_system,
    get_available_models as _get_available_models
)

# Legacy default model (for compatibility)
DEFAULT_LLM_MODEL = "openrouter/nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free"


def generate_response(*args, **kwargs):
    """
    DEPRECATED: Use agentic.llm_client.LLMClient instead.

    This is a legacy wrapper for backward compatibility.

    Migration:
        OLD: from agentic.llm import generate_response
        NEW: from agentic.llm_client import LLMClient
             client = LLMClient()
             response = client.generate(...)

    See: docs/MIGRATION_LLM_CLIENT.md
    """
    warnings.warn(
        "agentic.llm.generate_response is deprecated. "
        "Use agentic.llm_client.LLMClient instead. "
        "See docs/MIGRATION_LLM_CLIENT.md for migration guide.",
        DeprecationWarning,
        stacklevel=2
    )
    return _generate_response(*args, **kwargs)


def generate_response_with_system(*args, **kwargs):
    """
    DEPRECATED: Use agentic.llm_client.LLMClient instead.

    This is a legacy wrapper for backward compatibility.

    Migration:
        OLD: from agentic.llm import generate_response_with_system
        NEW: from agentic.llm_client import LLMClient
             client = LLMClient()
             response = client.generate(prompt, system_message=...)

    Or (quick fix):
        from agentic.llm_client import generate_response_with_system

    See: docs/MIGRATION_LLM_CLIENT.md
    """
    warnings.warn(
        "agentic.llm.generate_response_with_system is deprecated. "
        "Use agentic.llm_client.LLMClient.generate() instead. "
        "See docs/MIGRATION_LLM_CLIENT.md for migration guide.",
        DeprecationWarning,
        stacklevel=2
    )
    return _generate_response_with_system(*args, **kwargs)


def get_available_models():
    """
    DEPRECATED: Use agentic.llm_client.PROVIDER_MODELS instead.

    This is a legacy wrapper for backward compatibility.

    See: docs/MIGRATION_LLM_CLIENT.md
    """
    warnings.warn(
        "agentic.llm.get_available_models is deprecated. "
        "Use agentic.llm_client.PROVIDER_MODELS instead.",
        DeprecationWarning,
        stacklevel=2
    )
    return _get_available_models()
