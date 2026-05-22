# HTML Documentation System

**Created:** 2026-05-22  
**Purpose:** Interactive HTML documentation with better UX than raw markdown

---

## Overview

ThreatAssessor now has **dual documentation formats**:
- **Markdown sources** (git-tracked, CLI-friendly, source of truth)
- **HTML views** (git-tracked, browser-optimized, better UX)

### Generated HTML Files

| HTML File | Source | Purpose |
|-----------|--------|---------|
| `index.html` | `README.md` | Interactive user guide with copy buttons, search |
| `status.html` | `STATUS_AND_PLAN.md` | Project dashboard with charts, progress bars |
| `docs/specs/PRODUCT_ROADMAP.html` | `docs/specs/MVP_SPECIFICATION.md` | Strategic roadmap with sidebar nav, collapsible sections |

---

## Regenerating HTML Documentation

### Quick Command

```bash
make docs
```

### Manual Command

```bash
source .venv/bin/activate
python3 scripts/docs/generate_html_docs.py
```

### View Generated Docs

```bash
make view-docs
```

Or open manually:
- `index.html` - User guide
- `status.html` - Project status
- `docs/specs/PRODUCT_ROADMAP.html` - Roadmap

---

## When to Regenerate

**Always regenerate HTML after editing markdown sources:**

1. Edit markdown source (README.md, STATUS_AND_PLAN.md, or MVP_SPECIFICATION.md)
2. Run `make docs` to regenerate HTML
3. Commit both markdown AND HTML files together

### Git Workflow

```bash
# 1. Edit markdown source
vim README.md

# 2. Regenerate HTML
make docs

# 3. Review changes
git diff index.html

# 4. Commit both
git add README.md index.html
git commit -m "docs: Update user guide with new feature"
```

---

## Why HTML?

**Benefits over raw markdown:**
- ✅ **Interactive features:** Search, collapsible sections, sortable tables
- ✅ **Copy buttons:** One-click code copying
- ✅ **Syntax highlighting:** Color-coded code blocks
- ✅ **Charts & gauges:** Visual status dashboard
- ✅ **Navigation:** Sidebar, breadcrumbs, cross-links
- ✅ **Mobile-responsive:** Works on all devices
- ✅ **Dark mode:** Automatic theme switching

**Why keep markdown:**
- ✅ **CLI-friendly:** `cat`, `grep`, `less` work natively
- ✅ **Git diffs:** Easy to review changes
- ✅ **Source of truth:** Single place to edit
- ✅ **GitHub display:** README.md renders on GitHub

---

## HTML Features

### index.html (User Guide)
- Quick start commands with copy buttons
- Feature highlight cards
- Demo walkthroughs
- Architecture diagram previews
- Responsive layout
- Search functionality

### status.html (Project Dashboard)
- Confidence gauge (99.5%)
- Validation pass rate (100%)
- Phase status breakdown
- Interactive timeline
- Sortable validation tables
- Export to PDF (future)

### PRODUCT_ROADMAP.html (Strategic Vision)
- Fixed sidebar navigation
- Collapsible phase sections
- Phase timeline with completion indicators
- Code blocks with syntax highlighting
- Search by keyword
- Print-friendly mode

---

## Technical Details

### Generator Script

**Location:** `scripts/docs/generate_html_docs.py`

**Dependencies:**
```bash
pip install markdown beautifulsoup4
```

**Features:**
- Multi-document support
- Frontmatter extraction
- Prism.js syntax highlighting
- Bootstrap 5.3 responsive layout
- Chart.js metrics visualization
- Dark mode support
- Table sorting
- Copy buttons

### Template System

**CSS:** `docs/specs/templates/main.css`  
**CDN Libraries:**
- Bootstrap 5.3 (layout)
- Prism.js (syntax highlighting)
- Chart.js (metrics)
- Fuse.js (search)
- Font Awesome (icons)

---

## Troubleshooting

### HTML not updating after markdown changes

```bash
# Force regeneration
rm -f index.html status.html docs/specs/PRODUCT_ROADMAP.html
make docs
```

### Generator script fails

```bash
# Check dependencies
pip list | grep -E "(markdown|beautifulsoup4)"

# Reinstall if needed
pip install --upgrade markdown beautifulsoup4
```

### HTML looks broken in browser

- Clear browser cache (Ctrl+Shift+R or Cmd+Shift+R)
- Check browser console for errors (F12)
- Verify CDN libraries loaded (check network tab)

---

## Future Enhancements

### Planned Features
- [ ] Auto-regeneration on file save (watch mode)
- [ ] Git pre-commit hook (auto-regen on commit)
- [ ] PDF export for all docs
- [ ] Full-text search across all docs
- [ ] Interactive architecture diagram editor
- [ ] Real-time confidence score updates
- [ ] Version history and diff viewer

### Configuration
Future: `docs/html_config.json` for:
- Theme customization
- CDN URLs
- Feature toggles
- Layout options

---

## See Also

- [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md) - Documentation navigation guide
- [README.md](README.md) - Documentation index
- [../README.md](../README.md) - User quick start (markdown source)
- [../STATUS_AND_PLAN.md](../STATUS_AND_PLAN.md) - Project status (markdown source)

---

**Maintained By:** Project team  
**Last Updated:** 2026-05-22
