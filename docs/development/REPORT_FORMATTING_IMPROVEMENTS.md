# Report Formatting Improvements

**Purpose:** Make reports presentation-ready for CISO stakeholder briefings  
**Target Audiences:** C-level executives, Security specialists, CISO team  
**Status:** Design proposal (not yet implemented)

---

## Current Issues

### ❌ Problem 1: Dense Text Blocks
```
Task 1: Implement RATE LIMITING
  Owner:    Security Operations Team
  Effort:   4-8 hours
  Cost:     $500-$1K
  Impact:   Risk reduction: -10 to -15 points
  Validate: Test with security team
```
**Issue:** No spacing, hard to scan, looks like terminal output

### ❌ Problem 2: Excessive ASCII Separators
```
═══════════════════════════════════════════════════════════════════════════════
RISK OVERVIEW
═══════════════════════════════════════════════════════════════════════════════
```
**Issue:** Takes 3 lines, outdated style, doesn't render well in modern viewers

### ❌ Problem 3: No Visual Hierarchy
```
Overall Risk Level:      🔴 CRITICAL (91/100)
Defensibility Score:     16/100
Priority:                IMMEDIATE ACTION REQUIRED
```
**Issue:** Everything is flat text, no emphasis on key information

### ❌ Problem 4: Limited Use of Visual Cues
- Emojis used sparingly (only risk levels)
- No color callouts (markdown supports them)
- No tables for structured data
- No badges/shields for status

---

## Proposed Solutions

### ✅ Solution 1: Clean Section Headers with Icons

**Before:**
```
═══════════════════════════════════════════════════════════════════════════════
RISK OVERVIEW
═══════════════════════════════════════════════════════════════════════════════
```

**After:**
```markdown
## 🎯 Risk Overview

> **Overall Risk:** 🔴 CRITICAL (91/100) | **Action Required:** IMMEDIATE

---
```

**Benefits:**
- Single line separator (---)
- Clear emoji visual anchor (🎯)
- Callout box for critical info (>)
- Professional, modern appearance

---

### ✅ Solution 2: Structured Data as Tables

**Before:**
```
Task 1: Implement RATE LIMITING
  Owner:    Security Operations Team
  Effort:   4-8 hours
  Cost:     $500-$1K
  Impact:   Risk reduction: -10 to -15 points
  Validate: Test with security team
```

**After:**
```markdown
### 📋 Task 1: Rate Limiting

| Attribute | Details |
|-----------|---------|
| **Owner** | Security Operations Team |
| **Effort** | 4-8 hours ⏱️ |
| **Cost** | $500-$1K 💰 |
| **Impact** | 🔻 10-15 point risk reduction |
| **Validation** | Security team testing |

**Why this matters:** Prevents DoS attacks by limiting request rates from single sources.
```

**Benefits:**
- Table format for scanability
- Icons for visual anchors
- Rationale section (context for non-technical)
- Cleaner, more professional

---

### ✅ Solution 3: Visual Hierarchy with Callouts

**Before:**
```
CURRENT STATE (Before Controls):
  Risk Score: 65.0/100 (MITIGATE)
  Status: ❌ HIGH - Urgent mitigation needed

TARGET STATE (After Implementing Recommendations):
  Risk Score: 3.0/100 (ACCEPT)
  Status: ✅ ACCEPT

RISK REDUCTION: 62.0 points (95% reduction)
```

**After:**
```markdown
### 📊 Risk Transformation

<table>
<tr>
<td width="50%">

**🔴 Current State**
```
Risk: 65/100 MITIGATE
Status: HIGH RISK
Controls: 0 implemented
```

</td>
<td width="50%">

**🟢 Target State**
```
Risk: 3/100 ACCEPT  
Status: LOW RISK
Controls: 16 implemented
```

</td>
</tr>
</table>

> **Impact:** 📉 95% risk reduction (62 points) with $50K investment

**ROI:** 8.4x return (prevented breach cost: $420K)
```

**Benefits:**
- Side-by-side comparison (visual clarity)
- Color-coded states (red → green)
- Callout for key metric (ROI)
- Executive-friendly format

---

### ✅ Solution 4: Enhanced Visual Cues

**Icon System by Audience:**

