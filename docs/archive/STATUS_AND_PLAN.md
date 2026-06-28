# ThreatAssessor - Status & Action Plan

**Version:** 1.5  
**Last Updated:** 2026-06-07  
**Current Status:** ✅ REST API + Dashboard live — 5-Critic MoE Pipeline (Purple Team + Blackhat), Cross-Path Chain Analysis, Briefing Export, Sensitivity Presets

---

## 🎯 Current Status (June 2026)

### What's Working Now

| Component | Status | Details |
|-----------|--------|---------|
| REST API (FastAPI) | ✅ Live | `make start` → http://localhost:8000 |
| Dashboard UI | ✅ Live | http://localhost:8000/dashboard |
| Swagger / OpenAPI | ✅ Live | http://localhost:8000/docs + `openapi.yaml` in repo |
| SSE streaming analysis | ✅ Live | Real-time progress via `/api/v1/analyze-stream` |
| Expert Review tab | ✅ Live | Parallel/Sequential/Auto modes; per-critic bars; Pause/Resume/Cancel |
| Before/after risk bars | ✅ Live | Honest residual framing, 10% floor |
| Dynamic confidence scoring | ✅ Live | Architecture-sensitive base (0.72–0.995); complexity penalises, coverage recovers |
| ATLAS/ARC name resolution | ✅ Live | AML.T* / AML.M* IDs resolve to real names in all three API lookup endpoints |
| ARC category badges | ✅ Live | arc_id pill badges (SAF·Safety etc.) in Mitigations tab list + right pane |
| Parallel Expert Review UX | ✅ Live | Per-critic progress bars + per-second elapsed timer; synthesis bar appears on phase switch |
| Upload progress messages | ✅ Live | Animated tick updates [STAGE] N% inline + counts ETA down |
| Mitigations tab ordering | ✅ Live | Sorted by _impact formula (paths × risk × expertBoost) matching Overview |
| Technique hallucination prevention | ✅ Live | MITRE-grounded synthesis + reflection prompts; CRITIC_HALLUCINATION root cause |
| Residual risk floor | ✅ Fixed | 10% minimum per NIST (was producing 0 for 4+ controls) |
| Self-validation accuracy | ✅ Fixed | T1212/T1490/T1059/T1213 + 7 other techniques — no more false negatives |
| Tester scoring | ✅ Fixed | Sub-dimension penalty, critical_gaps override, PASS→MINOR_GAPS correction |
| Tester false-positive detection | ✅ Fixed | MITRE ground-truth check first; fixes M1032/T1485 hallucination |
| Expert Review UI | ✅ Fixed | Progressive critic cards; Pause/Resume; tab-switch state preserved |
| Reports tab | ✅ Fixed | Markdown + diagrams only; JSON moved to Raw Data tab |
| Raw Data tab | ✅ Fixed | Async file-based; Foundation + Expert Review JSON sections; individual downloads |
| Content tabs disabled | ✅ Fixed | All tabs greyed out before first upload; re-greyed after reset |
| requirements.txt | ✅ Fixed | FastAPI/uvicorn/pydantic/sse-starlette now pinned |
| Purple Team Critic (2D) | ✅ Live | Detection depth, coverage gaps, ADR operability — 3 lenses; output: `06b_purple_team_critique.json` |
| Blackhat Critic (2E) | ✅ Live | Cross-path chain exploitation, pivot-diverge chains, stealth scoring; supreme critic; output: `06c_blackhat_critique.json`; short-circuits if <2 APs |
| BH-N synthetic APs | ✅ Live | Blackhat pivot chains surfaced as BH-N attack paths in ThreatModel |
| Expert Consensus cards | ✅ Live | Expandable/collapsible per-critic cards in dashboard Expert Review tab |
| Analysis-in-progress state | ✅ Live | Dashboard correctly reflects running state and disables inputs during analysis |
| Blindspot Act/Note classification | ✅ Live | Blindspots tagged ⚠Act (actionable) or 📋Note (informational) |
| Export Briefing endpoint | ✅ Live | `GET /api/v1/reports/{name}/briefing?fmt=md` — self-contained Markdown two-pager |
| Config sensitivity presets | ✅ Live | Architect/Tester/Red Team accept `sensitivity: lenient \| balanced \| strict` instead of raw numeric thresholds |
| Completeness Check 7 | ✅ Live | Behavioral analytics / API Gateway detection gap check |
| Completeness Check 8 | ✅ Live | Supply chain / BCP coverage check |

