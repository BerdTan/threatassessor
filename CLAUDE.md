# DEV-TEST: MITRE Threat Modeling System

**Version:** 1.2 (AI/ML Pattern Complete)  
**Status:** ✅ Production Ready (99.5% deterministic + 85% LLM critique + AI/ML analysis)  
**Core Feature:** Architecture diagram (.mmd) → Threat assessment + AI/ML analysis + Residual risk (BEFORE/AFTER) + LLM critique

---

## What This Does

Analyze architecture diagrams to:
1. Identify attack paths and RAPIDS threats (6 categories)
2. **NEW:** AI/ML threat analysis (ARC Framework + MITRE ATLAS)
3. Recommend security controls (Prevention + DIR framework)
4. Calculate residual risk: BEFORE (current) vs AFTER (with controls)
5. Generate business-ready reports with ROI justification
6. LLM critique analysis (Architect + Tester agents)

**Time:** 30-60 seconds per architecture (+ 5-10 sec for critique)  
**Confidence:** 99.5% deterministic + 85% LLM critique (validated across 22 architectures)

---

## Quick Start

```bash
source .venv/bin/activate

# Validate for orphan nodes first (recommended)
./demo_architecture.sh --validate-orphan your_architecture.mmd

# Run threat analysis
python3 -m chatbot.main --gen-arch-truth your_architecture.mmd

# Run LLM critique (optional, Phase 3C)
python3 scripts/agent_testing/run_full_critique.py report/your_architecture

# View reports
ls report/your_architecture/
```

---

## Key Modules

**Core Analysis:**
- `chatbot/modules/ground_truth_generator.py` - Main analysis engine
- `chatbot/modules/threat_analyst.py` - Threat analyst agent (wraps deterministic engine + patterns)
- `chatbot/modules/completeness_validator.py` - 6-check validation (99.5% confidence)
- `chatbot/modules/per_node_ttp_mapper.py` - Per-node technique mapping
- `chatbot/modules/exhaustive_mitigation_mapper.py` - All 44 MITRE mitigations
- `chatbot/modules/threat_report.py` - Report generation with path-based control placement

**AI/ML Pattern (NEW):**
- `chatbot/modules/patterns/ai_pattern.py` - ARC Framework + MITRE ATLAS integration
- `chatbot/modules/pattern_registry.py` - Pattern registration system
- `chatbot/modules/atlas_helper.py` - MITRE ATLAS data loader (170 techniques, 35 mitigations)

**LLM Critique (Phase 3C):**
- `chatbot/modules/architect_critic.py` - Design quality assessment (82/100)
- `chatbot/modules/tester_critic.py` - MITRE validation (88/100)
- `chatbot/modules/agent_framework.py` - Reusable agent framework
- `chatbot/modules/artifact_extractor.py` - Extract 10 artifacts for agents

**Data:**
- `chatbot/data/enterprise-attack.json` (44MB) - MITRE ATT&CK (not in git)
- `chatbot/data/technique_embeddings.json` (45MB) - Embeddings cache (not in git)
- `chatbot/data/atlas/*.yaml` (230KB) - MITRE ATLAS for AI/ML threats
- `.env` - API key (optional, not in git)

**See:** [docs/core/V1_FEATURES.md](docs/core/V1_FEATURES.md) for complete feature documentation

---

## File Organization

```
DEV-TEST/
├── README.md, CLAUDE.md, STATUS_AND_PLAN.md    # Core 3 files only
├── chatbot/modules/                            # 22 core modules
├── docs/
│   ├── core/                                   # System documentation (4 files)
│   ├── operations/                             # Operations guides (2 files)
│   ├── development/                            # Dev guides (3 files)
│   ├── phases/                                 # Implementation history (3 files)
│   └── specs/                                  # Specifications (1 file)
├── tests/data/architectures/                   # 22 test .mmd files
├── scripts/                                    # Utilities (check_orphans.py, etc.)
├── report/                                     # Generated (gitignored)
└── archive/                                    # Historical (gitignored)
```

**Documentation Map:** See [docs/README.md](docs/README.md)  
**AI/ML Pattern:** See [docs/patterns/](docs/patterns/) for threat pattern documentation

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

### Testing
```bash
# Validate architecture for orphan nodes
./demo_architecture.sh --validate-orphan tests/data/architectures/02_minimal_defended.mmd

# Run full analysis
python3 -m chatbot.main --gen-arch-truth tests/data/architectures/02_minimal_defended.mmd

# Check validation
python3 -m chatbot.modules.completeness_validator 02_minimal_defended

# Batch test
python3 scripts/backtest_all_architectures.py
```

**See:** [docs/operations/OPERATIONS.md](docs/operations/OPERATIONS.md) for troubleshooting

---

## What NOT to Commit

```gitignore
_codex/                                  # Experimental code
archive/                                 # Historical docs
report/                                  # Generated reports
chatbot/data/*.json                      # Large data files (44MB + 45MB)
.env                                     # API keys
.claude/settings.local.json              # Local settings
```

**DO commit:**
- `tests/data/architectures/*.mmd` - Test diagrams
- `docs/` - All documentation
- `.claude/skills/` - Housekeeping skills

---

## Current Capabilities (v1.2)

