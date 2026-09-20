# TAclaw Hardening Plan

**Status:** Draft — under review  
**Date:** 2026-09-20  
**Context:** TAclaw is the external-facing agent interface to the TA engine. External developers, CI pipelines, and MCP-enabled coding agents (Claude Desktop, Cursor, Copilot) use it. The current state has silent gaps that make the output incomplete and the caller unidentifiable.

---

## Current State (from introspection, 2026-09-20)

| Area | Finding |
|---|---|
| Export bundle | `tatb` always `{}`, `brain_quality` not in export, `fidelity_detail` lost at merge |
| Routing | Always `api_only`; smart router never called; brain_fast arches waste ~30s |
| Agent identity | No caller identity on TAclaw jobs; `TM-AGENT-PASSPORT` not minted or checked |
| Dead surface | `enrich_from_github=True` accepted, stored, never executed |
| Single-file path | Bypasses TAclaw job system entirely — no brain ingest, no export bundle, no gate |
| Adapter gaps | Kubernetes YAML, Docker Compose, Bicep, ARM, Ansible not covered |
| Multi-tenant | `arch_name` collisions overwrite prior results silently |

---

## Improvement Groups

### Group 1 — Export Completeness

**Goal:** Every TAclaw export bundle carries a complete, trustworthy signal.

**Files:** `chatbot/api/routes/taclaw.py`, `chatbot/adapters/crawler.py`, `chatbot/modules/ta_exporter.py`

| Fix | File | Change |
|---|---|---|
| TATB scores | `taclaw.py:204–215` | Fetch `get_tatb_scores(arch_name)` from brain benchmarks before calling `build_export()`; pass as `tatb_scores` arg |
| `brain_quality` in export | `ta_exporter.py` | Add `brain_quality` field to `TAExportBundle`; populate from `query_brain(infer)` result's `brain_quality` dict |
| `fidelity_detail` through merge | `crawler.py:122–131` | Carry per-adapter `fidelity_detail` dicts into composite `adapter_metadata` as `adapters_fidelity: list[dict]`; set composite `fidelity` to `min(per-adapter fidelity values)` instead of hardcoding 1.0 |

**Tests:** extend `check-sip` with export completeness assertions; assert `tatb`, `brain_quality`, `adapters_fidelity` fields are non-empty after a TAclaw run on a known fixture.

---

### Group 2 — Routing Intelligence

**Goal:** TAclaw uses the same smart routing as the direct pipeline. Known brain_fast arches respond in ~2s, not ~30s.

**Files:** `chatbot/api/routes/taclaw.py`

| Change | Detail |
|---|---|
| Call `select_mode(arch_name)` | Before `ThreatAssessorHarness.run_typed()`, call smart_router `select_mode(base_arch_name)` |
| Pass routing decision | Set `pipeline_mode` on `PipelineRequest` from `RoutingDecision.mode` |
| Log in job response | Add `routing_mode` field to TAclaw job result JSON |
| Guard: new arch | If `select_mode` returns `api_only` due to no routing data (new arch, never seen), that is correct — no change needed |

**Tests:** add routing assertion to test suite fixture — after a run on a brain_fast-eligible arch, job result `routing_mode == "brain_fast"`.

---

### Group 3 — Agent Identity (Engine Item 11)

**Goal:** TAclaw jobs carry an unforgeable identity token. Callers without a valid passport are detected.

**Rationale:** TAclaw is an autonomous agent that calls the TA engine internally. When coding agents (Claude, Copilot, Cursor) call TAclaw via MCP, a chain of identity is needed for accountability, audit, and trust-based routing.

**Files:** new `chatbot/modules/agent_passport.py`, `chatbot/api/routes/taclaw.py`, `chatbot/harness/governance.py`, `policies/soc_detection_rules.yaml`

