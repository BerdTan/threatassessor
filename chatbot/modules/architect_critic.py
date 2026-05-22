"""
Architect Critic Agent - DEPRECATED MODULE

⚠️ DEPRECATION WARNING:
This module has moved to chatbot.modules.agents.critics.architect_critic

Legacy path (deprecated):
    from chatbot.modules.architect_critic import EnhancedArchitectCritic

New path (use this instead):
    from chatbot.modules.agents.critics import EnhancedArchitectCritic
    # or
    from chatbot.modules.agents.critics.architect_critic import EnhancedArchitectCritic

This backward compatibility wrapper will be removed in v2.0.
"""

import warnings

warnings.warn(
    "chatbot.modules.architect_critic is deprecated. "
    "Import from chatbot.modules.agents.critics.architect_critic instead.",
    DeprecationWarning,
    stacklevel=2
)

# Re-export everything from new location
from chatbot.modules.agents.critics.architect_critic import *

__all__ = ['EnhancedArchitectCritic', 'search_control_context', 'check_architecture_type']
