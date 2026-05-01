# Output Format Guide

The MITRE Chatbot supports 4 display formats tailored for different audiences.

## Quick Reference

| Format | Audience | Use Case | Length |
|--------|----------|----------|--------|
| `executive` | C-level, Board | Business justification, ROI | 1 page |
| `action-plan` | Security Managers | Implementation roadmap | 2-3 pages |
| `technical` | Security Analysts | Detailed analysis, scores | 3-5 pages |
| `all` | Comprehensive Review | Full report with all views | 6-9 pages |

---

## Usage

```bash
# Executive summary (default for leadership)
python3 -m chatbot.main --format executive --query "PowerShell attack"

# Action plan with timeline (default for managers)
python3 -m chatbot.main --format action-plan --query "PowerShell attack"

# Technical details (default for analysts)
python3 -m chatbot.main --format technical --query "PowerShell attack"

# All formats combined
python3 -m chatbot.main --format all --query "PowerShell attack"

# Interactive mode (prompts for query)
python3 -m chatbot.main --format executive

# Verbose mode (show debug logs)
python3 -m chatbot.main --format technical --verbose
```

---

## Format 1: Executive Summary

**Target Audience:** C-level executives, Board members, Business stakeholders

**Purpose:** Business justification and approval

**Content:**
- 🎯 Threat overview (type, risk level, techniques)
- 💰 Business impact (severity, expected loss, time to exploit)
- 🎯 Top 3 immediate actions (with time estimates)
- 📊 ROI analysis (cost, savings, ROI multiplier)
- ✅ Recommendation (approve/defer decision)

**Length:** ~40 lines (~1 page)

**When to Use:**
- Presenting to executives for budget approval
- Board-level security briefings
- Business case for security investments
- Incident response executive updates

**Example Output:**
```
╔══════════════════════════════════════════════════════════════════════════════╗
║                    EXECUTIVE THREAT SUMMARY                                  ║
╚══════════════════════════════════════════════════════════════════════════════╝

🎯 THREAT OVERVIEW
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Threat Type:     Persistence Attack
Risk Level:      ⚠️  MODERATE (52/100)
Techniques:      5 matched
Mitigations:     6 official MITRE controls available
Coverage:        80% (4/5 techniques have official mitigations)

💰 BUSINESS IMPACT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Severity:        MODERATE - Address within 1 week
Expected Loss:   $100K-$1M (if exploited)
Time to Exploit: Days to weeks

🎯 TOP 3 IMMEDIATE ACTIONS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. User Account Management (M1018)
   Time: < 1 day | Addresses: 4 techniques
   Confidence: 74/100

📊 EXPECTED ROI
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Implementation Cost:   ~$2.5K (labor) + $0 (tools)
Implementation Time:   5-7 days (1 FTE)
Risk Reduction:        80% of identified techniques
Expected Savings:      $420K+ (based on prevented breach cost)
ROI:                   ~170x

✅ RECOMMENDATION: APPROVE IMMEDIATELY
```

---

## Format 2: Action Plan

**Target Audience:** Security Managers, CISO, Project Managers

**Purpose:** Implementation roadmap with timeline and assignments

**Content:**
- 📊 Attack path analysis (stages and progression)
- 🔴 Priority 1: Immediate actions (days 1-2)
- ⚠️ Priority 2: Short-term actions (week 1)
- 📅 Implementation roadmap (phased timeline)
- 📊 Success metrics (KPIs and validation)
- 📋 Next steps (checkboxes for tracking)

**Length:** ~100-150 lines (~2-3 pages)

**When to Use:**
- Planning security implementations
- Team assignments and tracking
- Sprint planning for security work
- Progress reporting to management
- Purple team exercise planning

**Key Features:**
- **Phased timeline** (immediate → short-term → long-term)
- **Resource assignments** (SOC, Domain Admin, IAM teams)
- **Validation tests** (how to verify success)
- **Dependencies** (what must happen first)
- **Risk warnings** (potential business impact)

**Example Output:**
```
╔══════════════════════════════════════════════════════════════════════════════╗
║                        SECURITY ACTION PLAN                                  ║
╚══════════════════════════════════════════════════════════════════════════════╝

📊 ATTACK PATH ANALYSIS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Stage 1: EXECUTION
└─> Techniques: T1053.005, T1053, T1086
    Attacker runs PowerShell to create scheduled tasks

⚠️  CRITICAL GAP: Limited detection capability for attack chain

🔴 PRIORITY 1: IMMEDIATE (Days 1-2)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. User Account Management (M1018) - 4-8 hours
   ┌─────────────────────────────────────────────────────────────────┐
   │ What: User Account Management                                   │
   │ Why:  Limit privileges of user accounts and remediate...        │
   │ Impact: Covers 4 techniques (T1053.005, T1484.001, T1053)      │
   │ Confidence: 74/100 (Ease: 0.90, ROI: 0.38)                     │
   │ Owner: Security Operations / Domain Admin Team                  │
   │ Validate: Test with red team simulation                         │
   └─────────────────────────────────────────────────────────────────┘

📅 IMPLEMENTATION ROADMAP
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PHASE 1: IMMEDIATE (Week 1)
├─ Day 1-2: Implement 2 quick-win mitigations
└─ Day 2-3: Test and validate with security team

PHASE 2: SHORT-TERM (Weeks 2-3)
├─ Week 2: Business approval for privilege changes
└─ Week 4: Purple team validation exercise

📋 NEXT STEPS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[ ] Day 1: Implement User Account Management (4-8 hrs)
[ ] Day 2: Implement Operating System Configuration (4-8 hrs)
[ ] Day 2: Test detection rules with red team simulation
[ ] Week 2: Obtain executive approval for privilege changes
```

