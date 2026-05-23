# ThreatAssessor - Developer Quick Reference

**Version:** 1.3-dev  
**Status:** ✅ Production-Ready - Bug Fix + Hardening Phase Complete  
**Core Feature:** Architecture diagram → Threat assessment + AI/ML analysis + MoE validation + Hardening controls

---

## Primary Commands

**Web Dashboard (Recommended):**
```bash
# Start API server
./scripts/api/api_start.sh

# Access dashboard: http://localhost:8000/dashboard
# API docs: http://localhost:8000/docs
# See: API_MANAGEMENT.md for full details
```

**CLI Analysis:**
```bash
# Comprehensive analysis with MoE validation
./demo_expert_llm.sh your_architecture.mmd

# Quick deterministic validation (no LLM)
./demo_deterministic_engine.sh --validate-orphan your_architecture.mmd
```

**Output:** 16 files (dashboard + reports + critiques + diagrams)  
**Time:** 2 min (full) or 30 sec (deterministic only)  
**Confidence:** 93-96% (99.5% base ± expert validations)

---

## Key Module Paths

**Analysis Pipeline:**
- `chatbot/modules/ground_truth_generator.py` - Main analysis engine
- `chatbot/modules/threat_analyst.py` - RAPIDS + AI/ML pattern detection
- `chatbot/modules/completeness_validator.py` - 6-check validation
- `chatbot/modules/threat_report.py` - Report generation with path-based + hardening controls
- `chatbot/modules/exhaustive_mitigation_mapper.py` - Gap-filling controls (100% coverage)

**Agent Architecture (MoE):**
- `chatbot/modules/agents/critics/` - Architect, Tester, Red Team
- `chatbot/modules/agents/analysts/` - ThreatAnalyst + patterns
- `chatbot/modules/agents/orchestrators/` - MoEOrchestrator

**Patterns:**
- `chatbot/modules/patterns/ai_pattern.py` - ARC Framework + MITRE ATLAS
- `chatbot/modules/pattern_registry.py` - Pattern registration

**Data Sources (not in git):**
- `chatbot/data/enterprise-attack.json` (44MB) - MITRE ATT&CK
- `chatbot/data/technique_embeddings.json` (45MB) - Embeddings cache
- `chatbot/data/atlas/*.yaml` (230KB) - MITRE ATLAS

---

## Development Guidelines

### 95% Confidence Rule
Before code changes: **Ask clarifying questions** → **Research thoroughly** → **Test incrementally**

**Red flags:** "I think...", assumptions, unexplored code paths

### Code Standards
- Follow patterns in `chatbot/modules/`
- Type hints + docstrings for public APIs
- Test on multiple architectures before committing
- No secrets in code (use `.env`)

### Testing Commands
```bash
# Validate + analyze
./demo_deterministic_engine.sh --validate-orphan architecture.mmd
python3 -m chatbot.main --gen-arch-truth architecture.mmd

# Check validation
python3 -m chatbot.modules.completeness_validator architecture_name

# Batch test all 22 architectures
python3 scripts/backtest_all_architectures.py
```

---

## What NOT to Commit

```
_codex/                      # Experimental code
archive/                     # Historical docs
report/                      # Generated reports
chatbot/data/*.json          # Large data files (44MB + 45MB)
.env                         # API keys
```

**DO commit:** `tests/data/architectures/*.mmd`, `docs/`, `.claude/skills/`

---

## Quick Troubleshooting

**API Management (see [API_MANAGEMENT.md](API_MANAGEMENT.md) for full guide):**
```bash
./scripts/api/api_status.sh    # Check status
./scripts/api/api_stop.sh      # Stop API
./scripts/api/api_restart.sh   # Restart API
tail -f logs/api.log            # View logs
```

**Orphan nodes detected:**
```bash
python3 scripts/validation/check_orphans.py architecture_name
# See: docs/operations/ARCHITECTURE_VALIDATION.md
```

**Validation fails:**
```bash
python3 -m chatbot.modules.completeness_validator architecture_name
cat report/architecture_name/ground_truth.json
```

**Update MITRE data (quarterly):**
```bash
python3 -c "from chatbot.modules.mitre import MitreHelper; m = MitreHelper(); m.update_data()"
```

---

## Documentation Map

**Navigation:**
- [docs/PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md) - Start here for doc overview
- [index.html](index.html) - Interactive user guide (HTML)
- [status.html](status.html) - Project status dashboard (HTML)
- [docs/specs/PRODUCT_ROADMAP.html](docs/specs/PRODUCT_ROADMAP.html) - Full Stage 2 roadmap (HTML)

**Quick Reference:**
- Markdown sources: [README.md](README.md), [STATUS_AND_PLAN.md](STATUS_AND_PLAN.md) (git-tracked, CLI-friendly)
- HTML views: `index.html`, `status.html` (generated, better UX for browsers)
- Tactical guide: [docs/development/NEXT_STEPS.md](docs/development/NEXT_STEPS.md) - Current phase (Stage 2 Phase 2B)
- API management: [API_MANAGEMENT.md](API_MANAGEMENT.md) - Server lifecycle scripts

**Core references:**
- [docs/core/V1_FEATURES.md](docs/core/V1_FEATURES.md) - Feature list
- [docs/operations/OPERATIONS.md](docs/operations/OPERATIONS.md) - Troubleshooting
- [docs/phases/phase3d/](docs/phases/phase3d/) - MoE architecture details
- [docs/README.md](docs/README.md) - Full documentation index

---

**Purpose:** AI assistant context + developer quick reference  
**Last Updated:** 2026-05-23
