# ThreatAssessor — Architectural Decision Log

Read this file at the start of every session. After any significant decision about architecture, logic, or format, add an entry: date, what was decided, reasoning, alternatives rejected.

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
