# ThreatAssessor - Root Directory Overview

**Last Updated:** 2026-05-22  
**Version:** 1.3-dev

---

## 📋 Essential Files (Start Here)

### For Continuing Work
1. **docs/NEXT_STEPS.md** 👈 START HERE
   - Next phase to work on (Stage 2 Phase 2B: FastAPI Router)
   - Prerequisites checklist
   - Implementation guide
   - Success criteria

2. **docs/STATUS_AND_PLAN.md**
   - Current project status
   - Implementation history
   - Roadmap

3. **README.md**
   - User quick start
   - Demo scripts
   - Output examples

### For Development
4. **CLAUDE.md**
   - AI assistant context
   - Module paths
   - Development guidelines
   - Testing commands

---

## 📁 Directory Structure

```
ThreatAssessor/
├── 📄 README.md                  # User quick start
├── 📄 CLAUDE.md                  # Developer quick reference
│
├── 🔧 demo_deterministic_engine.sh  # Deterministic analysis (no LLM, 30s)
├── 🔧 demo_expert_llm.sh         # Full MoE pipeline with critics (2 min)
├── 📦 requirements.txt           # Python dependencies
│
├── 📁 docs/
│   ├── 📄 STATUS_AND_PLAN.md     # Current status + roadmap (moved from root)
│   └── …
│
├── 📁 chatbot/                   # Main application code
│   ├── modules/                  # Core analysis modules
│   │   ├── ground_truth_generator.py
│   │   ├── threat_report.py
│   │   ├── completeness_validator.py
│   │   ├── exhaustive_mitigation_mapper.py
│   │   └── agents/               # MoE architecture
│   │       ├── critics/          # Architect, Tester, Red Team
│   │       ├── analysts/         # ThreatAnalyst
│   │       └── orchestrators/    # MoEOrchestrator
│   ├── services/                 # Service layer (Phase 2A ✅)
│   │   ├── base_service.py
│   │   ├── threat_analysis_service.py
│   │   └── validation_service.py
│   └── api/                      # API endpoints (Phase 2B 🚧 NEXT)
│       ├── app.py                # (to be created)
│       ├── routes/               # (to be created)
│       └── models/               # (to be created)
│
├── 📁 docs/                      # Documentation
│   ├── 📄 NEXT_STEPS.md          # 👈 Next phase guide
│   ├── 📄 README.md              # Documentation index
│   ├── core/                     # Feature documentation
│   ├── operations/               # Operations guides
│   ├── phases/                   # Phase documentation
│   │   └── phase3d/              # MoE architecture
│   ├── completed/                # Completed phase docs
│   │   └── bugfix_phase/         # Bug fix + hardening phase
│   └── investigation/            # Investigation archives
│
├── 📁 tests/                     # Test suites
│   ├── diagnostic_regression.py  # 5 tests (all passing)
│   ├── test_services_concurrent.py # 6 tests (all passing)
│   ├── test_database_coverage.py
│   └── data/architectures/       # 22 test architectures
│
├── 📁 scripts/                   # Utility scripts
│   └── validation/
│       └── check_orphans.py
│
├── 📁 report/                    # Generated reports (gitignored)
│   └── <architecture_name>/
│       ├── 00_executive_dashboard.md
│       ├── 01_executive_summary.md
│       ├── 02_technical_report.md
│       ├── 03_action_plan.md
│       ├── after.mmd
│       └── 08{a,b,c}_*.mmd
│
└── 📁 archive/                   # Historical files
    ├── baseline_logs/            # Baseline test outputs
    └── agentic/                  # Old agentic code
```

---

## 🎯 Quick Actions

### I'm Returning to This Project
```bash
# 1. Read next steps
cat docs/NEXT_STEPS.md

# 2. Check current status
cat docs/STATUS_AND_PLAN.md | head -50

# 3. Run tests to verify everything works
python3 tests/diagnostic_regression.py
python3 -m pytest tests/test_services_concurrent.py -v
```

