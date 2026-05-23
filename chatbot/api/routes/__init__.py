"""
API Routes

Modular route handlers for different API features.
"""

from chatbot.api.routes.streaming import router as streaming_router

__all__ = ["streaming_router"]
