# ThreatAssessor — Architectural Decision Log

Read this file at the start of every session. After any significant decision about architecture, logic, or format, add an entry: date, what was decided, reasoning, alternatives rejected.

---

## 2026-06-28 — SM worktree rerun + ADR closed-loop verification

### 1. SM rerun as a named worktree — arch-sm{N} naming convention

**What was decided:**
ScrumMaster-recommended reruns use `{base_arch}-sm{N}` naming (e.g. `aivss_test_arch-sm1`, `aivss_test_arch-sm2`). Each is a first-class report directory — a full analysis run from the SM-recommended MMD (`08b_recommended_target.mmd`) treated exactly like any other architecture. Separate from the `_N` numeric suffix used for plain reruns. `N` is the count of SM-specific reruns for that base arch.

**Storage layout (decided):**
SM reruns live as **subfolders under the base arch directory**, not as siblings in `report/`:
```
report/
  aivss_test_arch/             ← original run, untouched
    ground_truth.json
    08_scrum_master.json
    08b_recommended_target.mmd ← SM recommends this
    sm1/                       ← first SM rerun, self-contained
      before.mmd               ← copy of 08b_recommended_target.mmd
      ground_truth.json
      governance_signals.json
      run_diff.json            ← diff vs parent arch
      harness_perf.json
      [all standard report files]
    sm2/                       ← second SM rerun
      ...
```
`report/` stays clean — only original arch names at the top level. All SM artifacts are scoped under their parent. The harness writes to whatever `report_dir` is passed — `report/{arch}/sm{N}/` works with no pipeline changes.

**API surface for SM runs (dedicated routes to avoid touching path-traversal checks on existing routes):**
- `POST /api/v1/reports/{arch}/rerun-with-sm` — creates `sm{N}/` subfolder, runs analysis, returns `{n: 1, report_dir: "aivss_test_arch/sm1"}`
- `GET /api/v1/reports/{arch}/sm` — list all SM reruns for an arch (returns `[{n, run_ts, confidence, controls_resolved, techniques_closed}]`)
- `GET /api/v1/reports/{arch}/sm/{n}/files/{filename}` — serve files from the SM subfolder
- `GET /api/v1/reports/{arch}/sm/{n}/diff` — return `run_diff.json`

**Three pieces (in dependency order):**
1. **Worktree button + API route** — `POST /api/v1/reports/{arch}/rerun-with-sm` reads `08b_recommended_target.mmd`, creates `sm{N}/` subfolder, writes the MMD as `before.mmd`, runs `ThreatAssessorHarness(scenario="api_only")` with that subfolder as `report_dir`, writes `run_diff.json` on completion. Button shown in arch history only when `08_scrum_master.json` exists.
2. **Run diff** — `run_diff.json` written into `sm{N}/` comparing `controls_missing`, `techniques`, and `confidence` between the base arch and this SM run. Pure set arithmetic on `ground_truth.json` values — no LLM.
3. **ADR verification** — SM-ADR entries store machine-readable `source_techniques` and `source_controls` at write time. Dashboard reads `sm{N}/run_diff.json` and renders ADR entries with a `VERIFIED` badge when the stored controls/techniques are absent from the SM run's `controls_missing`. File is never auto-edited — verification is display-only.

**Reasoning:**
Treating SM reruns as first-class report directories gives them the full report set, Insights trending, and worktree chain view with no special-casing. The `_sm{N}` suffix is machine-parseable (base name extraction strips `-smN`) while being visually distinct from numeric reruns. The worktree is what generates the reference `ground_truth.json` that makes ADR verification data-driven instead of text-matching. Without the worktree run there is nothing to diff against.

**Alternatives rejected:**
- Storing SM reruns in a sub-directory of the base arch: breaks the flat report directory assumption throughout the codebase (API routes, Insights, file serving all expect `report/{arch_name}/`).
- Auto-editing `10_adr_report.md` to flip status: risky (file corruption, concurrent edits), unnecessary — dashboard overlay achieves the same UX without touching the file.
- Text-matching ADR prose to finding descriptions: unreliable. Storing technique IDs and control names at write time is O(1) lookup vs O(n) fuzzy match.

**Confidence:**
- Worktree button + API route: **90%** — copies a file and calls the existing analysis endpoint; no new pipeline logic.
- Run diff: **88%** — pure set arithmetic on structured JSON; only uncertainty is prior-run lookup (base-name stripping, already done in Insights trending).
- ADR write-time enrichment: **92%** — adding two fields to the existing `add-to-adr` payload and entry template.
- ADR dashboard verification overlay: **75%** — reads two JSON files and matches sets; uncertainty is edge cases (partial control name matches, techniques that appear in multiple paths).
- Insights SM-chain section: **70%** — data exists, chart infrastructure exists, but section layout needs thought to avoid duplicating existing cross-run trending.

### 2. SM worktree UI — worktree chain view

**What was decided:**
SM reruns are shown as an indented chain *within* the base arch's history entry — not as siblings in the flat arch list:
```
aivss_test_arch            [reload] [rerun] [✨ SM rerun] [delete]
  └─ sm1  Δ+12% conf · 3 controls resolved  [view] [↻ SM rerun]
     └─ sm2  Δ+6% conf · 1 control resolved  [view]
```
Each SM entry shows the delta vs its parent (confidence change, controls resolved, techniques closed) fetched from `run_diff.json`. "View" loads the SM subfolder's reports into the main view. "↻ SM rerun" on an existing SM run creates `sm{N+1}` from that run's `08b_recommended_target.mmd` — chaining further improvements.

The Insights tab View A gains a SM-chain sub-section when `sm1/` exists: confidence trend line per run, controls resolved count, techniques closed. Data source is `GET /api/v1/reports/{arch}/sm` list endpoint.

`_base_arch_name()` in `reports.py` already strips `_N` suffixes for Insights grouping. No change needed — SM runs are subfolders not siblings so they don't appear in the top-level arch list at all.

**Alternatives rejected:**
- SM runs as flat siblings (`aivss_test_arch-sm1/` in `report/`): pollutes the top-level arch list, breaks `_base_arch_name()` grouping, and loses the parent-child relationship.
- Separate "SM History" tab: over-engineering — the arch dropdown already has the right scope.

---

## 2026-06-28 — Unified model provider strategy (deferred implementation)

### 1. Config-driven provider registry + harmonised model settings

**What was decided:**
Extend `chatbot/config/settings.py` with a `ProviderRegistry` block and an `EmbeddingModelConfig` block. All current TA model behaviour is preserved via backward-compat defaults — no code changes required at decision time. The strategy is captured now so future provider integrations require only config additions, not code changes.

**Target shape (settings.py additions, not yet implemented):**

```python
class ProviderConfig(BaseModel):
    base_url: str
    api_key_env: Optional[str] = None   # None = no auth (local Ollama/vLLM)
    auth_type: str = "bearer"           # bearer | sigv4 | none

class ProviderRegistry(BaseModel):
    """Config-driven provider table. New providers = new entries here, zero code."""
    providers: Dict[str, ProviderConfig] = Field(default_factory=lambda: {
        "openrouter": ProviderConfig(
            base_url="https://openrouter.ai/api/v1",
            api_key_env="OPENROUTER_API_KEY",
        ),
        "bedrock": ProviderConfig(
            base_url="",            # SigV4 path — handled by existing Bedrock client
            auth_type="sigv4",
        ),
        # Future — zero code to add:
        # "doubleword": ProviderConfig(base_url="https://api.doubleword.ai/v1", api_key_env="DOUBLEWORD_API_KEY"),
        # "sakana":     ProviderConfig(base_url="https://api.sakana.ai/v1",     api_key_env="SAKANA_API_KEY"),
        # "ollama":     ProviderConfig(base_url="http://localhost:11434/v1",     api_key_env=None, auth_type="none"),
        # "vllm_local": ProviderConfig(base_url="http://localhost:8000/v1",      api_key_env=None, auth_type="none"),
    })

class EmbeddingModelConfig(BaseModel):
    provider: str = "openrouter"
    model: str = "nvidia/llama-nemotron-embed-vl-1b-v2:free"
    dimensions: int = 2048
```

`AppSettings` gains two new fields with backward-compat defaults:
```python
providers: ProviderRegistry = Field(default_factory=ProviderRegistry)
embedding: EmbeddingModelConfig = Field(default_factory=EmbeddingModelConfig)
```

**Model name convention (once implemented):**
`AgentModelConfig.model` strings use `provider/model-id` format:
```yaml
agent_models:
  blackhat:    openrouter/anthropic/claude-opus-4-8   # today's value, explicit
  red_team:    ollama/llama3.1:70b                    # future local model
  tester:      vllm_local/mistral-7b-instruct         # future cloud-hosted open weight
```
Empty string (`""`) continues to fall through to `LLM_PROVIDER` env-var default — full backward compat.

**`LLMClient.generate()` dispatch (once implemented):**
```python
provider_name, _, model_id = model.partition("/")
cfg = settings.providers.providers.get(provider_name)
if cfg.auth_type == "sigv4":
    # existing Bedrock path, unchanged
else:
    litellm.completion(model=f"openai/{model_id}", api_base=cfg.base_url, ...)
```
Special case for Responses API models (o3, o4-mini) — single `_needs_responses_api()` dispatch inside `generate()`, ~20 lines, callers unchanged.

**Embeddings (`chatbot/modules/embeddings.py`):**
`DEFAULT_EMBEDDING_MODEL` and `EMBEDDING_URL` become reads from `settings.embedding` instead of module-level constants. `get_embedding()` signature unchanged — callers unaffected.

**Reasoning:**
All the target providers (OpenRouter, Doubleword, Sakana.ai, Ollama, vLLM) expose OpenAI-compatible `/v1/chat/completions`. LiteLLM routes to any of them via `api_base` + `api_key` — the integration cost per new provider is config, not code. The current `LLMProvider` enum in `llm_client.py` hardcodes providers as Python, which requires a code change for every new one. Moving to a registry flips that: the enum stays for the two live providers (OpenRouter, Bedrock) during transition and can be removed once all callers use the registry path. The embedding model is currently hardcoded as a module-level constant in `embeddings.py` with no settings entry — consolidating it into `AppSettings` means the Config tab and `user_config.json` can expose it alongside agent model routing.

**What is NOT changing now:**
- `LLMProvider` enum — stays, two active values (openrouter, bedrock)
- `PROVIDER_MODELS` dict in `llm_client.py` — stays
- `ProviderConfig` dataclass in `llm_client.py` — stays (different class from the new settings one; rename deferred)
- All critic, stage, and harness code — untouched
- All existing env-var defaults — preserved

**Alternatives rejected:**
- Implement immediately: no current provider gap; adding infrastructure ahead of need is premature. The design is clear enough to implement correctly when the first new provider is needed.
- Single flat `providers.yaml` file separate from settings: splits config into two sources and breaks `user_config.json` / Config tab integration. Everything in `AppSettings` is the single source of truth.
- Wrap each provider in its own adapter class: over-engineered for what is a URL + key difference. LiteLLM already abstracts the HTTP layer; adapters add indirection with no benefit.

---

## 2026-06-28 — Omnigent meta-harness assessment; TA CLI consideration

### 1. Omnigent not integrated into TA — patterns deferred to scale-out phase

**What was decided:**
Omnigent (v0.3.0-alpha, Apache 2.0) was assessed as a candidate meta-harness to augment or replace TA's harness. Decision: do not integrate. Two patterns worth borrowing — declarative cost ceiling gate and ALLOW/DENY/ASK verdict tier — are deferred until multi-tenant scale-out.

**Reasoning:**
The core architectural mismatch is runtime model. Omnigent supervises external CLI processes (Claude Code, Codex, Cursor) via a local server at `:6767`; TA makes direct Python LLM API calls via LiteLLM. Adapting TA's critics to Omnigent's model would require each critic to become an external CLI process, introduce a `:6767` server dependency, enforce a Python 3.12+ upgrade (TA runs on 3.10+), and replace `PipelineContext` state-passing with Omnigent's session/tool paradigm. The rewrite cost is high; the benefit is minimal because Omnigent has no domain intelligence (no concept of threats, techniques, AIVSS, or governance signals). The overlap in model routing, governance concepts, and stage isolation is real but superficial — they solve it at different layers for different problems.

Where Omnigent genuinely does more: OS-level sandboxing (bwrap/seatbelt), multi-harness routing (swap Claude Code → Codex per agent), multi-device session sharing, declarative `max_cost_usd` spend caps, SaaS tool governance (GitHub, Gmail, GDrive). None of these are current TA requirements.

Where TA does more: MITRE ATT&CK/ATLAS domain mapping, AIVSS three-flow safety scoring, MoE critic consensus with tier-sharpening, SIEM sink, 16-file report packages, Insights trending.

**Patterns deferred (implement when scaling out, no Omnigent dependency):**
- **Declarative cost ceiling** — `max_cost_usd` gate in `GovernanceSignals` that pauses the pipeline before expensive critic runs. Infrastructure already exists (`LLMClient` tracks `cost_usd` per call). Worth building when TA becomes multi-tenant.
- **ASK verdict tier** — currently governance returns ALLOW or BLOCK. An ASK tier (HIGH severity → pause for human confirmation, not hard block) requires a pause/resume SSE event + dashboard UI response surface. Worth building when the dashboard gains a human-approval workflow.

