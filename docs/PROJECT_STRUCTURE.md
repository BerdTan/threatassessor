# Project Documentation Structure

**Purpose:** Navigation hub for ThreatAssessor documentation  
**Audience:** Developers, architects, project managers, new contributors  
**Last Updated:** 2026-05-22

---

## Documentation Philosophy

ThreatAssessor uses **spec-driven development** with documentation serving as the single source of truth for planning and execution. Documentation is organized by **audience** and **time horizon**:

- **Tactical (2-4 hours):** Implementation guides in Markdown
- **Strategic (3-12 months):** Roadmaps and specifications in interactive HTML
- **Status (real-time):** Project tracking and metrics dashboards

---

## Quick Navigation

```
                    PROJECT_STRUCTURE.md (YOU ARE HERE)
                               │
           ┌───────────────────┼───────────────────┐
           │                   │                   │
       NEXT_STEPS.md      PRODUCT_ROADMAP     STATUS_AND_PLAN
        (Tactical)          (Strategic)         (Tracking)
           │                   │                   │
       [2-4 hours]         [3-12 months]      [Function-level]
```

---

## For Users (Getting Started)

### 1. [index.html](../html/index.html) - Interactive User Guide 🌐
**Purpose:** Quick start and feature overview  
**Format:** HTML with interactive features  
**Update Frequency:** After feature releases

**What's Inside:**
- Installation instructions
- Quick start commands with copy buttons
- Demo walkthroughs
- Feature highlights with visual examples
- Troubleshooting guide
- Architecture diagram previews

**When to Use:** New to ThreatAssessor, want to understand features, need command reference

**Source:** [README.md](../README.md) (Markdown, git-tracked)

---

## For Developers (Doing Work)

### 2. [NEXT_STEPS.md](NEXT_STEPS.md) - Current Phase Implementation 📋
**Purpose:** Tactical implementation guide for current phase  
**Format:** Markdown (optimal for git diffs, quick CLI reference)  
**Update Frequency:** After each phase completion

**What's Inside:**
- File paths and code templates
- Implementation checklists
- Time estimates (15-90 min per task)
- Success criteria
- Testing commands
- **Current Phase:** Stage 2 Phase 2B (FastAPI Router, ~2 hours)

**When to Use:** Actively implementing current phase, need file paths, want code examples

### 3. [CLAUDE.md](../CLAUDE.md) - Developer Quick Reference ⚡
**Purpose:** One-page developer cheat sheet  
**Format:** Markdown  
**Update Frequency:** When developer workflows change

**What's Inside:**
- Primary commands
- Key module paths
- Development guidelines (95% confidence rule)
- Testing shortcuts
- Troubleshooting quick fixes
- What NOT to commit

**When to Use:** Need quick command, forgot module path, onboarding AI assistant

---

## For Architects (Planning Work)

### 4. [PRODUCT_ROADMAP.html](../html/roadmap.html) - Multi-Month Vision 🗺️
**Purpose:** Strategic product roadmap and architectural decisions  
**Format:** HTML with interactive sidebar, search, collapsible sections  
**Update Frequency:** Quarterly or major milestone completion

**What's Inside:**
- Phase timeline (Stage 2: API/Web through deployment)
- Input/output specifications
- Technical architecture decisions
- Success metrics and requirements
- Open questions for future phases
- Complete feature documentation

**When to Use:** Planning next stages, understanding long-term vision, making architectural decisions

**Source:** [docs/specs/MVP_SPECIFICATION.md](specs/MVP_SPECIFICATION.md) (Markdown, git-tracked)

---

## For Status Tracking

### 5. [status.html](../html/status.html) - Project Status Dashboard 📊
**Purpose:** Real-time project tracking with metrics and visualizations  
**Format:** HTML with charts, progress bars, interactive timeline  
**Update Frequency:** Daily/weekly during active development

**What's Inside:**
- Phase completion metrics with progress bars
- Validation results (confidence: 99.5%, pass rate: 100%)
- Recent updates timeline
- Interactive phase filtering
- Sortable validation tables
- Export to PDF

**When to Use:** Checking project status, preparing status reports, tracking milestones

**Source:** [STATUS_AND_PLAN.md](../STATUS_AND_PLAN.md) (Markdown, git-tracked)

### 6. [STATUS_AND_PLAN.md](../STATUS_AND_PLAN.md) - Detailed Status (Source) 📄
**Purpose:** Detailed project status with function-level tracking  
**Format:** Markdown  
**Update Frequency:** After each phase completion

**What's Inside:**
- Function-by-function progress tracking
- Gap identification and priorities
- Phase completion summaries
- Validation metrics
- Known limitations
- Recent updates log

**When to Use:** Need detailed status, want CLI-readable format, generating status.html source

---

## Documentation Maintenance

