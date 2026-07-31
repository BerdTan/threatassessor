---
name: langfuse-to-ocsf
description: Fetch ThreatAssessor pipeline traces from Langfuse and export them as OCSF v1.1 events (ProcessActivity 1007, APIActivity 6003, SecurityFinding 2001, DetectionFinding 2004). Writes ocsf_export.json to the current directory or a specified path. Requires LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY env vars. Pass --trace-id for a single trace, --arch for all traces matching an architecture name, --since for a time window, or omit for the last 50 traces.
allowed-tools: Bash(python3:*) Bash(source:*)
---

# Langfuse → OCSF Exporter

Reads ThreatAssessor pipeline traces from the Langfuse API and converts each
observation hierarchy into OCSF v1.1 events for SIEM ingest.

**OCSF version:** 1.1 (stable; migrate to 1.2 when `AIActivity` class coverage matures — note in this file when that happens)
**Langfuse SDK:** 4.x (tested 4.14.0; re-test on major version bumps)

## Class mapping

| Langfuse concept | OCSF class | class_uid | Key fields |
|-----------------|------------|-----------|------------|
| Trace (pipeline run) | ProcessActivity | 1007 | arch name, duration, confidence |
| Generation (LLM call) | APIActivity | 6003 | model, tokens, cost, provider, latency |
| Span (critic/stage run) | ProcessActivity | 1007 | critic role, score, rating, gaps |
| Score (AIVSS inbound/internal/outbound) | SecurityFinding | 2001 | severity from score value tier |
| Governance metadata (D1-D5 on trace) | DetectionFinding | 2004 | category = dimension name |

## Run

```bash
# Last 50 traces
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate && \
  python3 .claude/skills/langfuse-to-ocsf/scripts/langfuse_to_ocsf.py

# Single trace by ID
python3 .claude/skills/langfuse-to-ocsf/scripts/langfuse_to_ocsf.py --trace-id <id>

# All traces for a specific architecture
python3 .claude/skills/langfuse-to-ocsf/scripts/langfuse_to_ocsf.py --arch 10_complex_enterprise

# Time window (ISO 8601)
python3 .claude/skills/langfuse-to-ocsf/scripts/langfuse_to_ocsf.py --since 2026-07-31T00:00:00Z

# Custom output path
python3 .claude/skills/langfuse-to-ocsf/scripts/langfuse_to_ocsf.py --out /tmp/ocsf_events.json

# Dry run (print, don't write)
python3 .claude/skills/langfuse-to-ocsf/scripts/langfuse_to_ocsf.py --dry-run --trace-id <id>
```

## Environment

```
LANGFUSE_PUBLIC_KEY   required
LANGFUSE_SECRET_KEY   required
LANGFUSE_BASE_URL     optional, default http://localhost:3000
```

## Output

A JSON array of OCSF events. Each event has:
- `class_uid`, `class_name`, `ocsf_version`, `time`, `severity_id`, `severity`
- `activity_id`, `activity_name` (ProcessActivity / APIActivity)
- `finding` (SecurityFinding / DetectionFinding)
- `actor.process.name` = "ThreatAssessor"
- `metadata.product`, `metadata.version`, `metadata.profiles`
- `unmapped` — raw Langfuse fields not covered by the OCSF class

## Failure fixes

| Error | Fix |
|-------|-----|
| `langfuse package not installed` | `pip install langfuse` |
| `LANGFUSE_PUBLIC_KEY not set` | Export env vars or add to `.env` |
| `Connection refused` | Start Langfuse: `docker compose up` in langfuse/ dir |
| No traces returned | Traces only exist after a pipeline run with LangfuseSink active |
| `api.trace.list` AttributeError | SDK version mismatch — re-test and update mapping table above |

## Related skills

- `/aivss-to-findings` — offline AIVSS → OCSF SecurityFinding (no Langfuse needed)
- `/aivss-gate` — show gate thresholds and last SIEM event
- `/check-eventbroker` — run EventBroker + Sink regression suite
