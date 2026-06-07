# ThreatAssessor

![Python](https://img.shields.io/badge/python-3.10%2B-blue) ![License](https://img.shields.io/badge/license-TBD-lightgrey)

Upload a Mermaid (`.mmd`) architecture diagram and receive a full, MITRE-mapped threat assessment in under two minutes.

## What it does

- Parses your architecture diagram and maps every component and data flow to MITRE ATT&CK techniques, generating prioritized security controls with before/after diagrams.
- Runs AI/ML threat pattern detection using the ARC Framework and MITRE ATLAS (AI/ML techniques) on top of the deterministic RAPIDS threat engine. ARC control recommendations are annotated with category badges (SAF, SEC, PRIV, etc.) and linked to ATLAS techniques with full name resolution.
- Enriches controls with the Singapore Government ICT&SS Security Standards for Providers (SSP) baseline — selectable profile (Low/Medium/High Risk Cloud, On-Premises, Generative AI, Digital Services, Sandbox) surfaces the mandatory controls your architecture must meet.
- Calculates architecture-sensitive confidence: complex architectures start with a lower base confidence that recovers only when coverage signals (control coverage, validation pass rate, attack path depth) prove the surface was thoroughly mapped. Final confidence is reported as a `confidence_breakdown` object.
- Validates findings through a Mixture of Experts (MoE) review — five critic agents running in a fixed sequence: Architect (2A) → Coverage Auditor (2B) → Exploit Analyst (2C) → Purple Team (2D) → Blackhat (2E). The core three (2A–2C) always run; Purple Team and Blackhat are optional toggles. Blackhat is the supreme critic — it sees all prior critique output and performs cross-path chain exploitation and pivot-diverge analysis. Produces 16 output files including an executive summary, technical report, 8-week action plan, and three phased architecture diagrams.

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
| `technique_embeddings.json` | Pre-computed — run `/build-embeddings-cache` after placing the JSON above | ~45 MB |

All other data files (ATLAS YAML, SSP catalog, ARC register) are included in the repo under `chatbot/data/`.

## Try it

```bash
# No API key required — deterministic analysis (~30 s)
make demo-quick

# Full Expert Review with MoE critics (~2 min, requires LLM key in .env)
make demo
```

Both commands write results to `report/<architecture-name>/` (16 files).

## How it works

ThreatAssessor parses the Mermaid diagram into a graph, then the RAPIDS engine walks every attack path and maps each hop to MITRE ATT&CK techniques and mitigations — the deterministic pass runs in under 30 seconds with no LLM call. The SSP enrichment layer overlays the user-selected policy baseline, flagging controls that are mandatory, recommended, or not applicable for that profile.

Confidence is architecture-sensitive: a complex multi-tier architecture starts at a lower base than a small demo diagram, recovering toward the ceiling only when control coverage, validation pass rate, and attack path depth prove the surface was thoroughly mapped.

When Expert Review is enabled, up to five MoE critic agents audit the findings in sequence. The core three (Architect, Coverage Auditor, Exploit Analyst) always run. Purple Team adds detection-depth and SOC operability analysis across three lenses (coverage, assume-breach, ADR operability). Blackhat — the supreme critic — runs last and performs cross-path chain exploitation, surfacing pivot-diverge chains as synthetic BH-N attack paths in the Threat Model; it short-circuits if fewer than two attack paths are present. The synthesis step is grounded against the MITRE ATT&CK database so technique-ID disputes between critics are resolved against authoritative names. The dashboard history dropdown lets you reload any past analysis without re-running the pipeline.

## API usage

The REST API is available at **http://localhost:8000/docs** (Swagger UI). The machine-readable spec is at `openapi.yaml`.

```bash
# Analyze an architecture diagram
curl -X POST http://localhost:8000/api/v1/analyze \
  -H "TM-API-KEY: <your-key>" \
  -F "architecture_file=@my_architecture.mmd" \
  -F "ssp_profile=medium_risk_cloud"

# Stream analysis with real-time progress
curl -N -X POST http://localhost:8000/api/v1/analyze-stream \
  -H "TM-API-KEY: <your-key>" \
  -F "architecture_file=@my_architecture.mmd" \
  -F "ssp_profile=medium_risk_cloud"
```

Set `API_KEY` in your `.env` file; the server reads it on startup.

### Key endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check (no auth) |
| POST | `/api/v1/analyze` | Deterministic analysis, returns JSON |
| POST | `/api/v1/analyze-stream` | Same analysis with SSE progress events |
| GET | `/api/v1/expert-review` | SSE stream for MoE validation (`?critic_mode=parallel`) |
| GET | `/api/v1/reports` | List generated report directories |
| GET | `/api/v1/reports/{name}/briefing` | Self-contained Markdown two-pager (`?fmt=md`) for offline sharing |
| GET | `/api/v1/reports/{name}/download` | Download report as ZIP |

## Repository layout

```
chatbot/          Core analysis engine and REST API
  api/            FastAPI application (app.py, routes/, models/, static/)
  modules/        Threat analysis, RAPIDS, MoE agents, SSP mapper, self-validation
  services/       Thread-safe service layer
  data/
    arc/          ARC Framework data (controls.yaml, risks.yaml) — in repo
    atlas/        MITRE ATLAS YAML corpus — in repo
    ssp/          Singapore Government SSP catalog JSON — in repo
    *.json        MITRE ATT&CK + embeddings — not in git (large files)
agentic/          Multi-provider LLM client (OpenRouter, Bedrock)
scripts/          Server lifecycle, validation, ingest, doc generation
  api/            api_start/stop/restart/status scripts
  ingest/         scrape_ssp_catalog.py — refresh SSP data from source
  integration/    test_openrouter.py and other integration tests
  validation/     check_orphans.py, validate_llm_config.py
tests/            Test suite + 25 sample .mmd architectures
docs/             Project documentation (DECISIONS.md, operations, specs)
demo_deterministic_engine.sh   Fast CLI analysis (no LLM, ~30 s)
demo_expert_llm.sh             Full MoE pipeline CLI (~2 min)
Makefile          Developer entry point (make help for all targets)
openapi.yaml      OpenAPI 3.0 spec
```

## Read more

Curious how the whole pipeline fits together — RAPIDS, MoE critics, SSP enrichment, and the design decisions behind them? The full walkthrough is on Medium:

> **[From Diagram to Threat Model Report in Minutes: Building an AI-Assisted Threat Model Assessor](https://medium.com/@breadtan/from-diagram-to-threat-model-report-in-minutes-building-an-ai-assisted-threat-model-assessor-b730d9f91459)**
>
> Covers: MITRE ATT&CK + ATLAS + ARC Framework + Singapore SSP — four authoritative sources, one architecture diagram, under two minutes.

---

## Links

- **Dashboard** — http://localhost:8000/dashboard
- **API docs (Swagger)** — http://localhost:8000/docs
- **OpenAPI spec** — [openapi.yaml](openapi.yaml)
- **API management guide** — [docs/operations/API_MANAGEMENT.md](docs/operations/API_MANAGEMENT.md)
- **Developer reference** — [CLAUDE.md](CLAUDE.md)
