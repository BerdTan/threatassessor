# model-audit — Model Trust Surface Audit

Engine Item 14. Audit the model trust surface: config integrity, routing staleness,
critic role validation, endogenous output scan (DETECT-QC-009), and provider config.
No API required — all checks read source files and config only.

## Run

```bash
python3 .claude/skills/model-audit/scripts/model-audit.py
```

## What it checks

| Dim | Name | What |
|---|---|---|
| DIM-1 | Config integrity | AGENT_MODEL_* env vars vs model_routing.yaml tested_models; exclusion registry |
| DIM-2 | Routing config staleness | model_routing.yaml mtime vs newest bench_summary.json |
| DIM-3 | Critic role validation | Excluded/blackhat-silence models not in active routing; all critic roles in guardian |
| DIM-4 | Endogenous output scan | SM synthesis_note/action_plan scanned for constraint-override language (DETECT-QC-009) |
| DIM-5 | Provider config audit | LLM_PROVIDER vs documented providers in .env.example |
| DIM-6 | HarnessModelGuardian wiring | Guardian in ctx; no direct os.getenv("AGENT_MODEL_*") in stages.py |

## Attack vectors covered

| Vector | Dim |
|---|---|
| Model substitution (MITM swaps endpoint) | DIM-5, DIM-6 |
| Routing config tampering (model_routing.yaml modified to demote critic) | DIM-2 |
| Excluded model bypass (env-var overrides exclusion registry) | DIM-1, DIM-3 |
| Endogenous constraint injection (model embeds override directives in SM output) | DIM-4 |
| Critic role confusion (generic assistant routed to blackhat — silent analysis) | DIM-3 |
| Direct env-var read bypassing guardian exclusion chain | DIM-6 |

## Exit codes

| Code | Meaning |
|---|---|
| 0 | No CRITICAL or HIGH findings |
| 1 | One or more CRITICAL/HIGH findings |
| 2 | Cannot parse input files |

## DETECT-QC-009 promotion path

DIM-4 scans existing SM output on disk for `sm_constraint_evasion_language` patterns.
The MEDIUM finding persists until DETECT-QC-009 is added to `policies/soc_detection_rules.yaml`
and wired into `rule_evaluator.py`. Promotion steps:

1. Add rule `DETECT-QC-009` to `policies/soc_detection_rules.yaml` (domain: QC)
2. Add a `sm_constraint_evasion_language` signal field to `RuleEvaluator`
3. Wire SM verdict text into the evaluator after `ScrumMasterStage`
4. Add test scenario to `tests/test_detect_rules.py`

## Relationship to other checks

- **HarnessModelGuardian** — runtime model routing validator; model-audit audits the *config layer* the guardian reads, not the guardian itself
- **mcp-audit** — audits MCP tool parameter surface; model-audit audits the model identity layer
- **aisurface-audit** — enumerates all ingest surfaces; model-audit drills into the model trust layer

## Findings — Engine Item 14 first run (2026-09-20)

Result: 0 critical, 0 high, 4 medium, 2 low, 11 info. Exit 0.

| Dim | Finding | Severity | Notes |
|---|---|---|---|
| DIM-1 | AGENT_MODEL_TATB_LABELLER not in tested_models | MEDIUM | Brain labeller — intentionally separate from critic routing registry |
| DIM-1 | AGENT_MODEL_TATB_LABELLER_FALLBACK not in tested_models | MEDIUM | Same — brain path |
| DIM-2 | model_routing.yaml 3d older than newest bench | MEDIUM | Bench 2026-09-12; routing updated 2026-09-08 |
| DIM-4 | DETECT-QC-009 not yet in soc_detection_rules.yaml | MEDIUM | Promotion item — next sprint |
| DIM-3 | hetzner_27b confirmed but not in any routing slot | LOW | Safe — consider as fallback |
| DIM-4 | No SM output files to scan | LOW | Run full_moe pipeline to generate SM output |
