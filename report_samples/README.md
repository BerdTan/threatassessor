# Sample Reports

This folder contains example outputs from the threat assessment system for reference.

## Example Architecture

Based on **01_minimal_vulnerable** - a truly vulnerable baseline with 3 nodes and 0 security controls.

**Before:** Internet → Web Server → Database (fully exposed)  
**After:** 16 recommended controls with MITRE mapping

### Files

- **before.mmd** - Input architecture diagram
- **after.mmd** - Generated diagram with 17 recommended controls
- **01_executive_summary.md** - Business summary with ROI
- **02_technical_report.md** - MITRE mapping + attack paths
- **03_action_plan.md** - 8-week implementation roadmap

### Key Features in after.mmd

The generated diagram includes:

1. **MITRE Technique IDs (T####)**
   - Shows what attacks each control prevents/detects
   - Example: `Prevents: T1190, T1203` (Exploit Public-Facing App, Exploitation for Client Execution)

2. **MITRE Mitigation IDs (M####)**
   - Maps controls to MITRE mitigation catalog
   - Example: `MITRE: M1037, M1050` (Filter Network Traffic, Exploit Protection)

3. **Attack Path Indicators (#1, #2, #3)**
   - Shows which attack paths each control protects
   - Correlates with attack path analysis in technical report

4. **Control Types**
   - Prevention: WAF, MFA, Input Validation, Rate Limiting
   - Detection: Logging, Audit Log, Behavioral Analysis
   - Isolation: Network Segmentation, Least Privilege
   - Response: Backup, Patching, EDR

5. **Visual Elements**
   - Green controls with black text (high contrast)
   - Solid arrows: inline controls (WAF → ALB)
   - Dotted arrows: monitoring/policy controls (Logging, Least Privilege)
   - Shape variations: [ ] prevention, / / detection, ( ) recovery

### What's Different from Manual Diagrams

**Automated Features:**
- ✅ Exhaustive MITRE coverage (100% of applicable techniques)
- ✅ Path-based placement (controls placed where attack paths need them)
- ✅ Multi-path controls (MFA on all entry points if needed)
- ✅ Dynamic control count (stops at 100% coverage, typically 15-17)
- ✅ Quantitative justification (residual risk BEFORE/AFTER)

**Not Just Visual:**
- Each control links to ground_truth.json with full analysis
- Recommendations prioritized by Prevention + DIR framework (40/30/20/10)
- Cost estimates and ROI calculation in action plan
- 8-week implementation roadmap with milestones

## Usage

```bash
# View the sample
cd report_samples/example_architecture/
cat 01_executive_summary.md

# Generate your own
python3 -m chatbot.main --gen-arch-truth your_architecture.mmd

# Output appears in report/your_architecture/
```

## Notes

- This is a static snapshot for reference
- Your actual output will vary based on your architecture
- All 22 test architectures in `tests/data/architectures/` have generated reports
- Run `./demo_architecture.sh` to see live generation
