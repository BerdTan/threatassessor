---
name: aivss-gate
description: Show per-critic AIVSS gate config, per-agent model assignments (HarnessModelGuardian), and last SIEM event summary. Use to verify gate thresholds are set, check which agents have custom models configured, and inspect the most recent inbound/internal/outbound scores. Read-only — no side effects.
allowed-tools: Bash(python3:*) Bash(source:*)
---

# AIVSS Gate Inspector

Prints three sections in sequence: the per-critic gate table, the per-agent model config, and the last SIEM event. No API calls, no file writes.

## Run

```bash
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate && python3 .claude/skills/aivss-gate/scripts/aivss-gate.py
```

## What it shows

| Section | What you see |
|---------|-------------|
| Per-Critic Gate Config | Critic name, allowed models, allowed tools, AIVSS gate threshold (10.0 = disabled; lower = active) |
| Per-Agent Model Config | Each swarm agent, its configured primary model + fallbacks, or "env-var default" if not set |
| Last SIEM Event | Architecture, timestamp, run_id, inbound/internal/outbound composites, overall severity, top threat, governance dim severities D1–D5 |

## Failure fixes

| Error | Fix |
|-------|-----|
| `settings` import fails | Ensure `.venv` is activated; run `/quick-test` to verify deps |
| `No SIEM log found` | No pipeline run yet, or `governance.save_signals_per_run` is False in settings |
| Gate threshold shows 10.0 for all critics | No per-critic gate configured — add a `critics` block to `chatbot/config/user_config.json` |
| Per-agent models all show "env-var default" | No `agent_models` block in `user_config.json` — configure via Harness tab → Harness Config |

## When to use

- After a pipeline run to confirm governance signals were scored
- When diagnosing "why did critic X get blocked?" — check gate threshold vs last inbound score
- To verify `HarnessModelGuardian` is routing the right models to each agent
- Before a demo — confirm AIVSS and model config is as expected

## Related skills

- `/aivss-score` — recompute AIVSS scores fresh from a report directory
- `/backfill-aivss` — generate governance_signals.json for all past reports missing it
- `/quick-test` — broader integration sanity check
