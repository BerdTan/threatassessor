# ThreatAssessor — Start Here

**Version:** 1.4 — REST API live, SSP enrichment, MoE expert review  
**Last Updated:** 2026-05-30

---

## I'm new here

```bash
git clone <repo-url> && cd DEV-TEST
make install && make setup   # install deps + generate API key in .env
make start                   # start API server on :8000
# open http://localhost:8000/dashboard
```

Full quick start: [../README.md](../README.md)

---

## I'm returning to continue work

```bash
# Read architectural decisions first
cat docs/DECISIONS.md | tail -80

# Check current status and roadmap
cat docs/STATUS_AND_PLAN.md | head -60

# Start API server
make start
```

---

## I want to run a quick test

```bash
# Deterministic only (~30 s, no LLM key needed)
./demo_deterministic_engine.sh tests/data/architectures/00_safeentry.mmd

# Full MoE pipeline (~2 min, requires OPENROUTER_API_KEY in .env)
./demo_expert_llm.sh tests/data/architectures/21_agentic_ai_system.mmd

# Unit tests
make test
```

---

## I need documentation

| Need | File |
|------|------|
| Architecture decisions | [docs/DECISIONS.md](DECISIONS.md) |
| Current status + roadmap | [docs/STATUS_AND_PLAN.md](STATUS_AND_PLAN.md) |
| Developer quick reference | [../CLAUDE.md](../CLAUDE.md) |
| MoE agent design | [docs/AGENTIC_DESIGN.md](AGENTIC_DESIGN.md) |
| API operations | [docs/operations/API_MANAGEMENT.md](operations/API_MANAGEMENT.md) |
| All docs | [docs/README.md](README.md) |

---

## Current status (v1.4)

- REST API live with SSE streaming and Swagger UI
- SSP enrichment: Singapore Government ICT&SS policy baseline per architecture
- MoE expert review: Architect + Tester + Red Team critics (parallel or sequential)
- Dashboard: upload, history dropdown, reload/re-run past analyses
- 25 test architectures, 16 output files per analysis

**Next priorities:** backtest script, CloudPattern, AgentTools  
See [docs/STATUS_AND_PLAN.md](STATUS_AND_PLAN.md) for full roadmap.
