# ThreatAssessor - Start Here

**Version:** 1.3-dev  
**Status:** ✅ Production-Ready - Bug Fix + Hardening Phase Complete

---

## 🎯 I'm New Here

Read these in order:
1. [README.md](README.md) - Quick start + demo scripts
2. [docs/ROOT_OVERVIEW.md](docs/ROOT_OVERVIEW.md) - Directory structure
3. [STATUS_AND_PLAN.md](STATUS_AND_PLAN.md) - Current status

---

## 🔄 I'm Returning to This Project

```bash
# 1. Read next steps
cat docs/NEXT_STEPS.md

# 2. Check status
cat STATUS_AND_PLAN.md | head -50

# 3. Test everything works
./test_demos.sh
```

**Next Phase:** Stage 2 Phase 2B - FastAPI Router (2h)  
**Details:** See [docs/NEXT_STEPS.md](docs/NEXT_STEPS.md)

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
