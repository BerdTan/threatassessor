---
name: regen-reports
description: Regenerate the markdown and diagram report files for one or all corpus architectures from their existing ground_truth.json and MoE JSON files, without re-running the analysis engine or Expert Review. Use after code changes to threat_report.py, improvement_summary_generator.py, executive_dashboard_generator.py, adr_generator.py, or narrative_enricher.py to keep all report files current. Also supports regenerating only specific report layers (md-only, dashboard-only, improvement-only).
allowed-tools: Bash(python3:*) Bash(source:*)
---

# regen-reports — Report File Regeneration

Regenerates report `.md` and `.mmd` files from existing JSON data (ground_truth.json + MoE/SM JSON files).
No engine re-run, no LLM calls, no Expert Review required.

Use this after changes to any report generator module to propagate the fix across the full corpus.

## Run

```bash
# Regenerate all report files for one architecture (MD + diagrams + dashboard + improvement)
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate \
  && python3 .claude/skills/regen-reports/scripts/regen-reports.py 21_agentic_ai_system

# Regenerate all 26 corpus architectures
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate \
  && python3 .claude/skills/regen-reports/scripts/regen-reports.py --all

# Regenerate only the markdown reports (01-03, 09, 10) — fastest
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate \
  && python3 .claude/skills/regen-reports/scripts/regen-reports.py 21_agentic_ai_system --md-only

# Regenerate only 00_executive_dashboard.md (requires 07_moe_orchestrator.json)
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate \
  && python3 .claude/skills/regen-reports/scripts/regen-reports.py 21_agentic_ai_system --dashboard-only

# Regenerate only 08_improvement_summary.md (requires 07_moe_orchestrator.json)
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate \
  && python3 .claude/skills/regen-reports/scripts/regen-reports.py 21_agentic_ai_system --improvement-only

# Dry-run: show what would be regenerated without writing files
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate \
  && python3 .claude/skills/regen-reports/scripts/regen-reports.py --all --dry-run
```

## What gets regenerated

| Layer | Files | Requires | When to use |
|-------|-------|----------|-------------|
| **MD reports** | `01_executive_summary.md`, `02_technical_report.md`, `03_action_plan.md`, `09_threat_model.md`, `10_adr_report.md` | `ground_truth.json` | After changes to threat_report.py |
| **Diagrams** | `before.mmd`, `after.mmd`, `threatmodel_adr.mmd`, `threatmodel_adr_bh.mmd` | `ground_truth.json` | After changes to diagram generators |
| **Dashboard** | `00_executive_dashboard.md` | `07_moe_orchestrator.json` | After changes to executive_dashboard_generator.py |
| **Improvement** | `08_improvement_summary.md`, `08a/b/c_*.mmd` | `07_moe_orchestrator.json` | After changes to improvement_summary_generator.py |

Layers without their required JSON files are silently skipped with a note in the output.

## Output format

```
Regen Reports — 21_agentic_ai_system

  ✓  01_executive_summary.md
  ✓  02_technical_report.md
  ✓  03_action_plan.md
  ✓  09_threat_model.md
  ✓  10_adr_report.md
  ✓  before.mmd
  ✓  after.mmd
  ✓  threatmodel_adr.mmd
  ✓  00_executive_dashboard.md  [requires 07_moe_orchestrator.json]
  ✓  08_improvement_summary.md  [requires 07_moe_orchestrator.json]
  –  08a_quick_wins.mmd          [skipped — no improvement_options in MoE data]

  Done: 10 regenerated · 1 skipped · 0 failed  (2.4s)
```

## When to run

- After any change to `chatbot/modules/threat_report.py`
- After any change to `chatbot/modules/improvement_summary_generator.py`
- After any change to `chatbot/modules/executive_dashboard_generator.py`
- After any change to `chatbot/modules/adr_generator.py` or `narrative_enricher.py`
- After upgrading ATLAS or MITRE data (technique names/descriptions change)
- Before sharing or reviewing a report that may be stale

## Notes

- Does NOT re-run the analysis engine or Expert Review — existing JSON data is the source of truth
- For each architecture, the script loads `ground_truth.json` and any present MoE/SM JSON files
- Architectures missing `ground_truth.json` are skipped
- `--all` processes all directories under `report/` with a `ground_truth.json`
- Takes ~2–5 seconds per architecture (pure Python, no LLM calls)

## Related skills

- `/rerun-corpus` — re-run the deterministic analysis engine (rewrites ground_truth.json)
- `/run-er` — run Expert Review to update MoE/SM JSON files
- `/tatb-score` — verify TATB scores after regenerating reports
