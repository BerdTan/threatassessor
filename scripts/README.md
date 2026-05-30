# Scripts

Organised by purpose. All scripts use relative paths from repo root unless noted.

**Last Updated:** 2026-05-30

## Structure

```
scripts/
├── api/              # Server lifecycle (used by Makefile)
│   ├── api_start.sh
│   ├── api_stop.sh
│   ├── api_restart.sh
│   ├── api_status.sh
│   └── diagnose_upload.sh
├── integration/      # Cross-module validation (run manually or in CI)
│   ├── backtest_all_architectures.py   # Run all 25 .mmd architectures, compare results
│   ├── validate_engine_accuracy.py     # Accuracy checks against ground truth
│   ├── validate_parser_harness.py      # Parser validation harness
│   ├── test_llm_providers.py           # Test OpenRouter + Bedrock providers
│   └── test_openrouter.py              # OpenRouter API connectivity test
├── validation/       # Quick one-off checks
│   ├── check_orphans.py                # Detect orphan nodes in architecture diagrams
│   └── validate_llm_config.py         # Validate .env LLM config
├── ingest/           # Data refresh
│   └── scrape_ssp_catalog.py          # Scrape SG Gov SSP catalog → chatbot/data/ssp/
├── generation/       # Ground truth and test data generation
│   ├── generate_ground_truth.py       # Generate ground_truth.json for one architecture
│   └── batch_generate_ground_truth.sh # Batch generate for all test architectures
├── docs/
│   └── generate_html_docs.py          # Regenerate html/ documentation (make docs)
└── test_demos.sh     # Validate demo_*.sh scripts exist and run correctly
```

## Common Commands

```bash
# Check for orphan nodes in an architecture
python3 scripts/validation/check_orphans.py <architecture_name>

# Backtest all architectures
python3 scripts/integration/backtest_all_architectures.py

# Refresh SSP catalog data
python3 scripts/ingest/scrape_ssp_catalog.py

# Generate ground truth for a new architecture
python3 scripts/generation/generate_ground_truth.py tests/data/architectures/00_safeentry.mmd

# Validate API server is healthy
./scripts/api/api_status.sh
```

## Archive

Phase 3D README-only stub and `agent_testing/` scripts (phase 3C/3D manual tests) have been moved to `scripts/archive/` (gitignored).
