# DEV-TEST: MITRE Threat Modeling System

**Status:** ✅ v1.0 Production Ready (82-85% confidence) 🚀  
**Primary Feature:** Architecture diagram → Comprehensive threat assessment + Residual risk (BEFORE/AFTER)

---

## Quick Start

```bash
source .venv/bin/activate

# Architecture threat assessment (v1.0 feature)
python3 -m chatbot.main --gen-arch-truth architecture.mmd

# Threat scenario chatbot
python3 -m chatbot.main
```

---

## Documentation Map

**Start Here:**
- `README.md` - Quick start and overview
- `docs/V1_FEATURES.md` - Complete v1.0 feature documentation
- `STATUS_AND_PLAN.md` - Implementation status and roadmap

**Key Docs:**
- `docs/PREVENTION_VS_MITIGATION.md` - Prevention + DIR framework
- `docs/CONFIDENCE_METHODOLOGY.md` - 5-factor confidence scoring
- `docs/REFERENCE_ARCHITECTURES.md` - Validation benchmarks
- `docs/OPERATIONS.md` - Troubleshooting and maintenance

**Future:**
- `docs/PHASE3C_OVERVIEW.md` - LLM as Judge/Critic (~4h)
- `docs/specs/MVP_SPECIFICATION.md` - Web UI (Phase 4, 15-20h)

---

## Core Architecture

### v1.0 Feature: Residual Risk Assessment

**Input:** Mermaid architecture diagram (.mmd)  
**Output:** Comprehensive threat assessment with BEFORE/AFTER residual risk

**What it does:**
1. Parse architecture → Identify attack paths
2. Assess RAPIDS threats (Ransomware, AppVulns, Phishing, Insider, DoS, Supply Chain)
3. Recommend controls (Prevention + DIR framework)
4. Calculate residual risk:
   - **BEFORE**: Risk with present controls (e.g., 65/100 MITIGATE)
   - **AFTER**: Risk after implementing recommendations (e.g., 9.5/100 ACCEPT)
   - **ROI**: Risk reduction % and cost justification

**Output Files:**
```
report/<arch_name>/
├── 01_executive_summary.md    # Business summary with ROI
├── 02_technical_report.md     # Technical details with MITRE mapping
├── 03_action_plan.md          # Implementation roadmap (8 weeks)
├── before.mmd                 # Current architecture
└── after.mmd                  # With recommended controls (context-aware labels)
```

### Key Modules

**Core Engine:**
- `chatbot/modules/ground_truth_generator.py` - Architecture analysis engine
- `chatbot/modules/rapids_driven_controls.py` - RAPIDS-first recommendations
- `chatbot/modules/layered_defense.py` - Hop-by-hop Prevention + DIR
- `chatbot/modules/residual_risk.py` - BEFORE/AFTER risk calculation
- `chatbot/modules/threat_report.py` - Report generation

**Data Requirements:**
- `chatbot/data/enterprise-attack.json` (44MB) - MITRE ATT&CK data
- `chatbot/data/technique_embeddings.json` (45MB) - Pre-computed embeddings
- `.env` - API key (optional, for LLM enhancement)

---

## Development Guidelines

### 95% Confidence Rule

Before code changes: **Ask clarifying questions** → **Research thoroughly** → **Test incrementally**

**Red flags:** "I think this might work...", assumptions, unexplored code

### Code Standards

- Follow existing patterns in `chatbot/modules/`
- Type hints + docstrings for public APIs
- Log important events
- Test before committing

### Testing Checklist

```bash
# Run architecture assessment on test cases
python3 -m chatbot.main --gen-arch-truth tests/data/architectures/02_minimal_defended.mmd

# Check no regressions
pytest tests/test_semantic_search.py -v

# Verify no secrets
grep -r "sk-or-v1" .
```

---

## File Organization

### Directory Structure

```
DEV-TEST/
├── chatbot/modules/         # Core engines (18 modules)
├── chatbot/parsers/         # Mermaid parser
├── tests/data/
│   ├── architectures/       # Test .mmd files (18 samples)
│   └── ground_truth/        # Validation JSON (7 validated)
├── docs/                    # Documentation
├── report/                  # Generated reports (gitignored)
└── archive/                 # Historical docs (gitignored)
```

### .gitignore Rules