**Alternatives rejected:**
- Thin wrapper only (borrow Omnigent's policy YAML, keep TA internals): YAML-based policy declaration adds config surface without reducing code complexity; TA's Python-native governance is already readable and testable.
- Evaluate again at v1.0: captured here instead — no need to re-evaluate the same framework; revisit only if Omnigent adds native LiteLLM/API-call mode.

---

### 2. TA CLI as a future interface layer

**What was decided:**
The idea of a first-class TA CLI (beyond the existing `demo_deterministic_engine.sh` and `demo_expert_llm.sh` wrappers) was raised during the Omnigent assessment. Not implemented; captured as a future interface direction.

**Reasoning:**
Omnigent's strongest surface is its CLI (`omni run agent.yaml`), which prompted the question of whether TA should have an equivalent. The existing shell wrappers are functional but are not a proper CLI — no subcommands, no flags, no composability. A real CLI (`ta analyze architecture.mmd --scenario full_moe --ssp medium_risk_cloud`) would: lower the barrier for CI/CD integration (run threat assessment in a GitHub Action), enable piping output to other tools, and make TA scriptable without standing up the FastAPI server. The Omnigent comparison confirmed the pattern — a CLI wrapper over `ThreatAssessorHarness.run()` is a natural next interface layer that doesn't conflict with the REST API.

**Deferred because:** REST API + dashboard is the primary delivery surface right now. CLI is the right next interface once the core pipeline stabilises further and there is a concrete CI/CD integration use case.

**Proposed shape when implemented:**
- Entry point: `chatbot/cli/main.py` using `click` or `typer`
- Commands: `ta analyze <mmd>`, `ta validate <mmd>`, `ta report <arch-name>`, `ta insights`
- Thin wrapper over `ThreatAssessorHarness` — no new pipeline logic
- Output modes: `--fmt json` (machine-readable), `--fmt md` (markdown briefing), default (human summary)
- No new dependency beyond `click`/`typer` (already common in the Python ecosystem)

**Alternatives rejected:**
- Omnigent's YAML agent spec as the TA CLI definition: requires Omnigent as a runtime dependency and reduces TA to one of many harnesses it can drive — wrong ownership model.

---

## 2026-06-27 (Session 7) — Per-Agent Model Routing, Insights Cross-Run Trending, Governance Gate Redesign

### 1. HarnessModelGuardian — single owner of all agent model routing

**What was decided:**
`HarnessModelGuardian` is constructed once per pipeline run, stored in `ctx["_model_guardian"]`, and owns one `ModelRouter` per named agent (architect, tester, red_team, purple_team, blackhat, storycaster, scrum_master, moe_orchestrator, threat_analyst). Per-agent config lives in `settings.agent_models` as `AgentSwarmConfig` (each entry: `model` string + `fallbacks` list). Empty `model` string = backward-compat sentinel that silently falls through to `LLM_PROVIDER` env-var default. Fallback events are drained from all routers after every stage and accumulated in `ctx["model_fallbacks"]`; any non-empty list appends a `model_fallback_warning` to `ctx.errors`. Chain exhaustion raises `ModelChainExhaustedError` (optional stages catch it and continue; required stages propagate).

**Reasoning:**
All agents previously shared one global model via env vars. Per-agent routing is needed to assign cheaper models to lower-stakes critics (tester/scrum_master) and more capable models to high-stakes ones (blackhat/moe_orchestrator). The guardian pattern avoids scattered env-var reads in stage logic and gives a single auditable place to see which model ran for which agent. LLMClient internals are untouched — fallback is at harness level, not provider level.

**Alternatives rejected:**
- Per-stage `model_router` (existing stub): had no mechanism to broadcast per-agent models into `run_moe_pipeline()`; would not have covered ScrumMaster re-trigger path.
- Single broadcast `model=` param to `MoEOrchestrator`: was the existing pattern — all critics got the same model, defeating the purpose.
- Separate config file for model routing: `settings.agent_models` keeps it with other tunable settings and benefits from the existing `update_settings()` / `user_config.json` machinery.

---

### 2. QualityStage added to API_ONLY scenario

**What was decided:**
`API_ONLY` scenario now runs `[AnalysisStage, ReportStage, QualityStage]`. Previously `QualityStage` only ran in `FULL_MOE`, so `governance_signals.json` was never written on normal analysis runs. The Insights tab Governance & AIVSS section showed "No governance data" on every standard analysis.

**Reasoning:**
Governance checks are cheap (66ms, $0.00) and benefit every run regardless of whether Expert Review is enabled. The AIVSS inbound/internal/outbound scoring requires `governance_signals` to exist; without it the Insights tab is empty. The fix is a one-line scenario change — no pipeline logic altered.

**Alternatives rejected:**
- Lazy governance computation in the API when Insights tab requests it: would require a new API endpoint that re-reads and re-processes `ground_truth.json` on demand, adding latency to the UI and duplicating the governance pipeline outside the harness.

---

### 3. Phone PII regex false positive on CVE IDs

**What was decided:**
`_RE_PHONE` pattern `\b\d{4}[\s-]?\d{4}\b` matched `CVE-2018-6789` because CVE IDs use `YYYY-NNNN` format. Fixed with negative lookbehind `(?<!CVE-)(?<!cve-)(?<!\d-)(?<!\d)` and tightened separator from optional (`?`) to required (`[\s-]`). This eliminates CVE false positives while preserving real SG phone number detection (`9123 4567`, `+65 9123-4567`).

**Alternatives rejected:**
- Requiring `+65` prefix: excludes the majority of local SG phone numbers which are written without country code.
- Post-filter: checking match context for "CVE" after the fact — more fragile than lookbehind.

---

### 4. Insights tab — cross-run trending architecture (three views)

**What was decided:**
The "Attack Surface" section (duplicating Threat Paths tab) was removed from Insights and replaced with a **Cross-Run Trends** section with three views accessible via a tab switcher:

- **View A — Single Arch:** architecture selector grouped by base name (strips `_N` rerun suffixes), run-over-run table with risk delta arrows (▼ improving, ▲ worsening), IPDR card-format persistent gaps (4 cards: Identify/Prevent/Detect/Respond — each with mini bar showing persistence proportion and colour bands red/amber/yellow), SVG line chart for pipeline gate drift (Ingress/Internal/Egress lines, Y-axis fully labelled LOW→CRITICAL, auto analysis note per gate).
- **View B — Multi-Arch:** top-8 risk cards (domain-style), systemic control gaps with hover popover listing arch names, most-frequent techniques with inline name + hover popover, paginated table (tbody-swap pagination — no full reload on page flip).
- **View C — Domain:** domain cards grouped by SSP profile + keyword classification, collapsible arch list on count click.

New backend endpoint `GET /api/v1/insights/all` returns all architectures in one call with: `base_name` (rerun grouping), `domain`, `risk_score`, `defensibility`, `confidence`, `controls_missing`, `techniques` (flat dedup), `aivss_overall/severity`, `governance_dims {D1–D5}`.

**Reasoning:**
The original Section B "Design Patterns" only showed the current run's attack paths sorted differently — genuinely duplicative of the Threat Paths tab. The trending use case (how is this architecture improving run-over-run? what do all my architectures consistently get wrong? which domain is weakest?) requires cross-run aggregation that the original design deferred indefinitely. The three-view structure maps directly to the three sensing modes: single-arch improvement, systemic multi-arch gaps, domain-level benchmarking.

**Alternatives rejected:**
- Keeping Attack Surface in Insights and adding trends: would make the section too long and bury the actionable insights below a table users have already seen.
- Server-side aggregation on every tab load: 28 dirs × 2 file reads = 56 reads, all fast enough for a single `/insights/all` call on tab switch; no caching layer needed at current scale.

---

### 5. Pipeline gate cards (Ingress/Internal/Egress) replace flat D1–D5 list

**What was decided:**
Governance & AIVSS section A now shows three gate cards mapped to the harness controller's three flow checks:
- **Ingress** = D1 Exploitation + D5 Sovereignty (inbound) — what enters the pipeline
- **Internal** = D2 Manipulation + D4 Identity — agent/LLM layer behaviour
- **Egress** = D3 Data Leakage + D5 Sovereignty (egress) — what leaves the system

Clean gate (no MEDIUM+ findings): green border, `✓ Clear` chip, check count, one-line confirmation. Found gate: severity chip, `Found:` concrete signals extracted from raw data, `Concern:` plain-language description, `💡` actionable guidance line scaled to severity. "LOW" badge suppressed when no findings — avoids the perception that something is wrong.

**Reasoning:**
The harness controller is designed around three flow gates (inbound/internal/outbound). Displaying D1–D5 as flat cards with no gate context required users to mentally map dimensions to pipeline stages. The gate framing makes the governance model self-explaining and directly connects to the AIVSS inbound/internal/outbound scores.

**Alternatives rejected:**
- Keeping D1–D5 cards and adding gate labels: D5 Sovereignty appears in both Ingress and Egress with different signals — splitting it across two cards is confusing. Gate cards with constituent dims shown inside is cleaner.

---

## 2026-06-21 (Session 4) — Governance Gateway: 5-dimension pipeline safety layer (steps 1–6)

### 1. Governance layer is deterministic only — no LLM subagents per run

**What was decided:**
`InhouseGovernanceAdapter` covers all 5 OWASP Agentic dimensions using regex, graph traversal, and file-stat checks. No LLM calls per pipeline run. `AGTGovernanceAdapter` is an optional compliance upgrade (`pip install agent-governance-toolkit`) that wraps the inhouse adapter with a formal policy engine and Merkle-chain audit log — enabled only when `governance.agt_enabled = True`.

**Reasoning:**
Governance checks are closed-world (finite, known-at-design-time patterns). LLM subagents are appropriate for open-world problems. Measured cost: 66ms/run, $0.00. An LLM doing equivalent checks would cost ~$0.02–0.05/run and add 10–20s latency — wrong cost profile for a gate that runs on every pipeline execution. The two known gaps (split injection across nodes, prose region format) are deliberate false negatives: fixing them would require semantic reconstruction that produces more false positives than true detections.

**Alternatives rejected:**
- Per-run LLM governance critic: too costly, wrong abstraction — would conflate "is the input safe" with "is the architecture good".
- Embedding similarity for split-injection detection: worth revisiting when a real adversarial corpus demonstrates the gap is exploited; not speculative work now.
- Full AGT integration as a required dependency: AGT's install footprint (Rust, Node.js 18+, .NET 8+) is disproportionate for the 1.5 dimensions it covers natively. InhouseAdapter is the primary implementation; AGT is an audit-layer upgrade.

---

### 2. QualityStage position in FULL_MOE pipeline

**What was decided:**
`QualityStage` sits between `ReportStage` and `CriticStage`: `analysis → report → quality → critics → scrum_master`. It checks the raw MMD input (captured by `AnalysisStage` as `_raw_mmd_content`) and the `ground_truth` artifact before critics run. It is `required=False` — governance failure is audited, never fatal, except `CRITICAL+blocked` exploitation which appends to `ctx.errors`.

**Known gap (documented, fix deferred to step 7):**
`QualityStage` runs before the SM retrigger loop, so ToolErrors accumulated during SM-triggered critic re-runs are not written to `governance_signals.json`. Fix: add a second `save_governance_signals()` call at the tail of `ScrumMasterStage._logic()` to merge accumulated D4 errors (~8 lines). Deferred because SM retriggering rarely calls tools (MVP1 has `_tools_enabled=False`).

**Alternatives rejected:**
- Moving QualityStage to after ScrumMasterStage: `governance_signals` SSE event would fire after `complete`, which the frontend never sees on a live run.
- Running QualityStage twice (before and after critics): doubles the check cost and creates two conflicting `governance_signals.json` writes mid-pipeline.

---

### 3. Governance + Summary UI merged into single `🔍 Insights` tab

**What was decided:**
The originally planned separate Governance SOC panel (inside Harness tab) and Summary nav tab are merged into one `🔍 Insights` nav tab with two clearly labelled sections:

- **Section A — "Input Safety" (this run):** 5 dimension cards from `governance_signals` SSE + past-run architecture selector. Filter pills: `[All] [Flagged only] [CRITICAL]`. Goal: "Was this architecture safe to process?"
- **Section B — "Design Patterns" (across runs):** Multi-select architecture filter driving Risk Trend table, Top Threats bar, Common Gaps table, Critic Attribution. Goal: "Are my architectures improving, what do I keep getting wrong?"

Single merged endpoint: `GET /api/v1/insights?archs=a,b,c` (replaces the originally planned separate `/api/v1/governance` + `/api/v1/summary` routes). Section B cross-links: clicking any architecture name loads it in the main dashboard.

**Reasoning:**
Two separate panels would show overlapping cross-run trend data from the same source files (`ground_truth.json`, `07_moe_orchestrator.json`). The merged design eliminates ~130 lines JS, one API route, one nav tab button, and the user confusion of "governance over time" vs "risk trend over time" being separately presented. The two sections have distinct goals and distinct data sources (SSE event vs aggregated report dirs) — the section header legend makes this explicit.

**Alternatives rejected:**
- Keeping Governance panel inside Harness tab only: buries the most user-relevant safety information inside a developer-facing tab.
- Dropping Summary tab entirely: cross-run design patterns are genuinely useful once a user has 3+ reports; worth keeping, just consolidated.
- Separate `/api/v1/governance` and `/api/v1/summary` routes: two round trips for data that can be merged in one aggregation pass over the same report directories.

---

### 4. Adversarial test corpus and red-team governance approach

**What was decided:**
After the initial 21-test suite was written, a systematic red-team analysis identified 7 bypass paths. Five were fixed in the detection logic; two were documented as deliberate false negatives via `xfail` tests:

Fixed bypasses: Cyrillic homoglyph injection (confusable map + NFD normalise), URL-encoded path traversal `..%2F`/`..%5c`, NRIC with spaces "S 1234567 A", custom credential keys (`db_pass`, `database_url`, `conn_string`), LLM→external-service ZDR edge not firing when labels are inline on edge lines (node-label map + edge-stripping fix).

All adversarial inputs live as named fixture files in `tests/data/governance/` so regressions are caught automatically. The `TestAdversarialCaught` class documents each bypass with an assertion message that names the specific regex or logic path that would have regressed.

**Reasoning:**
Inline test data (`mmd = '...'`) disappears from the regression corpus when tests are refactored. Fixture files persist independently and can be extended without touching test logic. The `xfail(strict=True)` pattern for known limitations is preferable to skipping — if detection improves unexpectedly, the suite flags it as a conscious change rather than silently passing.

**Alternatives rejected:**
- Keeping inline MMD strings for simple boundary cases: one exception made (`test_empty_validations_no_crash`) because an empty `expert_validations` dict cannot come from a real pipeline run — a fixture file would be misleading.
- Fixing split-injection via regex lookahead across node boundaries: produces false positives on legitimate multi-word node sequences; not worth the complexity.

---

## 2026-06-14 (Session 3) — Dashboard fixes, SM Overview sub-tab, Full pipeline perf telemetry

### 1. Threat Paths tab showed "Attack paths loading…" for saved reports

**What was decided:**
`_loadArchFromReports()` set `this.analysisData` from `ground_truth.json` but never populated `this.attackPaths`. `loadAttacksTab()` guards on `if (!this.attackPaths …) return` and bailed immediately, leaving the placeholder text. Fixed by adding `this.attackPaths = gt.expected_attack_paths || []` right after `this.analysisData` is set in `_loadArchFromReports`.

**Reasoning:**
`handleComplete()` (live SSE path) populates `attackPaths` from `analysisData.analysis.expected_attack_paths` at line 668. The saved-report load path skipped this step entirely. One-line fix.

**Alternatives rejected:**
- Removing the null guard in `loadAttacksTab`: would cause a crash on first page load before any analysis runs.

---

### 2. ScrumMaster Overview sub-tab added

**What was decided:**
Added a `🧩 ScrumMaster` sub-tab to the Overview detail bar (between Expert Consensus and User Journeys). Fetches `08_scrum_master.json` lazily on first click and renders: harmony chip + confidence trajectory, synthesis note, top-5 action plan items (immediate tier first with confidence-gain badges and first-step hints). Falls back to a "not run yet" prompt linking to Configuration if the file is absent.

**Reasoning:**
The ScrumMaster full tab is detailed but requires a separate nav click. Users wanted an at-a-glance SM summary before diving into Expert Review details — the Overview tab is the natural home for this.

**Alternatives rejected:**
- Embedding SM summary directly in the Overview dashboard card strip: too much density; the strip is already crowded with risk/defensibility/confidence chips.
- Rendering SM on Overview tab load: lazy-on-click is consistent with arch-diagram and user-journeys sub-tabs.

---

### 3. Harness Pipeline Performance — three root causes fixed, full seven-component table

**What was decided:**
Fixed three independent bugs that caused the Pipeline Performance section to show "No performance data yet":

1. **Wrong sort order in JS**: The reports list is sorted newest-first by `analysed_at`. The JS was iterating `reports[length-1]` downward, hitting the oldest (no-MoE) reports. Fixed by sorting `rawReports` by `analysed_at` descending before searching, with the currently-loaded arch pinned to position 0. Search window widened from 5 to 10.

2. **`pipeline_perf` saved before it was populated**: In `MoEOrchestrator.run()`, `result.to_dict()` was written to `07_moe_orchestrator.json` before the perf aggregation block ran, so the file always contained `"pipeline_perf": {}`. Fixed by moving the perf block above the `json.dump` call.

3. **Purple Team and Blackhat never called `_attach_perf`**: `architect`, `tester`, and `red_team` results go through `_process_*_validation()` which calls `_attach_perf`. Purple Team and Blackhat constructed `ValidationResult` directly without it. Fixed by wrapping both in `self._attach_perf(ValidationResult(...), critique_score)`.

Additionally: `RedTeamerCritic`, `PurpleTeamerCritic`, and `BlackhatCritic` override `critique()` and make their own `llm_client.generate()` calls without copying response telemetry back onto the returned `CritiqueScore`. Fixed by capturing `_wall_start`/elapsed and stamping `llm_calls`, `llm_tokens`, `llm_cost_usd`, `llm_latency_s`, `llm_model`, `wall_clock_s` onto `raw_score` before returning.

**Orchestrator synthesis** (`_llm_synthesize` + `_reflect_contradictions`) now accumulates into `self._synth_perf` (reset at `run()` start) and is written to `pipeline_perf["critics"]["orchestrator"]`.

**ScrumMaster**: Added `perf: Dict` field to `ScrumMasterResult`. Added `_reset_perf()` / `_accum_perf()` helpers on `ScrumMasterCritic`. Both SM LLM calls (`_formulate_proposals` + `_build_action_plan`) were also using `client.complete()` — a method that does not exist on `LLMClient` — causing silent fallback to the deterministic path with no LLM spend. Fixed to `client.generate()` with telemetry capture. `perf` is serialised into `08_scrum_master.json` via the existing `to_dict()` and fetched separately by the JS perf table.

JS table extended: `criticOrder` now includes `orchestrator` and `scrum_master`; SM tokens/cost added to grand totals; header changed from "Critics ran" to "LLM components".

**Reasoning:**
The perf table is referenced in the blog series (Part 5) and needs real numbers. The three bugs compounded: even after fixing the sort order, the data in the files was empty because of the save-order bug; even after fixing that, RT/PT/BH were always zero because their `critique()` overrides didn't propagate telemetry.

**Alternatives rejected:**
- Reconstructing perf from `expert_validations[*].perf` only (fallback path): still misses orchestrator, SM, and would be wrong for any critic using a non-standard `critique()` override.
- Adding a separate perf log file: unnecessary indirection — the existing `07_moe_orchestrator.json` and `08_scrum_master.json` are the natural homes.

---

### 4. `critic_count` inflated — zero-token critics excluded

**What was decided:**
`pipeline_perf["critic_count"]` was counting all critics with any `perf` dict (including empty `{}`), producing 5 even when only 2 ran. Fixed in both Python (perf aggregation loop: `_vr.perf.get("llm_tokens", 0) > 0` guard) and JS fallback reconstruction (same guard on `v.perf.llm_tokens`). `critic_count` now reflects only critics with actual LLM spend.

**Reasoning:**
The count was used in the summary line "Critics ran: 5" and efficiency calculations. Both were misleading.

**Alternatives rejected:**
- Counting based on non-null `validation_status`: would count resumed-from-disk critics that spent no tokens this run.

---

## 2026-06-14 (Session 2) — UI Polish, SM Enhancements, Harness Performance, Config Fixes

### 1. Config tab — `BOOL_FIELDS` coercion fix (applies to all boolean toggles)

**What was decided:**
`_collectConfigFormValues()` added a `BOOL_FIELDS` set. All `enabled` toggles and `llm_enrichment` now send actual JS booleans to the API instead of strings `"true"`/`"false"`. Pydantic v2 coerces any non-empty string to `True`, so saving "Disabled" was silently persisting as `True` for every critic toggle (MoE, Purple Team, Blackhat, ScrumMaster, StoryCaster LLM enrichment).

**Reasoning:**
Root cause was invisible — the Config tab appeared to work (no error) but changes to boolean fields were not persisted correctly. Affected all boolean selects since inception.

### 2. Expert Review tab — 3-section restructure with critic filter pills

**What was decided:**
Section A (User Journey), B (Critic Thematic), C (Synthesis). Each section is collapsible. Section B has filter pills per critic (All + individual). Section C has filter pills (Consensus, Blindspots, Disagreements, Tiers, ScrumMaster). SM excluded from Section B via `isSynthMeta` guard — only renders in Section C.

### 3. ScrumMaster UI card improvements

**What was decided:**
- **Legend** as collapsible `<details>` with one entry per line
- **Action plan** grouped into collapsible tiers (Immediate / Structural / Anti-patterns) with confidence gain badge per item
- **Anti-pattern detection** in action plan — items matching policy/governance/training keywords flagged and sorted last
- **`📋 Add to ADR` button** on each action plan item calls `POST /api/v1/reports/{arch}/add-to-adr` which appends an `SM-ADR-XX` entry to `10_adr_report.md` with OPEN status
- **SM ↻ re-run button** in Section C card header — same as other critics, calls `/run-critic?critic=scrum_master`
- **Rationale formatting** — `_smFormatRationale()` splits on `. ` / ` — ` separators, surfaces only named-critic evidence as `→` lines; generic notes folded into lead
- **SM tier items** — stripped to control name + first named-critic evidence, word-trimmed at sentence boundary (no mid-word cuts), old stale "consider enriching node labels" text upgraded at render time

### 4. Independent critic re-run (`GET /api/v1/run-critic`)

**What was decided:**
New SSE route runs a single critic or ScrumMaster on existing analysis without re-running the full pipeline. Uses `MoEOrchestrator.run_targeted([critic])` for critics, `ScrumMasterStage` for SM. After any critic completes, SM re-runs automatically if `scrum_master.enabled=true`. Every rendered critic panel (including already-run ones) has a `↻` button; not-run optional critics have `▶ Run now`. Status shown as a fixed bottom-right toast that never disrupts content.

**Reasoning:**
Re-running a full Expert Review (~90s) just to get one critic's output (e.g. enabling Blackhat after the initial run) was wasteful. `run_targeted()` loads cached JSON for other critics, runs only the named one, re-synthesises MoE.

### 5. RAPIDS category weights (`RAPIDSCategoryWeights` in settings.py)

**What was decided:**
New `RAPIDSCategoryWeights` model with per-category float multipliers (0.5–2.0, default 1.0) added to `AnalysisEngineSettings`. `calculate_overall_risk_score()` now does a weighted RAPIDS average instead of `sum/len`. SM `_build_baseline_feedback` hint generation fixed to map critic-used terminology to actual RAPIDS category keys (e.g. "lateral movement" → `insider_threat`). Dashboard has `⚖️ RAPIDS Category Weights` Config section with one-click "Apply for next run" buttons from SM hints.

**Reasoning:**
The previous equal-weighting ignores architecture-specific threat relevance. SM hints were generating hints for non-existent RAPIDS keys (e.g. `lateral_movement` doesn't exist; it maps to `insider_threat`). The hint was entirely inert before this fix.

### 6. LLM performance telemetry pipeline

**What was decided:**
`CritiqueScore` gains 6 perf fields (`llm_calls`, `llm_tokens`, `llm_cost_usd`, `llm_latency_s`, `llm_model`, `wall_clock_s`). `CriticAgent.critique()` captures from `LLMResponse`. `_attach_perf()` helper propagates to `ValidationResult.perf`. `MoEResult.pipeline_perf` aggregates per-critic timings + totals. Saved in `07_moe_orchestrator.json`. Harness tab `📊 Pipeline Performance` section shows per-critic table (calls, tokens, cost, latency, wall-clock, efficiency) with automatic improvement hints. Fallback path reconstructs from `expert_validations[*].perf` for files that don't yet have top-level `pipeline_perf`.

**Alternatives rejected:**
- Logging only (not persisted): can't show in dashboard across sessions.
- Separate metrics file: would need another API route; `07_moe_orchestrator.json` already loaded by the tab.

### 7. Harness tab

**What was decided:**
`🔧 Harness` nav tab (always accessible, own `harness-pane-wrapper` DOM element). Three collapsible sections with `localStorage` state: Self-Check (7 checks, run-on-trigger, per-item retry with fix hint), Scenario Registry (4 expanded cards per scenario with When/Example/Triggers/Troubleshoot), Stage Executors (2 expanded cards with same structure). SM-corrected MMD file reference in baseline feedback — picks `08b_recommended_target.mmd` if it exists, falls back to `08a_quick_wins.mmd`, then `after.mmd`.

### 8. SM `_build_redesign_recommendations` rewrite (tiered, concrete)

**What was decided:**
When `redesign_signal=True`, action plan is tiered: Tier A (Immediate) pulls from MoE consensus critical/high recs — apply now while structural work is planned. Tier B (Structural) maps each blindspot through a `_DECISION_MAP` keyword table to a concrete architectural decision with a specific `first_step`. Falls back to a useful generic template if no keyword matches. `is_antipattern` and `confidence_gain` fields added to all action plan items via the strategist LLM prompt.

**Reasoning:**
Original was 3 items all saying "Redesign: [blindspot description]" with identical rationale — useless for decision-making. The new approach gives the user something to do for each gap.

### 9. `save_settings()` nested model serialisation fix

**What was decided:**
`save_settings()` rewrote to use `model_dump()` on both `new_settings` and `defaults` — producing plain dicts that `json.dumps` can serialise. Previous version iterated model fields directly, failing on nested pydantic models like `RAPIDSCategoryWeights` with `TypeError: Object of type RAPIDSCategoryWeights is not JSON serializable`.

### 10. `_smAddToAdr` / `POST /api/v1/reports/{arch}/add-to-adr`

**What was decided:**
New route appends SM action items to `10_adr_report.md` as `SM-ADR-XX` entries (OPEN status, date, source, context, first step). Auto-increments index by scanning existing `SM-ADR-\d+` entries. Button shows `✅ SM-ADR-01 added` with inline `→ saved to 10_adr_report.md` confirmation. Button `📋 Add to ADR` (was `+ ADR`).

**Reasoning:**
Closes the SM action → ADR loop without requiring a full pipeline re-run. Users can mark individual SM items as accepted decisions directly from the Expert Review tab.

---

---

## 2026-06-14 — Phase D: ThreatAssessor Harness + ScrumMaster Critic

### 1. ThreatAssessor Harness (harness.py / harness_stages.py)

**What was decided:**
Built a controller gateway (`ThreatAssessorHarness`) that orchestrates the analysis pipeline via registered scenario-stage configurations. Stages: AnalysisStage, ReportStage, CriticStage, ScrumMasterStage. Framework interfaces mirror CrewAI/LiteLLM patterns without importing them — swap is one-line per stage. `ScenarioRegistry` uses a decorator; `PipelineContext(dict)` subclasses dict so existing consumers work unchanged. `SyncExecutor` is active; `AgentExecutor` is a stub for future LLM agent migration. `ModelRouter` provides primary→fallback chain via existing `llm_client.py` with no new deps.

**Reasoning:**
`streaming.py` and `moe_orchestrator.py` had no clean extension seam. Adding any new stage required editing core pipeline files. The harness isolates optional stage failures (non-required stages caught, not raised), routes by scenario, and becomes the single callable surface for the MCP gateway and backtest loops.

**Alternatives rejected:**
- CrewAI/LiteLLM dependency: would replace existing `llm_client.py` layer and add 50MB of deps for patterns we could implement in ~150 lines.
- Harness inside `streaming.py`: coupling; the backtest runner and MCP gateway also need `harness.run()`.

### 2. ScrumMaster Critic (scrum_master_critic.py)

**What was decided:**
Meta-critic that runs after all MoE critics complete. Algorithm: analyse impediments (deterministic) → confidence gate (≥90% → prioritise only) → harmony check (majority unresolvable → redesign_signal) → targeted re-trigger (max 2 iterations, max 2 critics/iter) → sharp top-N action plan → baseline feedback to det-engine. `ImpedimentItem.resolvable` distinguishes structural gaps (redesign needed) from addressable ones. `BaselineFeedback` carries structured engine-improvement hints when redesign_signal=True. SM items are classified by priority into MoE improvement tiers (critical/high → quick_wins, medium → recommended, low → maximum) and merged into `07_moe_orchestrator.json`, then `08_improvement_summary.md` is regenerated.

**Reasoning:**
MoE's synthesis is a single pass; SM adds an active improvement loop that works towards harmony rather than brute-forcing higher scores. Stop conditions (confidence gate, MIN_DELTA, redesign_signal) prevent wasteful re-trigger rounds when the architecture is inherently limited.

**Alternatives rejected:**
- SM inside MoEOrchestrator: MoE owns sequencing; SM owns cross-critic synthesis. Separation keeps each class single-responsibility.
- Running all critics again on re-trigger: `run_targeted()` added to MoEOrchestrator re-runs only named critics and loads saved JSON for others.

### 3. Expert Review tab — 3-section restructure

**What was decided:**
Expert Review tab restructured into three collapsible sections: A) User Journey Assessment (how stories shaped critic input), B) Critic Thematic Assessment (confidence waterfall + critic panels with filter pills), C) Synthesis Assessment (MoE consensus + blindspots + contradictions + improvement tiers + ScrumMaster card). ScrumMaster is synthesis-only — excluded from Section B's `isSynthMeta` guard. Both sections have filter pills. SM result loaded from `08_scrum_master.json`; SM-REFINED badge shown on consensus items from re-triggered critics.

