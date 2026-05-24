# ThreatAssessor

![Python](https://img.shields.io/badge/python-3.10%2B-blue) ![License](https://img.shields.io/badge/license-TBD-lightgrey)

Upload a Mermaid (`.mmd`) architecture diagram and receive a full, MITRE-mapped threat assessment in under two minutes.

## What it does

- Parses your architecture diagram and maps every component and data flow to MITRE ATT&CK techniques, generating prioritized security controls with before/after diagrams.
- Runs AI/ML threat pattern detection using the ARC Framework (88 controls) and MITRE ATLAS (170 AI/ML techniques) on top of the deterministic RAPIDS threat engine.
- Validates findings through a Mixture of Experts (MoE) review — three independent critic agents (Architect, Tester, Red Team) — and produces 16 output files including an executive summary, technical report, 8-week action plan, and three phased architecture diagrams.

## Quick Start

```bash
git clone <repo-url>
cd DEV-TEST
make install    # create virtualenv + install dependencies
make setup      # configure .env (add your API key when prompted)
make start      # start the FastAPI server on port 8000
```

Then open **http://localhost:8000/dashboard** in your browser.

### Required data files (not in repo)

Two large reference files must be downloaded separately and placed in `chatbot/data/`:

| File | Source | Size |
|------|--------|------|
| `enterprise-attack.json` | [MITRE ATT&CK releases](https://github.com/mitre/cti/tree/master/enterprise-attack) | ~44 MB |
| `technique_embeddings.json` | Pre-computed — see [docs/operations/API_MANAGEMENT.md](docs/operations/API_MANAGEMENT.md) | ~45 MB |

## Try it

```bash
# No API key required — deterministic analysis (~30 s)
make demo-quick

# Full Expert Review with MoE critics (~2 min, requires LLM key in .env)
make demo
```

Both commands write results to `report/<architecture-name>/` (16 files).

## How it works

ThreatAssessor parses the Mermaid diagram into a graph, then the RAPIDS engine walks every attack path and maps each hop to MITRE ATT&CK techniques and mitigations — this deterministic pass runs at 99.5% confidence in under 30 seconds with no LLM call. When Expert Review is enabled, three MoE critic agents independently audit the findings and adjust the final confidence to 93–96%. The pipeline then renders the full report package: executive summary, technical report, action plan, and priority-color-coded before/after architecture diagrams.

## API usage

The REST API is available at **http://localhost:8000/docs** (Swagger UI). The machine-readable spec is at `openapi.yaml`.

```bash
# Analyze an architecture diagram
curl -X POST http://localhost:8000/api/v1/analyze \
  -H "TM-API-KEY: <your-key>" \
  -F "architecture_file=@my_architecture.mmd"

# Stream analysis with real-time progress
curl -N -X POST http://localhost:8000/api/v1/analyze-stream \
  -H "TM-API-KEY: <your-key>" \
  -F "architecture_file=@my_architecture.mmd"
```

Set `API_KEY` in your `.env` file; the server reads it on startup.

### Key endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check (no auth) |
| POST | `/api/v1/analyze` | Deterministic analysis, returns JSON |
| POST | `/api/v1/analyze-stream` | Same analysis with SSE progress events |
| GET | `/api/v1/expert-review` | SSE stream for MoE validation |
| GET | `/api/v1/reports` | List generated report directories |
| GET | `/api/v1/reports/{name}/download` | Download report as ZIP |

## Repository layout

```
chatbot/          Core analysis engine and REST API
  api/            FastAPI application (app.py, routes/, models/, static/)
  modules/        Threat analysis, RAPIDS, MoE agents, self-validation
  services/       Thread-safe service layer
  data/           MITRE data files (not in git — see above)
agentic/          Multi-provider LLM client (OpenRouter, Bedrock)
scripts/          Server lifecycle, validation, doc generation
  api/            api_start/stop/restart/status scripts
  validation/     check_orphans.py, validate_llm_config.py
  docs/           generate_html_docs.py
tests/            Test suite + 22 sample .mmd architectures
docs/             Project documentation
html/             Generated HTML docs (index.html, status.html, roadmap.html)
openapi.yaml      OpenAPI 3.0 spec (auto-generated from FastAPI app)
```

## Links

- **Dashboard** — http://localhost:8000/dashboard
- **API docs (Swagger)** — http://localhost:8000/docs
- **OpenAPI spec** — [openapi.yaml](openapi.yaml)
- **API management guide** — [docs/operations/API_MANAGEMENT.md](docs/operations/API_MANAGEMENT.md)
- **Developer reference** — [CLAUDE.md](CLAUDE.md)
