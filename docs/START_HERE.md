# ThreatAssessor - Start Here

**Version:** 1.3-dev  
**Status:** ✅ Production-Ready - Bug Fix + Hardening Phase Complete

---

## 📚 Documentation Quick Links

**Understanding the docs?** Start with [docs/PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md) to understand the documentation structure

**User guide?** See [index.html](index.html) for interactive quick start (HTML with copy buttons)

**Current status?** Check [status.html](status.html) for project dashboard (HTML with charts)

**Implementing?** Go to [docs/NEXT_STEPS.md](NEXT_STEPS.md) for Stage 2 Phase 2B guide (FastAPI Router)

**Planning?** See [../html/roadmap.html](../html/roadmap.html) for strategic roadmap

---

## 🎯 I'm New Here

### Web Interface (Recommended)
Open these in your browser for the best experience:
1. [index.html](index.html) - Interactive user guide with demos
2. [status.html](status.html) - Project status dashboard
3. [../html/roadmap.html](../html/roadmap.html) - Product roadmap

### Command Line (Alternative)
Read these in order:
1. [README.md](README.md) - Quick start + demo scripts
2. [docs/ROOT_OVERVIEW.md](docs/ROOT_OVERVIEW.md) - Directory structure
3. [STATUS_AND_PLAN.md](STATUS_AND_PLAN.md) - Current status

---

## 🔄 I'm Returning to This Project

### Quick Status Check
```bash
# Option 1: View HTML dashboard (opens in browser)
open status.html

# Option 2: CLI status check
cat STATUS_AND_PLAN.md | head -50
```

### Next Implementation Phase
```bash
# 1. Read next steps (Stage 2 Phase 2B - FastAPI Router, 2h)
cat docs/NEXT_STEPS.md

# 2. View strategic roadmap (opens in browser)
open ../html/roadmap.html

# 3. Test everything works
./test_demos.sh
```

**Next Phase:** Stage 2 Phase 2B - FastAPI Router (2h)  
**Details:** [docs/NEXT_STEPS.md](NEXT_STEPS.md) (tactical) | [../html/roadmap.html](../html/roadmap.html) (strategic)

---

## 🧪 I Want to Test It

```bash
# Quick test (30s, no LLM)
./demo_deterministic_engine.sh tests/data/architectures/00_safeentry.mmd

# Full test (2 min, with LLM critics)
./demo_expert_llm.sh tests/data/architectures/21_agentic_ai_system.mmd

# View results
cat report/00_safeentry/00_executive_dashboard.md
```

---

## 📚 I Need Documentation

**Core Docs (root folder):**
- [README.md](README.md) - User guide
- [STATUS_AND_PLAN.md](STATUS_AND_PLAN.md) - Project status
- [CLAUDE.md](CLAUDE.md) - Developer reference

**Detailed Docs (docs/ folder):**
- [docs/NEXT_STEPS.md](docs/NEXT_STEPS.md) - Next phase guide
- [docs/ROOT_OVERVIEW.md](docs/ROOT_OVERVIEW.md) - Directory structure
- [docs/README.md](docs/README.md) - Documentation index

---

## 🛠️ Root Folder Contents

```
📄 START_HERE.md           ← This file
📄 README.md               ← User quick start
📄 STATUS_AND_PLAN.md      ← Current status + roadmap
📄 CLAUDE.md               ← Developer reference

🔧 demo_deterministic_engine.sh   ← Fast analysis (no LLM, 30s)
🔧 demo_expert_llm.sh             ← Full MoE pipeline (2 min)
🔧 test_demos.sh                  ← Test both scripts

📁 chatbot/                ← Application code
📁 docs/                   ← Documentation (start with NEXT_STEPS.md)
📁 tests/                  ← Test suites
📁 scripts/                ← Utility scripts
📁 archive/                ← Historical files
```

---

## ✅ Current Status

**Completed:**
- Phase 3D: Mixture of Experts (MoE) validation ✅
- Bug Fix Phase: Database coverage + validator ✅
- Hardening Phase: Gap-filling controls (purple) ✅
- Service Layer (Phase 2A): Thread-safe foundation ✅

**Next:**
- Stage 2 Phase 2B: FastAPI Router (2h estimated)

**Quality:**
- 99.5% deterministic confidence
- 93-96% MoE final confidence
- 100% database coverage
- 5/5 diagnostic tests passing
- 6/6 service layer tests passing

---

**Questions?** See [docs/README.md](docs/README.md)  
**Continue work?** See [docs/NEXT_STEPS.md](docs/NEXT_STEPS.md)