**Reasoning:**
The tab was a flat scrolling list. With 7 critics + synthesis + SM the list became unwieldy. Sectioned layout lets users zoom into the layer they care about without scrolling through everything.

### 4. Dashboard — Harness tab

**What was decided:**
Dedicated `🔧 Harness` nav tab (always accessible — not gated on `analysisData`). Uses its own `harness-pane-wrapper` DOM element (same pattern as `config-pane-wrapper`) so it never overlaps with the upload form or tab-content. Three collapsible sections (Harness Self-Check, Scenario Registry, Stage Executors) with `localStorage`-persisted open/close state. Self-check runs only on user trigger — idle checklist on load, animated per-check execution, per-item retry with fix hint. Scenario and Executor sections use expanded 4-field cards (when to use, example, triggers, troubleshooting) rather than sparse tables.

**Reasoning:**
The harness is invisible during normal operation but critical for understanding what's running. A health-check tab surfaces its state without requiring a developer to read source code. Run-on-trigger (not on load) avoids unnecessary API calls every time the tab is opened.

### 5. Config tab — boolean coercion bug fix

**What was decided:**
`_collectConfigFormValues()` in dashboard.js added a `BOOL_FIELDS` set. Fields in the set are converted from string `"true"`/`"false"` to actual JS booleans before sending the PUT payload. Affected fields: `enabled` (moe, purple_team, blackhat, scrum_master), `llm_enrichment` (story_caster).

**Reasoning:**
Pydantic v2's `model_validate` coerces any non-empty string to `True` for `bool` fields. The `<select>` elements returned strings, so saving "Disabled" (string `"false"`) would silently persist as `True`. Bug affected all boolean toggles across the Config tab since the beginning.

**Alternatives rejected:**
- Fix on the backend (coerce strings before validate): the API should receive correct types; the form is the source of the error.

---

## 2026-06-13 — Phase B: APT attribution + KEV-backed CVE enrichment on attack paths

### 1. APT group attribution added to attack path risk scenarios (MITRE ATT&CK intrusion-sets)

**What was decided:**
`MitreHelper` now indexes all non-revoked `intrusion-set` objects from `enterprise-attack.json` plus their `uses` relationships to `attack-pattern` and `malware`/`tool` objects. Six new indexes added:

| Index | Key → Value |
|---|---|
| `_intrusion_sets` | list of all non-revoked group objects |
| `_group_by_ext_id` | `"G0119"` → group object |
| `_techniques_by_group` | internal group ID → [attack-pattern IDs] |
| `_groups_by_technique` | attack-pattern ID → [group IDs] |
| `_malware_by_group` | internal group ID → [malware/tool IDs] |
| `_cves_by_technique` | attack-pattern ID → [CVE strings from description regex] |

Pickle cache versioned (`_PICKLE_VERSION = 2`) so stale caches auto-reject on load and rebuild from JSON — version mismatch raises `ValueError` caught at load time, falls through to JSON parse.

Four new public methods: `get_groups_by_technique()`, `get_techniques_for_group()`, `get_cves_for_technique()`, `get_malware_for_group()`. All resolve external IDs (`T1190`, `G0119`) to internal IDs before index lookup.

New module `chatbot/modules/threat_scene_deepener.py`: `deepen_threat_scenes()` adds `apt_evidence`, `cve_ids`, `kev_hits`, `ransomware_linked` to each AP's `risk_scenario` in-place. Called from `threat_report.py` after `enrich_ground_truth()`, wrapped in a try/except so failures never block report generation. Fully deterministic, no LLM.

`apt_evidence` structure: `{apt_groups: [{group_id, group_name, aliases, technique_overlap}], top_group, mitre_backed}`. Groups ranked by technique overlap count — groups that use more of the path's techniques score higher.

**Reasoning:**
Attack path rationales previously described topology only ("4 hops, criticality 0.95"). Adding MITRE-backed APT groups gives a report reader real-world attacker context: not "an external actor" but "Sandworm Team (ELECTRUM), known to use 6 of the 9 techniques on this path". This is the difference between a theoretical risk assessment and an evidence-backed one. 181 APT groups with 20,048 relationship objects were already in `enterprise-attack.json` and never queried.

**Alternatives rejected:**
- LLM-derived APT attribution: Non-deterministic, hallucination-prone. MITRE's own relationship objects are the authoritative source.
- Storing apt_evidence as a top-level AP field (not inside risk_scenario): `risk_scenario` is the right container — it holds the threat narrative, and APT is part of that narrative.
- Alias deduplication: `aliases[0]` was equal to `group_name` for several groups (e.g. "Sandworm Team / Sandworm Team"). Fixed by filtering aliases to exclude the canonical name before display.

---

### 2. CVE enrichment: two-gate quality filter (CTID KEV → CISA KEV)

**What was decided:**
CVE enrichment uses two independent data sources, not one:

**Gate 1 — CTID KEV→ATT&CK mapping** (`chatbot/data/kev/kev_ctid_by_technique.json`):
- Source: Center for Threat-Informed Defense Mappings Explorer (Apache 2.0)
- 155 ATT&CK techniques mapped to 1,177 CVE links via curated human-reviewed mapping
- Classification types: `primary_impact`, `secondary_impact`, `exploitation_technique`
- Fetch script auto-resolves the latest versioned file via GitHub Contents API (path: `mappings/kev/attack-{ver}/kev-{date}/enterprise/`)

**Gate 2 — CISA Known Exploited Vulnerabilities** (`chatbot/data/kev/kev_cisa_by_cve.json`):
- Source: CISA KEV catalog (public domain, daily updates)
- 1,619 CVEs confirmed actively exploited in the wild
- Fields: `vendor`, `product`, `date_added`, `ransomware` (bool), `cwes`, `required_action`

Combined flow in `threat_scene_deepener._collect_cves_with_kev()`:
1. CTID lookup: `technique_id` → list of CVEs (technique-precise)
2. Filter to `min_cve_year` (default 2018)
3. Cross-reference against CISA KEV for each CVE: `actively_exploited`, `ransomware`
4. Sort: ransomware-linked first, then by `date_added` newest-first
5. Output: `cve_ids` (all matches), `kev_hits` (CISA-confirmed subset), `ransomware_linked` (bool)

Fallback path: if KEV files are absent (`kev_helper.available = False`), falls back to the MITRE description regex. Deepener never blocks report generation.

`KevHelper` (`chatbot/modules/kev_helper.py`): singleton via `get_kev_helper()`, loads both JSON indexes on first call. `get_cves_for_technique()` returns CTID entries enriched with CISA metadata. Graceful noop (logs a warning, returns empty results) if data files not found — no error raised.

`scripts/data/fetch_kev.py`: downloads both sources, builds both index files + `kev_meta.json` (provenance). `.claude/skills/update-data/SKILL.md` Section 7 documents the update procedure. `update-kev.sh` script added alongside existing `update-mitre.sh` etc.

**Reasoning:**
The prior MITRE description regex approach found CVEs in only 6 techniques (CVEs mentioned in free-text technique descriptions — a sparse, unmaintained data source). CTID KEV is curated human-reviewed data specifically designed for ATT&CK integration. CISA KEV adds the critical signal that CTID lacks: active exploitation status and ransomware association. A CVE that passes both gates (technique-matched AND confirmed exploited) is vastly stronger signal than a regex match from a technique description.

The two-source design is intentional: CTID has ~550 CVEs with precise T-codes but no exploitation metadata; CISA has 1,619 exploitation-confirmed CVEs but no T-codes. Neither source alone provides what the combined approach does.

**Alternatives rejected:**
- MITRE-Cyber-Security-CVE-Database/mitre-cve-database GitHub repo: Assessed as unsuitable — early-stage aggregator, no actual data, no T-code mapping.
- threatsurfer/cve-attack-mapper: Live Flask API (6 req/min rate limit), no offline data, not suitable for bundling.
- Raw CISA KEV only (no CTID): No T-code link — would require keyword matching on node labels to connect CVEs to techniques, which is imprecise and architecture-dependent.
- NVD CWE→ATT&CK bridge: CWE→ATT&CK mappings are community-maintained and unreliable at the technique level. CTID's curated mapping is higher quality.
- Update cadence: CTID updates with ATT&CK releases (~quarterly); CISA updates daily. Skill documents running Section 7 monthly (sufficient for ransomware signal currency) or daily if tracking emerging exploits.

---

### 3. Dashboard: Threat Intelligence card in ThreatModel AP right pane

**What was decided:**
A "Threat Intelligence" card is rendered in the ThreatModel tab AP right pane, below the Impact row, only when `apt_evidence.top_group` or `cve_ids` is non-empty.

Card contents:
- **Header row**: "Threat Intelligence" label + `🔴 Ransomware` pill (shown only when `ransomware_linked=true`) + `⚠ N KEV` count badge (amber, shown when `kev_hits.length > 0`)
- **APT chips**: one per group in `apt_groups`, purple, hover tooltip shows group name + technique overlap count
- **CVE chips**: colour-coded by CISA KEV status — red = KEV confirmed + ransomware, amber = KEV confirmed, pale = not in CISA KEV; hover tooltip shows vendor/product/date_added; `⚠` suffix on KEV-confirmed chips
- Card border colour: red when `ransomware_linked`, purple otherwise

`09_threat_model.md` (report file) renders `**Known APT attribution:**` and `**Associated CVEs:**` lines in the per-AP section when present.

**Reasoning:**
The ThreatModel right pane already had Actor/Target/Exploited-via/Impact. APT attribution and CVE evidence are part of the same threat narrative — they belong in the same card group, not as a separate section. The ransomware border colour gives an immediate visual triage signal without requiring the reader to parse the chips first.

