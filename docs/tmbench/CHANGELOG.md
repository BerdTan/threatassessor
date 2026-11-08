# TMbench Spec Changelog

## v0.1.1 — 2026-11-08

Clarification patches only. No scoring logic changes; all existing scores remain valid.

### §1.4 Mitigations — `control_id` made optional
- **Before:** `control_id` listed as required with no fallback.
- **After:** `control_id` is optional when no standard control ID applies. `control_name` alone is sufficient in that case.
- **Rationale:** Tools using free-text mitigation names were flagged as gaps despite providing valid, meaningful mitigations. The intent of the field is control traceability, not mandatory framework citation.
- **Score impact:** None. The completeness bonus was already absorbing this correctly; removing the false positive reduces noise in `--spec-review` output (19 gap instances removed across 73 scored runs).

### §1.6 Governance Signals — agentic trigger definition tightened
- **Before:** "architectures with autonomous agents, LLM-driven components, or tool-calling pipelines" — no explicit component role list.
- **After:** Explicit trigger role list added: `agent`, `llm`, `tool_caller`, `ai`, `ml`, `language_model`, `orchestrator`. The `is_agentic: true` flag in `architecture_summary` also triggers the requirement.
- **Rationale:** External submitters could not reliably determine which of their architectures triggered the agentic governance block. The scorer was already using the role list internally; the spec now matches it.
- **Score impact:** None. Scorer behaviour unchanged.

### §1.6 Governance Signals — agentic field worked example added
- **Before:** `agent_autonomy_level`, `blast_radius`, `human_oversight_points`, `model_provenance` defined with brief descriptions only.
- **After:** Explicit value guidance for each field plus a JSON worked example for an agent fleet architecture.
- **Rationale:** Spec review showed 4 instances per field of these being absent in external tool submissions. Without worked examples, submitters have insufficient guidance on what constitutes a valid value (e.g. `blast_radius: "data"` vs a specific description of scope).
- **Score impact:** None for existing submissions. Future submitters with this guidance will score higher on the agentic bonus.

---

## v0.1.0 — 2026-11-01

Initial release. 10 reference architectures across 4 tiers (T1–T4). TATB rubric, max 13 with ATLAS bonus. Leaderboard at `docs/tmbench/results/`.