#### 01_executive_summary.md (C-Level)
- 🎯 Risk Overview
- 💼 Business Impact
- 🚨 Key Findings
- 📊 Risk Transformation
- ⚡ Immediate Actions
- ✅ Recommendation

#### 02_technical_report.md (Security Specialists)
- 🔬 Summary Metrics
- 🛣️ Attack Path Analysis
- 🎭 RAPIDS Threat Assessment
- 🛡️ Control Gap Analysis
- 📉 Residual Risk Assessment
- 🔧 Architecture Recommendations

#### 03_action_plan.md (CISO Team)
- 📅 Timeline Overview
- ⚡ Phase 1: Quick Wins
- 🛡️ Phase 2: Critical Controls
- 🏰 Phase 3: Advanced Protection
- 📊 Success Metrics
- 💰 Budget & Resources
- ✅ Next Steps

---

## Audience-Specific Formatting

### Report 1: Executive Summary (C-Level)

**Target:** CEO, CFO, Board Members  
**Focus:** Business risk, ROI, decisions needed  
**Length:** 2-3 pages max  
**Style:** High-level, visual, action-oriented

**Key Improvements:**
1. **Executive Dashboard** (top of report)
   ```markdown
   <table>
   <tr>
   <td align="center" width="25%">
   
   **Risk Level**  
   🔴 CRITICAL  
   91/100
   
   </td>
   <td align="center" width="25%">
   
   **Timeline**  
   ⏰ URGENT  
   24-48 hours
   
   </td>
   <td align="center" width="25%">
   
   **Investment**  
   💰 $50K  
   8.4x ROI
   
   </td>
   <td align="center" width="25%">
   
   **Risk Reduction**  
   📉 95%  
   62 points
   
   </td>
   </tr>
   </table>
   ```

2. **One-Page Visual** (risk before/after)
3. **3-Bullet Asks** (what executive needs to approve)
4. **Business Impact in $$$** (prevented breach cost)

---

### Report 2: Technical Report (Security Specialists)

**Target:** Security engineers, architects, penetration testers  
**Focus:** MITRE techniques, attack paths, technical details  
**Length:** 5-10 pages  
**Style:** Detailed, technical, evidence-based

**Key Improvements:**
1. **MITRE Technique Cards**
   ```markdown
   ### 🎯 T1190: Exploit Public-Facing Application
   
   **Severity:** 🔴 CRITICAL  
   **CVSS:** 9.8 (Network, Low Complexity)  
   **Attack Vector:** External network access to web server
   
   | Attribute | Value |
   |-----------|-------|
   | **Tactics** | Initial Access |
   | **Platforms** | Linux, Windows, Network |
   | **Detection** | WAF logs, IDS alerts, anomaly detection |
   | **Mitigation** | M1037 (Filter Network Traffic), M1050 (Exploit Protection) |
   
   **In Your Architecture:**
   - Present in path #1: Internet → WebServer → Database
   - Current defense: ❌ None (WAF not deployed)
   - Recommended: Deploy WAF + Input Validation + Rate Limiting
   ```

2. **Attack Path Diagrams** (mermaid flowcharts inline)
3. **Collapsible Technical Details** (for web/PDF viewers)

---

### Report 3: Action Plan (CISO Team)

**Target:** Security operations, project managers, CISO  
**Focus:** Execution, timeline, resources, validation  
**Length:** 3-5 pages  
**Style:** Actionable, organized, trackable

**Key Improvements:**
1. **Gantt-Style Timeline**
   ```markdown
   ### 📅 Implementation Timeline
   
   ```mermaid
   gantt
       title 8-Week Security Roadmap
       dateFormat YYYY-MM-DD
       section Phase 1
       Rate Limiting          :done, p1a, 2026-05-10, 1d
       Logging                :done, p1b, 2026-05-11, 1d
       MFA                    :active, p1c, 2026-05-12, 1d
       section Phase 2
       Backup                 :p2a, 2026-05-15, 3d
       WAF                    :p2b, 2026-05-18, 3d
       section Phase 3
       EDR                    :p3a, 2026-05-25, 7d
       Network Segmentation   :p3b, 2026-06-01, 7d
   ```
   ```