The Visualise tab node detail pane was intentionally not changed — it is a control-relevance pane, not a threat narrative pane. Adding APT/CVE there would be off-context.

**Alternatives rejected:**
- APT in ThreatModel AP list items (compact left list): Would clutter the list — the list is for scanning, the right pane is for detail.
- Separate "Intelligence" tab: Overkill for additive enrichment data; co-location with the risk scenario is more useful.
- Show CVEs in Overview tab: Overview is for expert consensus and confidence; per-path CVE evidence belongs in ThreatModel.

---

## 2026-06-07 — Expert Review UX: critic verdict field, collapsible findings, chain-prerequisite detection, SSP keyword precision

### 1. `reasoning` field added to all 5 critics — top-level CritiqueScore field, not buried in breakdown

**What was decided:**
Added `reasoning: str = ""` to `CritiqueScore` and `ValidationResult` dataclasses. Each critic's LLM output schema now includes a `reasoning` field (1-2 factual sentences, no evaluative adjectives). The field is forwarded through the SSE `critic_result` event and rendered as a "Critic verdict" block at the top of each panel body in Expert Review. The panel header always shows the critic's role description (what it looks out for), never the verdict — avoiding duplication.

Red-teamer was storing `reasoning` into `breakdown["reasoning"]` instead of the top-level field. Purple Team and Blackhat constructors were missing the argument entirely. All four non-architect critics now pass `reasoning=data.get("reasoning", "")` directly to `CritiqueScore`.

**Reasoning:**
Non-technical users need a plain-language "so what" before reading detailed findings. The header subtitle should orient the reader (what does this critic evaluate?), not restate the verdict already shown in the body.

**Alternatives rejected:**
- Show reasoning in header only: Hides it from users who open the panel expecting detail.
- Keep reasoning in breakdown dict: Not surfaced to the SSE layer or UI card.

---

### 2. Expert Review findings: collapsible per-category, Cross-Expert groups: collapsible per-priority

**What was decided:**
Individual critic findings are now grouped by `g.category` and rendered as collapsible rows (sorted by worst severity in each group, default expanded). Each category header shows name + finding count.

Cross-Expert Findings (Critical / High / For Review) each become independent collapsible groups with colour-matched headers — Critical = danger-color, High = warning-color, For Review = text-tertiary.

**Reasoning:**
Panels with 5+ findings are dense. Category grouping lets a reader scan "which area has the worst issues" without reading every item. The cross-expert groups were previously flat lists under plain-text headings with no visual weight hierarchy.

**Alternatives rejected:**
- Single collapse for the entire findings list: Loses the structure the categories provide.
- Always expanded, no collapse: Too much vertical space for architectures with many findings.

---

### 3. Chain-prerequisite detection in Tester post-validation (`_check_chain_prerequisite`)

**What was decided:**
Added `_check_chain_prerequisite()` to `TesterCritic._validate_gaps()`. After the existing MITRE direct-mapping check fails, the method checks whether the mitigation covers an upstream technique that appears earlier in the same attack path as the flagged technique. If so, the gap is reclassified as a valid indirect defence and suppressed rather than scored as a mapping error.

Example: M1032 (MFA) is not in MITRE's direct mitigation list for T1485 (Data Destruction). But M1032 mitigates T1078 (Valid Accounts), which often precedes T1485 in credential-abuse paths. Blocking the upstream technique breaks the chain before T1485 is reachable — a chain prerequisite, not a mapping error.

**Reasoning:**
The Tester evaluates direct logical prevention; the Exploit Analyst evaluates overall chain difficulty. Without this fix, the same MFA control produces an UNSURE contradiction between the two critics on every run containing credential-abuse → destruction paths — despite both critics being correct within their scopes.

**Alternatives rejected:**
- Add explicit M→T prerequisite exceptions to the Tester prompt: Brittle; can't enumerate all chain patterns.
- Accept as known contradiction: Produces noise in every Expert Review that includes this pattern.
- Mark as KNOWN contradiction rather than suppress: Still penalises the score incorrectly.

---

## 2026-06-13 — StoryCaster: user journey co-generation, critic enrichment, dashboard integration

### 1. Co-generation model: journey macro-stories share the exact BFS paths from expected_attack_paths

**What was decided:**
`story_caster.py` (`chatbot/modules/story_caster.py`) generates two story levels:
- **Edge micro-stories** — one per MMD edge, for critic context. Classify story type (`auth_flow`, `data_read`, `admin_access`, `external_ingress`, `external_egress`, `inter_service`), infer user role from node label keywords, map to MITRE tactics. Transparent infra-to-infra edges (DDoS→WAF) suppressed as `infra_only`.
- **Journey macro-stories** — one per ranked AP, co-generated on the same BFS path. `cast_journey_story()` called once per AP after path ranking. Produces corroboration signal: `no_user_story=False` (user follows this path) or `True` (post-compromise pivot only).

Structural guarantee: US == AP — journey story and attack path share identical `path` list. No separate cross-reference alignment needed.

`ground_truth["user_stories"] = {edges: [...], journeys: [...]}` — additive key, no existing fields modified. `ArtifactSet.user_stories` field added to `artifact_extractor.py`.

AP `rationale` field replaced with story-derived narrative: corroborated paths get flow description; attacker-only paths get "no legitimate user traversal — behavioural anomaly detection will not catch this."

**Reasoning:**
The "sweet spot" is structural: attacker hijacks the exact path a legitimate user takes. Making US == AP eliminates divergence at the architecture level — there is no reconciliation step. Generating them independently and aligning post-hoc loses the co-generation guarantee and adds complexity.

Attacker-only paths (no human actor on path) are a useful separate signal for the Red Team critic — "this path has no legitimate user baseline, so behavioural anomaly detection won't catch it." The flag is trivially computed from the actor-node keyword check.

**Alternatives rejected:**
- AP → US: Generate APs first, then derive stories aligned to them. Rejected — story would be hollow when no human legitimately traverses the AP (pure lateral movement).
- US → AP: BFS from actor nodes generates journeys first, AP scoring follows. Rejected — loses RAPIDS threat weighting.
- LLM story generation: Non-deterministic, slow, API cost. Deterministic template approach with contextual role inference produces good stories for well-labelled MMDs. LLM enrichment is available as `use_llm=True` opt-in.

---

### 2. Actor node classification: human group vs system/channel entry point

**What was decided:**
`_actor_is_human_group(label)` classifies whether a path's entry node label names a human group (use label as story subject) or a system/channel (use inferred role as subject, node as "via X").

Rules:
- Last token is a human stem (`user`, `customer`, `admin`, `operator`, `partner`, etc.) → human group, use label directly
- `Internet Users` → "Internet Users connect through..." (not "An end user from Internet Users...")
- `VPN Remote Access` → "A system administrator connects via VPN Remote Access..."
- System keywords (`console`, `portal`, `gateway`, `application`, `service`, `vpn`, `management`, etc.) in last-token position → system node
- `Internet` / `External` as standalone labels → system entry point, role refined from destination

**Reasoning:**
"An end user from Internet Users" is circular — the label already is the humans. Separating the two cases produces natural language without redundancy. The destination-context refinement (e.g. `Internet → Admin Console` → "system administrator") adds specificity where the source label alone is generic.

**Alternatives rejected:**
- Always use role prefix: Produces circular text for human group labels.
- Always use label as subject: "VPN Remote Access accesses the Database" is not human-readable.

---

### 3. Phase C: User journey signals injected into all five critics

**What was decided:**
Each critic receives a slice of story context relevant to its rubric:

| Critic | Context injected | Rubric effect |
|---|---|---|
| Architect | Flow type distribution + attacker-only AP list | Controls checked against dominant flow types; attacker-only APs get network segmentation recommendations |
| Tester | Corroboration status of each AP rationale | Validates story-derived rationales describe real user flows, not just topology |
| Red Team | Each AP labelled [corroborated] or [NO USER BASELINE] | Anomaly detection not credited as mitigation on corroborated paths; post-compromise scored on network controls only |
| Purple Team | Each AP annotated [CORROBORATED — role] or [POST-COMPROMISE] | Lens B (detection chain) assessed path-aware; corroborated paths need precise baselines, post-compromise paths need network-only detection |
| Blackhat | Corroborated paths elevate stealth at shared pivot nodes | Pivot chains through corroborated APs scored higher stealth_potential — attacker blends with real user traffic |

`_build_story_index()` added to `ArtifactExtractor`: builds `by_type`, `high_risk`, `attacker_only`, `corroborated`, `summary` from `user_stories`.

Purple Team bug fix: `ground_truth` was not in scope inside `_build_prompt` — fixed by extracting `user_stories` before the call and passing as `user_stories=` kwarg.

**Reasoning:**
Story signals improve input signal quality per critic, not the confidence score directly. Each critic has a specific lens; the story context is threaded in where it is relevant to that lens, not broadcast to all critics uniformly.

**Alternatives rejected:**
- Inject full story list into all critics: Wastes tokens; irrelevant context degrades focus. Each critic only needs the slice relevant to their rubric.
- Post-hoc story annotation of critic outputs: Loses the ability to change how critics reason during their analysis.

---

### 4. MoE synthesis: user journey intelligence block + tier sharpening rules

**What was decided:**
The synthesis prompt (`_llm_synthesize`) receives a USER JOURNEY INTELLIGENCE block (labelled deterministic, pre-LLM) listing each corroborated and post-compromise path with actor, resource, role, and tactics.

New RULES in the synthesis prompt for tier placement:
- Post-compromise paths → any preventive control covering them belongs in **Quick Win** (no detection fallback, prevention is the only lever)
- Corroborated paths → preventive controls (MFA, WAF, RBAC) in Quick Win; detection controls with precise baselines in Recommended (anomaly detection alone insufficient — attacker blends with user traffic)
- Each tier item must append `"— protects AP-X (role journey)"` or `"— covers post-compromise path AP-X"`
- Residual risk must reflect which detection strategy is appropriate per path type

Tier rationale templates updated to reference journey types explicitly.

**Reasoning:**
Without explicit journey context, the synthesis LLM places controls based on gap severity and cost alone. A post-compromise path with no detection fallback should always have its preventive control in Quick Win regardless of cost — not because the critic scored it HIGH, but because the structural situation demands it. This is a deterministic fact (like the validation report flags) that the LLM cannot derive from critic outputs alone.

**Alternatives rejected:**
- Derive tier placement from critic scores only: Critics' gap severity doesn't encode the post-compromise/corroborated distinction. A MEDIUM severity gap on a post-compromise path deserves Quick Win treatment; the same gap on a corroborated path with detection controls may be lower priority.
- Separate synthesis pass for journey-aware tier adjustment: Extra LLM call, extra cost, same result achievable in one pass.

---

### 5. Dashboard: User Journeys tab, per-report journey context, UJ explainer in Expert Review

**What was decided:**

**Dashboard:**
- New "🗺️ User Journeys" sub-tab in Overview alongside Expert Consensus and Architecture Diagram. Shows summary header (corroborated count, post-compromise count) + card grid — one card per journey with role, actor→resource, truncated story text, tactics, "View path details" link.
- AP list rows in ThreatModel and Threat Paths tabs: inline badge `✓ role` (green) or `⚠ post-compromise` (amber) per path.
- AP detail right pane (ThreatModel + Threat Paths): journey story card injected before Threat Intelligence block — story text, exploitation chain, detection strategy note.
- Highest Impact Controls (Overview): each top-3 control shows which user journey it protects inline.
- Expert Review: "🗺️ How User Journeys shaped this analysis" collapsible panel — one block per critic, dynamic text derived from actual run data (corroborated count, path IDs, flow types, roles). No static text.
- Contradiction detail pane: GENUINE_DISAGREEMENT cases now show "⚙ Deterministic engine signal" — cross-references contradiction topic against `validation_report.checks` failed checks; if no match, flags that the MMD needs more structural detail.

**Generated reports:**
- `01_executive_summary.md`: Journey coverage note + per-AP tag (corroborated / post-compromise) in attack paths list.
- `02_technical_report.md`: Per-AP story text, exploitation chain, detection strategy blockquote after MITRE techniques.
- `03_action_plan.md`: "Protects" column in each phase table — `end user workflow`, `system administrator workflow`, or `post-compromise pivot — network controls needed`.
- `09_threat_model.md`: Journey coverage summary at per-AP section header + per-AP story text + detection note.
- `10_adr_report.md`: "Who uses this path legitimately" section before each ADR threat scenario.

**Reasoning:**
User stories are only valuable if visible. The journey data is already in `ground_truth.json` — surfacing it in every view where a reader looks at an AP closes the loop between "what the system detected" and "what it means for a real user workflow." The "so what" — whether a finding is about a path a real person walks every day or a post-compromise pivot no one legitimately makes — is the most important contextual fact about any attack path's operational impact.

**Alternatives rejected:**
- Journey data only in ThreatModel tab: Other tabs (Threat Paths, Overview, Reports) are used by different personas who need the same signal.
- Show journeys as a separate top-level tab: Journey data is AP-contextual; it belongs alongside the AP it annotates, not as a standalone dataset.
- Static UJ explainer text in Expert Review: Text that doesn't reflect the actual architecture (which paths are corroborated, which are post-compromise, what the dominant flows are) is noise. Dynamic text derived from `story_index` makes the explainer architecture-specific.

---

### 4. SSP governance fallback: multi-word keywords only, specific control IDs

**What was decided:**
The SSP fallback callout (shown when a gap describes a process/people control with no MITRE runtime mitigation) now uses specific NIST 800-53 control IDs matched to the gap's content (e.g. AT-2/AT-3 for training gaps, CP-2/CP-9/CP-10 for BCP/DR, IR-4/IR-8 for incident response).

All trigger keywords are now multi-word governance-specific phrases. Bare words like `'process'`, `'policy'`, `'personnel'`, `'documentation'`, `'compliance'`, `'audit trail'` have been removed — they matched technical remediation text (e.g. "process monitoring", "EDR policy enforcement") and produced irrelevant SSP callouts on technical findings.

**Reasoning:**
The original keyword `'process'` was triggering on T1059 command-execution findings ("implement process monitoring"), mapping them to PS-6 (Access Agreements) and PM-2 (Senior Agency IS Official) — controls that have no relationship to behavioral detection gaps. SSP fallback must only fire on unambiguously governance-centric language.

**Alternatives rejected:**
- Regex word-boundary matching: Still ambiguous for short words like "policy".
- LLM classification of gap type: Adds latency; deterministic keyword matching is sufficient for this pattern.

---

## 2026-06-07 — MoE 5-critic pipeline, UNSURE engine, dashboard UX hardening, config consistency

### 1. Two new critics added: Purple Team (2D) and Blackhat (2E) — rationale, design, and harmonisation contract

#### Why two new critics were needed

The original three critics (Architect, Coverage Auditor, Exploit Analyst) all reason from an **attacker's perspective within a single attack path**. This leaves two systematic blind spots:

1. **No defender visibility lens.** None of the three critics ask: "if this attack succeeds, would defenders see it?" A path can have every hop mapped and every control placed and still be silently exploitable if no detection control exists. This is the classic red/blue split — the first three critics are all red.

2. **No cross-path reasoning.** Each critic analyses one AP at a time. A shared node (e.g. an API Gateway) that appears in AP-1 and AP-3 could serve as a pivot letting an attacker chain both paths into a composite exploit that per-path mitigations cannot block — because each mitigation only closes the gap on its own path.

These are not edge cases. They are structural gaps that arise on any architecture with shared infrastructure nodes and any architecture deployed in a monitored environment (which is every production system).

---

#### Purple Team Critic (Layer 2D) — `purple_teamer_critic.py` → `06b_purple_team_critique.json`

**Role:** Detection depth, coverage completeness, and TM/ADR operability. The defender's perspective on the same attack surface the first three critics assessed from the attacker side.

**Three validation lenses:**

| Lens | Focus | What it catches |
|---|---|---|
| A — Coverage (Red lens) | Every MITRE technique across all APs must have ≥1 control in `control_recommendations` | Techniques that are mapped but entirely undefended — not flagged at path level by Architect/Tester/Red Team |
| B — Assume Breach / Next Layer (Blue lens) | For each AP node, assumes attacker is already there; checks whether any detection control (SIEM, EDR, IDS, logging) exists on the onward path | Prevention-only downstream = silent breach; attacker dwell time unlimited |
| C — ThreatHunter / TM-ADR Operability (SOC lens) | For each CRITICAL/HIGH AP, every hop must have ≥1 detection control for IoA/IoC traceability; ADR control recommendations must not be hollow (technique still uncovered) | ADRs that recommend a control for a node but leave the node's techniques uncovered in `control_recommendations` |

**Scoring:** Forward scale 0–100 (higher = better coverage). Confidence adjustment: 0% to −4% depending on gap severity.

**Output fields:** `coverage_gaps`, `detection_blindspots`, `adr_coherence_failures`, `detection_focus` mode.

**Configuration:** `purple_team.enabled` (toggle), `purple_team.detection_focus` (balanced / detection / coverage / adr) — shifts lens weighting.

---

#### Blackhat Critic (Layer 2E) — `blackhat_critic.py` → `06c_blackhat_critique.json`

**Role:** Cross-path chain exploitation analysis. The "supreme critic" — runs last and sees all prior findings. Asks: can an attacker combine multiple APs via shared pivot nodes into a composite attack that per-path mitigations cannot stop?

**Four scoring dimensions:**

| Dimension | Weight | What it catches |
|---|---|---|
| Cross-Path Chain Feasibility | 30% | Whether a pivot-diverge chain from a shared node to multiple targets is technically executable |
| Least-Resistance Path | 25% | Which multi-hop chain requires the least privilege escalation or control bypass |
| Stealth Potential | 25% | Whether PT's detection blindspot data shows the pivot node is also invisible to defenders (double jeopardy) |
| Mitigation Chain Coverage | 20% | Whether any existing control closes the chain as a whole, vs only one leg of it |

