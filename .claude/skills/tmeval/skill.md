---
name: tmeval
description: Adversarial red-team probe of the TA pipeline. Phase 2 (inside-out, no API) injects crafted governance_signals directly into RuleEvaluator + BouncerStage — 21 cases across 3 threat-actor entry points. Phase 1 (outside-in, API required) POSTs 8 adversarial MMDs to the live REST endpoint and asserts governance_signals match expected DETECT rules. Use after any change to rule_evaluator.py, governance.py, BouncerStage, or the adversarial MMD corpus.
allowed-tools: Bash(python3:*) Bash(source:*)
---

# tmeval — ThreatAssessor Adversarial Red-Team Harness

Two-phase adversarial probe: outside-in (live REST) and inside-out (direct
signal injection). The inside-out phase runs without the API and covers the
majority of injection cases; the outside-in phase validates the full pipeline
path end-to-end.

## Phases

### Phase 2 — inside-out (no API needed)
Injects crafted `governance_signals` directly into `RuleEvaluator` and
`BouncerStage`. Covers 21 injection cases across three threat-actor entry
points:

| Entry point | Threat actor | Cases |
|-------------|-------------|-------|
| `qa` | Internal QA reviewer submitting crafted diagrams | 7 |
| `external` / `assumed_breach` | External attacker or compromised upstream | 7 |
| `insider` | Privileged insider with direct signal write access | 7 |

Each case asserts the correct rule fires (or Bouncer blocks) and that no false
positive fires on the clean baseline.

### Phase 1 — outside-in (API required)
POSTs 8 adversarial MMDs from `scripts/tmeval/adversarial_corpus/` to the live
`/analyze-stream` endpoint and asserts `governance_signals` in the SSE
`complete` event contain the expected DETECT rule hits.

| MMD | Domain | Expected rules |
|-----|--------|---------------|
| `agt_permission_escalation.mmd` | AGT | DETECT-AGT-001/002 |
| `agt_tool_bypass.mmd` | AGT | DETECT-AGT-003 |
| `exf_c2_beacon.mmd` | EXF | DETECT-EXF-* |
| `exf_credential_exposure.mmd` | EXF | DETECT-EXF-* |
| `inj_encoding_evasion.mmd` | INJ | DETECT-INJ-* |
| `inj_external_url.mmd` | INJ | DETECT-INJ-001 |
| `inj_path_traversal.mmd` | INJ | DETECT-INJ-002 |
| `clean_baseline.mmd` | — | no rules (false-positive check) |

## Run

```bash
# Phase 2 only — inside-out injection (no API, ~5s)
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate \
  && python3 scripts/tmeval/tmeval_run.py --phase2

# Phase 1 only — outside-in REST probe (API must be running)
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate \
  && python3 scripts/tmeval/tmeval_run.py --phase1 --api-url http://localhost:8000

# Both phases
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate \
  && python3 scripts/tmeval/tmeval_run.py --all --api-url http://localhost:8000

# Phase 1 dry-run — validate case YAML + MMD corpus, no API calls
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate \
  && python3 scripts/tmeval/tmeval_run.py --phase1 --dry-run
```

## Output

```
Phase 2 — inside-out injection
  qa/encoded_payload          ✓  DETECT-INJ-005 fired
  qa/governance_signal_spoof  ✓  Bouncer blocked
  ...
  insider/direct_signal_write ✓  DETECT-QC-009 fired

Domain coverage (cases passing vs domain total rules):
  AGT    ██████  6/6
  INJ    ████    4/5
  QC     ███     3/4

Phase 2: 21/21 PASS

Phase 1 — outside-in REST probe
  agt_permission_escalation  ✓  AGT-001 AGT-002
  clean_baseline             ✓  (no rules — clean)
  ...

Phase 1: 8/8 PASS

Overall: 29/29 PASS
```

Failed cases name the missing rules. Any case that fails but has an adversarial
MMD writes a synthetic queue entry to
`report/brain/synthetic_queue/` for brain ingest after the pipeline gap is fixed.

Exit 0 = all pass. Exit 1 = any failure.

## When to use

- After any change to `chatbot/harness/rule_evaluator.py`
- After any change to `chatbot/harness/governance.py` (new signals or merge logic)
- After any change to `chatbot/harness/stages.py` (BouncerStage checks)
- After promoting a new DETECT rule — verify it fires on the relevant injection cases
- After the `arch_metadata` merge bug class of fix — confirm AGT rules are live
- Before committing adversarial corpus changes in `scripts/tmeval/`
- As a CI gate alongside `/check-detect` and `/check-governance`

## Adding cases

**Phase 2:** add an entry to `scripts/tmeval/cases/phase2_cases.yaml` with
`entry_point`, `name`, `signals` (the injected `governance_signals` dict), and
`expect` (list of rule IDs that must fire, or `blocked: true` for Bouncer).

**Phase 1:** add an MMD to `scripts/tmeval/adversarial_corpus/` and a
corresponding entry to `scripts/tmeval/cases/phase1_cases.yaml` with the
expected `rules` list.
