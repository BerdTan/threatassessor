---
name: tatb-score
description: Run TATB (TA Test Benchmark) on a single architecture and print the four-rubric scorecard — Threat-Relevant, TTP-Accurate, Risk-Defensible, Plan-Actionable. Uses the same scoring logic as the dashboard TATB tab. Pass an architecture name as argument, or omit for the most recent report. Read-only. ~3 seconds (includes MITRE API fetch).
allowed-tools: Bash(python3:*) Bash(source:*)
---

# TATB Score — Single Architecture

Scores one architecture across all four TATB rubrics and prints a detailed breakdown with sub-signals, evidence, and stage attribution. Identical logic to the dashboard TATB tab.

## Run

```bash
# Most recent report
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate && python3 .claude/skills/tatb-score/scripts/tatb-score.py

# Named architecture
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate && python3 .claude/skills/tatb-score/scripts/tatb-score.py 01_minimal_vulnerable_2

# JSON output (for piping or agent consumption)
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate && python3 .claude/skills/tatb-score/scripts/tatb-score.py 01_minimal_vulnerable_2 --json
```

## What it shows

| Section | Contents |
|---------|----------|
| Overall | Weighted average, rating band (Excellent/Solid/Weak/Draft), data availability |
| Threat-Relevant | Node binding %, node coverage %, technique variety %, generic-fallback flag |
| TTP-Accurate | Validation depth (CONFIRMED/PLAUSIBLE/FAILED), MITRE alignment %, cross-critic %, MoE lift |
| Risk-Defensible | Technique mitigation coverage, hop layer completeness, residual exposure (MONITOR/MITIGATE count) |
| Plan-Actionable | Item completeness, measurable outcomes, sprint spreadability, control specificity, AP closure |
| Stage attribution | Which pipeline stages to investigate for each low-scoring signal |

## Failure fixes

| Error | Fix |
|-------|-----|
| `ground_truth.json not found` | Run analysis first from dashboard or CLI |
| MITRE fetch fails (alignment shows 50%) | API server must be running: `./scripts/api/api_start.sh` |
| Plan shows N/A | No ScrumMaster data — run `full_moe` scenario from dashboard Expert Review |
| Risk hop_pct = 50% (neutral) | No ADRs with hop data — run `full_moe` to generate ADRs |

## Notes

- **MITRE alignment** requires the API server (`localhost:8000`) to be running — it fetches `/api/v1/technique-mitigations`. Falls back to 50% neutral if unavailable.
- **Plan-Actionable** requires `08_scrum_master.json` — only present after full_moe run.
- Scores are **not** written back to disk — this is a read-only diagnostic tool.

## Feedback loop

Low scores point directly to pipeline stages:

| Signal | Stage | What to fix |
|--------|-------|-------------|
| node_binding < 80% | AnalysisStage → ground_truth_generator | Entry-node extraction; check parsed_nodes key names |
| tech_variety < 60% | AnalysisStage → RAPIDS + path-finding | Expand keyword lists or hop depth |
| val_pct < 70% | QualityStage → self_validation | Heuristic thresholds too permissive |
| mitre_pct < 70% | ReportStage → exhaustive_mitigation_mapper | Missing M-ID mappings for some techniques |
| hop_pct < 60% | ReportStage → ADR generator | dir_category assignment not covering all four layers |
| closure_pct < 80% | ScrumMasterStage → SM prompt | SM not referencing AP-IDs in action items |

## Related skills

- `/tatb-corpus` — score all architectures at once and show corpus-wide patterns
- `/aivss-score` — AIVSS-specific deep-dive
- `/quick-test` — integration sanity check
