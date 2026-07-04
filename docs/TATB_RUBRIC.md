# TATB — TA Test Benchmark

**Purpose.** TATB is ThreatAssessor's built-in evaluation harness for the threat models it produces. It scores every TM/ADR against four rubrics so users, reviewers, and auditors have a consistent, reproducible way to judge output quality.

**Why it exists.** No public benchmark evaluates threat-model correctness:

- **HELM / AgentBench / MMLU** measure general LLM reasoning — useful for choosing a model, not for judging whether a TM matches a specific architecture.
- **MITRE ATT&CK Evaluations** measure detection-tool coverage — a different problem: does the SIEM catch technique X, not "is our TM's mapping of technique X to node Y accurate."
- **OWASP LLM Top-10 / AVID** enumerate risk categories — vocabularies, not scoring systems.

If no public artefact scores threat-model quality, then TA — which produces threat models — has to establish the criteria itself. TATB is that attempt.

**Scope.** TATB scores a **single completed analysis** in isolation. It does not:
- re-run the pipeline,
- diff against a labelled corpus baseline (see `scripts/integration/backtest_all_architectures.py` for that),
- benchmark the underlying LLM (that's `HarnessModelGuardian`'s concern).

---

## The four rubrics

### 1. Threat-Relevant — are the threats architecturally grounded?

Guards against generic-boilerplate output. The same threats being predicted for every architecture is a sign the pipeline fell back to defaults rather than reasoning about the diagram.

| Sub-metric | Signal | Weight |
|---|---|---|
| Pattern diversity | `ground_truth.pattern_sources[]` — count of distinct triggers (RAPIDS, ARC, ATLAS, etc.) | 35% |
| Node-binding rate | Attack path `entry_node` / pivot appearing in `metadata.parsed_nodes{}` | 65% |
| Generic-fallback flag | Penalty when all paths share the same first three techniques `[T1078, T1059, T1005]` | −30 |
| ATLAS/AI check | Penalty when AI/ML pattern is detected but no ATLAS technique surfaces | −15 |

### 2. TTP-Accurate — do MITRE IDs bind correctly to behaviours?

Guards against technique hallucination or unjustified attribution. A TM that lists T1566 without saying *why* T1566 applies to this system is not usable evidence.

| Sub-metric | Signal | Weight |
|---|---|---|
| Validation pass rate | `technique_validation[].status === 'PASS'` ratio | 40% |
| Justification coverage | Techniques with non-empty `reason` (>10 chars) | 25% |
| Cross-critic agreement | Techniques mentioned by ≥2 critics (extracted from `07_moe_orchestrator.json`) | 20% |
| MoE lift | `confidence_breakdown.validation_adjustment` scaled to 0–100 | 15% |

### 3. Risk-Defensible — is scoring auditable and reproducible?

Guards against opaque scoring. A risk score that cannot be decomposed into contributing signals cannot survive an audit.

| Sub-metric | Signal | Weight |
|---|---|---|
| AIVSS completeness | All three flows (inbound, internal, outbound) have composite scores in `governance_signals.aivss` | 30% |
| Residual-risk sanity | Threats with `combined_effectiveness ≥ 0.90` must have `residual_risk_floor_applied: true` (NIST 10% floor) | 25% |
| Confidence provenance | `confidence_breakdown` keys present: `base`, `complexity_penalty`, `coverage_recovery`, `validation_adjustment`, `final` | 25% |
| Governance signals | `manipulation.critic_divergence_score`, `manipulation.confidence_swing`, `sovereignty` block populated | 20% |

### 4. Plan-Actionable — are controls concrete and prioritised?

Guards against alarm-fatigue (everything is CRITICAL) and against toothless recommendations ("review policies quarterly").

| Sub-metric | Signal | Weight |
|---|---|---|
| ADR completeness | `architecture_decision_records[]` with non-empty `context`, `hops[]`, `consequences` | 45% |
| P/D/I/R coverage | At least one control in each of Prevent / Detect / Isolate / Respond | 35% |
| Priority balance | `08_scrum_master.priority_tier_counts` — not all-CRITICAL, not zero-CRITICAL when CRITICAL paths exist | 20% |
| *(v2)* Actionability heuristic | Consequences reference concrete artefacts (specific IAM policy, log query, WAF rule) — deferred | — |

---

## Overall score and rating bands

Overall = simple average of the four rubric scores (25% each). Bands:

| Score | Band | Meaning |
|---|---|---|
| 85–100 | **Excellent** (green) | Would pass an external audit |
| 70–84  | **Solid** (olive)     | Usable for internal decisions |
| 50–69  | **Weak** (amber)      | Improve before sharing externally |
| 0–49   | **Draft** (red)       | TM is skeletal — re-run with fuller inputs |

---

## Design principles

**Warn-only.** TATB never blocks analysis. A low score is a signal for iteration, not a gate.

**No new analysis.** Every rubric reads from files the pipeline already writes. Three schema promotions (see below) make existing data easier to consume but add no new computation.

**Cross-scale.** Works for all architectures without per-arch labelling. A team can score 100 architectures on the same rubric consistently.

**Portable.** The rubric definitions in this document are the source of truth. Anyone implementing a threat modelling tool could adopt these rubrics — TATB is intentionally a public artefact.

---

## Schema dependencies

Three fields were added to make TATB implementable without heuristic parsing:

- `ground_truth.json:technique_validation` — top-level alias for `validation_report.validations.technique_relevance` so consumers don't need to navigate the nested structure.
- `ground_truth.json:residual_risks.per_threat[].residual_risk_floor_applied` — boolean flag when the NIST 10% floor kicked in, so residual-risk sanity is checkable rather than guessable.
- `08_scrum_master.json:priority_tier_counts{by_tier, by_priority, total}` — pre-aggregated tier/priority distribution rollup so priority-balance signal doesn't require re-iterating `action_plan[]`.

---

## Not in scope for TATB v1

- Cross-scenario diff (running `api_only` vs `full_moe` on the same MMD and comparing outputs). Deferred to v2 when a "Run Benchmark" backend endpoint exists.
- Labelled-corpus regression. Only 7 of 26 test architectures have labelled baselines — full-corpus regression stays in `scripts/integration/backtest_all_architectures.py`.
- MMD input-rigor scoring (does the diagram have enough nodes/edges/trust-zones to produce a meaningful TM). Governance's `check_input` reads the MMD for security signals but not thoroughness. This is a separate concern for a future rubric.
- LLM capability benchmarks (HELM, AgentBench). These evaluate the underlying model, not the TM output. Belongs in `HarnessModelGuardian` if added.

---

## References

- `chatbot/api/static/js/dashboard.js:loadBenchmarkTab` — the TATB Scorecard UI implementation.
- `chatbot/modules/ground_truth_generator.py` — emits `technique_validation` alias.
- `chatbot/modules/residual_risk.py` — emits `residual_risk_floor_applied`.
- `chatbot/harness/stages.py:ScrumMasterStage` — emits `priority_tier_counts`.
- `docs/DECISIONS.md` — architectural decisions including the TATB positioning entry.