---

## 📋 Recent Work (June 7, 2026)

### 5-Critic MoE Pipeline — Purple Team + Blackhat (this session)
**Commit:** `9eef4e3`

#### 1. Purple Team Critic (2D) — `purple_teamer_critic.py`
**Change:** New critic added as the fourth stage in the MoE pipeline. Evaluates findings across three lenses: (a) **coverage** — detection coverage gaps across the attack surface; (b) **assume-breach** — post-compromise lateral movement and persistence detection depth; (c) **SOC operability** — ADR operability and alert actionability. Output saved to `06b_purple_team_critique.json`. Optional toggle; off by default.

#### 2. Blackhat Critic (2E) — Supreme Critic
**Change:** New fifth-stage critic that runs last and receives all prior critique output (ground truth + critics 2A–2D). Focuses on cross-path chain exploitation — identifying multi-step pivot-diverge chains that individual path-scoped critics miss. Produces stealth scoring per chain. Short-circuits with a warning if fewer than two attack paths are present. Pivot chains are surfaced as **BH-N synthetic attack paths** in the ThreatModel output. Output saved to `06c_blackhat_critique.json`. Optional toggle; off by default. New file: `bh_diagram_generator.py`.

#### 3. MoE Pipeline Ordering
**Change:** Fixed pipeline sequence: Architect (2A) → Coverage Auditor (2B) → Exploit Analyst (2C) → Purple Team (2D) → Blackhat (2E). Core three (2A–2C) always execute. PT and BH are gated by `enable_purple_team` and `enable_blackhat` config flags.

#### 4. Config — Sensitivity Presets
**Change:** Architect, Tester, and Red Team critics now accept a `sensitivity` enum (`lenient | balanced | strict`) instead of raw numeric threshold parameters. The preset maps to internal scoring weights, reducing misconfiguration risk when customising critic aggressiveness.

#### 5. Completeness Validator — Checks 7 and 8
**Change:** Two new checks added to `completeness_validator.py`:
- **Check 7:** Behavioral analytics / API Gateway — detects architectures that lack monitoring coverage on gateway-tier components.
- **Check 8:** Supply chain / BCP — flags missing continuity or third-party risk controls.

#### 6. Export Briefing Endpoint
**Change:** New endpoint `GET /api/v1/reports/{name}/briefing?fmt=md` returns a self-contained Markdown two-pager suitable for offline sharing or executive distribution. `openapi.yaml` updated accordingly.

#### 7. Dashboard — Expert Consensus + Blindspot Classification
**Change:** Expert Consensus section cards are now expandable/collapsible. Analysis-in-progress state correctly disables upload and run controls. Blindspots are now classified as **⚠Act** (actionable gap requiring remediation) or **📋Note** (informational observation).

---

## 📋 Recent Work (May 27, 2026)

### Parallel Expert Review, Dynamic Confidence, ATLAS/ARC Fixes (this session)
**Commit:** `b2684c3`

#### 1. Parallel Expert Review — Per-Critic Progress Bars
**Change:** When `critic_mode` is `parallel` or `auto`, the Expert Review progress box renders three individual bars (Architect / Tester / Red Team) instead of one sequential bar. A per-second interval ticks elapsed time on each running card (`⟳ Running… 12s`). Each bar fills and shows `✓` in the critic's status colour when its `critic_result` SSE arrives. Synthesis gets its own bar row that slides in when the parallel phase ends.

#### 2. Upload Progress — Animated Tick Syncs Message % and ETA
**Change:** The animated tick that inches the bar forward between SSE events now also updates the status message text — replacing the stale `[PARSING] 5%` with the live animated value (e.g. `[PARSING] 9%`) and counting the ETA down by 0.6 s/tick. Previously the message froze while the bar moved.

