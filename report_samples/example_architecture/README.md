# Threat Assessment Report: 01_minimal_vulnerable

## Report Structure

```
01_minimal_vulnerable/
├── README.md                    # This file
├── ground_truth.json           # Raw assessment data
├── 01_executive_summary.md     # For decision-makers
├── 02_technical_report.md      # For security engineers
├── 03_action_plan.md           # For project managers
├── before.mmd                  # Current architecture (Mermaid)
└── after.mmd                   # Recommended improvements (Mermaid)
```

## Quick Start

### View Reports

1. **Executive Summary** - For business stakeholders
   - Risk level: 91/100
   - Decision: APPROVE IMMEDIATELY
   - Read: `01_executive_summary.md`

2. **Technical Report** - For security engineers
   - MITRE techniques, attack paths, RAPIDS assessment
   - Read: `02_technical_report.md`

3. **Action Plan** - For implementation teams
   - Phased roadmap, resource allocation, timeline
   - Read: `03_action_plan.md`

### Visualize Architecture

#### Before (Current State)
```bash
# View with Mermaid viewer
cat before.mmd

# Or render at: https://mermaid.live/
```

#### After (With Recommended Controls)
```bash
# View improved architecture
cat after.mmd

# Green hexagons = Recommended new controls
```

## Key Metrics

| Metric | Value |
|--------|-------|
| **Risk Score** | 91/100 (higher = worse) |
| **Defensibility** | 16/100 (higher = better) |
| **Controls Present** | 0 |
| **Critical Gaps** | 17 |
| **Attack Paths** | 2 identified |

## RAPIDS Threat Assessment

- 🔴 **Application Vulns**: Risk 80/100, Def 10/100
- 🔴 **Ransomware**: Risk 70/100, Def 20/100
- 🔴 **Dos**: Risk 70/100, Def 10/100
- 🟠 **Phishing**: Risk 60/100, Def 10/100
- 🟠 **Supply Chain**: Risk 60/100, Def 30/100
- 🟠 **Insider Threat**: Risk 50/100, Def 20/100


## Top 3 Recommendations

1. Implement **LEAST PRIVILEGE**
2. Implement **RATE LIMITING**
3. Implement **LOGGING**


## Generated

- **Date**: 2026-05-10 10:12 UTC
- **Engine**: parser
- **Architecture Type**: web_app

## Visual Improvements (Before → After)

The `after.mmd` diagram shows **where and how** to integrate recommended controls:

- 🟢 **Least Privilege**: Deploy as additional security layer
- 🟢 **Rate Limiting**: Protect application layer before web server
- 🟢 **Logging**: Collect logs from web servers and databases
- 🟢 **Patching**: Deploy as additional security layer
- 🟢 **User Training**: Deploy as additional security layer


**Legend:**
- Solid lines (→): Data/traffic flow
- Dotted lines (-.->): Monitoring/replication
- Green nodes (🟢): Recommended new controls

## Next Steps

1. Review executive summary with leadership
2. Assess technical report with security team
3. Plan implementation using action plan roadmap
4. **Visualize improvements with before/after diagrams** to understand placement
