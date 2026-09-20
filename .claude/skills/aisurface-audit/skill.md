# aisurface-audit — AI Ingest Surface Enumeration

Engine Item 13. Enumerate all data ingest paths across ThreatAssessor and rate their
adversarial gate coverage. Six surfaces; no API required.

## Run

```bash
python3 .claude/skills/aisurface-audit/scripts/aisurface-audit.py
```

## What it checks

| Surface | Name | Ingest path |
|---|---|---|
| SRF-1 | Prompt surface | mmd_content / arch_content → LLM context via ground_truth_generator |
| SRF-2 | Skill script surface | .claude/skills/ executables vs SHA256 manifest |
| SRF-3 | Brain JSONL surface | ta_brain_instances.jsonl integrity gate + circular ingest guard |
| SRF-4 | Enrichment API surface | POST /api/v1/enrich input fields → report lookup |
| SRF-5 | TAclaw crawl surface | RepoCrawler file types (.md/.txt/.pdf/.yaml) → harness |
| SRF-6 | MCP parameter surface | 18-tool free-form string params (cross-ref to mcp-audit) |

## Gap ratings

| Rating | Meaning |
|---|---|
| covered | Gate present and effective for this surface |
| partial | Gate present but non-fatal, incomplete, or bypassed by some code paths |
| open | No gate; adversarial payload can reach LLM or data store unchecked |

## Severity levels

| Level | Meaning |
|---|---|
| CRITICAL | Active tampering detected (e.g., SHA256 mismatch) or gate entirely absent |
| HIGH | Significant injection path; no gate or gate bypassed by known code paths |
| MEDIUM | Gate present but non-fatal, or partial coverage |
| LOW | Best-practice gap; bounded impact |
| INFO | Clean — gate present and effective |

## Exit codes

| Code | Meaning |
|---|---|
| 0 | No CRITICAL or HIGH findings |
| 1 | One or more CRITICAL/HIGH findings |
| 2 | Cannot parse input files |

## Relationship to other audit skills

- **mcp-audit** — drills into the MCP layer (6 dimensions). aisurface-audit cross-references SRF-6; mcp-audit provides depth.
- **check-skills** — SHA256 manifest integrity for skill scripts. aisurface-audit surfaces tampering via SRF-2; check-skills regenerates the manifest (`--regen`).
- **harden-audit** — runs TA against its own architecture diagram. aisurface-audit audits the data paths where adversarial content enters the system.

Run all three together for full surface coverage:

```bash
python3 .claude/skills/aisurface-audit/scripts/aisurface-audit.py
python3 .claude/skills/mcp-audit/scripts/mcp-audit.py
python3 .claude/skills/check-skills/scripts/check-skills.py
```

## Findings — Engine Item 13 first run (2026-09-20)

Result: 0 critical, 2 high, 4 medium, 0 low, 9 info.
(After regenerating skills.sha256 manifest to include mcp-audit, taclaw-swarm,
health-audit, aisurface-audit added in Sessions 87–91.)

Surface summary:

| Surface | Coverage | Worst |
|---|---|---|
| SRF-1 Prompt | partial | MEDIUM |
| SRF-2 Skill scripts | covered | INFO |
| SRF-3 Brain JSONL | partial | MEDIUM |
| SRF-4 Enrichment API | partial | MEDIUM |
| SRF-5 TAclaw crawl | open | HIGH |
| SRF-6 MCP params | covered | INFO |

HIGH findings:

| Finding | Surface | Remediation |
|---|---|---|
| Prose adapter accepts .md/.txt/.pdf/.docx from crawled repos — no injection check | SRF-5 | Sprint |
| RepoCrawler does not stamp source_trust on CrawledArtifact | SRF-5 | Sprint |

MEDIUM findings:

| Finding | Surface | Remediation |
|---|---|---|
| QualityStage.required=False — governance gate non-fatal | SRF-1 | Next sprint |
| pipeline_provenance="unknown" for pre-gate JSONL instances | SRF-3 | Next sprint |
| resolve_arch_dir() — no path traversal check visible | SRF-4 | Next sprint |
| TAclaw route: check_preflight() not wired explicitly | SRF-5 | Next sprint |
