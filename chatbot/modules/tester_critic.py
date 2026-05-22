"""
Tester Critic Agent - DEPRECATED MODULE

⚠️ DEPRECATION WARNING:
This module has moved to chatbot.modules.agents.critics.tester_critic

Legacy path (deprecated):
    from chatbot.modules.tester_critic import TesterCritic

New path (use this instead):
    from chatbot.modules.agents.critics import TesterCritic
    # or
    from chatbot.modules.agents.critics.tester_critic import TesterCritic

This backward compatibility wrapper will be removed in v2.0.
"""

import warnings

warnings.warn(
    "chatbot.modules.tester_critic is deprecated. "
    "Import from chatbot.modules.agents.critics.tester_critic instead.",
    DeprecationWarning,
    stacklevel=2
)

# Re-export everything from new location
from chatbot.modules.agents.critics.tester_critic import *

__all__ = ['TesterCritic']