#### 3. Mitigations Tab — Sorted by _impact Formula
**Change:** `loadControlsTab()` is now `async` and fetches MoE + Red Team endorsement data to sort controls by `_impact = paths × riskScore × expertBoost`, matching the Overview top-controls ranking. Secondary sort by priority tier (critical → high → medium).

#### 4. ARC Framework — arc_id Pill Badges
**Change:** ARC category names in control rationales (`AI/ML (ARC): Safety, Accountability`) are displayed as `[SAF · Safety] [ACC · Accountability]` pill badges in both the Mitigations list card and the right-pane detail. Client-side `_formatArcCats()` maps the 9 fixed category names to their `arc_id` short codes from `risks.yaml`.

#### 5. ATLAS/ARC Name Resolution (reports.py)
**Problem:** Mitigations right-pane showed `· Unknown (AML.T0043)` — `MitreHelper.find_technique()` only indexes Enterprise ATT&CK; `AML.*` IDs are a separate ATLAS corpus.  
**Fix:** All three lookup endpoints (`/api/v1/techniques`, `/api/v1/mitigations`, `/api/v1/technique-mitigations`) now route `AML.T*` / `AML.M*` IDs to `AtlasHelper` before falling back to `MitreHelper`.

#### 6. Dynamic Confidence Scoring (threat_analyst.py)
**Change:** `base_confidence` replaced from hardcoded `0.995` with `_compute_base_confidence(ground_truth)`. Formula: start at `0.995 − complexity_penalty` (node/edge count), then recover toward that ceiling proportionally to coverage signals (control coverage 40%, validation pass rate 30%, path coverage 20%, technique depth 10%). Floor at `0.72`. `confidence_breakdown` added to API response.

#### 7. Technique Hallucination Prevention (moe_orchestrator.py, architect_critic.py)
**Problem:** Architect LLM called `T1590.005` "model extraction" and `T1565.001` "data poisoning" — wrong labels for real, valid MITRE IDs. Tester saw the wrong labels and flagged the IDs as non-existent; synthesis generated a false `DATA_REFERENCE_ERROR` contradiction.  
**Fix:**
- `_resolve_technique_ids()` looks up all `T####[.###]` IDs from critic text against MITRE and builds a verified name block
- Injected into both the synthesis prompt and `_reflect_contradictions` prompt as authoritative grounding
- `CRITIC_HALLUCINATION` added as a root cause category in the reflection schema
- Architect critic prompt: rule added requiring technique IDs to come only from artifact data, never invented

#### 8. Parallel Critics Mode (moe_orchestrator.py)
**Change:** `run_pipeline()` accepts `critic_mode: sequential | parallel | auto`. `_run_full_parallel()` fires per-critic `progress_callback` inside `as_completed()` so each critic card updates the moment it finishes. `parallel_starting` callback signals the frontend before the thread pool blocks. `critic_mode` (resolved) stored in `MoEResult` and written to `07_moe_orchestrator.json`.

#### 9. ARC Framework Data — Committed to Repo
`chatbot/data/arc/controls.yaml` (88 controls) and `risks.yaml` (9 categories, component rules) are now in the repository. Previously the AI pattern couldn't be reproduced from a fresh clone.

---

## 📋 Recent Work (May 25, 2026)

### Expert Review UX Overhaul + Dashboard Polish (this session)

#### 1. Expert Review — Progressive Streaming
**Change:** Each critic's detailed card is appended live as it completes instead of waiting for all three. Critic results and the progress box update in real time.  
**Commit:** `cf10377`

#### 2. Expert Review — Pause / Resume / Cancel
**Change:** Pause aborts the SSE stream but preserves state (progress %, cards, live results) in `_erpState`. Resume reconnects and the orchestrator skips already-completed critics via `_load_saved_critique()` checkpoint loading. Cancel purges the three critique JSON files via `DELETE /api/v1/expert-review/cancel`. Cancel button appears immediately when run starts via in-place `outerHTML` button-row swap.  
**Commit:** `cf10377`

