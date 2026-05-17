# Documentation Index

**Version:** 1.3 (Phase 3D in progress)  
**Status:** Phase 3C+ Complete (with issues) → Phase 3D (MoE) approved  
**Last Updated:** 2026-05-17

---

## Quick Start

**New to the project?** Start here:
1. `../README.md` - Project overview and quick start
2. `V1_FEATURES.md` - Complete v1.0 feature documentation
3. `../CLAUDE.md` - Developer guidelines (concise)

---

## Active Documentation

### Core Features (v1.0)

| Document | Purpose | Audience |
|----------|---------|----------|
| **core/V1_FEATURES.md** | Complete v1.0 feature list, usage examples | All users |
| **core/PREVENTION_VS_MITIGATION.md** | Prevention + DIR framework (40/30/20/10) | Security architects |
| **core/CONFIDENCE_METHODOLOGY.md** | 5-factor confidence scoring explained | Developers |
| **core/REFERENCE_ARCHITECTURES.md** | Validation benchmarks, test results | QA/validation |

### Operations & Architecture

| Document | Purpose | Audience |
|----------|---------|----------|
| **operations/OPERATIONS.md** | Troubleshooting, maintenance, updates | DevOps, support |
| **operations/ARCHITECTURE_VALIDATION.md** | Orphan node detection & remediation | Developers, QA |
| **development/ARCHITECTURE.md** | System design, data flow, modules | Developers |
| **development/LLM_PROVIDER_ARCHITECTURE.md** | Multi-provider LLM client design | Developers |
| **development/LLM_TESTING_GUIDE.md** | LLM provider testing procedures | QA, DevOps |

### Phase 3B++: Visual Prioritization (v1.2.1)

| Document | Purpose | Status |
|----------|---------|--------|
| **phases/phase3b_plus/README.md** | Phase 3B++ overview | ✅ Complete |
| **phases/phase3b_plus/PRIORITY_COLOR_CODING.md** | Red/yellow/blue/green priority colors | ✅ Complete |
| **phases/phase3b_plus/RAPIDS_CONSISTENCY.md** | RAPIDS framework label consistency | ✅ Complete |
| **phases/phase3b_plus/PRIORITY_REFINEMENT.md** | Attack path coverage + hygiene classification | ✅ Complete |

### Phase 3C+: Orchestrator & Improvement Roadmaps (v1.3)

| Document | Purpose | Status |
|----------|---------|--------|
| **phases/phase3c/ROADMAP.md** | 3-phase roadmap (3B++/3C+/3D) **UPDATED** | ✅ Phase 2 complete, Phase 3D approved |
| **phases/phase3c/HYBRID_PLAN.md** | Orchestrator consensus design | ✅ Complete |
| **phases/phase3c/PHASE3C_COMPLETE.md** | Agent framework completion summary | ✅ Complete |
| **phases/phase3c/PHASE3C_IMPROVEMENTS_NEEDED.md** | **NEW** - Critical issues found | 🔴 3 issues blocking production |
| **phases/phase3c/README.md** | Phase 3C overview | Reference |

### Phase 3D: MoE Architecture (ThreatAssessor v1.3)

| Document | Purpose | Status |
|----------|---------|--------|
| **refactoring/MOE_ARCHITECTURE_DESIGN.md** | **NEW** - MoE sequential validation design | 📋 Approved (36h, 4 weeks) |
| **planning/CLEANUP_TESTS_SCRIPTS.md** | Tests/scripts cleanup plan | ✅ Executed |

### Future Roadmap

| Document | Purpose | Status |
|----------|---------|--------|
| **specs/MVP_SPECIFICATION.md** | Web UI requirements | Planned (~15-20h) |

---

## Subdirectories

```
docs/
├── core/              # Core v1.0 features & methodologies (4 files)
├── operations/        # Troubleshooting & maintenance (2 files)
├── development/       # System design & architecture (2 files)
├── phases/            # Implementation phases (3B, 3B++, 3C+, 3D)
│   ├── phase3b/       # Phase 3B: Diagram placement (3 files)
│   ├── phase3b_plus/  # Phase 3B++: Visual prioritization (4 files)
│   └── phase3c/       # Phase 3C+: Orchestrator + Phase 3D planning (5 files)
├── patterns/          # Threat patterns (AI/ML) (3 files)
├── testing/           # Testing strategy & data management (6 files)
├── deployment/        # Deployment checklists & guides (4 files)
├── refactoring/       # MoE architecture design (1 file)
├── planning/          # Cleanup & improvement plans (1 file)
├── specs/             # Future specifications (Web UI, etc.) (1 file)
└── archive/           # Historical documents (28 files)
    ├── development/   # Completed implementation docs (2 files)
    ├── tests/         # Obsolete test files
    └── scripts/       # Obsolete scripts
```