| Feature | Status | Notes |
|---------|--------|-------|
| Architecture parsing | ✅ | 22 test architectures |
| RAPIDS threat assessment | ✅ | 6 categories, 100% coverage |
| **AI/ML threat analysis** | ✅ | **ARC Framework (88 controls) + MITRE ATLAS (170 techniques)** |
| Attack path analysis | ✅ | Per-node technique mapping |
| Control recommendations | ✅ | 15-37 controls per arch (RAPIDS + AI) |
| Residual risk (BEFORE/AFTER) | ✅ | Business thresholds + ROI |
| Orphan node detection | ✅ | 0 orphans across all tests |
| Path-based control placement | ✅ | Multi-path, visual clarity 95%, MMD diagrams |
| Completeness validation | ✅ | 6 checks, 99.5% confidence |
| LLM critique agents | ✅ | Architect 82/100, Tester 88/100 (composite 85/100) |

**Validation:** 22/22 architectures pass, 99.5% deterministic + 85% LLM critique

**AI/ML Pattern:**
- Auto-detects AI architectures (LLM, agents, vector DB, etc.)
- 9 ARC risk categories scored 0-100
- 20 AI-specific controls recommended
- ARC control gap benchmarking (shows % coverage)
- MITRE ATLAS techniques mapped (AML.T####)
- Consistent structure with RAPIDS controls

---

## Phase History (Quick Reference)

- **Phase 3A** (May 2): RAPIDS-driven analysis → 81% confidence
- **Phase 3B** (May 3): Prevention + DIR + Residual Risk → 99.1% confidence
- **Phase 3B+** (May 9): Intelligent control placement + Orphan detection → 99.5% confidence
- **Phase 3C MVP** (May 10-16): LLM critic agents (Architect + Tester) → 85% composite

**Next:** Phase 3C+ (Red Teamer + Orchestrator, ~6h) or Phase 4 (Web UI, ~15-20h)

**See:** [docs/phases/](docs/phases/) for detailed phase documentation

---

## Quick Commands

```bash
# Architecture analysis
python3 -m chatbot.main --gen-arch-truth architecture.mmd

# Validate for orphan nodes
./demo_architecture.sh --validate-orphan architecture.mmd

# Check all architectures
python3 scripts/backtest_all_architectures.py

# Check orphans
python3 scripts/check_orphans.py

# Run LLM critique
python3 scripts/agent_testing/run_full_critique.py report/architecture_name

# Housekeep docs
# (Enhanced housekeep-docs skill - see .claude/skills/)
```

---

## When Things Break

**Orphan nodes detected:**
```bash
# Shows which nodes are unreachable
python3 scripts/check_orphans.py architecture_name

# See remediation patterns
cat docs/operations/ARCHITECTURE_VALIDATION.md
```

**Analysis seems wrong:**
```bash
# Check validation details
python3 -m chatbot.modules.completeness_validator architecture_name

# View ground truth
cat report/architecture_name/ground_truth.json
```

**Need to update:**
```bash
# Update MITRE data (quarterly)
python3 -c "from chatbot.modules.mitre import MitreHelper; m = MitreHelper(); m.update_data()"

# Regenerate embeddings
python3 -c "from chatbot.modules.mitre_embeddings import build_technique_embeddings, save_embeddings_json; from chatbot.modules.mitre import MitreHelper; mitre = MitreHelper(use_local=True); cache = build_technique_embeddings(mitre); save_embeddings_json(cache)"
```

**See:** [docs/operations/OPERATIONS.md](docs/operations/OPERATIONS.md) for detailed troubleshooting

---

## Documentation Structure

**Essential (read these first):**
- [README.md](README.md) - User quick start
- [STATUS_AND_PLAN.md](STATUS_AND_PLAN.md) - Current status
- [docs/core/V1_FEATURES.md](docs/core/V1_FEATURES.md) - Complete feature list

**Core System:**
- [docs/core/CONFIDENCE_METHODOLOGY.md](docs/core/CONFIDENCE_METHODOLOGY.md) - 6-factor validation
- [docs/core/PREVENTION_VS_MITIGATION.md](docs/core/PREVENTION_VS_MITIGATION.md) - Prevention + DIR framework
- [docs/core/REFERENCE_ARCHITECTURES.md](docs/core/REFERENCE_ARCHITECTURES.md) - Validation benchmarks

**Operations:**
- [docs/operations/OPERATIONS.md](docs/operations/OPERATIONS.md) - Day-to-day usage
- [docs/operations/ARCHITECTURE_VALIDATION.md](docs/operations/ARCHITECTURE_VALIDATION.md) - Orphan node guide

**Development:**
- [docs/development/ARCHITECTURE.md](docs/development/ARCHITECTURE.md) - System design
- [docs/development/LLM_PROVIDER_ARCHITECTURE.md](docs/development/LLM_PROVIDER_ARCHITECTURE.md) - LLM client

**Phases:**
- [docs/phases/PHASE3B_IMPROVEMENTS.md](docs/phases/PHASE3B_IMPROVEMENTS.md) - Phase 3B details
- [docs/phases/PHASE3B_DIAGRAM_PLACEMENT.md](docs/phases/PHASE3B_DIAGRAM_PLACEMENT.md) - Visual improvements
- [docs/phases/PHASE3C_OVERVIEW.md](docs/phases/PHASE3C_OVERVIEW.md) - Next phase plan

---

**Purpose:** System instructions for Claude Code  
**Audience:** AI assistant (this document), developers (reference)  
**Keep Updated:** After major features, before commits  
**Last Updated:** 2026-05-16
