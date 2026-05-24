.PHONY: help install setup start stop restart status logs demo demo-quick test docs clean

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
	@echo "    make install       Install Python dependencies"
	@echo "    make setup         Copy .env.example → .env (edit to add API keys)"
	@echo ""
	@echo "  Day-to-day:"
	@echo "    make start         Start the API server (http://localhost:8000)"
	@echo "    make stop          Stop the API server"
	@echo "    make restart       Restart the API server"
	@echo "    make status        Show API server status"
	@echo "    make logs          Tail live API logs"
	@echo ""
	@echo "  Try it out:"
	@echo "    make demo          Full analysis with Expert Review (~2 min, requires API key)"
	@echo "    make demo-quick    Deterministic-only analysis (~30 sec, no API key needed)"
	@echo ""
	@echo "  Development:"
	@echo "    make test          Run test suite"
	@echo "    make docs          Regenerate HTML documentation"
	@echo "    make clean         Remove generated reports and logs"
	@echo ""
	@echo "  URLs (after make start):"
	@echo "    Dashboard  →  http://localhost:8000/dashboard"
	@echo "    API docs   →  http://localhost:8000/docs"
	@echo "    Health     →  http://localhost:8000/health"
	@echo ""

# ── Setup ─────────────────────────────────────────────────────

install:
	@echo "Installing Python dependencies..."
	pip install -r requirements.txt
	@echo ""
	@echo "✓ Dependencies installed"
	@echo "  Next: make setup (configure API keys)"

setup:
	@if [ -f .env ]; then \
		echo "⚠  .env already exists — skipping copy"; \
	else \
		cp .env.example .env; \
		echo "✓ .env created from .env.example"; \
	fi
	@echo ""
	@echo "  Edit .env and set at least one of:"
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
	@echo "(~30 sec — no API key required)"
	@echo ""
	@./demo_deterministic_engine.sh --validate-orphan tests/data/architectures/00_safeentry.mmd

# ── Development ───────────────────────────────────────────────

test:
	@echo "Running test suite..."
	python3 -m pytest tests/ -v --tb=short

docs:
	@echo "Regenerating HTML documentation..."
	@bash -c "source .venv/bin/activate 2>/dev/null || true; python3 scripts/docs/generate_html_docs.py"
	@echo "✓ Documentation regenerated"

clean:
	@echo "Removing generated reports and logs..."
	@rm -rf report/*/
	@rm -f logs/api.log logs/api.pid
	@echo "✓ Cleaned"
