# Documentation Index

---
**Last Updated:** 2026-05-03  
**Status:** Current (Phase 3A Complete - RAPIDS-Driven Threat Modeling)
---

Complete documentation for the MITRE ATT&CK Threat Assessment System (Chatbot + Architecture Analysis).

## Quick Navigation

### 🚀 Getting Started
- **[../README.md](../README.md)** - Quick start guide and overview
- **[OUTPUT_FORMATS.md](OUTPUT_FORMATS.md)** - How to use different output formats
- **[deployment/](deployment/)** - Deployment guides (quick start, checklist)

### 🧪 For Testing
- **[../tests/README.md](../tests/README.md)** - How to run tests (START HERE)
- **[SELF_TEST.md](SELF_TEST.md)** - Self-test feature (8-second validation)
- **[testing/TESTING_STRATEGY.md](testing/TESTING_STRATEGY.md)** - Testing philosophy
- **[REFERENCE_ARCHITECTURES.md](REFERENCE_ARCHITECTURES.md)** - 2 validation benchmarks

### 👨‍💻 For Developers
- **[../CLAUDE.md](../CLAUDE.md)** - Developer guidelines and 95% confidence rule
- **[../STATUS_AND_PLAN.md](../STATUS_AND_PLAN.md)** - Current status and roadmap
- **[ARCHITECTURE.md](ARCHITECTURE.md)** - System design and components
- **[CONFIDENCE_METHODOLOGY.md](CONFIDENCE_METHODOLOGY.md)** - 5-factor confidence scoring

### 📋 Phase Implementation Plans
- **[PHASE3B_PLAN.md](PHASE3B_PLAN.md)** - DDIR + Resilience (NEXT, ~13h)
- **[PHASE3C_OVERVIEW.md](PHASE3C_OVERVIEW.md)** - LLM as Judge/Critic (FUTURE, ~4h)

### 🛠️ Operations
- **[OPERATIONS.md](OPERATIONS.md)** - Troubleshooting, maintenance, and updates

---

## Documentation Structure

**Single source of truth:**

```
Root/
├── README.md                    # Quick start (all users)
├── CLAUDE.md                    # Developer guidelines
└── STATUS_AND_PLAN.md           # Project status & roadmap

docs/
├── README.md (this file)        # Documentation index
├── ARCHITECTURE.md              # System design
├── OPERATIONS.md                # Troubleshooting & maintenance
├── OUTPUT_FORMATS.md            # Format usage guide
├── SELF_TEST.md                 # Self-test feature
│
├── deployment/                  # Deployment guides
│   ├── README.md                # Deployment overview
│   ├── QUICK_START.md           # 30-minute deployment
│   └── CHECKLIST.md             # Complete deployment guide
│
├── testing/                     # Testing strategy
│   ├── README.md                # Testing docs index
│   ├── TESTING_STRATEGY.md      # Why we test this way
│   └── DATA_STRATEGY.md         # Test data generation
│
├── specs/                       # Specifications
│   └── MVP_SPECIFICATION.md     # Web UI requirements (Phase 4)
│
└── archive/                     # Historical documents
    └── session-notes/           # Session summaries, working docs

tests/                           # Test suite (user-facing)
├── README.md                    # How to run tests (START HERE)
├── TEST_DATA_ASSESSMENT.md      # Coverage analysis
├── FALLBACK_ANALYSIS.md         # Fallback quality analysis
└── results/phase2.2/            # Test results
    └── summary.md               # 84.9% accuracy validated
```

**Clear separation:**
- `Root/` = Essential docs (3 files only)
- `docs/` = Reference documentation (permanent)
- `tests/` = Executable knowledge (run tests, see results)
- `archive/` = Historical context (not for production use)

---

## Documentation by Audience

### For Security Executives
**Goal:** Understand business value and ROI

Read:
1. [../README.md](../README.md) - Overview and quick start
2. [OUTPUT_FORMATS.md](OUTPUT_FORMATS.md) - Executive format section
3. [../STATUS_AND_PLAN.md](../STATUS_AND_PLAN.md) - Project status (84.9% accuracy, 79% confidence)

