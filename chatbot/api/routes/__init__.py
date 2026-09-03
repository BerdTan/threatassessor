"""
API Routes

Modular route handlers for different API features.
"""

from chatbot.api.routes.streaming import router as streaming_router
from chatbot.api.routes.reports import router as reports_router
from chatbot.api.routes.config import router as config_router
from chatbot.api.routes.workspaces import router as workspaces_router
from chatbot.api.routes.ta_wiz import router as ta_wiz_router
from chatbot.api.routes.graph_search import router as graph_search_router
from chatbot.api.routes.jobs import router as jobs_router
from chatbot.api.routes.mcp_sim import router as mcp_sim_router
from chatbot.api.routes.brain import router as brain_router
from chatbot.api.routes.taco import router as taco_router
from chatbot.api.routes.bench import router as bench_router
from chatbot.api.routes.enrich import router as enrich_router
from chatbot.api.routes.artifact import router as artifact_router
from chatbot.api.routes.taclaw import router as taclaw_router

__all__ = ["streaming_router", "reports_router", "config_router", "workspaces_router", "ta_wiz_router", "graph_search_router", "jobs_router", "mcp_sim_router", "brain_router", "taco_router", "bench_router"]
