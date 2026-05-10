# Documentation Index

**Version:** 1.0.1  
**Status:** Production Ready 🚀 + Phase 3C MVP1 (Agent Framework)  
**Last Updated:** 2026-05-10

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

### Phase 3C: Agent Framework (LLM as Judge/Critic)

| Document | Purpose | Status |
|----------|---------|--------|
| **phases/PHASE3C_OVERVIEW.md** | 4-agent architecture design | Reference |
| **phases/PHASE3C_MVP1_SUMMARY.md** | Architect agent implementation & validation | ✅ Complete |
| **phases/PHASE3C_MVP1_CONFIDENCE_ANALYSIS.md** | Validation methodology & test results | ✅ Complete |
| **phases/PHASE3C_MVP2_TESTER_SPEC.md** | Tester agent specification | 📋 Next (~2-3h) |
| **phases/PHASE3C_AGENT_FRAMEWORK_COMPARISON.md** | Framework selection rationale | Reference |

### Future Roadmap

| Document | Purpose | Status |
|----------|---------|--------|
| **specs/MVP_SPECIFICATION.md** | Web UI requirements | Planned (~15-20h) |

---

## Subdirectories

```
docs/
├── core/              # Core v1.0 features & methodologies
├── operations/        # Troubleshooting & maintenance
├── development/       # System design & architecture
├── phases/            # Implementation phases (3A, 3B, 3B+, 3C)
├── testing/           # Testing strategy & data management
├── deployment/        # Deployment checklists & guides
├── specs/             # Future specifications (Web UI, etc.)
└── archive/           # Historical documents (completed plans)
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

**2026-05-10:** Phase 3C MVP1 (Agent Framework) complete ✅
- **New:** Architect critic agent for quality assessment
- **New:** Improvement roadmap with verification methods for Tester
- **New:** Agent test data framework (`tests/data/agent_test_cases/`)
- **Docs:** 5 new Phase 3C documents (overview, summary, confidence analysis, tester spec, framework comparison)
- **Status:** Tested on 3 architectures (good=78/100, flawed=23/100 catches all planted errors)
- **Next:** MVP2 Tester agent (~2-3h)

**2026-05-09:** Multi-provider LLM client implementation complete ✅
- See: `development/` for LLM architecture documentation
- Status: 8/8 tests passing, all modules verified working

---

*Docs Count: 4 core | 2 operations | 5 development | 7 phases | 5 testing | 3 deployment | 25 archived*