**Scoring:** Inverted scale 0–100 (higher = easier to chain-exploit = weaker cross-path defence). Confidence adjustment: 0% to −8%.

**Output fields:** `chained_exploit_findings`, `shared_nodes`, `pivot_diverge_chains`, `stealth_score`, `least_resistance_paths`, `mitigation_gaps_for_chains`, `exploit_mitigation_roadmap`, `uniqueness_vs_critics`.

**Configuration:** `blackhat.enabled` (toggle), `blackhat.rubric_preset` (balanced / stealth_focused / chain_focused / mitigation_stress), `blackhat.stealth_techniques` (T-IDs used for stealth scoring).

**Short-circuit:** If fewer than 2 attack paths exist, returns PASS immediately with no LLM call — cross-path analysis is not applicable to single-path architectures.

---

#### Harmonisation contract between all five critics

The five critics are designed to be complementary, not overlapping. The following contracts are enforced in system prompts and code:

| Rule | Enforcement |
|---|---|
| Coverage Auditor (2B) does not re-assess structural design gaps | 2B system prompt: "validate technique mapping and control effectiveness — structural completeness is 2A's domain" |
| Exploit Analyst (2C) does not re-validate MITRE mappings | 2C receives 2B output and adjusts exploit scoring for known mapping errors, but does not re-map techniques |
| Purple Team (2D) does not re-raise exploit paths or structural gaps | 2D system prompt scopes it to detection depth and ADR operability only |
| Blackhat (2E) does not repeat any finding from 2A–2D | 2E system prompt: "Do NOT repeat findings already covered by Architect, Tester, Red Team, or Purple Team critics" |
| Blackhat uses PT's detection blindspot data as *input*, not output | 2E prompt: "use PT's detection blindspot data to identify pivot nodes where a cross-path chain would be invisible to defenders" — PT findings become BH's attack surface, not its conclusions |
| Sequential mode enforces the dependency chain | Each critic in sequential mode receives the prior critic's `CritiqueScore` as structured input — 2B sees 2A, 2C sees 2B, 2D sees 2A–2C, 2E sees 2A–2D |
| Parallel mode documents the tradeoff | Dashboard shows a "Parallel mode tradeoff" banner: critics ran blind, cross-referencing was not possible |

**Progressive information flow in sequential mode:**
```
2A Architect   → flags structural gaps, ADR completeness
      ↓ architect_critique
2B Coverage Auditor → validates MITRE mapping against 2A's roadmap
      ↓ tester_critique
2C Exploit Analyst  → adjusts exploit feasibility for 2B's mapping errors
      ↓ red_team_critique
2D Purple Team      → assesses detection depth across all 2A–2C findings; finds ADR hollow spots
      ↓ purple_team_critique (detection blindspots)
2E Blackhat         → uses 2D's blindspot nodes as stealth pivots; finds cross-path chains 2A–2D missed
      ↓ blackhat_critique (pivot_diverge_chains → BH-N APs in ThreatModel)
Layer 3 Orchestrator → synthesises all five; injects [DETERMINISTIC KNOWN] from completeness_validator
```

**Why this ordering is fixed and not configurable:**
Each later critic's reasoning quality depends on earlier outputs. Swapping 2D and 2E would mean BH cannot use PT's detection blindspot data. Swapping 2B and 2C would mean the Exploit Analyst penalises paths for MITRE mapping errors it has not yet seen. The order is a semantic dependency, not a convention.

**Files renamed to match pipeline order:**
- `06b_purple_team_critique.json` (was `06c`) — PT runs before BH
- `06c_blackhat_critique.json` (was `06b`) — BH runs after PT

**Alternatives rejected:**
- PT and BH as always-on: Adds ~50–100s to every run; optional toggle with "core three always run" guarantee prevents disabling from silently degrading the assessment.
- Merging PT and BH into one "advanced" critic: They use fundamentally different lenses (defender visibility vs cross-path chaining) and different scoring scales (forward vs inverted). A merged critic would produce a less interpretable score and harder-to-action findings.
- Running BH before PT: BH explicitly uses PT's detection blindspot data — this is a hard dependency.

---

### 2. BH-discovered attack paths appended to ThreatModel AP list

**What was decided:**
`pivot_diverge_chains` from the Blackhat breakdown are surfaced as synthetic `BH-N` entries in the ThreatModel AP list, annotated with a `⚔️ BH-Discovered` badge. Clicking opens a dedicated detail pane with an inline SVG pivot→targets diagram, "surfaced by BH expert" badge, feeding-AP links, techniques, mitigation gaps, and a "No ADR" notice.

**Reasoning:**
BH chains are cross-path risks that existing APs don't capture — hiding them in the BH critique JSON means they never get ADR treatment. Surfacing them as first-class APs in the ThreatModel tab gives them the same review workflow as regular paths.

**Alternatives rejected:**
- Show BH chains only in Expert Review tab: Users doing ThreatModel review would miss them entirely.
- Add BH chains as sub-items under existing APs: Cross-path chains don't belong to a single parent AP.

---

### 3. UNSURE / KNOWN classification engine improvements

**What was decided:**
- `_reflect_contradictions` now receives Purple Team and Blackhat results for cross-critic context, with a `pt_bh_corroboration` field in the response schema.
- Fallback KNOWN/UNSURE logic: PT findings with coverage/detection gaps → KNOWN; BH findings with pivot chains → KNOWN (deterministic escalation, no second critic needed).
- Deterministic Check 7 (behavioral analytics gaps, API Gateway placement) and Check 8 (supply chain vendor risk, BCP/DR gaps) added to `completeness_validator`; results injected as `[DETERMINISTIC KNOWN]` facts into synthesis prompt.
- "For Review" UNSURE cards now show a source-specific action hint per critic (Architect → accept/revisit; PT → add UEBA/DAM; BH → review pivot reachability; etc.).

**Reasoning:**
A finding raised by PT about a T1005/T1213 path with no behavioral analytics is structurally provable — it doesn't need a second LLM critic to be KNOWN. Same for BH pivot chains. Escalating these deterministically removes false UNSURE labels and surfaces them as confirmed gaps. Check 7/8 are structural checks that the orchestrator synthesis can now cite as ground truth rather than opinions.

**Alternatives rejected:**
- Require two critics for all KNOWN: Too strict — PT and BH findings are already deterministically validated before the LLM call.
- Show UNSURE without action guidance: Users couldn't tell whether to act or ignore; source-critic guidance makes it actionable.

---

### 4. Blindspot cards: note vs action classification

**What was decided:**
Each blindspot card is auto-classified by topic keyword match into `⚠ Act` (supply chain, BCP/DR, API Gateway placement) or `📋 Note` (other structural gaps). Act cards show a specific action (vendor assessment, RTO/RPO mapping, diagram review); Note cards say "document for awareness". Panel subtitle explains both pill types.

**Reasoning:**
Supply chain, BCP/DR, and API Gateway are structurally guaranteed misses for all security-focused critics — and all three have concrete remediation steps the user can take independently. Undifferentiated blindspot lists caused users to treat all entries as optional reading.

**Alternatives rejected:**
- LLM-assigned actionability: Non-deterministic; the three structural blindspot types are known in advance.
- No differentiation: Users treated all blindspots as awareness-only; actionable items were being skipped.

---

### 5. Expert Consensus expandable cards + Export Briefing API

**What was decided:**
- Expert Consensus cards: truncated at 120 chars with a `…more` inline toggle (no page jump); full text expands in-place.
- Export Briefing: `GET /api/v1/reports/{name}/briefing` returns a self-contained two-page Markdown covering architecture snapshot, top APs, expert consensus strip, KNOWN/UNSURE findings, improvement tiers, blindspots, and ADR action checklist. Intended for offline sharing with users who have no dashboard access.

**Reasoning:**
Long consensus descriptions were being cut mid-sentence with no way to read the full text. The `…more` toggle avoids opening a new pane for what is often just 2–3 extra sentences. The briefing endpoint fills a gap for regulated environments where the dashboard URL is not accessible to all stakeholders.

**Alternatives rejected:**
- Whole-card click to expand: Competed with the "Open full review" link and caused accidental navigation.
- PDF export: Requires a headless browser or third-party renderer; Markdown is universally renderable and can be printed.

---

### 6. Config tab: critic sensitivity presets replace raw threshold dropdowns

**What was decided:**
Architect, Coverage Auditor, and Exploit Analyst critics each expose a single `sensitivity` dropdown (`lenient` / `balanced` / `strict`) instead of three numeric threshold fields each. The backend `@model_validator` in `MoESettings` expands the chosen preset into the underlying pass/minor/major (or hard/medium/easy) threshold values at save time. The orchestrator code is untouched — it still reads the numeric thresholds.

**Reasoning:**
Nine numeric dropdowns (three per critic, three critics) were inconsistent with Purple Team's `detection_focus` and Blackhat's `rubric_preset` — both of which already used named presets. Users had no way to judge whether `architect_pass_threshold=85` vs `90` was meaningful without reading source code. Named presets communicate intent: `strict` = "flag more gaps for regulated environments"; `lenient` = "reduce noise for early-stage architectures".

**Alternatives rejected:**
- Keep raw thresholds and add a tooltip: Tooltips don't fix the inconsistency; users still had to reason about three interdependent numbers per critic.
- Single global "critic strictness" covering all five critics: Too coarse — Architect strictness (design quality bar) has different implications from Red Team strictness (exploit penalty threshold).

---

### 7. Config tab: all MoE critic sections visible under MoE filter; row layout fix

**What was decided:**
- `sectionCatMap` now maps all five MoE critic sections to `'moe'` so they appear when the MoE filter tab is active. Previously Architect/Tester/Red Team fell through to `'other'` and were hidden.
- All three config row templates (main sections, Quick Setup, Pattern sub-fields) switched from a rigid 3-column grid to a flex layout: label + input on the top row (wraps on narrow viewports), description below full-width. Select `max-width` capped at 520–560px to prevent long option labels from being clipped.

**Reasoning:**
The 3-column grid constrained dropdowns to 240–320px — long option labels (sensitivity presets, detection_focus) were truncated mid-sentence in the rendered select box. The flex layout gives dropdowns room to be readable while keeping the description always visible below.

**Alternatives rejected:**
- Wider fixed column: Would overflow on typical 1280px laptop screens when the config pane is not full-width.
- Tooltip for long option labels: Not discoverable; users would select options without reading the full label.

---

## 2026-06-01 — Visualise per-node control relevance, report enumeration, dropdown width

**What was decided:**

### 1. Per-node control relevance filtering in Visualise tab (`groupControlsByNode`)

Introduced `CONTROL_LAYER_RESTRICTIONS` — a table mapping control names to the node layer types they are technically applicable to. Controls absent from the table remain broadly applicable.

| Control | Applicable layers | Rationale |
|---|---|---|
| `edr`, `antivirus`, `device hardening` | device, application, identity, unknown | Requires a real OS/process; excluded from managed storage (data) and managed network appliances |
| `code signing` | application, device, identity, unknown | For deployable artifacts; excluded from data (storage buckets) and network (LBs/firewalls are not deployment targets) |
| `container scanning` | application, device, identity, network, unknown | Containers run everywhere software runs; excluded only from data layer |
| `patching`, `patch management` | device, application, identity, network, unknown | Any node running patchable software; excluded from data (cloud providers manage S3/RDS patching) |
| `waf` | network, application, identity, unknown | HTTP layer; excluded from data (no HTTP endpoint) and device (bare OS host layer) |
| `input validation` | application, identity, network, unknown | Application/API code defence; excluded from data and device (OS layer) |
| `database firewall`, `data masking`, `query monitoring` | data only | Data-layer-specific; meaningless outside storage/database nodes |

`unknown` is always permissive — unrecognised node types could be any kind of host.

Validated against all 12 saved report architectures (00_safeentry → 22_generic). All 112 remaining exclusions after the fix are true negatives.

**Reasoning:**
Before this fix, `groupControlsByNode` assigned every control to every hop's target in the path with no layer awareness. For AP-2 (CloudApp → S3), both nodes received identical 15-control lists including EDR and code signing on S3 — a managed object storage service with no host OS. The restriction table makes control assignment reflect infrastructure reality rather than mechanical hop enumeration.

**Alternatives rejected:**
- Restrict only data layer (original fix scope): Left identity/network nodes with false exclusions (e.g. auth servers need EDR and patching).
- LLM-driven per-node relevance judgement: Non-deterministic and adds latency; a static table is auditable and fast.
- Node-type detection via LLM labelling: Same objection; the layer categories from `categorize_hop_layer()` are already computed and stored in hop_analysis.

---

### 2. `groupControlsByNode` keyed by node ID, not label (fixes After-hardening diagram)

Changed the map key from `hop.target_label` (e.g. `"Legacy Application"`) to `hop.target_id` (e.g. `"OnPremApp"`), which matches `path.path` entries exactly. Added `_nodeLabelMap` as a side-channel (`nodeId → human label`) so the UI still shows readable names on hardened-node buttons and the detail pane. `findMatchingPathNode` updated to exact-match first, with fuzzy normalised fallback for any legacy data.

**Reasoning:**
The After-hardening diagram was rendering only the path nodes with no control overlays because `findMatchingPathNode` compared label keys (`"legacyapplication"`) against path node IDs (`"onpremapp"`) — no substring overlap, zero matches. Root cause: `hop_analysis` stores both `target_id` and `target_label`; the original code used `target_label` as the map key without realising `path.path` uses IDs.

**Alternatives rejected:**
- Build a label→id reverse map from the architecture nodes JSON: The architecture section in `ground_truth.json` stores the name as a string, not a node dict — no reliable reverse map available without re-parsing the `.mmd`.
- Normalise path.path IDs to labels before comparison: Would require the same reverse map and is more fragile than using the ID directly.

---

### 3. Report folder enumeration starts at `_1` (was `_2`)

`counter` initialised to `1` in `streaming.py`. Sequence is now `base → base_1 → base_2 → …`.

**Reasoning:** `_2` implied the first duplicate was the second attempt, but there is no `_1` — creating a gap that looks like a missing run. Starting at `_1` is consistent and unsurprising.

---

### 4. History dropdown width increased

Trigger button `max-width` `240 → 340px`; panel `min-width` `320 → 480px`, `max-width` `420 → 620px`. Added `min-width:0` to the name `<span>` in both the button label and each row item so flex truncation actually engages alongside the fixed-width siblings (timestamp, SSP pill, three icon buttons).

**Reasoning:** Long architecture names (e.g. `09_hybrid_cloud_2`) were ellipsised in the trigger button and obscured in the panel rows because the name flex child had no `min-width:0`, preventing the browser from shrinking it below its content width.

---

## 2026-06-01 — CloudPattern + CCM/SSP compliance layer + configurable pattern settings + UI

**What was decided:**

### 1. CloudPattern fully implemented (CAVEAT + CCM + SSP)

Three compliance layers stacked on the existing MITRE/RAPIDS baseline:
- **CAVEAT** (CSA, CC0-1.0): 63 cloud attack techniques, AWS/Azure/GCP-specific mitigations/detection → `caveat_helper.py`, `scripts/data/fetch_caveat.py`
- **CCM v4.1** (CTID, Apache 2.0): 57 controls, 213 T#### mappings, SSRM layer (shared/CSP/CSC), SG SSP prefix hints → `ccm_helper.py`, `scripts/data/fetch_ccm.py`
- **SG SSP**: cloud + AI control name mappings added to `control_name_mappings.json`; cloud SSP profile auto-selects (`low_risk_cloud` / `high_risk_cloud_cii` based on CII keywords); AI controls enriched with `generative_ai` profile (GA-1–GA-8)

**Pattern baseline architecture:**
```
Every architecture  →  MITRE ATT&CK + RAPIDS  (universal, always runs)
+ AI nodes detected →  ATLAS + ARC + GA SSP   (augments, additive)
+ Cloud nodes       →  CAVEAT + CCM + cloud SSP (augments, additive)
```
All layers are additive — cloud/AI patterns never replace RAPIDS, they enrich it with domain-specific techniques, compliance controls, and CSP-specific mitigations.

### 2. IAM abuse implicit on compute/API nodes

Cloud architectures rarely draw explicit IAM nodes but every Lambda/EC2/container has an attached execution role. Added `iam_abuse` to `compute` and `api` component categories so IAM threat and controls always surface for cloud workloads even when IAM isn't explicitly drawn in the diagram.

### 3. CloudPattern keyword detection covers camelCase node names

Mermaid parser concatenates label words (e.g. `Cloud Application` → `CloudApp`). Added camelCase/concatenated variants to keyword map. CDN providers (CloudFront, Cloudflare, Akamai, Fastly, Azure Front Door) mapped to `api` component type — SaaS delivery layer; treated as API/configuration surface not raw compute.

### 4. AIPatternSettings + CloudPatternSettings in settings.py

Both patterns now have a named settings section (`ai_pattern`, `cloud_pattern`) in `AppSettings`. Changing either via `PUT /api/v1/config` triggers `reset_pattern_registry()` so the new values take effect on the next analysis without a server restart. Fallback dataclasses (`_AIPatternDefaults`, `_CloudPatternDefaults`) ensure patterns work outside the full app stack (CLI, tests).

**Alternatives rejected:**
- Exposing per-component YAML risks from `risks.yaml` as settings: too granular (30+ values), requires ATLAS/ARC domain knowledge to tune safely. Only the `recommend_controls` thresholds are exposed — these are the values a security practitioner would actually want to tune.

### 5. Patterns panel redesigned — read-only status, inline config

