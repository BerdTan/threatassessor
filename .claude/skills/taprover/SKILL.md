---
name: taprover
description: "TAprover — independent, deterministic verifier of threat-model claims against ATT&CK STIX. Slice 1: technique_grounding + tactic_correctness. Emits a ProofAttestation (VERIFIED/UNVERIFIABLE/REFUTED per claim). Exit 1 on any REFUTED. Entry 249."
allowed-tools: Bash(python3:*)
---

# taprover

Proves correctness, where `tmbench-check` scores quality. Reads only the TM JSON and the ATT&CK STIX bundle;
imports nothing from `chatbot/` (independence invariant). No LLM, no network.

```bash
cd "$(git rev-parse --show-toplevel)"
python3 .claude/skills/taprover/scripts/taprover.py --prove <tm.json>        # threatmodel/0.1 or ta-export/1.0
python3 .claude/skills/taprover/scripts/taprover.py --prove-dir docs/tmbench/results/ --summary
python3 .claude/skills/taprover/scripts/taprover.py --prove <tm.json> --refuted-only --out att.json
```

- Scope follows spec §2: Enterprise (STIX), ICS (STIX `chatbot/data/ics-attack.json`), ATLAS (YAML `chatbot/data/atlas/`). A technique ID that exists in none of them is REFUTED; `--lenient` makes it UNVERIFIABLE.
- A domain whose catalog file is missing makes its IDs UNVERIFIABLE (`catalog_not_loaded`), never REFUTED. ICS is not identified by ID shape: ATT&CK is moving ICS techniques into `T1xxx` (e.g. `T0855` -> `T1692.001`), so a bare T-ID is only refuted when both Enterprise and ICS are loaded.
- Revoked/deprecated IDs are REFUTED and the evidence names the replacement ID when ATT&CK records one.
- Tactics are checked against the technique's own domain. Old ATLAS "ML ..." tactic names are accepted as the renamed "AI ..." tactics.
- Fetch ICS: `curl -o chatbot/data/ics-attack.json https://raw.githubusercontent.com/mitre-attack/attack-stix-data/master/ics-attack/ics-attack.json` (gitignored like the Enterprise bundle).
- An empty `technique_id` is UNVERIFIABLE (`reason: no_claim`), not REFUTED: an unmade claim cannot be false. `tmbench-check` scores the absence.
- Every claim carries a machine-readable `reason`.
- ta-export carries no tactic, so only `technique_grounding` runs there; tactic claims come from threatmodel/0.1.
- Attestation carries `run_id`, `arch`, `model_id`, `routing_mode` and input/evidence hashes so k-run pass^k aggregation can be layered on later.

Logic checks (Entry 262): `agentic_trigger_parity` (declared agentic/AI architecture must cite a verified ATLAS technique; REFUTED if not), `coverage` (every path cites a technique, all in the architecture-level list), `mitigation_validity` / `mitigation_coverage` (MITRE M-IDs exist and are current; addressed techniques are in the model).
Repeated runs: `--aggregate` groups attestations by architecture and prints pass@k (any run passes) and pass^k (all runs pass). A run passes when it has no REFUTED claim. Use pass^k for CI gates and public claims.
Later slices (Entry 249): cvss_validity, control_existence.

## Doc claims (Entry 266)
TAprover also checks a document's claim about pipeline stage order, e.g. "the Bouncer halts the pipeline before any LLM runs". The pipeline side only exports data; the verifier never imports it.
```bash
PYTHONPATH=. .venv/bin/python scripts/validation/export_stage_manifest.py report/stage_manifest.json
python3 .claude/skills/taprover/scripts/taprover.py --prove-docs report/stage_manifest.json \
  --docs README.md docs/ARCHITECTURE.md docs/HARNESS.md chatbot/harness/controller.py chatbot/harness/stages.py
```
REFUTED if any stage runs ahead of the Bouncer (every earlier stage counts as able to spend). UNVERIFIABLE if the manifest has no Bouncer. Output reports `checked=N`; `checked=0` means no claim was found, not that the docs are proven.

## Catalog drift (Entry 261)
The pipeline is pinned to `chatbot/data/enterprise-attack.json`; the latest ATT&CK bundle lives in `chatbot/data/attack_latest/` (gitignored). To prove against latest and separate catalog age from model error:
```bash
python3 .claude/skills/taprover/scripts/taprover.py --prove-dir docs/tmbench/corpus \
  --stix chatbot/data/attack_latest/enterprise-attack.json --ics chatbot/data/attack_latest/ics-attack.json \
  --baseline-stix chatbot/data/enterprise-attack.json --summary
```
Claims the pinned catalog accepts but latest refutes are `DRIFT`; they do not fail the exit code.
