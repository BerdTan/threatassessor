# TATB — TA Test Benchmark

**Purpose.** TATB is ThreatAssessor's built-in evaluation harness for the threat models it produces. It scores every TM/ADR against four rubrics so users, reviewers, and auditors have a consistent, reproducible way to judge output quality.

**Why it exists.** No public benchmark evaluates threat-model correctness:

- **HELM / AgentBench / MMLU** measure general LLM reasoning — useful for choosing a model, not for judging whether a TM matches a specific architecture.
- **MITRE ATT&CK Evaluations** measure detection-tool coverage — a different problem: does the SIEM catch technique X, not "is our mapping of technique X to node Y accurate."
- **OWASP LLM Top-10 / AVID** enumerate risk categories — vocabularies, not scoring systems.

If no public artefact scores threat-model quality, then TA — which produces threat models — has to establish the criteria itself. TATB is that attempt.

**Scope.** TATB scores a **single completed analysis** in isolation. It does not:
- re-run the pipeline,
- diff against a labelled corpus baseline (see `scripts/integration/backtest_all_architectures.py` for that),
- benchmark the underlying LLM (that is `HarnessModelGuardian`'s concern).

---

## The four rubrics

### 1. Threat-Relevant — are the threats architecturally grounded?

Guards against generic-boilerplate output. The same threats predicted for every architecture is a sign the pipeline fell back to defaults rather than reasoning about the diagram.

| Sub-metric | Signal | Weight |
|---|---|---|
| Node binding | Attack path `entry_node` / first path node appearing in `metadata.parsed_nodes` | 40% |
| Node coverage | Fraction of diagram nodes appearing in at least one attack path | 25% |
| Technique variety | Distinct MITRE techniques across all paths, normalised (12 = 100%) | 35% |
| Generic-fallback penalty | All paths share an identical technique set | −20 pts |
| ATLAS-when-AI penalty | AI/ML architecture detected but no ATLAS (AML.T*) techniques emitted | −15 pts |

**Analysis engines** (RAPIDS / AI+ATLAS / Cloud) are shown as a tile for transparency but are not in the score — engine count reflects architecture type, not analysis quality.

---

### 2. TTP-Accurate — do MITRE IDs bind correctly to behaviours?

Guards against technique hallucination or unjustified attribution. A threat model that lists T1566 without explaining *why* T1566 applies to this system is not usable evidence.

| Sub-metric | Signal | Weight |
|---|---|---|
| Validation depth | CONFIRMED (structural evidence) × 1.0 + PLAUSIBLE (keyword heuristic) × 0.5 + FAILED × 0; from `self_validation.py` | 30% |
| MITRE alignment | For each (technique, control) pair: does the control match MITRE's recommended mitigations? Synonym expansion covers common controls (ids/ips → Network Intrusion Prevention, mfa → Multi-factor Authentication, etc.) | 30% |
| Cross-critic agreement | Techniques independently flagged by ≥ 2 Expert Review critics (`07_moe_orchestrator.json`) | 25% |
| MoE lift | How much the Expert Review panel moved the confidence score; negative lift flags over-confident initial analysis | 15% |

**Validation classes:**
- `CONFIRMED` — structural evidence: path contains the nodes that justify the technique (e.g. "Execution environment present" for T1059)
- `PLAUSIBLE` — keyword heuristic match; carries half weight in the score
- `FAILED` — no structural or keyword evidence; zero weight

---

### 3. Risk-Defensible — are defences mapped to specific paths and hops?

Guards against arch-wide hand-waving. Saying "we have a WAF" is not the same as "the WAF covers AP-3, node WebServer, technique T1190."

| Sub-metric | Signal | Weight |
|---|---|---|
| Technique mitigation | Fraction of attack-path techniques with at least one mapped control | 40% |
| AP-aligned mitigation | Fraction of (AP, technique) pairs where a control explicitly covers that path *and* that technique — stricter than arch-wide | 15% |
| Hop layer coverage | Each hop on each path should have Prevent + Detect + Isolate + Respond controls; hops missing any layer are flagged | 30% |
| Residual exposure | Threats remaining at MONITOR or MITIGATE after controls are applied (lower = better) | 25% |

**Analysis hygiene** (AIVSS completeness, confidence trail, governance markers) is shown as a separate tile for pipeline-provenance transparency. It is **not included in the Risk-Defensible score**.

**Zero-trust layer inference:** the hop-layer checker infers which zero-trust layers a control covers from its name. Examples: `edr` covers prevention + detect + respond; `human_oversight` covers detect + respond; `rate limiting` covers prevention + detect + isolate + respond. The synonym table is maintained in `rapids_driven_controls.py:_MULTI_LAYER_CONTROLS`.

---

### 4. Plan-Actionable — can an engineer act on this today?

Guards against alarm fatigue (everything is CRITICAL) and toothless recommendations ("review policies quarterly").

| Sub-metric | Signal | Weight |
|---|---|---|
| Item completeness | Each SM action item has `action`, `rationale`, `first_step`, and `effort` | 25% |
| Measurable outcomes | Items include `confidence_gain` or `risk_reduction_estimate` | 20% |
| Sprint spreadability | Effort uses days/weeks; priority uses critical/high/medium/low | 15% |
| Control specificity | Items name a specific tool, node, or technique | 10% |
| ADR alignment | High-priority items reference controls mandated by the ADR hop analysis | 10% |
| AP closure | Every CRITICAL attack path has at least one explicit plan item | 20% |

---

## Overall score and rating bands

Overall = weighted average of the four rubrics:

| Rubric | Weight |
|---|---|
| Threat-Relevant | 30% |
| TTP-Accurate | 25% |
| Risk-Defensible | 25% |
| Plan-Actionable | 20% |

| Score | Band | Meaning |
|---|---|---|
| 85–100 | **Excellent** | Would pass an external audit |
| 70–84  | **Solid**     | Usable for internal decisions |
| 50–69  | **Weak**      | Improve before sharing externally |
| 0–49   | **Draft**     | Skeletal — re-run with fuller inputs |

---

## Data requirements

| File | Required for |
|---|---|
| `ground_truth.json` | All four rubrics |
| `governance_signals.json` | TTP-Accurate (MoE lift), Risk-Defensible (hygiene display) |
| `07_moe_orchestrator.json` | TTP-Accurate (cross-critic, MoE lift) |
| `08_scrum_master.json` | Plan-Actionable |

Rubrics with missing data fall back to a neutral 50% for the unavailable signals.

---

## Design principles

**Warn-only.** TATB never blocks analysis. A low score is a signal for iteration, not a gate.

**No new analysis.** Every rubric reads from files the pipeline already writes.

**Cross-scale.** Works for all architectures without per-arch labelling. A team can score 100 architectures on the same rubric consistently.

**Portable.** The rubric definitions in this document are the source of truth. Anyone implementing a threat modelling tool could adopt these rubrics — TATB is intentionally a public artefact.

---

## Implementation references

- `chatbot/api/static/js/dashboard.js` — `_computeTatbScores()` (dashboard scorer) and `_tatbShowRubricDoc()` (this document's UI rendering)
- `.claude/skills/tatb-score/scripts/tatb-score.py` — CLI scorer (mirrors dashboard logic)
- `chatbot/modules/self_validation.py` — emits `technique_validation` with CONFIRMED/PLAUSIBLE/FAILED classification
- `chatbot/modules/rapids_driven_controls.py` — `_MULTI_LAYER_CONTROLS` (hop-layer inference)
- `chatbot/modules/ground_truth_generator.py` — emits `architecture_decision_records`, `pattern_sources`, `run_id`
- `chatbot/modules/adr_generator.py` — builds ADR hop structure with zero-trust gap notes
- `chatbot/harness/stages.py:ScrumMasterStage` — emits action plan with measurable outcomes