Removed enable/disable toggles from the Patterns UI panel. Patterns activate automatically when the engine detects a matching architecture type — a user disabling cloud pattern on a cloud system would silently lose threat coverage with no warning. Status is now read-only (green dot = auto-detected, grey = coming soon). Each active pattern has a collapsible `⚙ Scoring Thresholds` sub-panel inline with its status row — all pattern config lives in one place.

---

## 2026-06-01 — CCM + SSP compliance layer on top of CloudPattern and AIPattern

**What was decided:**

### 1. CCM compliance enrichment is additive, not scoring

`CloudPattern.get_ccm_controls(threats)` returns CCM control IDs derived from the T#### IDs already in the threat assessment. It does not feed back into risk scoring — CCM is a compliance layer, not a threat detection layer. This keeps the two concerns separate: CAVEAT/MITRE = threat model, CCM/SSP = compliance posture.

**Reasoning:** CCM→ATT&CK mapping reliability varies by control — a broadly-mapped CCM control (IAM-16 covers 60+ techniques) is too coarse for risk weighting. Better to surface it informatively.

### 2. SSP profile auto-selection for cloud architectures

`_infer_cloud_ssp_profile()` in ThreatAnalyst defaults to `low_risk_cloud` but escalates to `high_risk_cloud_cii` when CII keywords (gov, finance, health, critical) appear in the description or architecture name. An explicit `ssp_profile` in request metadata always wins. This means the same architecture diagram can yield different compliance levels depending on deployment context — no code change needed.

### 3. GenAI SSP profile wired to AIPattern output

AI control recommendations are now enriched with `target_profile="generative_ai"` so GA-1–GA-8 (all L0 Cardinal for generative_ai profile) surface alongside ARC controls. This was the missing link — the SSP has a generative AI catalogue but it was never being used.

**Alternatives rejected:**
- Adding GA controls to `control_name_mappings.json` as name→ID: The GA controls are the profile itself — they don't map to control names in the deterministic engine; the profile affinity approach (pushing `ga` prefix to surface GA controls under AI threat categories) is cleaner.

### 4. CCM → SSP bridge is prefix-only (not specific control IDs)

`get_ssp_prefixes(ccm_id)` returns SSP category prefixes (e.g., `["ac"]` for IAM group) rather than specific control IDs. CCM and SG SSP don't share a 1:1 mapping — forcing one would be inaccurate. Prefix hints allow informational cross-reference without false precision.

---

## 2026-06-01 — CloudPattern implementation anchored to CSA CAVEAT framework

**What was decided:**

### 1. CloudPattern is now active, anchored to CSA CAVEAT

The prior deprioritisation (2026-05-31) was due to no distinct authoritative source. The CSA CAVEAT framework (CC0-1.0) resolves this: 63 cloud-specific attack techniques with per-CSP (AWS/Azure/GCP) mitigation steps and detection guidance that MITRE ATT&CK Enterprise does not provide at the service level. CloudPattern is now marked `status: "active"` in `patterns_catalog.py` (kept `default_enabled: False` until validated on more architectures).

**Reasoning:** MITRE covers *what* happens; CAVEAT covers *how* on each CSP. The IAM Abuse technique, for example, maps to different audit procedures on AWS vs Azure vs GCP — CAVEAT captures this exactly.

### 2. CAVEAT data is generated (git-ignored); MITRE mapping is committed

`chatbot/data/caveat/caveat_techniques.yaml` is generated by `scripts/data/fetch_caveat.py` (similar to `enterprise-attack.json` — not committed). `chatbot/data/caveat/caveat_mitre_mapping.yaml` is hand-authored and committed — it bridges CAVEAT titles to MITRE T#### cloud sub-technique IDs and is version-controlled like `arc/risks.yaml`.

**Alternatives rejected:**
- Committing the full CAVEAT YAML: At 414 KB it's manageable but creates the same maintenance burden as the ATT&CK JSON (stale copy, merge conflicts). Fetch script is cleaner.
- Using CSA CCM instead: CCM is a compliance control catalogue, not a threat technique database — wrong abstraction level for CloudPattern.

### 3. CSP auto-detection from node names

`ThreatAnalyst._detect_csp()` infers the dominant CSP (aws/azure/gcp) by counting keyword hits across node names and description. This means the same cloud architecture diagram gets AWS-specific or Azure-specific mitigation text automatically, without manual tagging.

### 4. No RAPIDS duplication — CloudPattern adds a layer, not new findings

RAPIDS already surfaces MITRE T#### from the Enterprise matrix. CloudPattern does not re-report those as new findings; it adds: (1) CSP-specific mitigation/detection text sourced from CAVEAT, (2) cloud service-level threat categories (iam_abuse, data_exposure, etc.) that RAPIDS does not model, (3) CAVEAT-native techniques (e.g. Abuse Queue Services) with no MITRE T#### equivalent.

---

## 2026-06-01 — Live config system, Configuration tab, pattern toggling + UX fixes

**What was decided:**

### 1. Centralised config package (`chatbot/config/`)

A new `chatbot/config/` package owns all tunable parameters. `settings.py` defines Pydantic v2 `AppSettings` composed of 8 section models: `AnalysisEngineSettings`, `ConfidenceSettings`, `CompletenessSettings`, `ResidualRiskSettings`, `MoESettings`, `LLMSettings`, `SystemSettings`, `PatternsSettings`. Defaults match all previously-hardcoded values so no behaviour changes when `user_config.json` is absent. A thread-safe singleton pattern (`_settings`, `_lock`) ensures a single in-memory object shared across all request threads. `save_settings()` persists only non-default diffs (sparse diff), so the file stays small and defaults always win for absent keys.

**Reasoning:** ~30 constants were scattered across 10 modules with no way to tune them without code edits. The config package centralises them, enables live updates, and provides validated bounds via Pydantic `Field(ge=..., le=...)`.

### 2. All settings are live in memory — no server restart needed

`get_settings()` is called at request time in every engine module (not cached on instances). `update_settings()` replaces the singleton atomically. The one stale-cache issue was `self.pattern_registry` on `ThreatAnalyst` instances — fixed by always calling `get_pattern_registry()` directly instead of caching on `self`.

**Reasoning:** If settings required a restart, the config tab would be useless for an ops workflow. Atomic singleton replacement is the simplest live-reload mechanism that works across all callsites without dependency injection.

**Alternatives rejected:**
- Per-module config caching: Would require explicit cache invalidation signals in each module.
- Restart-required config: Defeats the purpose of a UI config panel.

### 3. Three authenticated config API endpoints

`GET /api/v1/config`, `PUT /api/v1/config`, `POST /api/v1/config/reset` all require `TM-API-KEY`. GET was initially planned as public but moved to auth-required because config data (scoring thresholds, weight formulae) reveals internal engine logic that could assist reverse-engineering.

Response includes `_provider_chain` (not `_secrets`) — shows the full LLM chain as `openrouter → bedrock` with per-credential presence flags and a note explaining `AWS_BEDROCK_API_KEY` is the bearer token used whenever any step in the chain resolves to Bedrock (including when it is the fallback provider via `LLM_FALLBACK_PROVIDERS=bedrock`). Key values are never returned.

**Alternatives rejected:**
- Public GET: Exposes scoring logic with no benefit — dashboard always has the key stored.
- Show active model names: Model strings tied to credentials; exposing them creates misconfiguration risk.

### 4. Configuration tab as a full main-pane takeover

The config tab hides both `#upload-form-container` and `#tab-content` when active and shows `#config-pane-wrapper` with its own sticky header and scrollable body. `_syncConfigTabVisibility()` hides the nav tab until `tm_api_key` is present in localStorage; key clear hides the tab and redirects if it was active.

**Reasoning:** Rendering config "below" the overview pane would create scroll/layout conflicts. A full takeover gives config its own dedicated scroll context and prevents any cross-contamination with analysis result state.

**Alternatives rejected:**
- Config as a modal/drawer: Harder to scroll through 30 fields, no URL-addressability.
- Config inside `#tab-content` (disabled until analysis): Config must be accessible before any analysis runs.

### 5. Filter chips with Quick Setup as the default view

Eight filter chips sit above the config sections: Quick Setup (default on open), All Settings, Engine, Confidence & Risk, MoE / Experts, LLM & System, Patterns, Provider Chain. Quick Setup shows a single card with 5 high-impact settings (critic mode, max paths, top-N, report directory, pattern toggles) and hides all other section cards.

**Reasoning:** 30 fields are overwhelming on first use. Quick Setup surfaces the 5 settings that cover 80% of real tuning scenarios without exposing the sensitive threshold bands. Users who need deeper tuning choose All or a specific category chip. Filter state is preserved across re-renders.

**Alternatives rejected:**
- Always show all sections: Too much cognitive load; high-risk threshold fields visible to everyone.
- Separate "Advanced" page: Extra navigation step; chips accomplish the same with less friction.

### 6. All numeric fields converted to curated select dropdowns

Every tunable field is a `<select>` with 3–5 labelled options. Options matching the validated production default are labelled `(recommended)` in green. Practical upper bounds are enforced at the option level (e.g. `max_tokens_synthesis` tops at 6000, not 16000; `max_tokens` tops at 2000). No free numeric inputs remain in the UI.

**Reasoning:** Free numerics allow out-of-range values that pass Pydantic validation but produce nonsensical results (e.g. `max_paths=1` with `top_n=10`, or weight sum ≠ 1.0). Curated options constrain the space to tested values. The `(recommended)` label makes the default explicit without hiding other options.

**Alternatives rejected:**
- Free numerics with range hints: Still allows arbitrary bad values; users ignore hints.
- Sliders: Poor for precise values like `0.35` or `0.995`; accessibility issues.

### 7. Pattern configuration with live toggling

`PatternsSettings.enabled_patterns: List[str]` controls which patterns are registered at runtime. `AVAILABLE_PATTERNS` in `patterns_catalog.py` is the canonical registry with `status: active | planned`. `create_default_registry()` checks `get_settings().patterns.enabled_patterns` before registering. `update_settings()` calls `reset_pattern_registry()` when the patterns section changes, so the singleton is rebuilt on the next analysis. Pattern toggles auto-save immediately (no need to click Save Changes).

**Reasoning:** `AIPattern` was always registered regardless of architecture type or user preference. Config-driven registration allows future patterns (Cloud, ICS, Mobile) to be enabled per deployment without code changes. The auto-save behaviour is safe for patterns because enabling/disabling a pattern has no side-effects on existing reports.

**Alternatives rejected:**
- Env-var–based pattern enable/disable: Already have too many env vars; structured config is cleaner.
- Pattern registration at import time: Would require a module reload to change.

### 8. Dropdown readability fixes

Select inputs use `background:#1e293b; color:#e2e8f0; color-scheme:dark` so the browser renders the native option list with dark background and light text — visible in dark theme without custom CSS. Input column widened from `190px` fixed to `minmax(240px, 320px)` so selected values are not truncated.

### 9. History dropdown UX fixes (also in this session)

- **Delete report folder** — 🗑 button on each history item triggers `confirm()` then `DELETE /api/v1/reports/{name}`. New endpoint added to `reports.py` using `shutil.rmtree`, auth-required.
- **7-day Recent boundary** — Changed from "current calendar week (Mon 00:00)" to rolling 7 days from now. Avoids Monday resets where Sunday's analysis moves to "Past" at midnight.
- **"Past analyses" → "Past analysis"** — Corrected to singular (one collapsible group).
- **Default SSP profile → Low Risk — Cloud** — Changed `selected` in HTML and all three `'medium_risk_cloud'` fallback string literals in `dashboard.js`. Rationale: most users start with a low-risk cloud system; the previous default over-scoped control requirements for typical demos.

**Alternatives rejected:**
- Soft-delete (move to archive folder): Adds complexity for a rarely-needed recovery path; hard delete with confirm is sufficient.
- Keep calendar-week boundary: Inconsistent user experience when a session spans a Monday.

---

## 2026-05-31 — CloudPattern deprioritised; MCP server and AgentTools confirmed as next priorities

**What was decided:**
CloudPattern removed from near-term roadmap. MCP server and AgentTools for critics confirmed as the next two priorities.

**Reasoning:**
MITRE ATT&CK Enterprise already covers cloud techniques within its existing tactic/technique structure (Initial Access via cloud APIs, lateral movement across tenants, etc.). A CloudPattern would have no distinct authoritative source behind it — unlike AIPattern which is grounded in MITRE ATLAS + GovTech ARC Framework. The only candidates that would give a CloudPattern genuine authority are the CSA Cloud Controls Matrix (CCM) or OWASP Cloud-Native Application Security Top 10, but there is no concrete use case driving that work today.

AgentTools is higher priority because it directly improves the accuracy of the existing MoE critics (MITRE ID verification inside LLM calls, reducing hallucination on complex architectures). MCP server is higher priority because it extends the tool's reach into agent-to-agent workflows without requiring new threat domain knowledge.

**Alternatives rejected:**
- Proceed with CloudPattern using MITRE ATT&CK cloud techniques only: Would duplicate existing RAPIDS coverage without adding a new knowledge source — not a meaningful improvement.
- Anchor CloudPattern to CSA CCM now: No use case driving it; premature. Revisit if a concrete cloud-compliance gap emerges from real architecture reviews.

---

## 2026-05-31 — Report naming root cause fix, SSP Form binding, dashboard header + UX pass

**What was decided:**
Six related fixes and improvements in one session:

1. **Report folder naming — 4-layer chain fix** — The temp path was leaking through the entire stack. Root cause was `analyst_agent._extract_architecture_name()` preferring `architecture_path` stem over the `architecture_name` kwarg. Fixed by: (a) reversing priority in `analyst_agent.py`, (b) adding `architecture_name` param to `generate_ground_truth()` and storing it in `ground_truth["architecture"]`, (c) passing it through in `threat_analyst.execute()`, (d) deriving the report folder from `ground_truth["architecture"]` in `threat_report.generate_report_package()` rather than from `original_mmd_path` stem.

2. **SSP profile always defaulting to `low_risk_cloud`** — `ssp_profile`, `enable_ssp`, and `include_validation` were declared as plain `str`/`bool` params on `POST /analyze-stream`. FastAPI treats those as query parameters on a POST route, ignoring the multipart form body. Fixed by importing `Form` and declaring them as `Form(...)` fields.

3. **Dynamic analysis status bar in header** — Replaced the static "MITRE ATT&CK" pattern-badges pill and the buried SSP badge (hidden below the history dropdown) with a compact status bar in `header-right`. After analysis: shows arch name, SSP profile pill, foundation confidence pill, and a MoE pill (`🧠 MoE 70.3% · seq`) that appears once Expert Review completes. Populates on fresh analysis and history reload; resets on new analysis.

4. **History dropdown live refresh** — Dropdown now calls `_loadArchHistory()` on every open rather than relying on a cached list. Shows "No analyses yet" and hides the button when all reports have been deleted. Previously left stale "Refreshing…" text on empty state.

5. **Mitigations score card** — Score now displayed as `N / 100` with a 4px mini progress bar and a plain-English label (`high impact` ≥20, `medium impact` ≥10, `lower impact` <10). Previously showed a bare number with label "score" that was opaque to non-security users.

6. **Technique rows collapsed by default in control detail** — Each technique row in the control detail right-pane now defaults to collapsed. Click the header to expand the mitigations list. Chevron (`›`/`⌄`) and inline mitigation count give affordance. Prevents the pane from being overwhelmed when a control maps to many techniques with long mitigation lists.

7. **MoE re-run from completed results** — A re-run row (mode selector + `▶ Re-run MoE` button) is now rendered at the top of the completed Expert Review view. Calls `_rerunMoE(archName, mode)` which purges the existing critic files via the cancel endpoint then calls `runExpertReview()` with the selected mode. Previously the only way to re-run MoE with a different mode was to restart the full analysis.

**Reasoning:**
The naming bug meant every upload via the API created a `tmp*` folder regardless of the DECISIONS.md entry from 2026-05-30 which fixed it at the route level — the fix only reached `streaming.py` but not the service/analyst/generator/report chain. The SSP form bug meant compliance data was silently wrong in all prior runs. The header changes address consistent user feedback that the SSP selection was not visible after analysis and the MITRE pill was static noise. Collapse-by-default on techniques follows the principle that detail should be accessible but not overwhelming on first view.

**Alternatives rejected:**
- Timestamp-based unique IDs for report folders: Addressed in 2026-05-30 entry — unreadable in dropdown.
- Single confidence number without breakdown: The `confidence_breakdown` object already exists; surfacing it in the header gives users a quick signal without opening a tab.
- MoE re-run as a separate page/modal: Inline row in the results view is the minimal surface — same pattern as the history item re-run button.

---

## 2026-05-30 — Dashboard UX: meaningful filenames, duplicate dedup, history icons, action buttons

**What was decided:**
Four related dashboard improvements in one session:

1. **Meaningful report folder names + duplicate dedup** — `streaming.py` now derives the report folder name from the uploaded filename (strip `.mmd`, replace `.`/` ` with `_`) rather than using a generic name. If the folder already exists, it appends `_2`, `_3`, etc. to avoid clobbering prior results.

2. **History dropdown: 👁 reload and ▶ re-run icons** — Each entry in the architecture history dropdown now shows two icon buttons alongside the row. 👁 loads the previous analysis result from `ground_truth.json` (no re-analysis). ▶ fetches the saved `before.mmd`, pre-fills the SSP profile, and triggers a fresh analysis. New `_rerunArchAnalysis()` method handles the re-run flow.

3. **Upload form: Clear / Upload / Analyse button row** — The upload form now has three explicit action buttons: `✕ Clear` (resets file input and drop-zone label), `📂 Upload File` (opens file picker), `🔍 Analyse` (submits). Drop-zone label updates to show the selected filename once a file is chosen.

4. **`btn-secondary` CSS class** — Added outlined/ghost button style for use alongside `btn-primary`.

