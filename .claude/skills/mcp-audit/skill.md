# mcp-audit — MCP Attack Surface Security Posture Audit

Engine Item 12. Six static audit dimensions against the 18-tool ThreatAssessor MCP server.
No API required — all checks read source files only.

## Run

```bash
python3 .claude/skills/mcp-audit/scripts/mcp-audit.py
```

## What it checks

| Dim | Name | What |
|---|---|---|
| DIM-1 | Tool description injection | Scan all 18 tool docstrings + FastMCP.instructions for instruction-override patterns |
| DIM-2 | Parameter validation gaps | Flag unvalidated string params that reach LLM, crawler, or API without sanitization |
| DIM-3 | Scope gap analysis | Flag tools not called by any client_sim persona (no access-log baseline) |
| DIM-4 | Transport security | Verify TM_MCP_KEY guard for network transports; default bind address risk |
| DIM-5 | Adversarial persona coverage | Flag tools with no adversarial test coverage; detect missing adversarial sim file |
| DIM-6 | Agent identity validation | Verify ABAC caller-identity check at MCP dispatch for modify-tier tools |

## Severity levels

| Level | Meaning |
|---|---|
| CRITICAL | Exploitable without authentication; immediate action |
| HIGH | Significant attack vector; fix before shipping |
| MEDIUM | Defense-in-depth gap; fix in current sprint |
| LOW | Best practice deviation; address in next sprint |
| INFO | Clean — no issue |

## Exit codes

| Code | Meaning |
|---|---|
| 0 | No CRITICAL or HIGH findings |
| 1 | One or more CRITICAL/HIGH findings |
| 2 | Cannot parse input files |

## Relationship to check-mcp

`check-mcp` validates protocol correctness (40 checks: imports, tool count, routing,
live REST endpoints). `mcp-audit` audits the security posture of the exposed surface.
Run both together:

```bash
python3 .claude/skills/check-mcp/scripts/check-mcp.py
python3 .claude/skills/mcp-audit/scripts/mcp-audit.py
```

## Findings — Engine Item 12 first run (2026-09-20)

Result: 0 critical, 11 high, 11 medium, 5 low, 5 info.
DIM-1 clean (no description injection). DIM-4 mostly clean (TM_MCP_KEY guard present).

HIGH findings:

| Finding | Dim | Remediation priority |
|---|---|---|
| `run_taco_agent.query` bypasses content trust gate | DIM-2 | Sprint |
| `run_taclaw.target` has no path-traversal check | DIM-2 | Sprint |
| `analyze_architecture` uncovered by any persona (tier: analyze) | DIM-3 | Sprint |
| `governance_check` uncovered (tier: analyze) | DIM-3 | Sprint |
| `run_expert_review` uncovered (tier: modify) | DIM-3 | Sprint |
| `record_brain_feedback` uncovered (tier: modify) | DIM-3 | Sprint |
| `generate_synthetic_architectures` uncovered (tier: modify) | DIM-3 | Sprint |
| `run_taco_agent` uncovered (tier: modify) | DIM-3 | Sprint |
| `run_taclaw` uncovered (tier: analyze) | DIM-3 | Sprint |
| No adversarial persona file (client_sim_adversarial.py) | DIM-5 | Sprint |
| 7 modify/analyze-tier tools have no adversarial coverage | DIM-5 | Sprint |

MEDIUM findings:

| Finding | Dim | Remediation priority |
|---|---|---|
| `generate_synthetic_architectures.max_per_run` unbounded | DIM-2 | Next sprint |
| `record_brain_feedback.feedback` enum not enforced | DIM-2 | Next sprint |
| `lookup_mitre_technique.technique_ids` not validated | DIM-2 | Next sprint |
| `run_taclaw.target_type` enum not enforced | DIM-2 | Next sprint |
| `export_assessment`, `get_job_status`, `get_mcp_access_signals`, `query_ta_brain` uncovered | DIM-3 | Next sprint |
| Default --host 0.0.0.0 for network transports | DIM-4 | Next sprint |
| No ABAC caller-identity check at dispatch | DIM-6 | Next sprint |
| `_mcp_content_trust_check` scope limited to mmd_content only | DIM-6 | Next sprint |
