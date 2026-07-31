---
name: aivss-to-findings
description: Convert governance_signals.json + AIVSS output into OCSF SecurityFinding 2001 events (confirmed/suspicious/anomalous). Pass an architecture name, a path to governance_signals.json, or omit for all corpus architectures. Writes OCSF JSON and prints a summary table. Read-only on governance_signals; output written to report/<arch>/ocsf_findings.json.
allowed-tools: Bash(python3:*) Bash(source:*)
---

# AIVSS → OCSF SecurityFinding Exporter

Converts TA governance signals into OCSF v1.1 `SecurityFinding` (class_uid 2001) events
for ingest into any OCSF-compatible SIEM (Splunk, AWS Security Hub, Panther, Chronicle).

**OCSF version:** 1.1 (stable; migrate to 1.2 when `AIActivity` class coverage matures)

## Run

```bash
# All corpus architectures
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate && \
  python3 .claude/skills/aivss-to-findings/scripts/aivss_to_findings.py

# Single architecture
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate && \
  python3 .claude/skills/aivss-to-findings/scripts/aivss_to_findings.py 10_complex_enterprise

# From a specific governance_signals.json path
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate && \
  python3 .claude/skills/aivss-to-findings/scripts/aivss_to_findings.py --file /path/to/governance_signals.json
```

## Classification thresholds (AIVSS 0–10 scale)

These are the canonical thresholds. Update here when AIVSS scoring changes — nowhere else.

| Status | AIVSS Condition | Governance Condition |
|--------|----------------|----------------------|
| **confirmed** | overall composite ≥ 7.0 | no governance block |
| **suspicious** | composite 4.0–7.0 OR manipulation severity MEDIUM+ OR leakage detected | any soft governance signal |
| **anomalous** | composite < 4.0 with any per-threat CRITICAL OR governance block (injection CRITICAL or manipulation CRITICAL) | hard block |

## Output

Each `ocsf_findings.json` is a list of OCSF SecurityFinding 2001 objects:

```json
{
  "class_uid": 2001,
  "class_name": "Security Finding",
  "ocsf_version": "1.1",
  "time": 1722384000,
  "severity_id": 3,
  "severity": "High",
  "status": "suspicious",
  "finding": { "uid": "ta-<run_id>-internal", "title": "AIVSS Internal Flow", "desc": "..." },
  "resources": [{ "name": "<arch_name>", "type": "architecture_diagram" }],
  "metadata": { "product": "ThreatAssessor", "version": "1.4", "profiles": ["security_control"] },
  "unmapped": { "aivss_composite": 6.25, "manipulation_severity": "MEDIUM", ... }
}
```

## What it prints

```
Architecture              | Confirmed | Suspicious | Anomalous | Findings written
--------------------------|-----------|------------|-----------|------------------
10_complex_enterprise     |         0 |          2 |         0 | report/.../ocsf_findings.json
21_agentic_ai_system      |         0 |          2 |         0 | ...
```

## Failure fixes

| Error | Fix |
|-------|-----|
| `governance_signals.json not found` | Run `/backfill-aivss <arch_name>` first |
| All findings show anomalous | Check that AIVSS scoring ran — composites near 0.0 indicate missing signals |
| Output path permission error | Ensure `report/<arch>/` directory exists (created by analysis pipeline) |

## Related skills

- `/aivss-score` — recompute AIVSS scores from disk
- `/backfill-aivss` — generate governance_signals.json for existing reports
- `/check-governance` — run governance guardrail regression suite
- `/aivss-gate` — show gate thresholds and last SIEM event
