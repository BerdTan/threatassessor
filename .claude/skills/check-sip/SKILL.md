# check-sip — TA Security Intelligence Platform test suite

Validates the full SIP layer: adapter registry, input adapters (TF/CF/OAI/Prose/MMD),
enrichment API, artifact endpoint, TAclaw jobs, brain match, and taclaw CLI.

## Usage

```bash
# Static checks only (no API needed — adapters, schema, mcp_connector models, CLI)
source /mnt/c/BACKUP/DEV-TEST/.venv/bin/activate
python3 .claude/skills/check-sip/scripts/check-sip.py

# Static + live REST API checks (API must be running)
python3 .claude/skills/check-sip/scripts/check-sip.py --live

# Full suite: static + live + CLI smoke tests
python3 .claude/skills/check-sip/scripts/check-sip.py --all
```

## What it checks

| Section | Checks | Requires API |
|---|---|---|
| 1 — Adapter Registry | 6 checks: all adapters import, detect_adapter() routes correctly | No |
| 2 — Extract + to_mmd() | 4 checks: TF/CF/OAI extract nodes, valid Mermaid output | No |
| 3 — Schema + Models | 4 checks: JSON Schema valid, mcp_connector models, CLI pyproject | No |
| 4 — Live REST API | 7 checks: /sip/health, /adapters, /schemas, /taclaw/jobs, /enrich, /brain/match | Yes |
| 5 — CLI Smoke | 2 checks: import + --help | No (import only) |

## Test fixtures

Located in `tests/data/adapters/`:
- `sample.tf` — Terraform: API GW + Lambda + IAM role + RDS + S3 + SQS
- `template.yaml` — CloudFormation: same topology via CFn Resources
- `openapi.yaml` — OpenAPI 3.1: /threats, /findings/enrich paths + schemas
- `prose.txt` — 8-component architecture prose description

## Exit codes

- 0 — all checks passed
- 1 — one or more checks failed