| Component | Detail |
|---|---|
| `AgentPassport` dataclass | `caller`, `target`, `job_id`, `issued_at`, `ttl=300`; signed with HMAC-SHA256 using `API_KEY` as secret |
| Mint on job start | `taclaw.py:_run_taclaw_job()` mints passport at job creation; stored in job record |
| Stamp on harness call | Pass `agent_passport` token in `PipelineRequest.agent_context`; governance adapter reads it |
| Validate in governance | `governance.py`: if `agent_context.agent_passport` present but invalid signature or expired → `governance_signals.agent_passport_invalid=True` |
| Persist in export | `ta_export.json` under `provenance.agent_passport: {caller, job_id, issued_at}` (no secret) |
| `DETECT-AGT-001` | Rule: `agent_identity_spoofing` — fires when agentic call arrives at harness without valid passport; T1134/T1550 |
| MCP surface | `run_taclaw` MCP tool response includes `passport_id` field so MCP caller can reference the job identity |

**Tests:** unit test passport mint + validate + expire; governance test that fires DETECT-AGT-001 on missing passport; integration: TAclaw job export has `provenance.agent_passport`.

---

### Group 4 — MCP Surface Completeness

**Goal:** The `run_taclaw` MCP tool response reflects the Group 1–3 improvements so MCP callers get a complete, trustworthy signal.

**Files:** `mcp_server/server.py` (tool schema), `mcp_connector/client.py`

| Change | Detail |
|---|---|
| Add `routing_mode` to tool response | After Group 2 |
| Add `brain_quality` summary to tool response | Brier score + confidence — lets MCP callers judge reliability |
| Add `adapters_fidelity` summary | Per-adapter fidelity — callers know source quality |
| Add `passport_id` to tool response | After Group 3 |
| Remove `enrich_from_github` from schema | Dead flag — remove from MCP tool parameters to avoid misleading callers |

---

### Group 5 — Test Suite MVP

**Goal:** A self-contained runner that external developers execute against their own TA instance to verify TAclaw works and evaluate output quality.

**Location:** `taclaw/tests/`

#### Fixtures (`tests/data/taclaw/`)

| Fixture | Type | Expected gate | Adapter path | Purpose |
|---|---|---|---|---|
| `simple_webapp/` | directory (3 TF files) | PASS | TerraformAdapter | Basic crawl + export |
| `mixed_iac/` | directory (TF + CF + OpenAPI) | PASS | Multi-adapter merge | Fidelity propagation |
| `high_risk.mmd` | single file | BLOCK | MermaidAdapter | Governance gate fires |
| `ecommerce_api.yaml` | single file (OpenAPI) | PASS | OpenAPIAdapter | API surface analysis |

Fixtures are minimal (5–15 components), deterministic, and committed to `tests/data/taclaw/`. No real infrastructure.

#### Runner (`taclaw/tests/run_suite.py`)

```
python taclaw/tests/run_suite.py              # full suite
python taclaw/tests/run_suite.py --smoke      # simple_webapp only, fastest path
python taclaw/tests/run_suite.py --eval-only  # re-run eval against cached outputs
```

Flags: `--api-url`, `--api-key`, `--timeout`, `--output-dir`

#### Assertions (per fixture)

**Structural assertions** (pass/fail):
- Job completed without error
- Gate result matches expected (`PASS` or `BLOCK`)
- Export bundle shape: `gate`, `threats`, `detect_findings`, `otm`, `tatb`, `brain_quality`, `adapters_fidelity` all present and non-empty
- `routing_mode` field present (Group 2)
- `provenance.agent_passport` present (Group 3)

**Quality eval** (scored 0–100):
- `threat_coverage`: techniques found ÷ expected minimum for fixture type (e.g., ≥5 for simple_webapp)
- `key_techniques_present`: fixture-specific required techniques present (e.g., T1190 for internet-facing TF fixture)
- `aivss_in_range`: composite score within expected band per fixture (e.g., 4.0–7.0 for simple_webapp PASS)
- `fidelity_adequate`: `adapters_fidelity[*].node_coverage >= 0.7` for all adapters
- `brain_quality_calibrated`: if `brain_quality` present, `brier_combined < 0.3`
- `detect_signal`: `detect_findings` count matches expected range (≥1 for high_risk.mmd BLOCK)

