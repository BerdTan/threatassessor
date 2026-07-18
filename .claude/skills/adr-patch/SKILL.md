---
name: adr-patch
description: Collect "add to ADR" signals from all ER sources (SM action plan, KNOWN cross-expert findings, expert gaps, resolved UNSURE items) and write structured hop-level control entries into 10_adr_report.md. Idempotent — re-running never duplicates. Use after any ER run or after /review-unsure resolves REAL findings.
allowed-tools: Bash(python3:*) Bash(source:*)
compatibility: Requires 07_moe_orchestrator.json and 10_adr_report.md for the target architecture. Run /run-er first if missing.
---

# adr-patch — ADR Signal Collector + Patcher

After an ER run, several sources contain "add to ADR" instructions scattered across:
- SM action_plan immediate items (e.g. "Apply T1083 at WebUI — add to the architecture ADR")
- KNOWN cross-expert findings (multi-critic corroborated gaps)
- Expert gaps at CRITICAL/HIGH with a specific node + technique + clean control recommendation
- REAL verdicts from `/review-unsure` resolved items

This skill collects all of them, deduplicates by (technique, node), and writes structured
hop-level control entries into `10_adr_report.md` — in the right ADR, inside the right
`#### \`NodeName\`` section.

## Run

```bash
# Patch all sources (default)
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate \
  && python3 .claude/skills/adr-patch/scripts/adr-patch.py 21_agentic_ai_system

# Preview without writing
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate \
  && python3 .claude/skills/adr-patch/scripts/adr-patch.py 21_agentic_ai_system --dry-run

# Only SM action_plan signals
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate \
  && python3 .claude/skills/adr-patch/scripts/adr-patch.py 21_agentic_ai_system --source sm

# Only KNOWN consensus findings
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate \
  && python3 .claude/skills/adr-patch/scripts/adr-patch.py 21_agentic_ai_system --source known

# Most recent report (no arch argument)
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate \
  && python3 .claude/skills/adr-patch/scripts/adr-patch.py
```

## What it patches

Each signal becomes a hop-level entry inside the relevant `#### \`NodeName\`` section:

```markdown
**file integrity monitoring** [CRITICAL] — Detect  _(added via /adr-patch · source: gap purple_team)_
> T1083 at WebUI across AP-1, AP-2, AP-4
> Deploy file integrity monitoring (FIM) on WebUI to detect unauthorized directory traversal.
> Risk: unmitigated → partially mitigated (T1083 coverage gap addressed)
```

Entries are placed just before the hop section ends (before the next `####` or `_Next step_`).

## Signal sources and filters

| Source | `--source` flag | What it includes |
|---|---|---|
| SM `action_plan` immediate | `sm` | Non-structural items where `first_step` mentions "add to the architecture ADR" |
| KNOWN consensus findings | `known` | Multi-critic corroborated gaps with a specific node + clean control name in recommendation |
| Expert gaps CRITICAL/HIGH | `gaps` | Single-critic gaps with exactly one primary node + technique + actionable control name |
| Resolved REAL from /review-unsure | `resolved` | Items in `consensus_recommendations.resolved[]` with `verdict=REAL` |

**Deduplication:** If multiple sources name the same (technique, node), only the highest-severity signal is kept.

**Idempotency:** If a control name + "added via /adr-patch" already exists in the hop section, that signal is skipped.

## Output example

```
  ADR Patch — 21_agentic_ai_system
  all sources
  ─────────────────────────────────────

  11 signals collected:

  CRI  T1083  WebUI  APs: AP-1, AP-2, AP-4
     control:  file integrity monitoring
     source:   gap_purple_team

  CRI  T1083  AgentOrchestrator  APs: AP-1, AP-2
     control:  HIDS
     source:   gap_purple_team

  …

  ✓ 24 insertion(s) written to 10_adr_report.md

  Next steps:
  1. Review 10_adr_report.md — search 'added via /adr-patch' to find new entries
  2. Assign owners and target sprint in each patched hop section
  3. Re-run /tatb-score to check Plan-Actionable improvement
  4. Re-run /run-er when controls are implemented to close the ER loop
```

## Prerequisites

1. `07_moe_orchestrator.json` exists (run /run-er first)
2. `10_adr_report.md` exists (run analysis + regen-reports if missing)
3. For SM signals: `08_scrum_master.json` exists (run /run-er --full)

## Workflow integration

```
/run-er <arch> --full
    ↓
/review-unsure <arch>        ← clears UNSURE queue, marks REAL items
    ↓
/adr-patch <arch>            ← writes all REAL + KNOWN + SM signals into ADRs
    ↓
/tatb-score <arch>           ← verify Plan-Actionable improved
```

## Related skills

- `/review-unsure` — triage UNSURE items before patching (REAL verdicts feed into /adr-patch)
- `/run-er` — re-run critics after ADR changes are implemented
- `/tatb-score` — verify Plan-Actionable score after patching
- `/regen-reports` — regenerate all report files from updated ground_truth