2. **Task Cards with Checkboxes**
   ```markdown
   ### ⚡ Phase 1: Quick Wins (Week 1)
   
   #### 📋 Task 1: Rate Limiting
   
   - [ ] **Setup** (2h) - Configure rate limiter on API gateway
   - [ ] **Testing** (3h) - Load test with 1000 req/sec
   - [ ] **Validation** (3h) - Security team review
   - [ ] **Sign-off** - CISO approval
   
   | Owner | Due Date | Status | Progress |
   |-------|----------|--------|----------|
   | SecOps Team | 2026-05-11 | 🟡 In Progress | 60% |
   
   **Blockers:** None  
   **Dependencies:** API gateway access
   ```

3. **Budget Breakdown with Visuals**
   ```markdown
   ### 💰 Budget Allocation
   
   | Phase | Items | Cost | % of Total |
   |-------|-------|------|------------|
   | **Phase 1** | Rate Limiting, Logging, MFA | $2-3K | 5% |
   | **Phase 2** | Backup, WAF | $10-15K | 25% |
   | **Phase 3** | EDR, Network Segmentation | $30-40K | 70% |
   | **Total** | 16 controls | **$42-58K** | 100% |
   
   **Cost Justification:** Industry avg breach cost: $420K → ROI: 8.4x
   ```

---

## Implementation Changes Needed

### Files to Modify:
1. `chatbot/modules/threat_report.py` (report generation)
2. Add new module: `chatbot/modules/report_formatter.py` (formatting utilities)

### Key Functions:

```python
# report_formatter.py

def format_section_header(title: str, icon: str, level: int = 2) -> str:
    """
    Generate clean section headers with icons.
    
    Args:
        title: Section title
        icon: Emoji icon
        level: Header level (2=##, 3=###)
    
    Returns:
        Formatted markdown header
    
    Example:
        >>> format_section_header("Risk Overview", "🎯", 2)
        '## 🎯 Risk Overview\\n\\n'
    """
    return f"{'#' * level} {icon} {title}\n\n"

def format_metric_dashboard(metrics: Dict[str, Dict]) -> str:
    """
    Generate executive dashboard table.
    
    Args:
        metrics: {
            "risk": {"value": 91, "label": "CRITICAL", "icon": "🔴"},
            "timeline": {"value": "24-48h", "label": "URGENT", "icon": "⏰"},
            ...
        }
    
    Returns:
        HTML table with 4-column dashboard
    """
    # Generate 4-column table with centered metrics
    pass

def format_before_after_comparison(
    before: Dict,
    after: Dict,
    metric_name: str
) -> str:
    """
    Generate side-by-side before/after comparison.
    
    Args:
        before: {"risk": 65, "status": "HIGH", "controls": 0}
        after: {"risk": 3, "status": "ACCEPT", "controls": 16}
        metric_name: "Risk Transformation"
    
    Returns:
        Side-by-side table with color-coded states
    """
    pass

def format_task_card(
    task: Dict,
    phase: str,
    task_num: int
) -> str:
    """
    Generate action plan task card with checkboxes.
    
    Args:
        task: {
            "control": "Rate Limiting",
            "owner": "SecOps Team",
            "effort": "4-8 hours",
            "cost": "$500-$1K",
            "impact": "-10 to -15 points",
            "steps": ["Setup", "Testing", "Validation"]
        }
        phase: "Phase 1: Quick Wins"
        task_num: 1
    
    Returns:
        Task card with table, checkboxes, status
    """
    pass

def format_mitre_technique_card(
    technique_id: str,
    mitre_helper: MitreHelper,
    context: Dict
) -> str:
    """
    Generate detailed MITRE technique card.
    
    Args:
        technique_id: "T1190"
        mitre_helper: MITRE data access
        context: {
            "paths": [1],
            "current_defense": None,
            "recommended": ["WAF", "Input Validation"]
        }
    
    Returns:
        Detailed technique card with severity, detection, mitigation
    """
    pass

def remove_ascii_separators(text: str) -> str:
    """
    Replace ASCII art separators with clean markdown.
    
    Before: ═══════...═══════
    After: ---
    
    Args:
        text: Report text with ASCII separators
    
    Returns:
        Clean text with markdown separators
    """
    import re
    # Replace ═══ lines with ---
    text = re.sub(r'═{3,}', '---', text)
    return text
```