#### 3. Expert Review — Synthesis Sub-Step Progress
**Change:** Layer 3 (previously a silent ~20s block showing only "Running") now fires 5 `progress_callback` signals: `synthesis:confidence`, `synthesis:llm`, `synthesis:build`, `synthesis:save`, `synthesis:artifacts`. The SSE loop converts these to distinct progress events; the Synthesis card status shows the current sub-step (e.g. "⚙ LLM consensus (~20s)...").  
**Commit:** `cf10377`

#### 4. Expert Review — Confidence 0% Display
**Change:** When a critic's confidence adjustment is zero, display "No adjustment" in neutral grey instead of "0% confidence" (which falsely implies low confidence). Applies to live cards, progress preview, completed panel headers, and the waterfall.  
**Commit:** `cf10377`

#### 5. Tester False-Positive Fix — M1032/T1485 (`tester_critic.py`)
**Problem:** Tester LLM claimed M1032 is not a valid mitigation for T1485 (Data Destruction) — this is a hallucination; MITRE lists M1032, M1053, M1018 for T1485.  
**Fix:** Rewrote `_check_if_false_positive()` to check MITRE ground truth first — if the M-code is in `get_technique_mitigations(T####)`, it is definitively not a false positive, regardless of LLM wording.  
**Commit:** `cf10377`

#### 6. Reports / Raw Data Tab Split
**Reports:** Now shows markdown and mermaid only. Expert Review JSON section removed. "Full Pack" replaced with "All Reports" (`pack=reports`).  
**Raw Data:** Rewritten as async. Fetches saved JSON from report directory. Organised into **Foundation Analysis** (`ground_truth.json`) and **Expert Review** (04–07 JSON) sections, plus **Live Session Data** for in-memory artifacts. Individual download buttons + "Download All JSON" (`pack=json` zip).  
**Download endpoint:** Added `pack=json` and `pack=reports` to `/api/v1/reports/{name}/download`.  
**Commit:** `cf10377`

#### 7. Content Tabs Disabled Until Analysis Complete
**Change:** Attacks, Controls, Hardening, Expert Review tabs get `disabled` class (35% opacity, `pointer-events:none`) on page load, during analysis-in-progress, and after reset. Enabled only when `displayResults()` fires.  
**Commit:** `cf10377`

#### 8. Mitigations Legend Font Size
**Change:** Downsized from `h4` / `0.875rem` to match the Threat Paths legend (`0.875rem` title, `0.8125rem` body). Score/Implementation/Click notes condensed to a single muted italic line.  
**Commit:** `cf10377`

---

## 📋 Recent Work (May 23–24, 2026)

### Bug Fix + Validation Hardening (this session)

#### 1. Residual Risk — 10% Floor (`residual_risk.py`)
**Problem:** Independence stacking with 4+ controls drove `failure_probability` below `int()` truncation — phishing/ransomware/supply_chain showed residual = 0, which is physically implausible.  
**Fix:** Applied `MIN_FAILURE_PROBABILITY = 0.10` cap (NIST industry standard). No control suite provides >90% effectiveness against determined attackers.  
**Impact:** Risk reduction changed from ~95% → ~78%, which is accurate. Re-run recommended warning added in dashboard for old reports.  
**Commit:** `2bea585`

#### 2. Expert Review UI — 3 Items (`dashboard.js`)
**Problem (a):** "Collapse all/Expand all" only covered the 3 agent panels, not Cross-Expert Findings / Blindspots / Disagreements / Improvement Tiers.  
**Fix:** Wrapped all orchestrator output sections in `.er-panel` structure.  
**Problem (b):** Tester coverage MEDIUM + consistency LOW + validation HIGH → overall PASS +0.0% was illogical. Dead `critical_gaps` variable never used; `roadmap_validation: 1/10 = 10%` sub-score ignored.  
**Fix:** Sub-dimension penalty (−2% per sub-score < 50% of max), critical_gaps override (PASS → MINOR_GAPS when HIGH/CRITICAL gaps present), sub-dimension bars in UI.  
**Problem (c):** No indication when residual = 0 for high-risk threats.  
**Fix:** Added "Re-run recommended" banner listing affected threats.  
**Commit:** `a01aa74`