**Regression eval** (comparison):
- On first run: write `tests/data/taclaw/<fixture>/baseline.json` (technique IDs + gate + aivss)
- On subsequent runs: diff against baseline; flag regressions (techniques disappeared) and additions (new threats found)
- `--update-baseline` flag to accept current output as new baseline

#### Scorecard output

```
TAclaw Test Suite — 2026-09-20 14:32
API: http://localhost:8000

Fixture               Gate    Structural  Quality   Regression
simple_webapp         PASS    ✅ 8/8      87/100    ✅ no delta
mixed_iac             PASS    ✅ 8/8      79/100    ⚠ +2 techniques
high_risk.mmd         BLOCK   ✅ 8/8      91/100    ✅ no delta
ecommerce_api.yaml    PASS    ✅ 8/8      83/100    ✅ no delta

Overall: 4/4 passed  |  Avg quality: 85/100  |  Regressions: 0
```

Exits 0 if all structural assertions pass. Exits 1 if any structural assertion fails. Quality score is advisory only (does not fail the suite run).

---

## Distribution Roadmap (next layer, separate session)

| Step | What | Effort |
|---|---|---|
| Docker image | `docker run threatassessor serve` — brings up TA API + brain; external dev points `TA_API_URL=http://localhost:8000` | M |
| PyPI publish | `pip install taclaw` (CLI) + `pip install threatassessor-mcp` (connector) | S |
| Quick-start README | Three steps: install → configure → `ta analyze <your-repo>` | S |
| MCP manifest | `mcp.json` descriptor for Claude Desktop / Cursor / Copilot auto-discovery | S |

---

## Sequencing and Dependencies

```
Group 1 (export completeness)
  ↓
Group 2 (routing)       ← independent of Group 1; can be parallel
  ↓
Group 3 (agent passport)
  ↓
Group 4 (MCP surface)   ← depends on Groups 1–3
  ↓
Group 5 (test suite MVP) ← validates Groups 1–4; fixtures committed first
  ↓
Distribution roadmap     ← separate session
```

Group 2 is independent of Group 1 and can be implemented in parallel. Groups 3 and 4 depend on Groups 1 and 2 being complete so the test suite can validate everything together.

---

## Success Criteria

- [ ] TAclaw export bundle: `tatb`, `brain_quality`, `adapters_fidelity` non-empty on known arches
- [ ] TAclaw routing: brain_fast-eligible arches complete in <5s (was ~30s)
- [ ] Agent passport: every TAclaw job has `provenance.agent_passport` in export
- [ ] DETECT-AGT-001 fires on passport-less agentic call
- [ ] Test suite: `4/4 passed` on CI with committed fixtures
- [ ] Quality eval: avg quality score ≥ 75/100 across all fixtures
- [ ] Regression baseline committed for all 4 fixtures

---

## Files Touched (summary)

| File | Group | Change type |
|---|---|---|
| `chatbot/api/routes/taclaw.py` | 1, 2, 3 | TATB fetch + smart routing + passport mint |
| `chatbot/adapters/crawler.py` | 1 | fidelity_detail propagation through merge |
| `chatbot/modules/ta_exporter.py` | 1 | brain_quality + adapters_fidelity in TAExportBundle |
| `chatbot/modules/agent_passport.py` | 3 | NEW — passport mint/validate/expire |
| `chatbot/harness/governance.py` | 3 | passport validation in GovernanceAdapter |
| `policies/soc_detection_rules.yaml` | 3 | DETECT-AGT-001 rule |
| `mcp_server/server.py` | 4 | tool schema updates |
| `mcp_connector/client.py` | 4 | typed response updates |
| `taclaw/tests/run_suite.py` | 5 | NEW — test suite runner |
| `tests/data/taclaw/` | 5 | NEW — 4 fixtures + baseline files |
