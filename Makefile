.PHONY: help install setup start stop restart status logs demo demo-quick test openapi docs clean

# ──────────────────────────────────────────────────────────────
# ThreatAssessor — Developer Makefile
# Try-it-yourself entry point for new contributors and API users
# ──────────────────────────────────────────────────────────────

# Default target
help:
	@echo ""
	@echo "  ThreatAssessor — Available Commands"
	@echo "  ─────────────────────────────────────────────────────"
	@echo ""
	@echo "  First time?"
	@echo "    make install       Install Python dependencies (including FastAPI + uvicorn)"
	@echo "    make setup         Copy .env.example → .env (generates API_KEY automatically)"
	@echo ""
	@echo "  Day-to-day:"
	@echo "    make start         Start the API server (http://localhost:8000)"
	@echo "    make stop          Stop the API server"
	@echo "    make restart       Restart the API server"
	@echo "    make status        Show API server status"
	@echo "    make logs          Tail live API logs"
	@echo ""
	@echo "  Try it out:"
	@echo "    make demo          Full analysis with Expert Review (~2 min, requires LLM key)"
	@echo "    make demo-quick    Deterministic-only analysis (~30 sec, no LLM key needed)"
	@echo ""
	@echo "  Development:"
	@echo "    make test          Run test suite"
	@echo "    make openapi       Regenerate openapi.yaml from live FastAPI app"
	@echo "    make docs          Regenerate HTML documentation in html/"
	@echo "    make clean         Remove generated reports and logs"
	@echo ""
	@echo "  URLs (after make start):"
	@echo "    Dashboard  →  http://localhost:8000/dashboard"
	@echo "    API docs   →  http://localhost:8000/docs"
	@echo "    Health     →  http://localhost:8000/health"
	@echo "    OpenAPI    →  openapi.yaml (in repo root)"
	@echo ""

# ── Setup ─────────────────────────────────────────────────────

install:
	@echo "Installing Python dependencies..."
	pip install -r requirements.txt
	@echo ""
	@echo "✓ Dependencies installed (FastAPI, uvicorn, pydantic, LiteLLM, ...)"
	@echo "  Next: make setup"

setup:
	@if [ -f .env ]; then \
		echo "⚠  .env already exists — skipping copy"; \
	else \
		cp .env.example .env; \
		echo "✓ .env created from .env.example"; \
	fi
	@echo ""
	@API_KEY=$$(openssl rand -hex 32); \
	if grep -q "^API_KEY=" .env 2>/dev/null; then \
		sed -i "s|^API_KEY=.*|API_KEY=$$API_KEY|" .env; \
	else \
		echo "API_KEY=$$API_KEY" >> .env; \
	fi; \
	echo "  ✓ API_KEY generated in .env"
	@echo ""
	@echo "  Also set at least one LLM provider key in .env:"
	@echo "    OPENROUTER_API_KEY   (free tier at openrouter.ai — recommended)"
	@echo "    AWS_BEDROCK_API_KEY  (enterprise fallback)"
	@echo ""
	@echo "  Then: make start"

# ── Server lifecycle ──────────────────────────────────────────

start:
	@./scripts/api/api_start.sh

stop:
	@./scripts/api/api_stop.sh

restart:
	@./scripts/api/api_restart.sh

status:
	@./scripts/api/api_status.sh

logs:
	@tail -f logs/api.log

# ── Try it out ────────────────────────────────────────────────

demo:
	@echo "Running full analysis with Expert Review on sample architecture..."
	@echo "(~2 min — requires LLM API key in .env)"
	@echo ""
	@./demo_expert_llm.sh tests/data/architectures/00_safeentry.mmd

demo-quick:
	@echo "Running deterministic-only analysis on sample architecture..."
	@echo "(~30 sec — no LLM key required)"
	@echo ""
	@./demo_deterministic_engine.sh --validate-orphan tests/data/architectures/00_safeentry.mmd

# ── Development ───────────────────────────────────────────────

test:
	@echo "Running test suite..."
	python3 -m pytest tests/ -v --tb=short

openapi:
	@echo "Regenerating openapi.yaml from FastAPI app..."
	@python3 -c "\
import json, yaml; \
from chatbot.api.app import app; \
spec = app.openapi(); \
open('openapi.yaml', 'w').write(yaml.dump(spec, default_flow_style=False, allow_unicode=True, sort_keys=False)); \
print('✓ openapi.yaml updated')"

docs:
	@echo "Regenerating HTML documentation in html/..."
	@bash -c "source .venv/bin/activate 2>/dev/null || true; python3 scripts/docs/generate_html_docs.py"
	@echo "✓ Documentation regenerated"

clean:
	@echo "Removing generated reports and logs..."
	@rm -rf report/*/
	@rm -f logs/api.log logs/api.pid
	@echo "✓ Cleaned"
