# Architecture Validation Guide

**Last Updated:** 2026-05-09  
**Purpose:** Validate architecture diagrams before threat analysis

---

## Overview

Before running threat analysis, validate your architecture to ensure complete and accurate results. The validation checks for **orphan nodes** - components that won't be analyzed because they're unreachable from entry points.

---

## Quick Start

```bash
# Validate your architecture
./demo_architecture.sh --validate-orphan your_architecture.mmd

# If validation passes, run analysis
python3 -m chatbot.main --gen-arch-truth your_architecture.mmd
```

---

## What Are Orphan Nodes?

**Definition:** Nodes with outbound connections but unreachable from entry points

**Example:**
```mermaid
flowchart TB
    Internet((Internet))
    WebApp[Web App]
    Database[(Database)]
    
    Internet --> WebApp
    WebApp --> Database
    
    AdminPortal[Admin Portal]  ❌ ORPHAN!
    AdminPortal --> Database   # Can attack, but unreachable
```

**Impact:**
- ❌ Not included in attack path analysis
- ❌ Not included in threat assessment
- ⚠️ Confidence penalty (~16% per orphan)
- ⚠️ Incomplete security recommendations

---

## Validation Checks

The validator performs 5 checks:

### 1. File Exists ✅
Verifies the .mmd file is accessible

### 2. Valid Mermaid Syntax ✅
Checks for `flowchart` or `graph` declaration

### 3. Has Nodes ✅
Architecture needs at least 2 nodes

### 4. Has Connections ✅
Architecture needs at least 1 edge (-->)

### 5. No Orphan Nodes ✅
**Most Important:** Ensures all nodes reachable from entry points

---

## Validation Output

### ✅ Clean Architecture
```
═══════════════════════════════════════════════════════════════════════════
📋 PRE-ANALYSIS VALIDATION: my_architecture
═══════════════════════════════════════════════════════════════════════════

✅ Architecture file found
✅ Valid Mermaid syntax
✅ Architecture has 8 nodes
✅ Architecture has 12 connections

🔍 Checking for orphan nodes...
   ✅ No orphan nodes found

✅ Validation complete - ready for analysis

✅ Architecture is ready for threat analysis!

Run analysis:
  python3 -m chatbot.main --gen-arch-truth my_architecture.mmd
```

### ❌ Orphan Nodes Found
```
═══════════════════════════════════════════════════════════════════════════
📋 PRE-ANALYSIS VALIDATION: my_architecture
═══════════════════════════════════════════════════════════════════════════

✅ Architecture file found
✅ Valid Mermaid syntax
✅ Architecture has 8 nodes
✅ Architecture has 12 connections

🔍 Checking for orphan nodes...

   ⚠️  ORPHAN NODES DETECTED!

   📍 my_architecture
   Entry points: Internet, Partners
   ❌ AdminPortal (Admin Portal) → PrimaryDB, Monitoring
   ❌ Monitoring (Monitoring System) → WebApp

   Orphan nodes are components that:
   • Have outbound connections (can attack other components)
   • Are unreachable from entry points (Internet, VPN, Users)
   • Will NOT be analyzed in threat modeling

   Impact: Confidence penalty (~16% per orphan)

   Options:
   1) Fix the architecture (add entry point or connection)
   2) Skip this architecture for now
   3) Continue anyway (NOT RECOMMENDED - incomplete analysis)

   Choose [1/2/3]:
```

---

## Fixing Orphan Nodes

When orphans are detected, you have 3 options:

### Option 1: Add Entry Point (Recommended)

**When:** Node represents external access method (VPN, Admin Console, API)

**Before:**
```mermaid
flowchart TB
    Internet((Internet))
    Internet --> WebApp --> Database
    
    AdminPortal --> Database  ❌ ORPHAN
```

**After:**
```mermaid
flowchart TB
    Internet((Internet))
    VPN((VPN Remote Access))  ← NEW ENTRY POINT
    
    Internet --> WebApp --> Database
    VPN --> AdminPortal  ← CONNECTED
    AdminPortal --> Database
```

**Attack Path Created:** `VPN → AdminPortal → Database`

---

### Option 2: Connect to Existing Path

**When:** Node is internal component accessed via existing entry

**Before:**
```mermaid
flowchart TB
    Internet --> WebApp --> AppServer
    
    Monitoring --> AppServer  ❌ ORPHAN
```

**After:**
```mermaid
flowchart TB
    Internet --> WebApp --> AppServer
    AppServer --> Monitoring  ← CONNECTED
    Monitoring --> Database
```

**Attack Path Extended:** `Internet → WebApp → AppServer → Monitoring → Database`

---

### Option 3: Remove Node

**When:** Node is out of scope for this threat model

**Before:**
```mermaid
flowchart TB
    Internet --> WebApp
    ExternalAPI --> ThirdPartyDB  ❌ ORPHAN, out of scope
```

**After:**
```mermaid
flowchart TB
    Internet --> WebApp
    # ExternalAPI removed - analyzed separately
```

---

## Common Mistakes

### ❌ Mistake 1: Assuming Subgraph = Connection

```mermaid
subgraph Application
    WebApp
end

subgraph Management
    AdminPortal
end

# Mistake: Assuming both reachable just because they're in subgraphs
# Reality: AdminPortal is orphan without entry point!
```

**Fix:** Add explicit connections even within/across subgraphs.

---

### ❌ Mistake 2: Monitoring "Just Exists"

```mermaid
Internet --> WebApp --> Database

Monitoring --> WebApp  ❌ How is Monitoring accessed?
Monitoring --> Database
```

**Fix:** Show monitoring architecture:
```mermaid
VPN --> AdminPortal --> Monitoring
Monitoring --> WebApp
```

---

### ❌ Mistake 3: Out-of-Band = Out-of-Diagram

