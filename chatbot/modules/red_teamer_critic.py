"""
Red Team Critic Agent - DEPRECATED MODULE

⚠️ DEPRECATION WARNING:
This module has moved to chatbot.modules.agents.critics.red_teamer_critic

Legacy path (deprecated):
    from chatbot.modules.red_teamer_critic import RedTeamerCritic

New path (use this instead):
    from chatbot.modules.agents.critics import RedTeamerCritic
    # or
    from chatbot.modules.agents.critics.red_teamer_critic import RedTeamerCritic

This backward compatibility wrapper will be removed in v2.0.
"""

import warnings

warnings.warn(
    "chatbot.modules.red_teamer_critic is deprecated. "
    "Import from chatbot.modules.agents.critics.red_teamer_critic instead.",
    DeprecationWarning,
    stacklevel=2
)

# Re-export everything from new location
from chatbot.modules.agents.critics.red_teamer_critic import *

__all__ = ['RedTeamerCritic']