**Active subdirectories:**
- **core/** - V1 features, confidence methodology, Prevention+DIR framework
- **operations/** - Operations guide, architecture validation (orphan nodes)
- **development/** - System architecture, LLM client design, testing guides
- **phases/** - Phase 3C agent framework (MVP1 complete, MVP2-5 planned)
- **testing/** - Test data strategy, ground truth guide
- **deployment/** - Deployment checklists

**Archived:**
- **archive/** - Completed implementation plans, superseded designs

---

## Document Lifecycle

**Active docs** (in this directory):
- Relevant to current v1.0 release
- Updated regularly
- Referenced by README.md or CLAUDE.md

**Archived docs** (in archive/):
- Completed implementation plans
- Superseded designs
- Historical session notes
- Dated with filename suffix (e.g., `PHASE3B_PLAN_2026-05-03.md`)

**Spec docs** (in specs/):
- Future feature specifications
- Not yet implemented
- Updated when work begins

---

## Documentation Map

```
ROOT/
├── README.md                        # Start here (project overview)
├── CLAUDE.md                        # Developer quick reference
├── STATUS_AND_PLAN.md              # Implementation roadmap
│
└── docs/
    ├── README.md                    # This file (documentation index)
    │
    ├── V1_FEATURES.md               # ⭐ v1.0 complete feature list
    ├── PREVENTION_VS_MITIGATION.md  # ⭐ Core framework
    ├── CONFIDENCE_METHODOLOGY.md    # How confidence is calculated
    ├── REFERENCE_ARCHITECTURES.md   # Validation benchmarks
    │
    ├── OPERATIONS.md                # Troubleshooting & maintenance
    ├── ARCHITECTURE.md              # System design details
    │
    ├── PHASE3B_IMPROVEMENTS.md      # Optional polish (next)
    ├── PHASE3C_OVERVIEW.md          # LLM as Critic (ready)
    │
    ├── implementation/              # Implementation reports
    │   └── llm_client/              # LLM client (2026-05-09) ✅
    │
    ├── specs/                       # Future specifications
    ├── archive/                     # Historical documents
    │   └── planning/                # Completed planning docs
    ├── testing/                     # Testing strategy
    └── deployment/                  # Deployment guides
```

---

---

## Recent Updates

**2026-05-17:** Phase 3C+ Complete (with issues) → Phase 3D (MoE) Approved
- **Phase 3B++:** ✅ Priority color coding, RAPIDS consistency, priority refinement (3h)
- **Phase 3C+:** ✅ Orchestrator, improvement summaries, stepped MMDs (6h)
- **Output:** 15 files per architecture (tested on AI architectures)
- **Issues Found:** 🔴 Report coherence, 🟡 Missing files, 🔴 Non-deterministic
- **Phase 3D:** 📋 MoE architecture approved (36h over 4 weeks)
  - Sequential expert chain (Deterministic → Architect → Tester → Red Team)
  - Fail-fast validation (missing prerequisite = abort)
  - Unified CISO report (00_executive_dashboard.md)
  - Rebrand to **ThreatAssessor**
- **Next:** Start Phase 3D Week 1 (Foundation, 8h)

**2026-05-10:** Phase 3C MVP (Agent Framework) complete ✅
- **New:** 3-agent critique (Architect, Tester, Red Team)
- **New:** Orchestrator consensus (composite scoring)
- **Status:** Tested on 22 architectures, 85% composite confidence
- **Docs:** Phase 3C documentation (HYBRID_PLAN, ROADMAP, agent docs)

**2026-05-17:** Documentation cleanup
- **Archived:** 2 completed implementation docs (LLM client, report formatting)
- **Structure:** Added `archive/development/` subfolder
- **Organization:** Updated docs/README.md with Phase 3B++/3C+ completion

---

*Docs Count: 4 core | 2 operations | 3 development | 11 phases (4 new phase3b_plus) | 3 patterns | 6 testing | 3 deployment | 3 refactoring | 1 spec | 26 archived (2 new)*