**DO NOT commit:**
- `_codex/` - Experimental code
- `archive/` - Historical documents
- `report/` - Generated reports (regenerate from .mmd)
- `chatbot/data/*.json` - Large data files (44MB + 45MB)
- `.env` - API keys

**COMMIT:**
- `tests/data/ground_truth/*.json` - Validation ground truths
- `tests/data/architectures/*.mmd` - Test diagrams

---

## Current Status (v1.0)

### Production Ready ✅

| Feature | Status | Performance |
|---------|--------|-------------|
| Architecture parsing | ✅ Working | 18 test architectures |
| RAPIDS threat assessment | ✅ Working | 6 threat categories |
| Control recommendations | ✅ Working | 80+ control mappings |
| Residual risk (BEFORE/AFTER) | ✅ Working | Tested across 5 architectures |
| Prevention + DIR framework | ✅ Working | Context-aware control labels |
| Report generation | ✅ Working | 3 formats + diagrams |

**Validation:**
- Pass rate: 80% (4/5 architectures)
- Confidence: 82-85%
- Residual risk accuracy: ✅ (65→9.5, 26→13 tested)
- ROI calculation: ✅ (risk reduction %)

### Known Limitations

1. **Hop visualization**: Controls placed heuristically (data correct in JSON, polish item)
2. **AI/ML edge cases**: Ambiguous entries may flag validation warnings (acceptable)
3. **LLM optional**: System works without LLM (deterministic parser)

---

## Quick Commands

```bash
# Architecture assessment
python3 -m chatbot.main --gen-arch-truth architecture.mmd

# Run tests
pytest tests/ -v

# Update MITRE data (quarterly)
python3 -c "from chatbot.modules.mitre import MitreHelper; m = MitreHelper(); m.update_data()"

# Regenerate embeddings cache (after MITRE update)
python3 -c "from chatbot.modules.mitre_embeddings import build_technique_embeddings, save_embeddings_json; from chatbot.modules.mitre import MitreHelper; mitre = MitreHelper(use_local=True); cache = build_technique_embeddings(mitre); save_embeddings_json(cache)"
```

---

## Troubleshooting

**Architecture assessment not working:**
```bash
# Check Mermaid syntax
cat architecture.mmd

# Run with verbose output
python3 -m chatbot.main --gen-arch-truth architecture.mmd 2>&1 | grep ERROR
```

**Residual risk calculation seems off:**
- Check control detection: `grep "Controls present" report/<name>/ground_truth.json`
- Verify RAPIDS scores: Look for "ransomware", "application_vulns" in logs
- See control effectiveness: `chatbot/modules/residual_risk.py` lines 43-129

**See:** `docs/OPERATIONS.md` for detailed troubleshooting

---

## What's New in v1.0

**Major Features:**
1. **Residual Risk Assessment** - BEFORE/AFTER with ROI calculation
2. **Prevention + DIR Framework** - Defense-in-depth clarity (40/30/20/10 budget)
3. **Layered Defense** - Hop-by-hop security + resilience analysis
4. **Context-Aware Labels** - Diagram controls show Prevents/Detects/Contains/Recovers
5. **SPOF Detection** - Graph topology identifies single points of failure

**Files Added:**
- `chatbot/modules/layered_defense.py` (498 lines)
- `chatbot/modules/residual_risk.py` (365 lines)
- `docs/V1_FEATURES.md` - Complete feature documentation
- `docs/PREVENTION_VS_MITIGATION.md` - Framework documentation

**Files Enhanced:**
- `chatbot/modules/ground_truth_generator.py` - Residual risk integration
- `chatbot/modules/rapids_driven_controls.py` - DIR inference + hop enrichment
- `chatbot/modules/threat_report.py` - Context-aware verbs + BEFORE/AFTER sections

---

## Next Steps (Post v1.0)

**Optional Polish (~6h):**
- Enhanced validation (6 checks vs 2)
- Budget enforcement (strict 40/30/20/10)
- Hop-specific diagram placement

**Phase 3C: LLM as Critic (~4h):**
- Gap detection beyond deterministic rules
- Architecture-specific risk identification
- See `docs/PHASE3C_OVERVIEW.md`

**Phase 4: Web UI (15-20h):**
- React + FastAPI interface
- Interactive attack path visualization
- See `docs/specs/MVP_SPECIFICATION.md`

---

*Version: 1.0.0 (Residual Risk Assessment)*  
*Last Updated: 2026-05-03*  
*Status: Production Ready 🚀*