**Key Sections:**
- Business impact and ROI calculations
- Risk quantification
- Validation results (146 queries tested)

---

### For Security Managers
**Goal:** Plan and track implementation

Read:
1. [deployment/QUICK_START.md](deployment/QUICK_START.md) - 30-minute deployment
2. [OUTPUT_FORMATS.md](OUTPUT_FORMATS.md) - Action plan format section
3. [OPERATIONS.md](OPERATIONS.md) - Maintenance procedures

**Key Sections:**
- Implementation roadmaps
- Resource assignments
- Success metrics
- Troubleshooting

---

### For Security Analysts
**Goal:** Use tool for threat analysis

Read:
1. [../README.md](../README.md) - Quick start
2. [OUTPUT_FORMATS.md](OUTPUT_FORMATS.md) - Technical format section
3. [ARCHITECTURE.md](ARCHITECTURE.md) - System internals
4. [SELF_TEST.md](SELF_TEST.md) - Self-validation (8 seconds)

**Key Sections:**
- Detailed scoring explanations
- MITRE data structures
- Semantic search mechanics
- Validation tests

---

### For Developers
**Goal:** Extend or modify the system

Read:
1. [../CLAUDE.md](../CLAUDE.md) - **START HERE** (95% confidence rule)
2. [../STATUS_AND_PLAN.md](../STATUS_AND_PLAN.md) - Current state
3. [ARCHITECTURE.md](ARCHITECTURE.md) - System design
4. [../tests/README.md](../tests/README.md) - How to run tests
5. [testing/TESTING_STRATEGY.md](testing/TESTING_STRATEGY.md) - Testing philosophy

**Key Sections:**
- Code standards
- Testing requirements (84.9% accuracy validated)
- Module architecture
- Git workflow

---

## Core Documents (Essential)

### [../README.md](../README.md)
**Purpose:** Quick start guide for all users  
**Audience:** Everyone  
**Content:** Installation, usage examples, troubleshooting, project status

### [../CLAUDE.md](../CLAUDE.md)
**Purpose:** Developer guidelines and project context  
**Audience:** Developers  
**Content:** 95% confidence rule (CRITICAL), code standards, testing procedures

### [../STATUS_AND_PLAN.md](../STATUS_AND_PLAN.md)
**Purpose:** Current implementation status and roadmap  
**Audience:** Developers, project managers  
**Content:** Phase status (Phase 2.2 complete: 84.9% accuracy), roadmap, tasks

---

## User Guides

### [OUTPUT_FORMATS.md](OUTPUT_FORMATS.md)
**Purpose:** Complete guide to output formats  
**Audience:** All users  
**Content:** Executive/Action Plan/Technical/All formats, best practices

### [OPERATIONS.md](OPERATIONS.md)
**Purpose:** Troubleshooting and maintenance guide  
**Audience:** Operators, analysts  
**Content:** Common issues, cache regeneration, MITRE updates, performance tuning

### [ARCHITECTURE.md](ARCHITECTURE.md)
**Purpose:** System design and technical details  
**Audience:** Developers, architects  
**Content:** Data flow, module descriptions, scoring algorithms, API integrations

### [SELF_TEST.md](SELF_TEST.md)
**Purpose:** Self-test feature documentation  
**Audience:** All users  
**Content:** How to run self-test (8 seconds), 9 validation tests, troubleshooting

---

## Deployment

### [deployment/](deployment/)
**Purpose:** Deployment guides and checklists  
**Audience:** Operators, managers  
**Content:**
- [QUICK_START.md](deployment/QUICK_START.md) - 30-minute deployment
- [CHECKLIST.md](deployment/CHECKLIST.md) - Complete deployment guide
- [README.md](deployment/README.md) - Deployment overview

---

## Testing

### [../tests/README.md](../tests/README.md)
**Purpose:** How to run tests (START HERE for testing)  
**Audience:** All users  
**Content:** Quick start, test results (84.9% accuracy), commands, troubleshooting

