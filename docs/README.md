# Documentation Index

Complete documentation for the MITRE ATT&CK Threat Assessment Chatbot.

---

## Quick Navigation

### 🚀 Getting Started
- **[Main README](../README.md)** - Quick start guide and overview
- **[OUTPUT_FORMATS.md](OUTPUT_FORMATS.md)** - How to use different output formats

### 👨‍💻 For Developers
- **[CLAUDE.md](../CLAUDE.md)** - Developer guidelines and 95% confidence rule
- **[STATUS_AND_PLAN.md](../STATUS_AND_PLAN.md)** - Current status and roadmap
- **[ARCHITECTURE.md](ARCHITECTURE.md)** - System design and components

### 🛠️ Operations
- **[OPERATIONS.md](OPERATIONS.md)** - Troubleshooting, maintenance, and updates

---

## Documentation Structure

```
docs/
├── README.md (this file)         # Documentation index
├── ARCHITECTURE.md                # System design
├── OPERATIONS.md                  # Troubleshooting & maintenance
├── OUTPUT_FORMATS.md              # Format usage guide
│
├── implementation/                # Technical implementation details
│   ├── IMPLEMENTATION_SUMMARY.md  # Hybrid mitigation + scoring
│   ├── FORMATS_IMPLEMENTATION.md  # Output formats
│   ├── SESSION_COMPLETE.md        # Complete session summary
│   └── CONFIDENCE_VALIDATION.md   # Path to 99%+ confidence
│
├── specs/                         # Specifications
│   └── MVP_SPECIFICATION.md       # Web UI requirements (Phase 4)
│
└── archive/                       # Old/deprecated docs (15 files)
    └── ...
```

---

## Documentation by Audience

### For Security Executives
**Goal:** Understand business value and ROI

Read:
1. [Main README](../README.md) - Overview and quick start
2. [OUTPUT_FORMATS.md](OUTPUT_FORMATS.md) - Executive format section
3. [implementation/SESSION_COMPLETE.md](implementation/SESSION_COMPLETE.md) - Full capabilities summary

**Key Sections:**
- Business impact and ROI calculations
- Risk quantification
- Implementation costs

---

### For Security Managers
**Goal:** Plan and track implementation

Read:
1. [Main README](../README.md) - Overview and quick start
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
1. [Main README](../README.md) - Quick start
2. [OUTPUT_FORMATS.md](OUTPUT_FORMATS.md) - Technical format section
3. [ARCHITECTURE.md](ARCHITECTURE.md) - System internals
4. [OPERATIONS.md](OPERATIONS.md) - Advanced usage

**Key Sections:**
- Detailed scoring explanations
- MITRE data structures
- Semantic search mechanics
- Validation tests

---

### For Developers
**Goal:** Extend or modify the system

Read:
1. [CLAUDE.md](../CLAUDE.md) - **START HERE** (95% confidence rule)
2. [STATUS_AND_PLAN.md](../STATUS_AND_PLAN.md) - Current state
3. [ARCHITECTURE.md](ARCHITECTURE.md) - System design
4. [implementation/IMPLEMENTATION_SUMMARY.md](implementation/IMPLEMENTATION_SUMMARY.md) - Recent changes
5. [OPERATIONS.md](OPERATIONS.md) - Testing and deployment

**Key Sections:**
- Code standards
- Testing requirements
- Module architecture
- Git workflow

---

## Core Documents

### [Main README](../README.md)
**Purpose:** Quick start guide for all users  
**Length:** ~300 lines  
**Audience:** Everyone  
**Content:**
- Installation and setup
- Usage examples (all formats)
- Quick troubleshooting
- Project status

---

### [CLAUDE.md](../CLAUDE.md)
**Purpose:** Developer guidelines and project context  
**Length:** ~400 lines  
**Audience:** Developers  
**Content:**
- 95% confidence rule (CRITICAL)
- Code standards
- Testing procedures
- File exclusions (.gitignore rationale)
- Current status and limitations

---

### [STATUS_AND_PLAN.md](../STATUS_AND_PLAN.md)
**Purpose:** Current implementation status and roadmap  
**Length:** ~200 lines  
**Audience:** Developers, project managers  
**Content:**
- Phase status (what's done, what's next)
- Detailed task breakdown
- Time estimates
- Dependencies

---

## User Guides

### [OUTPUT_FORMATS.md](OUTPUT_FORMATS.md)
**Purpose:** Complete guide to output formats  
**Length:** ~400 lines  
**Audience:** All users  
**Content:**
- Format comparison table
- Usage examples for each format
- Best practices by audience
- Customization tips

**Key Sections:**
- Executive format (business summary)
- Action plan format (implementation roadmap)
- Technical format (detailed analysis)
- When to use each format

---

### [OPERATIONS.md](OPERATIONS.md)
**Purpose:** Troubleshooting and maintenance guide  
**Length:** ~300 lines  
**Audience:** Operators, analysts  
**Content:**
- Common issues and fixes
- Cache regeneration
- MITRE data updates
- Performance tuning
- Testing procedures

---

### [ARCHITECTURE.md](ARCHITECTURE.md)
**Purpose:** System design and technical details  
**Length:** ~400 lines  
**Audience:** Developers, architects  
**Content:**
- Data flow diagrams
- Module descriptions
- Scoring algorithms
- API integrations
- Design decisions