**Reasoning:**
Previously every upload used the same folder name if the same `.mmd` filename was re-used, silently overwriting prior reports. Explicit action buttons replace a single implicit "click drop-zone to pick + submit" gesture that was not obvious. The reload/re-run icons surface two previously hidden actions (history load vs fresh analysis) that users were unaware of.

**Alternatives rejected:**
- Timestamp suffix on all folder names: Makes history dropdown entries unreadable (names would include a timestamp always, not just on collision).
- Single "Re-analyse" icon replacing row click: Separating view (👁) from re-run (▶) avoids accidental expensive re-analysis when the user only wants to review.
- Modal for action buttons: Overkill for three simple actions; inline row is sufficient.

---

## 2026-05-30 — Skills overhaul: agentskills.io folder structure, 3 new skills, 3 retired

**What was decided:**
Converted all `.claude/skills/` from flat `.md` files to the agentskills.io spec (`skill-name/SKILL.md` + optional `scripts/` subfolder). Heavy bash extracted to `scripts/` files; `SKILL.md` bodies kept lean (<100 lines).

Three new skills:
- **`repo-organise`** — read-only audit of `/docs`, `/tests`, `/scripts`, `/report`; proposes moves/prunes for user approval, never auto-executes.
- **`update-data`** — quarterly refresh for MITRE ATT&CK, ATLAS YAML, SSP catalog (via existing scraper), and ARC risk register from GovTech GitHub (`govtech-responsibleai/agentic-risk-capability-framework`).
- **`docs-health`** — audits `CLAUDE.md`, `docs/DECISIONS.md`, and memory files; outputs ✅/⚠/❌ health table with proposed edits, no auto-writes.

Three converted (flat → folder): `build-embeddings-cache`, `check-deprecation` (module list expanded with `ssp_mapper`, `ai_pattern`, `streaming`), `quick-test` (MITRE count updated to ≥835).

Three retired: `housekeep-docs` (replaced by `repo-organise`; removed risky `sed -i` in-place writes), `update-mitre-data` (absorbed into `update-data`), `validate-integration` (references moved file).

**Reasoning:**
Flat `.md` files didn't follow the agentskills.io spec — no `name:` frontmatter, no folder structure, scripts embedded inline making bodies >600 lines. Separation into `SKILL.md` + `scripts/` keeps activation token cost low (<5000 tokens) while keeping scripts executable and testable independently. ARC data source confirmed as GovTech GitHub (5 YAML files: capabilities, components, controls, design, risks).

**Alternatives rejected:**
- Keep flat files with corrected frontmatter only: Doesn't resolve the token-bloat problem for large skills like `check-deprecation` (650 lines).
- Single combined `update-data` + `build-embeddings-cache`: Embeddings rebuild is optional (only needed after MITRE update) and takes 3 min — keeping it separate avoids blocking the other data updates.

---

## 2026-05-30 — SSP control enrichment: scraper fix, profile levels, dashboard UX

**What was decided:**
Four related decisions in one session:

1. **Scraper fix** — `_scrape_ssp_profiles()` rewrote from element-walk heuristics to h3-sibling traversal. Each control on the SSP site has `<h3>XX-N: Title</h3>` followed by `<p><b>Profile Level:</b>N</p>` in its siblings. The old code scanned `h2/h3/h4/tr/td/li` elements, missing the `<p>` tags entirely, causing every control to default to L1. Post-fix: 0 mismatches across all 8 profiles vs live site.

2. **SSP profile badge in header, not sidebar** — Sidebar real-estate is reserved for tab navigation and will be needed as the architecture list grows. A compact inline pill (`SSP · Low Risk — Cloud`) in the header-left is always visible and adds no column width.

3. **Architecture history dropdown in header** — `GET /api/v1/reports` now returns `analysed_at` (folder mtime as Unix timestamp) and `ssp_profile` (from `ground_truth.metadata.ssp_profile`). A `<select>` in the header lists all past analyses newest-first with date and profile. Selecting one loads `ground_truth.json` directly, bypassing re-analysis. Refreshes automatically after each new analysis completes.

4. **Coverage Audit PASS + findings** — When tester status is PASS but `gaps[]` is non-empty (LOW severity findings), the header now reads `PASS (N low findings)` so users aren't misled into thinking there is nothing to review.

**Reasoning:**
Sidebar SSP badge cluttered nav; header keeps it persistent and globally visible. History dropdown avoids re-running expensive LLM analysis to revisit a prior result. PASS-with-findings is a common tester outcome (score ≥ threshold but minor gaps exist) — suppressing the gap count in the header was misleading.

**Alternatives rejected:**
- Sidebar SSP badge: Takes space needed for future per-architecture nav items.
- Tab for history: Would need a full list-detail UI; a dropdown is sufficient for ~20 entries.
- Color-code PASS differently when gaps exist: More complex; appending count is clearer.

---

## 2026-05-27 — ATLAS/ARC technique & mitigation name lookups via AtlasHelper

**What was decided:**
`/api/v1/techniques`, `/api/v1/mitigations`, and `/api/v1/technique-mitigations` now route `AML.T*` and `AML.M*` IDs to `AtlasHelper` instead of `MitreHelper`. `MitreHelper` only indexes Enterprise ATT&CK; ATLAS IDs are a separate corpus.

**Reasoning:**
The dashboard right pane was rendering `· Unknown (AML.T0043)` because `MitreHelper.find_technique()` only queries `_technique_by_ext_id` which has no `AML.*` keys. `AtlasHelper.get_technique_name()` and `get_mitigation_by_id()` already load the ATLAS YAML corpus.

**Alternatives rejected:**
- Merge ATLAS into MitreHelper index: Would conflate two independent frameworks with different ID namespaces.

---

## 2026-05-27 — ARC category arc_id badges in Mitigations tab

**What was decided:**
ARC category names extracted from the rationale string (`AI/ML (ARC): Safety, Accountability`) are now displayed as `[SAF · Safety] [ACC · Accountability]` pill badges via a client-side `_formatArcCats()` helper with a static name→arc_id lookup (9 categories).

**Reasoning:**
The `arc_id` short codes (INT, SAF, SEC, PRIV, TRANS, ACC, FAIR, RES, SOC) are not stored in ground truth `control_recommendations` — only the full category names appear in the rationale string. The mapping is static and stable (defined in `risks.yaml`), so a client-side lookup avoids a new API call.

**Alternatives rejected:**
- Store arc_id in ground truth at generation time: Requires a generator change and re-run of all existing reports.

---

## 2026-05-27 — Parallel Expert Review: per-critic progress bars + elapsed timer

**What was decided:**
When `critic_mode` is `parallel` or `auto`, the Expert Review progress box renders three individual bars (Architect, Tester, Red Team) instead of a single sequential bar. A per-second interval ticks elapsed time on each still-running card (`⟳ Running… 12s`). Each bar turns its critic's status colour and shows `✓` when that critic's `critic_result` SSE event arrives.

**Reasoning:**
With concurrent execution a single bar with sequential stage labels is meaningless — the bar would jump from "Architect" to "done" with no intermediate stages for Tester/Red Team. Per-critic bars give the user accurate per-agent feedback and make clear which critics are still outstanding.

**Alternatives rejected:**
- Keep single bar, just update label to "Running in parallel": Hides which critics are done vs still running.

---

## 2026-05-27 — Upload progress bar: animated tick updates message % and ETA

**What was decided:**
The animated tick interval (which inches the bar forward between SSE events) now also updates the status message by replacing the inline `[STAGE] N%` percentage with the current animated value and decrementing the ETA counter at 0.6s/tick.

**Reasoning:**
Previously the tick updated `progress-fill` width and `progress-text` percentage only. The status message (`[PARSING] 5% - arch.mmd - ...`) stayed frozen at the last SSE value while the bar visibly advanced, creating a confusing discrepancy.

**Alternatives rejected:**
- Remove the inline % from SSE messages: Would require changing the backend message format and lose the stage label context.

---

## 2026-05-27 — Mitigations tab sort order: _impact formula matching Overview

**What was decided:**
`loadControlsTab()` is now `async` and fetches MoE + Red Team endorsement data to compute the same `_impact = paths × riskScore × expertBoost` formula used by Overview's top controls. Controls are sorted by priority tier first (critical > high > medium), then by `_impact` within each tier.

**Reasoning:**
Ground truth order is arbitrary (generation order). Users expect the Mitigations list to be consistent with the "Highest Impact Controls" ranking on the Overview dashboard.

**Alternatives rejected:**
- Sort by `score` field only: Ignores expert validation signals and attack path coverage.

---

## 2026-05-27 — Synthesis/reflection: MITRE technique grounding to prevent false contradictions

**What was decided:**
Before calling the synthesis LLM and the `_reflect_contradictions` LLM, all `T####[.###]` IDs mentioned in critic outputs are resolved against the MITRE ATT&CK database and injected as a verified name block. A new `CRITIC_HALLUCINATION` root cause category is added to the reflection prompt for cases where a critic incorrectly claimed an ID doesn't exist.

**Reasoning:**
The Architect LLM hallucinated wrong labels for `T1590.005` ("model extraction") and `T1565.001` ("data poisoning") — their real names are "IP Addresses" and "Stored Data Manipulation". The Tester saw the wrong labels and flagged the IDs as non-existent, generating a false `DATA_REFERENCE_ERROR` contradiction. Grounding both LLM calls with authoritative names prevents this category of error.

**Alternatives rejected:**
- Post-process contradictions to filter known-valid IDs: Would require running MITRE lookups after the LLM call anyway; better to prevent the false contradiction from being generated.
- Constrain critic prompts to never mention technique IDs: Too restrictive — technique IDs are legitimate evidence citations.

---

## 2026-05-27 — Parallel critics + dynamic confidence scoring

**What was decided:**

**Dynamic confidence:** Replaced `base_confidence = 0.995` constant in `threat_analyst.py` with `_compute_base_confidence(ground_truth)`. The formula applies a complexity penalty (up to -25%, saturating at 20 nodes / 40 edges) and recovers it via a coverage score (control coverage 40%, validation pass rate 30%, path coverage 20%, technique depth 10%). Range: 0.72–0.995. A `confidence_breakdown` dict (`base`, `complexity_penalty`, `coverage_recovery`, `validation_adjustment`, `final`, `signals`) is now written to `result.data["confidence_breakdown"]` and surfaced in the API response via `ServiceResult.data["confidence_breakdown"]`.

**Parallel critics:** `MoEOrchestrator.run_pipeline()` gained a `critic_mode` param (`"sequential"` | `"parallel"` | `"auto"`). Three private execution methods:
- `_run_sequential()` — unchanged Architect→Tester(arch)→RedTeam(tester) chain
- `_run_partial_parallel()` — Architect ∥ Red Team blind first-pass concurrently, then Tester uses Architect output, then Red Team score adjusted post-hoc via `_adjust_for_tester_gaps()`
- `_run_full_parallel()` — all three critics via `ThreadPoolExecutor(max_workers=3)`, no cross-referencing

**Auto mode threshold:** `complexity_score = node_count*2 + edge_count + path_count*3 + tech_count`. Score ≥ 60 → sequential; < 60 → partial parallel.

**SSE endpoint** (`streaming.py`): Added `?critic_mode=` query param. Reads `confidence_breakdown.final` from `ground_truth.json` to chain the deterministic base into the MoE confidence pipeline (instead of always using 99.5%).

**Dashboard** (`dashboard.js`): Added mode selector (Auto/Sequential/Parallel) above the Run Expert Review button. Selected mode stored in `_erpState.criticMode` and appended to the fetch URL.

**Alternatives rejected:**
- *Compare mode (sequential + parallel side-by-side):* Requires two full LLM pipeline runs (~180s). Excluded to avoid API quota exhaustion on a single button press; can be added later as a CLI/batch comparison tool.
- *Parallel critics without auto threshold:* Without complexity-aware dispatch, parallel mode would run on complex architectures where cross-critic reasoning is most needed.
- *Fixed thread pool size > 3:* The pipeline only has 3 critics; more threads would be idle.

---

## 2026-05-27 — MITRE load latency: background warmup + signed pickle cache

**What was decided:**
Three-layer approach to eliminate the perceived load delay when uploading an architecture:

1. **Removed fake MITRE progress stage** (`streaming.py` routes) — the 5 SSE messages with `asyncio.sleep()` that pretended to load data already in memory were deleted. Progress stages compressed from `parsing(0-10%), mitre(10-20%), rapids(20-60%)` to `parsing(0-5%), rapids(5-55%)`.

2. **Background thread warmup** (`app.py`) — replaced synchronous `create_app()` preload with a daemon thread. Server is reachable immediately; `/health` returns `mitre_cache: loading` until the thread sets `_warmup_done` (typically <0.4s on pickle-warm boot). Dashboard polls `/health` on load and disables the upload button during the warmup window.

3. **Signed pickle cache** (`pickle_cache.py`, used by `mitre.py` and `atlas_helper.py`) — MITRE JSON parses once, then the result is stored as HMAC-SHA256–signed pickle. Subsequent boots load from pickle (~0.4s vs ~1.0s). ATLAS YAML load drops from ~0.35s to ~0.02s.

**Security: HMAC-SHA256 signing** — `chatbot/modules/pickle_cache.py` prepends `magic(8) + hmac_digest(32)` before the pickle bytes. `hmac.compare_digest()` is checked before `pickle.loads()` is ever called. A tampered file raises `ValueError` and both loaders fall back to JSON/YAML. Signing key prefers `TM_PICKLE_KEY` env var; falls back to a stable app-specific constant if absent.

**Alternatives rejected:**
- *No signing (raw pickle):* Attacker with write access to `chatbot/data/` could drop a crafted `.pkl` for RCE.
- *Hash-only (SHA-256 without secret):* An attacker can recompute the hash of their malicious payload — provides no integrity guarantee.
- *Store pickle outside data dir:* Complicates deployment; the signing approach lets the file stay alongside the source data.
- *orjson/ujson for faster JSON:* Not installed in environment; pickle is already 2-3× faster and is the right tool for caching parsed Python objects.

---

## 2026-05-27 — AIPattern YAML extraction complete (v1.1 → v1.2)

**What was decided:**
Extracted all hardcoded risk-scoring logic and control benchmark data from `ai_pattern.py` into two YAML files:
- `chatbot/data/arc/risks.yaml` — 9 ARC categories with per-component scoring rules (default_risk, missing_controls floors, present_controls reductions, static rationale)
- `chatbot/data/arc/controls.yaml` — 88-control benchmark grouped by category

`AIPattern` (v1.2) loads these at `__init__` and a single generic `_score_category()` dispatcher handles all three rule patterns (per-component, simple_rule, static). Public API is identical to v1.1.

**Evaluation order in `_score_category`:** present_controls reductions run first, then missing_controls `raise_to` floors. This ensures a critical missing control establishes a minimum floor even when other controls are present (mirrors v1.1 explicit if-chain behaviour).

**Alternatives rejected:**
- *JSON instead of YAML:* YAML is more readable for multi-line rationale strings and list values without quoting. PyYAML is already in the environment.
- *Single flat file:* Separating risks from controls keeps each file focused on one concern and makes it easy to edit controls without touching the scoring logic.
- *Jinja/formula expressions in YAML:* Overkill; the three rule patterns cover all current scoring logic without a mini-language.

---

## 2026-05-26 — Strategic Roadmap Priority: AIPattern YAML extraction first

**What was decided:**
Extract the hardcoded threat risk and control data from `chatbot/modules/patterns/ai_pattern.py` into YAML files (`chatbot/data/arc/risks.yaml`, `chatbot/data/arc/controls.yaml`) as the top roadmap priority.

**Reasoning:**
AIPattern embeds ~1,100 lines of Python dicts for ARC Framework risks (46 risks, 9 categories) and controls (88 controls). Updating a threat description, adding a new risk, or adjusting a control currently requires a Python edit and server restart. YAML extraction makes maintenance low-friction and sets the data-driven pattern that CloudPattern and ICSPattern should follow.

**Alternatives rejected:**
- *Implement CloudPattern first:* More user-visible but AIPattern is already in production and accumulating staleness debt.
- *MCP server first:* Higher external value but depends on a stable internal architecture; better to solidify the pattern layer first.
- *No change:* Acceptable short-term, but every new threat domain adds 1,000+ lines of hardcoded Python.

---

## 2026-05-26 — Roadmap: full priority order agreed

**What was decided:**
1. AIPattern → YAML data extraction
2. `scripts/backtest_all_architectures.py` — create missing script
3. CloudPattern implementation (ThreatPattern ABC already exists)
4. Enable AgentTool stubs in Architect + Tester critics (currently MVP1-disabled)
5. MCP server (5 tools wrapping REST API)
6. Parallel critic execution (optional — cuts ~40s from Expert Review)

**Reasoning:**
Items 1–2 are maintenance/correctness fixes. Items 3–4 deepen coverage and accuracy. Item 5 opens agent-to-agent integration. Item 6 is a performance optimisation with architectural trade-offs (loses fail-fast semantics).

**Alternatives rejected:**
- Parallel critics before agent tools: Performance gain is secondary to accuracy improvement.
- MCP before CloudPattern: MCP makes more sense once the pattern layer is richer.

---

## 2026-05-25 — Expert Review: Synthesis sub-step progress callbacks

**What was decided:**
Added 5 `progress_callback` signals inside Layer 3 of `MoEOrchestrator.run_pipeline()` using a `"synthesis:*"` stage prefix: `synthesis:confidence`, `synthesis:llm`, `synthesis:build`, `synthesis:save`, `synthesis:artifacts`.

**Reasoning:**
Layer 3 was a ~20s silent block. The SSE loop only had a generic ticker. Users saw "Running…" with no indication of which sub-step was executing. The `progress_callback` pattern was already established for critics (stages: `architect`, `tester`, `red_team`); extending it to synthesis sub-steps required only 5 `put_nowait()` calls and a branch in the SSE drain loop.