---

## Format 3: Technical Details

**Target Audience:** Security Analysts, SOC Operators, Threat Hunters

**Purpose:** Detailed technical analysis with scores and evidence

**Content:**
- 📊 Matched techniques (with similarity scores)
- 🎯 Detailed scoring breakdown (Accuracy, Relevance, Confidence)
- 🎯 Attack path analysis (narrative + stages)
- 🛡️ Official MITRE mitigations (with specific guidance)
- 📈 Coverage statistics
- 🎯 Prioritized actions (LLM-enhanced)
- ⚡ Quick wins

**Length:** ~150-250 lines (~3-5 pages)

**When to Use:**
- Deep dive threat analysis
- Incident investigation
- Threat intelligence research
- MITRE ATT&CK mapping exercises
- Security tool tuning (detection rules)

**Key Features:**
- **Source attribution** (MITRE vs LLM)
- **Score breakdowns** (sub-components explained)
- **Similarity scores** (semantic match confidence)
- **External references** (research links)
- **Detailed tactics** (kill chain phases)

**Example Output:**
```
================================================================================
THREAT ASSESSMENT RESULTS (Semantic Mode)
================================================================================

📊 MATCHED TECHNIQUES:

1. T1053.005 - Scheduled Task
   Similarity: 0.534 | LLM Confidence: N/A
   Relevance: N/A
   Tactics: execution, persistence, privilege-escalation

   SCORES:
   • Accuracy:   40.5/100  (Source: llm_speculative)
   • Relevance:  68.0/100  (Impact: 0.80, Resistance: 0.50)
   • Confidence: 68.0/100
   • COMPOSITE:  57.0/100  ⚠️  MODERATE

🛡️  OFFICIAL MITRE MITIGATIONS (Authoritative):

1. User Account Management (M1018)
   Addresses: T1053.005, T1484.001, T1053, T1197
   CONFIDENCE SCORE: 74.3/100  ⚠️  MODERATE EFFORT
     (Ease: 0.90 | ROI: 0.38 | Effectiveness: 1.00)
   Example (T1053.005): Limit privileges of user accounts...
   → https://attack.mitre.org/mitigations/M1018

📈 COVERAGE STATS:
   • Techniques with official mitigations: 4
   • Techniques without mitigations: 1
   • Total MITRE mitigations: 6
   • LLM enrichment applied: No
```

---

## Format 4: All (Comprehensive Report)

**Target Audience:** Comprehensive review, documentation, audits

**Purpose:** Complete analysis for records and handoff

**Content:**
- All three formats combined in order:
  1. Executive Summary
  2. Action Plan
  3. Technical Details

**Length:** ~300-400 lines (~6-9 pages)

**When to Use:**
- Formal security assessments
- Audit documentation
- Handoff to external consultants
- Comprehensive incident reports
- Security posture reviews

**Example:**
```bash
python3 -m chatbot.main --format all --query "Ransomware attack" > report.txt
```

---

## Comparison Table

| Feature | Executive | Action Plan | Technical | All |
|---------|-----------|-------------|-----------|-----|
| **Risk level** | ✅ | ✅ | ✅ | ✅ |
| **ROI calculation** | ✅ | ❌ | ❌ | ✅ |
| **Implementation timeline** | ❌ | ✅ | ❌ | ✅ |
| **Resource assignments** | ❌ | ✅ | ❌ | ✅ |
| **Detailed scores** | ❌ | ❌ | ✅ | ✅ |
| **MITRE references** | ❌ | ❌ | ✅ | ✅ |
| **Source attribution** | ❌ | ❌ | ✅ | ✅ |
| **Checkboxes for tracking** | ❌ | ✅ | ❌ | ✅ |

---

## Customization Tips

### Suppress Debug Logs

By default, INFO/WARNING logs are hidden. For debugging:
```bash
python3 -m chatbot.main --format technical --verbose
```

### Redirect to File

```bash
# Save executive summary for presentation
python3 -m chatbot.main --format executive --query "Phishing attack" > exec_summary.txt

# Save action plan for tracking
python3 -m chatbot.main --format action-plan --query "Ransomware" > action_plan.md

# Save technical analysis for investigation
python3 -m chatbot.main --format technical --query "Lateral movement" > analysis.txt
```

### Batch Processing

```bash
# Process multiple scenarios
for scenario in "PowerShell" "Ransomware" "Phishing"; do
    python3 -m chatbot.main --format executive --query "$scenario" > "${scenario}_exec.txt"
done
```

---

## Best Practices

### For Executives
- Use `--format executive` always
- Focus on: Risk level, Expected loss, ROI
- Key question: "What's the business impact?"

### For Managers
- Use `--format action-plan` for implementation
- Track checkboxes for progress
- Key question: "Who does what, and when?"

### For Analysts
- Use `--format technical` for investigations
- Enable `--verbose` when debugging
- Key question: "What's the evidence?"

### For Documentation
- Use `--format all` for comprehensive records
- Save to file with timestamp
- Key question: "What did we know and when?"

---

## Output Length Estimates

| Format | Lines | Pages (at 50 lines/page) | Time to Read |
|--------|-------|--------------------------|--------------|
| Executive | ~40 | 1 | 2-3 minutes |
| Action Plan | 100-150 | 2-3 | 5-7 minutes |
| Technical | 150-250 | 3-5 | 10-15 minutes |
| All | 300-400 | 6-9 | 15-20 minutes |

---

## Future Enhancements

Planned additions:
- `--format json` - Machine-readable output for SIEM integration
- `--format pdf` - Formatted PDF reports
- `--format csv` - Spreadsheet export for tracking
- `--format markdown` - GitHub-compatible documentation

---

*Last Updated: 2026-05-01*
