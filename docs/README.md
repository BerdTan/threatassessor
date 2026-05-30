# ThreatAssessor Documentation

**Version:** 1.4 — REST API live, SSP enrichment, MoE expert review  
**Last Updated:** 2026-05-30

---

## Quick Navigation

| If you want to… | Go to |
|---|---|
| Get started fast | [START_HERE.md](START_HERE.md) |
| Understand architecture decisions | [DECISIONS.md](DECISIONS.md) |
| Check current status and roadmap | [STATUS_AND_PLAN.md](STATUS_AND_PLAN.md) |
| Run the API server | [operations/API_MANAGEMENT.md](operations/API_MANAGEMENT.md) |
| Troubleshoot issues | [operations/OPERATIONS.md](operations/OPERATIONS.md) |
| Understand the MoE agent design | [AGENTIC_DESIGN.md](AGENTIC_DESIGN.md) |
| Browse all docs | [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md) |

---

## Active Documentation

### Root (this directory)

| File | Purpose |
|---|---|
| [DECISIONS.md](DECISIONS.md) | Architectural decision log — read at session start |
| [STATUS_AND_PLAN.md](STATUS_AND_PLAN.md) | Current status, feature list, roadmap |
| [AGENTIC_DESIGN.md](AGENTIC_DESIGN.md) | MoE agent architecture, AgentTools, MCP server design |
| [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md) | Full directory map |
| [ROOT_OVERVIEW.md](ROOT_OVERVIEW.md) | Root-level files explained |
| [START_HERE.md](START_HERE.md) | Entry point for new/returning contributors |

### Operations

| File | Purpose |
|---|---|
| [operations/API_MANAGEMENT.md](operations/API_MANAGEMENT.md) | Start/stop/restart API, health checks |
| [operations/OPERATIONS.md](operations/OPERATIONS.md) | Troubleshooting common issues |
| [operations/ARCHITECTURE_VALIDATION.md](operations/ARCHITECTURE_VALIDATION.md) | Orphan node detection workflow |
| [operations/API_LIFECYCLE.md](operations/API_LIFECYCLE.md) | API process lifecycle |
| [operations/API_KEY_SETUP.md](operations/API_KEY_SETUP.md) | API key configuration |
| [operations/CACHE_BUSTING.md](operations/CACHE_BUSTING.md) | MITRE cache management |

### API Reference

| File | Purpose |
|---|---|
| [api/API_SPECIFICATION.md](api/API_SPECIFICATION.md) | Endpoint reference |
| [api/API_INTEGRATION_GUIDE.md](api/API_INTEGRATION_GUIDE.md) | Integration examples |
| [api/API_AUDIT.md](api/API_AUDIT.md) | API audit log |

### Core Concepts

| File | Purpose |
|---|---|
| [core/V1_FEATURES.md](core/V1_FEATURES.md) | Feature list with examples |
| [core/CONFIDENCE_METHODOLOGY.md](core/CONFIDENCE_METHODOLOGY.md) | How confidence is calculated |
| [core/PREVENTION_VS_MITIGATION.md](core/PREVENTION_VS_MITIGATION.md) | Control classification rationale |
| [core/REFERENCE_ARCHITECTURES.md](core/REFERENCE_ARCHITECTURES.md) | Test architecture descriptions |

### Development

| File | Purpose |
|---|---|
| [development/ARCHITECTURE.md](development/ARCHITECTURE.md) | System architecture overview |
| [development/NEXT_STEPS.md](development/NEXT_STEPS.md) | Development backlog |
| [development/LLM_PROVIDER_ARCHITECTURE.md](development/LLM_PROVIDER_ARCHITECTURE.md) | Multi-provider LLM client design |
| [development/AGENT_MIGRATION_GUIDE.md](development/AGENT_MIGRATION_GUIDE.md) | Agent refactoring guide |

### AI Pattern

| File | Purpose |
|---|---|
| [patterns/README.md](patterns/README.md) | AI/ML pattern system overview |
| [patterns/AI_PATTERN_STATUS.md](patterns/AI_PATTERN_STATUS.md) | ARC + ATLAS pattern status |
| [patterns/AI_PATTERN_VERIFICATION.md](patterns/AI_PATTERN_VERIFICATION.md) | Pattern verification results |

### SSP

| File | Purpose |
|---|---|
| [ssp/cyber.md](ssp/cyber.md) | Singapore Government ICT&SS SSP reference notes |

### Dashboard / UI

| File | Purpose |
|---|---|
| [ui/DASHBOARD_GUIDE.md](ui/DASHBOARD_GUIDE.md) | Dashboard user guide |
| [ui/DASHBOARD_COMPLETE.md](ui/DASHBOARD_COMPLETE.md) | Dashboard implementation summary |
| [ui/MOE_UI_DESIGN.md](ui/MOE_UI_DESIGN.md) | Expert Review UI design |

### Testing

| File | Purpose |
|---|---|
| [testing/TESTING_STRATEGY.md](testing/TESTING_STRATEGY.md) | Test approach and coverage |
| [testing/GROUND_TRUTH_GUIDE.md](testing/GROUND_TRUTH_GUIDE.md) | Ground truth generation guide |
| [testing/DATA_STRATEGY.md](testing/DATA_STRATEGY.md) | Test data strategy |

### Phase 3D (MoE) — completed reference

**Location:** [phases/phase3d/](phases/phase3d/)  
Contains architecture design, weekly completion notes, and agent-type documentation for the MoE implementation. Read-only reference; work is complete.

---

## Archive

Completed-phase docs, investigation snapshots, phase 3B/3C planning files, and superseded specs are in [archive/](archive/). Nothing in `archive/` needs to be read during normal development.

---

## Document Count

| Area | Files |
|---|---|
| Root docs | 6 |
| operations/ | 6 |
| api/ | 3 |
| core/ | 4 |
| development/ | 4 |
| patterns/ | 3 |
| ui/ | 3 |
| testing/ | 3 |
| ssp/ | 1 |
| phases/phase3d/ | 7 |
| **Active total** | **~44** |
| archive/ | 100+ |
