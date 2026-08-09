---
name: audit-to-detect
description: Translate /harden-audit security findings into new DETECT rules. Reads security-assessment/REPORT.md, filters findings to those that are structurally detectable and not already covered, proposes DETECT rule YAML, gates on human approval, applies to policies/soc_detection_rules.yaml, and verifies with /check-detect. Use after any /harden-audit run to close the loop between security findings and the SOC detection layer.
argument-hint: "[--report <path>] [--observe-only] [--finding <RT-ID>]"
---

# audit-to-detect — Security Findings → DETECT Rules

Reads a `security-assessment/REPORT.md` and proposes new DETECT rules for findings
that are structurally detectable as architecture or governance signals — not just
one-off code fixes. Follows the same observe→diagnose→prescribe→gate→apply→verify
cycle as `/detect-loop`.

## When to use

- After any `/harden-audit` run
- When a new attack surface is found that recurs across architectures
- When a finding maps to an OWASP Agentic Top 10 or MITRE ATLAS technique

## Do NOT create DETECT rules for

- Pure code bugs (missing guard, wrong comparison) — these are fixed in code
- One-off misconfigurations specific to this deployment
- Runtime/timing attacks not visible in MMD diagrams or governance signals

## Run

```bash
# Read default report path, show candidates, no changes
python3 .claude/skills/audit-to-detect/scripts/audit_to_detect.py --observe-only

# Full cycle — propose + gate + apply for each candidate
python3 .claude/skills/audit-to-detect/scripts/audit_to_detect.py

# Target a specific finding
python3 .claude/skills/audit-to-detect/scripts/audit_to_detect.py --finding RT-02

# Use a non-default report path
python3 .claude/skills/audit-to-detect/scripts/audit_to_detect.py --report /path/to/REPORT.md
```

## Filter criteria (applied automatically)

A finding is a DETECT candidate if ALL of the following are true:

1. **Structurally detectable** — the attack is visible in one of:
   - MMD diagram topology or node labels
   - governance_signals fields (exploitation, injection, manipulation, sovereignty)
   - AIVSS score dimensions (inbound/internal/outbound)
   - MCP access patterns (mcp_access.*)
2. **Not already covered** — no existing DETECT rule fires on the same signal
3. **Architecture-level pattern** — recurs across system types, not a single deployment quirk
4. **Severity High or Critical** — Medium/Low findings rarely warrant a standing rule

## Output

Per-candidate:
- Finding summary + why it passes the filter
- Proposed DETECT rule YAML (id, name, description, conditions, severity, actions, provenance)
- Gate: `y` to apply, `n` to skip, `q` to quit
- After apply: re-runs `/check-detect` and shows delta

## Prerequisites

- `security-assessment/REPORT.md` exists (run `/harden-audit` first)
- API not required — operates on local files only
