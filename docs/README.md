# Documentation Index

**Version:** 1.0.0  
**Status:** Production Ready 🚀  
**Last Updated:** 2026-05-03

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
| **V1_FEATURES.md** | Complete v1.0 feature list, usage examples | All users |
| **PREVENTION_VS_MITIGATION.md** | Prevention + DIR framework (40/30/20/10) | Security architects |
| **CONFIDENCE_METHODOLOGY.md** | 5-factor confidence scoring explained | Developers |
| **REFERENCE_ARCHITECTURES.md** | Validation benchmarks, test results | QA/validation |

### Operations

| Document | Purpose | Audience |
|----------|---------|----------|
| **OPERATIONS.md** | Troubleshooting, maintenance, updates | DevOps, support |
| **ARCHITECTURE.md** | System design, data flow, modules | Developers |

### Future Roadmap

| Document | Purpose | Status |
|----------|---------|--------|
| **PHASE3C_OVERVIEW.md** | LLM as Judge/Critic (~4h) | Planned |
| **specs/MVP_SPECIFICATION.md** | Web UI requirements (~15-20h) | Planned |

---

## Subdirectories

- **archive/** - Historical documents (completed plans, old designs)
- **specs/** - Future specifications (Web UI, integrations)
- **testing/** - Testing strategy and data management
- **deployment/** - Deployment checklists and guides

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
    ├── PHASE3C_OVERVIEW.md          # Future: LLM as Critic
    │
    ├── archive/                     # Historical documents (24 files)
    ├── specs/                       # Future specifications
    ├── testing/                     # Testing strategy
    └── deployment/                  # Deployment guides
```

---

*Docs Count: 8 active | 24 archived*
