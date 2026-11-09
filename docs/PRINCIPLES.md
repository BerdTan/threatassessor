# ThreatAssessor — Design Principles

Ten governing principles derived from TA's own design history. These are not rules — they are the distilled reasoning behind decisions already made. When a proposed change is in tension with a principle, the tension must be named explicitly in DECISIONS.md before coding begins. The principles guide; they do not restrict when a principle is demonstrably wrong. When a principle needs revision, update this file and add a DECISIONS entry explaining why.

**How to use:** At session start, before any ⬜ priority item: 30-second audit against these ten. Flag any tension in the DECISIONS entry. This is a forcing function for explicit trade-off documentation, not a veto.

---

## 1 — Simplest architecture that works

Introduce a stage, component, or mode only when it solves an actual problem that simpler wiring cannot. The harness stage registry (register_scenario decorator) enforces this: adding a scenario requires a decorated function, not edits scattered across the codebase.

**Confirmed violation:** brain_fast was introduced to solve a real performance problem but overreached into skipping TM generation — the simplest fix for throughput was not the simplest architecture for correctness.

---

## 2 — Context as engineering decision

More information is not automatically useful. Each stage receives what it needs for its bounded task, not the full pipeline state. RepoCrawler (MAX_FILES=200, dedup 0.85) and the adapter layer enforce this at ingestion.

**Gap:** Critics currently receive full pipeline context rather than a scoped view of the dimension they review. When a stage uses more context than its task requires, it becomes harder to reason about, harder to test, and slower.

---

## 3 — Deterministic over LLM where the problem is deterministic

If the answer can be computed from a lookup, a rule, or a schema, compute it. Reserve LLM calls for problems that are genuinely ambiguous.

**TA examples:** DETECT rules (65 deterministic pattern checks), MITRE technique validation in self_validation.py (lookup, not generation), Jev for routing confidence (classifier, not generation), CVSS/AIVSS scoring (formula), governance YAML enforcement (rule check). TAprover extends this furthest: ATT&CK STIX lookups are pure deterministic; no LLM is needed to verify that T1190 exists in the Enterprise catalog.

---

## 4 — Uncertainty must be visible

When the pipeline is guessing, the caller must know it is guessing. A marginal confidence score and a high-confidence score must not produce identical-looking output.

**Gap:** Brain confidence score exists internally but does not surface in the ta-export or API response. A caller receiving a brain_fast-routed output had no signal that the TM was derived from pattern retrieval rather than fresh analysis — now partially addressed by brain_annotations in the export.

**Closing:** TAprover's UNVERIFIABLE verdict is the first mechanism that explicitly names uncertainty in the output — the pipeline saying "I cannot prove this claim" rather than silently including it.

---

## 5 — Authorisation and business rules live in application code, not prompts

The agent recommends; the harness decides. Any rule that must hold under adversarial conditions must be in code, not in a prompt that an adversary can influence.

**TA examples:** BouncerStage enforces governance signals regardless of what any critic or LLM output says. PolicyBroker reads live governance signals and adjusts routing before critics run — critics cannot override it. kill_switch in agent_governance.yaml halts the pipeline; no prompt can override it.

---

## 6 — Observability and evaluation throughout execution, not just at the final output

Instrument each stage, not just the result. The gap this principle identified: evaluation covers pipeline health (did stages run correctly?) but not output correctness (is what the pipeline said true?).

**TA examples:** EventBroker publishes to SIEM/Langfuse/Webhook sinks at stage boundaries. DETECT rules evaluate inline during pipeline execution. TAgym captures Brier snapshots per iteration. TMbench provides external evaluation against an independent spec.

**Closing:** TAprover closes the remaining gap — it evaluates the claims in the output, not the execution that produced them.

---

## 7 — Classify and execute are separate layers

The classifier decides the mode; the executor acts on it. Never collapse them. The classifier has no side effects; the executor has no routing logic.

**Confirmed correct:** smart_router's select_mode() returns a RoutingDecision and nothing else.

**Confirmed violation:** _brain_fast_stream() both served as a routing outcome and smuggled TM generation logic (skip pipeline, serve patterns) into what should have been a pure execution handler. Fixed in P51 (brain_route refactor, commit d5f4139).

---

## 8 — Decompose complexity; compose strengths

When a problem is genuinely complex, break it into the smallest units where each component has a clear, bounded strength. The final deliverable emerges from composition, not from one component doing everything.

**TA examples:** AnalysisStage generates ground truth; each CriticStage reviews one dimension; each adapter handles one input format; BouncerStage enforces one class of rule; TAprover verifies one class of claim. ta-export is the composition of all bounded contributions.

**Failure mode guarded against:** the God component — a stage that analyses, routes, enforces, and reports.

---

## 9 — Adapt, recall and prioritise with purpose

Memory and priority are navigation instruments, not bookkeeping. What to remember is determined by why it matters and how it will be used, not by completeness for its own sake. Priority ordering directs the build so each item's output strengthens the next.

**TA examples:** MEMORY.md carries why alongside what. DECISIONS.md is read at session start, not archived. P-sequencing is determined by build-up dependency (P50 → P44 → P45 → P42b is load-bearing, not arbitrary — each item's output is evidence for the next blog and input to the next build). The principle audit fires before each P-item: not to block, but to surface tensions early.

**Failure mode:** accumulating notes that are never used because the connection between memory and action was never made explicit. Memory without a use-case is noise.

---

## 10 — Document raw, reflect, recircle

Write what you think even before the idea is fully formed. Return to it, reflect, and capture the essence. The document guides when it is right and can be revised when it is wrong — it is not a constraint, it is a thinking tool.

**TA examples:** TAprover was documented as a memory file and DECISIONS entry before a line of code was written. brain_route was named before the refactor was complete. The principle audit was written before it had three cases. In each instance, the raw documentation created the conditions for the design to be correct — it forced explicit reasoning that would otherwise have remained implicit and unexamined.

**Failure mode:** waiting until the idea is fully formed to write it down. By then the intermediate reasoning that would have caught errors is gone, and the written version records a conclusion without the path that produced it.

---

*Last updated: 2026-11-09. For the decision history behind these principles, see DECISIONS.md Entry 251.*