#### 3. Self-Validation — False Negatives (`self_validation.py`)
**Problem:** `overall_valid: False` was triggering for architectures where all MITRE mappings are actually correct. Two root causes across 3 sessions:

| Commit | Techniques fixed | Root cause |
|--------|-----------------|-----------|
| `389e667` | T1059, T1213, T1005, T1567, T1486, T1490, T1485, T1203, T1212 | CamelCase node names (`APIGateway`, `AuthService`) didn't match lowercase keyword list |
| `38a1801` | T1212 (AccessControlAPI paths), T1490 (Cache target) | `"access control"` not in T1212 keyword list; `"cache"` not in T1490 data keyword list |

**Impact:** Downstream: Architect vs Red Team disagreement in Expert Review was caused by this — Red Team misread `overall_valid: False` as invalid control mappings; in reality the control-to-technique mappings were all MITRE-valid. After fix, `overall_valid: True`, 0 issues for architectures like `tmpchrsnkmg` and `tmpnhh2jf38`.

#### 4. Root-Level Cleanup (`d4bcdca`)
- `requirements.txt` — Added 5 missing FastAPI-tier packages (were in venv, not pinned)
- `CLAUDE.md` — Updated version/status, added endpoint table, correct html/ links
- `README.md` — Added endpoint table, repo layout, streaming curl example
- `Makefile` — Added `make openapi` target, fixed `make setup` idempotency
- `openapi.yaml` — New file: 14-path OpenAPI 3.1 spec with server + ApiKeyAuth scheme
- `chatbot/api/app.py` — Added `custom_openapi()` hook (injects server URL + security scheme)

---

## 🔜 Next Session — Pending Items

### High Priority

#### A. End-to-end test of 5-critic pipeline across all architectures
The Purple Team (2D) and Blackhat (2E) critics have not yet been validated across all 22 test architectures. Run the full pipeline with both optional critics enabled and confirm no regressions.

```bash
# Full MoE with PT + BH enabled
./demo_expert_llm.sh tests/data/architectures/<arch>.mmd

# Or batch re-run all 22 (once script exists — see item B)
python3 scripts/backtest_all_architectures.py
```

#### B. `scripts/backtest_all_architectures.py` — File missing
`CLAUDE.md` and `Makefile` reference this script but it doesn't exist. Create it or remove references before publishing.

#### C. BH-N synthetic AP ADR coverage
Blackhat pivot chains are surfaced as BH-N synthetic attack paths in the ThreatModel but ADR generation does not yet produce a corresponding decision record for them. Extend `adr_generator.py` to handle BH-N entries.

### Medium Priority

#### D. Dynamic confidence — validate against real architectures
Run deterministic on the smallest test arch and on `21_agentic_ai_system` (20 nodes). Confirm:
- Small arch with poor coverage: `confidence_breakdown.base` < 0.90
- Complex arch with low coverage: base < 0.80
- Complex arch with high coverage + all 8 checks: base recovers to ~0.93
- `confidence_breakdown` present in API response with all fields

#### E. Cloud-specific threat patterns (roadmap item #3)
No AWS/Azure/GCP-specific threat models yet. The current `cloud_generic` pattern uses MITRE Enterprise as a proxy and explicitly notes its limitations. Cloud pattern would add misconfiguration detection and serverless-specific attack paths.

#### F. Tester scoring — roadmap_validation sub-dimension
`roadmap_validation` scores low because the Tester evaluates the Architect's roadmap against its own findings (structurally expected divergence, not a real quality failure). Consider reducing its weight relative to `validation_checks` and `coverage_metrics`.

---

## 📋 Implementation History

### ✅ Stage 2 Phase 2B (May 2026) — REST API + Dashboard
**Goal:** FastAPI REST API with live dashboard for browser-based analysis  
**Result:** Full API live with SSE streaming, Expert Review integration, and `openapi.yaml`

