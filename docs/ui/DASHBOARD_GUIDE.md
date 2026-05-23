# ThreatAssessor Dashboard Guide

**Version:** 1.0 (PHASE 1 - Progress Visibility)  
**Date:** 2026-05-23  
**Status:** ✅ Production Ready

---

## Quick Start

### 1. Generate API Key (First Time Only)
```bash
# Generate secure API key
echo "API_KEY=$(openssl rand -hex 32)" >> .env
```

### 2. Start the API Server
```bash
# From project root
source .venv/bin/activate
export API_KEY=$(grep "^API_KEY=" .env | cut -d'=' -f2)
uvicorn chatbot.api.app:app --host 0.0.0.0 --port 8000
```

### 3. Open Dashboard
Navigate to: **http://localhost:8000/dashboard**

### 4. Upload Architecture
- Click "📤 Upload Architecture" or drag-and-drop a `.mmd` file
- Watch real-time progress as analysis runs
- Explore results in multiple tabs

---

## Dashboard Features

### Header
- **Pattern Badges**: Shows which threat patterns were applied (RAPIDS, AI/ML, Cloud)
- **Theme Toggle** (🌙/☀️): Switch between dark and light themes
- **Upload Button**: Start new analysis

### Sidebar Navigation
- 📊 **Overview**: Threat heat map + architecture diagram
- 🧩 **Patterns**: Threat patterns applied and why
- 🎯 **Attacks**: Attack paths with left-to-right flow
- 🛡️ **Controls**: Security controls (present/missing)
- 📋 **MITRE**: Technique coverage matrix
- 🤖 **AI/ML**: AI/ML risks (only shown if detected)
- 📄 **Reports**: Generated reports
- 💾 **Raw Data**: JSON/Markdown artifacts

### Progress Bar (Bottom)
- **Visual progress**: 0-100% with color gradient
- **Percentage display**: Shows current progress

### Status Bar (Bottom)
- **Real-time messages**: "Loading MITRE cache...", "Running RAPIDS...", etc.
- **ETA display**: Estimated time remaining in seconds

### Stage Indicators (Bottom)
- **Stage flow**: Parsing → MITRE → RAPIDS → AI/ML → Validation
- **Visual states**:
  - ⚪ Pending (not started)
  - ● Active (currently running)
  - ✅ Complete (finished)

---

## Pattern-Aware UI

### Pattern Detection
The dashboard automatically detects which threat patterns apply:

#### RAPIDS (Always Applied)
- **Badge Color**: Blue
- **Scope**: Universal
- **Categories**: Ransomware, Application, Phishing, Insider, DoS, Supply Chain
- **Source**: MITRE Enterprise ATT&CK (14 tactics)

#### AI/ML (Conditional)
- **Badge Color**: Purple
- **Scope**: AI/ML architectures only
- **Trigger**: Detected services like Lambda, SageMaker, ML APIs
- **Risks**: 46 AI/ML risks (ARC Framework)
- **Controls**: 88 AI-specific controls
- **Source**: MITRE ATLAS (14 tactics, 146 techniques)

#### Cloud Generic (Conditional)
- **Badge Color**: Teal
- **Scope**: Cloud architectures
- **Trigger**: Detected cloud services (S3, EC2, IAM, etc.)
- **Status**: ⚠️ Partial implementation
- **Limitations**: Uses MITRE Enterprise (not cloud-specific)

### Dynamic UI Behavior
- **AI/ML tab**: Only visible if AI/ML pattern detected
- **Progress stages**: AI/ML stage only appears if applicable
- **Pattern cards**: Color-coded by pattern type

---

## Real-Time Progress

### SSE Event Stream
The dashboard uses Server-Sent Events (SSE) for real-time updates:

```javascript
// Event types:
progress         → Stage updates (parsing, mitre, rapids, ai_ml, validation)
patterns_detected → Which patterns apply and why
threat_scores    → Risk scores grouped by pattern
attack_path      → Attack paths discovered (streamed as found)
complete         → Final analysis result
error            → Error occurred
```

### Progress Stages

| Stage | Progress | Duration | Message |
|-------|----------|----------|---------|
| Parsing | 0-10% | ~1s | "Parsing architecture diagram..." |
| MITRE | 10-20% | ~2s | "Loading MITRE ATT&CK cache (44MB)..." |
| RAPIDS | 20-60% | ~15s | "Running RAPIDS threat assessment..." |
| AI/ML | 60-80% | ~10s | "Analyzing AI/ML risks (ATLAS + ARC)..." (if applicable) |
| Validation | 80-100% | ~5s | "Running completeness validation..." |

**Total Time**: ~30 seconds (without AI/ML) or ~45 seconds (with AI/ML)

---

## Tab Descriptions

### 📊 Overview Tab
**Purpose**: High-level threat summary

**Features**:
- Threat heat map (bar chart) showing RAPIDS risk scores
- Color-coded by risk level:
  - Red: High risk (70+)
  - Orange: Medium risk (50-69)
  - Blue: Low risk (<50)
- Architecture diagram (Mermaid rendering)

### 🧩 Patterns Tab
**Purpose**: Understand which threat patterns were applied

**Features**:
- Pattern cards with color-coded borders
- Status badges (✓ Applied, ⚠️ Partial)
- Scope (universal vs conditional)
- Trigger information (why pattern was applied)
- Limitations (for partial implementations)

**Example**:
```
┌─────────────────────────────────────────┐
│ ✅ MITRE ATT&CK + RAPIDS                │
│ ─────────────────────────────────────── │
│ Scope: Universal (Always Applied)       │
│ Status: ✓ Analysis Complete             │
│                                          │
│ Coverage:                                │
│ • 6 RAPIDS threat categories            │
│ • 14 MITRE Enterprise tactics           │
│ • 196 techniques mapped                 │
│ • 42 controls recommended               │
└─────────────────────────────────────────┘
```

