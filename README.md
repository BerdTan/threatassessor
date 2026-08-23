# ThreatAssessor

Upload a Mermaid (`.mmd`) architecture diagram and receive a MITRE ATT&CK-mapped threat model, SOC detection signals, and optional MoE expert review — in under two minutes.

## System overview

```mermaid
flowchart TD
    subgraph Inputs
        mmd_in["Mermaid .mmd"]
        pr_in["GitHub PR"]
        ai_in["AI agent"]
    end

    subgraph Service["FastAPI  port 8000"]
        rest_api["REST API"]
        dash_ui["Dashboard"]
    end

    mcp_srv["MCP Server  16 tools"]

    subgraph Harness["Harness v2"]
        an_s["Analysis"]
        bo_s["Bouncer"]
        cr_s["MoE Critics + SM"]
        av_s["AIVSS Scorer"]
    end

    subgraph Outputs
        rep_o["report/ directory"]
        det_o["31 DETECT rules"]
        brn_o["TA Brain"]
    end

    mmd_in --> rest_api
    pr_in --> rest_api
    ai_in --> mcp_srv
    mcp_srv --> rest_api

    rest_api --> an_s
    dash_ui --> rest_api

    an_s --> bo_s
    bo_s -->|"API_ONLY"| av_s
    bo_s -->|"FULL_MOE"| cr_s
    cr_s --> av_s

    av_s --> rep_o
    av_s --> det_o
    av_s --> brn_o
```

| Component | Responsibility | Location |
|---|---|---|
| **FastAPI service** | REST API, web dashboard, SSE streaming | `chatbot/api/` |
| **Harness v2** | Pipeline controller: stages, circuit breaker, event broker | `chatbot/harness/` |
| **Analysis engine** | Deterministic threat mapping — RAPIDS + MITRE ATT&CK embeddings | `chatbot/modules/ground_truth_generator.py` |
| **MoE critics** | 5-critic panel (Architect / Tester / Red Team / Purple Team / Blackhat) + ScrumMaster | `chatbot/modules/agents/critics/` |
| **SOC detection layer** | 31 DETECT rules → OCSF DetectionFinding 2004 events per run | `policies/soc_detection_rules.yaml` |
| **Model benchmark** | N-model (up to 3) side-by-side critic evaluation; colour-coded HTML radar report with per-critic improvement hints and cross-model gap detection | `scripts/bench_critics.py`, `scripts/bench_report.py` |
| **TA Brain** | Persistent knowledge graph distilled from corpus; Stages 1–8 (Gap→MMD closes the self-growing loop); TACO query surface + CLI skills | `chatbot/modules/ta_brain_*.py` |
| **AIVSS v4** | Three-flow safety scoring: inbound / internal / outbound | `chatbot/harness/stages.py` |
| **MCP server** | 16 tools exposing TA capabilities to Claude Desktop and external agents | `mcp_server/` |
| **GitHub Actions CI** | PR reviewer — governance check + full analysis on every `.mmd` change | `.github/workflows/ta-review.yml` |

## How a request flows

A `.mmd` file submitted to `POST /api/v1/analyze` passes through Harness v2 in order:

1. **AnalysisStage** — parses the diagram, runs RAPIDS pattern matching, maps MITRE ATT&CK techniques per node and hop, computes a confidence band, writes `ground_truth.json` and 16 report files to `report/<arch-name>/`.
2. **ReportStage** — generates the executive summary, technical report, action plan, improvement summary, ADR, and TATB scores.
3. **QualityStage** — evaluates governance signals (injection, evasion, PII leakage, sovereignty). Runs `PolicyBroker` to adjust per-agent model routing.
4. **BouncerStage** (`required=True`) — halts the pipeline if `exploitation.blocked` is set, a kill-switch is active, or outbound signals indicate compromise. Raises `BlockedPipelineError` → API returns 400.
5. **CriticStage × 5** (FULL_MOE only) — runs in `partial_parallel` mode by default; each critic receives user-journey context relevant to its rubric.
6. **ScrumMasterStage** (FULL_MOE only) — synthesises critic findings into sprint-ready impediments and an 8-week action plan.
7. **AIVSSStage** — produces inbound / internal / outbound safety scores and appends to `governance_signals_history.jsonl`.
8. **RuleEvaluator** — evaluates all 31 DETECT rules against the governance signals and emits OCSF DetectionFinding events.