**What Was Built:**
1. **FastAPI application** (`chatbot/api/app.py`) — `POST /analyze`, `GET /health`, dashboard serve
2. **SSE streaming** (`chatbot/api/streaming.py`) — `/analyze-stream` + `/expert-review` with real-time progress
3. **Reports API** (`chatbot/api/routes/reports.py`) — 8 endpoints: list, file serve, summary, ZIP download, MITRE libraries
4. **Dashboard UI** (`chatbot/api/static/`) — 5 tabs: Overview, Controls, Visualise, Reports, Expert Review
5. **Expert Review tab** — MoE streaming, collapsible panels (all sections), sub-dimension bars, contradiction pane
6. **Before/after risk bars** — Honest residual framing with 10% floor, tier markers
7. **OpenAPI spec** (`openapi.yaml`) — 14 paths, server URL, ApiKeyAuth scheme
8. **Server lifecycle scripts** (`scripts/api/`) — start/stop/restart/status

**Key commits in this phase:**
- `d3214a0` FastAPI MVP (PHASE 0)
- `174ed6e` SSE streaming (PHASE 1)  
- `40090ef` Expert Review streaming endpoint + dashboard integration
- `e545907` LLM synthesis in Layer 3 orchestrator
- Dashboard UI: `d4dc523` → `25e6bd5` → `0297e07` → `c9ecfa4` → `5e2f649` → `c432ced` → `739c753` → `1af7ab3`
- Bug fixes: `2bea585` (residual floor), `a01aa74` (Expert Review), `389e667` + `38a1801` (self-validation)
- Root cleanup: `d4bcdca`

---

### ✅ Phase 3D (May 15–17, 2026) — Mixture of Experts (MoE)
**Goal:** Production-ready MoE validation system with coherent executive dashboard  
**Time:** 18 hours (Week 1: 8h, Week 2: 4h, Week 3: 6h)  
**Result:** 3-layer validation pipeline with 16 files per architecture and 93–96% final confidence

**What Was Built:**
1. Agent module structure (`chatbot/modules/agents/`) — critics/, analysts/, orchestrators/
2. MoE Orchestrator — sequential validation, fail-fast, confidence adjustments, consensus synthesis
3. Validation-only critics (v3.0) — no recommendation conflicts, prerequisite checking
4. Executive Dashboard Generator (`00_executive_dashboard.md`) — single source of truth
5. Demo scripts — `demo_deterministic_engine.sh` (30s) + `demo_expert_llm.sh` (2 min)

**Key metrics:**
- 16 files generated per architecture
- Confidence: 93–96% (99.5% base ± adjustments)
- Coherence: 95/100 (single narrative)
- Tested on 22 architectures

**See:** [docs/phases/phase3d/](phases/phase3d/)

---

### ✅ Phase 3C MVP (May 10–16, 2026) — LLM Critics
**Goal:** LLM as Judge/Critic — intelligent gap detection  
**Time:** ~8.5 hours  
**Result:** 85/100 composite confidence; Architect 82 + Tester 88

**What Was Built:** Hybrid MITRE approach, Architect Critic, Tester Critic, Agent Framework, full critique pipeline  
**See:** [docs/phases/phase3c/85_PERCENT_ACHIEVED.md](phases/phase3c/85_PERCENT_ACHIEVED.md)

---

### ✅ Phase 3B+ (May 9, 2026) — Path-based Controls
**Goal:** Intelligent control placement + orphan detection  
**Time:** ~6 hours  
**Result:** Confidence 99.1% → 99.5%, visual clarity 70% → 95%

**See:** [docs/phases/PHASE3B_DIAGRAM_PLACEMENT.md](phases/PHASE3B_DIAGRAM_PLACEMENT.md)

---

### ✅ Phase 3B (May 3, 2026) — Completeness Validation
**Goal:** Prevention + DIR Framework + Residual Risk  
**Time:** ~8 hours  
**Result:** Confidence 81% → 99.1%, technique coverage 100%

**See:** [docs/phases/PHASE3B_IMPROVEMENTS.md](phases/PHASE3B_IMPROVEMENTS.md)