---

## Implementation Details

### [implementation/IMPLEMENTATION_SUMMARY.md](implementation/IMPLEMENTATION_SUMMARY.md)
**Purpose:** Hybrid mitigation + scoring implementation  
**Length:** ~600 lines  
**Audience:** Developers  
**Content:**
- What was built (Phase 1)
- Architecture decisions
- Validation results
- Files changed
- Performance metrics

---

### [implementation/FORMATS_IMPLEMENTATION.md](implementation/FORMATS_IMPLEMENTATION.md)
**Purpose:** Output formats implementation  
**Length:** ~400 lines  
**Audience:** Developers  
**Content:**
- What was built (Phase 2)
- Format design rationale
- Before/after comparison
- Real-world use cases
- Testing results

---

### [implementation/SESSION_COMPLETE.md](implementation/SESSION_COMPLETE.md)
**Purpose:** Complete session summary (Phases 1 + 2)  
**Length:** ~300 lines  
**Audience:** All  
**Content:**
- Full work summary
- Key achievements
- Deliverables list
- Confidence assessment
- What's production-ready

---

### [implementation/CONFIDENCE_VALIDATION.md](implementation/CONFIDENCE_VALIDATION.md)
**Purpose:** Path to 99%+ confidence  
**Length:** ~300 lines  
**Audience:** Developers, QA  
**Content:**
- Current 5% uncertainty breakdown
- Validation tests needed
- Test suites (LLM, tactic weights, edge cases)
- Extended validation (breach analysis, expert review)
- Confidence milestones

---

## Specifications

### [specs/MVP_SPECIFICATION.md](specs/MVP_SPECIFICATION.md)
**Purpose:** Web UI requirements (Phase 4 - future)  
**Length:** ~200 lines  
**Audience:** Product, developers  
**Content:**
- Feature requirements
- UI mockups
- Technology stack
- Implementation timeline

---

## Archive

15 old/deprecated documents moved to `docs/archive/`:
- Old architecture versions
- Completed planning docs
- Deprecated quick starts
- Merged references
- Outdated roadmaps

**Access:** `docs/archive/` (for historical reference only)

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
| **implementation/*.md** | After major implementations (archive when obsolete) |

### Documentation Checklist

When adding features:
- [ ] Update README.md (usage section)
- [ ] Update relevant user guide
- [ ] Create implementation doc if major change
- [ ] Update STATUS_AND_PLAN.md (mark phase complete)
- [ ] Update CLAUDE.md if guidelines change
- [ ] Run spell check
- [ ] Test all code examples

---

## Quick Links

### Most Frequently Used
1. [Main README](../README.md) - Start here
2. [OUTPUT_FORMATS.md](OUTPUT_FORMATS.md) - How to use formats
3. [OPERATIONS.md](OPERATIONS.md) - Troubleshooting

### For Implementation Work
1. [CLAUDE.md](../CLAUDE.md) - Developer guidelines
2. [ARCHITECTURE.md](ARCHITECTURE.md) - System design
3. [implementation/IMPLEMENTATION_SUMMARY.md](implementation/IMPLEMENTATION_SUMMARY.md) - Recent changes

### For Planning
1. [STATUS_AND_PLAN.md](../STATUS_AND_PLAN.md) - Roadmap
2. [specs/MVP_SPECIFICATION.md](specs/MVP_SPECIFICATION.md) - Web UI plans
3. [implementation/CONFIDENCE_VALIDATION.md](implementation/CONFIDENCE_VALIDATION.md) - Validation path

---

## Contributing to Documentation

### Style Guide
- Use Markdown formatting
- Include code examples
- Add table of contents for long docs (>200 lines)
- Use emoji sparingly (✅ ❌ ⚠️ 📊 🎯 only)
- Keep line length < 100 characters
- Use `bash` code blocks for commands

### File Naming
- Use SCREAMING_SNAKE_CASE for docs (e.g., `OUTPUT_FORMATS.md`)
- Use lowercase for directories (e.g., `implementation/`)
- Use descriptive names (not `doc1.md`)

### Organization
- Root: Essential docs only (README, CLAUDE, STATUS)
- `docs/`: User guides
- `docs/implementation/`: Technical implementation details
- `docs/specs/`: Specifications
- `docs/archive/`: Deprecated docs (don't delete, archive)

---

## Getting Help

### Issues
- Tool not working: See [OPERATIONS.md](OPERATIONS.md)
- Documentation unclear: Open GitHub issue
- Feature request: See [STATUS_AND_PLAN.md](../STATUS_AND_PLAN.md) first

### Questions
- "How do I...?" → [Main README](../README.md) or [OUTPUT_FORMATS.md](OUTPUT_FORMATS.md)
- "Why does it...?" → [ARCHITECTURE.md](ARCHITECTURE.md)
- "What's the status...?" → [STATUS_AND_PLAN.md](../STATUS_AND_PLAN.md)
- "How do I contribute...?" → [CLAUDE.md](../CLAUDE.md)

---

*Documentation Index last updated: 2026-05-01*  
*Total documents: 13 active, 15 archived*
