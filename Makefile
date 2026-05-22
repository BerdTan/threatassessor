.PHONY: docs view-docs clean-html help

# Generate HTML documentation from markdown sources
docs:
	@echo "Generating HTML documentation..."
	@bash -c "source .venv/bin/activate && python3 scripts/docs/generate_html_docs.py"
	@echo ""
	@echo "✓ Documentation generated in html/ folder"
	@echo ""
	@echo "Generated files:"
	@echo "  - html/index.html (from README.md)"
	@echo "  - html/status.html (from STATUS_AND_PLAN.md)"
	@echo "  - html/roadmap.html (from docs/specs/MVP_SPECIFICATION.md)"

# Open generated HTML documentation in browser
view-docs:
	@echo "Opening HTML documentation..."
	@open html/index.html 2>/dev/null || xdg-open html/index.html 2>/dev/null || echo "Please open html/index.html manually"
	@open html/status.html 2>/dev/null || xdg-open html/status.html 2>/dev/null || echo "Please open html/status.html manually"
	@open html/roadmap.html 2>/dev/null || xdg-open html/roadmap.html 2>/dev/null || echo "Please open html/roadmap.html manually"

# Clean generated HTML files
clean-html:
	@echo "Cleaning generated HTML files..."
	@rm -f html/*.html
	@echo "✓ HTML files removed"

# Show help
help:
	@echo "ThreatAssessor - Available Make Targets"
	@echo ""
	@echo "  make docs       - Regenerate HTML documentation from markdown sources"
	@echo "  make view-docs  - Open generated HTML documentation in browser"
	@echo "  make clean-html - Remove generated HTML files"
	@echo "  make help       - Show this help message"
	@echo ""
	@echo "Documentation:"
	@echo "  Sources (edit these):         Outputs (generated):"
	@echo "  - README.md                 → html/index.html"
	@echo "  - STATUS_AND_PLAN.md        → html/status.html"
	@echo "  - docs/specs/MVP_SPECIFICATION.md → html/roadmap.html"
	@echo ""
	@echo "The Makefile provides shortcuts for:"
	@echo "  1. Regenerating HTML after editing markdown"
	@echo "  2. Opening HTML docs in your browser"
	@echo "  3. Cleaning up generated HTML files"