### Updating Documentation

**Markdown Sources (Git-Tracked):**
- `README.md` → generates `index.html`
- `STATUS_AND_PLAN.md` → generates `status.html`
- `docs/specs/MVP_SPECIFICATION.md` → generates `PRODUCT_ROADMAP.html`
- `docs/NEXT_STEPS.md` → stays as Markdown (tactical, no HTML needed)

**HTML Generation:**
```bash
# Regenerate all HTML documentation
source .venv/bin/activate
python3 scripts/docs/generate_html_docs.py

# Generated files (build artifacts):
# - index.html
# - status.html
# - html/roadmap.html
```

**Workflow:**
1. Edit markdown source (README.md, STATUS_AND_PLAN.md, MVP_SPECIFICATION.md)
2. Run generator script
3. Commit both markdown source AND generated HTML (or add HTML to .gitignore)

### When to Update Each Document

| Document | Update When | Updated By |
|----------|-------------|------------|
| NEXT_STEPS.md | Phase completes, next phase starts | Phase lead |
| PRODUCT_ROADMAP.html | Quarterly, major milestones | Product owner |
| status.html | Weekly during active development | Project manager |
| CLAUDE.md | Developer workflows change | Tech lead |
| index.html | Feature releases, major changes | Product owner |

### Cross-Reference Guidelines

- NEXT_STEPS.md → links to PRODUCT_ROADMAP.html (strategic context)
- PRODUCT_ROADMAP.html → links to NEXT_STEPS.md (implementation details)
- All docs → link to PROJECT_STRUCTURE.md (this file) for navigation help
- Use relative paths (works in git clones)

---

## For Agent-Based Development

### AI Assistant Context

This documentation structure supports **spec-driven agent-based development**:

1. **Planning Phase:** AI reads PRODUCT_ROADMAP.html to understand strategic vision
2. **Implementation Phase:** AI reads NEXT_STEPS.md for tactical execution details
3. **Status Check:** AI reads status.html or STATUS_AND_PLAN.md for current state

### Prompting Guidelines

**For planning:**
> "What's the next phase after Phase 2B?"  
> → Agent reads PRODUCT_ROADMAP.html → answers Phase 2C

**For implementation:**
> "How do I implement Phase 2B?"  
> → Agent reads NEXT_STEPS.md → provides code templates and file paths

**For navigation:**
> "Where should I look for the FastAPI implementation plan?"  
> → Agent references PROJECT_STRUCTURE.md → points to NEXT_STEPS.md

---

## External Documentation

### GitHub Repository
- **[CLAUDE.md](../CLAUDE.md)** - AI assistant context (also serves as developer quick reference)
- **[README.md](../README.md)** - GitHub landing page (also source for index.html)

### Completed Phases
- **[docs/phases/](phases/)** - Phase-specific documentation (Phase 3A, 3B, 3C, 3D, Hardening)
- **[docs/completed/](completed/)** - Archived completed documentation

### Core Documentation
- **[docs/core/](core/)** - Feature specifications, confidence methodology, frameworks
- **[docs/operations/](operations/)** - Operations guide, troubleshooting, architecture validation

### Specs
- **[docs/specs/](specs/)** - Technical specifications (MVP_SPECIFICATION.md → PRODUCT_ROADMAP.html)

---

## Quick Links Summary

| Audience | Document | Format | Purpose |
|----------|----------|--------|---------|
| **New Users** | [index.html](../html/index.html) | HTML | Quick start guide |
| **Developers** | [NEXT_STEPS.md](NEXT_STEPS.md) | Markdown | Current phase implementation |
| **Developers** | [CLAUDE.md](../CLAUDE.md) | Markdown | Quick reference cheat sheet |
| **Architects** | [PRODUCT_ROADMAP.html](../html/roadmap.html) | HTML | Strategic roadmap |
| **Managers** | [status.html](../html/status.html) | HTML | Project dashboard |
| **Anyone** | [STATUS_AND_PLAN.md](../STATUS_AND_PLAN.md) | Markdown | Detailed status |

---

## Getting Help

**Can't find what you're looking for?**

1. **Start here:** [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md) (this document)
2. **Browse:** [docs/README.md](README.md) - Complete documentation index
3. **Search:** Use browser search (Ctrl+F) in HTML docs, or `grep` in markdown sources
4. **Ask:** Check [docs/operations/OPERATIONS.md](operations/OPERATIONS.md) for troubleshooting

**For AI assistants:**
- Load [CLAUDE.md](../CLAUDE.md) for project context
- Reference this file (PROJECT_STRUCTURE.md) for navigation
- Read NEXT_STEPS.md for current implementation details

---

**Last Updated:** 2026-05-22  
**Maintained By:** Project team  
**Source:** `docs/PROJECT_STRUCTURE.md`
