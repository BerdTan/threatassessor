"""
API Routes

Modular route handlers for different API features.
"""

from chatbot.api.routes.streaming import router as streaming_router
from chatbot.api.routes.reports import router as reports_router

__all__ = ["streaming_router", "reports_router"]