### I Want to Test Current Features
```bash
# Option 1: Deterministic engine only (no LLM, fast 30s)
./demo_deterministic_engine.sh tests/data/architectures/00_safeentry.mmd
# Output: Ground truth + attack paths + control recommendations

# Option 2: Full MoE pipeline with LLM critics (2 min)
./demo_expert_llm.sh tests/data/architectures/21_agentic_ai_system.mmd
# Output: 16 files (deterministic + 3 critics + dashboard + phased roadmaps)

# Option 3: Test both demo scripts
./scripts/test_demos.sh
# Validates both scripts work correctly

# View generated reports
cat report/00_safeentry/00_executive_dashboard.md
cat report/21_agentic_ai_system/00_executive_dashboard.md
```

### I'm Starting Phase 2B (FastAPI Router)
```bash
# 1. Read implementation guide
cat docs/NEXT_STEPS.md

# 2. Create API directory structure
mkdir -p chatbot/api/routes chatbot/api/models
touch chatbot/api/__init__.py
touch chatbot/api/routes/__init__.py
touch chatbot/api/models/__init__.py

# 3. Start with app.py (follow NEXT_STEPS.md)
```

---

## 🔧 Demo Scripts Explained

### demo_deterministic_engine.sh
**Purpose:** Fast deterministic analysis (no LLM required)
**Time:** ~30 seconds
**Output:** 
- Ground truth analysis
- Attack paths with techniques
- Control recommendations
- RAPIDS assessment
- Before/after diagrams

**Use when:**
- Testing changes quickly
- No LLM API available
- Just need threat analysis

**Example:**
```bash
./demo_deterministic_engine.sh tests/data/architectures/00_safeentry.mmd
```

### demo_expert_llm.sh
**Purpose:** Complete MoE validation pipeline with LLM critics
**Time:** ~2 minutes
**Output:** 16 files including:
- All deterministic outputs (above)
- 3 critic validations (Architect, Tester, Red Team)
- Executive dashboard (unified report)
- Phased deployment roadmaps (08a/b/c.mmd)
- Consensus synthesis

**Use when:**
- Need full validation
- Want critic feedback
- Preparing final reports
- Testing MoE pipeline

**Example:**
```bash
./demo_expert_llm.sh tests/data/architectures/21_agentic_ai_system.mmd
```

### scripts/test_demos.sh
**Purpose:** Validate both demo scripts work correctly
**Time:** ~3 minutes
**Output:** Test results for both scripts

**Use when:**
- After code changes
- Before committing
- Verifying setup

**Example:**
```bash
./scripts/test_demos.sh
```

---

## 📊 Current Status

**Completed:**
- ✅ Phase 3D: Mixture of Experts (MoE) validation
- ✅ Bug Fix Phase: Database coverage + validator fixes
- ✅ Hardening Phase: Gap-filling controls (purple visual distinction)
- ✅ Service Layer (Phase 2A): Thread-safe foundation

**In Progress:**
- 🚧 Stage 2 Phase 2B: FastAPI Router (2h estimated)

**Test Results:**
- ✅ 5/5 diagnostic tests passing
- ✅ 6/6 service layer tests passing
- ✅ 22/22 architectures validated
- ✅ 99.5% deterministic confidence
- ✅ 93-96% MoE final confidence

**Quality Metrics:**
- 100% database coverage
- 100% technique coverage
- 0 orphan nodes
- 95% visual clarity

---

## 🔗 External Resources

**MITRE Data (not in git):**
- `chatbot/data/enterprise-attack.json` (44MB)
- `chatbot/data/technique_embeddings.json` (45MB)
- `chatbot/data/atlas/*.yaml` (230KB)

**Update quarterly:**
```bash
python3 -c "from chatbot.modules.mitre import MitreHelper; m = MitreHelper(); m.update_data()"
```

---

## 📝 Notes

- **Do NOT commit:** `report/`, `chatbot/data/*.json`, `.env`
- **Do commit:** Test architectures, documentation, test suites
- **Archive old:** Use `archive/` for baseline logs, old experiments
- **Document phases:** Use `docs/completed/` for finished phases

---

**For questions:** See `docs/README.md` or `CLAUDE.md`  
**To continue work:** Start with `docs/NEXT_STEPS.md`