**Alternatives rejected:**
- Polling a status file: More complex, requires disk writes per sub-step.
- Single "synthesis started" callback: Doesn't convey the LLM wait (~20s) vs. fast steps.

---

## 2026-05-25 — Reports tab: JSON removed, moved to Raw Data tab

**What was decided:**
Reports tab shows only `.md` and `.mmd` files. All JSON (including Expert Review critique files) moved to Raw Data tab, which fetches the report directory async and organises JSON into Foundation / Expert Review / Live Session sections.

**Reasoning:**
Reports tab was mixing narrative documents (executive summary, action plan) with raw JSON data (critique files, ground truth). Analysts reading reports don't need raw JSON; developers debugging need JSON separately. The split makes each tab's purpose clear.

**Alternatives rejected:**
- Keep JSON in Reports under a collapsible section: Still mixes audiences.
- Remove JSON from UI entirely: Useful for debugging and download; should be accessible.

---

## 2026-05-24 — Tester false-positive detection: MITRE ground truth first

**What was decided:**
Rewrote `_check_if_false_positive()` in `tester_critic.py` to query `mitre.get_technique_mitigations(technique_id)` first. If the M-code is in the official MITRE list → definitively not a false positive, regardless of LLM phrasing.

**Reasoning:**
The Tester LLM was claiming M1032 is not a valid mitigation for T1485, which is factually wrong (MITRE lists M1032, M1053, M1018 for T1485). The previous heuristic relied on regex extraction from the LLM's own description, making it vulnerable to phrasing variations. Authoritative data should always override LLM output for factual assertions.

**Alternatives rejected:**
- Add explicit ground-truth assertions to the Tester system prompt: Prompt engineering is brittle; the LLM can still contradict it.
- Accept as known LLM limitation: Produces false findings in every Expert Review run — not acceptable.

---

## 2026-05-23 — Expert Review: Pause/Resume via SSE abort + checkpoint loading

**What was decided:**
Pause aborts the client-side `AbortController` (stops SSE). Resume creates a new `AbortController` and reconnects. The orchestrator skips already-completed critics by calling `_load_saved_critique(path)` — each critic saves its JSON immediately on completion, which serves as a natural checkpoint.

**Reasoning:**
Re-running completed critics on resume would waste ~60s of LLM calls and API quota. The orchestrator already saves critic JSON files immediately (`04_architect_critique.json` etc.), making checkpoint-based resume trivial — load the file, fire the `progress_callback` with the loaded result so the SSE frontend replays the live card.

**Alternatives rejected:**
- Server-side pause (pause the asyncio task): Complex and fragile across SSE reconnects.
- Re-run entire pipeline on resume: Wastes LLM API calls, adds ~90s latency.

---

## 2026-05-22 — MoE architecture: sequential fail-fast, not parallel

**What was decided:**
Critics run sequentially: Architect → Tester → Red Team. Each receives the previous critic's output. Pipeline aborts if a prerequisite is missing.

**Reasoning:**
Tester receives `architect_critique` to validate roadmap alignment. Red Team receives `tester_critique` to adjust exploit difficulty for known mapping errors. This chain enables cross-critic reasoning. Parallelism would break this dependency and reduce synthesis quality.

**Alternatives rejected:**
- Parallel execution: Faster (~40s saved) but critics would lose cross-referencing ability.
- Single monolithic LLM prompt: No independent validation; single point of hallucination.

---

## 2026-06-07 — Visualise tab: D3 topological layout, BH narrative, arch-diagram reload, ER UX hardening

### 1. Arch-diagram subtab works on history reload (no `uploadedFile`)

**What was decided:**
`renderArchitectureDiagram` previously returned early if `this.uploadedFile` was null. On history reload via the dropdown, no file is uploaded — `before.mmd` is fetched into `this.originalMmdContent` during `_loadArchFromReports`. Added a fast-path: if `!uploadedFile && originalMmdContent`, render directly from `originalMmdContent` without a FileReader. The subtab click guard updated to `(uploadedFile || originalMmdContent) && !diagramRendered`. Mermaid render + toolbar + zoom/orient/fit extracted to `_renderMmdContent(mmdContent)`, shared by both paths.

**Reasoning:**
Users who reload a previous analysis via the history dropdown couldn't see the architecture diagram. Fetching `before.mmd` once during `_loadArchFromReports` avoids re-fetching on every subtab click and mirrors how the rest of the report data is loaded.

**Alternatives rejected:**
- Force a file re-upload on reload: Breaks the "review without re-running" use case.
- Re-fetch `before.mmd` on subtab click: Adds a network roundtrip on every click; one-time fetch on load is sufficient.

---

### 2. D3 Visualise tab: force simulation replaced with topological BFS column layout

**What was decided:**
Replaced the D3 force simulation with a deterministic left-to-right BFS column layout. Each node is assigned a column depth via BFS from zero-in-degree nodes; rows within a column are centred. Fixed parameters: `NODE_R=18`, `COL_W=190`, `ROW_H=85`. All nodes rendered as circles (no diamond body shape). Ring colour encodes role: entry=red, target=orange, pivot=amber, other=regular. `d3.drag()` added so users can reposition nodes freely. `requestAnimationFrame(() => applyFit())` defers SVG sizing until after tab layout pass.

**Reasoning:**
The force simulation produced unreadable clusters — variable radius `16*sqrt(n)` plus force repulsion had no stable layout for DAG-shaped architectures. A topological BFS layout is deterministic and reads naturally as an attack flow (left=entry, right=target) for architectures like DMZ.

**Alternatives rejected:**
- Force simulation with stronger repulsion: Still non-deterministic; degrades on high-connectivity graphs.
- Manual fixed positions per architecture: Not scalable.

---

### 3. BH edges sourced from `pivot_diverge_chains`, not `least_resistance_paths`

**What was decided:**
The D3 edge builder was using `least_resistance_paths[].chain` which holds AP IDs (`AP-1`, `AP-3`), not node names. These were passed to `nodeMap.get()` which returned undefined → NaN positions → blank SVG render. Switched to `pivot_diverge_chains[].pivot` + `.targets` which hold actual node names. Added an `edgeSetBh` dedup guard and fallback to insert missing nodes if any pivot/target is absent from `nodeMap`.

**Reasoning:**
`pivot_diverge_chains` is the correct source for pivot-to-target edges — it was designed for this purpose. `least_resistance_paths` stores a different shape (AP sequences, not node pairs).

**Alternatives rejected:**
- Build AP-ID → entry node lookup from attack paths: More complex; the pivot-diverge structure already has the right names.

---

### 4. `shared_nodes` is a dict, not an array — `.forEach()` TypeError

**What was decided:**
`shared_nodes` in `blackhat_critique` JSON is `{NodeName: [AP-IDs]}`, not an array. The D3 loader called `(blackhat.shared_nodes || []).forEach(n => sharedPivotSet.add(n))`, which threw a TypeError on a plain object, crashing before `listContainer.innerHTML` was ever replaced — leaving the static placeholder permanently visible. Fixed: `const sn = blackhat.shared_nodes || {}; (Array.isArray(sn) ? sn : Object.keys(sn)).forEach(n => sharedPivotSet.add(n))`. `loadHardeningTab` wrapped in try/catch delegating to `_loadHardeningTabInternal` to surface future crashes.

**Reasoning:**
The crash was silent — no user-visible error, just a perpetually blank Visualise tab. The try/catch wrapper ensures any future throw surfaces as a visible error message rather than leaving static placeholder text.

**Alternatives rejected:**
- Convert `shared_nodes` to an array in the backend: Would break existing reports already on disk.

---

### 5. Pivot badge repositioned to top-right (adjacent to AP-count badge)

**What was decided:**
The diamond pivot badge was rendered at top-left `(-(NODE_R+2), -(NODE_R+2))`. Moved to top-right: `badgeX = NODE_R+2` (AP-count), `pivotX = hasBadge ? NODE_R+20 : NODE_R+2` (pivot diamond). Both badges cluster at top-right so they read as a pair.

**Reasoning:**
Top-left badge competed visually with the node label. Grouping both badges top-right matches the reading pattern of the node (label below, metadata top-right).

---

### 6. BH narrative block below the D3 graph

**What was decided:**
Added a `#vg-bh-narrative` div injected below the SVG when BH data is present. Renders: a header strip with chain rating and stealth score; a dashed-edge explanation (inline SVG dashed-line icon + text "dashed edges = Blackhat-identified pivot routes"); a collapsible "Why per-path controls don't stop pivots" note; per-chain cards from `pivot_diverge_chains` listing pivot node, targets, and contributing APs. Help text updated to mention drag support.

**Reasoning:**
Dashed edges in the D3 graph are not self-explanatory. Users asked why nodes could pivot despite existing controls. The narrative block provides the attacker-mindset explanation (shared node ownership transcends per-path mitigations) and per-chain specifics so users can act on findings without opening a separate tab.

**Alternatives rejected:**
- Tooltip on dashed edges: Not discoverable on mobile; doesn't convey the "why" at the structural level.
- Move explanation to Expert Review only: Visualise tab is where users see the graph; explanation should be co-located.

---

### 7. Expert Review: tester `reasoning` synthesised when blank

**What was decided:**
When `tester_critique.reasoning` is `""`, the Critic verdict block was rendering empty. Synthesised fallback: `strengths[0]` (what the controls do right) + first sentence of the worst `breakdown[x].reasoning` (what the gap is). Same synthesis applied in both the ER panel body and the Expert Consensus strip (which was still showing the old generic one-liner).

**Reasoning:**
The Tester LLM returns an empty `reasoning` field when its score is a PASS with only minor gaps — it puts the detail in `breakdown[].reasoning` instead. The synthesised verdict surfaces the signal without requiring a backend schema change.

**Alternatives rejected:**
- Require non-empty `reasoning` from Tester LLM: Prompt change needed; existing reports on disk would still be blank.
- Show generic fallback text: "No verdict provided" is less useful than the actual finding.

---

### 8. T-code inline legend replaces tooltip approach in Expert Review

**What was decided:**
Replaced `title` attribute tooltips on `<code>TID</code>` spans with a `_techLegendHtml(...texts)` inline block rendered directly in the panel body between the verdict and the breakdown bars. Collects all T-codes from the passed text(s), filters to cache hits, renders `<code>TID</code> Name` rows. Pre-fetch scan extended to cover `breakdown[*].reasoning` and `strengths[]` so tester synthesised verdict T-codes are in cache when the panel opens.

**Reasoning:**
Browser `title` tooltips are unreliable: hover delay (1s+), no mobile support, clipped in iframe contexts. An inline legend is always visible and does not require interaction.

**Alternatives rejected:**
- Custom JS tooltip on mouseover: More code, still not mobile-friendly.
- Link T-codes to MITRE ATT&CK URLs: Opens an external tab; breaks focus; not always allowed in enterprise environments.

---

## 2026-06-07 — Blackhat KeyError 'chain' and bh_diagram_generator pivot-edge fix

### 1. `_find_control_gaps_for_chains` crashed on pivot-diverge chains

**What was decided:**
Fixed `chain["chain"]` → `chain.get("chain") or chain.get("ap_ids", [])` in `_find_control_gaps_for_chains`. `all_chains` is the merged list of sequential chains (have `"chain"` key) and pivot-diverge chains (have `"ap_ids"` key). The function always read `chain["chain"]`, crashing with `KeyError` on any pivot-diverge entry. Since the DMZ has 4 pivot-diverge nodes found, BH crashed immediately and the error was silently swallowed — appearing as if BH simply didn't run. Also normalized `least_resistance_paths` breakdown to a consistent `{chain, pivot, chain_type, chain_criticality}` shape to prevent downstream serialization mismatch.

**Reasoning:**
Silent exception in `try/except Exception` block. Debug-level traceback logging added to surface future failures. The structural bug was in place since the pivot-diverge analysis was added — any architecture with shared nodes (most real architectures) would fail BH silently.

**Alternatives rejected:**
- Filter out pivot-diverge entries from `all_chains` passed to the function: would miss control gaps on pivot routes. Better to handle both types.

### 2. `bh_diagram_generator` drew edges between AP IDs, not diagram nodes

**What was decided:**
Rewrote the chain-edge section of `generate_bh_diagram`. The old code read `chain_aps[0]` / `chain_aps[1]` from `least_resistance_paths` entries and called `_node_id()` on them — producing `AP1`, `AP3` as Mermaid node IDs. These don't exist in the diagram, so the edges rendered as floating disconnected nodes.

New approach: pivot-diverge chains are drawn as `pivot -.-> target` edges using the actual node names from `pivot_diverge_chains[].pivot` and `.targets`. Sequential chains (if any) use the first/last element of their `chain` list. The result for DMZ: 8 dashed orange edges (4 pivot nodes × 2 targets) correctly anchored to ExtFirewall, WebServer, IntFirewall, AppServer → Database/FileServer.

**Reasoning:**
`pivot_diverge_chains` in `ground_truth["blackhat_critique"]` stores actual diagram node names (pivot, targets), while `least_resistance_paths` stores AP IDs in its normalized `chain` list. The diagram generator was using the wrong source.

**Alternatives rejected:**
- Building an AP-ID → entry-node lookup from `expected_attack_paths`: more complex, and the pivot-diverge structure already has the right node names available directly.

---

## 2026-06-26 (Session 5) — CriticRegistry + Harness Namespace (Phases A & B complete)

### 1. Harness namespace: `chatbot/harness/` with re-export shims

**What was decided:**
The three harness files (`harness.py`, `harness_stages.py`, `harness_governance.py`) are moved to a dedicated `chatbot/harness/` package: `controller.py`, `stages.py`, `governance.py`. The originals in `chatbot/modules/` are replaced with 3-line re-export shims so all existing callsites continue to work without change.

**Reasoning:**
The harness has grown into a major sub-system (~2,000 lines across 3 files + registry) and is now the primary enforcement surface for governance, model routing, and agent policy. Flat layout in `chatbot/modules/` beside 40+ unrelated domain modules creates cognitive overhead. A dedicated `chatbot/harness/` namespace signals ownership: harness/ is the extensibility/composition layer; modules/ is domain logic. Shims allow gradual migration without a flag-day import sweep.

**Alternatives rejected:**
- Flag-day import update across all callsites: disruptive, high regression risk, no benefit until all callers are updated at once.
- Keeping flat layout: sustainable for 3 files; unsustainable once registry + event_broker + sinks + manifest + router are added.

---

### 2. CriticRegistry as control tower for agent activation and governance enforcement

**What was decided:**
`chatbot/harness/registry.py` — `CriticDescriptor` + `CriticRegistry` with `register()`, `activate()`, `get()`, `list_all()`. Each critic self-registers at module import time (3-line `try/except` block, bottom of file). `MoEOrchestrator.__init__()` calls `registry.activate(blocked_agents)` instead of 4 hardcoded instantiations. `GovernanceSignals` gains a `blocked_agents: list` field. `QualityStage` reads `agent_policy` from `policies/agent_governance.yaml` and writes `ctx["blocked_agents"]` based on severity. `CriticStage` forwards `blocked_agents` to `run_moe_pipeline()` → `MoEOrchestrator`.

**Reasoning:**
Hardcoded instantiation meant adding a new critic required editing the orchestrator. The `PatternRegistry` for analysts already proved this pattern works. Registry membership is the contract: governance policy file (`agent_policy.blocked_agents_on_critical`) is the single place to allow/block critics — discoverable, auditable, zero-code enforcement. `list_all()` becomes the source for the Insights tab "Active Agents" display.

**Governance tiers:** `standard` (always eligible; governance can block on CRITICAL), `elevated` (requires policy allow — Blackhat), `optional` (non-scoring — EventBroker, activated separately via `registry.get()`).

**Alternatives rejected:**
- Hardcoding blocked_agents check inside MoEOrchestrator: duplicates policy logic in Python rather than in the policy file.
- Dynamic class discovery via importlib/pkgutil: brittle (name conventions required), harder to test, no benefit over explicit self-registration.
- Single global activation flag per critic in settings.py: doesn't support condition-based blocking (CRITICAL → block red_team); governance policy file is richer.

---

### 3. EventBroker: registry-resident optional critic as structured event bus (designed, not yet built)

**What was decided:**
`EventBrokerCritic` will be registered in `CriticRegistry` with `governance_tier="optional"`. It collects `HarnessEvent` objects (stage_trace, critic_trace, governance, aivss) from the pipeline and routes them to configured sinks (SiemSink, LangfuseSink, WebhookSink) via per-sink event filter lists. Sink config lives in `policies/agent_governance.yaml` under `event_broker.sinks` and is editable via the Config tab (not direct YAML edits). The Langfuse tab (`🔭 Traces`) in the dashboard embeds locally-hosted Langfuse as an iframe with graceful degradation.

**Reasoning:**
Traces cannot be appreciated without a UI to observe them. Langfuse self-hosted (Docker) provides a purpose-built trace/span viewer at zero marginal cost. Config tab exposure prevents users from needing to edit YAML directly — consistent with the one-stop-settings principle already in place for RAPIDS weights and model config. Registry membership makes the broker discoverable and governable (it can be blocked to disable all external emission).

**Alternatives rejected:**
- Standalone `harness_siem.py` as designed in the AIVSS plan: absorbed into `SiemSink` inside `chatbot/harness/sinks.py` — same JSONL output, cleaner ownership.
- Separate observability service outside TA: adds ops overhead; local Langfuse Docker is sufficient for the target context (SG Gov, development/staging use).
- Always-on verbose emit: per-sink event filter + verbosity presets (`minimal/standard/debug`) give operators explicit control over trace noise.

**Build order:** Phase C follows Phase B. Steps C1–C8 as documented in plan file `/home/bread/.claude/plans/i-am-thinking-for-piped-pie.md`.
