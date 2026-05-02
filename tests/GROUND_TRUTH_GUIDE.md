# Ground Truth Generation Guide

## Overview

Ground truth labels are human-validated expected results used to test algorithm accuracy. This guide shows how to generate ground truth for new architecture diagrams.

## Current Status

**Completed:** 7/21 architectures (33%)  
**Validation:** 96.7% F1 score on control detection  
**Time Investment:** 3 hours manual (7 files), ~2 hours automated (remaining 14)

---

## Process Comparison

### Manual Process (Original - 30 min per file)

**Steps:**
1. Read `.mmd` file to understand topology
2. Manually identify security controls
3. Trace attack paths by walking graph
4. Map MITRE ATT&CK techniques to each path
5. Assess RAPIDS risk scores (ransomware, phishing, etc.)
6. Write JSON (80-120 lines)

**Time:** 20-45 minutes per architecture  
**Accuracy:** High (human expert judgment)  
**Scalability:** Poor (doesn't scale beyond 10-20 files)

---

### Semi-Automated Process (New - 10 min per file)

**Steps:**
1. Run generator: `python3 tests/generate_ground_truth.py <file>.mmd`
2. LLM generates initial labels (30-60 sec)
3. Review generated JSON
4. Validate/correct if needed
5. Save and auto-validate

**Time:** 5-15 minutes per architecture (60-70% time savings)  
**Accuracy:** High (LLM + human validation)  
**Scalability:** Good (can process 14 remaining files in 2-3 hours)

---

## Quick Start: Generate Single Ground Truth

### Prerequisites

```bash
# Ensure LLM client configured
cat .env | grep OPENROUTER_API_KEY

# Activate virtual environment
source .venv/bin/activate
```

### Generate for New Architecture

```bash
# Example: Generate ground truth for Azure 3-tier
python3 tests/generate_ground_truth.py tests/data/architectures/06_azure_3tier.mmd
```

**Output:**
```
📊 Parsed Architecture:
   Nodes: 8
   Edges: 7
   Subgraphs: 3
   Auto-detected controls: ['load balancer', 'network segmentation', 'waf']

🤖 Generating initial labels with LLM...
   (This may take 30-60 seconds)

================================================================================
GENERATED GROUND TRUTH - REVIEW & VALIDATE
================================================================================
{
  "architecture": "06_azure_3tier.mmd",
  "description": "Azure 3-tier web application with VNet segmentation",
  "controls_present": [
    "load balancer",
    "network segmentation",
    "waf"
  ],
  ...
}
================================================================================

📝 Review the generated labels above.

Options:
  [a] Accept as-is
  [e] Edit JSON manually
  [c] Correct specific fields
  [q] Quit without saving

Your choice: a

✅ Ground truth saved to: tests/data/ground_truth/06_azure_3tier.json

🧪 Running validation test...

✅ Validation passed!
```

---

## Batch Generation: All Remaining Architectures

### Option 1: Automatic (Fast, Requires Review)

Generate all remaining ground truth automatically:

```bash
# Generate for all .mmd files without ground truth
./tests/batch_generate_ground_truth.sh
```

**What it does:**
1. Finds all `.mmd` files without corresponding `.json`
2. Runs generator for each (with validation prompts)
3. Runs full validation suite at end
4. Reports accuracy metrics

**Time:** ~2-3 hours for 14 remaining architectures (10 min each + validation)

### Option 2: Manual Review (Slower, Higher Accuracy)

Generate one at a time with careful review:

```bash
# Process in order of complexity (simple → complex)
for arch in 04 06 07 08 09 12 13 14 15 16 17 18 19 20; do
    python3 tests/generate_ground_truth.py tests/data/architectures/${arch}_*.mmd
    sleep 2  # Pause between generations
done
```

---

## Generator Options

### Skip LLM (Parser Only)

Use only parser + control detection, no LLM:

```bash
python3 tests/generate_ground_truth.py <file>.mmd --no-llm
```

**Use when:**
- LLM unavailable (free tier rate limited)
- Architecture is very simple (minimal attack paths)
- Want to validate parser output only

### Auto-Accept (No Validation Prompt)

Accept LLM output without review (use cautiously):

```bash
python3 tests/generate_ground_truth.py <file>.mmd --auto-accept
```

**Use when:**
- High confidence in LLM output quality
- Batch processing with post-validation review
- Time-constrained (will review later)

### Custom Output Path

```bash
python3 tests/generate_ground_truth.py <file>.mmd --output custom/path.json
```

---

## What Gets Auto-Generated

### 1. Controls (90-95% Accurate)

**Auto-detected by control_detection.py:**
- Perimeter: WAF, firewall, DDoS protection, load balancer
- Authentication: MFA, SSO, IAM
- Network: Segmentation (from subgraphs), DMZ, VPN
- Data: Encryption, backup, cache
- Monitoring: SIEM, logging, audit logs

**LLM adds:**
- Missing controls analysis
- Rationale for each control

### 2. Attack Paths (70-80% Accurate)

**LLM generates:**
- Entry points (Internet, Partners, Admin)
- Target assets (Database, FileServer, etc.)
- Path sequences (node by node)
- MITRE technique IDs (T1190, T1078, etc.)
- Rationale for each path

**Human review needed:**
- Verify node IDs match exactly
- Check path realism (not just BFS shortest path)
- Validate technique mappings

### 3. Risk Scores (60-70% Accurate)

**LLM estimates:**
- Overall risk (0-100)
- Overall defensibility (0-100)
- RAPIDS categories (ransomware, phishing, DoS, etc.)

**Human calibration needed:**
- Adjust based on control presence
- Compare to similar architectures
- Ensure consistency across dataset

---

## Validation Workflow

### After Generation

**Automatic validation:**
```bash
# Runs automatically after each generation
PYTHONPATH=. python3 tests/validate_parser_harness.py
```

**What it checks:**
1. Attack paths are findable via BFS
2. Node counts reasonable
3. Edge counts match unique edges
4. Control detection passes (96.7% F1 target)

**Expected output:**
```
✅ 06_azure_3tier
   ✓ Attack path AP-1: Internet → Database EXISTS
   ✓ Attack path AP-2: Internet → Storage EXISTS
   ✓ Node count 8 >= 7 (minimum from paths)
   ✓ Edge count 7 >= 6 (sufficient, unique edges counted)
   → All checks passed (4 tests)
```

### If Validation Fails

**Common issues:**

1. **Node ID mismatch**
   - **Problem:** Attack path uses "DB" but parser found "Database"
   - **Fix:** Check parsed node IDs with:
     ```bash
     python3 -c "from chatbot.parsers.mermaid_parser import parse_mermaid_file; import json; r=parse_mermaid_file('file.mmd'); print(json.dumps(list(r['nodes'].keys()), indent=2))"
     ```
   - **Update:** Change attack path to use exact node ID

2. **Attack path not findable**
   - **Problem:** Path ["A", "C"] doesn't exist, should be ["A", "B", "C"]
   - **Fix:** Verify edge connectivity:
     ```bash
     python3 -c "from chatbot.parsers.mermaid_parser import parse_mermaid_file; r=parse_mermaid_file('file.mmd'); print([(e['source'], e['target']) for e in r['edges']])"
     ```

3. **Control detection mismatch**
   - **Problem:** Expected "firewall" but node says "Router - No Firewall"
   - **Fix:** Check with:
     ```bash
     python3 -c "from tests.data.architectures.control_detection import detect_controls_in_text; print(detect_controls_in_text('Node Label Here'))"
     ```

---

## Ground Truth Schema Reference

```json
{
  "architecture": "filename.mmd",
  "description": "Brief description of architecture type",
  
  "controls_present": [
    "waf",
    "load balancer",
    "mfa"
  ],
  
  "controls_missing": [
    "edr",
    "backup",
    "encryption at rest"
  ],
  
  "expected_attack_paths": [
    {
      "id": "AP-1",
      "entry": "Internet",
      "target": "Database",
      "path": ["Internet", "WAF", "LoadBalancer", "WebServer", "Database"],
      "techniques": ["T1190", "T1078", "T1213"],
      "technique_names": [
        "Exploit Public-Facing Application",
        "Valid Accounts",
        "Data from Information Repositories"
      ],
      "rationale": "Main attack path through web tier with perimeter controls"
    }
  ],
  
  "expected_risk_score": 55,
  "expected_defensibility": 60,
  
  "rapids_assessment": {
    "ransomware": {
      "risk": 60,
      "defensibility": 50,
      "rationale": "No backup visible, but segmentation helps contain"
    },
    "application_vulns": {
      "risk": 40,
      "defensibility": 70,
      "rationale": "WAF and load balancer provide good protection"
    },
    "phishing": {
      "risk": 65,
      "defensibility": 40,
      "rationale": "MFA missing, credentials could be compromised"
    },
    "insider_threat": {
      "risk": 55,
      "defensibility": 55,
      "rationale": "Segmentation present but no access logging visible"
    },
    "dos": {
      "risk": 35,
      "defensibility": 75,
      "rationale": "Load balancer provides DoS protection"
    },
    "supply_chain": {
      "risk": 50,
      "defensibility": 50,
      "rationale": "Standard dependencies, no special protections"
    }
  },
  
  "rationale": "Overall 2-3 sentence assessment of security posture"
}
```

---

## Scoring Guidelines

### Risk Score (0-100, higher = worse)

- **90-100**: Worst case (flat network, no controls, everything exposed)
- **70-89**: Poor (minimal controls, direct Internet access to sensitive data)
- **50-69**: Moderate (some controls, but gaps in coverage)
- **30-49**: Good (defense-in-depth, most controls present)
- **0-29**: Excellent (comprehensive controls, minimal attack surface)

### Defensibility Score (0-100, higher = better)

- **0-20**: No defenses, attacker wins easily
- **21-40**: Minimal defenses, attacker succeeds with moderate effort
- **41-60**: Some defenses, attacker needs skill and time
- **61-80**: Good defenses, attacker needs significant resources
- **81-100**: Strong defenses, attacker faces high barriers

### Consistency Check

Compare to reference architectures:

- **01_minimal_vulnerable**: Risk 90, Defensibility 10 (baseline worst)
- **02_minimal_defended**: Risk 40, Defensibility 70 (baseline good)
- **05_legacy_flat_network**: Risk 95, Defensibility 5 (absolute worst)
- **10_complex_enterprise**: Risk 45, Defensibility 65 (best practice)

---

## Example: Step-by-Step Generation

### 1. Start Generation

```bash
python3 tests/generate_ground_truth.py tests/data/architectures/06_azure_3tier.mmd
```

### 2. Review Auto-Detected Controls

```
Auto-detected controls: ['load balancer', 'network segmentation', 'waf']
```

**Check:** Does this match what you see in the diagram?

### 3. Review LLM-Generated Attack Paths

```json
"expected_attack_paths": [
  {
    "entry": "Internet",
    "target": "Database",
    "path": ["Internet", "AppGateway", "WebTier", "AppTier", "Database"]
  }
]
```

**Validate:**
- Are node IDs correct? (Check .mmd file)
- Does path make sense? (Can you trace it?)
- Are techniques appropriate? (T1190 for Internet entry = correct)

### 4. Validate Risk Scores

```json
"expected_risk_score": 55,
"expected_defensibility": 60
```

**Check:**
- Compared to 05_legacy (risk 95): Is this better? ✓
- Compared to 10_enterprise (risk 45): Is this worse? ✓
- Matches controls present? (WAF + segmentation = moderate risk) ✓

### 5. Accept or Correct

```
Options:
  [a] Accept as-is         ← Choose if everything looks good
  [c] Correct specific fields  ← Fix individual items
  [e] Edit JSON manually   ← Full control
```

### 6. Automatic Validation

```
✅ Validation passed!
```

**If failed:** Read error message, fix in JSON, re-run validation

---

## Troubleshooting

### LLM Returns Invalid JSON

**Error:** `json.JSONDecodeError: Expecting value`

**Fix:**
1. LLM sometimes adds explanation text before/after JSON
2. Generator automatically strips ```json blocks
3. If still fails, use `--no-llm` and fill manually

### LLM Rate Limited (429 Error)

**Error:** `Rate limit exceeded`

**Fix:**
1. Wait 60 seconds, retry
2. Use `--no-llm` for batch generation
3. Process in smaller batches (5 at a time)

### Node IDs Don't Match

**Error:** `Attack path AP-1: NodeX → NodeY NOT FOUND`

**Fix:**
```bash
# Get exact node IDs from parser
python3 -c "
from chatbot.parsers.mermaid_parser import parse_mermaid_file
result = parse_mermaid_file('file.mmd')
print('Node IDs:', list(result['nodes'].keys()))
"
```

Update ground truth JSON to use exact IDs.

### Control Detection Mismatch

**Error:** `False positives: encryption`

**Fix:**
```bash
# Test detection on specific label
python3 -c "
from tests.data.architectures.control_detection import detect_controls_in_text
print(detect_controls_in_text('Your Node Label Here'))
"
```

Either:
- Update ground truth to match detection
- Fix node label in .mmd file
- Add keyword to control_detection.py

---

## Best Practices

### 1. Generate in Batches

Process 5-7 architectures at a time, then validate as a group:

```bash
# Generate batch
for i in 04 06 07 08 09; do
    python3 tests/generate_ground_truth.py tests/data/architectures/${i}_*.mmd
done

# Validate batch
PYTHONPATH=. python3 tests/validate_parser_harness.py
```

### 2. Review High-Risk Architectures Carefully

Architectures with risk > 80 or defensibility < 20 need extra attention:
- Verify attack paths are realistic (not just theoretical)
- Check risk scores match control absence
- Ensure consistency with similar architectures

### 3. Use Existing Ground Truth as Templates

Copy structure from similar architecture:
- Cloud 3-tier: Use 03_aws_3tier.json as template
- Flat network: Use 05_legacy_flat_network.json
- AI systems: Use 21_agentic_ai_system.json

### 4. Version Control Ground Truth

Commit ground truth as you generate:

```bash
git add tests/data/ground_truth/*.json
git commit -m "test: Add ground truth for architectures 06-09"
```

### 5. Run Full Validation Before PR

```bash
# Validate parser
PYTHONPATH=. python3 tests/validate_parser_harness.py

# Validate control detection
PYTHONPATH=. python3 tests/test_control_detection.py
```

Both should show ≥90% accuracy.

---

## Performance Metrics

### Current (7/21 architectures)

| Metric | Value | Target |
|--------|-------|--------|
| Parser validation | 100% (35/35 tests) | ≥95% |
| Control detection F1 | 96.7% | ≥70% |
| Coverage | 33% (7/21) | 100% |
| Time per file | 30 min (manual) | <10 min |

### Projected (21/21 architectures with automation)

| Metric | Estimated | Target |
|--------|-----------|--------|
| Parser validation | ≥95% | ≥95% |
| Control detection F1 | ≥90% | ≥70% |
| Coverage | 100% (21/21) | 100% |
| Total time investment | 5 hours (3 done + 2 remaining) | <6 hours |

---

## Next Steps

### Immediate (Complete Phase 3A)

1. Generate ground truth for remaining 14 architectures
2. Run full validation suite
3. Document any new edge cases discovered
4. Update control_detection.py if needed

### Future (Scale Beyond 21)

1. **Add new architecture types** (Kubernetes, serverless, OT/SCADA)
2. **Community contributions** - Others can generate ground truth for their diagrams
3. **Continuous validation** - CI/CD runs validation on every commit
4. **LLM fine-tuning** - Use validated ground truth to fine-tune models

---

## Summary: Why This Matters

**Without Ground Truth:**
- ❓ Unknown if algorithms work correctly
- ❓ Can't measure accuracy improvements
- ❓ No regression detection
- ❓ Manual testing only

**With Ground Truth (Automated):**
- ✅ Measurable accuracy (96.7% F1 currently)
- ✅ Regression testing in CI/CD
- ✅ Algorithm validation before deployment
- ✅ Confidence in production use
- ✅ Scales to 100+ architectures with <1 hour per 10 files

**ROI:** 5 hours investment → validates algorithms worth 15-20 hours of implementation

---

*Version: 1.0*  
*Last Updated: 2026-05-02*  
*Status: 7/21 complete, automation ready*