```mermaid
Internet --> WebApp

# "Admin access is via out-of-band network"
# Mistake: Not showing it = not analyzing it!
```

**Fix:** Show out-of-band explicitly:
```mermaid
Internet --> WebApp
OutOfBand((Out-of-Band Network)) --> AdminInterface
```

---

## Integration with Analysis Workflow

### Recommended Workflow

```bash
# Step 1: Create architecture diagram
vi my_architecture.mmd

# Step 2: Validate for orphan nodes
./demo_architecture.sh --validate-orphan my_architecture.mmd

# Step 3: Fix any orphans (if found)
# ... edit my_architecture.mmd ...

# Step 4: Re-validate
./demo_architecture.sh --validate-orphan my_architecture.mmd

# Step 5: Run full threat analysis
python3 -m chatbot.main --gen-arch-truth my_architecture.mmd

# Step 6: Review reports
ls -la report/my_architecture/
```

---

## Validation in Demo Script

The `demo_architecture.sh` script has two modes:

### Demo Mode (Default)
Validates both test architectures before running comparison:
```bash
./demo_architecture.sh
```

**What it does:**
1. Validates 01_minimal_vulnerable.mmd
2. Validates 02_minimal_defended.mmd
3. If both pass, runs full comparison demo
4. If either fails, stops with error message

### Validate-Only Mode
Checks a specific architecture:
```bash
./demo_architecture.sh --validate-orphan your_architecture.mmd
```

**What it does:**
1. Runs all 5 validation checks
2. If orphans found, offers 3 options (fix/skip/continue)
3. Exit code 0 = ready, 1 = needs fixes

---

## Orphan Detection Script

The validation uses `scripts/check_orphans.py`:

```bash
# Check specific architecture
python3 scripts/check_orphans.py my_architecture

# Check all architectures
python3 scripts/check_orphans.py

# Check multiple architectures
python3 scripts/check_orphans.py 10_complex_enterprise 03_aws_3tier
```

**Output:**
```
🔍 Checking 1 architecture for orphan nodes...

================================================================================
ORPHAN DETECTION SUMMARY
================================================================================

Total: 1 architecture
With orphans: 0
No report: 0

✅ No orphans found in any architecture!
```

---

## Best Practices

### When Creating Diagrams

1. **Start with entry points:**
   ```mermaid
   Internet((Internet))
   Users((Internal Users))
   VPN((VPN Access))
   ```

2. **Connect all components to entry points:**
   - Every node should be reachable via at least one entry point
   - If unreachable, ask: "How is this accessed?"

3. **Identify management paths explicitly:**
   ```mermaid
   VPN --> AdminPortal
   AdminPortal --> Monitoring
   Monitoring --> AllSystems
   ```

4. **Use subgraphs for clarity, not isolation:**
   ```mermaid
   subgraph Management
       AdminPortal
       Monitoring
   end
   
   # Still connect to entry!
   VPN --> AdminPortal
   ```

### When Reviewing Diagrams

1. Run orphan detection before analysis
2. For each orphan, ask: "How is this accessed?"
3. Add entry point OR connect to existing path
4. Re-validate until clean
5. Then run full analysis

---

## Confidence Impact

### With Orphans (Before Fix)
```
Architecture: 10_complex_enterprise
Nodes: 17
Orphans: 2 (AdminPortal, Monitoring)

Attack paths: 3 (covering 15/17 nodes)
Confidence: 84% (-16% penalty for orphans)

⚠️ AdminPortal and Monitoring NOT analyzed
⚠️ Incomplete threat assessment
⚠️ Missing security recommendations
```

### Without Orphans (After Fix)
```
Architecture: 10_complex_enterprise
Nodes: 17
Orphans: 0

Attack paths: 5 (covering 17/17 nodes)
Confidence: 100% (no penalties)

✅ All nodes analyzed
✅ Complete threat assessment
✅ Comprehensive security recommendations
```

---

## Troubleshooting

### Validation Says "No previous report found"

**Cause:** Architecture hasn't been analyzed yet

**Solution:** This is expected - orphan check will run after first analysis. To check immediately:
```bash
# Generate initial report
python3 -m chatbot.main --gen-arch-truth your_architecture.mmd

# Then validate
./demo_architecture.sh --validate-orphan your_architecture.mmd
```

### False Positive: Node Not Actually Orphan

**Cause:** Entry point not detected correctly

**Check:** Ensure entry points follow naming conventions:
- `Internet((Internet))`
- `VPN((VPN Remote Access))`
- `Users((Internal Users))`
- `Mobile((Mobile Users))`

**Fix:** Use explicit entry point notation with double parentheses `(())`

### Validation Passes But Analysis Shows Low Confidence

**Other issues may exist:**
- Incomplete MITRE technique coverage
- Missing controls in control library
- Insufficient layered defense

**Solution:** Review full confidence breakdown in ground_truth.json

---

## References

- **[Orphan Remediation Guide](../../archive/session-notes/ORPHAN_REMEDIATION.md)** - Detailed examples
- **[Complex Enterprise Fix](../../tests/data/architectures/10_complex_enterprise.mmd)** - Real fix example
- **[Orphan Detection Script](../../scripts/check_orphans.py)** - Source code

---

## Summary

**Purpose:** Ensure complete threat analysis by detecting unreachable components

**Usage:** `./demo_architecture.sh --validate-orphan your_architecture.mmd`

**Benefits:**
- ✅ Catch orphan nodes before analysis
- ✅ Maintain 100% confidence scores
- ✅ Get complete security recommendations
- ✅ Save time (no re-analysis needed)

**Best Practice:** Always validate before running full analysis!

---

**Document Version:** 1.0  
**Date:** 2026-05-09  
**Status:** Current