---

### ✅ Phase 3A (May 2, 2026) — RAPIDS-driven modeling
**Result:** Confidence 79% → 81%  
**See:** [docs/phases/](phases/) for earlier history

---

## 📊 Current Validation Metrics

| Metric | Target | Actual | Status |
|--------|--------|--------|--------|
| Validation pass rate | 95%+ | 100% (22/22) | ✅ |
| Deterministic base confidence | architecture-sensitive | 0.72–0.995 | ✅ |
| MoE final confidence | 93–96% | 93–96% | ✅ |
| Technique coverage | 100% | 100% | ✅ |
| Orphan nodes | 0 | 0 | ✅ |
| Visual clarity | 90%+ | 95% | ✅ |
| Residual risk floor | ≥10% | ≥10% (NIST) | ✅ |
| Self-validation false negatives | 0 | 0 (post-fix) | ✅ |
| ATLAS technique name resolution | 100% | 100% (AML.T*/AML.M*) | ✅ |
| Synthesis hallucination prevention | n/a | MITRE-grounded prompts | ✅ |

---

## 🐛 Known Limitations

| Issue | Impact | Status |
|-------|--------|--------|
| Policy controls (behavioral analysis, audit log) may appear in "Additional recommended" comment | Cosmetic — data correct in ground_truth.json | Accepted |
| LLM availability (~33% uptime on free tier) | Expert Review unavailable intermittently | Workaround: deterministic-only mode |
| Large architectures (>30 nodes) may produce cluttered diagrams | Visual complexity | Workaround: use subgraphs |
| Tester LLM sometimes hallucinates invalid mitigation claims | False finding in Expert Review | MITRE ground-truth post-process overrides LLM verdict (fixed `cf10377`) |
| Old reports (pre May 24) may still show `overall_valid: False` | Stale self-validation result | Regenerate with `demo_expert_llm.sh` |
| No AWS/Azure/GCP-specific threat models | Cloud misconfigurations not detected | Partial — `cloud_generic` pattern uses MITRE Enterprise as proxy |
| Dynamic confidence not yet validated across all 22 architectures | Base confidence formula may need tuning | Pending — run backtests |
| BH-N synthetic APs not yet covered by ADR generation | Blackhat pivot chains produce ThreatModel entries but no corresponding ADR | Pending |
| 5-critic pipeline not yet e2e tested across all 22 architectures | Regressions from PT/BH addition possible | Pending — run `backtest_all_architectures.py` |

---

## 🚀 Quick Commands

```bash
# Start API server
make start                              # → http://localhost:8000/dashboard

# CLI analysis
./demo_expert_llm.sh your_arch.mmd      # Full MoE (~2 min, requires LLM key)
./demo_deterministic_engine.sh arch.mmd # Deterministic only (~30 sec)

# Development
make test                               # Run test suite
make openapi                            # Regenerate openapi.yaml
python3 -m chatbot.modules.completeness_validator arch_name

# View report
cat report/your_architecture/00_executive_dashboard.md
```

---

## 🔗 Key Documentation

| Doc | Purpose |
|-----|---------|
| [README.md](../README.md) | User quick start + endpoint table |
| [CLAUDE.md](../CLAUDE.md) | Developer quick reference + module paths |
| [openapi.yaml](../openapi.yaml) | Machine-readable API spec (14 paths) |
| [docs/operations/API_MANAGEMENT.md](operations/API_MANAGEMENT.md) | Server lifecycle |
| [docs/operations/OPERATIONS.md](operations/OPERATIONS.md) | Troubleshooting |
| [docs/core/V1_FEATURES.md](core/V1_FEATURES.md) | Complete feature list |
| [docs/phases/phase3d/](phases/phase3d/) | MoE architecture details |

---

**Single Source of Truth:** This file tracks project status and roadmap  
**Last Updated:** 2026-06-07  
**Status:** ✅ REST API + Dashboard live — 5-Critic MoE Pipeline (Purple Team + Blackhat), Cross-Path Chain Analysis, Briefing Export, Sensitivity Presets
