---
name: summarise-er
description: One-page ER digest — confidence waterfall, per-critic verdict + top 2 findings, cross-expert consensus, UNSURE queue status. No LLM calls. Use after any ER run to get a scannable executive view of what each critic found and what needs action.
allowed-tools: Bash(python3:*) Bash(source:*)
compatibility: Requires 07_moe_orchestrator.json for the target architecture. Run /run-er first.
---

# summarise-er — Expert Review Digest

Prints a one-page summary of an ER run: who found what, how bad, and what to do next.
Draws from `07_moe_orchestrator.json` (pre-synthesised by MoE). No LLM calls — instant.

## Run

```bash
# Most recent report
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate \
  && python3 .claude/skills/summarise-er/scripts/summarise-er.py

# Named architecture
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate \
  && python3 .claude/skills/summarise-er/scripts/summarise-er.py 21_agentic_ai_system

# JSON output (for scripting or post-processing)
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate \
  && python3 .claude/skills/summarise-er/scripts/summarise-er.py 21_agentic_ai_system --json
```

## Output sections

```
  ER Summary — 21_agentic_ai_system
  NEEDS REVIEW - Significant gaps found

  Confidence waterfall
  Base 73.6%  →  Architect -5.0%  →  Tester -1.0%  →  Red Team -10.0%  →  ...  →  Final 56.8%
  ███████████░░░░░░░░░

  Per-critic verdicts
  🏛 Architect     72/100  MINOR GAPS  -5.0%
    → after.mmd contains only 22 NEW_* nodes but 37 controls were recommended.
    ▪ HIGH   after.mmd missing 15 controls (40% gap)
        → Add missing controls with NEW_* node naming convention
    ▪ MEDIUM Attack paths missing AI-specific threats like prompt injection
        → Develop AI-specific attack paths targeting VectorDB, AgentOrchestrator

  🔬 Tester        82/100  MINOR GAPS  -1.0%
    → Checked 25 technique-mitigation pairs across 11 controls.
    ...

  Cross-expert consensus  (8 critical · 7 high · 3 UNSURE)
  ▪ CRITICAL  [purple_team]  T1083 unmapped in WebUI, AgentOrchestrator, ToolRegistry...
  ▪ CRITICAL  [blackhat+red_team]  WebUI pivot T1190 — 14 targets without WAF coverage
  ...
  3 UNSURE items need review — run /review-unsure 21_agentic_ai_system

  ─────────────────────────────────────
  ACTION REQUIRED
  30 findings total · 16 critical/high · 15 multi-critic KNOWN
  3 UNSURE → run /review-unsure · 2 already resolved
```

## Verdict synthesis

The "Critic verdict" line is synthesised deterministically:
- If `expert_validations[critic].reasoning` is non-empty: use it (capped at 2 sentences for PT/BH)
- Otherwise: find the breakdown dimension with most points lost, extract its first sentence
- Final fallback: first sentence of the top CRITICAL/HIGH gap description

This matches the "Critic verdict" block shown in the ER tab of the dashboard.

## Prerequisites

1. `07_moe_orchestrator.json` exists (run `/run-er` first)
2. No API key or network access needed

## Related skills

- `/run-er` — run Expert Review to generate the ER data
- `/review-unsure` — triage UNSURE items flagged in the Cross-Expert Findings section
- `/adr-patch` — write ADR entries for KNOWN and SM findings
- `/tatb-score` — check TATB rubric scores