### [testing/](testing/)
**Purpose:** Testing strategy and philosophy  
**Audience:** Developers  
**Content:**
- [TESTING_STRATEGY.md](testing/TESTING_STRATEGY.md) - Iterative validation approach
- [DATA_STRATEGY.md](testing/DATA_STRATEGY.md) - Test data generation

---

## Specifications

### [specs/MVP_SPECIFICATION.md](specs/MVP_SPECIFICATION.md)
**Purpose:** Web UI requirements (Phase 4 - future)  
**Audience:** Product, developers  
**Content:** Feature requirements, UI mockups, technology stack, timeline

---

## Archive

Historical documents in `docs/archive/` and `archive/session-notes/`:
- Old architecture versions
- Completed planning docs
- Session summaries and working docs
- Implementation notes

**Access:** For historical reference only (not production use)

---

## Document Maintenance

### When to Update

| Document | Update Trigger |
|----------|----------------|
| **README.md** | New features, status changes |
| **CLAUDE.md** | Code standards change, new guidelines |
| **STATUS_AND_PLAN.md** | Phase completion, roadmap changes |
| **ARCHITECTURE.md** | Major design changes |
| **OPERATIONS.md** | New troubleshooting procedures |
| **OUTPUT_FORMATS.md** | Format changes, new examples |
| **tests/README.md** | New test suites, validation results |

### Pre-Commit Checklist

**Before every commit:** Follow [../.github/COMMIT_RULES.md](../.github/COMMIT_RULES.md)

Key checks:
- [ ] Root has only 3 .md files (README, CLAUDE, STATUS_AND_PLAN)
- [ ] No duplicates
- [ ] No sensitive data (API keys, passwords)
- [ ] Files in correct locations
- [ ] "Last Updated" dates added
- [ ] STATUS_AND_PLAN.md updated

---

## Quick Links

### Most Frequently Used
1. [../README.md](../README.md) - Start here
2. [OUTPUT_FORMATS.md](OUTPUT_FORMATS.md) - How to use formats
3. [../tests/README.md](../tests/README.md) - Run tests
4. [OPERATIONS.md](OPERATIONS.md) - Troubleshooting

### For Implementation Work
1. [../CLAUDE.md](../CLAUDE.md) - Developer guidelines
2. [ARCHITECTURE.md](ARCHITECTURE.md) - System design
3. [../STATUS_AND_PLAN.md](../STATUS_AND_PLAN.md) - Roadmap
4. [testing/TESTING_STRATEGY.md](testing/TESTING_STRATEGY.md) - Testing approach

### For Deployment
1. [deployment/QUICK_START.md](deployment/QUICK_START.md) - 30-minute deploy
2. [deployment/CHECKLIST.md](deployment/CHECKLIST.md) - Complete guide
3. [SELF_TEST.md](SELF_TEST.md) - Validation (8 seconds)

---

## Contributing to Documentation

### Style Guide
- Use Markdown formatting
- Include code examples
- Use emoji sparingly (✅ ❌ ⚠️ 📊 🎯 only)
- Keep line length < 100 characters
- Use `bash` code blocks for commands

### File Organization (Single Source of Truth)
- Root: 3 essential docs only (README, CLAUDE, STATUS_AND_PLAN)
- `docs/`: Permanent reference documentation
- `tests/`: Executable knowledge (how to run tests)
- `archive/`: Historical documents (not for production use)

**No duplicates. Clear intent. Fast reference.**

---

## Getting Help

### Questions by Type
- "How do I run tests?" → [../tests/README.md](../tests/README.md)
- "How do I use formats?" → [OUTPUT_FORMATS.md](OUTPUT_FORMATS.md)
- "Tool not working?" → [OPERATIONS.md](OPERATIONS.md)
- "How to deploy?" → [deployment/](deployment/)
- "What's the status?" → [../STATUS_AND_PLAN.md](../STATUS_AND_PLAN.md)
- "How to contribute?" → [../CLAUDE.md](../CLAUDE.md)

---

**Documentation Status:** ✅ Organized (Phase 3A complete - RAPIDS-driven)  
**Last Updated:** 2026-05-03  
**Total Active Docs:** ~32 files (3 root + 17 docs/ + 10 tests/ + archive/)