### 🎯 Attacks Tab
**Purpose**: Visualize attack paths

**Features**:
- Left pane: Attack paths list (clickable)
- Right pane: Attack path details
- Shows: Entry → Target path
- Displays: Hop count, techniques, criticality

### 🛡️ Controls Tab
**Purpose**: Review security controls

**Features**:
- Left pane: Controls table (present/missing)
- Right pane: Control recommendations
- Priority levels (HIGH, MEDIUM, LOW)

### 📋 MITRE Tab
**Purpose**: MITRE ATT&CK technique coverage

**Features**:
- Technique matrix (tactics × techniques)
- Coverage indicators (✓ covered, ⚠️ partial, ✗ missing)

### 🤖 AI/ML Tab (Conditional)
**Purpose**: AI/ML specific risk analysis

**Visibility**: Only shown if AI/ML pattern detected

**Features**:
- AI/ML risk heat map (ARC Framework)
- AI-specific control recommendations
- ATLAS technique coverage

### 📄 Reports Tab
**Purpose**: Access generated reports

**Features**:
- Left pane: Report list
- Right pane: Report preview (Markdown rendered as HTML)

### 💾 Raw Data Tab
**Purpose**: View raw analysis artifacts

**Features**:
- Left pane: Artifact list (ground_truth.json, reports/*.md)
- Right pane: Syntax-highlighted viewer
- JSON with syntax highlighting
- Markdown rendered as HTML or raw text

---

## Theme System

### Dark Theme (Default)
- Background: Dark gray (#1a1a1a)
- Cards: Medium gray (#2c3e50)
- Text: Light gray (#ecf0f1)
- Accent: Blue (#3498db)

### Light Theme
- Background: White (#ffffff)
- Cards: White with shadow
- Text: Dark gray (#2c3e50)
- Accent: Blue (#3498db)

### Switching Themes
- Click 🌙/☀️ button in header
- Preference saved in localStorage
- Persists across sessions

---

## Browser Compatibility

**Tested**:
- Chrome 120+
- Firefox 121+
- Edge 120+
- Safari 17+

**Required Features**:
- ES6 JavaScript
- CSS Grid
- Fetch API
- localStorage
- Server-Sent Events (SSE)

---

## API Integration

### Authentication
The dashboard prompts for TM-API-KEY on first use and stores it in localStorage.

**To set API key manually**:
```javascript
localStorage.setItem('tm_api_key', 'your-key-here');
```

### Endpoints Used
- `POST /api/v1/analyze-stream` - SSE streaming analysis
- `GET /health` - Health check
- `GET /static/*` - Static assets (CSS, JS)

---

## Troubleshooting

### Dashboard Not Loading
**Symptom**: Blank page or 404 error  
**Solution**: Ensure static files exist in `chatbot/api/static/`

### SSE Connection Fails
**Symptom**: "Connection failed" error  
**Solution**: Check API key, verify server is running

### No Progress Updates
**Symptom**: Progress bar stuck at 0%  
**Solution**: Check browser console for JavaScript errors

### Theme Not Switching
**Symptom**: Theme toggle doesn't work  
**Solution**: Check if localStorage is enabled in browser

### Analysis Fails
**Symptom**: "Analysis failed" error  
**Solution**: Check file is valid .mmd format, < 10MB

---

## Developer Notes

### File Structure
```
chatbot/api/static/
├── index.html              # Main dashboard HTML
├── css/
│   ├── dashboard.css       # Layout styles
│   └── themes.css          # Dark/light themes
└── js/
    ├── dashboard.js        # Main controller
    ├── sse-client.js       # SSE connection manager
    ├── visualizations.js   # Chart.js helpers
    ├── artifact-viewer.js  # JSON/MD viewer
    └── theme-toggle.js     # Theme switcher
```

### External Dependencies (CDN)
- Chart.js 4.4.0 - Threat visualizations
- marked.js 9.1.6 - Markdown rendering
- highlight.js 11.9.0 - Syntax highlighting

### Customization

**Change colors**:
Edit `chatbot/api/static/css/themes.css`

**Add new tab**:
1. Add nav button in `index.html`
2. Add tab pane in `index.html`
3. Add load handler in `dashboard.js`

**Modify charts**:
Edit `visualizations.js` and chart rendering in `dashboard.js`

---

## Performance

### Page Load Time
- Initial load: <1 second
- Static assets: ~50KB (CSS + JS)
- External libraries: ~200KB (cached by CDN)

### Analysis Time
- Small architecture (<10 components): ~20 seconds
- Medium architecture (10-30 components): ~30 seconds
- Large architecture (30+ components): ~45 seconds
- With AI/ML detection: +10-15 seconds

### Memory Usage
- Dashboard: ~10MB
- Analysis in progress: +50MB (MITRE cache)
- Total: ~60MB

---

## Next Steps (PHASE 2)

**Planned Enhancements**:
1. ✅ Interactive attack path diagrams (vis.js)
2. ✅ MITRE ATT&CK matrix view (interactive table)
3. ✅ Mermaid diagram rendering in Overview tab
4. ✅ Export functionality (download reports as PDF)
5. ✅ Historical analysis comparison
6. ✅ Control effectiveness scoring
7. ✅ Risk trend visualization over time

**Timeline**: PHASE 2 (+5-6 hours)

---

## Support

**Documentation**:
- API Guide: docs/API_INTEGRATION_GUIDE.md
- OpenAPI Docs: http://localhost:8000/docs

**Logs**:
- Server logs: `api.log`
- Browser console: F12 → Console tab

**Version**: 1.0 (PHASE 1 Complete)  
**Status**: ✅ Production Ready for demo and integration testing
