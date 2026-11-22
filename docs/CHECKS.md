# Check commands

Moved out of CLAUDE.md (2026-11-22) to keep it short. Every command here is also a skill; `/skill-name` is the usual way to run it.

## Regression and health checks

```bash
# ── Session start ────────────────────────────────────────────────────────────
# Docs health — CLAUDE.md, DECISIONS.md, memory staleness (read-only, no API)
/docs-health

# ── Pipeline / gate ──────────────────────────────────────────────────────────
# AIVSS gate config + HarnessModelGuardian model assignments + last SIEM scores
/aivss-gate

# ── SOC detection ────────────────────────────────────────────────────────────
# Regression suite (70 rules, 64 scenarios)
python3 .claude/skills/check-detect/scripts/check-detect.py
python3 .claude/skills/check-detect/scripts/check-detect.py --all   # + live corpus

# Governance guardrails (56 tests)
python3 .claude/skills/check-governance/scripts/check-governance.py

# EventBroker + sinks (65 tests)
python3 .claude/skills/check-eventbroker/scripts/check-eventbroker.py

# Adversarial red-team probe (Phase 2: no API; Phase 1: API required; Phase 3: spend gate, run with PYTHONPATH=. .venv/bin/python)
/tmeval

# TAprover: claims vs ATT&CK; also doc stage-order claims (export manifest first, see taprover skill)
python3 .claude/skills/taprover/scripts/taprover.py --prove-docs report/stage_manifest.json --docs README.md docs/ARCHITECTURE.md

# DETECT coverage flywheel
python3 .claude/skills/detect-loop/scripts/detect-loop.py --observe-only

# Rule trend analysis
python3 .claude/skills/detect-trend/scripts/detect-trend.py --all

# ── MCP / connector ──────────────────────────────────────────────────────────
# MCP server — static validation (40 checks, no API needed)
python3 .claude/skills/check-mcp/scripts/check-mcp.py
python3 .claude/skills/check-mcp/scripts/check-mcp.py --live  # + live REST + MCP stdio

# MCP client simulator — integration persona testing (API must be running)
python3 mcp_server/client_sim.py --dry-run                       # protocol handshake only
python3 mcp_server/client_sim.py --all --arch <arch>             # all 6 benign personas live

# Connector layer (mcp_connector package + openapi.yaml + transport flag)
python3 .claude/skills/check-connector/scripts/check-connector.py          # static + live
python3 .claude/skills/check-connector/scripts/check-connector.py --static # no API needed

# ── SIP platform ──────────────────────────────────────────────────────────────
# Adapter registry, endpoints, TAclaw, CLI (15 static + 7 live)
python3 .claude/skills/check-sip/scripts/check-sip.py
python3 .claude/skills/check-sip/scripts/check-sip.py --live  # + REST API checks
```

---

## Occasional checks

```bash
/session-cleanup      # master housekeeping: docs-health + repo-organise in one pass
/health-audit         # structural health: orphaned routes/adapters, DETECT coverage gaps, env-var drift
/check-skills         # supply-chain + phishing audit of .claude/skills/ corpus
/check-deprecation    # broken imports + anti-patterns — run after heavy refactoring
/skill-stress-test    # red-team a skill before finalising — pass skill name as arg
/langfuse-to-ocsf     # pipeline traces → OCSF events — requires LANGFUSE_* env vars
/repo-organise        # audit docs/tests/scripts/report — proposes, never auto-executes
/cost-estimate        # investment tier costs vs CIS/NIST/Gartner benchmarks
```
