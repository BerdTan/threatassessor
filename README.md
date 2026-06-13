# ThreatAssessor

![Python](https://img.shields.io/badge/python-3.10%2B-blue) ![License](https://img.shields.io/badge/license-TBD-lightgrey)

Upload a Mermaid (`.mmd`) architecture diagram and receive a full, MITRE-mapped threat assessment in under two minutes.

## What it does

| Capability | What you get |
|---|---|
| **Threat mapping** | MITRE ATT&CK techniques per node and hop, prioritised controls, before/after architecture diagrams |
| **User journey intelligence** | Every attack path cross-referenced against real user workflows — tells you whether an attacker blends with legitimate traffic or is on a post-compromise pivot with no user baseline |
| **Real-world threat intel** | APT group attribution (MITRE intrusion-sets) and CVEs per attack path, cross-checked against CISA Known Exploited Vulnerabilities including ransomware flags |
| **Policy alignment** | Singapore Government ICT&SS SSP baseline overlay — mandatory controls surfaced per profile (cloud, on-prem, GenAI, etc.) |
| **Expert Review** | Five MoE critic agents — Architect → Coverage Auditor → Exploit Analyst → Purple Team → Blackhat — each receiving user journey context relevant to their rubric, producing a consensus with tiered improvement recommendations |
| **Confidence scoring** | Architecture-sensitive confidence band; recovers toward ceiling only when coverage signals prove the surface was thoroughly mapped |

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

**1. Deterministic pass (~30 s, no LLM)** — The diagram is parsed into a graph. RAPIDS walks every attack path, maps each hop to MITRE ATT&CK techniques and mitigations, and overlays the selected SSP policy baseline. StoryCaster runs here too: it classifies each attack path as *corroborated* (a real user follows this route) or *post-compromise* (no user baseline — attacker must already be inside). APT group attribution and KEV-backed CVEs are added to each path's risk scenario.

**2. Expert Review (~90 s, LLM)** — Five MoE critics audit in sequence, each receiving a slice of the journey intelligence relevant to their rubric. Blackhat runs last and looks for cross-path pivot chains the individual critics cannot see. The synthesis step applies deterministic tier-sharpening: post-compromise paths push preventive controls to Quick Win (no detection fallback); corroborated paths place preventive controls in Quick Win and precision-detection controls in Recommended.

**3. Output** — Executive summary, technical report, 8-week action plan, three phased architecture diagrams, and a threat model with ADR walkthrough — all annotated with user journey context so every finding tells you *who is affected* and *whether the attacker looks like a real user*.

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
    story_caster.py          User journey co-generation (StoryCaster)
    threat_scene_deepener.py APT attribution + KEV CVE enrichment
    kev_helper.py            CTID + CISA KEV singleton loader
    agents/critics/          Five MoE critic agents (Architect, Tester, RedTeam, Purple, Blackhat)
    agents/orchestrators/    MoE synthesis + tier sharpening
  services/       Thread-safe service layer
  data/
    arc/          ARC Framework data (controls.yaml, risks.yaml) — in repo
    atlas/        MITRE ATLAS YAML corpus — in repo
    ssp/          Singapore Government SSP catalog JSON — in repo
    kev/          CTID + CISA KEV indexes — not in git (run update-kev.sh to fetch)
    *.json        MITRE ATT&CK + embeddings — not in git (large files)
agentic/          Multi-provider LLM client (OpenRouter, Bedrock)
scripts/          Server lifecycle, validation, ingest, doc generation
  api/            api_start/stop/restart/status scripts
  data/           fetch_kev.py — download CTID + CISA KEV indexes
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