For `POST /api/v1/analyze-stream`, the same pipeline runs with SSE progress events for the dashboard.

## Running it locally

### Prerequisites

- Python 3.10+
- Two data files in `chatbot/data/` (not in the repo):

| File | Source | Size |
|---|---|---|
| `enterprise-attack.json` | [MITRE CTI releases](https://github.com/mitre/cti/tree/master/enterprise-attack) | ~44 MB |
| `technique_embeddings.npz` | Pre-computed — run `/build-embeddings-cache` after placing the JSON above | ~3 MB |

### Install and start

```bash
# Create virtual environment and install dependencies
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env — at minimum set API_KEY and one LLM provider key:
#   OPENROUTER_API_KEY=sk-or-v1-...   (recommended — free tier at openrouter.ai)

# Start the API server
make start        # wraps ./scripts/api/api_start.sh
```

Then open **http://localhost:8000/dashboard**.

| URL | What |
|---|---|
| `http://localhost:8000/dashboard` | Web dashboard |
| `http://localhost:8000/docs` | Swagger API docs |
| `http://localhost:8000/health` | Health check |

```bash
make stop         # stop server
make restart      # restart
make logs         # tail logs/api.log
make test         # run test suite
```

### Try it

33 sample `.mmd` diagrams in `tests/data/architectures/` cover cloud-native, zero-trust, IoT, agentic AI, data pipeline, multi-region, and microservices patterns. Drag any into the dashboard's **Upload** tab, or run:

```bash
curl -X POST http://localhost:8000/api/v1/analyze \
  -H "TM-API-KEY: your-key" \
  -F "architecture_file=@tests/data/architectures/00_serviceentry.mmd"
```

No LLM key is required for deterministic-only analysis. Add `OPENROUTER_API_KEY` to run MoE Expert Review.

## MCP server

The MCP server exposes ThreatAssessor as 16 tools to Claude Desktop and any MCP-compatible agent. The REST API must be running first.

**Claude Desktop config** (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "threatassessor": {
      "command": "python",
      "args": ["-m", "mcp_server.server"],
      "env": {
        "TM_API_BASE_URL": "http://localhost:8000",
        "TM_API_KEY": "your-key-here"
      }
    }
  }
}
```

For network transport (SSE / streamable-HTTP), start with `--transport sse --port 8001` and set `TM_MCP_KEY`.

| Tool | What it does |
|---|---|
| `analyze_architecture` | Submit `.mmd` → full threat model (~30s) |
| `run_expert_review` | Queue FULL_MOE, returns `job_id` |
| `get_job_status` | Poll job; `wait_for_completion=True` blocks until done |
| `get_threat_briefing` | CISO-ready briefing (md or json) |
| `get_ciso_brief` | Full CISO brief with investment tiers |
| `get_governance_signals` | AIVSS composite + signal dimensions |
| `get_detect_trends` | DETECT rule firing trends per architecture |
| `get_tatb_scores` | TATB benchmark scores (corpus or single arch) |
| `list_architectures` | All analysed architectures + metadata |
| `lookup_mitre_technique` | Technique details + mitigations by ATT&CK ID |
| `get_mcp_access_signals` | Live session access patterns (feeds DETECT-020–022) |
| `export_assessment` | TA bundle (`ta-export/1.0`, OTM-compatible) |
| `governance_check` | Fast MMD governance scan (~50ms, no LLM) |
| `query_ta_brain` | Query Brain patterns: infer / gaps / list |
| `record_brain_feedback` | Mark a Brain prediction confirmed / wrong / partial |
| `generate_synthetic_architectures` | Generate synthetic MMD diagrams from Brain meta-layer gaps; stages for approval |

## Configuration

All variables documented in `.env.example`. Minimum required:

| Variable | Description |
|---|---|
| `API_KEY` | REST API auth (`openssl rand -hex 32`) |
| `LLM_PROVIDER` | `openrouter` \| `bedrock` \| `anthropic` \| `azure` |
| `OPENROUTER_API_KEY` | `sk-or-v1-...` — free tier at openrouter.ai |

Optional per-agent model overrides via `AGENT_MODEL_*` (Architect, Tester, Red Team, Purple Team, Blackhat, ScrumMaster, MOE). Validate routing without API calls:

```bash
python3 .claude/skills/check-model-routing/scripts/check-model-routing.py
```

## Security notes

**API authentication** — all endpoints require a `TM-API-KEY` header except `/health`. Generate with `openssl rand -hex 32`; set as `API_KEY` in `.env`.

**MCP transport** — stdio transport (default) has no network exposure. Network transport (`--transport sse` / `--transport streamable-http`) requires `TM_MCP_KEY`; the server refuses to start without it.

**Governance gate** — `BouncerStage` (`required=True`) halts the pipeline on `CRITICAL` exploitation signals before any critic or output stage runs. The 31 DETECT rules emit OCSF events for SOC consumption.

## Design decisions

**Deterministic first.** The analysis engine runs without any LLM call — RAPIDS pattern matching and MITRE ATT&CK embeddings produce the threat model. MoE critics run only on explicit `FULL_MOE` requests.

**BouncerStage as required.** Sits between QualityStage and the critics. A blocked pipeline raises `BlockedPipelineError` and returns HTTP 400 before any LLM token is spent.

**TA Brain is LLM-free in its core.** All 8 completed stages (ingest, distil, cache, confidence decay, gap weighting, calibration, TACO processor, Gap→MMD generator) derive values from formulas and hashes — except the generator, which uses an LLM in the generation phase only and gates output behind human approval before entering the training loop. The topology signature is a pure SHA-256 of node shapes and edge patterns — collision-resistant across the corpus.

**Event bus between stages.** Each stage emits `HarnessEvent` objects to `EventBrokerCritic`, which fans out to SIEM, Langfuse, and webhook sinks. Stages have no knowledge of their consumers.

## TA Brain

The Brain is a self-growing knowledge graph that accumulates learning from every pipeline run and drives corpus growth. It operates in three layers:

- **Instance layer** (`ta_brain_instances.jsonl`) — append-only record of every analysed architecture: topology signature, techniques, missing controls, AIVSS score, fired DETECT rules.
- **Pattern layer** (`ta_brain.json`) — frequency-derived generalizations per architecture type. Each pattern carries `corpus_confidence` (training evidence) and `benchmark_confidence` (hold-out calibration). Published confidence = `min(corpus, benchmark)`.
- **Meta layer** (`ta_brain.json` gaps) — gaps the brain knows it doesn't cover; each gap carries a `generation_prompt` for targeted synthetic MMD generation.

**Stage 8 closes the loop.** The Gap→MMD generator reads the meta layer, generates synthetic Mermaid diagrams via LLM targeting under-sampled topology regions, stages them for human approval, and — once approved — submits them to the full harness pipeline. The resulting instances feed back into the pattern layer on the next `brain-grow` run.

Four CLI skills operate the Brain outside the dashboard:

| Skill | What |
|---|---|
| `brain-grow` | Full rebuild + N-round generate→ingest→calibrate loop |
| `brain-ingest` | Add one architecture report to the instance layer |
| `brain-cache` | Cache stats, pre-warm, evict stale, record feedback |
| `brain-infer` | Predictions vs ground truth — precision and recall per arch |

The Brain tab in the dashboard shows the live pattern table, gap cards, and the synthetic generation queue with approve/reject controls.

## Repo layout

```
DEV-TEST/
├── chatbot/
│   ├── api/                FastAPI app, routes, static dashboard (index.html + JS)
│   ├── harness/            Harness v2: controller, stages, governance, rule evaluator
│   ├── modules/            Analysis engine, MoE critics, TA Brain (ta_brain_*.py)
│   ├── config/             Settings loader, user_config.json, agent model config
│   └── services.py         ThreatAnalysisService — single callable surface
├── mcp_server/             MCP server: 16 tools, job client, access logger, sim personas
├── policies/               soc_detection_rules.yaml (31 rules), agent_governance.yaml
├── tests/
│   ├── data/architectures/ 33 sample .mmd files
│   └── unit/               Unit tests (233 for TA Brain alone)
├── scripts/
│   ├── api/                api_start.sh  api_stop.sh  api_status.sh  api_restart.sh
│   ├── ci/                 ta_pr_review.py (GitHub Actions PR reviewer)
│   ├── bench_critics.py    Two-model MoE benchmark (--models openrouter hetzner --archs ...)
│   └── bench_report.py     Self-contained HTML radar report from bench_summary.json
├── .github/workflows/      ta-review.yml — triggers on *.mmd PR changes
├── .env.example            All environment variable names with defaults
├── Makefile                Developer shortcuts: install / setup / start / stop / test
└── requirements.txt        Python dependencies
```

## Build story

The full build story is on Medium — 22 published parts covering the pipeline, cloud threat modelling, user journey intelligence, the MoE critic system, the harness, the quality flywheel, the detection layer, the skills infrastructure, TA as a GitHub Actions PR reviewer, the self-assessment that found a Critical in its own codebase, why a self-growing knowledge graph had the right answers all along, why new capabilities always introduce new attack surface, and how divergence between the Brain and live analysis reveals genuinely novel architectures:

| # | Title | What it covers |
|---|---|---|
| 1 | [From Diagram to Threat Model Report in Minutes](https://medium.com/@breadtan/from-diagram-to-threat-model-report-in-minutes-building-an-ai-assisted-threat-model-assessor-b730d9f91459) | MITRE ATT&CK + ATLAS + ARC + Singapore SSP — four sources, one diagram, under two minutes |
| 2 | [Cloud Threat Modelling: CSP-Aware, Risk-First — CAVEAT + CCM + SSP](https://medium.com/@breadtan/cloud-threat-modelling-csp-aware-risk-first-caveat-ccm-ssp-c367ac96d6cf) | How cloud-specific attack patterns layer onto the RAPIDS baseline; SSRM, IAM inference, GenAI profiles |
| 3 | [When Good Enough Is Not Enough: Teaching a Threat Assessor to See What It Couldn't](https://medium.com/@breadtan/when-good-enough-is-not-enough-teaching-a-threat-assessor-to-see-what-it-couldnt-0e027d6578fe) | MoE critics, self-validation, and closing the gaps a deterministic engine misses |
| 4 | [StoryCaster: Read the Human Stories Hidden in Your Architecture](https://medium.com/@breadtan/storycaster-read-the-human-stories-hidden-in-your-architecture-4fed8dfdcf05) | User journey co-generation — corroborated vs post-compromise paths, APT attribution, KEV CVEs |
| 5 | [When the Critics Disagree: ScrumMaster and the Art of Security Harmony](https://medium.com/@breadtan/when-the-critics-disagree-scrummaster-and-the-art-of-security-harmony-6cfacb7eb05e) | ScrumMaster synthesis, harmony checking, performance telemetry across the full critic pipeline |
| 6 | [The Conductor's Job: How a Lightweight Harness Keeps Your AI Pipeline Together](https://medium.com/@breadtan/the-conductors-job-how-a-lightweight-harness-keeps-your-ai-pipeline-together-9667f5712d9f) | Harness architecture — scenario registry, stage isolation, model guardian, and governance gate |
| 7 | [Threat Modeling Is the Art of Storytelling a Graph](https://medium.com/@breadtan/threat-modeling-is-the-art-of-storytelling-a-graph-719d0ef5a536) | Practitioner reflection — what good, bad, and ugly TM look like; what AI changes and what it doesn't |
| 8 | [You Can't Improve What You Don't Measure: A Practical Rubric for Threat Model Quality](https://medium.com/@breadtan/you-cant-improve-what-you-don-t-measure-a-practical-rubric-for-threat-model-quality-354f6f5856a2) | TATB four-rubric scorecard — Threat-Relevant, TTP-Accurate, Risk-Defensible, Plan-Actionable; the deterministic feedback loop |
| 9 | [The Flywheel Nobody Talks About: How a Benchmark Teaches Itself](https://medium.com/@breadtan/the-flywheel-nobody-talks-about-how-a-benchmark-teaches-itself-75e2dd955807) | Nova Pro independent labeller, labelled-corpus regression, recall 22% to 62% across 10 tuning rounds |
| 10 | [When the Benchmark Finds Its Own Blind Spots](https://medium.com/@breadtan/when-the-benchmark-finds-its-own-blind-spots-0d6461a5406b) | 26-arch corpus gauntlet — engine gaps, T1083/T1018 mitigation holes, and what a truthful TTP-Accurate score really means |
| 11 | [The Honest Harness: Learning, Unlearning, Relearning](https://medium.com/@breadtan/the-honest-harness-learning-unlearning-relearning-ffeec3e0166f) | Skill machine, UNSURE triage, AIVSS governing the critics, EventBroker audit trail, and the staged autonomy arc |
| 12 | [The Graph That Ate Its Own Architecture](https://medium.com/@breadtan/the-graph-that-ate-its-own-architecture-0186760253fe) | Replacing RAG with a 50ms deterministic graph; why frequency isn't criticality; canonicalisation as a query-time-only transform |
| 13 | [The Instrumentation We Forgot to Talk About](https://medium.com/@breadtan/the-instrumentation-we-forgot-to-talk-about-cd44c4a7a893) | EventBroker + 48 unit tests; the test suite as specification; sink isolation; why the instrumentation TA recommends for others is the same instrumentation TA runs on itself |
| 14 | [Beneath the Iceberg: The AI Pipeline Signals You Have But Aren't Reading](https://medium.com/@breadtan/beneath-the-iceberg-the-ai-pipeline-signals-you-have-but-arent-reading-e23abf9247f4) | 18 DETECT rules (now 30); the detect-loop flywheel; OWASP AST10 pipeline coverage; SOC KG provenance graph |
| 15 | [19 in a Day. Frequency Isn't the Signal.](https://medium.com/@breadtan/19-in-a-day-frequency-isnt-the-signal-ce2b3e459124) | DETECT-019 added same day Part 14 published; rule firing trend infrastructure; SOC KG trend badges |
| 16 | [Two Handymen and the Face: How ThreatAssessor Grew Ways to Be Used](https://medium.com/@breadtan/two-handymen-and-the-face-how-threatassessor-grew-ways-to-be-used-f6a80bb75064) | Skills as internal operator (41 skills); MCP as external interface (13 tools); adversarial sim live fire; governance_check 50ms gate |
| 17 | [The Architecture That Told You First: Four Signals from the AISI Incident](https://medium.com/@breadtan/architecture-that-told-you-first-four-signals-from-the-aisi-incident-727bfb75960c) | AISI INC-2026-07-28 breakdown; DETECT-025–028 grounded in real incident; governance_check two-severity split |
| 18 | [Skills That Built the Builder: How Developer Automation Grew Alongside ThreatAssessor](https://medium.com/@breadtan/skills-that-built-the-builder-how-developer-automation-grew-alongside-threatassessor-cc23897eee82) | 44-skill developer automation layer — regression suites, feedback flywheels, data portability, operational skills |
| 19 | [Always Verify, Never Trust — Even Yourself: ThreatAssessor's Self-Assessment](https://medium.com/@breadtan/always-verify-never-trust-even-yourself-threatassessors-self-assessment-47aea99e229b) | Running /harden-audit on TA itself — 1 Critical confirmed, 7 findings fixed, 2 new DETECT rules grounded in own findings |
| 20 | [The Wrong Ruler](https://medium.com/@breadtan/the-wrong-ruler-9b73117dbbbf) | Self-growing loop closed (Stage 8); brain-infer reveals 94% precision vs 0.09 calibration — the metric was measuring the wrong thing; 0.09→0.80 after fix |
| 21 | [Capability Is Attack Surface](https://medium.com/@breadtan/capability-is-attack-surface-57476a1f8ae2) | Every new capability introduces new surface — 3 findings all in same-session code; fix becomes detection rule (DETECT-031); 31 rules, 6 Critical |
| 22 | [Two Maps in the Jungle](https://medium.com/@breadtan/two-maps-in-the-jungle-6a26e2c24f20) | Divergence % between Brain predictions and live analysis as a novelty signal; teal = Workspace-only; what to do when the maps disagree |