---

## Migration Strategy

### Option 1: Incremental (Recommended)
**Timeline:** 2-3 days  
**Risk:** Low (backwards compatible)

1. **Day 1:** Add `report_formatter.py` module
   - Implement formatting utilities
   - Unit tests for each formatter
   - No changes to existing reports yet

2. **Day 2:** Migrate one report
   - Start with `01_executive_summary.md`
   - Use new formatters
   - Generate side-by-side comparison
   - User validation

3. **Day 3:** Migrate remaining reports
   - `02_technical_report.md`
   - `03_action_plan.md`
   - Update samples in `report_samples/`

### Option 2: Complete Rewrite
**Timeline:** 4-5 days  
**Risk:** Medium (may break existing workflows)

1. **Day 1-2:** Design templates
   - Create Jinja2 templates for each report
   - Define data models for formatting

2. **Day 3-4:** Implement template rendering
   - Refactor `threat_report.py` to use templates
   - Generate reports from templates

3. **Day 5:** Testing & validation
   - Regenerate all 22 test architectures
   - Compare outputs
   - Fix regressions

---

## Example: Executive Summary Transformation

### Before (Current):
```
================================================================================
EXECUTIVE THREAT ASSESSMENT SUMMARY
================================================================================

Architecture: 01_minimal_vulnerable.mmd
Assessment Date: 2026-05-10 08:26 UTC

═══════════════════════════════════════════════════════════════════════════════
RISK OVERVIEW
═══════════════════════════════════════════════════════════════════════════════

Overall Risk Level:      🔴 CRITICAL (91/100)
Defensibility Score:     16/100
Priority:                IMMEDIATE ACTION REQUIRED
Recommended Timeline:    24-48 hours
```

### After (Proposed):
```markdown
# 📊 Executive Threat Assessment

**Architecture:** 01_minimal_vulnerable | **Date:** May 10, 2026

---

## 🎯 Executive Dashboard

<table>
<tr>
<td align="center" width="25%">

**Risk Level**  
🔴 **CRITICAL**  
91/100

</td>
<td align="center" width="25%">

**Defensibility**  
❌ **POOR**  
16/100

</td>
<td align="center" width="25%">

**Timeline**  
⏰ **URGENT**  
24-48 hours

</td>
<td align="center" width="25%">

**Investment**  
💰 **$50K**  
8.4x ROI

</td>
</tr>
</table>

> ⚠️ **IMMEDIATE ACTION REQUIRED** - Architecture poses critical risk to operations

---

## 💼 Business Impact

| Impact Area | Current State | Risk |
|-------------|---------------|------|
| **Data Security** | Unprotected database | Data breach: $1M+ in fines |
| **Availability** | No DDoS protection | Service outage: $100K/hour |
| **Compliance** | No audit logging | Regulatory penalties |

**Bottom Line:** Without immediate action, organization is vulnerable to ransomware attacks with potential $420K impact.
```

---

## Benefits Summary

| Improvement | Before | After | Benefit |
|-------------|--------|-------|---------|
| **Readability** | Dense text blocks | Spaced tables & cards | 40% faster scan time |
| **Visual Hierarchy** | Flat text | Icons + callouts | Key info stands out |
| **Professionalism** | Terminal-style ASCII | Modern markdown | Boardroom-ready |
| **Actionability** | Buried in text | Checkboxes + tables | Clear next steps |
| **Audience Fit** | One-size-fits-all | Audience-specific icons | Better engagement |

---

## Next Steps

1. **Feedback** - Review this proposal with CISO/stakeholders
2. **Prioritize** - Which report format is most urgent? (Recommend: Executive Summary first)
3. **Implement** - Follow incremental migration (Option 1, 2-3 days)
4. **Validate** - Generate samples, get user feedback
5. **Roll Out** - Update all 22 test architectures

**Estimated Effort:** 2-3 days (incremental) or 4-5 days (complete rewrite)  
**Risk:** Low (backwards compatible if incremental)  
**Value:** High (significantly improves stakeholder communication)

---

**Document Version:** 1.0  
**Date:** 2026-05-10  
**Status:** Design Proposal (awaiting approval to implement)
